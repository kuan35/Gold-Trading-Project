"""Build static, read-only history assets after explicit public-data approval.

The raw case archive is copied byte-for-byte. The separate rank index keeps
only pre-entry features; no outcome enters the similarity algorithm. This
script never reads credentials or original statement files.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from backend.candidate_profile import profile_before_entry
from backend.candidate_sidecar import load_candidate_sidecar
from backend.market_sequence import describe_market_sequence
from backend.market_state_description import describe_market_state


PRODUCT = Path(__file__).resolve().parents[1]


def compact_profile(profile: dict) -> dict:
    five = profile['pre_entry_bars']['5m']
    first = float(five[0]['close'])
    if len(five) != 60 or first <= 0:
        raise ValueError('profile needs 60 valid five-minute closes')
    path = [(float(bar['close']) / first - 1) * 100 for bar in five]
    return {
        'as_of': profile['as_of'],
        'tier': profile['tier'],
        'path': path,
        'indicators': {key: float(value) for key, value in profile['indicators'].items()},
        'pattern': describe_market_sequence(profile)['pattern_code'],
        'text': describe_market_state(profile)['text'],
    }


def export_history(output: Path) -> dict:
    private = PRODUCT / 'private'
    case_path = private / 'cases.json'
    profiles, status = load_candidate_sidecar(
        case_path, private / 'case_candidate_market_profiles.json', private)
    if status != 'READY':
        raise RuntimeError('private profile status: ' + status)
    raw = json.loads(case_path.read_text(encoding='utf-8'))
    cases = raw['cases']
    if len({row['id'] for row in cases}) != len(cases):
        raise ValueError('duplicate case id')
    index = []
    for case in cases:
        profile = profiles.get(case['id'])
        if profile is None:
            continue
        index.append({
            'id': case['id'], 'group': case['group'], 'side': case['side'],
            'available_at': case['available_at'], **compact_profile(profile),
        })
    demo = json.loads((PRODUCT / 'frontend/src/demo-data.json').read_text(encoding='utf-8'))
    bars = demo['bars']
    queries = []
    for cursor in range(360, len(bars) + 1):
        clock = bars[cursor - 1]['time'] + 300
        profile = profile_before_entry(bars[:cursor], clock, {'tier': 'full'})
        if profile['status'] != 'candidate_only':
            raise ValueError(f'synthetic query at cursor {cursor} lacks closed bars')
        queries.append({'cursor': cursor, **compact_profile(profile)})
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(case_path, output / 'trader-cases.json')
    (output / 'trader-market-index.json').write_text(
        json.dumps({'schema': 'market_rank_index_v1', 'clock_status': 'UNKNOWN',
                    'alignment_scope': 'PROJECT_REFERENCE', 'cases': index},
                   ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    (output / 'synthetic-query-profiles.json').write_text(
        json.dumps({'schema': 'synthetic_query_profiles_v1', 'queries': queries},
                   ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    return {'real_cases': len(cases), 'rankable_cases': len(index),
            'synthetic_query_times': len(queries),
            'bytes': {path.name: path.stat().st_size for path in sorted(output.glob('*.json'))}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export_history(args.output), sort_keys=True))
