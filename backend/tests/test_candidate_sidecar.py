import hashlib
import json

from backend.candidate_sidecar import load_candidate_sidecar


INDICATORS = ('5m_ma_gap', '5m_atr_pct', '5m_rsi14', '5m_macd_hist',
              '5m_slope', 'range_position', '15m_ma_gap', '15m_atr_pct',
              '15m_rsi14', '15m_macd_hist', '1h_ma_gap', '1h_atr_pct')


def fixture(tmp_path):
    root = tmp_path / 'private'
    root.mkdir()
    case_path = root / 'cases.json'
    case_path.write_text(json.dumps({'cases': [{'id': 'T-001'}]}), encoding='utf-8')
    evidence = root / 'evidence.json'
    evidence.write_text('{}', encoding='utf-8')
    alignment = root / 'alignment.json'
    alignment.write_text(json.dumps([dict(case_id='T-001', marker_status='BOTH_MARKERS_AVAILABLE',
        candidate_open_utc='1970-01-01T01:00:00+00:00', candidate_close_utc='1970-01-01T01:05:00+00:00',
        entry_bar_utc='1970-01-01T01:00:00+00:00', exit_bar_utc='1970-01-01T01:05:00+00:00',
        candidate_clock_basis='ledger_price_hypothesis', timezone_status='UNKNOWN',
        production_enabled=False, frozen_boundary_policy_difference=False)]), encoding='utf-8')
    profile = dict(status='candidate_only', timezone_status='UNKNOWN',
                   production_enabled=False, tier='full', as_of=3600,
                   latest_closed={'5m': 3600, '15m': 3600, '1h': 3600},
                   shape=['0'] * 240,
                   indicators={key: '0' for key in INDICATORS},
                   pre_entry_bars={'5m': [], '15m': [], '1h': []})
    payload = dict(method='candidate_market_v1',
                   input_cases_sha256=hashlib.sha256(case_path.read_bytes()).hexdigest(),
                   inputs={'evidence': {'path': 'evidence.json',
                                        'sha256': hashlib.sha256(evidence.read_bytes()).hexdigest()},
                           'alignment': {'path': 'alignment.json',
                                         'sha256': hashlib.sha256(alignment.read_bytes()).hexdigest()}},
                   timezone_status='UNKNOWN', production_enabled=False,
                   profiles={'T-001': profile})
    sidecar = root / 'sidecar.json'
    sidecar.write_text(json.dumps(payload), encoding='utf-8')
    return root, case_path, evidence, sidecar, payload


def test_hash_bound_loader_accepts_only_candidate_profiles(tmp_path):
    root, cases, evidence, sidecar, payload = fixture(tmp_path)
    profiles, status = load_candidate_sidecar(cases, sidecar, root)
    assert status == 'READY' and set(profiles) == {'T-001'}
    cases.write_text('{"cases":[]}', encoding='utf-8')
    assert load_candidate_sidecar(cases, sidecar, root) == ({}, 'STALE')
    cases.write_text(json.dumps({'cases': [{'id': 'T-001'}]}), encoding='utf-8')
    evidence.write_text('{"changed":true}', encoding='utf-8')
    assert load_candidate_sidecar(cases, sidecar, root) == ({}, 'STALE')


def test_loader_rejects_escape_future_or_production_flags(tmp_path):
    root, cases, evidence, sidecar, payload = fixture(tmp_path)
    payload['inputs']['evidence']['path'] = '../outside.json'
    sidecar.write_text(json.dumps(payload), encoding='utf-8')
    assert load_candidate_sidecar(cases, sidecar, root)[1] == 'INVALID'
    payload['inputs']['evidence']['path'] = 'evidence.json'
    payload['profiles']['T-001']['latest_closed']['5m'] = 3900
    sidecar.write_text(json.dumps(payload), encoding='utf-8')
    assert load_candidate_sidecar(cases, sidecar, root)[1] == 'INVALID'
    payload['profiles']['T-001']['latest_closed']['5m'] = 3600
    payload['profiles']['T-001']['production_enabled'] = True
    sidecar.write_text(json.dumps(payload), encoding='utf-8')
    assert load_candidate_sidecar(cases, sidecar, root)[1] == 'INVALID'


def test_reference_alignment_requires_both_price_markers(tmp_path):
    root, cases, _, sidecar, payload = fixture(tmp_path)
    alignment = root / 'alignment.json'
    row = json.loads(alignment.read_text(encoding='utf-8'))[0]
    row['marker_status'] = 'CLOSE_CLOCK_BOUNDARY_OR_UNEXPECTED_ZONE'
    alignment.write_text(json.dumps([row]), encoding='utf-8')
    payload['inputs']['alignment']['sha256'] = hashlib.sha256(alignment.read_bytes()).hexdigest()
    sidecar.write_text(json.dumps(payload), encoding='utf-8')
    assert load_candidate_sidecar(cases, sidecar, root) == ({}, 'READY')
    row['marker_status'] = 'BOTH_MARKERS_AVAILABLE'
    row['candidate_close_utc'] = '1970-01-01T00:55:00+00:00'
    alignment.write_text(json.dumps([row]), encoding='utf-8')
    payload['inputs']['alignment']['sha256'] = hashlib.sha256(alignment.read_bytes()).hexdigest()
    sidecar.write_text(json.dumps(payload), encoding='utf-8')
    assert load_candidate_sidecar(cases, sidecar, root) == ({}, 'READY')


def test_reference_alignment_rejects_unbound_or_changed_ledger(tmp_path):
    root, cases, _, sidecar, payload = fixture(tmp_path)
    payload['inputs'].pop('alignment')
    sidecar.write_text(json.dumps(payload), encoding='utf-8')
    assert load_candidate_sidecar(cases, sidecar, root)[1] == 'INVALID'
    payload['inputs']['alignment'] = {'path': 'alignment.json',
        'sha256': hashlib.sha256((root / 'alignment.json').read_bytes()).hexdigest()}
    sidecar.write_text(json.dumps(payload), encoding='utf-8')
    (root / 'alignment.json').write_text('[]', encoding='utf-8')
    assert load_candidate_sidecar(cases, sidecar, root)[1] == 'STALE'
