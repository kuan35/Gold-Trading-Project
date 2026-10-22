"""Repeat the unchanged dual-path retriever on ten disjoint broker days."""
from __future__ import annotations
import argparse
import csv
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

PRODUCT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PRODUCT))
from scripts.fetch_ctrader_review_days import sample_clocks,OUTPUT
from backend.dual_path_retrieval import DualPathIndex,profile_from_dual_frames,METHOD
from backend.compact_market import describe_compact
from backend.candidate_sidecar import load_candidate_sidecar


def dump(path,value):path.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2),encoding='utf-8')
def tw(clock):return datetime.fromtimestamp(clock,ZoneInfo('Asia/Taipei')).strftime('%Y-%m-%d %H:%M')


def selected(packet):
    if packet['status']!='COMPLETE':raise ValueError('INCOMPLETE_FETCH')
    records=sorted(packet['records'],key=lambda r:r['as_of'])
    if [r['as_of'] for r in records]!=sample_clocks():raise ValueError('UNEXPECTED_SAMPLE_DATES')
    previous=None;signatures={iv:set() for iv in ('5m','1h')};chosen=[];excluded=[]
    for r in records:
        clock=r['as_of'];number=len(chosen)+1;side='BUY' if number%2 else 'SELL'
        frames={iv:[b for b in r['bars'][iv] if b['time']+seconds<=clock] for iv,seconds in [('5m',300),('1h',3600)]}
        profile=profile_from_dual_frames(frames['5m'],frames['1h'],clock,packet.get('trading_schedule'))
        if profile['status']!='candidate_only':
            excluded.append(dict(as_of=clock,reason=profile.get('reason','')));continue
        desc=describe_compact(profile,side)
        if previous and previous['window_end']>=desc['window_start']:raise ValueError('QUERY_WINDOWS_OVERLAP')
        previous=desc
        for iv in ('5m','1h'):
            closes=tuple(b['close'] for b in profile['pre_entry_bars'][iv])
            if closes in signatures[iv]:raise ValueError('DUPLICATE_PRICE_PATH')
            signatures[iv].add(closes)
        chosen.append(dict(sample=f'D{number:02}',as_of=clock,side=side,profile=profile,
                   query_description=desc,sample_kind='broker_historical_day_replay'))
    if len(chosen)!=10:raise ValueError('EXPECTED_TEN_COMPLETE_DAYS: '+str(excluded))
    return chosen,excluded


