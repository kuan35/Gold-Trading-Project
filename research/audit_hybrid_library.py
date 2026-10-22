"""Aggregate-only audit of the local point-in-time case library.

Never emit case IDs, file names, account details, timestamps, prices or rows.
This audit checks coverage and chronology; it does not score relevance.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

from backend.candidate_sidecar import load_candidate_sidecar
from backend.market_sequence import describe_market_sequence
from backend.market_state_description import describe_market_state


def audit_library(cases: list[dict], profiles: dict[str, dict]) -> dict:
    lookup = {case['id']: case for case in cases}
    years: Counter[int] = Counter()
    tiers: Counter[str] = Counter()
    sides: Counter[str] = Counter()
    matched_groups = set()
    future_or_unclosed = 0
    mature_after_entry = 0
    not_mature_after_entry = 0
    pattern_ready = 0
    text_ready = 0
    for case_id, profile in profiles.items():
        case = lookup.get(case_id)
        if case is None:
            continue
        clock = profile['as_of']
        years[datetime.fromtimestamp(clock, timezone.utc).year] += 1
        tiers[profile['tier']] += 1
        sides[case['side']] += 1
        matched_groups.add(case['group'])
        if type(case.get('available_at')) is int and case['available_at'] > clock:
            mature_after_entry += 1
        else:
            not_mature_after_entry += 1
        bars = (profile.get('pre_entry_bars') or {}).get('5m') or []
        if len(bars) != 60 or any(
                type(bar.get('time')) is not int or bar['time'] + 300 > clock
                for bar in bars):
            future_or_unclosed += 1
        try:
            describe_market_sequence(profile)
            pattern_ready += 1
        except (KeyError, TypeError, ValueError):
            pass
        try:
            describe_market_state(profile)
            text_ready += 1
        except (KeyError, TypeError, ValueError):
            pass
    return {
        'cases_total': len(cases),
        'profiles_ready': len(profiles),
        'cases_without_ready_profile': len(cases) - len(profiles),
        'ready_groups': len(matched_groups),
        'ready_by_year': dict(sorted(years.items())),
        'ready_by_tier': dict(sorted(tiers.items())),
        'ready_by_side': dict(sorted(sides.items())),
        'mature_after_entry': mature_after_entry,
        'not_mature_after_entry': not_mature_after_entry,
        'future_or_unclosed_five_minute_profiles': future_or_unclosed,
        'pattern_ready': pattern_ready,
        'fixed_text_ready': text_ready,
        'human_relevance_judgments_for_new_period': 0,
        'similarity_accuracy': None,
        'clock_status': 'UNKNOWN',
        'alignment_scope': 'PROJECT_REFERENCE',
    }


def main() -> dict:
    private = Path(__file__).resolve().parents[1] / 'private'
    case_path = private / 'cases.json'
    profiles, status = load_candidate_sidecar(
        case_path, private / 'case_candidate_market_profiles.json', private)
    if status != 'READY':
        raise RuntimeError('candidate sidecar status: ' + status)
    cases = json.loads(case_path.read_text(encoding='utf-8'))['cases']
    return audit_library(cases, profiles)


if __name__ == '__main__':
    print(json.dumps(main(), ensure_ascii=False, sort_keys=True, indent=2))
