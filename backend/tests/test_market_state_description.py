from backend.market_state_description import describe_market_state


def _profile(tier='5m_only'):
    indicators = {'5m_atr_pct': '0.10', '5m_ma_gap': '0.5', '5m_slope': '-0.02',
                  '5m_rsi14': '58', '5m_macd_hist': '0.03', 'range_position': '0.75'}
    frames = {'5m': [{'close': str(100 + index)} for index in range(60)]}
    closed = {'5m': 1000}
    if tier == 'full':
        indicators.update({'15m_atr_pct': '0.2', '15m_ma_gap': '0.3',
                           '15m_rsi14': '52', '15m_macd_hist': '0.01',
                           '1h_atr_pct': '0.4', '1h_ma_gap': '-0.2'})
        frames.update({'15m': [{}], '1h': [{}]})
        closed.update({'15m': 990, '1h': 960})
    return {'status': 'candidate_only', 'tier': tier, 'as_of': 1000,
            'latest_closed': closed, 'pre_entry_bars': frames,
            'indicators': indicators, 'timezone_status': 'UNKNOWN',
            'profit': '999999'}


def test_description_uses_pre_entry_market_and_omits_outcome():
    result = describe_market_state(_profile('full'))
    assert result['schema_version'] == 'pre_entry_market_v1'
    assert result['values']['5m_path_change_pct'] == '59.00'
    assert '首尾收盤變動 59.00%' in result['text']
    assert result['values']['5m_range_position'] == '75.00'
    assert '15分鐘' in result['text'] and '1小時' in result['text']
    assert '999999' not in result['text']


def test_limited_tier_declares_missing_frames():
    result = describe_market_state(_profile())
    assert result['tier'] == '5m_only'
    assert '資料不足' in result['text']
    assert '15m_atr_pct' not in result['values']


def test_future_bar_and_missing_indicator_are_rejected():
    import pytest
    profile = _profile()
    profile['latest_closed']['5m'] = 1001
    with pytest.raises(ValueError, match='future bar'):
        describe_market_state(profile)
    profile = _profile()
    del profile['indicators']['5m_rsi14']
    with pytest.raises(ValueError, match='missing numeric'):
        describe_market_state(profile)
    profile = _profile()
    del profile['indicators']['range_position']
    with pytest.raises(ValueError, match='missing numeric'):
        describe_market_state(profile)
    profile = _profile()
    profile['pre_entry_bars']['5m'][0]['close'] = 'NaN'
    with pytest.raises(ValueError, match='invalid closes'):
        describe_market_state(profile)