def queries(packet):return iter(selected(packet)[0])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=OUTPUT)
    out=parser.parse_args().output.resolve()
    if not out.is_relative_to((PRODUCT/'private').resolve()):raise ValueError('PRIVATE_OUTPUT_REQUIRED')
    out.mkdir(parents=True,exist_ok=True)
    source=OUTPUT/'broker_days_PRIVATE.json';packet=json.loads(source.read_text(encoding='utf-8'))
    files=[source,PRODUCT/'private/cases.json',PRODUCT/'private/case_candidate_market_profiles.json',
           PRODUCT/'backend/dual_path_retrieval.py',PRODUCT/'backend/compact_market.py',
           PRODUCT/'backend/live_candidate_profile.py',PRODUCT/'backend/candidate_profile.py',
           PRODUCT/'backend/candidate_bars.py',PRODUCT/'scripts/fetch_ctrader_review_days.py',
           PRODUCT/'research/path_similarity_experiment.py',PRODUCT/'docs/distinct_day_sampling_20261021.md',Path(__file__)]
    inputs={p.relative_to(PRODUCT).as_posix():sha256(p.read_bytes()).hexdigest() for p in files}
    cases=json.loads(files[1].read_text(encoding='utf-8'))['cases']
    profiles,status=load_candidate_sidecar(files[1],files[2],PRODUCT/'private')
    if status!='READY':raise ValueError('INVALID_HISTORICAL_INDEX: '+status)
    print('building unchanged dual-path index',flush=True)
    index=DualPathIndex(cases,profiles)
    import numpy as np
    from research.path_similarity_experiment import order_candidates
    records=[];pairs=0
    selected_queries,excluded=selected(packet)
    for q in selected_queries:
        result=index.retrieve(q['profile'],q['side']);desc=q['query_description']
        if len(result['cases'])!=5:raise ValueError(q['sample']+' fewer than five eligible cases')
        pool,_=index.eligible(q['profile'],q['side']);seen=set();times=set()
        for c in result['cases']:
            original=index.lookup[c['id']];d=index.descriptions[c['id']]
            assert original['side']==q['side'] and original['available_at']<=q['as_of']
            assert d['window_end']<=desc['window_start']
            assert c['group'] not in seen and (d['end_5m'],d['end_1h']) not in times
            seen.add(c['group']);times.add((d['end_5m'],d['end_1h']));pairs+=1
        def path(p,iv):
            bars=p['pre_entry_bars'][iv];base=float(bars[0]['close'])
            return np.array([(float(b['close'])/base-1)*100 for b in bars])
        distances={iv:np.array([float(np.sqrt(np.mean((path(q['profile'],iv)-path(profiles[c['id']],iv))**2))) for c in pool]) for iv in ('5m','1h')}
        expected=order_candidates(pool,index.descriptions,desc,distances['5m'],distances['1h'],structure_first=True)
        assert [r['case_id'] for r in expected]==[c['id'] for c in result['cases']]
        for c in result['cases']:
            at=next(i for i,r in enumerate(pool) if r['id']==c['id'])
            assert abs(c['path_distance_pct']-distances['5m'][at])<1e-10
            assert abs(c['hour_path_distance_pct']-distances['1h'][at])<1e-10
        first=result['cases'][0]
        records.append(dict(**q,result=result,matched_profile=profiles[first['id']],matched_description=index.descriptions[first['id']]))
        print(q['sample']+' '+tw(q['as_of'])+' '+q['side']+' -> '+first['id'],flush=True)
    payload=dict(method=METHOD,capture_kind='broker_historical_day_replay',fetched_at_utc=packet['fetched_at_utc'],sample_count=10,excluded_query_days=excluded,records=records)
    dump(out/'samples_PRIVATE.json',payload)
    digest=sha256((out/'samples_PRIVATE.json').read_bytes()).hexdigest()
    firsts=[r['result']['cases'][0] for r in records]
    summary=dict(samples=10,buy=5,sell=5,distinct_days=10,nonoverlapping_query_windows=True,
        distinct_top_one_cases=len({c['id'] for c in firsts}),
        same_structure_top_one=sum(c['structure_match'] for c in firsts),
        mean_five_path_distance=sum(c['path_distance_pct'] for c in firsts)/10,
        mean_hour_path_distance=sum(c['hour_path_distance_pct'] for c in firsts)/10,
        mean_volatility_ratio=sum(c['volatility_ratio'] for c in firsts)/10,
        query_structures=sorted({r['query_description']['structure'] for r in records}),
        result_digest=digest,similarity_accuracy=None)
    dump(out/'summary.json',summary);dump(out/'manifest_PRIVATE.json',dict(inputs=inputs,result_digest=digest))
    dump(out/'validation.json',dict(status='PASS',query_dates=10,query_window_overlap=0,
        distinct_five_and_hour_close_paths=10,checked_pairs=pairs,offline_top_five_matches=10,temporal_or_group_violations=0,orders_sent=0))
    with (out/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        keys=['sample','query_taiwan','side','case_id','reference_taiwan','structure_same','five_path_pp','hour_path_pp','volatility_ratio']
        writer=csv.DictWriter(stream,fieldnames=keys);writer.writeheader()
        for r in records:
            c=r['result']['cases'][0]
            writer.writerow(dict(sample=r['sample'],query_taiwan=tw(r['as_of']),side=r['side'],case_id=c['id'],reference_taiwan=tw(r['matched_description']['as_of']),structure_same=c['structure_match'],five_path_pp=c['path_distance_pct'],hour_path_pp=c['hour_path_distance_pct'],volatility_ratio=c['volatility_ratio']))
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
