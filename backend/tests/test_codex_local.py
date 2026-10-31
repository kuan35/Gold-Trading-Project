import json,os
from pathlib import Path
from backend import codex_local as c

def test_env_and_safe_arguments_have_no_broker_tokens_or_user_customizations(monkeypatch):
 monkeypatch.setenv('CTRADER_ACCESS_TOKEN','PRIVATE');monkeypatch.setenv('GOLD_LLM_API_KEY','PRIVATE')
 assert 'CTRADER_ACCESS_TOKEN' not in c.environment() and 'GOLD_LLM_API_KEY' not in c.environment()
 flags=c.exec_flags('指示')
 assert '--ignore-user-config' in flags and '--ephemeral' in flags and 'read-only' in flags
 assert 'features.shell_tool=false' in flags and 'features.hooks=false' in flags and 'features.plugins=false' in flags
 assert not any('dangerously' in s for s in flags)

def test_model_capabilities_are_sanitized_and_account_identity_not_returned():
 info=c.capabilities({'account':{'type':'chatgpt','email':'private@example.com'}}, {'data':[{'id':'a','model':'model-a','displayName':'Model A','isDefault':True,'defaultReasoningEffort':'medium','supportedReasoningEfforts':[{'reasoningEffort':'low'},{'reasoningEffort':'medium'}]}]})
 assert info['authenticated'] and info['model_options']==['model-a'] and 'email' not in str(info)
 assert info['models'][0]['efforts']==['low','medium']
 assert not c.capabilities({'account':None},{'data':[]})['authenticated']

def test_result_parser_rejects_tools_errors_and_multiple_answers():
 ok=json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'{"sections":[]}'}})+'\n'+json.dumps({'type':'turn.completed'})
 assert c.parse_output(ok,True)==('ok','{"sections":[]}')
 assert c.parse_output(ok+'\n'+json.dumps({'type':'item.started','item':{'type':'command_execution'}}),True)[0]=='tool_use_rejected'
 assert c.parse_output('{"type":"turn.failed"}',False)[0]!='ok'

def test_completion_requires_valid_capability_and_argv_is_not_shell(monkeypatch):
 monkeypatch.setattr(c,'configuration',lambda:dict(authenticated=True,models=[dict(id='model-a',efforts=['low'])],model='model-a',default_effort='low'))
 monkeypatch.setattr(c,'command',lambda:['official-codex']);calls=[]
 class Process:
  returncode=0
  def __init__(self,argv,**kwargs):calls.append((argv,kwargs))
  def communicate(self,input=None,timeout=None):return json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'{}'}})+'\n'+json.dumps({'type':'turn.completed'}),''
 monkeypatch.setattr(c.subprocess,'Popen',Process)
 r=c.complete('system','payload',json_output=True,model='model-a',effort='low');assert r['status']=='ok'
 assert calls[0][1]['shell'] is False and calls[0][0][-1]=='-' and calls[0][0][calls[0][0].index('--model')+1]=='model-a'
 assert c.complete('system','payload',model='model-a;attack',effort='low')['status']=='invalid_configuration'

def test_old_cli_without_isolation_flags_is_not_probed_or_reported_ready(monkeypatch):
 monkeypatch.setattr(c,'command',lambda:['old-codex']);monkeypatch.setattr(c,'_cache',None)
 monkeypatch.setattr(c.subprocess,'run',lambda *a,**k:type('Help',(),{'returncode':0,'stdout':'old flags only'})())
 monkeypatch.setattr(c,'RPC',lambda *a:(_ for _ in ()).throw(AssertionError('must stop before auth probe')))
 assert c.configuration()['reason']=='cli_upgrade_required'
