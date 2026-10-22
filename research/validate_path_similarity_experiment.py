"""Independent export audit and byte-for-byte reproduction comparison."""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

PRODUCT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PRODUCT))
from backend.compact_market import pair_measure
from research.path_similarity_experiment import OUTPUT, BASE, METHODS, verify_record


def load_rows(path):
    return list(map(json.loads,path.read_text(encoding='utf-8').splitlines()))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--repro',type=Path,default=OUTPUT/'repro')
    args=parser.parse_args()
    manifest=json.loads((OUTPUT/'manifest_PRIVATE.json').read_text(encoding='utf-8'))
    for relative,expected in manifest['inputs'].items():
        assert sha256((PRODUCT/relative).read_bytes()).hexdigest()==expected,relative
    summary=json.loads((OUTPUT/'summary.json').read_text(encoding='utf-8'))
    assert sha256((OUTPUT/'queries_PRIVATE.jsonl').read_bytes()).hexdigest()==summary['result_digest']
    old={r['case_id']:r for r in load_rows(BASE/'queries_PRIVATE.jsonl') if 'existing_hybrid' in r['methods']}
    records=load_rows(OUTPUT/'queries_PRIVATE.jsonl')
    assert len(records)==len(old)==41
    cases={c['id']:c for c in json.loads((PRODUCT/'private/cases.json').read_text(encoding='utf-8'))['cases']}
    descriptions={d['case_id']:d for d in load_rows(BASE/'descriptions_PRIVATE.jsonl')}
    checked=0
    extra={'dtw_5m_pct','dtw_1h_pct','derivative_5m_rmse_pct'}
    for r in records:
        previous=old[r['case_id']]
        assert r['counts']==previous['counts'] and r['volatility_bounds']==previous['volatility_bounds']
        assert set(r['methods'])==set(METHODS)
        checked+=verify_record(r,cases,descriptions)
        for method,rows in r['methods'].items():
            assert len(rows)==5
            if method in METHODS[:3]:
                # Imported baselines cannot silently change or switch candidate pools.
                assert [{k:v for k,v in p.items() if k not in extra} for p in rows]==previous['methods'][method]
            for p in rows:
                measure=pair_measure(descriptions[r['case_id']],descriptions[p['case_id']],r['volatility_bounds'])
                assert measure['field_matches']==p['fields']
                assert measure['agreement_count']==p['agreement']
        for method in ('dual_structure','dual_dtw_structure'):
            values=[p['fields']['structure'] for p in r['methods'][method]]
            assert values==sorted(values,reverse=True)
    assert (OUTPUT/'queries_PRIVATE.jsonl').read_bytes()==(args.repro/'queries_PRIVATE.jsonl').read_bytes()
    assert (OUTPUT/'summary.json').read_bytes()==(args.repro/'summary.json').read_bytes()
    assert (OUTPUT/'comparison.csv').read_bytes()==(args.repro/'comparison.csv').read_bytes()
    value=dict(status='PASS',queries=len(records),checked_pairs=checked,input_hashes_checked=len(manifest['inputs']),
               temporal_or_group_violations=0,reproducible_query_rows=len(records),
               unchanged_baseline_pairs=41*5*3,summary_and_csv_byte_identical=True,
               similarity_accuracy=None,validator_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    (OUTPUT/'validation.json').write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2),encoding='utf-8')
    print(json.dumps(value,ensure_ascii=False))


if __name__=='__main__':main()
