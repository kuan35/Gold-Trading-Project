"""Synthetic subprocess fixtures only: no model inference or user credentials."""
import json
import subprocess
from pathlib import Path

import pytest
from backend import claude_code
REAL_COMMAND=claude_code.command


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    claude_code.clear_probe_cache()
    monkeypatch.setenv('GOLD_CLAUDE_MODEL','sonnet')
    monkeypatch.setattr(claude_code,'command',lambda: ['node','C:/official/claude/cli.js'])


def test_completion_is_isolated_no_tools_no_shell_and_no_app_credentials(monkeypatch):
    monkeypatch.setenv('CTRADER_CLIENT_SECRET','private-broker')
    monkeypatch.setenv('GOLD_LLM_API_KEY','private-groq')
    monkeypatch.setenv('ANTHROPIC_API_KEY','unintended-api-billing')
    monkeypatch.setenv('NODE_OPTIONS','--require private-hook')
    seen={}
    class Process:
        returncode=0
        def __init__(self,args,**kw):
            seen.update(args=args,**kw)
            assert Path(kw['cwd']).is_dir() and not list(Path(kw['cwd']).iterdir())
        def communicate(self,input=None,timeout=None):
            assert input=='合成盤面；不含真實案例'
            return json.dumps({'type':'result','subtype':'success','is_error':False,'result':'{"sections":[]}'}),''
    monkeypatch.setattr(claude_code.subprocess,'Popen',Process)
    r=claude_code.complete('只解釋給定facts','合成盤面；不含真實案例',json_output=True)
    assert r['status']=='ok' and json.loads(r['text'])=={'sections':[]}
    assert seen['shell'] is False and seen['args'][seen['args'].index('--tools')+1]==''
    assert '--safe-mode' in seen['args'] and '--no-session-persistence' in seen['args']
    assert '--strict-mcp-config' in seen['args'] and '--disable-slash-commands' in seen['args']
    assert all(k not in seen['env'] for k in ('CTRADER_CLIENT_SECRET','GOLD_LLM_API_KEY','ANTHROPIC_API_KEY','NODE_OPTIONS'))
    assert not Path(seen['cwd']).exists()


@pytest.mark.parametrize('code,stdout,stderr,status',[
    (1,'','Not logged in. Please run /login','authentication_failed'),
    (1,'','You have hit your usage limit','rate_limited'),
    (0,'not json','','invalid_response'),
    (0,json.dumps({'type':'result','subtype':'error_max_turns','is_error':True}),'','truncated'),
    (1,json.dumps({'type':'result','subtype':'error_max_turns','is_error':True}),'','truncated'),
    (0,json.dumps({'type':'result','subtype':'success','is_error':False,'result':'plain text'}),'','invalid_response'),
])
def test_safe_failures_never_return_raw_error(monkeypatch,code,stdout,stderr,status):
    class Process:
        returncode=code
        def __init__(self,*a,**kw):pass
        def communicate(self,input=None,timeout=None):return stdout,stderr+' sk-test-private'
    monkeypatch.setattr(claude_code.subprocess,'Popen',Process)
    r=claude_code.complete('system','synthetic',json_output=True)
    assert r['status']==status and r['text'] is None and 'sk-test-private' not in json.dumps(r)


def test_timeout_terminates_owned_process_and_releases_slot(monkeypatch):
    killed=[]
    class Process:
        returncode=None
        def __init__(self,*a,**kw):pass
        def communicate(self,*a,**kw):raise subprocess.TimeoutExpired('claude',1)
    monkeypatch.setattr(claude_code.subprocess,'Popen',Process)
    monkeypatch.setattr(claude_code,'terminate',lambda p:killed.append(p))
    assert claude_code.complete('s','q')['status']=='timeout'
    assert claude_code.complete('s','q')['status']=='timeout'
    assert len(killed)==2


def test_busy_does_not_start_another_process(monkeypatch):
    monkeypatch.setattr(claude_code.subprocess,'Popen',lambda *a,**k:pytest.fail('must not start'))
    with claude_code.SLOT:
        assert claude_code.complete('s','q')['status']=='busy'


def test_auth_probe_returns_only_readiness_and_is_cached(monkeypatch):
    calls=[]
    def run(args,**kw):
        calls.append(args)
        assert '--safe-mode' in args and 'auth' in args and 'status' in args and '-p' not in args
        return subprocess.CompletedProcess(args,1,json.dumps({'loggedIn':False,'authMethod':'none','email':'PRIVATE'}),'')
    monkeypatch.setattr(claude_code.subprocess,'run',run)
    assert claude_code.configuration()==dict(installed=True,authenticated=False,reason='authentication_required')
    assert 'PRIVATE' not in json.dumps(claude_code.configuration()) and len(calls)==1


def test_missing_cli_is_reported_without_running_anything(monkeypatch):
    monkeypatch.setattr(claude_code,'command',lambda:None)
    assert claude_code.configuration()['reason']=='cli_not_installed'
    assert claude_code.complete('s','q')['status']=='cli_not_installed'


def test_npm_native_wrapper_resolves_direct_exe_without_invoking_shell(monkeypatch,tmp_path):
    wrapper=tmp_path/'claude.cmd';wrapper.write_text('wrapper must never execute')
    exe=tmp_path/'node_modules/@anthropic-ai/claude-code/bin/claude.exe'
    exe.parent.mkdir(parents=True);exe.write_bytes(b'placeholder')
    monkeypatch.setattr(claude_code,'command',REAL_COMMAND)
    monkeypatch.setenv('GOLD_CLAUDE_EXECUTABLE',str(wrapper))
    assert claude_code.command()==[str(exe)]


def test_diagnostic_preview_and_default_mode_never_infer(monkeypatch,capsys):
    from scripts import check_claude_local as diagnostic
    monkeypatch.setattr(diagnostic,'complete',lambda *a,**kw:pytest.fail('explicit flag required'))
    assert diagnostic.main(['--preview'])==0
    assert 'synthetic_connection_test' in capsys.readouterr().out
    monkeypatch.setattr(diagnostic,'configuration',lambda:dict(installed=True,authenticated=False,reason='authentication_required'))
    assert diagnostic.main([])==2
    assert diagnostic.main(['--allow-external'])==2
    assert '"inference_requested": false' in capsys.readouterr().out
