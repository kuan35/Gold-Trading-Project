"""Validate downloaded native bars and build a separate research index.

The production HistData/candidate profiles are never modified. Native OHLC and
tick volume always stay together under their original provider identity.
"""
import bisect,csv,hashlib,json
from collections import Counter,defaultdict
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
from backend.candidate_sidecar import load_candidate_sidecar
from backend.forward_outcomes import _prices
from scripts.fetch_ctrader_history_volume import plan,task_key,PERIODS
from backend.volume_paths import volume_folder

ROOT=Path(__file__).resolve().parents[1]


def frame(index,times,asof,interval):
    span=PERIODS[interval][1];count=60 if interval=='5m' else 20
    end=bisect.bisect_right(times,asof-span)
    baseline=times[max(0,end-max(count,21)):end]
    chosen=baseline[-count:]
    ready=len(chosen)==count and asof-(chosen[-1]+span)<span
    volumes=[index[t]['volume'] for t in baseline[-21:]]
    mean=sum(volumes[:-1])/Decimal(20) if len(volumes)==21 else None
    ratio=Decimal(volumes[-1])/mean if mean is not None and mean>0 else None
    return dict(status='AVAILABLE' if ready else 'INSUFFICIENT_OR_STALE',times=chosen,
      last_volume=volumes[-1] if volumes else None,prior20_mean=format(mean,'f') if mean is not None else None,
      relative_volume_ratio=format(ratio,'f') if ratio is not None else None,
      volume_basis='broker_native_tick_count',ratio_basis='LAST_CLOSED_OVER_PREVIOUS_20_AVAILABLE_BARS',
      gap_count=sum(b-a!=span for a,b in zip(baseline[-21:],baseline[-21:][1:])),
      window_gap_count=sum(b-a!=span for a,b in zip(chosen,chosen[1:])),
      bars_closed_before_asof=all(t+span<=asof for t in chosen))


def main():
    private=ROOT/'private';folder=volume_folder(private)
    meta=json.loads((private/'case_candidate_market_profiles.json').read_text(encoding='utf-8'))
    wanted=plan(meta['profiles']);indices={iv:{} for iv in PERIODS};identity=None;missing=[];hashes={}
    for task in wanted:
        path=folder/(task_key(task)+'.json')
        if not path.exists():missing.append(task_key(task));continue
        raw=path.read_bytes();data=json.loads(raw)
        if any(data[k]!=task[k] for k in ('interval','start','end')) or data.get('volume_basis')!='broker_native_tick_count':raise ValueError('CHUNK_METADATA_MISMATCH')
        if identity is None:identity=data['source_key']
        if data['source_key']!=identity:raise ValueError('MIXED_SOURCE_IDENTITY')
        if data['status'] not in ('AVAILABLE','EMPTY') or (data['status']=='EMPTY')!= (not data['bars']):raise ValueError('CHUNK_STATUS_MISMATCH')
        index=indices[task['interval']];previous=-1;span=PERIODS[task['interval']][1]
        for b in data['bars']:
            t=b['time']
            if type(t) is not int or t%span or not task['start']<=t<task['end'] or t<=previous:raise ValueError('INVALID_NATIVE_TIME')
            if type(b['volume']) is not int or b['volume']<0:raise ValueError('INVALID_NATIVE_VOLUME')
            _prices(b);previous=t
            if t in index and index[t]!=b:raise ValueError('CONFLICTING_NATIVE_BAR')
            index[t]=b
        hashes[path.name]=hashlib.sha256(raw).hexdigest()
    if missing:
        print(json.dumps(dict(status='INCOMPLETE_DOWNLOAD',missing_chunks=len(missing),expected_chunks=len(wanted))))
        return 2
    profiles,status=load_candidate_sidecar(private/'cases.json',private/'case_candidate_market_profiles.json',private)
    if status!='READY':raise ValueError('INVALID_REFERENCE_PROFILES')
    times={iv:sorted(index) for iv,index in indices.items()};records={};counts=Counter();by_year=defaultdict(Counter)
    for ident,p in profiles.items():
        frames={iv:frame(indices[iv],times[iv],p['as_of'],iv) for iv in PERIODS}
        ready=all(f['status']=='AVAILABLE' for f in frames.values())
        counts['profiles']+=1;counts['both_timeframes_ready']+=ready
        year=str(datetime.fromtimestamp(p['as_of'],timezone.utc).year)
        by_year[year]['profiles']+=1;by_year[year]['both_timeframes_ready']+=ready
        for iv,f in frames.items():
            counts[iv+'_ready']+=f['status']=='AVAILABLE'
            counts[iv+'_relative_volume_ready']+=f['status']=='AVAILABLE' and f['relative_volume_ratio'] is not None
            counts[iv+'_ready_with_window_gaps']+=f['status']=='AVAILABLE' and f['window_gap_count']>0
            counts[iv+'_ready_with_volume_baseline_gaps']+=f['status']=='AVAILABLE' and f['gap_count']>0
        records[ident]=dict(as_of=p['as_of'],source_key=identity,source='ctrader_demo_native',alignment='PROJECT_REFERENCE',
            clock_status='UNKNOWN',production_enabled=False,frames=frames)
    for iv,index in indices.items():
        path=folder/('native_'+iv+'.csv');temp=path.with_suffix('.tmp')
        with temp.open('w',encoding='utf-8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=['time','open','high','low','close','volume']);writer.writeheader()
            for t in times[iv]:writer.writerow(index[t])
        temp.replace(path)
    target=folder/'case_volume_references_PRIVATE.json';temp=target.with_suffix('.tmp')
    temp.write_text(json.dumps(dict(source_key=identity,chunk_hashes=hashes,profiles_sha256=hashlib.sha256((private/'case_candidate_market_profiles.json').read_bytes()).hexdigest(),
       production_enabled=False,cases=records),separators=(',',':')),encoding='utf-8');temp.replace(target)
    summary=dict(status='COMPLETE',downloaded_chunks=len(wanted),native_bars={iv:len(index) for iv,index in indices.items()},
        product_candidates=len(json.loads((private/'cases.json').read_text(encoding='utf-8'))['cases']),
        counts=dict(counts),by_reference_year={y:dict(c) for y,c in sorted(by_year.items())},
        production_changed=False,source='cTrader DEMO native',volume_basis='broker_native_tick_count',
        note='新OHLC與量一起保存；沒有把券商tick量直接貼入HistData盤面。相對量若跨休市缺口會標gap_count；原始時鐘仍未獨立核實。')
    (folder/'download_summary_PRIVATE.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
