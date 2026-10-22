"""Ten recent broker candle clocks, fixed alternating sides, no order calls."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

PRODUCT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PRODUCT))
from backend.candidate_sidecar import load_candidate_sidecar
from backend.dual_path_retrieval import DualPathIndex,profile_from_dual_frames,METHOD
from backend.compact_market import describe_compact

OUTPUT=PRODUCT/'private/live_dual_path_samples_20261021'


def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2),encoding='utf-8')


def selected_queries(snapshot):
    """No fake historical tick: clock comes from the returned closed candles."""
    source=datetime.fromisoformat(snapshot['quote']['source_time_utc'])
    if source.tzinfo is None:raise ValueError('source clock missing UTC offset')
    ceiling=int(source.timestamp())//300*300
    five=snapshot['bars']['5m'];hour=snapshot['bars']['1h']
    clocks=sorted({b['time']+300 for b in five if b['time']+300<=ceiling})[-10:]
    if len(clocks)!=10:raise ValueError('fewer than ten distinct closed-bar clocks')
    schedule=(snapshot.get('symbol') or {}).get('trading_schedule')
    for number,clock in enumerate(clocks,1):
        frames={iv:[b for b in raw if b['time']+seconds<=clock]
                for iv,raw,seconds in [('5m',five,300),('1h',hour,3600)]}
        profile=profile_from_dual_frames(frames['5m'],frames['1h'],clock,schedule)
        if profile['status']!='candidate_only':raise ValueError(f'Q{number:02} unavailable: '+profile.get('reason',''))
        yield dict(sample=f'Q{number:02}',side='BUY' if number%2 else 'SELL',as_of=clock,
                   sample_kind='recent_broker_closed_bar_replay',profile=profile)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=OUTPUT)
    args=parser.parse_args();out=args.output.resolve()
    if not out.is_relative_to((PRODUCT/'private').resolve()):raise ValueError('private output required')
    out.mkdir(parents=True,exist_ok=True)
    snapshot_path=OUTPUT/'broker_snapshot_PRIVATE.json'
    snapshot=json.loads(snapshot_path.read_text(encoding='utf-8-sig'))
    if snapshot.get('connection_status')!='CONNECTED' or snapshot['quote']['status']!='CURRENT':
        raise ValueError('snapshot was not captured from a fresh broker connection')
    # Refuse accidental persistence of credentials or account state in a market packet.
    def check_keys(value):
        if isinstance(value,dict):
            assert not ({str(k).lower() for k in value}&{'account','account_id','client_secret','access_token','refresh_token','token','positions','pending_orders'})
            for child in value.values():check_keys(child)
        elif isinstance(value,list):
            for child in value:check_keys(child)
    check_keys(snapshot)
    files=[snapshot_path,PRODUCT/'private/cases.json',PRODUCT/'private/case_candidate_market_profiles.json',
           PRODUCT/'backend/dual_path_retrieval.py',PRODUCT/'backend/compact_market.py',
           PRODUCT/'backend/live_candidate_profile.py',PRODUCT/'backend/candidate_profile.py',
           PRODUCT/'backend/candidate_bars.py',PRODUCT/'docs/live_dual_path_sampling_20261021.md',Path(__file__)]
    inputs={p.relative_to(PRODUCT).as_posix():sha256(p.read_bytes()).hexdigest() for p in files}
    profiles,status=load_candidate_sidecar(files[1],files[2],PRODUCT/'private')
    if status!='READY':raise RuntimeError('historical profile integrity '+status)
    cases=json.loads(files[1].read_text(encoding='utf-8'))['cases']
    print('building immutable dual-path index',flush=True)
    index=DualPathIndex(cases,profiles)
    records=[];checked=0;offline_matches=0
    from research.path_similarity_experiment import order_candidates
    import numpy as np
    for query in selected_queries(snapshot):
        result=index.retrieve(query['profile'],query['side'])
        if not result['cases']:raise RuntimeError(query['sample']+' found no comparable case')
        q=describe_compact(query['profile'],query['side']);seen=set();times=set()
        for candidate in result['cases']:
            c=index.lookup[candidate['id']];d=index.descriptions[c['id']]
            assert c['side']==query['side'] and c['available_at']<=query['as_of']
            assert d['window_end']<=q['window_start'] and d['as_of']<=query['as_of']
            assert c['group'] not in seen and (d['end_5m'],d['end_1h']) not in times
            seen.add(c['group']);times.add((d['end_5m'],d['end_1h']));checked+=1
        # Same pool, independent NumPy distance accumulation + frozen offline sorter.
        pool,_=index.eligible(query['profile'],query['side'])
        def path(p,iv):
            bars=p['pre_entry_bars'][iv];base=float(bars[0]['close'])
            return np.array([(float(b['close'])/base-1)*100 for b in bars])
        distances={iv:np.array([float(np.sqrt(np.mean((path(query['profile'],iv)-path(profiles[c['id']],iv))**2)))
                                for c in pool]) for iv in ('5m','1h')}
        expected=order_candidates(pool,index.descriptions,q,distances['5m'],distances['1h'],structure_first=True)
        assert [r['case_id'] for r in expected]==[c['id'] for c in result['cases']],query['sample']
        offline_matches+=1
        for row in result['cases']:
            at=next(i for i,c in enumerate(pool) if c['id']==row['id'])
            assert abs(row['path_distance_pct']-distances['5m'][at])<1e-10
            assert abs(row['hour_path_distance_pct']-distances['1h'][at])<1e-10
        first=result['cases'][0]
        record=dict(**query,result=result,query_description=q,
                    matched_profile=profiles[first['id']],matched_description=index.descriptions[first['id']])
        records.append(record)
        print(query['sample']+' '+query['side']+' -> '+first['id'],flush=True)
    payload=dict(method=METHOD,capture_kind=snapshot['capture_kind'],captured_at_utc=snapshot['captured_at_utc'],
                 broker_quote_source_time=snapshot['quote']['source_time_utc'],sample_count=len(records),
                 query_start=records[0]['as_of'],query_end=records[-1]['as_of'],records=records)
    dump(out/'samples_PRIVATE.json',payload)
    digest=sha256((out/'samples_PRIVATE.json').read_bytes()).hexdigest()
    dump(out/'manifest_PRIVATE.json',dict(inputs=inputs,result_digest=digest))
    firsts=[r['result']['cases'][0] for r in records]
    summary=dict(method=METHOD,samples=len(records),buy=5,sell=5,checked_pairs=checked,
                 same_structure_top_one=sum(c['structure_match'] for c in firsts),
                 distinct_top_one_cases=len({c['id'] for c in firsts}),
                 distinct_hourly_query_windows=len({r['query_description']['end_1h'] for r in records}),
                 mean_five_path_distance=sum(c['path_distance_pct'] for c in firsts)/len(firsts),
                 mean_hour_path_distance=sum(c['hour_path_distance_pct'] for c in firsts)/len(firsts),
                 mean_volatility_ratio=sum(c['volatility_ratio'] for c in firsts)/len(firsts),
                 result_digest=digest,similarity_accuracy=None)
    dump(out/'summary.json',summary)
    dump(out/'validation.json',dict(status='PASS',samples=10,checked_pairs=checked,offline_top_five_matches=offline_matches,
                                    source_clock_and_maturity_violations=0,sensitive_snapshot_keys=0))
    with (out/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        keys=['sample','query_taiwan','side','case_id','reference_taiwan','structure_same','five_path_pp','hour_path_pp','volatility_ratio']
        writer=csv.DictWriter(stream,fieldnames=keys);writer.writeheader()
        from zoneinfo import ZoneInfo
        def tw(stamp):return datetime.fromtimestamp(stamp,ZoneInfo('Asia/Taipei')).strftime('%Y-%m-%d %H:%M')
        for r in records:
            c=r['result']['cases'][0]
            writer.writerow(dict(sample=r['sample'],query_taiwan=tw(r['as_of']),side=r['side'],case_id=c['id'],
                                 reference_taiwan=tw(r['matched_description']['as_of']),structure_same=c['structure_match'],
                                 five_path_pp=c['path_distance_pct'],hour_path_pp=c['hour_path_distance_pct'],volatility_ratio=c['volatility_ratio']))
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
