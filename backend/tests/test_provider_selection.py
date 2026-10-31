import os
from backend import assistant,codex_local,claude_code

def test_request_provider_isolated_without_environment_mutation(monkeypatch):
 monkeypatch.setenv('GOLD_ENABLE_LLM','true');monkeypatch.setenv('GOLD_LLM_PROVIDER','claude_code')
 monkeypatch.setattr(codex_local,'configuration',lambda:dict(installed=True,authenticated=True,reason='ready'))
 calls=[]
 monkeypatch.setattr(codex_local,'complete',lambda *a,**kw:(calls.append(kw) or dict(status='ok',text='{}',model='model-a',provider='codex')))
 monkeypatch.setattr(claude_code,'complete',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('wrong provider')))
 r=assistant.explain_context({},'合成',catalog={},request_opt_in=True,provider_override='codex',model_override='model-a',effort_override='low')
 assert r['provider']=='codex' and calls[0]['model']=='model-a'
 assert os.environ['GOLD_LLM_PROVIDER']=='claude_code'
 assert assistant.explain_context({},'合成',provider_override='program')['status']=='disabled'

def test_codex_api_fields_validate_separately_from_claude(monkeypatch):
 from backend.app import LiveChatInput,_model_options
 from fastapi import HTTPException
 monkeypatch.setattr(codex_local,'configuration',lambda:dict(authenticated=True,model='model-a',default_effort='low',models=[dict(id='model-a',efforts=['low'])]))
 assert _model_options(LiveChatInput(message='問',provider='codex',codex_model='model-a',codex_effort='low'))==dict(provider='codex',model='model-a',effort='low')
 import pytest
 with pytest.raises(HTTPException):_model_options(LiveChatInput(message='問',provider='codex',codex_model='not-available',codex_effort='low'))
