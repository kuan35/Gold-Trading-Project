"""Cross-platform local installer/launcher. Never installs AI CLI or logs secrets."""
import argparse,json,os,shutil,socket,subprocess,sys,time,urllib.request,venv,webbrowser
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ALLOWED={'GOLD_ENABLE_LLM','GOLD_LLM_PROVIDER','GOLD_LLM_API_KEY','GOLD_LLM_BASE_URL','GOLD_LLM_MODEL','GOLD_LLM_TOKEN_FIELD','GOLD_LLM_MAX_TOKENS','GOLD_LLM_REASONING_EFFORT','GOLD_LLM_TIMEOUT_SECONDS','GOLD_CLAUDE_MODEL','GOLD_CLAUDE_EFFORT','GOLD_CLAUDE_TIMEOUT_SECONDS','GOLD_CLAUDE_EXECUTABLE','GOLD_CODEX_EXECUTABLE','GOLD_CODEX_TIMEOUT_SECONDS'}
ALLOWED.add('GOLD_NATIVE_VOLUME_FOLDER')

def read_settings(path):
 values={}
 if not path.exists():return values
 for raw in path.read_text(encoding='utf-8-sig').splitlines():
  line=raw.strip()
  if not line or line.startswith('#'):continue
  key,sep,value=line.partition('=')
  if not sep or key.strip() not in ALLOWED or key.strip() in values:raise ValueError('本機設定有未知或重複欄位，請核對範本')
  values[key.strip()]=value.strip().strip('"').strip("'")
 return values

def ensure_template(source,target):
 try:
  with target.open('x',encoding='utf8') as f:f.write(source.read_text(encoding='utf8'))
 except FileExistsError:pass

def venv_python(root,platform=None):return root/('.venv/Scripts/python.exe' if (platform or sys.platform)=='win32' else '.venv/bin/python')
def start_arguments(root,platform=None):return [str(venv_python(root,platform)),'-m','uvicorn','backend.app:app','--host','127.0.0.1','--port','8765']

def npm_command():
 node=shutil.which('node');npm=shutil.which('npm')
 if not node or not npm:raise ValueError('需要Node.js與npm；請依README安裝Node.js 24 LTS')
 path=Path(npm).resolve()
 if path.suffix.lower() in ('.cmd','.ps1','.bat'):
  path=path.parent/'node_modules/npm/bin/npm-cli.js'
  if not path.is_file():raise ValueError('找不到npm CLI，請修復Node.js安裝')
 return [node,str(path)] if path.suffix=='.js' else [str(path)]

def setup(root=ROOT,skip_install=False):
 if sys.version_info<(3,11):raise ValueError('需要Python3.11或更新版本')
 ensure_template(root/'.env.local.example',root/'.env.local');ensure_template(root/'ctrader.env.example',root/'.env.ctrader')
 if not skip_install:
  npm=npm_command();node=json.loads(subprocess.check_output([shutil.which('node'),'-p','JSON.stringify(process.versions.node)'],text=True))
  if int(node.split('.')[0])<22:raise ValueError('需要Node.js22以上，建議24 LTS')
  if not venv_python(root).exists():venv.EnvBuilder(with_pip=True).create(root/'.venv')
  subprocess.run([str(venv_python(root)),'-m','pip','install','-r','requirements.txt','-r','research/requirements.txt','-r','requirements-ctrader.txt'],cwd=root,check=True)
  subprocess.run(npm+['ci','--no-audit','--no-fund'],cwd=root/'frontend',check=True)
  subprocess.run(npm+['run','build'],cwd=root/'frontend',check=True)
 return dict(status='ready' if (root/'frontend/dist/index.html').exists() else 'build_required',settings_preserved=True)

def doctor(root=ROOT,check_ai=False):
 settings=read_settings(root/'.env.local');result=dict(python=sys.version.split()[0],platform=sys.platform,venv=venv_python(root).is_file(),frontend=(root/'frontend/dist/index.html').is_file(),node=bool(shutil.which('node')),provider=settings.get('GOLD_LLM_PROVIDER','program'))
 result['data']='private_bundle_present' if (root/'private/cases.json').is_file() else 'synthetic_demo'
 if (root/'private/cases.json').is_file() and not (root/'private/bundle_manifest.json').is_file():result['data']='private_local_data_unbundled'
 if (root/'private/bundle_manifest.json').is_file():
  try:
   from scripts.data_bundle import validate_runtime
   result['runtime']=validate_runtime(root/'private');result['data']='private_runtime_ready'
  except (ValueError,OSError):result['data']='private_runtime_incomplete_or_invalid'
 result['ctrader']='not_configured'
 try:
  from scripts.check_ctrader_demo import load_local_config
  config=load_local_config(root/'.env.ctrader')
  if config.get('CTRADER_ACCESS_TOKEN'):result['ctrader']='configured_not_connection_tested'
 except ValueError:pass
 if check_ai:
  os.environ.update(settings)
  from backend.assistant import model_configuration
  info=model_configuration();result['ai']={k:info.get(k) for k in ('provider','configured','reason','model','model_options')}
 return result

def start(root=ROOT,open_browser=True):
 if not venv_python(root).is_file() or not (root/'frontend/dist/index.html').is_file():raise ValueError('請先執行setup安裝與建置')
 with socket.socket() as s:
  if s.connect_ex(('127.0.0.1',8765))==0:raise ValueError('8765已被使用；不自動停止其他程序。已有Gold Desk時直接開 http://127.0.0.1:8765/')
 env=dict(os.environ);env.update(read_settings(root/'.env.local'))
 folder=root/'private/runtime';folder.mkdir(parents=True,exist_ok=True)
 kw=dict(cwd=root,env=env,stdin=subprocess.DEVNULL,shell=False)
 if os.name=='nt':kw['creationflags']=subprocess.CREATE_NO_WINDOW
 else:kw['start_new_session']=True
 with (folder/'server.log').open('ab') as out,(folder/'server-error.log').open('ab') as err:
  process=subprocess.Popen(start_arguments(root),stdout=out,stderr=err,**kw)
 for _ in range(60):
  if process.poll() is not None:raise ValueError('服務啟動失敗，請查看private/runtime/server-error.log')
  try:
   with urllib.request.urlopen('http://127.0.0.1:8765/',timeout=1) as response:
    if response.status==200:
     if open_browser:webbrowser.open('http://127.0.0.1:8765/')
     return dict(status='ready',pid=process.pid,url='http://127.0.0.1:8765/')
  except (OSError,TimeoutError):pass
  time.sleep(1)
 raise ValueError('服務仍在啟動，請稍後查看本機網址及server-error.log；沒有重複啟動')

def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['setup','start','doctor']);p.add_argument('--skip-install',action='store_true');p.add_argument('--no-open',action='store_true');p.add_argument('--check-ai',action='store_true');args=p.parse_args()
 try:
  result=setup(skip_install=args.skip_install) if args.action=='setup' else start(open_browser=not args.no_open) if args.action=='start' else doctor(check_ai=args.check_ai)
  print(json.dumps(result,ensure_ascii=False))
 except (ValueError,OSError,subprocess.CalledProcessError) as e:
  print(str(e) if isinstance(e,ValueError) else '本機操作失敗，請核對README與必要軟體；不輸出設定值',file=sys.stderr);return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
