"""Personal, local-only OAuth setup. No trading request types are imported."""
import argparse,getpass,json,os,secrets,tempfile,time,webbrowser
from pathlib import Path
from http.server import BaseHTTPRequestHandler,HTTPServer
from urllib.parse import urlsplit,parse_qs,urlencode
from scripts.check_ctrader_demo import load_local_config
ROOT=Path(__file__).resolve().parents[1]

def checked_callback(path,state):
 url=urlsplit(path);q=parse_qs(url.query)
 if url.path!='/callback' or set(q)!={'code','state'} or len(q['state'])!=1 or len(q['code'])!=1 or not secrets.compare_digest(q['state'][0],state) or not q['code'][0]:raise ValueError('授權回應不符，未保存token')
 return q['code'][0]

def choose_demo(accounts,index):
 demos=[a for a in accounts if a.get('is_live') is False]
 if type(index) is not int or not 0<=index<len(demos):raise ValueError('沒有可選DEMO帳戶，LIVE不在此流程')
 return demos[index]['id']

def write_config(path,values):
 allowed={'CTRADER_CLIENT_ID','CTRADER_CLIENT_SECRET','CTRADER_ACCESS_TOKEN','CTRADER_ACCOUNT_ID','CTRADER_ENVIRONMENT','CTRADER_REFRESH_TOKEN','CTRADER_TOKEN_EXPIRES_AT'}
 if set(values)-allowed or values.get('CTRADER_ENVIRONMENT')!='demo' or any('\n' in str(v) or '\r' in str(v) for v in values.values()):raise ValueError('設定無效')
 fd,name=tempfile.mkstemp(prefix='.ctrader-',dir=path.parent)
 try:
  with os.fdopen(fd,'w',encoding='utf8') as f:f.write('\n'.join(k+'='+str(v) for k,v in values.items())+'\n')
  os.chmod(name,0o600);os.replace(name,path)
 finally:
  if Path(name).exists():Path(name).unlink()

def token_request(params):
 import httpx
 try:
  r=httpx.get('https://openapi.ctrader.com/apps/token',params=params,headers={'Accept':'application/json'},timeout=20,follow_redirects=False);data=r.json()
  if r.status_code!=200 or not isinstance(data.get('accessToken'),str) or not isinstance(data.get('refreshToken'),str):raise ValueError()
  return data
 except (httpx.HTTPError,ValueError,TypeError):raise ValueError('官方token交換未成功，沒有輸出或保存憑證') from None

def demo_accounts(config):
 from ctrader_open_api import Client,EndPoints,Protobuf,TcpProtocol
 from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAApplicationAuthReq,ProtoOAApplicationAuthRes,ProtoOAGetAccountListByAccessTokenReq,ProtoOAGetAccountListByAccessTokenRes
 from twisted.internet import reactor
 result=[];failed=[];client=Client(EndPoints.PROTOBUF_DEMO_HOST,EndPoints.PROTOBUF_PORT,TcpProtocol)
 def stop():
  if reactor.running:reactor.stop()
 def fail(_):failed.append(True);stop()
 def listed(message):
  if message.payloadType!=ProtoOAGetAccountListByAccessTokenRes().payloadType:return fail(None)
  result.extend(dict(id=str(a.ctidTraderAccountId),is_live=bool(a.isLive)) for a in Protobuf.extract(message).ctidTraderAccount);stop()
 def authorized(message):
  if message.payloadType!=ProtoOAApplicationAuthRes().payloadType:return fail(None)
  client.send(ProtoOAGetAccountListByAccessTokenReq(accessToken=config['CTRADER_ACCESS_TOKEN']),responseTimeoutInSeconds=15).addCallbacks(listed,fail)
 def connected(_):client.send(ProtoOAApplicationAuthReq(clientId=config['CTRADER_CLIENT_ID'],clientSecret=config['CTRADER_CLIENT_SECRET']),responseTimeoutInSeconds=15).addCallbacks(authorized,fail)
 client.setConnectedCallback(connected);client.startService();reactor.callLater(35,lambda:fail(None));reactor.run(installSignalHandlers=False)
 if failed:raise ValueError('DEMO帳戶清單讀取失敗，未選取LIVE')
 return result

