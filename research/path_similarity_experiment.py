"""Frozen, matched-month comparison of full paths and bounded time warping.

This is offline chart retrieval, not a trading strategy or relevance classifier.
All floats are dimensionless percent paths/distances. No account/API access.
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))
from backend.compact_market import distinct_rows, eligible_pool, volatility_bounds
from backend.candidate_sidecar import load_candidate_sidecar
from research.backtest_compact_retrieval import path_pct, annotate, aggregate, dump

BASE = PRODUCT/'private/compact_retrieval_backtest_20261020'
OUTPUT = PRODUCT/'private/path_similarity_experiment_20261020'
METHODS = ('existing_hybrid','full','path_only','dual_path','dual_structure','dual_dtw_structure')
LABELS = dict(existing_hybrid='原12指標混合法', full='四欄文字基線', path_only='單五分鐘路徑',
              dual_path='完整雙週期路徑', dual_structure='雙週期＋高低狀態',
              dual_dtw_structure='雙週期＋高低＋小幅錯時')


def band_dtw(query: np.ndarray, candidates: np.ndarray, radius: int) -> np.ndarray:
    """Exact batched squared-cost DTW in a fixed Sakoe-Chiba index band.

    Equal-length, endpoint-anchored paths; divide accumulated cost by nominal
    series length, not warped path length. Radius 0 is exactly pointwise RMSE.
    """
    query, candidates = np.asarray(query, dtype=float), np.asarray(candidates, dtype=float)
    if (type(radius) is not int or radius < 0 or query.ndim != 1 or len(query) == 0
            or candidates.ndim != 2 or candidates.shape[1] != len(query)
            or not np.isfinite(query).all() or not np.isfinite(candidates).all()):
        raise ValueError('finite equal-length sequences and nonnegative integer radius required')
    n, batch = len(query), len(candidates)
    previous = np.full((n+1, batch), np.inf)
    previous[0] = 0
    for i in range(1, n+1):
        current = np.full_like(previous, np.inf)
        for j in range(max(1, i-radius), min(n, i+radius)+1):
            current[j] = (query[i-1]-candidates[:, j-1])**2 + np.minimum(
                np.minimum(previous[j], previous[j-1]), current[j-1])
        previous = current
    return np.sqrt(previous[n]/n)


def percentile_rank(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or not np.isfinite(values).all():
        raise ValueError('finite distance vector required')
    if not len(values): return np.array([], dtype=float)
    return np.searchsorted(np.sort(values), values, side='left')/len(values)


def order_candidates(pool, descriptions, query, five, hour, *, structure_first):
    if len(pool) != len(five) or len(pool) != len(hour):
        raise ValueError('pool and distance lengths differ')
    r5, rh = percentile_rank(five), percentile_rank(hour)
    rows = []
    for i, c in enumerate(pool):
        same = descriptions[c['id']]['structure'] == query['structure']
        rows.append(dict(case_id=c['id'], group=c['group'], structure_same=same,
                         rank_max=float(max(r5[i],rh[i])), rank_sum=float(r5[i]+rh[i])))
    rows.sort(key=lambda r: ((not r['structure_same']) if structure_first else False,
                             r['rank_max'],r['rank_sum'],r['case_id']))
    return distinct_rows(rows, descriptions)


def verify_record(record, cases_by_id, descriptions):
    q = descriptions[record['case_id']]
    count = 0
    for method, rows in record['methods'].items():
        groups, windows = set(), set()
        for row in rows:
            c = cases_by_id[row['case_id']]; d = descriptions[c['id']]
            assert c['side'] == q['side'] == d['side']
            assert c['group'] != record['group'] and c['available_at'] <= q['as_of']
            assert d['as_of'] <= q['as_of'] and d['window_end'] <= q['window_start']
            assert d['tier'] == q['tier'] == 'full'
            window = (d['end_5m'],d['end_1h'])
            assert c['group'] not in groups and window not in windows
            groups.add(c['group']); windows.add(window); count += 1
            assert all(np.isfinite(row[k]) and row[k] >= 0 for k in (
                'path_5m_rmse_pct','path_1h_rmse_pct','dtw_5m_pct','dtw_1h_pct'))
            # The diagonal alignment is always allowed: DTW cannot exceed RMSE.
            assert row['dtw_5m_pct'] <= row['path_5m_rmse_pct']+1e-10
            assert row['dtw_1h_pct'] <= row['path_1h_rmse_pct']+1e-10
    return count


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--limit', type=int)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if not output.is_relative_to((PRODUCT/'private').resolve()):
        raise ValueError('private per-case outputs must remain under product/private')
    output.mkdir(parents=True,exist_ok=True)
    # Freeze source files, including the previous experiment code and specification.
    old_manifest = json.loads((BASE/'manifest_PRIVATE.json').read_text(encoding='utf-8'))
    for relative, expected in old_manifest['inputs'].items():
        file = PRODUCT/relative.replace('\\','/')
        if sha256(file.read_bytes()).hexdigest() != expected:
            raise RuntimeError('frozen original input changed: '+relative)
    inputs = [PRODUCT/'private/cases.json',PRODUCT/'private/case_candidate_market_profiles.json',
              BASE/'queries_PRIVATE.jsonl',BASE/'descriptions_PRIVATE.jsonl',BASE/'manifest_PRIVATE.json',
              Path(__file__),PRODUCT/'backend/compact_market.py',
              PRODUCT/'research/backtest_compact_retrieval.py',
              PRODUCT/'docs/path_similarity_experiment_plan_20261020.md']
    manifest = {p.relative_to(PRODUCT).as_posix():sha256(p.read_bytes()).hexdigest() for p in inputs}
    profiles, status = load_candidate_sidecar(inputs[0],inputs[1],PRODUCT/'private')
    if status != 'READY': raise RuntimeError('profile integrity: '+status)
    cases = json.loads(inputs[0].read_text(encoding='utf-8'))['cases']
    by_id = {c['id']:c for c in cases}
    descriptions = {d['case_id']:d for d in map(json.loads,(BASE/'descriptions_PRIVATE.jsonl').read_text(encoding='utf-8').splitlines())}
    old_records = list(map(json.loads,(BASE/'queries_PRIVATE.jsonl').read_text(encoding='utf-8').splitlines()))
    queries = [r for r in old_records if 'existing_hybrid' in r['methods']]
    if args.limit: queries = queries[:args.limit]
    elif len(queries) != 41: raise RuntimeError('frozen monthly cohort changed')
    full_cases = [c for c in cases if c['id'] in descriptions and descriptions[c['id']]['tier']=='full']
    paths = {c['id']:{iv:path_pct(profiles[c['id']],iv) for iv in ('5m','1h')} for c in full_cases}
    index = {c['id']:i for i,c in enumerate(full_cases)}
    matrices = {iv:np.asarray([paths[c['id']][iv] for c in full_cases]) for iv in ('5m','1h')}
    records, timings = [], []
    checked = 0
    for number, old in enumerate(queries,1):
        qid = old['case_id']; q = descriptions[qid]
        pool, counts = eligible_pool(full_cases,descriptions,q,exclude_group=old['group'])
        bounds = volatility_bounds(pool,descriptions)
        if counts != old['counts'] or bounds != old['volatility_bounds']:
            raise RuntimeError('candidate pool differs from original comparison')
        positions = np.asarray([index[c['id']] for c in pool],dtype=int)
        started = perf_counter()
        arrays = {iv:matrices[iv][positions] for iv in matrices}
        rms = {iv:np.sqrt(np.mean((a-np.asarray(paths[qid][iv]))**2,axis=1)) for iv,a in arrays.items()}
        elapsed_rms = perf_counter()-started
        started = perf_counter()
        warped = {iv:band_dtw(np.asarray(paths[qid][iv]),a,3 if iv=='5m' else 1) for iv,a in arrays.items()}
        elapsed_dtw = perf_counter()-started
        location = {c['id']:i for i,c in enumerate(pool)}
        paths['query'] = paths[qid]
        methods = {name:old['methods'][name] for name in METHODS[:3]}
        for method, metric, structure in [('dual_path',rms,False),('dual_structure',rms,True),
                                            ('dual_dtw_structure',warped,True)]:
            ranked = order_candidates(pool,descriptions,q,metric['5m'],metric['1h'],structure_first=structure)
            methods[method] = annotate(ranked,descriptions,q,bounds,paths)
        for method, rows in methods.items():
            for row in rows:
                i = location[row['case_id']]
                row.update(dtw_5m_pct=float(warped['5m'][i]),dtw_1h_pct=float(warped['1h'][i]),
                           derivative_5m_rmse_pct=float(np.sqrt(np.mean((np.diff(paths[qid]['5m'])-np.diff(paths[row['case_id']]['5m']))**2))))
        record = {k:v for k,v in old.items() if k != 'methods'}
        record.update(methods=methods, same_structure_groups=len({c['group'] for c in pool if descriptions[c['id']]['structure']==q['structure']}))
        checked += verify_record(record,by_id,descriptions)
        records.append(record)
        timings.append(dict(case_id=qid,eligible_rows=len(pool),path_distance_seconds=elapsed_rms,dtw_distance_seconds=elapsed_dtw))
        if number%5==0 or number==len(queries): print(f'matched-month={number}/{len(queries)} pairs_checked={checked}',flush=True)
    with (output/'queries_PRIVATE.jsonl').open('w',encoding='utf-8',newline='\n') as stream:
        for r in records: stream.write(json.dumps(r,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n')
    stats = {m:aggregate(records,m) for m in METHODS}
    for m in METHODS:
        pairs = [p for r in records for p in r['methods'][m]]
        for key in ('dtw_5m_pct','dtw_1h_pct','derivative_5m_rmse_pct'):
            stats[m][key] = float(np.mean([p[key] for p in pairs])) if pairs else None
    summary = dict(cohort='frozen 41 monthly queries 2021-2025',queries=len(records),
                   methods=stats, by_year={str(year):{m:aggregate([r for r in records if r['year']==year],m) for m in METHODS}
                                         for year in sorted({r['year'] for r in records})},
                   similarity_accuracy=None, checked_pairs=checked,
                   result_digest=sha256((output/'queries_PRIVATE.jsonl').read_bytes()).hexdigest())
    dump(output/'summary.json',summary)
    dump(output/'manifest_PRIVATE.json',dict(inputs=manifest,dtw_radius=dict(five=3,hour=1),
                                            no_post_entry_ranking_features=True))
    dump(output/'timings.json',timings)
    dump(output/'validation.json',dict(status='PASS',queries=len(records),checked_pairs=checked,
                                       temporal_or_group_violations=0,input_hashes_checked=len(manifest)))
    with (output/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        keys=['queries','pair_count','path_5m_rmse_pct','path_1h_rmse_pct','structure_agreement',
              'hourly_pattern_agreement','volatility_ratio','mean_agreement','dtw_5m_pct','dtw_1h_pct']
        writer=csv.DictWriter(stream,fieldnames=['method','label']+keys);writer.writeheader()
        for m in METHODS:writer.writerow(dict(method=m,label=LABELS[m],**{k:stats[m][k] for k in keys}))
    print(json.dumps(dict(queries=len(records),checked_pairs=checked,result_digest=summary['result_digest']),ensure_ascii=False),flush=True)


if __name__=='__main__': main()
