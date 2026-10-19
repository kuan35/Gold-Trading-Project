"""The local hybrid mode must be reproducible and point-in-time safe."""

from decimal import Decimal

from backend.cases import CaseStore
from backend.candidate_retrieval import FIVE, HIGH
from backend.hybrid_retrieval import rank_hybrid_candidates, rerank_pattern_window


def profile(code='UDU', *, clock=18000, tier='full', bump=0):
    anchors = {'UDU': (100, 103, 100, 103), 'UUU': (100, 103, 106, 109),
               'DDD': (100, 97, 94, 91)}[code]
    closes = []
    for index in range(60):
        segment = 0 if index <= 19 else 1 if index <= 39 else 2
        start, end = (0, 19) if segment == 0 else (19, 39) if segment == 1 else (39, 59)
        value = anchors[segment] + (anchors[segment + 1] - anchors[segment]) * (index - start) / (end - start)
        closes.append(str(value + bump))
    bars = [dict(time=clock - 18000 + index * 300, close=value,
                 open=value, high=value, low=value) for index, value in enumerate(closes)]
    keys = FIVE + HIGH if tier == 'full' else FIVE
    return dict(status='candidate_only', tier=tier, as_of=clock,
                timezone_status='UNKNOWN', latest_closed={'5m': clock,
                    **({'15m': clock, '1h': clock} if tier == 'full' else {})},
                indicators={key: '0.5' if key == '5m_atr_pct' else '0' for key in keys},
                pre_entry_bars={'5m': bars, **({'15m': [], '1h': []} if tier == 'full' else {})})


def case(ident, *, side='BUY', group=None, available_at=16000, lot='0.1', profit='1'):
    return dict(id=ident, side=side, group=group or ident, available_at=available_at,
                lot=lot, profit=profit, action='FIRST', label=ident,
                source_kind='trader_history', time_alignment='unknown')


def test_pattern_rerank_deduplicates_groups_and_never_searches_beyond_window():
    rows = [dict(case_id='A1', group='A', pattern_code='UUU'),
            dict(case_id='A2', group='A', pattern_code='UDU'),
            dict(case_id='B', group='B', pattern_code='UDU'),
            dict(case_id='C', group='C', pattern_code='UUU'),
            dict(case_id='D', group='D', pattern_code='UDU'),
            dict(case_id='E', group='E', pattern_code='UUU'),
            dict(case_id='F', group='F', pattern_code='UDU')]
    result = rerank_pattern_window(rows, 'UDU', window=5)
    assert [row['case_id'] for row in result] == ['B', 'D', 'A1', 'C', 'E', 'F']
    assert result[0]['pattern_match'] is True
    assert result[-1]['pattern_match'] is True  # F was outside the five-group window


def test_hybrid_filters_time_and_side_and_ignores_trade_outcome():
    query = profile()
    rows = [case('A'), case('A2', group='A'), case('B'),
            case('future', available_at=19000), case('sell', side='SELL')]
    profiles = {'A': profile('UUU', clock=15000),
                'A2': profile('UDU', clock=15000),
                'B': profile('UDU', clock=15000, bump=1),
                'future': profile('UDU', clock=15000),
                'sell': profile('UDU', clock=15000)}
    first = rank_hybrid_candidates(rows, profiles, query, 'BUY', 18000)
    changed = [dict(row, lot='99', profit='-999', action='ADD') for row in reversed(rows)]
    second = rank_hybrid_candidates(changed, profiles, query, 'BUY', 18000)
    assert [row['case_id'] for row in first['full']] == [row['case_id'] for row in second['full']]
    assert len(first['full']) == 2
    assert first['query_pattern_code'] == 'UDU'
    assert first['full'][0]['pattern_match'] is True
    assert first['similarity_sufficiency'] == 'UNCALIBRATED'
    assert first['counts']['full_pool'] == 3


def test_case_store_uses_hybrid_for_local_history_and_keeps_no_match_explicit():
    store = object.__new__(CaseStore)
    store.source = 'trader_history'
    store.items = [case('A')]
    store.group_sequences = {}
    store.candidate_profile_status = 'READY'
    store.candidate_profiles = {'A': profile(clock=15000)}
    result = store.retrieve('BUY', 'FIRST', Decimal('0.1'), 18000,
                            query_candidate=profile())
    assert result['comparison']['method'] == 'path_indicator_pattern_v1'
    assert result['comparison']['query_pattern_code'] == 'UDU'
    assert result['cases'][0]['pattern_match'] is True
    assert result['cases'][0]['path_rank'] is not None
    assert result['similarity_sufficiency'] == 'UNCALIBRATED'
    missing = store.retrieve('SELL', 'FIRST', Decimal('0.1'), 18000,
                             query_candidate=profile())
    assert missing['similarity_sufficiency'] == 'NO_MATCH'


def test_five_minute_query_does_not_describe_unused_higher_frames_or_future_bars():
    query = profile(tier='5m_only')
    valid = profile(clock=15000)
    future = profile(clock=15000)
    future['pre_entry_bars']['5m'][-1]['time'] = 15000
    result = rank_hybrid_candidates([case('valid'), case('future')],
                                    {'valid': valid, 'future': future}, query, 'BUY', 18000)
    assert [row['case_id'] for row in result['five_minute_only']] == ['valid']
    assert '15分鐘與1小時：資料不足' in result['five_minute_only'][0]['market_state_text']
