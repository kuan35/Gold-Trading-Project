from copy import deepcopy

import pytest

from backend.compact_market import describe_compact, rank_compact


def profile(clock=200000, *, tier='full', factor=1):
    def candles(count, seconds):
        return [dict(time=clock - count * seconds + i * seconds,
                     open=str((100 + i * 0.02) * factor),
                     close=str((100 + i * 0.02) * factor),
                     high=str((100.2 + i * 0.02) * factor),
                     low=str((99.8 + i * 0.02) * factor)) for i in range(count)]
    return dict(status='candidate_only', tier=tier, as_of=clock,
                indicators={'5m_atr_pct': '0.5', '1h_atr_pct': '0.8'},
                pre_entry_bars={'5m': candles(60, 300),
                                **({'1h': candles(20, 3600)} if tier == 'full' else {})})


def case(ident, group=None, available=100000, side='BUY'):
    return dict(id=ident, group=group or ident, side=side,
                available_at=available, lot='0.1', profit='1', action='FIRST')


def test_structure_uses_previous_twenty_bars_and_distinguishes_close_and_wick():
    p = profile()
    previous_high = max(float(b['high']) for b in p['pre_entry_bars']['5m'][-21:-1])
    last = p['pre_entry_bars']['5m'][-1]
    last.update(open=str(previous_high), close=str(previous_high + .2),
                high=str(previous_high + 1), low=str(previous_high - .1))
    result = describe_compact(p, 'BUY')
    assert result['structure'] == 'CLOSE_ABOVE'
    assert float(result['reference_high']) == previous_high
    last['close'] = str(previous_high)
    result = describe_compact(p, 'BUY')
    assert result['structure'] == 'UPPER_SWEEP_RETURN'
    assert result['high_gap_atr'] == 0


def test_lower_and_both_wicks_are_not_called_confirmed_breakouts():
    p = profile()
    bars = p['pre_entry_bars']['5m']
    low = min(float(b['low']) for b in bars[-21:-1])
    high = max(float(b['high']) for b in bars[-21:-1])
    middle = str((low + high) / 2)
    bars[-1].update(open=middle, close=middle, low=str(low - .1), high=str(high))
    assert describe_compact(p, 'BUY')['structure'] == 'LOWER_SWEEP_RETURN'
    bars[-1]['high'] = str(high + .1)
    assert describe_compact(p, 'BUY')['structure'] == 'BOTH_SWEEPS_RETURN'
    bars[-1].update(close=str(low - .05), open=str(low), high=str(low + .1))
    assert describe_compact(p, 'BUY')['structure'] == 'CLOSE_BELOW'


def test_descriptor_has_both_phase_codes_and_uses_no_future_bar():
    p = profile()
    d = describe_compact(p, 'BUY')
    assert len(d['phase_5m_atr']) == len(d['phase_1h_atr']) == 3
    assert d['window_start'] == p['as_of'] - 20 * 3600
    assert d['window_end'] == p['as_of']
    p['pre_entry_bars']['1h'][-1]['time'] = p['as_of']
    with pytest.raises(ValueError, match='future'):
        describe_compact(p, 'BUY')


@pytest.mark.parametrize('bad', ['NaN', '0', '-1', 'Infinity'])
def test_invalid_atr_is_rejected(bad):
    p = profile()
    p['indicators']['5m_atr_pct'] = bad
    with pytest.raises(ValueError):
        describe_compact(p, 'BUY')


def test_price_scale_does_not_change_unitless_description():
    a = describe_compact(profile(), 'BUY')
    b = describe_compact(profile(factor=3), 'BUY')
    assert a['pattern_5m'] == b['pattern_5m']
    assert a['pattern_1h'] == b['pattern_1h']
    assert a['structure'] == b['structure']
    assert a['phase_5m_atr'] == pytest.approx(b['phase_5m_atr'])
    assert a['phase_1h_atr'] == pytest.approx(b['phase_1h_atr'])


