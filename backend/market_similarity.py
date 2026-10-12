"""Point-in-time market context. No P/L, trader psychology or inferred time zones."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from pathlib import Path
import hashlib
import json
from bisect import bisect_right
from .technical import wilder

D = Decimal
METHOD = 'closed_market_context_20261012'
MAX_MARKET_DISTANCE = .40
# Weights are transparent engineering defaults, not fit to historical outcomes.
FEATURES = (
    ('5m_ma_gap', '5分價格距MA20／ATR', .15, D(2)),
    ('15m_ma_gap', '15分價格距MA20／ATR', .15, D(2)),
    ('1h_ma_gap', '1小時價格距MA20／ATR', .10, D(2)),
    ('5m_slope', '5分MA20近5根平均斜率／ATR', .10, D(1)),
    ('range_position', '5分近60根區間位置', .10, D(1)),
    ('support_atr', '距候選支撐／ATR', .10, D(2)),
    ('resistance_atr', '距候選壓力／ATR', .10, D(2)),
    ('atr_pct', '5分ATR占價格百分比', .20, None),
)


def number(value: Any) -> D | None:
    try:
        n=D(str(value))
        return n if n.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def snapshot(bars: list[dict], clock: int) -> dict:
    """Fixed context of at most 120 completed candles per frame, Decimal prices."""
    result=dict(method=METHOD,as_of=clock,status='insufficient',features={},latest_closed={},
                counts={},reason='已收K棒不足、存在過長缺口或末根行情過期')
    visible=[b for b in bars if b['time']+300<=clock][-1440:]
    if not visible or clock-(visible[-1]['time']+300)>=300:
        return result
    frames={}
    try:
        for b in visible:
            o,h,l,c=(D(str(b[k])) for k in ('open','high','low','close'))
            if any(not n.is_finite() or n<=0 for n in (o,h,l,c)) or not l<=min(o,c)<=max(o,c)<=h:
                return result
        if any(b['time']<=a['time'] for a,b in zip(visible,visible[1:])):return result
        for label,seconds,minimum in (('5m',300,60),('15m',900,60),('1h',3600,20)):
            groups: dict[int,list[dict]]={}
            for b in visible:
                start=b['time']//seconds*seconds
                if start+seconds<=clock: groups.setdefault(start,[]).append(b)
            candles=[]
            for start,group in sorted(groups.items()):
                if len(group)!=seconds//300 or any(b['time']!=start+i*300 for i,b in enumerate(group)):
                    continue
                candles.append(dict(time=start,close=D(str(group[-1]['close'])),
                                    high=max(D(str(b['high'])) for b in group),
                                    low=min(D(str(b['low'])) for b in group)))
            candles=candles[-120:]
            result['counts'][label]=len(candles)
            if len(candles)<minimum or clock-(candles[-1]['time']+seconds)>=seconds:
                return result
            if any(b['time']-a['time']>seconds*3 for a,b in zip(candles[-minimum:],candles[-minimum+1:])):
                return result
            if any(not v.is_finite() or v<=0 for b in candles for k,v in b.items() if k!='time'):
                return result
            ranges=[max(b['high']-b['low'],abs(b['high']-a['close']),abs(b['low']-a['close'])) for a,b in zip(candles,candles[1:])]
            atr=wilder(ranges,14)
            if atr is None or atr<=0: return result
            ma=sum((b['close'] for b in candles[-20:]),D(0))/20
            frames[label]=(candles,ma,atr)
            result['latest_closed'][label]=candles[-1]['time']+seconds
        features={}
        for label,(candles,ma,atr) in frames.items():
            features[label+'_ma_gap']=(candles[-1]['close']-ma)/atr
        candles,ma,atr=frames['5m'];last=candles[-1]['close']
        previous_ma=sum((b['close'] for b in candles[-25:-5]),D(0))/20
        features['5m_slope']=(ma-previous_ma)/5/atr
        recent=candles[-60:];low=min(b['low'] for b in recent);high=max(b['high'] for b in recent)
        features['range_position']=(last-low)/(high-low) if high>low else None
        features['atr_pct']=atr/last*100
        support=[];resistance=[]
        for i in range(2,len(recent)-2):
            b=recent[i];neighbours=recent[i-2:i]+recent[i+1:i+3]
            if b['low']<min(n['low'] for n in neighbours) and b['low']<last: support.append(b['low'])
            if b['high']>max(n['high'] for n in neighbours) and b['high']>last: resistance.append(b['high'])
        features['support_atr']=(last-max(support))/atr if support else None
        features['resistance_atr']=(min(resistance)-last)/atr if resistance else None
        result.update(status='ready',features={k:str(v) if v is not None else None for k,v in features.items()},
                      reason='僅已收K棒；支撐壓力為左右各2根已確認轉折候選，非交易員畫線；ATR為Wilder14，固定最多120根上下文')
    except (InvalidOperation,ValueError,TypeError,KeyError,ZeroDivisionError):
        pass
    return result


def valid_profile(profile: dict | None, clock: int) -> bool:
    if not profile or profile.get('alignment_status')!='confirmed' or profile.get('status')!='ready':
        return False
    if profile.get('method')!=METHOD or not isinstance(profile.get('as_of'),int) or profile['as_of']>clock:
        return False
    closed=profile.get('latest_closed',{})
    return isinstance(closed,dict) and isinstance(profile.get('features'),dict) and set(closed)=={'5m','15m','1h'} and all(isinstance(t,int) and
        0<=profile['as_of']-t<seconds for (label,seconds) in (('5m',300),('15m',900),('1h',3600)) for t in [closed[label]])


def load_sidecar(case_path: Path, profile_path: Path, private_root: Path) -> tuple[dict,str]:
    if not profile_path.exists():return {},'MISSING'
    try:
        data=json.loads(profile_path.read_text(encoding='utf-8'))
        if data.get('input_cases_sha256')!=hashlib.sha256(case_path.read_bytes()).hexdigest() or data.get('method')!=METHOD:
            return {},'STALE'
        inputs=data.get('inputs',{})
        if not {'bars','alignment'}<=inputs.keys():return {},'INVALID'
        for ref in inputs.values():
            bound=(private_root/ref.get('path','')).resolve()
            if not bound.is_relative_to(private_root.resolve()) or not bound.is_file() or ref.get('sha256')!=hashlib.sha256(bound.read_bytes()).hexdigest():
                return {},'STALE'
        if not isinstance(data.get('profiles'),dict):return {},'INVALID'
        if any(not isinstance(p,dict) for p in data['profiles'].values()):return {},'INVALID'
        return data['profiles'],'READY'
    except (OSError,ValueError,TypeError,AttributeError):
        return {},'INVALID'


def compare_market(query: dict, case: dict) -> dict | None:
    """Each axis must pass independently; missing dimensions retain their weight."""
    if any(p.get('status')!='ready' or p.get('method')!=METHOD for p in (query,case)):
        return None
    components=[];coverage=0.0
    qf,cf=query.get('features',{}),case.get('features',{})
    if not isinstance(qf,dict) or not isinstance(cf,dict):return None
    for key,label,weight,scale in FEATURES:
        q,c=number(qf.get(key)),number(cf.get(key))
        if qf.get(key) is not None and q is None or cf.get(key) is not None and c is None:
            return None
        if key in ('5m_ma_gap','15m_ma_gap','1h_ma_gap') and (q is None or c is None): return None
        if key=='1h_ma_gap' and abs(q)>D('.5') and abs(c)>D('.5') and q*c<0:
            return None
        missing=q is None or c is None
        if missing:
            distance=1.0
        elif scale is None:
            if q<=0 or c<=0: return None
            ratio=max(q,c)/min(q,c)
            if ratio>2: return None
            # A bounded dimensionless ratio is safe to convert to float.
            import math
            distance=math.log2(float(ratio))
        else:
            distance=float(min(abs(q-c)/scale,D(1)))
        if not missing: coverage+=weight
        components.append(dict(feature=key,label=label,query=str(q) if q is not None else None,
                               case=str(c) if c is not None else None,weight=weight,distance=round(distance,6),missing=missing))
    distance=sum(c['weight']*c['distance'] for c in components)
    if coverage<.8-1e-9 or distance>MAX_MARKET_DISTANCE: return None
    return dict(status='matched',label='盤面條件接近',distance=round(distance,6),coverage=round(coverage,3),
                components=components,reason='比較趨勢、相對進場位置及波動；不是逐根K線形狀或勝率預測')


def build_profiles(cases: list[dict], alignment: list[dict], bars: list[dict]) -> dict:
    """Only explicit reviewed UTC timestamps qualify. Price candidates never do."""
    by_id={r.get('case_id'):r for r in alignment}
    if len(by_id)!=len(alignment):raise ValueError('同一案例出現重複時間證據，請先釐清')
    profiles={};counts=dict(total=len(cases),unconfirmed=0,insufficient=0,ready=0)
    times=[b['time'] for b in bars]
    for c in cases:
        r=by_id.get(c['id'],{})
        if (r.get('timezone_status')!='CONFIRMED' or r.get('market_time_status')!='CONFIRMED'
            or r.get('can_use_for_market_similarity') is not True or not r.get('evidence_ref') or not r.get('reviewed_by')):
            counts['unconfirmed']+=1;continue
        try:
            opened=datetime.fromisoformat(r['open_utc'])
            if opened.tzinfo is None: raise ValueError('UTC timestamp required')
            clock=int(opened.timestamp());end=bisect_right(times,clock)
            profile=snapshot(bars[max(0,end-1441):end],clock)
        except (ValueError,KeyError,TypeError):
            counts['insufficient']+=1;continue
        if profile['status']!='ready':counts['insufficient']+=1;continue
        profiles[c['id']]=dict(profile,alignment_status='confirmed')
        counts['ready']+=1
    return dict(method=METHOD,profiles=profiles,counts=counts)
