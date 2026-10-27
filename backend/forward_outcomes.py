"""Historical post-reference windows, never a similarity feature or prediction.

The offline builder binds the same private cases/profiles/BID CSV by SHA-256.
Runtime serves only complete horizons already known at the query cutoff.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
from hashlib import sha256
import csv,json
from pathlib import Path
from threading import RLock

SOURCE='HistData BID'
BASIS='NEXT_COMPLETE_5M_OPEN'
METHOD='case_forward_outcomes_v2'
HORIZONS=(5,30,60)
PRICES=('open','high','low','close')
REASONS={
    'AVAILABLE':'完整歷史觀察區間已可用。',
    'GAPPED_WINDOW':'觀察區間有缺棒或超出來源範圍，沒有補棒或跨缺口計算。',
    'INCOMPLETE_MINUTES':'觀察區間含未完整觀測五分鐘的K棒。',
    'INVALID_OHLC':'觀察區間的價格或K棒格式無效。',
    'INVALID_REFERENCE':'歷史方向或參考時點無效。',
    'NOT_YET_KNOWN':'這段歷史觀察期間在本次查詢截止時尚未完整發生。',
    'INVALID_QUERY_TIME':'缺少有效的查詢截止時間。',
    'MISSING':'尚未建立本機歷史後續行情側檔。',
    'STALE':'歷史後續側檔與目前案例、參考盤面或來源行情不一致，請重建側檔。',
    'INVALID':'歷史後續側檔格式或驗證資料無效。',
    'CASE_NOT_FOUND':'這個案例沒有可用的歷史後續紀錄。',
}


def _text(number):
    value=format(number,'f')
    if '.' in value:value=value.rstrip('0').rstrip('.')
    return '0' if value in ('-0','') else value


def _horizon(status,minutes,anchor_time=None):
    return dict(status=status,reason=REASONS[status],minutes=minutes,
        end_time=anchor_time+minutes*60 if anchor_time is not None else None,
        bars=[],change_pct=None,mae_pct=None,mfe_pct=None)


def _unavailable(status,*,case_as_of=None,side=None,anchor_time=None):
    return dict(status=status,reason=REASONS[status],case_as_of=case_as_of,
        anchor_time=anchor_time,anchor_price=None,side=side,source=SOURCE,basis=BASIS,
        horizons={str(n):_horizon(status,n,anchor_time) for n in HORIZONS})


def _prices(bar):
    values={name:Decimal(str(bar[name])) for name in PRICES}
    if (any(not v.is_finite() or v<=0 for v in values.values()) or
        not values['low']<=min(values['open'],values['close'])<=max(values['open'],values['close'])<=values['high']):
        raise ValueError('invalid price')
    return values


def _measure(side,anchor_time,rows,minutes):
    expected=[anchor_time+i*300 for i in range(minutes//5)]
    if len(rows)!=len(expected) or [b.get('time') for b in rows]!=expected:
        return _horizon('GAPPED_WINDOW',minutes,anchor_time)
    if any(type(b.get('observed_minutes')) is not int or b['observed_minutes']!=5 for b in rows):
        return _horizon('INCOMPLETE_MINUTES',minutes,anchor_time)
    try:
        prices=[_prices(b) for b in rows]
    except (InvalidOperation,ValueError,TypeError,KeyError):
        return _horizon('INVALID_OHLC',minutes,anchor_time)
    anchor=prices[0]['open'];sign=Decimal(1 if side=='BUY' else -1)
    low=min(p['low'] for p in prices);high=max(p['high'] for p in prices)
    change=(prices[-1]['close']/anchor-1)*100*sign
    mae=max(Decimal(0),(anchor-low if side=='BUY' else high-anchor)/anchor*100)
    mfe=max(Decimal(0),(high-anchor if side=='BUY' else anchor-low)/anchor*100)
    return dict(status='AVAILABLE',reason=REASONS['AVAILABLE'],minutes=minutes,end_time=anchor_time+minutes*60,
        bars=[dict(time=b['time'],observed_minutes=5,**{k:_text(p[k]) for k in PRICES}) for b,p in zip(rows,prices)],
        change_pct=_text(change),mae_pct=_text(mae),mfe_pct=_text(mfe))


def build_case_outcome(side,case_as_of,rows):
    """Measure fixed horizons from the first full five-minute bar after entry.

    Rows may include surrounding market data; no entry partial bar is included.
    Percentages are side-adjusted, with MAE/MFE reported as nonnegative sizes.
    """
    if side not in ('BUY','SELL') or type(case_as_of) is not int or case_as_of<0:
        return _unavailable('INVALID_REFERENCE')
    anchor=(case_as_of+299)//300*300
    value=_unavailable('GAPPED_WINDOW',case_as_of=case_as_of,side=side,anchor_time=anchor)
    if not isinstance(rows,list) or any(not isinstance(b,dict) for b in rows):
        return _unavailable('INVALID_OHLC',case_as_of=case_as_of,side=side,anchor_time=anchor)
    selected=[b for b in rows if type(b.get('time')) is int and anchor<=b['time']<anchor+3600]
    selected.sort(key=lambda b:b['time'])
    if len({b['time'] for b in selected})!=len(selected):
        return _unavailable('INVALID_OHLC',case_as_of=case_as_of,side=side,anchor_time=anchor)
    try:
        if selected and selected[0]['time']==anchor:value['anchor_price']=_text(_prices(selected[0])['open'])
    except (InvalidOperation,TypeError,ValueError,KeyError):pass
    for minutes in HORIZONS:
        window=[b for b in selected if b['time']<anchor+minutes*60]
        value['horizons'][str(minutes)]=_measure(side,anchor,window,minutes)
    if any(h['status']=='AVAILABLE' for h in value['horizons'].values()):
        value.update(status='AVAILABLE',reason=REASONS['AVAILABLE'])
    else:
        value.update(status=value['horizons']['5']['status'],reason=value['horizons']['5']['reason'])
    return value


def _reference(root,path):
    path=Path(path).resolve()
    if not path.is_relative_to(root) or not path.is_file():raise ValueError('invalid source')
    return dict(path=str(path.relative_to(root)).replace('\\','/'),sha256=sha256(path.read_bytes()).hexdigest())


def build_sidecar(private_root,output_path=None):
    """Offline-only, deterministic stream of the validated source CSV."""
    from .candidate_sidecar import load_candidate_sidecar
    root=Path(private_root).resolve();casepath=root/'cases.json';profilepath=root/'case_candidate_market_profiles.json'
    profiles,status=load_candidate_sidecar(casepath,profilepath,root)
    if status!='READY':raise ValueError('CANDIDATE_PROFILES_'+status)
    metadata=json.loads(profilepath.read_text(encoding='utf8'))
    barsref=metadata['inputs']['bars'];barpath=(root/barsref['path']).resolve()
    if _reference(root,barpath)!=dict(path=str(Path(barsref['path'])).replace('\\','/'),sha256=barsref['sha256']):
        raise ValueError('SOURCE_BARS_CHANGED')
    cases=json.loads(casepath.read_text(encoding='utf8'))['cases'];sides={c['id']:c.get('side') for c in cases}
    anchors={case_id:(p['as_of']+299)//300*300 for case_id,p in profiles.items()}
    wanted={anchor+i*300 for anchor in anchors.values() for i in range(12)}
    selected={};previous=-1;row_count=0
    with barpath.open(encoding='utf-8-sig',newline='') as stream:
        for row in csv.DictReader(stream):
            dt=datetime.fromisoformat(row['timestamp'].replace('Z','+00:00'))
            if dt.tzinfo is None or dt.utcoffset().total_seconds()!=0:raise ValueError('SOURCE_TIME_NOT_UTC')
            stamp=int(dt.timestamp())
            if stamp<=previous or stamp%300:raise ValueError('SOURCE_TIME_NOT_SORTED_UNIQUE')
            previous=stamp;row_count+=1
            if stamp not in wanted:continue
            try:observed=int(row['observed_minutes'])
            except (ValueError,TypeError,KeyError):observed=None
            if row.get('source')!='HistData' or row.get('quote_side')!='BID':raise ValueError('SOURCE_PRICE_BASIS_CHANGED')
            selected[stamp]=dict(time=stamp,observed_minutes=observed,**{k:row.get(k) for k in PRICES})
    records={case_id:build_case_outcome(sides[case_id],p['as_of'],
        [selected[t] for t in range(anchors[case_id],anchors[case_id]+3600,300) if t in selected])
        for case_id,p in sorted(profiles.items())}
    counts={str(n):dict(Counter(r['horizons'][str(n)]['status'] for r in records.values())) for n in HORIZONS}
    payload=dict(method=METHOD,source=SOURCE,basis=BASIS,alignment='PROJECT_REFERENCE',clock_status='UNKNOWN',
        inputs={'cases':_reference(root,casepath),'profiles':_reference(root,profilepath),'bars':_reference(root,barpath)},
        counts=counts,total_cases=len(records),source_rows=row_count,profiles=records)
    destination=Path(output_path).resolve() if output_path else root/'case_forward_outcomes.json'
    if not destination.is_relative_to(root):raise ValueError('PRIVATE_OUTPUT_REQUIRED')
    if destination in (casepath,profilepath,barpath):raise ValueError('SOURCE_OVERWRITE_FORBIDDEN')
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n',encoding='utf8')
    return dict(path=str(destination),total_cases=len(records),counts=counts,source_rows=row_count,sha256=sha256(destination.read_bytes()).hexdigest())


class HistoricalOutcomeStore:
    """Lazy immutable data cache; invalidate on any source/sidecar stat change."""
    def __init__(self,private_root):
        self.root=Path(private_root).resolve();self.path=self.root/'case_forward_outcomes.json'
        self._paths=[self.path,self.root/'cases.json',self.root/'case_candidate_market_profiles.json']
        self._signature=None;self._records={};self._meta={};self._status='MISSING';self._lock=RLock()

    def _stat(self):
        values=[]
        for path in self._paths:
            try:s=path.stat();values.append((str(path),s.st_size,s.st_mtime_ns))
            except OSError:values.append((str(path),None,None))
        return tuple(values)

    def _load(self):
        self._records={};self._meta={};self._status='INVALID'
        if not self.path.is_file():self._status='MISSING';return
        try:
            payload=json.loads(self.path.read_text(encoding='utf8'))
            if payload.get('method')!=METHOD or set(payload['inputs'])!={'cases','profiles','bars'}:return
            paths={}
            for name,ref in payload['inputs'].items():
                if not isinstance(ref,dict) or set(ref)!={'path','sha256'} or not isinstance(ref['path'],str):return
                path=(self.root/ref['path']).resolve()
                if not path.is_relative_to(self.root):return
                if name in ('cases','profiles') and path!=(self.root/('cases.json' if name=='cases' else 'case_candidate_market_profiles.json')).resolve():return
                paths[name]=path
            self._paths=[self.path,*paths.values()]
            for name,path in paths.items():
                if not path.is_file():return
                if sha256(path.read_bytes()).hexdigest()!=payload['inputs'][name]['sha256']:self._status='STALE';return
            cases=json.loads(paths['cases'].read_text(encoding='utf8'))['cases']
            if len({c['id'] for c in cases})!=len(cases):return
            sides={c['id']:c.get('side') for c in cases}
            profiles=json.loads(paths['profiles'].read_text(encoding='utf8'))
            if profiles.get('input_cases_sha256')!=payload['inputs']['cases']['sha256']:return
            if profiles['inputs']['bars']!=payload['inputs']['bars']:return
            self._meta={k:(sides[k],v['as_of']) for k,v in profiles['profiles'].items() if k in sides}
            records=payload['profiles']
            if not isinstance(records,dict) or not set(records)<=set(self._meta):return
            self._records=records;self._status='READY'
        except (OSError,KeyError,ValueError,TypeError,AttributeError):return

    def _valid_record(self,case_id,record):
        try:
            side,as_of=self._meta[case_id]
            if (record['side']!=side or record['case_as_of']!=as_of or type(as_of) is not int or as_of<0
                or record['anchor_time']!=(as_of+299)//300*300 or record['basis']!=BASIS or record['source']!=SOURCE
                or set(record['horizons'])!={str(n) for n in HORIZONS}):return False
            if record['anchor_price'] is not None:
                p=Decimal(record['anchor_price'])
                if not p.is_finite() or p<=0:return False
            any_available=False
            for n in HORIZONS:
                h=record['horizons'][str(n)]
                if h['minutes']!=n or h['end_time']!=record['anchor_time']+n*60:return False
                if h['status']=='AVAILABLE':
                    measured=_measure(side,record['anchor_time'],h['bars'],n)
                    if measured!=h or h['bars'][0]['open']!=record['anchor_price']:return False
                    any_available=True
                elif h['status'] not in ('GAPPED_WINDOW','INCOMPLETE_MINUTES','INVALID_OHLC') or h['bars'] or any(h[k] is not None for k in ('change_pct','mae_pct','mfe_pct')):return False
            expected='AVAILABLE' if any_available else record['horizons']['5']['status']
            return record['status']==expected
        except (KeyError,TypeError,ValueError,ArithmeticError):return False

    def get(self,case_id,query_as_of):
        if not isinstance(case_id,str) or not case_id:return _unavailable('CASE_NOT_FOUND')
        with self._lock:
            signature=self._stat()
            if signature!=self._signature:
                self._load();self._signature=self._stat()
            if self._status!='READY':return _unavailable(self._status)
            original=self._records.get(case_id)
            if original is None:return _unavailable('CASE_NOT_FOUND')
            if not self._valid_record(case_id,original):return _unavailable('INVALID')
            value=deepcopy(original)
        valid_time=type(query_as_of) in (int,float) and query_as_of>=0
        if valid_time:
            try:valid_time=Decimal(str(query_as_of)).is_finite()
            except (ValueError,ArithmeticError):valid_time=False
        for n in HORIZONS:
            h=value['horizons'][str(n)]
            if not valid_time:value['horizons'][str(n)]=_horizon('INVALID_QUERY_TIME',n,value['anchor_time'])
            elif h['end_time']>query_as_of:value['horizons'][str(n)]=_horizon('NOT_YET_KNOWN',n,value['anchor_time'])
        if not valid_time or value['anchor_time']>query_as_of:value['anchor_price']=None
        available=any(h['status']=='AVAILABLE' for h in value['horizons'].values())
        status='AVAILABLE' if available else value['horizons']['5']['status']
        value.update(status=status,reason=REASONS[status])
        return value