def authorize(path,trade=False):
 config=load_local_config(path);state=secrets.token_urlsafe(32);received=[]
 class Callback(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def do_GET(self):
   try:
    if self.headers.get('Host')!='127.0.0.1:8766' or received:raise ValueError()
    code=checked_callback(self.path,state);received.append(code);self.send_response(200);self.end_headers();self.wfile.write(b'Authorization received. Return to your local terminal.')
   except ValueError:self.send_response(400);self.end_headers()
 redirect='http://127.0.0.1:8766/callback'
 with HTTPServer(('127.0.0.1',8766),Callback) as server:
  server.timeout=1
  print('請在你的Open API應用先加入redirect：'+redirect)
  input('確認已設定，按Enter開啟本人授權頁：')
  webbrowser.open('https://id.ctrader.com/my/settings/openapi/grantingaccess/?'+urlencode(dict(client_id=config['CTRADER_CLIENT_ID'],redirect_uri=redirect,scope='trading' if trade else 'accounts',product='web',state=state)))
  end=time.monotonic()+180
  while not received and time.monotonic()<end:server.handle_request()
 if not received:raise ValueError('授權逾時，請重新操作；不自動重試')
 token=token_request(dict(grant_type='authorization_code',code=received[0],redirect_uri=redirect,client_id=config['CTRADER_CLIENT_ID'],client_secret=config['CTRADER_CLIENT_SECRET']))
 config.update(CTRADER_ACCESS_TOKEN=token['accessToken'],CTRADER_REFRESH_TOKEN=token['refreshToken'],CTRADER_TOKEN_EXPIRES_AT=str(int(time.time())+int(token.get('expiresIn',0))))
 accounts=demo_accounts(config);demos=[a for a in accounts if not a['is_live']]
 for i,a in enumerate(demos):print(f'{i+1}. DEMO …{a["id"][-4:]}')
 try:index=int(input('選擇DEMO編號：'))-1
 except ValueError:raise ValueError('編號無效，沒有保存token')
 config['CTRADER_ACCOUNT_ID']=choose_demo(accounts,index);config['CTRADER_ENVIRONMENT']='demo';write_config(path,config)
 return dict(status='saved',environment='demo',requested_scope='TRADE' if trade else 'ACCOUNTS',orders_sent=0)

def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['credentials','authorize','refresh']);p.add_argument('--trade',action='store_true');a=p.parse_args();path=ROOT/'.env.ctrader'
 if a.action=='credentials':
  if path.exists() and load_local_config_safe(path):raise ValueError('已有應用憑證，不覆蓋；請自行編輯本機設定')
  write_config(path,dict(CTRADER_CLIENT_ID=input('本人應用Client ID：').strip(),CTRADER_CLIENT_SECRET=getpass.getpass('本人應用Client Secret（隱藏）：').strip(),CTRADER_ENVIRONMENT='demo'));result=dict(status='credentials_saved')
 elif a.action=='authorize':result=authorize(path,a.trade)
 else:
  config=load_local_config(path)
  if not config.get('CTRADER_REFRESH_TOKEN'):raise ValueError('缺refresh token，請重新授權')
  token=token_request(dict(grant_type='refresh_token',refresh_token=config['CTRADER_REFRESH_TOKEN'],client_id=config['CTRADER_CLIENT_ID'],client_secret=config['CTRADER_CLIENT_SECRET']))
  config.update(CTRADER_ACCESS_TOKEN=token['accessToken'],CTRADER_REFRESH_TOKEN=token['refreshToken'],CTRADER_TOKEN_EXPIRES_AT=str(int(time.time())+int(token.get('expiresIn',0))));write_config(path,config);result=dict(status='refreshed',orders_sent=0)
 print(json.dumps(result));return 0
def load_local_config_safe(path):
 try:return bool(load_local_config(path).get('CTRADER_CLIENT_SECRET'))
 except ValueError:return False
if __name__=='__main__':
 try:raise SystemExit(main())
 except (ValueError,OSError) as e:print(str(e) if isinstance(e,ValueError) else '本機授權操作失敗，沒有輸出憑證');raise SystemExit(1)
