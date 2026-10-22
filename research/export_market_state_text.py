"""Export every available pre-entry profile to a private, repeatable JSONL file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from backend.market_state_description import describe_market_state  # noqa: E402


def export_profiles(source: Path, destination: Path) -> dict:
    if not destination.is_relative_to(PRODUCT / 'private'):
        raise ValueError('text export must stay under product/private')
    raw = json.loads(source.read_text(encoding='utf-8'))
    profiles = raw['profiles']
    destination.parent.mkdir(parents=True, exist_ok=True)
    counts = {'full': 0, '5m_only': 0}
    with destination.open('w', encoding='utf-8', newline='\n') as output:
        for case_id in sorted(profiles):
            description = describe_market_state(profiles[case_id])
            counts[description['tier']] += 1
            output.write(json.dumps({'case_id': case_id, **description}, ensure_ascii=False,
                                    sort_keys=True, separators=(',', ':')) + '\n')
    return {'records': sum(counts.values()), 'tiers': counts,
            'schema_version': 'pre_entry_market_v1', 'output': str(destination)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path,
                        default=PRODUCT / 'private/case_candidate_market_profiles.json')
    parser.add_argument('--output', type=Path,
                        default=PRODUCT / 'private/market_state_text_20261019/cases_PRIVATE.jsonl')
    arguments = parser.parse_args()
    print(json.dumps(export_profiles(arguments.source.resolve(), arguments.output.resolve()),
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
