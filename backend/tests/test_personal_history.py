import copy
from datetime import datetime, timezone
import json
from hashlib import sha256

import pytest

from scripts.personal_history import (export_references, plan_reference_download,
                                      validate_references)
from scripts.build_personal_history import build as build_personal, load_native_chunks
from scripts.history_bootstrap import verify
from scripts.fetch_ctrader_history_volume import task_key


def marker(ident='T-one'):
    return dict(case_id=ident, candidate_open_utc='2025-01-08T10:00:00+00:00',
                candidate_close_utc='2025-01-08T11:00:00+00:00',
                entry_bar_utc='2025-01-08T10:00:00+00:00',
                exit_bar_utc='2025-01-08T11:00:00+00:00',
                candidate_clock_basis='ledger_price_hypothesis',
                marker_status='BOTH_MARKERS_AVAILABLE', timezone_status='UNKNOWN',
                production_enabled=False, frozen_boundary_policy_difference=False)


def test_public_reference_export_allows_only_index_ids_and_fields():
    payload = export_references([marker(), marker('private-unmatched')],
                                {'cases': [{'id': 'T-one'}]})
    assert [row['case_id'] for row in payload['cases']] == ['T-one']
    for change in ({'source_private': 'statement.html'},
                   {'timezone_status': 'CONFIRMED'},
                   {'candidate_open_utc': '2025-01-08T10:00:00'},
                   {'candidate_close_utc': '2025-01-07T11:00:00+00:00'}):
        invalid = copy.deepcopy(payload)
        invalid['cases'][0].update(change)
        with pytest.raises(ValueError):
            validate_references(invalid, {'T-one'})
    with pytest.raises(ValueError):
        validate_references(payload, {'T-one', 'T-two'})


def test_download_plan_is_deterministic_and_includes_entry_exit_and_hourly():
    row = marker()
    now = int(datetime(2025, 1, 10, tzinfo=timezone.utc).timestamp())
    first = plan_reference_download([row], now=now)
    assert first == plan_reference_download([row, row], now=now)
    assert {task['interval'] for task in first} == {'5m', '1h'}
    entry = int(datetime(2025, 1, 8, 10, tzinfo=timezone.utc).timestamp())
    assert all(any(task['start'] <= entry < task['end']
                   for task in first if task['interval'] == interval)
               for interval in ('5m', '1h'))


def test_same_source_native_history_builds_profiles_volume_and_outcomes(tmp_path, monkeypatch):
    case_id = 'T-one'
    open_at = int(datetime(2025, 1, 8, 10, tzinfo=timezone.utc).timestamp())
    first = open_at - 60 * 3600
    last = open_at + 3 * 3600
    public = tmp_path / 'public'
    public.mkdir()
    (public / 'trader-cases.json').write_text(json.dumps({'cases': [
        {'id': case_id, 'side': 'BUY', 'group': 'G-one', 'available_at': last,
         'entry': '2600', 'exit': '2602', 'lot': '0.1', 'profit': '20'}],
        'group_sequences': {}}), encoding='utf-8')
    (public / 'trader-market-index.json').write_text(json.dumps({'cases': [{'id': case_id}]}), encoding='utf-8')
    reference = marker()
    reference['candidate_open_utc'] = datetime.fromtimestamp(open_at, timezone.utc).isoformat()
    reference['candidate_close_utc'] = datetime.fromtimestamp(open_at + 3600, timezone.utc).isoformat()
    reference['entry_bar_utc'] = reference['candidate_open_utc']
    reference['exit_bar_utc'] = reference['candidate_close_utc']
    (public / 'trader-case-reference-times.json').write_text(json.dumps(export_references(
        [reference], {'cases': [{'id': case_id}]})), encoding='utf-8')
    tasks = plan_reference_download([reference], now=last + 3600)
    root = tmp_path / 'personal_history' / sha256(b'demo:1').hexdigest()
    chunks = root / 'native_history'
    chunks.mkdir(parents=True)
    key = 'a' * 64
    for task in tasks:
        span = 300 if task['interval'] == '5m' else 3600
        bars = []
        for stamp in range(max(first, task['start']), min(last, task['end']), span):
            price = 2600 + (stamp - first) / 86400
            bars.append(dict(time=stamp, open=str(price), high=str(price + 0.8),
                             low=str(price - 0.7), close=str(price + 0.1), volume=100))
        (chunks / (task_key(task) + '.json')).write_text(json.dumps(dict(
            **task, source_key=key, source='ctrader_demo_native',
            volume_basis='broker_native_tick_count',
            status='AVAILABLE' if bars else 'EMPTY', bars=bars)), encoding='utf-8')
    summary = build_personal(root, public_root=public, environment='demo',
                             now=last + 3600, personal_base=tmp_path / 'personal_history')
    assert summary['status'] == 'READY'
    assert summary['usable_profiles'] == 1
    assert summary['outcome_cases'] == 1
    assert summary['execution_cases'] == 1
    assert json.loads((root / 'case_forward_outcomes.json').read_text(encoding='utf-8'))['source'] == 'Pepperstone cTrader DEMO BID'
    assert json.loads((root / 'case_execution_bars_v2.json').read_text(encoding='utf-8'))['price_source'] == 'Pepperstone cTrader DEMO BID'
    verified = verify(root, personal_base=tmp_path / 'personal_history')
    assert verified['usable_profiles'] == 1
    assert verified['native_volume_ready'] == 1
    import backend.cases as case_module
    monkeypatch.setattr(case_module, 'case_data_root', lambda *_: root)
    monkeypatch.setenv('GOLD_NATIVE_VOLUME_FOLDER', 'native_history')
    store = case_module.CaseStore()
    query = dict(store.candidate_profiles.get(case_id) or json.loads(
        (root / 'case_candidate_market_profiles.json').read_text(encoding='utf-8'))['profiles'][case_id])
    query['market_source_key'] = 'b' * 64
    result = store.retrieve('BUY', 'FIRST', case_module.D('0.1'), open_at,
                            query_candidate=query, retrieval_method='context_contract_v1')
    assert result['sufficiency']['reasons'] == ['SOURCE_MISMATCH']
    assert result['case_data_source'] == 'Pepperstone cTrader DEMO'
    assert '自建' in result['limitations'][0] and 'Pepperstone cTrader DEMO' in result['limitations'][0]
    # A second account's chunk cannot be blended into the first account's data.
    selected = chunks / (task_key(tasks[0]) + '.json')
    changed = json.loads(selected.read_text(encoding='utf-8'))
    changed['source_key'] = 'b' * 64
    selected.write_text(json.dumps(changed), encoding='utf-8')
    with pytest.raises(ValueError, match='MIXED_SOURCE_IDENTITY'):
        load_native_chunks(chunks, tasks, 'demo')
    with pytest.raises(ValueError, match='PERSONAL_VOLUME_CHUNK_CHANGED'):
        verify(root, personal_base=tmp_path / 'personal_history')
