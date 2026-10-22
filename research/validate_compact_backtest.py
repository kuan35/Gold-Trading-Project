"""Audit every exported retrieval pair, optionally compare a second replay."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

PRODUCT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PRODUCT))
from backend.compact_market import pair_measure


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=PRODUCT/'private/compact_retrieval_backtest_20261020')
    parser.add_argument('--repro',type=Path)
    args=parser.parse_args()
    out=args.output
    manifest=json.loads((out/'manifest_PRIVATE.json').read_text(encoding='utf-8'))
    for relative,digest in manifest['inputs'].items():
        assert sha256((PRODUCT/relative).read_bytes()).hexdigest()==digest, 'Changed input/code: '+relative
    cases={r['id']:r for r in json.loads((PRODUCT/'private/cases.json').read_text(encoding='utf-8'))['cases']}
    descriptions={r['case_id']:r for r in rows(out/'descriptions_PRIVATE.jsonl')}
    records=rows(out/'queries_PRIVATE.jsonl')
    summary=json.loads((out/'summary.json').read_text(encoding='utf-8'))
    assert summary['result_digest']==sha256((out/'queries_PRIVATE.jsonl').read_bytes()).hexdigest()
    count=0;seen_query_windows=set()
    for record in records:
        q=descriptions[record['case_id']]
        assert q['window_end']<=record['as_of']==q['as_of']
        window=(record['side'],q['end_5m'],q['end_1h'])
        assert record['primary']==(window not in seen_query_windows)
        seen_query_windows.add(window)
        for method,results in record['methods'].items():
            seen_groups=set();seen_windows=set()
            assert len(results)<=5
            for result in results:
                c=cases[result['case_id']];d=descriptions[c['id']]
                assert c['side']==record['side'] and c['group']!=record['group']
                assert c['available_at']<=record['as_of'] and d['as_of']<=record['as_of']
                assert d['window_end']<=q['window_start'], 'Overlapping pre-entry charts'
                candidate_window=(d['end_5m'],d['end_1h'])
                assert c['group'] not in seen_groups and candidate_window not in seen_windows
                seen_groups.add(c['group']);seen_windows.add(candidate_window)
                pair=pair_measure(q,d,record['volatility_bounds'])
                assert pair['agreement_count']==result['agreement']
                assert pair['field_matches']==result['fields']
                assert abs(pair['max_difference_atr']-result['max_difference_atr'])<1e-12
                count+=1
            if method=='full':
                assert [r['agreement'] for r in results]==sorted((r['agreement'] for r in results),reverse=True)
    equal=None
    if args.repro:
        other=rows(args.repro/'queries_PRIVATE.jsonl')
        assert len(records)==len(other)
        for a,b in zip(records,other):
            a=dict(a,methods={k:v for k,v in a['methods'].items() if k!='existing_hybrid'})
            b=dict(b,methods={k:v for k,v in b['methods'].items() if k!='existing_hybrid'})
            assert a==b, 'Non-reproducible query '+a['case_id']
        assert (out/'descriptions_PRIVATE.jsonl').read_bytes()==(args.repro/'descriptions_PRIVATE.jsonl').read_bytes()
        equal=len(records)
    result=dict(status='PASS',queries=len(records),primary_queries=len(seen_query_windows),
                checked_pairs=count,reproducible_query_rows=equal,temporal_or_group_violations=0,
                input_hashes_checked=len(manifest['inputs']),similarity_accuracy=None)
    (out/'validation.json').write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
