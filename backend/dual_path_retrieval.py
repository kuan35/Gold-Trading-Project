"""Full 5m/1h close paths with explicit previous-high/low state priority.

No model, numerical-library dependency, lot or outcome enters the ranking.
"""
from __future__ import annotations

from bisect import bisect_left
from datetime import datetime, timezone
from decimal import Decimal
from math import sqrt, isfinite

from .candidate_profile import profile_before_entry, _indicators
from .compact_market import describe_compact, eligible_pool, distinct_rows, STRUCTURES
from .live_candidate_profile import _closed_frame
from .candidate_retrieval import summarize_candidate_tier

METHOD='dual_path_structure_v1'


def profile_from_dual_frames(five, hour, clock, schedule=None):
    try:
        five=_closed_frame(five,300,61,clock,schedule)
        hour=_closed_frame(hour,3600,20,clock,schedule)
        if five[-1]['time']+300!=clock:raise ValueError('FIVE_MINUTE_LAST_CLOSE_MISSING')
        result=profile_before_entry(five,clock,{'tier':'5m_only'})
        if result['status']!='candidate_only':return result
        values,_=_indicators(hour,'1h',momentum=False)
        if values is None:raise ValueError('HOURLY_ATR_UNAVAILABLE')
        result['indicators'].update({key:str(value) for key,value in values.items()})
        result['pre_entry_bars']['1h']=hour
        result['latest_closed']['1h']=hour[-1]['time']+3600
        result.update(tier='full',source='ctrader_demo_xauusd',query_clock_status='UTC_SOURCE_TIMESTAMP')
        return result
    except (KeyError,TypeError,ValueError,ArithmeticError) as exc:
        return dict(status='insufficient',reason=str(exc) or 'INVALID_DUAL_BARS')


def profile_from_live_dual_snapshot(snapshot):
    quote=snapshot.get('quote') or {}
    if snapshot.get('connection_status')!='CONNECTED' or quote.get('status')!='CURRENT':
        return dict(status='insufficient',reason='BROKER_QUOTE_UNAVAILABLE')
    try:
        stamp=datetime.fromisoformat(quote['source_time_utc'])
        if stamp.tzinfo is None:raise ValueError('BROKER_TIME_UNAVAILABLE')
        clock=int(stamp.astimezone(timezone.utc).timestamp())//300*300
        frames=snapshot.get('bars') or {}
        return profile_from_dual_frames(frames['5m'],frames['1h'],clock,
                                        (snapshot.get('symbol') or {}).get('trading_schedule'))
    except (KeyError,TypeError,ValueError,ArithmeticError) as exc:
        return dict(status='insufficient',reason=str(exc) or 'BROKER_TIME_UNAVAILABLE')


def _path(profile,interval):
    bars=profile['pre_entry_bars'][interval][-(60 if interval=='5m' else 20):]
    first=float(bars[0]['close'])
    values=[(float(b['close'])/first-1)*100 for b in bars]
    if not all(isfinite(v) for v in values):raise ValueError('NONFINITE_CLOSE_PATH')
    return values


def _rms(a,b):return sqrt(sum((x-y)**2 for x,y in zip(a,b))/len(a))


def _profit_sign(case):
    try:
        value=Decimal(str(case.get('profit')))
        return (1 if value>0 else -1 if value<0 else 0) if value.is_finite() else 0
    except ArithmeticError:return 0


def _text(d):
    return (f"{d['side']}｜5分60根＋1小時20根已收收盤路徑｜"
            f"{STRUCTURES[d['structure']]}｜ATR/價格 {d['atr_pct_5m']:.4f}%（另列，不排名）")


def unavailable(reason):
    return dict(total=0,wins=0,losses=0,flat=0,unknown=0,win_rate=None,cases=[],full_cases=[],
                five_minute_only_cases=[],five_minute_only_total=0,profit_cases=[],loss_cases=[],
                query_status='insufficient',query_reason=reason,candidate_market_unavailable_reason=reason,
                similarity_sufficiency='NO_MATCH',limitations=[reason],
                comparison=dict(mode='candidate_market',method=METHOD,basis='direction_and_dual_path',
                    alignment_scope='NONE',clock_status='UNKNOWN',independent_clock_verified=False,
                    market_features_enabled=False,reason=reason))


