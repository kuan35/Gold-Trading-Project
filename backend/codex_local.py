"""Official local Codex bridge; auth stays in Codex, prompts travel over stdin."""
import json,os,re,shutil,subprocess,tempfile,threading,time,queue
from pathlib import Path
from .claude_code import environment as base_environment,terminate,process_options as base_options

SLOT=threading.Lock();_LOCK=threading.Lock();_cache=None
SAFE_FEATURES=('shell_tool','unified_exec','hooks','plugins','apps','view_image','multi_agent','multi_agent_v2','code_mode','code_mode_host','workspace_dependencies','skill_search','sleep_tool','goals')
VALID=re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,100}')

def command():
 candidate=os.getenv('GOLD_CODEX_EXECUTABLE','').strip() or shutil.which('codex')
 if not candidate and os.name=='nt':
  base=Path(os.getenv('LOCALAPPDATA',''))/'OpenAI/Codex/bin'
  hits=sorted(base.glob('*/codex.exe'),key=lambda p:p.stat().st_mtime,reverse=True) if base.is_dir() else []
  candidate=str(hits[0]) if hits else None
 if not candidate:return None
 path=Path(candidate).resolve()
 if path.suffix.lower() in ('.cmd','.ps1','.bat'):path=path.parent/'node_modules/@openai/codex/bin/codex.js'
 if not path.is_file():return None
 if path.suffix=='.js':return [shutil.which('node'),str(path)] if shutil.which('node') else None
 return [str(path)]

def environment():
 env=base_environment();env.pop('CLAUDE_CONFIG_DIR',None)
 if os.getenv('CODEX_HOME'):env['CODEX_HOME']=os.environ['CODEX_HOME']
 return env

def options(cwd):
 kw=base_options(cwd);kw['env']=environment();return kw

def restrictions():
 return [arg for feature in SAFE_FEATURES for arg in ('-c',f'features.{feature}=false')]+['-c','web_search="disabled"','-c','mcp_servers={}','-c','project_doc_max_bytes=0']

def exec_flags(system):
 return ['exec','--ignore-user-config','--ephemeral','--skip-git-repo-check','--sandbox','read-only','--json','--color','never',*restrictions(),'-c','developer_instructions='+json.dumps(system,ensure_ascii=False)]

class RPC:
 def __init__(self,cmd,cwd):
  kw=options(cwd);kw['stderr']=subprocess.DEVNULL
  self.process=subprocess.Popen(cmd+['app-server','--stdio',*restrictions()],**kw);self.messages=queue.Queue();self.ident=0
  def read():
   total=0
   try:
    while True:
     line=self.process.stdout.readline(1_000_001)
     if not line:break
     total+=len(line)
     if len(line)>1_000_000 or total>3_000_000:raise ValueError('oversized protocol')
     self.messages.put(json.loads(line))
   except (ValueError,OSError):pass
   finally:self.messages.put(None)
  threading.Thread(target=read,daemon=True).start()
 def send(self,message):self.process.stdin.write(json.dumps(message)+'\n');self.process.stdin.flush()
 def call(self,method,params):
  self.ident+=1;ident=self.ident;self.send(dict(id=ident,method=method,params=params));end=time.monotonic()+8
  while time.monotonic()<end:
   row=self.messages.get(timeout=max(.01,end-time.monotonic()))
   if row is None:raise ValueError('protocol closed')
   if row.get('id')==ident:
    if 'error' in row:raise ValueError('protocol rejected')
    return row['result']
  raise TimeoutError()
 def close(self):terminate(self.process)

def capabilities(account,models):
 ready=isinstance(account.get('account'),dict);items=[]
 for m in models.get('data',[])[:100]:
  ident=m.get('model');efforts=[e.get('reasoningEffort') for e in m.get('supportedReasoningEfforts',[]) if e.get('reasoningEffort') in ('none','minimal','low','medium','high','xhigh','max','ultra')]
  if isinstance(ident,str) and VALID.fullmatch(ident) and efforts and not m.get('hidden'):
   items.append(dict(id=ident,label=str(m.get('displayName') or ident)[:100],efforts=list(dict.fromkeys(efforts)),default_effort=m.get('defaultReasoningEffort') if m.get('defaultReasoningEffort') in efforts else efforts[0],is_default=bool(m.get('isDefault'))))
 default=next((m for m in items if m['is_default']),items[0] if items else {})
 return dict(installed=True,authenticated=ready,reason='ready' if ready and items else 'models_unavailable' if ready else 'authentication_required',models=items,
  model_options=[m['id'] for m in items],model=default.get('id',''),default_effort=default.get('default_effort','medium'))

