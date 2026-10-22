"""Compare longer five-minute-only paths without changing production retrieval."""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sys

import numpy as np

PRODUCT=Path(__file__).resolve().parents[1]
PRIVATE=PRODUCT/'private'
PROBE=PRIVATE/'price_only_probe_20261013'
BASE=PRIVATE/'compact_retrieval_backtest_20261020'
OUTPUT=PRIVATE/'five_minute_lookback_20261020'
sys.path.insert(0,str(PRODUCT))
sys.path.insert(0,str(PROBE))
from backend.candidate_bars import _prices
from backend.candidate_sidecar import load_candidate_sidecar
from backend.compact_market import eligible_pool, volatility_bounds, distinct_rows
from research.path_similarity_experiment import percentile_rank, order_candidates
from research.backtest_compact_retrieval import path_pct, annotate, dump, aggregate
from full_corpus_kline_audit import load_bars, HISTDATA, DUKASCOPY
from candidate_gap_sources import load_allowed_session_gaps, EVIDENCE

METHODS=('five60','five120','five240','five_nested','dual_structure')
LABELS=dict(five60='5分60根＋高低',five120='5分120根＋高低',five240='5分240根＋高低',
            five_nested='5分60／120／240分窗＋高低',dual_structure='5分60＋1h20對照＋高低')


def closed_window(bars,times,as_of,count,allowed):
    end=bisect_right(times,as_of-300)
    if end<count:return [],'INSUFFICIENT_HISTORY'
    selected=bars[end-count:end]
    if as_of-selected[-1]['time']-300>=300:return [],'STALE_LAST_CLOSED_BAR'
    for b in selected:_prices(b)
    for a,b in zip(selected,selected[1:]):
        if b['time']<=a['time']:raise ValueError('unordered or duplicate five-minute window')
        if b['time']-a['time']!=300 and (a['time']+300,b['time']) not in allowed:
            return [],'UNEXPLAINED_GAP'
    return selected,None


def normalise_closes(bars):
    closes=np.array([float(b['close']) for b in bars])
    if not len(closes) or not np.isfinite(closes).all() or np.any(closes<=0):
        raise ValueError('finite positive prices required')
    return (closes/closes[0]-1)*100


def rank_windows(pool,descriptions,query,distances):
    if not distances or any(len(d)!=len(pool) for d in distances):
        raise ValueError('distance vectors must match pool')
    ranks=np.asarray([percentile_rank(d) for d in distances])
    rows=[dict(case_id=c['id'],group=c['group'],
               same=descriptions[c['id']]['structure']==query['structure'],
               worst=float(np.max(ranks[:,i])),total=float(np.sum(ranks[:,i])))
          for i,c in enumerate(pool)]
    rows.sort(key=lambda r:(not r['same'],r['worst'],r['total'],r['case_id']))
    return distinct_rows(rows,descriptions)


def load_inputs():
    original=json.loads((BASE/'manifest_PRIVATE.json').read_text(encoding='utf-8'))
    for relative,expected in original['inputs'].items():
        assert sha256((PRODUCT/relative.replace('\\','/')).read_bytes()).hexdigest()==expected,relative
    profiles,status=load_candidate_sidecar(PRIVATE/'cases.json',PRIVATE/'case_candidate_market_profiles.json',PRIVATE)
    if status!='READY':raise RuntimeError('sidecar integrity: '+status)
    descriptions={d['case_id']:d for d in map(json.loads,(BASE/'descriptions_PRIVATE.jsonl').read_text(encoding='utf-8').splitlines())}
    cases=json.loads((PRIVATE/'cases.json').read_text(encoding='utf-8'))['cases']
    records=list(map(json.loads,(BASE/'queries_PRIVATE.jsonl').read_text(encoding='utf-8').splitlines()))
    queries=[r for r in records if 'existing_hybrid' in r['methods']]
    return cases,profiles,descriptions,queries


