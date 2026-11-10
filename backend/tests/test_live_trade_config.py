import pytest

from scripts.live_readonly_policy import load_live_trade_config


def test_live_trade_config_requires_explicit_enable_and_both_limits(tmp_path):
    path = tmp_path / 'live.env'
    base = ('CTRADER_ENVIRONMENT=live\nCTRADER_CLIENT_ID=a\nCTRADER_CLIENT_SECRET=b\n'
            'CTRADER_ACCESS_TOKEN=c\nCTRADER_ACCOUNT_ID=123\n')
    path.write_text(base, encoding='utf-8')
    with pytest.raises(ValueError, match='LIVE_TRADING_DISABLED'):
        load_live_trade_config(path)
    path.write_text(base + 'CTRADER_LIVE_TRADING_ENABLED=YES\n', encoding='utf-8')
    with pytest.raises(ValueError, match='LIVE_LIMITS_MISSING'):
        load_live_trade_config(path)
    path.write_text(base + 'CTRADER_LIVE_TRADING_ENABLED=YES\n'
                    'GOLD_LIVE_MAX_ORDER_STOP_USD=50\nGOLD_LIVE_MAX_GROSS_LOTS=0.1\n', encoding='utf-8')
    assert load_live_trade_config(path)['CTRADER_ACCOUNT_ID'] == '123'
    path.write_text(path.read_text(encoding='utf-8').replace('0.1', 'NaN'), encoding='utf-8')
    with pytest.raises(ValueError, match='LIVE_LIMITS_INVALID'):
        load_live_trade_config(path)
