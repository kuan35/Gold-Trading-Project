"""Audit the exported long-window replay independently of ranking code."""
from __future__ import annotations
from collections import Counter
from decimal import Decimal
from hashlib import sha256
import json
from math import sqrt
from pathlib import Path
from statistics import mean
import sys

PRODUCT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PRODUCT))
from backend.compact_market import pair_measure

OUT=PRODUCT/'private/five_minute_lookback_20261020'
BASE=PRODUCT/'private/compact_retrieval_backtest_20261020'


def rows(path):return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


def independent_path(bars):
    base=Decimal(bars[0]['close'])
    return [float((Decimal(b['close'])/base-1)*100) for b in bars]


def main():
    manifest=json.loads((OUT/'manifest_PRIVATE.json').read_text(encoding='utf-8'))
    for relative,expected in manifest['inputs'].items():
        assert sha256((PRODUCT.parent/relative).read_bytes()).hexdigest()==expected,relative
    summary=json.loads((OUT/'summary.json').read_text(encoding='utf-8'))
    assert sha256((OUT/'queries_PRIVATE.jsonl').read_bytes()).hexdigest()==summary['result_digest']
    cases={c['id']:c for c in json.loads((PRODUCT/'private/cases.json').read_text(encoding='utf-8'))['cases']}
    profiles=json.loads((PRODUCT/'private/case_candidate_market_profiles.json').read_text(encoding='utf-8'))['profiles']
    desc={d['case_id']:d for d in rows(BASE/'descriptions_PRIVATE.jsonl')}
    windows=json.loads((OUT/'extended_windows_PRIVATE.json').read_text(encoding='utf-8'))
    coverage=json.loads((OUT/'coverage_PRIVATE.json').read_text(encoding='utf-8'))
    assert len(coverage)==len(desc)==10887
    assert all(r['recent60_matches_profile'] for r in coverage)
    assert {r['case_id'] for r in coverage if r['statuses']['240']=='READY'}==set(windows)
    for tier in ('full','5m_only'):
        for n in (60,120,240):
            counts=dict(Counter(r['statuses'][str(n)] for r in coverage if r['tier']==tier))
            assert counts==summary['coverage'][tier][str(n)]
    original=[r['case_id'] for r in rows(BASE/'queries_PRIVATE.jsonl') if 'existing_hybrid' in r['methods']]
    records=rows(OUT/'queries_PRIVATE.jsonl')
    assert [r['case_id'] for r in records]==original
    assert len(records)==41 and all(r['status']=='READY' for r in records)
    checked=0
    for r in records:
        q=desc[r['case_id']];q_start=min(q['window_start'],windows[r['case_id']][0])
        assert windows[r['case_id']][1]<=q['as_of']
        qpaths={iv:independent_path(profiles[r['case_id']]['pre_entry_bars'][iv]) for iv in ('5m','1h')}
        for m,results in r['methods'].items():
            groups=set();times=set()
            assert len(results)==5
            for p in results:
                c=cases[p['case_id']];d=desc[c['id']]
                assert c['side']==q['side'] and c['group']!=r['group']
                assert c['available_at']<=q['as_of'] and d['as_of']<=q['as_of']
                assert max(d['window_end'],windows[c['id']][1])<=q_start
                assert d['tier']==q['tier']=='full'
                win=(d['end_5m'],d['end_1h'])
                assert c['group'] not in groups and win not in times
                groups.add(c['group']);times.add(win)
                measure=pair_measure(q,d,r['volatility_bounds'])
                assert measure['field_matches']==p['fields'] and measure['agreement_count']==p['agreement']
                for iv,key in [('5m','path_5m_rmse_pct'),('1h','path_1h_rmse_pct')]:
                    path=independent_path(profiles[c['id']]['pre_entry_bars'][iv])
                    distance=sqrt(mean((a-b)**2 for a,b in zip(qpaths[iv],path)))
                    assert abs(distance-p[key])<1e-10
                checked+=1
            same=[p['fields']['structure'] for p in results]
            assert same==sorted(same,reverse=True)
    # A separate full run must match every row and all coverage results.
    for name in ('queries_PRIVATE.jsonl','coverage_PRIVATE.json','coverage_summary.json','extended_windows_PRIVATE.json','summary.json','examples_PRIVATE.json'):
        assert (OUT/name).read_bytes()==(OUT/'repro'/name).read_bytes(),name
    value=dict(status='PASS',queries=41,checked_pairs=checked,coverage_rows=len(coverage),
               source_recent60_matches=10887,temporal_or_group_violations=0,input_hashes_checked=len(manifest['inputs']),
               independent_decimal_path_checks=checked*2,reproducible_query_rows=41,
               six_exports_byte_identical=True,similarity_accuracy=None,
               validator_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    (OUT/'validation.json').write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2),encoding='utf-8')
    print(json.dumps(value,ensure_ascii=False))


if __name__=='__main__':main()
