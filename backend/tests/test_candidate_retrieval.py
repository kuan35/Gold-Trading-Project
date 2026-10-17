from backend.candidate_retrieval import rank_candidates, summarize_candidate_tier


FIVE = ('5m_ma_gap', '5m_atr_pct', '5m_rsi14', '5m_macd_hist',
        '5m_slope', 'range_position')
HIGH = ('15m_ma_gap', '15m_atr_pct', '15m_rsi14', '15m_macd_hist',
        '1h_ma_gap', '1h_atr_pct')


def profile(shape, indicator, tier='full'):
    keys = FIVE + HIGH if tier == 'full' else FIVE
    return dict(status='candidate_only', tier=tier, as_of=100,
                shape=[str(shape)] * 240,
                indicators={key: str(indicator) for key in keys})


def case(case_id, group=None, side='BUY', available_at=50, **extra):
    return dict(id=case_id, group=group or case_id, side=side,
                available_at=available_at, lot='0.1', action='FIRST',
                profit='5', exit='2000', **extra)


def test_two_axis_rank_is_deterministic_and_ignores_operation_and_outcome():
    cases = [case('A'), case('B'), case('C'), case('D', side='SELL'),
             case('E', available_at=150), case('F', group='B')]
    profiles = {key: profile(i, 2 - i) for i, key in enumerate('ABC')}
    profiles.update(D=profile(0, 0), E=profile(0, 0), F=profile(0, 0, '5m_only'))
    query = profile(0, 0)
    first = rank_candidates(cases, profiles, query, 'BUY', 100)
    assert [row['case_id'] for row in first['full']] == ['B', 'A', 'C']
    assert first['five_minute_only'] == []  # group B already appears in full tier
    changed = [dict(item, lot='9', action='ADD', profit='-9999', exit='9999') for item in cases]
    second = rank_candidates(list(reversed(changed)), profiles, query, 'BUY', 100)
    assert [row['case_id'] for row in second['full']] == ['B', 'A', 'C']
    assert second['similarity_sufficiency'] == 'UNCALIBRATED'


def test_query_with_only_five_minutes_never_claims_full_comparison():
    cases = [case('A'), case('B')]
    profiles = {'A': profile(0, 0), 'B': profile(1, 1, '5m_only')}
    result = rank_candidates(cases, profiles, profile(0, 0, '5m_only'), 'BUY', 100)
    assert result['full'] == []
    assert len(result['five_minute_only']) == 2
    assert summarize_candidate_tier(result['five_minute_only'], {x['id']: x for x in cases})['label'] == '歷史結果分布'
