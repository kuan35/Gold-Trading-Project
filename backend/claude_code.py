"""Text-only official CLI adapter. Never reads tokens or exposes agent tools."""
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time

SLOT=threading.Lock()
MODELS=('sonnet','opus','haiku')
EFFORTS=('low','medium','high','xhigh','max')
_PROBE_LOCK=threading.Lock()
_probe=None


def command():
    candidate=os.getenv('GOLD_CLAUDE_EXECUTABLE','').strip() or shutil.which('claude')
    if not candidate:return None
    path=Path(candidate).resolve()
    if not path.is_file():return None
    # Do not execute npm cmd/PowerShell wrappers: their shell quoting cannot
    # safely carry arbitrary prompts. Invoke the official Node entrypoint.
    if path.suffix.lower() in ('.cmd','.ps1','.bat'):
        package=path.parent/'node_modules/@anthropic-ai/claude-code'
        native=package/'bin/claude.exe'
        path=native if native.is_file() else package/'cli.js'
        if not path.is_file():return None
    if path.suffix.lower()=='.js':
        node=shutil.which('node')
        return [node,str(path)] if node else None
    return [str(path)]


def environment():
    allowed={'PATH','PATHEXT','SYSTEMROOT','WINDIR','COMSPEC','TEMP','TMP','APPDATA',
      'LOCALAPPDATA','USERPROFILE','HOMEDRIVE','HOMEPATH','HOME','LANG','LC_ALL',
      'PROGRAMFILES','PROGRAMFILES(X86)','PROGRAMDATA','USERDOMAIN','USERNAME',
      'CLAUDE_CONFIG_DIR','NODE_EXTRA_CA_CERTS','HTTPS_PROXY','HTTP_PROXY','NO_PROXY'}
    env={k:v for k,v in os.environ.items() if k.upper() in allowed}
    env.update(CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1',CLAUDE_CODE_MAX_OUTPUT_TOKENS='2048')
    return env


def safe_flags():
    # safe-mode preserves official authentication while disabling project and
    # user customizations; bare mode instead requires API authentication.
    return ['--safe-mode','--tools','','--disallowedTools','mcp__*',
      '--strict-mcp-config','--mcp-config','{"mcpServers":{}}',
      '--setting-sources','','--settings','{"disableAllHooks":true}',
      '--disable-slash-commands']


def process_options(cwd):
    kw=dict(cwd=cwd,env=environment(),shell=False,stdin=subprocess.PIPE,
      stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace')
    if os.name=='nt':kw['creationflags']=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP
    else:kw['start_new_session']=True
    return kw


def clear_probe_cache():
    global _probe
    with _PROBE_LOCK:_probe=None


def configuration():
    global _probe
    cmd=command()
    if not cmd:return dict(installed=False,authenticated=False,reason='cli_not_installed')
    key=(tuple(cmd),os.getenv('CLAUDE_CONFIG_DIR',''))
    with _PROBE_LOCK:
        if _probe and _probe[0]==key and time.monotonic()-_probe[1]<10:return dict(_probe[2])
        result=dict(installed=True,authenticated=False,reason='cli_probe_failed')
        try:
            with tempfile.TemporaryDirectory(prefix='gold-desk-claude-probe-') as cwd:
                options=process_options(cwd);options.pop('stdin')
                p=subprocess.run(cmd+safe_flags()+['auth','status'],timeout=6,**options)
            body=json.loads(p.stdout)
            if type(body.get('loggedIn')) is bool:
                ready=p.returncode==0 and body['loggedIn']
                result.update(authenticated=ready,reason='ready' if ready else 'authentication_required')
        except (OSError,subprocess.TimeoutExpired,ValueError,TypeError,AttributeError):pass
        _probe=(key,time.monotonic(),dict(result))
        return result


def terminate(process):
    """Only terminate the subprocess tree created by this invocation."""
    try:
        if os.name=='nt':
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],
              stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5,
              creationflags=subprocess.CREATE_NO_WINDOW,check=False)
        else:os.killpg(process.pid,signal.SIGKILL)
    except (OSError,subprocess.TimeoutExpired):pass
    try:
        if process.poll() is None:process.kill()
        process.communicate(timeout=3)
    except (OSError,subprocess.TimeoutExpired):pass


def failure_status(text):
    value=text.lower()
    if any(s in value for s in ('not logged in','/login','login required','authentication','invalid api key','oauth token expired')):return 'authentication_failed'
    if any(s in value for s in ('rate limit','usage limit','hit your limit','429','overloaded')):return 'rate_limited'
    return 'provider_error'


def complete(system,prompt,*,json_output=False,model=None,effort=None):
    model=(model or os.getenv('GOLD_CLAUDE_MODEL','sonnet')).strip()
    effort=(effort or os.getenv('GOLD_CLAUDE_EFFORT','medium')).strip()
    result=dict(status='provider_error',text=None,model=model,requested_effort=effort,provider='claude_code')
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._:-]{0,100}',model):return dict(result,status='invalid_configuration')
    if effort not in EFFORTS:return dict(result,status='invalid_configuration')
    try:timeout=float(os.getenv('GOLD_CLAUDE_TIMEOUT_SECONDS','120'))
    except ValueError:return dict(result,status='invalid_configuration')
    if not 1<=timeout<=150 or len(prompt)>180_000 or len(system)>30_000:return dict(result,status='invalid_configuration')
    cmd=command()
    if not cmd:return dict(result,status='cli_not_installed')
    if not SLOT.acquire(blocking=False):return dict(result,status='busy')
    try:
        with tempfile.TemporaryDirectory(prefix='gold-desk-claude-') as cwd:
            argv=cmd+safe_flags()+['-p','--output-format','json','--no-session-persistence',
                '--max-turns','1','--model',model,'--effort',effort,'--system-prompt',system+('\n只回覆 JSON 物件，不要 Markdown。' if json_output else '')]
            process=subprocess.Popen(argv,**process_options(cwd))
            try:stdout,stderr=process.communicate(input=prompt,timeout=timeout)
            except subprocess.TimeoutExpired:
                terminate(process)
                return dict(result,status='timeout')
        if len(stdout)>1_000_000 or len(stderr)>1_000_000:return dict(result,status='invalid_response')
        try:body=json.loads(stdout)
        except ValueError:return dict(result,status=failure_status(stdout+'\n'+stderr) if process.returncode else 'invalid_response')
        if not isinstance(body,dict):return dict(result,status='invalid_response')
        if body.get('subtype') in ('error_max_turns','error_max_budget_usd','error_max_structured_output_retries'):
            return dict(result,status='truncated')
        if process.returncode!=0:return dict(result,status=failure_status(stdout+'\n'+stderr))
        if body.get('type')!='result' or body.get('subtype')!='success' or body.get('is_error') is not False:
            return dict(result,status=failure_status(stdout))
        text=body.get('result')
        if not isinstance(text,str) or not text.strip():return dict(result,status='invalid_response')
        if json_output:
            try:
                parsed=json.loads(text)
                if not isinstance(parsed,dict):raise ValueError('expected object')
            except ValueError:return dict(result,status='invalid_response')
        return dict(result,status='ok',text=text.strip())
    except OSError:return dict(result,status='cli_unavailable')
    finally:SLOT.release()
