"""Offline, frozen A/B context comparison; never imported by product routes."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean
import csv
import sys
from time import perf_counter

PRODUCT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PRODUCT))
from backend.compact_market import describe_compact
from backend.dual_path_retrieval import DualPathIndex
from backend.candidate_sidecar import load_candidate_sidecar
from backend.context_rules import market_features, pair_metrics, evaluate_rows, LIMITS

METHOD='context_contract_probe_v1'
OUTPUT=PRODUCT/'private/context_similarity_ab_20261021'

RUNS={
    'B_paths':('medium','paths'),
    'B_tail':('medium','tail'),
    'B_vol':('medium','vol'),
    'B_medium':('medium','full'),
    'B_strict':('strict','full'),
    'B_loose':('loose','full'),
}


def dump(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def aggregate(records,method):
    usable=[r for r in records if r['methods'][method]['rows']]
    top=[r['methods'][method]['rows'][0] for r in usable]
    result=dict(queries=len(records),queries_with_output=len(usable),empty_queries=len(records)-len(usable),
                displayed_pairs=sum(len(r['methods'][method]['rows']) for r in records),
                full_five_queries=sum(len(r['methods'][method]['rows'])==5 for r in records))
    for key in ('d5','d1h','dtail','vol_ratio'):
        result['mean_top1_'+key]=mean(r[key] for r in top) if top else None
    result['event_match_top1']=sum(r['query_event']==r['case_event'] and r['query_event']!='BOUNDARY_UNKNOWN' for r in top)
    result['opposed_tail_top1']=sum({r['query_tail'],r['case_tail']}=={'U','D'} for r in top)
    result['similarity_accuracy']=None
    return result


def write_review_template(records,path):
    """Create once: rendering must never replace a person's completed labels."""
    try:
        stream=path.open('x',encoding='utf-8-sig',newline='')
    except FileExistsError:
        return False
    with stream:
        writer=csv.writer(stream)
        writer.writerow(['query_id','method','case_id','reviewer','comparable_yes_no_insufficient','reason'])
        for r in records:
            for method in ('A','B_medium'):
                for pair in r['methods'][method]['rows']:
                    writer.writerow([r['query_id'],method,pair['case_id'],'','',''])
    return True