class DualPathIndex:
    """Immutable historical index. Callers replace it when source profiles change."""
    def __init__(self,cases,profiles):
        self.cases=[];self.descriptions={};self.paths={};self.lookup={};self.invalid_profiles=0
        for c in sorted(cases,key=lambda c:c['id']):
            p=profiles.get(c['id'])
            if not p or p.get('tier')!='full':continue
            try:
                d=describe_compact(p,c['side'])
                paths={iv:_path(p,iv) for iv in ('5m','1h')}
            except (KeyError,TypeError,ValueError,ArithmeticError):
                self.invalid_profiles+=1;continue
            self.cases.append(c);self.lookup[c['id']]=c
            self.descriptions[c['id']]=d;self.paths[c['id']]=paths

    def eligible(self,query,side,exclude_group=None):
        d=describe_compact(query,side)
        return eligible_pool(self.cases,self.descriptions,d,exclude_group=exclude_group,purge_overlap=True)

    def retrieve(self,query,side,*,exclude_group=None,top_k=5):
        if type(top_k) is not int or not 1<=top_k<=20:raise ValueError('invalid top_k')
        try:
            d=describe_compact(query,side)
            if d['tier']!='full':return unavailable('DUAL_FRAME_QUERY_REQUIRED')
            qpaths={iv:_path(query,iv) for iv in ('5m','1h')}
            pool,counts=self.eligible(query,side,exclude_group)
        except (KeyError,TypeError,ValueError,ArithmeticError) as exc:
            return unavailable(str(exc) or 'DUAL_QUERY_UNAVAILABLE')
        if not pool:
            result=unavailable('沒有查詢前成熟、窗口不重疊的同方向完整雙週期案例')
            result.update(query_status='candidate_only',query_reason=None)
            return result
        rows=[]
        for c in pool:
            cid=c['id'];other=self.descriptions[cid]
            rows.append(dict(case_id=cid,group=c['group'],
                             path_distance_pct=_rms(qpaths['5m'],self.paths[cid]['5m']),
                             hour_path_distance_pct=_rms(qpaths['1h'],self.paths[cid]['1h']),
                             structure_match=d['structure']==other['structure']))
        fives=sorted(r['path_distance_pct'] for r in rows)
        hours=sorted(r['hour_path_distance_pct'] for r in rows)
        for r in rows:
            r['path_rank']=bisect_left(fives,r['path_distance_pct'])/len(rows)
            r['hour_path_rank']=bisect_left(hours,r['hour_path_distance_pct'])/len(rows)
        rows.sort(key=lambda r:(not r['structure_match'],max(r['path_rank'],r['hour_path_rank']),
                                r['path_rank']+r['hour_path_rank'],r['case_id']))
        unique=distinct_rows(rows,self.descriptions,top_k=None)
        stats=summarize_candidate_tier(unique,self.lookup)
        counts_out=stats['counts'];known=stats['total']-counts_out['unknown']
        displayed=[]
        for r in unique[:top_k]:
            c=self.lookup[r['case_id']];other=self.descriptions[c['id']]
            safe={k:v for k,v in c.items() if k not in ('size_profile','scope_private','market_profile',
                                                       'market','source_format','market_alignment_reason')}
            safe.update(candidate_tier='full',reference_alignment='PROJECT_REFERENCE',clock_status='UNKNOWN',
                        retrieval_method=METHOD,distance=None,
                        path_distance_pct=r['path_distance_pct'],hour_path_distance_pct=r['hour_path_distance_pct'],
                        path_rank=r['path_rank'],hour_path_rank=r['hour_path_rank'],structure=other['structure'],
                        query_structure=d['structure'],structure_match=r['structure_match'],
                        structure_label=STRUCTURES[other['structure']],query_structure_label=STRUCTURES[d['structure']],
                        volatility_ratio=max(d['atr_pct_5m']/other['atr_pct_5m'],other['atr_pct_5m']/d['atr_pct_5m']),
                        market_state_text=_text(other),match_reasons=['方向相同',
                            '前高低狀態相同' if r['structure_match'] else '前高低狀態不同，屬補充參考',
                            '完整五分／一小時收盤路徑雙軸排序'],
                        differences=['案例原始時鐘尚未獨立核實；路徑排名不是足夠相似機率'])
            displayed.append(safe)
        return dict(total=len(unique),wins=counts_out['win'],losses=counts_out['loss'],flat=counts_out['flat'],
                    unknown=counts_out['unknown'],win_rate=str((Decimal(counts_out['win'])*100/known).quantize(Decimal('.1'))) if known else None,
                    cases=displayed,full_cases=displayed,five_minute_only_cases=[],five_minute_only_total=0,
                    profit_cases=[c for c in displayed if _profit_sign(c)>0],
                    loss_cases=[c for c in displayed if _profit_sign(c)<0],
                    query_status='candidate_only',query_reason=None,candidate_market_unavailable_reason=None,
                    similarity_sufficiency='UNCALIBRATED',
                    comparison=dict(mode='candidate_market',method=METHOD,basis='direction_and_dual_path',
                        alignment_scope='PROJECT_REFERENCE',clock_status='UNKNOWN',independent_clock_verified=False,
                        market_features_enabled=True,parameters_validated=False,query_market_text=_text(d),
                        query_structure=d['structure'],query_structure_label=STRUCTURES[d['structure']],
                        full_pool=len(pool),full_groups=len(unique),same_structure_groups=sum(r['structure_match'] for r in unique),
                        excluded_overlap_rows=counts['excluded_overlap_rows'],
                        reason='相同前高低狀態優先；完整五分與一小時路徑先看較差軸排名，群與盤面時點去重。'),
                    limitations=['前五是相對最近參考，足夠相似門檻尚未校準',
                                 '只比較已收收盤路徑及末棒前高低狀態；波動倍率不參與排名',
                                 '歷史結果分布是完整可比較池的事後描述，不是獲利預測'])
