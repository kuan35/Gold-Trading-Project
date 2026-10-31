"""Explicit private runtime export/import; never an all-private zip or public upload."""
import argparse,hashlib,json,os,re,shutil,socket,stat,tempfile,zipfile
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1]
BASE={'cases.json','case_size_profiles.json','case_candidate_market_profiles.json','case_execution_bars_v2.json','case_forward_outcomes.json','bars.json'}
VOLUME='ctrader_history_volume_20261030/'
ALIGN_KEYS={'case_id','marker_status','timezone_status','production_enabled','frozen_boundary_policy_difference','candidate_clock_basis','candidate_open_utc','candidate_close_utc','entry_bar_utc','exit_bar_utc'}
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def allowed(name):
 p=PurePosixPath(name)
 return '\\' not in name and ':' not in name and not p.is_absolute() and all(v not in ('..','.') for v in p.parts) and (name in BASE or name in ('reference/bars.csv','reference/alignment.json') or name==VOLUME+'case_volume_references_PRIVATE.json' or re.fullmatch(VOLUME+r'(?:5m|1h)-\d+\.json',name) is not None)
def ref(root,p):return dict(path=p.relative_to(root).as_posix(),sha256=digest(p))
def write(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,separators=(',',':')),encoding='utf8')

def validate_runtime(root):
 """Validate the assembled runtime before touching the destination; no network."""
 from backend.candidate_sidecar import load_candidate_sidecar
 from backend.forward_outcomes import HistoricalOutcomeStore
 from backend.execution_store import ExecutionStore
 from backend.tick_volume import NativeTickStore
 root=Path(root)
 required=(BASE-{'bars.json'})|{'reference/bars.csv','reference/alignment.json',VOLUME+'case_volume_references_PRIVATE.json'}
 if not all((root/n).is_file() for n in required):raise ValueError('runtime資料包不完整')
 try:
  cases=json.loads((root/'cases.json').read_text(encoding='utf8'))['cases']
  keys={'id','side','action','entry','exit','lot','profit','group','available_at','opened_at','closed_at'}
  if not isinstance(cases,list) or not cases or any(not isinstance(c,dict) or not keys<=c.keys() or c['side'] not in ('BUY','SELL') for c in cases):raise ValueError()
  profiles,status=load_candidate_sidecar(root/'cases.json',root/'case_candidate_market_profiles.json',root)
  if status!='READY' or not profiles:raise ValueError()
  size=json.loads((root/'case_size_profiles.json').read_text(encoding='utf8'))
  if size['input_cases_sha256']!=digest(root/'cases.json') or not isinstance(size['profiles'],dict):raise ValueError()
  outcomes=HistoricalOutcomeStore(root);outcomes._load()
  if outcomes._status!='READY':raise ValueError()
  # The default case bundle is independent from a personal account's selected folder.
  ticks=NativeTickStore(root);ticks.folder=root/VOLUME.rstrip('/');ticks.path=ticks.folder/'case_volume_references_PRIVATE.json';ticks.paths=[ticks.path,ticks.profile_path]
  if not ticks._load():raise ValueError()
  executions=ExecutionStore(root);by_id={c['id']:c for c in cases};ready=0
  for ident,profile in sorted(profiles.items()):
   if ident not in by_id:raise ValueError()
   if executions.get(ident,profile,by_id[ident],profile['reference_close_utc']+7200)['status']=='AVAILABLE':ready+=1;break
  if not ready:raise ValueError()
  return dict(cases=len(cases),profiles=len(profiles),execution_smoke='AVAILABLE',outcomes='READY',native_ticks='READY')
 except (OSError,KeyError,TypeError,AttributeError,ValueError,ArithmeticError) as e:raise ValueError('runtime資料結構或索引不可用，未替換原資料') from e

def export_bundle(private,destination):
 private=Path(private).resolve();destination=Path(destination).resolve()
 if destination.exists():raise ValueError('輸出已存在，不覆蓋')
 with tempfile.TemporaryDirectory(prefix='gold-private-export-',dir=destination.parent) as td:
  stage=Path(td)
  for name in BASE:
   if name=='bars.json' and not (private/name).exists():continue
   shutil.copyfile(private/name,stage/name)
  profile=json.loads((stage/'case_candidate_market_profiles.json').read_text(encoding='utf8'))
  bars=(private/profile['inputs']['bars']['path']).resolve();alignment=(private/profile['inputs']['alignment']['path']).resolve()
  if not bars.is_relative_to(private) or not alignment.is_relative_to(private):raise ValueError('來源越界')
  (stage/'reference').mkdir();shutil.copyfile(bars,stage/'reference/bars.csv')
  markers=json.loads(alignment.read_text(encoding='utf8'));write(stage/'reference/alignment.json',[{k:v for k,v in m.items() if k in ALIGN_KEYS} for m in markers])
  profile['inputs']={'bars':ref(stage,stage/'reference/bars.csv'),'alignment':ref(stage,stage/'reference/alignment.json')}
  write(stage/'case_candidate_market_profiles.json',profile)
  for name in ('case_execution_bars_v2.json','case_forward_outcomes.json'):
   value=json.loads((stage/name).read_text(encoding='utf8'))
   for key in value['inputs']:
    p=stage/({'cases':'cases.json','profiles':'case_candidate_market_profiles.json','bars':'reference/bars.csv','alignment':'reference/alignment.json'}[key]);value['inputs'][key]=ref(stage,p)
   write(stage/name,value)
  vm=json.loads((private/VOLUME/'case_volume_references_PRIVATE.json').read_text(encoding='utf8'));vm['profiles_sha256']=digest(stage/'case_candidate_market_profiles.json')
  write(stage/VOLUME/'case_volume_references_PRIVATE.json',vm)
  for name in vm['chunk_hashes']:
   if not allowed(VOLUME+name):raise ValueError('無效量能檔名')
   source=private/VOLUME/name
   if digest(source)!=vm['chunk_hashes'][name]:raise ValueError('量能來源校驗失敗')
   shutil.copyfile(source,stage/VOLUME/name)
  files={p.relative_to(stage).as_posix():dict(sha256=digest(p),size=p.stat().st_size) for p in sorted(stage.rglob('*')) if p.is_file()}
  if not all(allowed(n) for n in files):raise ValueError('未允許的匯出檔案')
  manifest=dict(format='gold-desk-private-v1',data_policy='TEAM_PRIVATE_NOT_PUBLIC',files=files)
  with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
   z.writestr('manifest.json',json.dumps(manifest,separators=(',',':')))
   for n in files:z.write(stage/n,n)
 return dict(status='exported',files=len(files),bytes=destination.stat().st_size)

