from types import SimpleNamespace

from scripts.stream_ctrader_demo import decode_trader_leverage


def test_live_account_leverage_uses_broker_cents_not_demo_default():
    trader = SimpleNamespace(leverageInCents=3000, maxLeverage=3000)
    assert decode_trader_leverage(trader) == '30'


def test_missing_or_invalid_leverage_stays_unknown():
    assert decode_trader_leverage(SimpleNamespace(leverageInCents=0)) is None
    assert decode_trader_leverage(SimpleNamespace()) is None
