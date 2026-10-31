"""Explicit read-only broker download to a separate personal source namespace."""
import argparse,json,os,subprocess,sys
from pathlib import Path
from backend.volume_paths import volume_folder
from scripts.local_app import read_settings
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--max-chunks',type=int);p.add_argument('--folder',default='ctrader_history_volume_local');p.add_argument('--activate',action='store_true');a=p.parse_args()
 env=dict(os.environ,GOLD_NATIVE_VOLUME_FOLDER=a.folder);old=os.environ.get('GOLD_NATIVE_VOLUME_FOLDER');os.environ['GOLD_NATIVE_VOLUME_FOLDER']=a.folder
 try:folder=volume_folder(ROOT/'private')
 finally:
  if old is None:os.environ.pop('GOLD_NATIVE_VOLUME_FOLDER',None)
  else:os.environ['GOLD_NATIVE_VOLUME_FOLDER']=old
 if a.folder=='ctrader_history_volume_20261030':raise ValueError('請使用獨立個人資料夾，不覆蓋作者來源')
 print(json.dumps(dict(mode='download' if a.execute else 'dry_run',folder=a.folder,orders_sent=0,note='可能需要多次下載；先完成案例資料包匯入。不同來源不可混寫。')))
 if a.execute:
  args=[sys.executable,'-m','scripts.fetch_ctrader_history_volume']
  if a.max_chunks is not None:args+=['--max-chunks',str(a.max_chunks)]
  subprocess.run(args,cwd=ROOT,env=env,check=True)
  built=subprocess.run([sys.executable,'-m','scripts.build_native_volume_index'],cwd=ROOT,env=env)
  if built.returncode:raise ValueError('下載尚未完整，不啟用此索引；可繼續斷點下載')
 if a.activate:
  if not (folder/'case_volume_references_PRIVATE.json').is_file():raise ValueError('還沒有完成的索引，不啟用')
  path=ROOT/'.env.local';read_settings(path)
  lines=[line for line in path.read_text(encoding='utf8').splitlines() if not line.startswith('GOLD_NATIVE_VOLUME_FOLDER=')]
  temp=path.with_suffix('.volume.tmp');temp.write_text('\n'.join(lines)+f'\nGOLD_NATIVE_VOLUME_FOLDER={a.folder}\n',encoding='utf8');temp.replace(path)
  print('已設定個人量能資料夾；請重啟網站並核對來源狀態。')
 return 0
if __name__=='__main__':raise SystemExit(main())