def import_bundle(archive,private,*,replace=False):
 private=Path(private).resolve();private.mkdir(parents=True,exist_ok=True)
 lock=private/'.bundle-import.lock'
 try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 except FileExistsError:raise ValueError('已有資料匯入工作，請勿同時執行')
 os.close(fd)
 try:
  with zipfile.ZipFile(archive) as z,tempfile.TemporaryDirectory(prefix='.bundle-stage-',dir=private) as td:
   entries=z.infolist();names=[e.filename for e in entries]
   if len(names)>1200 or len(names)!=len(set(names)) or names.count('manifest.json')!=1:raise ValueError('資料包目錄無效')
   meta=z.getinfo('manifest.json')
   if meta.file_size>500_000:raise ValueError('manifest過大')
   m=json.loads(z.read(meta))
   if not isinstance(m,dict):raise ValueError('資料包清單格式無效')
   files=m.get('files',{})
   if m.get('format')!='gold-desk-private-v1' or not isinstance(files,dict) or set(names)!={'manifest.json',*files}:raise ValueError('資料包清單不符')
   if sum(e.file_size for e in entries)>2_000_000_000:raise ValueError('資料包過大')
   stage=Path(td);changes=[]
   for name,expected in files.items():
    e=z.getinfo(name)
    if not isinstance(expected,dict) or not allowed(name) or stat.S_ISLNK(e.external_attr>>16) or e.file_size>1_000_000_000 or e.file_size!=expected.get('size'):raise ValueError('資料包路徑／大小無效')
    target=private/name
    if any(p.is_symlink() for p in [target,*target.parents] if p.is_relative_to(private)):raise ValueError('目的地含連結，拒絕匯入')
    if not target.resolve().is_relative_to(private):raise ValueError('目的地越界')
    path=stage/name;path.parent.mkdir(parents=True,exist_ok=True)
    with z.open(e) as source,path.open('wb') as out:shutil.copyfileobj(source,out,1024*1024)
    if digest(path)!=expected.get('sha256'):raise ValueError('資料SHA不符，原資料未變更')
    if target.is_file() and digest(target)==expected['sha256']:continue
    if target.exists() and not replace:raise ValueError('已有不同版本資料；需明確使用--replace，請先停止網站')
    changes.append(name)
   validate_runtime(stage)
   backups=stage/'.backup';done=[];receipt=private/'bundle_manifest.json';old_receipt=receipt.read_bytes() if receipt.exists() else None
   try:
    for name in changes:
     target=private/name;target.parent.mkdir(parents=True,exist_ok=True);backup=backups/name
     if target.exists():backup.parent.mkdir(parents=True,exist_ok=True);target.replace(backup)
     done.append(name);(stage/name).replace(target)
    write(receipt,m)
   except OSError:
    for name in reversed(done):
     target=private/name;backup=backups/name
     if target.is_file():target.unlink()
     if backup.exists():backup.replace(target)
    if old_receipt is None:receipt.unlink(missing_ok=True)
    else:receipt.write_bytes(old_receipt)
    raise
   return dict(status='imported' if changes else 'unchanged',files=len(files),changed=len(changes))
 finally:lock.unlink(missing_ok=True)

def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['export','import','verify']);p.add_argument('archive',nargs='?');p.add_argument('--replace',action='store_true');a=p.parse_args();private=ROOT/'private'
 if a.action=='verify':
  m=json.loads((private/'bundle_manifest.json').read_text(encoding='utf8'));bad=sum(not allowed(n) or not (private/n).is_file() or digest(private/n)!=v['sha256'] for n,v in m['files'].items());result=dict(status='valid' if bad==0 else 'invalid',files=len(m['files']),invalid=bad)
  if not bad:result['runtime']=validate_runtime(private)
 else:
  if not a.archive:p.error('需要資料包路徑')
  if a.action=='import':
   with socket.socket() as s:
    if s.connect_ex(('127.0.0.1',8765))==0:raise ValueError('請先停止本機網站再匯入資料')
  result=export_bundle(private,Path(a.archive)) if a.action=='export' else import_bundle(Path(a.archive),private,replace=a.replace)
 print(json.dumps(result));return 0 if result['status']!='invalid' else 1
if __name__=='__main__':raise SystemExit(main())
