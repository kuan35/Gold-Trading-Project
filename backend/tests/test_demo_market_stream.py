from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from starlette.requests import Request

from backend.app import _local_broker_access
from backend.demo_market_stream import DemoMarketStream, _advance_order
from scripts import stream_ctrader_demo
from scripts.stream_ctrader_demo import decode_bar, money


class Bar:
    utcTimestampInMinutes = 30000000
    low = 416100000
    deltaOpen = 20000
    deltaHigh = 50000
    deltaClose = 30000
    volume = 47


def test_closed_broker_bar_decoding_and_forming_bar_exclusion():
    now_ms = (Bar.utcTimestampInMinutes + 5) * 60000
    result = decode_bar(Bar(), 2, 5, now_ms)
    assert result == {'time': Bar.utcTimestampInMinutes * 60,
                      'open': 4161.2, 'high': 4161.5, 'low': 4161.0,
                      'close': 4161.3, 'volume': 47}
    assert decode_bar(Bar(), 2, 5, now_ms - 1) is None
    assert money(1000000000000, 8) == '10000.00000000'


def test_symbol_schedule_payload_retains_broker_session_boundaries():
    symbol = SimpleNamespace(scheduleTimeZone='UTC', schedule=[
        SimpleNamespace(startSecond=22 * 3600, endSecond=45 * 3600),
        SimpleNamespace(startSecond=46 * 3600, endSecond=69 * 3600),
    ])
    assert stream_ctrader_demo.decode_symbol_schedule(symbol) == {
        'time_zone': 'UTC',
        'intervals': [{'start_second': 79200, 'end_second': 162000},
                      {'start_second': 165600, 'end_second': 248400}],
    }


def test_market_snapshot_marks_old_tick_stale_and_excludes_credentials():
    stream = DemoMarketStream()
    stream._start = lambda: None
    source_time = (datetime.now(timezone.utc) - timedelta(minutes=4)).isoformat()
    stream._quote = {'status': 'CURRENT', 'bid': '4161.00', 'ask': '4161.20',
                     'source_time_utc': source_time, 'age_seconds': 0,
                     'source': 'ctrader_demo_xauusd', 'environment': 'demo',
                     'order_connection': False}
    stream._account = {'status': 'CURRENT', 'balance': '10000.00', 'equity': '9999.00'}
    value = stream.snapshot()
    assert value['quote']['status'] == 'STALE'
    assert value['order_connection'] is False
    assert value['account']['balance'] == '10000.00'
    assert 'account_id' not in str(value).lower()
    assert 'access_token' not in str(value).lower()


def test_disconnected_stream_never_labels_cached_quote_or_bars_current():
    stream = DemoMarketStream()
    stream._start = lambda: None
    stream._status = 'DISCONNECTED'
    stream._quote = {'status': 'CURRENT', 'bid': '4161.00', 'ask': '4161.20',
                     'source_time_utc': datetime.now(timezone.utc).isoformat(),
                     'age_seconds': 0, 'source': 'ctrader_demo_xauusd',
                     'environment': 'demo', 'order_connection': False}
    stream._account = {'status': 'CURRENT', 'balance': '10000.00'}
    stream._bars['5m'] = [{'time': 1800000000, 'close': 4161.0}]
    assert stream.snapshot()['quote']['status'] == 'STALE'
    assert stream.snapshot()['account']['status'] == 'STALE'
    assert stream.bars('5m')['status'] == 'STALE'


def test_broker_market_endpoint_is_loopback_only():
    local = Request({'type': 'http', 'scheme': 'http', 'path': '/', 'client': ('127.0.0.1', 12345),
                     'headers': [(b'host', b'127.0.0.1:8765')]})
    remote = Request({'type': 'http', 'scheme': 'http', 'path': '/', 'client': ('192.0.2.5', 12345),
                      'headers': [(b'host', b'127.0.0.1:8765')]})
    rebinding = Request({'type': 'http', 'scheme': 'http', 'path': '/', 'client': ('127.0.0.1', 12345),
                         'headers': [(b'host', b'example.org')]})
    cross_site = Request({'type': 'http', 'scheme': 'http', 'path': '/', 'client': ('127.0.0.1', 12345),
                          'headers': [(b'host', b'127.0.0.1:8765'),
                                      (b'origin', b'https://example.org')]})
    assert _local_broker_access(local)
    assert not _local_broker_access(remote)
    assert not _local_broker_access(rebinding)
    assert not _local_broker_access(cross_site)


def test_late_unknown_event_cannot_hide_broker_acceptance_or_fill():
    accepted = _advance_order(None, {'status': 'ACCEPTED', 'order_id': '123'})
    assert _advance_order(accepted, {'status': 'UNKNOWN'}) == accepted
    filled = _advance_order(accepted, {'status': 'FILLED', 'execution_price': '2500.10'})
    assert filled['order_id'] == '123'
    assert filled['execution_price'] == '2500.10'
    assert _advance_order(filled, {'status': 'PARTIALLY_FILLED'}) == filled
