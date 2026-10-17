"""Load private candidate-market profiles with fail-closed integrity checks."""

from __future__ import annotations

import math
import hashlib
import json
from pathlib import Path


COMMON = {'5m_ma_gap', '5m_atr_pct', '5m_rsi14', '5m_macd_hist',
          '5m_slope', 'range_position'}
FULL = COMMON | {'15m_ma_gap', '15m_atr_pct', '15m_rsi14',
                 '15m_macd_hist', '1h_ma_gap', '1h_atr_pct'}
SECONDS = {'5m': 300, '15m': 900, '1h': 3600}


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
        if not isinstance(inputs, dict) or not inputs:
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
        return profiles, 'READY'
    except (OSError, KeyError, ValueError, TypeError, AttributeError):
        return {}, 'INVALID'
