import json,os
import pytest
from pydantic import ValidationError
from backend import assistant,claude_code


def test_request_options_reach_cli_and_do_not_modify_environment(monkeypatch):
    monkeypatch.setenv('GOLD_ENABLE_LLM','true');monkeypatch.setenv('GOLD_LLM_PROVIDER','claude_code')
    monkeypatch.setenv('GOLD_CLAUDE_MODEL','sonnet');monkeypatch.setenv('GOLD_CLAUDE_EFFORT','medium')
    monkeypatch.setattr(claude_code,'configuration',lambda:dict(installed=True,authenticated=True,reason='ready'))
    calls=[]
    def complete(*a,**kw):
        calls.append(kw)
        return dict(status='ok',text='{}',model=kw.get('model') or 'sonnet',requested_effort=kw.get('effort') or 'medium',provider='claude_code')
    monkeypatch.setattr(claude_code,'complete',complete)
    for model,effort in [('opus','max'),('haiku','low')]:
        result=assistant.explain_context({},'合成',catalog={},request_opt_in=True,model_override=model,effort_override=effort)
        assert result['model']==model and result['requested_effort']==effort
    assistant.explain_context({},'合成',catalog={},request_opt_in=True)
    assert calls[-1].get('model') is None and calls[-1].get('effort') is None
    assert os.environ['GOLD_CLAUDE_MODEL']=='sonnet' and os.environ['GOLD_CLAUDE_EFFORT']=='medium'


def test_api_models_accept_only_supported_options_and_keep_old_request_default():
    from backend.app import LiveChatInput,DraftChatInput,CaseReviewInput
    base=[(LiveChatInput,dict(message='合成')),(DraftChatInput,dict(message='合成',draft_id='x')),(CaseReviewInput,{})]
    for cls,fields in base:
        v=cls(**fields,model='opus',effort='xhigh')
        assert v.model=='opus' and v.effort=='xhigh'
        for bad in [dict(model='shell --run'),dict(effort='ultracode')]:
            with pytest.raises(ValidationError):cls(**fields,**bad)
    assert not LiveChatInput(message='合成').llm_enabled


def test_http_service_rejects_claude_specific_selection(monkeypatch):
    from fastapi import HTTPException
    from backend.app import _model_options,LiveChatInput
    monkeypatch.setenv('GOLD_LLM_PROVIDER','openai_compatible')
    with pytest.raises(HTTPException) as exc:_model_options(LiveChatInput(message='合成',model='opus'))
    assert exc.value.status_code==422


def test_model_and_effort_are_separate_argv_values(monkeypatch):
    args=[]
    monkeypatch.setattr(claude_code,'command',lambda:['official-claude'])
    class Process:
        returncode=0
        def __init__(self,argv,**kw):args.extend(argv)
        def communicate(self,input=None,timeout=None):return json.dumps(dict(type='result',subtype='success',is_error=False,result='{}')),''
    monkeypatch.setattr(claude_code.subprocess,'Popen',Process)
    result=claude_code.complete('合成','合成',json_output=True,model='opus',effort='max')
    assert result['status']=='ok' and result['requested_effort']=='max'
    assert args[args.index('--model')+1]=='opus' and args[args.index('--effort')+1]=='max'


def test_live_reply_preserves_request_effort_and_passes_the_selection(monkeypatch):
    from backend import live_assistant
    from backend.tests.test_live_assistant import snapshot,NOW
    context=live_assistant.build_live_context(snapshot(),now=NOW);seen=[]
    def fake(*a,**kw):
        seen.append(kw)
        return dict(status='timeout',text=None,model='opus',requested_effort='high')
    monkeypatch.setattr(live_assistant,'explain_context',fake)
    reply=live_assistant.respond_context(context,'分析',enabled=True,model='opus',effort='high')
    assert seen[0]['model_override']=='opus' and seen[0]['effort_override']=='high'
    assert reply['model']=='opus' and reply['requested_effort']=='high'