def build_windows(cases,profiles,descriptions,bars,allowed):
    times=[b['time'] for b in bars]
    windows={};coverage=[];cache={};extended={};paths={};sample_bars={}
    for number,c in enumerate(cases,1):
        cid=c['id']
        if cid not in descriptions:continue
        d=descriptions[cid];clock=d['as_of']
        if clock not in cache:
            cache[clock]={n:closed_window(bars,times,clock,n,allowed) for n in (60,120,240)}
        item=cache[clock]
        recent,reason=item[60]
        prior=profiles[cid]['pre_entry_bars']['5m']
        matches=not reason and len(recent)==len(prior) and all(
            a['time']==b['time'] and all(Decimal(a[k])==Decimal(b[k]) for k in ('open','high','low','close'))
            for a,b in zip(recent,prior))
        statuses={str(n):(error or 'READY') for n,(window,error) in item.items()}
        if not matches:statuses={k:'RECENT_PROFILE_MISMATCH' for k in statuses}
        coverage.append(dict(case_id=cid,tier=d['tier'],statuses=statuses,
                             recent60_matches_profile=bool(matches)))
        if statuses['240']=='READY':
            selected=item[240][0]
            windows[cid]=[selected[0]['time'],selected[-1]['time']+300]
            extended[cid]=dict(d,window_start=min(d['window_start'],selected[0]['time']),
                               window_end=max(d['window_end'],selected[-1]['time']+300))
            paths[cid]={str(n):normalise_closes(selected[-n:]) for n in (60,120,240)}
            # The raw bars are only a view of the existing immutable cache.
            sample_bars[cid]=selected
        if number%1500==0:print(f'coverage={number}/{len(cases)} extended={len(extended)}',flush=True)
    return coverage,extended,paths,windows,sample_bars


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--coverage-only',action='store_true')
    args=parser.parse_args(argv)
    output=args.output.resolve()
    if not output.is_relative_to(PRIVATE.resolve()):raise ValueError('private output required')
    output.mkdir(parents=True,exist_ok=True)
    cases,profiles,descriptions,queries=load_inputs()
    files=[PRIVATE/'cases.json',PRIVATE/'case_candidate_market_profiles.json',BASE/'queries_PRIVATE.jsonl',
           BASE/'descriptions_PRIVATE.jsonl',BASE/'manifest_PRIVATE.json',HISTDATA,DUKASCOPY,EVIDENCE,
           Path(__file__),PROBE/'full_corpus_kline_audit.py',PROBE/'candidate_gap_sources.py',
           PRODUCT/'research/path_similarity_experiment.py',PRODUCT/'research/backtest_compact_retrieval.py',
           PRODUCT/'backend/compact_market.py',PRODUCT/'backend/candidate_bars.py',
           PRODUCT/'docs/five_minute_lookback_plan_20261020.md']
    hashes={str(p.relative_to(PRODUCT.parent)).replace('\\','/'):sha256(p.read_bytes()).hexdigest() for p in files}
    print('loading original five-minute caches',flush=True)
    bars,cache_counts=load_bars()
    allowed=set(load_allowed_session_gaps())
    coverage,extended,paths,windows,sample_bars=build_windows(cases,profiles,descriptions,bars,allowed)
    dump(output/'coverage_PRIVATE.json',coverage)
    counts={tier:{str(n):dict(Counter(r['statuses'][str(n)] for r in coverage if r['tier']==tier))
                  for n in (60,120,240)} for tier in ('full','5m_only')}
    dump(output/'coverage_summary.json',dict(total=len(coverage),by_original_tier=counts,cache_counts=cache_counts))
    print('coverage='+json.dumps(counts),flush=True)
    if args.coverage_only:return
    full_cases=[c for c in cases if c['id'] in extended and extended[c['id']]['tier']=='full']
    pos={c['id']:i for i,c in enumerate(full_cases)}
    matrices={str(n):np.asarray([paths[c['id']][str(n)] for c in full_cases]) for n in (60,120,240)}
    hour={c['id']:path_pct(profiles[c['id']],'1h') for c in full_cases}
    hour_matrix=np.asarray([hour[c['id']] for c in full_cases])
    old_paths={c['id']:{'5m':paths[c['id']]['60'].tolist(),'1h':hour[c['id']]} for c in full_cases}
    records=[];checked=0
    by_case={c['id']:c for c in cases}
    for number,old in enumerate(queries,1):
        qid=old['case_id']
        record={k:v for k,v in old.items() if k not in ('methods','counts','volatility_bounds')}
        record.update(methods={m:[] for m in METHODS},status='QUERY_240_UNAVAILABLE',counts={})
        if qid not in pos:
            record['reason']=next(r['statuses']['240'] for r in coverage if r['case_id']==qid)
            records.append(record);continue
        q=extended[qid]
        pool,pool_counts=eligible_pool(full_cases,extended,q,exclude_group=old['group'])
        record['counts']=pool_counts
        bounds=volatility_bounds(pool,extended)
        record.update(volatility_bounds=bounds,status='NO_COMPARABLE_HISTORY' if not bounds else 'READY')
        if bounds:
            locations=np.asarray([pos[c['id']] for c in pool],dtype=int)
            distance={n:np.sqrt(np.mean((a[locations]-paths[qid][n])**2,axis=1)) for n,a in matrices.items()}
            h_distance=np.sqrt(np.mean((hour_matrix[locations]-np.asarray(hour[qid]))**2,axis=1))
            lookup={c['id']:i for i,c in enumerate(pool)}
            old_paths['query']=old_paths[qid]
            for m in METHODS:
                if m=='dual_structure':
                    ranked=order_candidates(pool,extended,q,distance['60'],h_distance,structure_first=True)
                else:
                    selected=list(distance.values()) if m=='five_nested' else [distance[m[4:]]]
                    ranked=rank_windows(pool,extended,q,selected)
                rows=annotate(ranked,extended,q,bounds,old_paths)
                seen_groups=set();seen_windows=set()
                for p in rows:
                    cid=p['case_id'];d=extended[cid];c=by_case[cid];i=lookup[cid]
                    p.update(path_120_rmse_pct=float(distance['120'][i]),path_240_rmse_pct=float(distance['240'][i]))
                    assert c['available_at']<=q['as_of'] and c['side']==q['side'] and c['group']!=old['group']
                    assert d['window_end']<=q['window_start']
                    win=(d['end_5m'],d['end_1h'])
                    assert c['group'] not in seen_groups and win not in seen_windows
                    seen_groups.add(c['group']);seen_windows.add(win);checked+=1
                record['methods'][m]=rows
        records.append(record)
        if number%5==0 or number==len(queries):print(f'replay={number}/{len(queries)} checked={checked}',flush=True)
    with (output/'queries_PRIVATE.jsonl').open('w',encoding='utf-8',newline='\n') as stream:
        for r in records:stream.write(json.dumps(r,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n')
    stats={m:aggregate(records,m) for m in METHODS}
    for m in METHODS:
        pairs=[p for r in records for p in r['methods'][m]]
        for key in ('path_120_rmse_pct','path_240_rmse_pct'):
            stats[m][key]=float(np.mean([p[key] for p in pairs])) if pairs else None
    summary=dict(query_denominator=len(records),statuses=dict(Counter(r['status'] for r in records)),
                 all_extended_profiles=len(extended),full_intersection_rows=len(full_cases),methods=stats,
                 coverage=counts,checked_pairs=checked,similarity_accuracy=None,
                 result_digest=sha256((output/'queries_PRIVATE.jsonl').read_bytes()).hexdigest())
    dump(output/'summary.json',summary)
    dump(output/'extended_windows_PRIVATE.json',windows)
    dump(output/'manifest_PRIVATE.json',dict(inputs=hashes,method='five_minute_lookback_v1',windows=[60,120,240],
                                             allowed_gap_count=len(allowed)))
    # Persist only fixed diagram examples; all rows remain reproducible from caches.
    example_records=[]
    for year in (2024,2025):
        record=next((r for r in records if r['year']==year and all(len(r['methods'][m])==5 for m in METHODS)),None)
        if not record:continue
        ids=[record['case_id']]+[record['methods'][m][0]['case_id'] for m in METHODS]
        example_records.append(dict(record=record,bars={cid:sample_bars[cid] for cid in ids}))
    dump(output/'examples_PRIVATE.json',example_records)
    for relative,expected in hashes.items():
        assert sha256((PRODUCT.parent/relative).read_bytes()).hexdigest()==expected,'input changed during run'
    dump(output/'validation.json',dict(status='PASS',queries=len(records),checked_pairs=checked,
                                       temporal_or_group_violations=0,input_hashes_checked=len(hashes)))
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
