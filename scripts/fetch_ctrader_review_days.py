"""Read-only DEMO candles at ten predeclared weekly query clocks. No orders."""
from datetime import datetime,timezone
from decimal import Decimal
import json
from pathlib import Path
import sys

PRODUCT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PRODUCT))
from scripts.check_ctrader_demo import load_local_config
from scripts.stream_ctrader_demo import decode_symbol_schedule

OUTPUT=PRODUCT/'private/distinct_day_dual_path_20261021'


def sample_clocks():
    last=int(datetime(2026,10,20,15,tzinfo=timezone.utc).timestamp())
    return [last-i*7*86400 for i in reversed(range(11))]


def decode_closed(raw,seconds,clock):
    opened=int(raw.utcTimestampInMinutes)*60
    if opened+seconds>clock:return None
    low=int(raw.low)
    values=[low+int(raw.deltaOpen),low+int(raw.deltaHigh),low,low+int(raw.deltaClose)]
    if opened%seconds or min(values)<=0 or values[1]<max(values):raise ValueError('INVALID_BAR')
    return dict(time=opened,**{k:format(Decimal(v)/100000,'f') for k,v in zip(('open','high','low','close'),values)},volume=int(raw.volume))


def fetch(config):
    from ctrader_open_api import Client,EndPoints,Protobuf,TcpProtocol
    from ctrader_open_api.messages.OpenApiMessages_pb2 import (
        ProtoOAApplicationAuthReq,ProtoOAApplicationAuthRes,
        ProtoOAGetAccountListByAccessTokenReq,ProtoOAGetAccountListByAccessTokenRes,
        ProtoOAAccountAuthReq,ProtoOAAccountAuthRes,ProtoOASymbolsListReq,ProtoOASymbolsListRes,
        ProtoOASymbolByIdReq,ProtoOASymbolByIdRes,ProtoOAGetTrendbarsReq,ProtoOAGetTrendbarsRes)
    from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import ProtoHeartbeatEvent
    from twisted.internet import reactor
    client=Client(EndPoints.PROTOBUF_DEMO_HOST,EndPoints.PROTOBUF_PORT,TcpProtocol)
    state=dict(status='PENDING',source='ctrader_demo_xauusd',capture_kind='broker_historical_day_replay',
               requested_clocks=sample_clocks(),records=[],orders_sent=0)
    account=None;symbol=None;tasks=[];active=None;stopping=False
    def finish(reason):
        nonlocal stopping
        if stopping:return
        stopping=True;state['status']=reason
        if reactor.running:reactor.stop()
    def send(req,res,callback):
        def received(message):
            if message.payloadType!=res().payloadType:finish('UNEXPECTED_RESPONSE');return
            try:callback(Protobuf.extract(message))
            except Exception:finish('INVALID_RESPONSE')
        try:client.send(req,responseTimeoutInSeconds=20).addCallbacks(received,lambda _:finish('REQUEST_FAILED'))
        except Exception:finish('SEND_FAILED')
    def next_task():
        nonlocal active
        if not tasks:finish('COMPLETE');return
        active=tasks.pop(0);clock,iv,period,seconds,span,count=active
        send(ProtoOAGetTrendbarsReq(ctidTraderAccountId=account,symbolId=symbol,period=period,
            count=count,fromTimestamp=(clock-span)*1000,toTimestamp=clock*1000),ProtoOAGetTrendbarsRes,bars_received)
    def bars_received(response):
        clock,iv,period,seconds,span,count=active
        bars=[b for raw in response.trendbar if (b:=decode_closed(raw,seconds,clock)) is not None]
        bars=sorted(bars,key=lambda b:b['time'])
        record=next(r for r in state['records'] if r['as_of']==clock)
        record['bars'][iv]=bars
        print(f"received {datetime.fromtimestamp(clock,timezone.utc).date()} {iv}: {len(bars)} closed bars",flush=True)
        reactor.callLater(.6,next_task)
    def symbol_received(response):
        if len(response.symbol)!=1:finish('SYMBOL_DETAIL_MISSING');return
        state['trading_schedule']=decode_symbol_schedule(response.symbol[0])
        for clock in sample_clocks():
            state['records'].append(dict(as_of=clock,bars={}))
            tasks.extend([(clock,'5m',5,300,10*3600,120),(clock,'1h',9,3600,48*3600,60)])
        next_task()
    def symbols(response):
        nonlocal symbol
        item=next((s for s in response.symbol if s.enabled and s.symbolName.upper()=='XAUUSD'),None)
        if item is None:finish('XAUUSD_MISSING');return
        symbol=item.symbolId
        send(ProtoOASymbolByIdReq(ctidTraderAccountId=account,symbolId=[symbol]),ProtoOASymbolByIdRes,symbol_received)
    def authorized(_):
        send(ProtoOASymbolsListReq(ctidTraderAccountId=account),ProtoOASymbolsListRes,symbols)
    def accounts(response):
        nonlocal account
        choices=[a for a in response.ctidTraderAccount if not a.isLive]
        requested=config.get('CTRADER_ACCOUNT_ID')
        item=next((a for a in choices if str(a.ctidTraderAccountId)==requested),None) if requested else next(iter(choices),None)
        if item is None:finish('DEMO_ACCOUNT_UNAVAILABLE');return
        account=item.ctidTraderAccountId
        send(ProtoOAAccountAuthReq(ctidTraderAccountId=account,accessToken=config['CTRADER_ACCESS_TOKEN']),ProtoOAAccountAuthRes,authorized)
    def app_authorized(_):
        send(ProtoOAGetAccountListByAccessTokenReq(accessToken=config['CTRADER_ACCESS_TOKEN']),ProtoOAGetAccountListByAccessTokenRes,accounts)
    def connected(_):
        send(ProtoOAApplicationAuthReq(clientId=config['CTRADER_CLIENT_ID'],clientSecret=config['CTRADER_CLIENT_SECRET']),ProtoOAApplicationAuthRes,app_authorized)
    def heartbeat():
        if stopping:return
        client.send(ProtoHeartbeatEvent()).addErrback(lambda _:None)
        reactor.callLater(10,heartbeat)
    client.setConnectedCallback(connected)
    reactor.callLater(150,lambda:finish('TIMEOUT'))
    reactor.callLater(10,heartbeat)
    client.startService();reactor.run(installSignalHandlers=False)
    state['fetched_at_utc']=datetime.now(timezone.utc).isoformat()
    return state


def main():
    try:result=fetch(load_local_config())
    except Exception:
        print('FETCH_FAILED (credentials and raw responses suppressed)');return 1
    OUTPUT.mkdir(parents=True,exist_ok=True)
    (OUTPUT/'broker_days_PRIVATE.json').write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2),encoding='utf-8')
    print('status='+result['status']+'; orders_sent=0',flush=True)
    return 0 if result['status']=='COMPLETE' else 1


if __name__=='__main__':sys.exit(main())
