from backend.live_trade_stream import LiveTradeStream


def test_live_trade_stream_is_separate_and_does_not_inherit_demo_authority():
    stream = LiveTradeStream()
    value = stream._snapshot_locked()
    assert value['environment'] == 'live'
    assert value['source'] == 'ctrader_live_xauusd'
    assert value['order_connection'] is False
    assert stream.module == 'scripts.stream_ctrader_live_trade'


def test_live_trade_process_is_distinct_from_readonly_process():
    from backend.live_readonly import LiveReadOnlyStream
    assert LiveReadOnlyStream().module != LiveTradeStream().module
