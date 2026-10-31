"""Private reference execution bars, bound to source hashes and frozen per query."""
import csv,json,hashlib,math
from datetime import datetime
from pathlib import Path
from threading import RLock
from .candidate_sidecar import load_candidate_sidecar
from .execution_overlay import execution_overlay
from .forward_outcomes import _prices
from .trade_result import trade_result

# Display/performance bound, not a similarity threshold (60 calendar days).
MAX_HOLDING_SLOTS=60*24*12


def _window(a,b,*,full):
    slots=(b-a)//300+1
    if slots<=0:raise ValueError('INVALID_REFERENCE')
    if full and slots<=MAX_HOLDING_SLOTS:
        return list(range(a,b+300,300)),[],'FULL_HOLDING'
    if not full and b-a<288*300:
        return list(range(a,b+300,300)),[],'CONTIGUOUS'
    return [a],list(range(max(a,b-3300),b+300,300)),'SEPARATE_CLOSE'


def build(root):
    """Build v2 beside v1. Keep only observed, valid source bars; never fill gaps."""
    root=Path(root).resolve();cp=root/'cases.json';pp=root/'case_candidate_market_profiles.json'
    profiles,status=load_candidate_sidecar(cp,pp,root)
    if status!='READY':raise ValueError('INVALID_PROFILES_'+status)
    meta=json.loads(pp.read_text(encoding='utf-8'));bp=(root/meta['inputs']['bars']['path']).resolve()
    if not bp.is_relative_to(root):raise ValueError('PRIVATE_SOURCE_REQUIRED')
    records={};wanted=set()
    for ident,p in sorted(profiles.items()):
        a,b=p['reference_open_utc']//300*300,p['reference_close_utc']//300*300
        stamps,close,mode=_window(a,b,full=True)
        records[ident]={'times':stamps,'close_times':close,'mode':mode}
        wanted.update(stamps);wanted.update(close)
    bars={};previous=-1
    with bp.open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            date=datetime.fromisoformat(r['timestamp'].replace('Z','+00:00'))
            if date.tzinfo is None or date.utcoffset().total_seconds()!=0:raise ValueError('NON_UTC_SOURCE')
            t=int(date.timestamp())
            if t<=previous or t%300:raise ValueError('INVALID_SOURCE_TIME')
            previous=t
            if t not in wanted:continue
            if r.get('source')!='HistData' or r.get('quote_side')!='BID':raise ValueError('WRONG_PRICE_SOURCE')
            try:
                prices=_prices(r)
                if int(r['observed_minutes'])!=5:continue
            except (ValueError,TypeError,KeyError,ArithmeticError):continue
            bars[str(t)]={'time':t,**{k:float(v) for k,v in prices.items()}}
    paths={'cases':cp,'profiles':pp,'bars':bp,'alignment':(root/meta['inputs']['alignment']['path']).resolve()}
    if any(not p.is_relative_to(root) for p in paths.values()):raise ValueError('PRIVATE_SOURCE_REQUIRED')
    inputs={k:{'path':str(p.relative_to(root)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for k,p in paths.items()}
    value={'method':'execution_reference_v2','max_holding_slots':MAX_HOLDING_SLOTS,'inputs':inputs,'records':records,'bars':bars}
    target=root/'case_execution_bars_v2.json';temp=target.with_suffix('.tmp')
    temp.write_text(json.dumps(value,separators=(',',':'),allow_nan=False),encoding='utf-8');temp.replace(target)
    return {'profiles':len(records),'unique_bars':len(bars),'full_holding_records':sum(r['mode']=='FULL_HOLDING' for r in records.values()),
        'endpoint_ready':sum(str(r['times'][0]) in bars and str((r['close_times'] or r['times'])[-1]) in bars for r in records.values()),
        'continuous_holding_windows':sum(r['mode']=='FULL_HOLDING' and all(str(t) in bars for t in r['times']) for r in records.values()),'path':str(target)}


class ExecutionStore:
    def __init__(self,root,*,prefer_full=True):
        self.root=Path(root).resolve();full=self.root/'case_execution_bars_v2.json'
        self.path=full if prefer_full and full.exists() else self.root/'case_execution_bars.json'
        self.expected_method='execution_reference_v2' if self.path==full else 'execution_reference_v1'
        self.signature=None;self.paths=[self.path];self.data=None;self.lock=RLock()

    def get(self,ident,profile,source,cutoff):
        missing={'status':'UNAVAILABLE','reason':'參考進出場資料缺漏、窗口缺棒或來源已變；保留原單價格結果。','bars':[],'close_bars':[],'markers':[],'result':trade_result(source)}
        with self.lock:
            try:
                sig=tuple((str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in self.paths)
                if sig!=self.signature:
                    self.data=None;v=json.loads(self.path.read_text(encoding='utf-8'))
                    if (not isinstance(v,dict) or v.get('method')!=self.expected_method or
                        not isinstance(v.get('inputs'),dict) or set(v['inputs'])!={'cases','profiles','bars','alignment'}):return missing
                    if v['method']=='execution_reference_v2' and v.get('max_holding_slots')!=MAX_HOLDING_SLOTS:return missing
                    paths=[]
                    for k,ref in v['inputs'].items():
                        p=(self.root/ref['path']).resolve()
                        if not p.is_relative_to(self.root) or hashlib.sha256(p.read_bytes()).hexdigest()!=ref['sha256']:return missing
                        if k in ('cases','profiles') and p!=self.root/('cases.json' if k=='cases' else 'case_candidate_market_profiles.json'):return missing
                        paths.append(p)
                    self.paths=[self.path,*paths];self.signature=tuple((str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in self.paths);self.data=v
                v=self.data
                if v is None or type(cutoff) not in (int,float) or not math.isfinite(cutoff):return missing
                opened,closed=profile.get('reference_open_utc'),profile.get('reference_close_utc')
                if type(opened) is not int or type(closed) is not int or closed<opened or closed>cutoff:return missing
                full=v['method']=='execution_reference_v2'
                a,b=opened//300*300,closed//300*300
                expected,close_expected,mode=_window(a,b,full=full)
                record=v['records'][ident]
                if record['times']!=expected or record['close_times']!=close_expected or record['mode']!=mode:return missing
                def take(times):
                    rows=[]
                    for t in times:
                        if full and str(t) not in v['bars']:continue
                        row=v['bars'][str(t)]
                        if row['time']!=t or t+300>cutoff:raise ValueError('INVALID_TIME')
                        _prices(row);rows.append(dict(row))
                    return rows
                rows=take(expected);closes=take(close_expected)
                available={row['time'] for row in rows+closes}
                if a not in available or b not in available:return missing
                overlay=execution_overlay(source,profile,rows+closes,cutoff=cutoff)
                result=dict(overlay,bars=rows,close_bars=closes,mode=mode)
                if full:
                    slots=(b-a)//300+1
                    result['coverage']=dict(scope='WHOLE_REFERENCE_HOLDING' if mode=='FULL_HOLDING' else 'ENDPOINT_WINDOWS',
                        calendar_slots=slots,available_bars=len(available),gap_slots=slots-len(available))
                    result['reason']='已載入指定持倉範圍內來源可用的完整五分鐘棒；時間間隔可能含休市或來源缺漏。參考時鐘未獨立核實。'
                return result
            except (OSError,KeyError,ValueError,TypeError,ArithmeticError):return missing
