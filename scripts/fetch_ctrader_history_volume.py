"""Resumable, read-only native M5/H1 OHLC and tick volume for case windows.

Only broker authentication and market-data request types are imported. Never
adds volume to HistData bars or overwrites the existing case profiles.
"""
import argparse,hashlib,json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from scripts.check_ctrader_demo import load_local_config
from scripts.fetch_ctrader_review_days import decode_closed
from backend.volume_paths import volume_folder

ROOT=Path(__file__).resolve().parents[1]
WEEK=7*86400
PERIODS={'5m':(5,300),'1h':(9,3600)}


def plan(profiles):
    wanted={iv:set() for iv in PERIODS}
    for p in profiles.values():
        for iv in PERIODS:
            for b in p.get('pre_entry_bars',{}).get(iv,[]):wanted[iv].add(b['time']//WEEK*WEEK)
            if type(p.get('as_of')) is int:
                # Download H1 even for formerly 5m-only cases, with one extra
                # baseline bar for last-volume / previous-20 mean.
                span=PERIODS[iv][1];count=60 if iv=='5m' else 21
                start=p['as_of']-(count+2)*span;end=p['as_of']
                wanted[iv].update(range(start//WEEK*WEEK,end//WEEK*WEEK+WEEK,WEEK))
    return [dict(interval=iv,start=t,end=t+WEEK) for iv in PERIODS for t in sorted(wanted[iv])]


def task_key(t):return t['interval']+'-'+str(t['start'])


def decode_page(raw,task,clock):
    span=PERIODS[task['interval']][1]
    values=[v for b in raw if (v:=decode_closed(b,span,clock)) is not None]
    if any(v['time']>task['end'] or v['volume']<0 for v in values):raise ValueError('INVALID_BAR_RANGE_OR_VOLUME')
    # Some servers prioritize count backwards from toTimestamp, returning older
    # padding before fromTimestamp. Keep only the exact half-open interval.
    values=[v for v in values if task['start']<=v['time']<task['end']]
    if len({v['time'] for v in values})!=len(values):raise ValueError('DUPLICATE_TIME')
    return sorted(values,key=lambda v:v['time'])


def next_cursor(page,cursor):
    if not page:raise ValueError('EMPTY_PAGINATION')
    result=min(b['time'] for b in page)*1000-1
    if result>=cursor:raise ValueError('PAGINATION_DID_NOT_ADVANCE')
    return result


def fetch(tasks,*,max_chunks=None):
    config=load_local_config()
    from ctrader_open_api import Client,EndPoints,Protobuf,TcpProtocol
    from ctrader_open_api.messages.OpenApiMessages_pb2 import (
      ProtoOAApplicationAuthReq,ProtoOAApplicationAuthRes,ProtoOAGetAccountListByAccessTokenReq,ProtoOAGetAccountListByAccessTokenRes,
      ProtoOAAccountAuthReq,ProtoOAAccountAuthRes,ProtoOASymbolsListReq,ProtoOASymbolsListRes,ProtoOAGetTrendbarsReq,ProtoOAGetTrendbarsRes)
    from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import ProtoHeartbeatEvent
    from twisted.internet import reactor
    client=Client(EndPoints.PROTOBUF_DEMO_HOST,EndPoints.PROTOBUF_PORT,TcpProtocol)
    output=volume_folder(ROOT/'private');output.mkdir(exist_ok=True)
    state=dict(status='CONNECTING',source='ctrader_demo_native',volume_basis='broker_native_tick_count',orders_sent=0,
      requested_chunks=len(tasks),requests_sent=0,completed_chunks=0,empty_chunks=0,rows=0,failures=[])
    queue=[];active=None;bars={};cursor=None;account=None;symbol=None;stopping=False;identity=None;processed=0
    def save():
        state['updated_at_utc']=datetime.now(timezone.utc).isoformat()
        temp=output/'manifest.tmp';temp.write_text(json.dumps(state,ensure_ascii=False,sort_keys=True,indent=2),encoding='utf-8');temp.replace(output/'manifest_PRIVATE.json')
    def finish(status):
        nonlocal stopping
        if stopping:return
        stopping=True;state['status']=status;save()
        if reactor.running:reactor.stop()
    def send(req,expected,callback):
        state['requests_sent']+=1
        def got(message):
            if message.payloadType!=expected().payloadType:finish('UNEXPECTED_RESPONSE');return
            try:callback(Protobuf.extract(message))
            except Exception as error:
                safe=str(error) if isinstance(error,ValueError) and str(error) in ('INVALID_BAR_RANGE_OR_VOLUME','DUPLICATE_TIME','EMPTY_PAGINATION','PAGINATION_DID_NOT_ADVANCE','INVALID_BAR') else type(error).__name__
                state['failures'].append(dict(chunk=task_key(active) if active else None,reason=safe))
                finish('INVALID_RESPONSE')
        try:client.send(req,responseTimeoutInSeconds=25).addCallbacks(got,lambda _:finish('REQUEST_FAILED'))
        except Exception:finish('SEND_FAILED')
    def request_page():
        send(ProtoOAGetTrendbarsReq(ctidTraderAccountId=account,symbolId=symbol,period=PERIODS[active['interval']][0],
             fromTimestamp=active['start']*1000,toTimestamp=cursor,count=(active['end']-active['start'])//PERIODS[active['interval']][1]+1),ProtoOAGetTrendbarsRes,received_bars)
    def next_task():
        nonlocal active,bars,cursor
        if not queue:finish('COMPLETE');return
        if max_chunks is not None and processed>=max_chunks:finish('CHECKPOINT');return
        active=queue.pop(0);bars={};cursor=active['end']*1000-1;request_page()
    def received_bars(response):
        nonlocal cursor,processed
        stamps=[int(b.utcTimestampInMinutes)*60 for b in response.trendbar]
        state['last_page_diagnostic']=dict(requested_year=datetime.fromtimestamp(active['start'],timezone.utc).year,
            returned_count=len(stamps),returned_years=sorted({datetime.fromtimestamp(t,timezone.utc).year for t in stamps}),
            before_start=sum(t<active['start'] for t in stamps),at_end=sum(t==active['end'] for t in stamps),after_end=sum(t>active['end'] for t in stamps),
            negative_volume=sum(int(b.volume)<0 for b in response.trendbar))
        page=decode_page(response.trendbar,active,int(datetime.now(timezone.utc).timestamp()))
        for b in page:
            if b['time'] in bars and bars[b['time']]!=b:raise ValueError('CONFLICTING_BAR')
            bars[b['time']]=b
        # SDK 0.9.2 predates hasMore. Without it, walk backwards until the
        # requested boundary or an empty page; never assume a server cap.
        has_flag='hasMore' in response.DESCRIPTOR.fields_by_name and response.HasField('hasMore')
        reached_start=bool(stamps) and min(stamps)<=active['start']
        more=(bool(response.hasMore) if has_flag else bool(page)) and not reached_start
        if more:
            cursor=next_cursor(page,cursor)
            if cursor>=active['start']*1000:reactor.callLater(.55,request_page);return
        values=sorted(bars.values(),key=lambda b:b['time'])
        payload=dict(**active,source_key=identity,source='ctrader_demo_native',volume_basis='broker_native_tick_count',
          status='AVAILABLE' if values else 'EMPTY',bars=values)
        path=output/(task_key(active)+'.json');temp=path.with_suffix('.tmp')
        temp.write_text(json.dumps(payload,separators=(',',':')),encoding='utf-8');temp.replace(path)
        state['completed_chunks']+=1;state['empty_chunks']+=not bool(values);state['rows']+=len(values);processed+=1
        save()
        print(f"chunk {state['completed_chunks']}/{state['requested_chunks']} {active['interval']} {datetime.fromtimestamp(active['start'],timezone.utc).date()} rows={len(values)}",flush=True)
        reactor.callLater(.55,next_task)
    def symbols(response):
        nonlocal symbol,identity,queue
        item=next((s for s in response.symbol if s.enabled and s.symbolName.upper()=='XAUUSD'),None)
        if item is None:finish('XAUUSD_MISSING');return
        symbol=item.symbolId;identity=hashlib.sha256(f'ctrader-demo:{account}:{symbol}'.encode()).hexdigest()
        state['source_key']=identity
        for task in tasks:
            path=output/(task_key(task)+'.json')
            try:
                prior=json.loads(path.read_text(encoding='utf-8'))
                if prior['source_key']!=identity:finish('SOURCE_IDENTITY_CHANGED');return
                if prior['start']!=task['start'] or prior['end']!=task['end'] or prior['interval']!=task['interval'] or prior['status'] not in ('AVAILABLE','EMPTY'):raise ValueError('invalid cache')
                state['completed_chunks']+=1;state['empty_chunks']+=prior['status']=='EMPTY';state['rows']+=len(prior['bars'])
            except (OSError,ValueError,KeyError,TypeError):queue.append(task)
        state['status']='DOWNLOADING';save();next_task()
    def authorized(_):send(ProtoOASymbolsListReq(ctidTraderAccountId=account),ProtoOASymbolsListRes,symbols)
    def accounts(response):
        nonlocal account
        requested=config.get('CTRADER_ACCOUNT_ID');choices=[a for a in response.ctidTraderAccount if not a.isLive]
        item=next((a for a in choices if str(a.ctidTraderAccountId)==requested),None) if requested else next(iter(choices),None)
        if item is None:finish('DEMO_ACCOUNT_UNAVAILABLE');return
        account=item.ctidTraderAccountId
        send(ProtoOAAccountAuthReq(ctidTraderAccountId=account,accessToken=config['CTRADER_ACCESS_TOKEN']),ProtoOAAccountAuthRes,authorized)
    def app_authorized(_):send(ProtoOAGetAccountListByAccessTokenReq(accessToken=config['CTRADER_ACCESS_TOKEN']),ProtoOAGetAccountListByAccessTokenRes,accounts)
    def connected(_):send(ProtoOAApplicationAuthReq(clientId=config['CTRADER_CLIENT_ID'],clientSecret=config['CTRADER_CLIENT_SECRET']),ProtoOAApplicationAuthRes,app_authorized)
    def heartbeat():
        if stopping:return
        client.send(ProtoHeartbeatEvent()).addErrback(lambda _:None);reactor.callLater(10,heartbeat)
    client.setConnectedCallback(connected);client.startService();reactor.callLater(10,heartbeat)
    reactor.callLater(max(180,len(tasks)*10),lambda:finish('TIMEOUT'))
    reactor.run(installSignalHandlers=False)
    print(json.dumps({k:v for k,v in state.items() if k!='source_key'},ensure_ascii=False),flush=True)
    return state


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--max-chunks',type=int);parser.add_argument('--pilot',action='store_true');args=parser.parse_args()
    data=json.loads((ROOT/'private/case_candidate_market_profiles.json').read_text(encoding='utf-8'))
    tasks=plan(data['profiles'])
    if args.pilot:
        chosen=[]
        for iv in PERIODS:
            group=[t for t in tasks if t['interval']==iv]
            chosen.extend(group[i] for i in sorted({0,len(group)//2,len(group)-1}))
        tasks=chosen
    try:result=fetch(tasks,max_chunks=args.max_chunks)
    except Exception:
        print('FETCH_FAILED (credentials and raw errors suppressed)');raise SystemExit(1)
    raise SystemExit(0 if result['status'] in ('COMPLETE','CHECKPOINT') else 1)
