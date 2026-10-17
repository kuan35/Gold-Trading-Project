from copy import deepcopy
from decimal import Decimal as D

import pytest
from backend.cases import CaseStore


def case(i, lot='0.1', action='FIRST', **extra):
    return dict(id=str(i), group=f'G{i}', lot=lot, action=action, side='BUY',
                available_at=99, opened_at='2024-01-01T00:00:00', profit='1',
                time_alignment='unknown', prior_count=1, prior_lot='0.1',
                signed_distance='-0.2', **extra)


def store(items):
    s = CaseStore.__new__(CaseStore)
    s.items, s.source = items, 'legacy_fixture'
    return s


def test_relative_size_can_match_different_account_scales_and_exclude_wrong_habit():
    a, b = case('a', '1'), case('b', '0.1')
    a['size_profile'] = dict(typical_lot='1', status='READY', count=20, days=5)
    b['size_profile'] = dict(typical_lot='0.01', status='READY', count=20, days=5)
    rows = store([a, b]).rank('BUY', 'FIRST', D('.1'), 100, typical_lot=D('.1'))
    assert [c['id'] for c in rows] == ['a']
    assert rows[0]['comparison_basis'] == 'relative_lot'
    assert rows[0]['components'][0]['query'] == '1'
    assert rows[0]['components'][0]['case'] == '1'


def test_no_baseline_is_explicit_absolute_fallback_and_large_size_is_excluded():
    r = store([case('a'), case('b', '.5')]).retrieve('BUY','FIRST',D('.1'),100)
    assert r['total'] == 1
    assert r['comparison']['basis'] == 'absolute_lot'
    assert r['sufficiency']['status'] == 'insufficient'
    assert r['cases'][0]['differences']


def test_add_missing_prices_are_not_zero_distance_and_opposite_sign_is_rejected():
    a, b, c = [case(x, action='ADD') for x in 'abc']
    b['signed_distance'] = None
    c['signed_distance'] = '0.2'
    rows = store([a,b,c]).rank('BUY','ADD',D('.1'),100,prior_count=1,prior_lot=D('.1'),signed_distance=D('-.2'))
    assert [r['id'] for r in rows] == ['a','b']
    assert rows[1]['distance'] > rows[0]['distance']
    assert rows[1]['missing_features'] == ['signed_distance']


def test_add_exposure_ratio_distinguishes_equal_lot_with_different_positions():
    a, b = case('a', action='ADD'), case('b', action='ADD')
    b['prior_lot'] = '10'
    rows = store([a,b]).rank('BUY','ADD',D('.1'),100,prior_count=1,prior_lot=D('.1'),signed_distance=D('-.2'))
    assert [r['id'] for r in rows] == ['a']


def test_balanced_display_and_outcomes_cannot_change_matching():
    items = [case(i) for i in range(12)]
    for i,c in enumerate(items):
        c['profit'] = '-2' if i < 9 else '3'
    s = store(items)
    before = [(c['id'],c['distance']) for c in s.rank('BUY','FIRST',D('.1'),100)]
    r = s.retrieve('BUY','FIRST',D('.1'),100)
    assert len([c for c in r['cases'] if D(c['profit']) > 0]) == 3
    assert len([c for c in r['cases'] if D(c['profit']) < 0]) == 3
    for c in s.items: c['profit'] = str(-D(c['profit']))
    assert [(c['id'],c['distance']) for c in s.rank('BUY','FIRST',D('.1'),100)] == before
    assert len(r['profit_cases']) == 3 and len(r['loss_cases']) == 6


def test_time_group_gates_and_unknown_clock_cap_evidence():
    items = [case(i) for i in range(40)]
    items[0]['available_at'] = 101
    items[1]['group'] = items[2]['group']
    items[3]['side'] = 'SELL'
    r = store(items).retrieve('BUY','FIRST',D('.1'),100)
    assert r['total'] == 37
    assert r['sufficiency']['status'] == 'limited'
    assert len({c['group'] for c in r['cases']}) == len(r['cases'])


@pytest.mark.parametrize('typical', ['NaN','0','-1','Infinity'])
def test_invalid_typical_size_cannot_silently_fall_back(typical):
    with pytest.raises(ValueError):
        store([case('a')]).retrieve('BUY','FIRST',D('.1'),100,typical_lot=D(typical))


def test_relative_mode_does_not_mix_missing_profiles_or_leak_scope_identifiers():
    a,b = case('a'),case('b')
    a['size_profile'] = dict(typical_lot='.1',status='READY',count=20,days=5,scope_private='SECRET')
    r = store([a,b]).retrieve('BUY','FIRST',D('.1'),100,typical_lot=D('.1'))
    assert r['total'] == 1
    assert r['comparison']['excluded_missing_profile'] == 1
    assert 'SECRET' not in str(r)


def test_profiles_use_prior_completed_buckets_only_not_profit_or_future():
    from backend.similarity import build_size_profiles
    rows = []
    for day in range(1,13):
        rows.append(dict(record_id=str(day),source='s',side='BUY',lot='.1',open_time=f'2024-01-{day:02} 10:00:00'))
    rows += [dict(record_id='now',source='s',side='BUY',lot='9',open_time='2024-01-13 10:00:00'),
             dict(record_id='tie',source='s',side='SELL',lot='99',open_time='2024-01-13 10:01:00'),
             dict(record_id='future',source='s',side='BUY',lot='500',open_time='2024-01-14 10:00:00')]
    profiles = build_size_profiles(rows)
    assert profiles['now']['typical_lot'] == '0.1'
    assert profiles['now']['count'] == 12
    assert profiles['tie']['typical_lot'] == '0.1'
    assert profiles['1']['typical_lot'] is None
    changed = deepcopy(rows)
    changed[-1]['lot'] = '9999'
    for r in changed: r['profit'] = '-999'
    assert build_size_profiles(changed)['now'] == profiles['now']


def test_extreme_finite_baseline_never_crashes_matching():
    a=case('a')
    a['size_profile']=dict(typical_lot='.1',status='READY',count=20,days=5)
    r=store([a]).retrieve('BUY','FIRST',D('.1'),100,typical_lot=D('1e500'))
    assert r['total']==0


def test_stale_profile_file_disables_relative_comparison_without_breaking_app(tmp_path,monkeypatch):
    import json
    import backend.cases as module
    folder=tmp_path/'private';folder.mkdir()
    (folder/'cases.json').write_text(json.dumps({'cases':[case('a')]}),encoding='utf-8')
    (folder/'case_size_profiles.json').write_text(json.dumps({'input_cases_sha256':'stale','profiles':{'a':{'typical_lot':'.1','status':'READY'}}}),encoding='utf-8')
    monkeypatch.setattr(module,'ROOT',tmp_path)
    s=CaseStore()
    assert s.retrieve('BUY','FIRST',D('.1'),100)['total']==0
    assert s.retrieve('BUY','FIRST',D('.1'),100)['candidate_market_unavailable_reason']
