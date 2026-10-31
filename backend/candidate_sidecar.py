"""Load private candidate-market profiles with fail-closed integrity checks."""

from __future__ import annotations

import math
import hashlib
import json
from datetime import datetime
from pathlib import Path


COMMON = {'5m_ma_gap', '5m_atr_pct', '5m_rsi14', '5m_macd_hist',
          '5m_slope', 'range_position'}
FULL = COMMON | {'15m_ma_gap', '15m_atr_pct', '15m_rsi14',
                 '15m_macd_hist', '1h_ma_gap', '1h_atr_pct'}
SECONDS = {'5m': 300, '15m': 900, '1h': 3600}
REFERENCE_CLOCK_BASES = {'ledger_price_hypothesis', 'source_model_scenario'}


def _utc_second(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return int(parsed.timestamp()) if parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0 else None
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None


def _reference_ready(marker, profile):
    if (marker.get('marker_status') != 'BOTH_MARKERS_AVAILABLE'
            or marker.get('timezone_status') != 'UNKNOWN'
            or marker.get('production_enabled') is not False
            or marker.get('frozen_boundary_policy_difference') is not False
            or marker.get('candidate_clock_basis') not in REFERENCE_CLOCK_BASES):
        return False
    opened = _utc_second(marker.get('candidate_open_utc'))
    closed = _utc_second(marker.get('candidate_close_utc'))
    entry = _utc_second(marker.get('entry_bar_utc'))
    exit_ = _utc_second(marker.get('exit_bar_utc'))
    return (opened is not None and closed is not None and closed >= opened
            and profile['as_of'] == opened
            and entry == opened // 300 * 300 and exit_ == closed // 300 * 300)


def _finite(value):
    try:
        return math.isfinite(float(value))
    except (OverflowError, TypeError, ValueError):
        return False


def _valid_profile(profile):
    if (not isinstance(profile, dict) or profile.get('status') != 'candidate_only'
            or profile.get('timezone_status') != 'UNKNOWN'
            or profile.get('production_enabled') is not False
            or profile.get('tier') not in ('full', '5m_only')
            or type(profile.get('as_of')) is not int):
        return False
    tier = profile['tier']
    keys = {'5m', '15m', '1h'} if tier == 'full' else {'5m'}
    latest = profile.get('latest_closed')
    if not isinstance(latest, dict) or set(latest) != keys:
        return False
    if any(type(value) is not int or value > profile['as_of'] or
           profile['as_of'] - value >= SECONDS[label]
           for label, value in latest.items()):
        return False
    shape = profile.get('shape')
    if not isinstance(shape, list) or len(shape) != 240 or not all(_finite(value) for value in shape):
        return False
    indicators = profile.get('indicators')
    if (not isinstance(indicators, dict) or set(indicators) !=
            (FULL if tier == 'full' else COMMON)
            or not all(_finite(value) for value in indicators.values())):
        return False
    bars = profile.get('pre_entry_bars')
    if not isinstance(bars, dict) or set(bars) != keys:
        return False
    for label, candles in bars.items():
        if not isinstance(candles, list) or any(
                type(bar.get('time')) is not int or
                bar['time'] + SECONDS[label] > profile['as_of'] or
                not all(_finite(bar.get(key)) for key in ('open', 'high', 'low', 'close'))
                for bar in candles if isinstance(bar, dict)):
            return False
        if any(not isinstance(bar, dict) for bar in candles):
            return False
    return True


def load_candidate_sidecar(case_path, sidecar_path, private_root):
    root = Path(private_root).resolve()
    sidecar_path = Path(sidecar_path)
    if not sidecar_path.exists():
        return {}, 'MISSING'
    try:
        cases = json.loads(Path(case_path).read_text(encoding='utf-8'))['cases']
        ids = {case['id'] for case in cases}
        if len(ids) != len(cases):
            return {}, 'INVALID'
        payload = json.loads(sidecar_path.read_text(encoding='utf-8'))
        if (payload.get('method') != 'candidate_market_v1' or
                payload.get('timezone_status') != 'UNKNOWN' or
                payload.get('production_enabled') is not False):
            return {}, 'INVALID'
        if payload.get('input_cases_sha256') != hashlib.sha256(Path(case_path).read_bytes()).hexdigest():
            return {}, 'STALE'
        inputs = payload.get('inputs')
        if not isinstance(inputs, dict) or not isinstance(inputs.get('alignment'), dict):
            return {}, 'INVALID'
        for ref in inputs.values():
            if not isinstance(ref, dict) or not isinstance(ref.get('path'), str):
                return {}, 'INVALID'
            path = (root / ref['path']).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                return {}, 'INVALID'
            if hashlib.sha256(path.read_bytes()).hexdigest() != ref.get('sha256'):
                return {}, 'STALE'
        profiles = payload.get('profiles')
        if (not isinstance(profiles, dict) or not set(profiles) <= ids
                or any(not _valid_profile(value) for value in profiles.values())):
            return {}, 'INVALID'
        alignment_path = (root / inputs['alignment']['path']).resolve()
        markers = json.loads(alignment_path.read_text(encoding='utf-8'))
        if not isinstance(markers, list):
            return {}, 'INVALID'
        by_id = {}
        for marker in markers:
            if not isinstance(marker, dict):
                return {}, 'INVALID'
            case_id = marker.get('case_id')
            if case_id is not None:
                if case_id in by_id:
                    return {}, 'INVALID'
                by_id[case_id] = marker
        ready = {case_id: dict(profile, reference_alignment='PROJECT_REFERENCE',
                               reference_clock_basis=by_id[case_id]['candidate_clock_basis'],
                               reference_open_utc=_utc_second(by_id[case_id]['candidate_open_utc']),
                               reference_close_utc=_utc_second(by_id[case_id]['candidate_close_utc']))
                 for case_id, profile in profiles.items()
                 if case_id in by_id and _reference_ready(by_id[case_id], profile)}
        return ready, 'READY'
    except (OSError, KeyError, ValueError, TypeError, AttributeError):
        return {}, 'INVALID'