def configuration():
 global _cache
 cmd=command()
 if not cmd:return dict(installed=False,authenticated=False,reason='cli_not_installed',models=[],model_options=[],model='')
 cache_key=(tuple(cmd),os.getenv('CODEX_HOME',''))
 with _LOCK:
  if _cache and _cache[0]==cache_key and time.monotonic()-_cache[1]<30:return dict(_cache[2])
  result=dict(installed=True,authenticated=False,reason='cli_probe_failed',models=[],model_options=[],model='')
  client=None
  try:
   with tempfile.TemporaryDirectory(prefix='gold-desk-codex-probe-',ignore_cleanup_errors=True) as cwd:
    try:
     help_result=subprocess.run(cmd+['exec','--help'],**options(cwd),timeout=8)
     required=('--ignore-user-config','--ephemeral','--skip-git-repo-check','--sandbox','--json')
     if help_result.returncode or not all(flag in help_result.stdout for flag in required):result['reason']='cli_upgrade_required'
     else:
      client=RPC(cmd,cwd);client.call('initialize',dict(clientInfo=dict(name='gold_desk',version='1.0.0')));client.send(dict(method='initialized'))
      result=capabilities(client.call('account/read',dict(refreshToken=False)),client.call('model/list',dict(limit=100,includeHidden=False)))
    finally:
     if client:client.close();client=None
  except (OSError,ValueError,KeyError,TypeError,queue.Empty,TimeoutError,subprocess.TimeoutExpired):pass
  finally:
   if client:client.close()
  _cache=(cache_key,time.monotonic(),dict(result));return result

def parse_output(output,json_output):
 answer=[];finished=False
 try:
  for line in output.splitlines():
   row=json.loads(line)
   if row.get('type') in ('turn.failed','error'):return 'provider_error',None
   item=row.get('item',{});kind=item.get('type')
   if kind and kind not in ('agent_message','reasoning'):return 'tool_use_rejected',None
   if row.get('type')=='item.completed' and kind=='agent_message':answer.append(item['text'])
   finished|=row.get('type')=='turn.completed'
  if not finished or len(answer)!=1 or not answer[0].strip():return 'invalid_response',None
  text=answer[0].strip()
  if json_output and not isinstance(json.loads(text),dict):return 'invalid_response',None
  return 'ok',text
 except (ValueError,KeyError,TypeError,AttributeError):return 'invalid_response',None

def complete(system,prompt,*,json_output=False,model=None,effort=None):
 info=configuration();model=model or info.get('model');effort=effort or info.get('default_effort','medium')
 result=dict(status='provider_error',text=None,model=model,requested_effort=effort,provider='codex')
 if not info.get('authenticated'):return dict(result,status=info['reason'])
 selected=next((m for m in info.get('models',[]) if m['id']==model),None)
 if not selected or effort not in selected['efforts']:return dict(result,status='invalid_configuration')
 if len(prompt)>180_000 or len(system)>30_000:return dict(result,status='invalid_configuration')
 if not SLOT.acquire(blocking=False):return dict(result,status='busy')
 try:
  try:timeout=float(os.getenv('GOLD_CODEX_TIMEOUT_SECONDS','120'))
  except ValueError:return dict(result,status='invalid_configuration')
  if not 1<=timeout<=150:return dict(result,status='invalid_configuration')
  cmd=command()
  if not cmd:return dict(result,status='cli_not_installed')
  with tempfile.TemporaryDirectory(prefix='gold-desk-codex-') as cwd:
   process=subprocess.Popen(cmd+exec_flags(system+('\n只輸出JSON物件。' if json_output else ''))+['--model',model,'-c','model_reasoning_effort='+json.dumps(effort),'-'],**options(cwd))
   try:out,err=process.communicate(input=prompt,timeout=timeout)
   except subprocess.TimeoutExpired:terminate(process);return dict(result,status='timeout')
  if len(out)>1_000_000 or len(err)>1_000_000:return dict(result,status='invalid_response')
  if process.returncode:
   from .claude_code import failure_status
   return dict(result,status=failure_status(err+out))
  status,text=parse_output(out,json_output);return dict(result,status=status,text=text)
 except OSError:return dict(result,status='cli_unavailable')
 finally:SLOT.release()
