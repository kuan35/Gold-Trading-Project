from copy import deepcopy
from scripts.live_candles import LiveCandles

NOW=1800000123456


def test_all_intervals_follow_bid_ticks_and_volume_is_observed_not_fake():
    live=LiveCandles()
    live.observe(400000000,NOW,2,NOW)
    live.observe(400050000,NOW+10,2,NOW+10)
    live.observe(399980000,NOW+20,2,NOW+20)
    for interval in ('5m','15m','1h'):
        item=live.frame(interval)
        b=item['bar']
        assert (b['open'],b['high'],b['low'],b['close'],b['volume'])==(4000,4000.5,3999.8,3999.8,3)
        assert item['volume_basis']=='observed_bid_updates'
        assert item['partial'] is True


def test_duplicate_older_stale_and_future_ticks_never_mutate_candle():
    live=LiveCandles();live.observe(400000000,NOW,2,NOW)
    original=deepcopy(live.frame('5m'))
    for value,t,now in [(400000000,NOW,NOW),(399000000,NOW-1,NOW),
                        (399000000,NOW+1,NOW+10000),(399000000,NOW+10000,NOW)]:
        live.observe(value,t,2,now)
    assert live.frame('5m')==original


def test_small_future_tick_cannot_advance_bucket_or_poison_next_tick():
    live=LiveCandles();boundary=1800000300000
    live.observe(400000000,boundary-100,2,boundary-100)
    live.observe(400050000,boundary+100,2,boundary-100)
    assert live.frame('5m')['bar']['time']==(boundary-300000)//1000
    live.observe(400010000,boundary,2,boundary)
    assert live.frame('5m')['bar']['close']==4000.1


def test_rollover_does_not_fabricate_gaps_and_keeps_pending_bar_for_display():
    live=LiveCandles();start=1800000000000
    live.observe(400000000,start+100,2,start+100)
    live.observe(400010000,start+300000,2,start+300000)
    frame=live.frame('5m')
    assert frame['bar']['time']==(start+300000)//1000
    assert frame['bar']['volume']==1 and frame['partial'] is True  # no ticks observed across this gap
    assert frame['pending_bars'][0]['time']==start//1000
    assert live.frame('15m')['bar']['volume']==2
    live.observe(400020000,start+1200000,2,start+1200000)
    assert len(live.frame('5m')['pending_bars'])==2


def test_continuously_observed_next_period_is_not_labelled_mid_connection():
    live=LiveCandles();start=1800000000000
    for t in range(start,start+300001,5000):live.observe(400000000,t,2,t)
    assert live.frame('5m')['partial'] is False


def test_native_forming_seed_repairs_open_and_extremes_not_tick_count_or_latest_close():
    live=LiveCandles();live.observe(400000000,NOW,2,NOW)
    t=(NOW//300000)*300
    live.seed('5m',dict(time=t,open=3998.,high=4002.,low=3997.,close=4001.,volume=999))
    b=live.frame('5m')['bar']
    assert b==dict(time=t,open=3998.,high=4002.,low=3997.,close=4000.,volume=1)
    assert live.frame('5m')['price_basis']=='broker_seed_and_bid_ticks'


def test_forming_display_never_enters_closed_retrieval_snapshot():
    from backend.demo_market_stream import DemoMarketStream
    stream=DemoMarketStream();stream._start=lambda:None;stream._status='CONNECTED'
    live=LiveCandles();live.observe(400000000,NOW,2,NOW)
    stream._forming={'5m':live.frame('5m')}
    closed=dict(time=1799999700,open=3998.,high=3999.,low=3997.,close=3998.5,volume=19)
    stream._bars={'5m':[closed]}
    assert stream.query_snapshot()['bars']=={'5m':[closed]}
    assert stream.bars('5m')['bars']==[closed]
    drawing=stream.chart_snapshot('5m',now_ms=NOW)
    assert drawing['forming']['bar']['close']==4000.
    assert drawing['bars']==[closed] and drawing['closed_only'] is False
    stream._status='DISCONNECTED'
    assert stream.chart_snapshot('5m',now_ms=NOW)['forming'] is None


def test_chart_snapshot_freezes_stale_forming_bar():
    from backend.demo_market_stream import DemoMarketStream
    stream=DemoMarketStream();stream._start=lambda:None;stream._status='CONNECTED'
    live=LiveCandles();live.observe(400000000,NOW,2,NOW)
    stream._forming={'5m':live.frame('5m')}
    assert stream.chart_snapshot('5m',now_ms=NOW+6000)['forming'] is None


def test_close_transport_builds_position_request_instead_of_reverse_entry():
    from scripts.ctrader_account_payloads import close_request_args
    positions=[dict(id='12',volume_units='12.50')]
    args=close_request_args({'position_id':'12','volume_cents':1250},123,positions)
    assert args==dict(ctidTraderAccountId=123,positionId=12,volume=1250)
    import pytest
    with pytest.raises(ValueError):close_request_args({'position_id':'12','volume_cents':2500},123,positions)
    with pytest.raises(ValueError):close_request_args({'position_id':'14','volume_cents':1250},123,positions)


def test_close_event_correlation_ignores_external_closes_and_uses_request_id():
    import ast
    from pathlib import Path
    from types import SimpleNamespace as N
    class Proto(N):
        def HasField(self,name):return hasattr(self,name)
    tree=ast.parse(Path('scripts/stream_ctrader_demo.py').read_text(encoding='utf-8'))
    run=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run')
    callback=next(n for n in run.body if isinstance(n,ast.FunctionDef) and n.name=='execution_result')
    scope={'account_id':7,'order_ids':{10:'gd-first-close'},'request_commands':{}}
    exec(compile(ast.Module(body=[callback],type_ignores=[]),'callback','exec'),scope)
    order=Proto(orderId=99,positionId=12,closingOrder=True,clientOrderId='gd-original-entry',executionPrice=4000.)
    event=Proto(ctidTraderAccountId=7,order=order,executionType=3)
    assert scope['execution_result'](event) is None
    result=scope['execution_result'](event,'gd-current-close')
    assert result['client_order_id']=='gd-current-close' and result['status']=='FILLED'
    assert scope['execution_result'](event)['client_order_id']=='gd-current-close'


def test_chart_sse_is_local_only_and_display_stream_has_no_order_permission(monkeypatch):
    import importlib,asyncio,json
    from types import SimpleNamespace
    app=importlib.import_module('backend.app')
    stream=SimpleNamespace(chart_snapshot=lambda interval:dict(interval=interval,bars=[],forming=None))
    monkeypatch.setattr(app,'demo_market_stream',stream)
    request=SimpleNamespace(client=SimpleNamespace(host='127.0.0.1'),url=SimpleNamespace(hostname='127.0.0.1'),headers={},
        is_disconnected=lambda:asyncio.sleep(0,result=False))
    response=app.broker_demo_chart_stream(request,'5m')
    assert response.media_type=='text/event-stream' and response.headers['cache-control']=='no-store'
    async def one():
        iterator=app.broker_chart_events(request,'5m')
        value=await anext(iterator);await iterator.aclose();return value
    payload=json.loads(asyncio.run(one()).split('data: ')[1])
    assert payload['forming'] is None
    request.client.host='192.0.2.1'
    assert app.broker_demo_chart_stream(request,'5m').status_code==403
    assert app.broker_demo_close_draft(request,'12').status_code==403
