import copy
import importlib.util
import json
import sys
from decimal import Decimal as D
from pathlib import Path

import pytest

from backend.cases import CaseStore

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'audit_case_retrieval_baseline.py'
spec = importlib.util.spec_from_file_location('retrieval_baseline', SCRIPT)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def case(ident, group, lot='0.1', available=99, action='FIRST', side='BUY', profit='1'):
    return dict(id=ident, group=group, lot=lot, available_at=available, action=action,
                side=side, profit=profit, prior_count=1, signed_distance='-0.2',
                opened_at='2024-01-01 00:00:00')


def store(items):
    value = CaseStore.__new__(CaseStore)
    value.items = items
    value.source = 'trader_history'
    return value


def query(action='FIRST'):
    return module.Query('Q', 'BUY', action, D('0.1'), 1 if action == 'ADD' else 0,
                        D('-0.2') if action == 'ADD' else None)


def test_grid_has_twelve_queries_and_normalized_lots():
    queries = module.make_queries()
    assert len(queries) == 12
    assert len({(q.side, q.action, q.lot) for q in queries}) == 12
    assert {q.lot for q in queries} == {D('0.05'), D('0.10'), D('0.50')}
    assert all(q.prior_count == 1 and q.signed_distance == D('-0.2')
               for q in queries if q.action == 'ADD')


def test_denominator_obeys_time_side_action_and_unique_groups():
    items = [case('a', 'g1'), case('b', 'g1'), case('c', 'g2', lot='10'),
             case('future', 'g3', available=101), case('sell', 'g4', side='SELL'),
             case('add', 'g5', action='ADD')]
    row = module.evaluate_query(store(items), query(), 100, {})
    assert row['eligible_rows'] == 3
    assert row['eligible_groups'] == 2
    assert row['matched_groups'] == 1
    assert row['matched_pct'] == '50.00'
    assert row['best_distance_tied_groups'] == 1


def test_no_eligible_cases_has_unknown_ratio_and_zero_matches():
    row = module.evaluate_query(store([]), query(), 100, {})
    assert row['matched_groups'] == 0
    assert row['matched_pct'] is None
    assert row['pool_jaccard_pct_lot_plus10'] is None
    assert row['largest_source_share_pct'] is None


def test_profit_changes_display_but_not_retrieval_and_input_is_untouched():
    items = [case(str(i), f'g{i}', lot=str(D('0.1') + D(i) / 100),
                  profit='-1' if i == 6 else '1') for i in range(7)]
    original = copy.deepcopy(items)
    a = module.evaluate_query(store(items), query(), 100, {})
    assert items == original
    changed = copy.deepcopy(items)
    for item in changed:
        item['profit'] = str(-D(item['profit']))
    b = module.evaluate_query(store(changed), query(), 100, {})
    assert a['ui_top6_overlap_count'] == 5
    for key in a:
        if key != 'ui_top6_overlap_count':
            assert a[key] == b[key]


def test_concentration_is_on_matched_group_representatives_and_no_identifiers():
    items = [case('a', 'g1'), case('b', 'g1'), case('c', 'g2'), case('d', 'g3')]
    metadata = {'a': {'source': 'private_account_123', 'year': '2024'},
                'b': {'source': 'other', 'year': '2021'},
                'c': {'source': 'private_account_123', 'year': '2024'}}
    row = module.evaluate_query(store(items), query(), 100, metadata)
    assert row['largest_year_share_pct'] == '100.00'
    assert row['largest_source_share_pct'] == '100.00'
    assert row['source_coverage_pct'] == '66.67'
    assert 'private_account_123' not in json.dumps(row)


def test_signed_distance_difference_and_lot_perturbation_are_measured():
    items = [case('a', 'g1', action='ADD'), case('b', 'g2', action='ADD')]
    items[1]['signed_distance'] = '-0.3'
    row = module.evaluate_query(store(items), query('ADD'), 100, {})
    assert row['top6_signed_delta_max_pct'] == '0.1'
    assert row['pool_jaccard_pct_lot_plus10'] == '100.00'
    assert row['top6_jaccard_pct_lot_plus10'] == '100.00'


def test_query_clock_requires_explicit_timezone():
    with pytest.raises(ValueError, match='時區'):
        module.parse_clock('2025-10-02T07:00:00')
    assert module.parse_clock('2025-10-02T07:00:00Z') == 1759388400


def test_zero_matches_with_nonempty_denominator_is_zero_not_unknown():
    row = module.evaluate_query(store([case('far', 'g1', lot='100')]), query(), 100, {})
    assert row['eligible_groups'] == 1
    assert row['matched_pct'] == '0.00'
    assert row['top6_count'] == 0
    assert row['best_distance_tied_groups'] == 0


def test_missing_private_input_never_falls_back_to_synthetic(tmp_path):
    with pytest.raises(FileNotFoundError):
        module.run(tmp_path / 'missing.json', tmp_path / 'audit.csv', tmp_path / 'out',
                   '2025-10-02T07:00:00Z')
    assert not (tmp_path / 'out').exists()


def test_outputs_are_deterministic_private_fields_absent_and_no_overwrite(tmp_path):
    cases = tmp_path / 'input.json'
    cases.write_text(json.dumps({'cases': [case('SECRET_ID', 'SECRET_GROUP')]}), encoding='utf-8')
    audit = tmp_path / 'audit.csv'
    audit.write_text('record_id,source,open_time\nsecret,SECRET_SOURCE,2024-01-01\n', encoding='utf-8')
    first, second = tmp_path / 'first', tmp_path / 'second'
    module.run(cases, audit, first, '2025-10-02T07:00:00Z')
    module.run(cases, audit, second, '2025-10-02T07:00:00Z')
    for name in ('queries.csv', 'summary.csv', 'report.md'):
        text = (first / name).read_text(encoding='utf-8-sig')
        assert 'SECRET' not in text
        assert (first / name).read_bytes() == (second / name).read_bytes()
    with pytest.raises(FileExistsError):
        module.run(cases, audit, first, '2025-10-02T07:00:00Z')