def test_constant_price_offset_with_same_absolute_atr_preserves_shape():
    original = profile()
    shifted = deepcopy(original)
    for label, bars in shifted['pre_entry_bars'].items():
        old_last = float(bars[-1]['close'])
        for bar in bars:
            for key in ('open', 'high', 'low', 'close'):
                bar[key] = str(float(bar[key]) + 10)
        shifted['indicators'][label + '_atr_pct'] = str(
            float(original['indicators'][label + '_atr_pct']) * old_last / (old_last + 10))
    a, b = describe_compact(original, 'BUY'), describe_compact(shifted, 'BUY')
    assert a['phase_5m_atr'] == pytest.approx(b['phase_5m_atr'])
    assert a['phase_1h_atr'] == pytest.approx(b['phase_1h_atr'])
    assert a['structure'] == b['structure']


def test_exact_one_atr_is_neutral_and_a_larger_move_is_directional():
    p = profile()
    for i, bar in enumerate(p['pre_entry_bars']['5m']):
        close = 100.5 if i in (19, 39) else 100
        bar.update(open=str(close), close=str(close), high=str(close + .2), low=str(close - .2))
    assert describe_compact(p, 'BUY')['pattern_5m'] == 'SSS'
    bar = p['pre_entry_bars']['5m'][19]
    bar.update(open='100.50001', close='100.50001')
    assert describe_compact(p, 'BUY')['pattern_5m'] == 'USS'


def test_missing_hourly_data_stays_explicitly_limited():
    d = describe_compact(profile(tier='5m_only'), 'BUY')
    assert d['pattern_1h'] is None and d['phase_1h_atr'] is None
    assert '資料不足' in d['text']
    result = rank_compact([], {}, d)
    assert result['status'] == 'INSUFFICIENT_QUERY'


def test_time_group_overlap_side_and_window_deduplication():
    query = describe_compact(profile(), 'BUY')
    earlier = describe_compact(profile(90000), 'BUY')
    rows = [case('a'), case('a2', group='a'), case('duplicate-window'),
            case('future', available=300000), case('own', group='query'),
            case('overlap'), case('sell', side='SELL')]
    descriptions = {r['id']: deepcopy(earlier) for r in rows}
    descriptions['overlap'] = describe_compact(profile(190000), 'BUY')
    descriptions['sell'] = describe_compact(profile(90000), 'SELL')
    result = rank_compact(rows, descriptions, query, exclude_group='query')
    assert [r['case_id'] for r in result['rows']] == ['a']
    assert result['counts']['excluded_overlap_rows'] == 1
    assert result['rows'][0]['agreement_count'] == 4
    assert result['rows'][0]['field_count'] == 4


def test_future_pool_values_do_not_change_volatility_boundaries_or_ranks():
    q = describe_compact(profile(), 'BUY')
    d = describe_compact(profile(90000), 'BUY')
    base = rank_compact([case('a')], {'a': d}, q)
    future = deepcopy(d)
    future['atr_pct_5m'] = 100
    changed = rank_compact([case('a'), case('future', available=300000)],
                           {'a': d, 'future': future}, q)
    assert base['volatility_bounds'] == changed['volatility_bounds']
    assert base['rows'] == changed['rows']


def test_outcomes_size_action_and_input_order_never_change_ranking():
    q = describe_compact(profile(), 'BUY')
    rows = [case('b'), case('a')]
    descriptions = {'a': describe_compact(profile(90000), 'BUY'),
                    'b': describe_compact(profile(80000), 'BUY')}
    before = rank_compact(rows, descriptions, q)
    changed = [dict(r, profit='-9999', lot='55', action='ADD') for r in reversed(rows)]
    after = rank_compact(changed, descriptions, q)
    assert before == after
    assert before['rows'][0]['case_id'] == 'a'


def test_empty_eligible_pool_is_not_presented_as_a_similarity_match():
    q = describe_compact(profile(), 'BUY')
    result = rank_compact([case('a', available=300000)], {}, q)
    assert result['status'] == 'NO_MATCH' and not result['rows']
