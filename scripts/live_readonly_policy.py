"""Allowlisted LIVE read requests. No order type is allowed, regardless of scope."""
from pathlib import Path

READ_REQUESTS=frozenset(('ProtoOAApplicationAuthReq','ProtoOAGetAccountListByAccessTokenReq',
 'ProtoOAAccountAuthReq','ProtoOAAssetListReq','ProtoOASymbolsListReq','ProtoOASymbolByIdReq',
 'ProtoOATraderReq','ProtoOAReconcileReq','ProtoOAGetPositionUnrealizedPnLReq','ProtoOAGetTrendbarsReq',
 'ProtoOASubscribeSpotsReq','ProtoOASubscribeLiveTrendbarReq','ProtoOAOrderListReq','ProtoOADealListReq','ProtoHeartbeatEvent'))


def validate_request(request):
    if type(request).__name__ not in READ_REQUESTS:raise ValueError('LIVE_READ_ONLY_REQUEST_REJECTED')


class ReadOnlyClient:
    def __init__(self,client):self.client=client
    def __getattr__(self,name):return getattr(self.client,name)
    def send(self,request,*args,**kwargs):
        validate_request(request)
        return self.client.send(request,*args,**kwargs)


def select_live(accounts,requested):
    if not requested:raise ValueError('ACCOUNT_ID_REQUIRED')
    result=next((a for a in accounts if a.isLive and str(a.ctidTraderAccountId)==requested),None)
    if result is None:raise ValueError('LIVE_ACCOUNT_NOT_FOUND')
    return result


def load_live_config(path=None):
    path=Path(path) if path else Path(__file__).resolve().parents[1]/'.env.ctrader.live'
    keys={'CTRADER_ENVIRONMENT','CTRADER_CLIENT_ID','CTRADER_CLIENT_SECRET','CTRADER_ACCESS_TOKEN','CTRADER_ACCOUNT_ID'}
    if not path.is_file():raise ValueError('NOT_CONFIGURED')
    values={}
    for raw in path.read_text(encoding='utf-8-sig').splitlines():
        line=raw.strip()
        if not line or line.startswith('#'):continue
        if '=' not in line:raise ValueError('CONFIG_FORMAT_INVALID')
        key,value=(x.strip() for x in line.split('=',1))
        if key not in keys or key in values:raise ValueError('CONFIG_KEY_INVALID')
        values[key]=value.strip('"').strip("'")
    if values.get('CTRADER_ENVIRONMENT')!='live':raise ValueError('LIVE_ENVIRONMENT_REQUIRED')
    account=values.get('CTRADER_ACCOUNT_ID','')
    if not account.isdecimal() or int(account)<=0:raise ValueError('ACCOUNT_ID_REQUIRED')
    if any(not values.get(k) for k in ('CTRADER_CLIENT_ID','CTRADER_CLIENT_SECRET','CTRADER_ACCESS_TOKEN')):raise ValueError('CREDENTIALS_MISSING')
    return values
