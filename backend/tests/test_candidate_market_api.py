"""Local candidate mode must fail closed and ignore order sizing in retrieval."""
from decimal import Decimal

from backend.cases import CaseStore
from backend.candidate_retrieval import FIVE, HIGH


def _profile(tier='full', value='0', clock=90):
    bars = [dict(time=clock-18000+index*300, open='100', high='101', low='99',
                 close=str(100+index/10+float(value))) for index in range(60)]
    return dict(status='candidate_only', timezone_status='UNKNOWN', production_enabled=False,
                tier=tier, as_of=clock, shape=[value] * 240,
                latest_closed={'5m': clock},
                indicators={key: '0.5' if key == '5m_atr_pct' else value
                            for key in (FIVE + HIGH if tier == 'full' else FIVE)},
                pre_entry_bars={'5m': bars,
                                **({'15m': [], '1h': []} if tier == 'full' else {})})


def _store(status='READY'):
    store = object.__new__(CaseStore)
    store.source = 'trader_history'
    store.items = [dict(id='full', group='G1', side='BUY', action='FIRST', lot='0.1',
                        available_at=80, profit='-2', label='候選一', source_kind='trader_history',
                        time_alignment='unknown'),
                   dict(id='limited', group='G2', side='BUY', action='ADD', lot='9',
                        available_at=80, profit='3', label='候選二', source_kind='trader_history',
                        time_alignment='unknown')]
    store.group_sequences = {}
    store.candidate_profile_status = status
    store.candidate_profiles = {'full': _profile(), 'limited': _profile('5m_only', '1')} if status == 'READY' else {}
    return store


def test_candidate_retrieval_ignores_action_and_lot_and_has_separate_tiers():
    store = _store()
    query = _profile(clock=100)
    a = store.retrieve('BUY', 'FIRST', Decimal('.1'), 100, query_candidate=query)
    b = store.retrieve('BUY', 'ADD', Decimal('5'), 100, typical_lot=Decimal('8'), query_candidate=query)
    assert [row['id'] for row in a['full_cases']] == [row['id'] for row in b['full_cases']]
    assert [row['id'] for row in a['five_minute_only_cases']] == ['limited']
    assert a['total'] == 1 and a['five_minute_only_total'] == 1
    assert a['comparison']['mode'] == 'candidate_market'
    assert a['comparison']['clock_status'] == 'UNKNOWN'
    assert a['comparison']['alignment_scope'] == 'PROJECT_REFERENCE'
    assert a['comparison']['independent_clock_verified'] is False
    assert a['similarity_sufficiency'] == 'UNCALIBRATED'
    assert a['cases'][0]['distance'] is None
    assert a['comparison']['method'] == 'path_indicator_pattern_v1'
    assert a['cases'][0]['reference_alignment'] == 'PROJECT_REFERENCE'


def test_stale_sidecar_has_no_weighted_fallback():
    store = _store('STALE')
    result = store.retrieve('BUY', 'FIRST', Decimal('.1'), 100, query_candidate=_profile())
    assert result['total'] == 0 and result['five_minute_only_total'] == 0
    assert result['candidate_market_unavailable_reason']
    assert result['comparison']['mode'] == 'candidate_market'


def test_candidate_chart_never_includes_entry_or_exit_bar():
    store = _store()
    store.candidate_profiles['full'] = _profile(clock=400)
    detail = store.get_candidate_detail('full', 600)
    assert detail['bars'] and all(bar['time'] + 300 <= 400 for bar in detail['bars'])
    assert detail['markers'] == []
    assert detail['reference_alignment'] == 'PROJECT_REFERENCE'
    assert store.get_candidate_detail('full', 70) is None
