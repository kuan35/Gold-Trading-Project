"""Shared frozen context rules for offline experiments and product retrieval.

All distance thresholds are exploratory tolerances, not calibrated probabilities.
"""
from collections import Counter
from decimal import Decimal
from math import log, sqrt, isfinite

from .compact_market import describe_compact, distinct_rows
from .dual_path_retrieval import _path

LIMITS={
    'strict':dict(d5=.15,d1h=.30,dtail=.06,vol_ratio=1.5),
    'medium':dict(d5=.25,d1h=.50,dtail=.10,vol_ratio=2.),
    'loose':dict(d5=.40,d1h=.80,dtail=.16,vol_ratio=3.),
}

def market_features(profile):
    d=describe_compact(profile,'BUY')  # Side is filtered by the common index, not a chart feature.
    if d['tier']!='full':raise ValueError('FULL_PROFILE_REQUIRED')
    bars=profile['pre_entry_bars']['5m'][-60:]
    reference=bars[-26:-6]
    event=bars[-6:]
    tr=[]
    for previous,b in zip(reference,reference[1:]):
        hi,lo,pc=Decimal(b['high']),Decimal(b['low']),Decimal(previous['close'])
        tr.append(max(hi-lo,abs(hi-pc),abs(lo-pc)))
    atr=sum(tr[-14:],Decimal(0))/14
    if atr<=0:raise ValueError('EVENT_REFERENCE_ATR_UNAVAILABLE')
    hi=max(Decimal(b['high']) for b in reference)
    lo=min(Decimal(b['low']) for b in reference)
    buffer=atr*Decimal('.1')
    def zone(close):
        if close>hi+buffer:return 'ABOVE'
        if close<lo-buffer:return 'BELOW'
        if lo+buffer<close<hi-buffer:return 'INSIDE'
        return 'BOUNDARY_UNKNOWN'
    zones=[zone(Decimal(b['close'])) for b in event]
    state=zones[-1]
    if state=='INSIDE':
        above,below='ABOVE' in zones[:-1],'BELOW' in zones[:-1]
        state=('BOTH_RECLAIM' if above and below else 'UPPER_RECLAIM' if above
               else 'LOWER_RECLAIM' if below else 'IN_RANGE')
    anchor=Decimal(reference[-1]['close'])
    tail_return=(Decimal(event[-1]['close'])-anchor)/atr
    direction='U' if tail_return>Decimal('.5') else 'D' if tail_return<Decimal('-.5') else 'N'
    tail=[float((Decimal(b['close'])/anchor-1)*100) for b in [reference[-1]]+event]
    return dict(path5=_path(profile,'5m'),path1h=_path(profile,'1h'),tail_path=tail,
                atr_pct=d['atr_pct_5m'],event=state,tail_direction=direction,
                tail_return_atr=float(tail_return),reference_high=str(hi),reference_low=str(lo),
                reference_atr=str(atr),reference_buffer=str(buffer),close_zones=zones,
                upper_wick_outside=any(Decimal(b['high'])>hi+buffer for b in event),
                lower_wick_outside=any(Decimal(b['low'])<lo-buffer for b in event))


def pair_metrics(query,candidate):
    def rms(a,b):return sqrt(sum((x-y)**2 for x,y in zip(a,b))/len(a))
    return dict(d5=rms(query['path5'],candidate['path5']),d1h=rms(query['path1h'],candidate['path1h']),
                dtail=rms(query['tail_path'],candidate['tail_path']),
                vol_ratio=max(query['atr_pct']/candidate['atr_pct'],candidate['atr_pct']/query['atr_pct']),
                query_event=query['event'],case_event=candidate['event'],
                query_tail=query['tail_direction'],case_tail=candidate['tail_direction'])


def evaluate_rows(rows,descriptions,limits,*,components='full',top_k=5):
    if components not in ('paths','tail','vol','full'):raise ValueError('UNKNOWN_COMPONENTS')
    if any(not isfinite(v) or v<=0 for v in limits.values()) or limits['vol_ratio']<=1:
        raise ValueError('INVALID_LIMITS')
    rejections=Counter();passed=[];scored=[];first_rejection=Counter()
    for original in rows:
        r=dict(original)
        if any(not isfinite(r[k]) or r[k]<0 for k in ('d5','d1h','dtail')) or not isfinite(r['vol_ratio']) or r['vol_ratio']<1:
            raise ValueError('INVALID_PAIR_METRICS')
        reasons=[];distances=[r['d5']/limits['d5'],r['d1h']/limits['d1h']]
        if r['d5']>limits['d5']:reasons.append('five_path')
        if r['d1h']>limits['d1h']:reasons.append('hour_path')
        if components!='paths':
            distances.append(r['dtail']/limits['dtail'])
            if r['dtail']>limits['dtail']:reasons.append('tail_path')
            if {r['query_tail'],r['case_tail']}=={'U','D'}:reasons.append('tail_direction')
        if components in ('vol','full'):
            distances.append(log(r['vol_ratio'])/log(limits['vol_ratio']))
            if r['vol_ratio']>limits['vol_ratio']:reasons.append('volatility')
        if components=='full':
            if 'BOUNDARY_UNKNOWN' in (r['query_event'],r['case_event']):reasons.append('event_unknown')
            elif r['query_event']!=r['case_event']:reasons.append('event_stage')
        r.update(score_max=max(distances),score_sum=sum(distances),reasons=reasons)
        rejections.update(reasons)
        if reasons:first_rejection[reasons[0]]+=1
        else:passed.append(r)
        scored.append(r)
    key=lambda r:(r['score_max'],r['score_sum'],r['case_id'])
    passed.sort(key=key);scored.sort(key=key)
    unique=distinct_rows(passed,descriptions,top_k=None)
    return dict(rows=unique[:top_k],passed_rows=len(passed),passed_unique=len(unique),
                rejections=dict(sorted(rejections.items())),first_rejection=dict(sorted(first_rejection.items())),
                nearest_rejected=[r for r in scored if r['reasons']][:10],
                _passed_ids={r['case_id'] for r in passed})
