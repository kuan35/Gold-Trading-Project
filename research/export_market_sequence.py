"""Export private pre-entry sequence tags for the hybrid retrieval experiment."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from backend.market_sequence import describe_market_sequence  # noqa: E402


def export_sequences(source: Path, destination: Path) -> dict:
    if not destination.resolve().is_relative_to((PRODUCT / 'private').resolve()):
        raise ValueError('sequence export must stay under product/private')
    profiles = json.loads(source.read_text(encoding='utf-8'))['profiles']
    destination.parent.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    with destination.open('w', encoding='utf-8', newline='\n') as output:
        for case_id in sorted(profiles):
            description = describe_market_sequence(profiles[case_id])
            counts[description['pattern_code']] += 1
            output.write(json.dumps({'case_id': case_id, **description},
                                    ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')) + '\n')
    return {'records': sum(counts.values()), 'unique_patterns': len(counts),
            'schema_version': 'pre_entry_sequence_v1', 'output': str(destination)}


if __name__ == '__main__':
    print(json.dumps(export_sequences(
        PRODUCT / 'private/case_candidate_market_profiles.json',
        PRODUCT / 'private/market_state_text_20261019/sequences_PRIVATE.jsonl'),
        ensure_ascii=False))
