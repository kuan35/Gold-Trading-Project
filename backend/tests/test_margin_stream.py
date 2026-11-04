from datetime import datetime,timezone
from io import StringIO
from types import SimpleNamespace
import json
from backend.demo_market_stream import DemoMarketStream


def ready():
    stream=DemoMarketStream();stream._start=lambda:None;stream._status='CONNECTED'
    stream._quote=dict(source_time_utc=datetime.now(timezone.utc).isoformat(),status='CURRENT',bid='4000',ask='4000.20')
    stream._account=dict(account_key='synthetic',currency='USD',status='CURRENT',updated_at_utc=datetime.now(timezone.utc).isoformat(),positions=[],pending_orders=[])
    stream._symbol=dict(lot_size_cents=10000,digits=2)
    stream._process=SimpleNamespace(stdin=StringIO())
    return stream


def test_expected_margin_never_uses_trading_channel_and_cannot_cross_exposure_or_accounts():
    stream=ready();snapshot=stream.snapshot()
    assert stream.expected_margin(snapshot,5000) is None
    commands=[json.loads(line) for line in stream._process.stdin.getvalue().splitlines()]
    assert len(commands)==1 and commands[0]['kind']=='expected_margin'
    assert commands[0]['volume_cents']==5000 and not stream._commands and not stream._order_results
    stream.expected_margin(snapshot,5000)
    assert len(stream._process.stdin.getvalue().splitlines())==1
    from time import monotonic
    stream._margin_cache.accept(dict(request_id=commands[0]['request_id'],status='AVAILABLE',buy='1000',sell='1100',currency='USD'),now=monotonic())
    assert stream.expected_margin(snapshot,5000)['buy']=='1000'
    stream._account['positions']=[dict(id='p',side='BUY',volume_units='10')]
    assert stream.expected_margin(snapshot,5000) is None
    stream._account['account_key']='other'
    assert stream.expected_margin(snapshot,5000) is None


def test_disconnected_nonusd_and_live_streams_do_not_query_margin():
    stream=ready();stream._account['currency']='EUR'
    assert stream.expected_margin(stream.snapshot(),5000) is None
    stream._account['currency']='USD';stream.module='scripts.stream_ctrader_live'
    assert stream.expected_margin(stream.snapshot(),5000) is None
    stream.module='scripts.stream_ctrader_demo';stream._status='DISCONNECTED'
    assert stream.expected_margin(stream.snapshot(),5000) is None
    assert stream._process.stdin.getvalue()==''


def test_installed_official_protobuf_margin_money_and_default_precision():
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAExpectedMarginReq,ProtoOAExpectedMarginRes
    from scripts.expected_margin import decode_margin
    request=ProtoOAExpectedMarginReq(ctidTraderAccountId=1,symbolId=2,volume=[5000])
    assert list(request.volume)==[5000]
    response=ProtoOAExpectedMarginRes(ctidTraderAccountId=1)
    response.margin.add(volume=5000,buyMargin=100000,sellMargin=110000)
    assert decode_margin(response,1,5000,'USD')['buy']=='1000.00'
