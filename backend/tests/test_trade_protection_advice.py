from backend.trade_protection_advice import protection_advice


def test_breakout_references_boundary_and_projects_range():
    signal = dict(kind='ABOVE', side='BUY', high='110', low='100', buffer='1')
    result = protection_advice(signal, entry='112', digits=2)
    assert result['stop'] == '109.00'
    assert result['target'] == '120.00'
    assert result['reward_risk_ratio'] == '2.67'


def test_reclaim_stop_respects_excursion_and_short_prices_mirror():
    signal = dict(kind='UPPER_RECLAIM', side='SELL', high='110', low='100', buffer='1')
    result = protection_advice(signal, entry='106', digits=2, recent_high='113')
    assert result['stop'] == '114.00'
    assert result['target'] == '100.00'
    assert result['reward_risk_ratio'] == '0.75'


def test_chased_price_has_no_valid_target():
    signal = dict(kind='ABOVE', side='BUY', high='110', low='100', buffer='1')
    result = protection_advice(signal, entry='121', digits=2)
    assert result['status'] == 'UNAVAILABLE'
    assert result['target'] is None


def test_limit_entry_that_already_crosses_invalidation_is_unavailable():
    signal = dict(kind='BELOW', side='SELL', high='110', low='100', buffer='1')
    assert protection_advice(signal, entry='102', digits=2)['status'] == 'UNAVAILABLE'
