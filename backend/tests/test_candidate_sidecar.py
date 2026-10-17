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
    profile = dict(status='candidate_only', timezone_status='UNKNOWN',
                   production_enabled=False, tier='full', as_of=3600,
                   latest_closed={'5m': 3600, '15m': 3600, '1h': 3600},
                   shape=['0'] * 240,
                   indicators={key: '0' for key in INDICATORS},
                   pre_entry_bars={'5m': [], '15m': [], '1h': []})
    payload = dict(method='candidate_market_v1',
                   input_cases_sha256=hashlib.sha256(case_path.read_bytes()).hexdigest(),
                   inputs={'evidence': {'path': 'evidence.json',
                                        'sha256': hashlib.sha256(evidence.read_bytes()).hexdigest()}},
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