def main(argv=None):
    import numpy as np  # Optional numeric runtime; pure rule tests need only stdlib.
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=OUTPUT)
    args=parser.parse_args(argv);out=args.output.resolve()
    if not out.is_relative_to((PRODUCT/'private').resolve()):raise ValueError('PRIVATE_OUTPUT_REQUIRED')
    out.mkdir(parents=True,exist_ok=True)
    paths=[PRODUCT/'private/cases.json',PRODUCT/'private/case_candidate_market_profiles.json',
           PRODUCT/'private/path_similarity_experiment_20261020/queries_PRIVATE.jsonl',
           PRODUCT/'private/distinct_day_dual_path_20261021/samples_PRIVATE.json',
           PRODUCT/'backend/dual_path_retrieval.py',PRODUCT/'backend/compact_market.py',
           PRODUCT/'backend/candidate_sidecar.py',PRODUCT/'backend/candidate_profile.py',
           PRODUCT/'backend/candidate_bars.py',PRODUCT/'backend/live_candidate_profile.py',
           PRODUCT/'docs/context_similarity_ab_plan_20261021.md',Path(__file__),
           PRODUCT/'research/test_context_similarity_ab.py',PRODUCT/'research/requirements.txt',
           PRODUCT/'backend/context_rules.py']
    inputs={p.relative_to(PRODUCT).as_posix():sha256(p.read_bytes()).hexdigest() for p in paths}
    cases=json.loads(paths[0].read_text(encoding='utf-8'))['cases']
    profiles,status=load_candidate_sidecar(paths[0],paths[1],PRODUCT/'private')
    if status!='READY':raise RuntimeError('INVALID_INDEX: '+status)
    index=DualPathIndex(cases,profiles)
    print('Building shared index and context features; no model, API or order calls.',flush=True)
    features={c['id']:market_features(profiles[c['id']]) for c in index.cases}
    ids=[c['id'] for c in index.cases];positions={cid:i for i,cid in enumerate(ids)}
    matrices={key:np.asarray([features[cid][key] for cid in ids]) for key in ('path5','path1h','tail_path')}
    monthly=[json.loads(s) for s in paths[2].read_text(encoding='utf-8').splitlines()]
    broker=json.loads(paths[3].read_text(encoding='utf-8'))['records']
    queries=[]
    for n,r in enumerate(monthly,1):
        queries.append(dict(query_id=f'M{n:02}',cohort='monthly_2021_2025',as_of=r['as_of'],side=r['side'],
                            profile=profiles[r['case_id']],exclude_group=r['group'],
                            frozen_a=[c['case_id'] for c in r['methods']['dual_structure']],
                            case_id=r['case_id']))
    for r in broker:
        queries.append(dict(query_id=r['sample'],cohort='broker_10_days',as_of=r['as_of'],side=r['side'],
                            profile=r['profile'],exclude_group=None,
                            frozen_a=[c['id'] for c in r['result']['cases']],case_id=None))
    assert len(monthly)==41 and len(broker)==10
    records=[];timings=[];plot_profiles={'queries':{},'cases':{}};checked=0
    for number,q in enumerate(queries,1):
        start=perf_counter();qp=q['profile'];qf=market_features(qp)
        pool,counts=index.eligible(qp,q['side'],q['exclude_group'])
        a=index.retrieve(qp,q['side'],exclude_group=q['exclude_group'])
        assert [c['id'] for c in a['cases']]==q['frozen_a'],q['query_id']+' BASELINE_CHANGED'
        pos=np.array([positions[c['id']] for c in pool],dtype=int)
        vectors={key:np.sqrt(np.mean((matrices[key][pos]-np.asarray(qf[key]))**2,axis=1)) for key in matrices}
        rows=[]
        for i,c in enumerate(pool):
            cf=features[c['id']]
            rows.append(dict(case_id=c['id'],group=c['group'],d5=float(vectors['path5'][i]),
                             d1h=float(vectors['path1h'][i]),dtail=float(vectors['tail_path'][i]),
                             vol_ratio=max(qf['atr_pct']/cf['atr_pct'],cf['atr_pct']/qf['atr_pct']),
                             query_event=qf['event'],case_event=cf['event'],
                             query_tail=qf['tail_direction'],case_tail=cf['tail_direction']))
        by_id={r['case_id']:r for r in rows}
        a_rows=[by_id[c['id']] for c in a['cases']]
        for old,new in zip(a['cases'],a_rows):
            assert abs(old['path_distance_pct']-new['d5'])<1e-10
            assert abs(old['hour_path_distance_pct']-new['d1h'])<1e-10
        methods={'A':dict(rows=a_rows,passed_rows=None,passed_unique=None,rejections={},first_rejection={})}
        passed_ids={}
        for name,(limit,components) in RUNS.items():
            result=evaluate_rows(rows,index.descriptions,LIMITS[limit],components=components)
            passed_ids[name]=result.pop('_passed_ids')
            if name!='B_medium':result.pop('nearest_rejected')
            methods[name]=result
        assert passed_ids['B_strict'] <= passed_ids['B_medium'] <= passed_ids['B_loose']
        assert passed_ids['B_medium'] <= passed_ids['B_vol'] <= passed_ids['B_tail'] <= passed_ids['B_paths']
        for name,result in methods.items():
            groups=set();windows=set()
            for row in result['rows']:
                c=index.lookup[row['case_id']];d=index.descriptions[c['id']]
                assert c['available_at']<=q['as_of'] and c['side']==q['side']
                assert d['window_end']<=describe_compact(qp,q['side'])['window_start']
                assert c['group']!=q['exclude_group'] and c['group'] not in groups
                window=(d['end_5m'],d['end_1h']);assert window not in windows
                groups.add(c['group']);windows.add(window);checked+=1
                if name!='A':assert not row['reasons'] and row['score_max']<=1+1e-12
        records.append(dict(query_id=q['query_id'],cohort=q['cohort'],as_of=q['as_of'],side=q['side'],
                            query_case_id=q['case_id'],query_features=qf,counts=counts,methods=methods))
        plot_profiles['queries'][q['query_id']]=qp
        for name in ('A','B_medium'):
            if methods[name]['rows']:
                cid=methods[name]['rows'][0]['case_id'];plot_profiles['cases'][cid]=profiles[cid]
        timings.append(dict(query_id=q['query_id'],eligible_rows=len(pool),seconds=perf_counter()-start))
        if number%5==0 or number==len(queries):print(f'queries={number}/51; checked displayed pairs={checked}',flush=True)
    for filename,data in [('queries_PRIVATE.json',records),('plot_profiles_PRIVATE.json',plot_profiles)]:dump(out/filename,data)
    summary={}
    for cohort in ('broker_10_days','monthly_2021_2025'):
        selected=[r for r in records if r['cohort']==cohort]
        common=[r for r in selected if r['methods']['B_medium']['rows']]
        summary[cohort]=dict(methods={m:aggregate(selected,m) for m in ('A',*RUNS)},
                            common_output_queries=[r['query_id'] for r in common],
                            common_subset={m:aggregate(common,m) for m in ('A','B_medium')},
                            same_top_one=sum(r['methods']['A']['rows'][0]['case_id']==r['methods']['B_medium']['rows'][0]['case_id'] for r in common))
    with (out/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        fields=['cohort','query_id','as_of','side','method','shown','passed_rows','case_id','d5','d1h','dtail','vol_ratio','query_event','case_event','query_tail','case_tail']
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for r in records:
            for name,v in r['methods'].items():
                first=v['rows'][0] if v['rows'] else {}
                writer.writerow(dict(cohort=r['cohort'],query_id=r['query_id'],as_of=r['as_of'],side=r['side'],method=name,
                                     shown=len(v['rows']),passed_rows=v['passed_rows'],
                                     **{k:first.get(k) for k in fields[7:]}))
    digest=sha256((out/'queries_PRIVATE.json').read_bytes()).hexdigest()
    dump(out/'summary.json',dict(method=METHOD,cohorts=summary,result_digest=digest,similarity_accuracy=None))
    dump(out/'manifest_PRIVATE.json',dict(inputs=inputs,limits=LIMITS,runs=RUNS,method=METHOD,
                                           event_tail_bars=6,event_reference_bars=20,event_buffer_atr='.1',
                                           tail_neutral_atr='.5',parameters_calibrated=False,result_digest=digest))
    dump(out/'timings.json',timings)
    dump(out/'validation.json',dict(status='PASS',queries=51,baseline_top_fives_exact=51,
                                      displayed_pairs_checked=checked,temporal_group_violations=0,
                                      sensitivity_nested=True,ablation_nested=True,similarity_accuracy=None))
    (out/'notes.txt').write_text('Frozen exploratory A/B: existing 41 monthly queries plus 10 disjoint broker days.\n'
                               'Thresholds chosen before execution, not calibrated. No human accuracy or profit claim.\n'
                               f'Result digest {digest}\n',encoding='utf-8')
    print(json.dumps(dict(status='PASS',queries=51,result_digest=digest)),flush=True)


if __name__=='__main__':main()
