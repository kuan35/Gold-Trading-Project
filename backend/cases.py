"""Transparent distances; profit never enters retrieval ranking."""
from __future__ import annotations
import json
from .similarity import build_size_profiles, compare, positive, summarize
from .market_similarity import valid_profile, compare_market, load_sidecar, METHOD as MARKET_METHOD
from .candidate_sidecar import load_candidate_sidecar
from .candidate_retrieval import rank_candidates, summarize_candidate_tier
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = Decimal
LABELS = {'NO_OBSERVED_POSITION':'可見初始單','ADD_ADVERSE':'價格不利時加單',
          'ADD_FAVORABLE':'價格有利時加單','ADD_FLAT':'同價加單','TIME_TIE':'順序不明',
          'OPPOSITE':'反向持倉','MIXED':'混合持倉','INVALID':'無法判讀'}


class CaseStore:
    def __init__(self) -> None:
        path = ROOT/'private'/'cases.json'
        self.source = 'trader_history' if path.exists() else 'synthetic_demo'
        payload=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        self.items = payload['cases'] if path.exists() else self._demo()
        self.group_sequences=payload.get('group_sequences',{})
        profiles_path = ROOT/'private'/'case_size_profiles.json'
        self.profile_status = 'MISSING'
        if path.exists() and profiles_path.exists():
            import hashlib
            data = json.loads(profiles_path.read_text(encoding='utf-8'))
            valid = data.get('input_cases_sha256') == hashlib.sha256(path.read_bytes()).hexdigest()
            self.profile_status = 'READY' if valid else 'STALE'
            profiles = data['profiles'] if valid else {}
            for item in self.items:
                item['size_profile'] = profiles.get(item['id'])
        elif not path.exists():
            profiles = build_size_profiles([dict(record_id=c['id'],source='synthetic',lot=c['lot'],open_time=c['opened_at']) for c in self.items])
            for item in self.items:
                item['size_profile'] = profiles.get(item['id'])
        profiles,self.market_profile_status=load_sidecar(path,ROOT/'private'/'case_market_profiles.json',ROOT/'private') if path.exists() else ({},'MISSING')
        for item in self.items:
            item['market_profile']=profiles.get(item['id'])
        self.candidate_profiles={}
        self.candidate_profile_status='NOT_LOADED' if path.exists() else 'MISSING'

    def ensure_candidate_profiles(self) -> None:
        if self.candidate_profile_status == 'NOT_LOADED':
            private=ROOT/'private'
            self.candidate_profiles,self.candidate_profile_status=load_candidate_sidecar(
                private/'cases.json',private/'case_candidate_market_profiles.json',private)

    def market_context(self, side: str, action: str, clock: int, query_market: dict | None) -> dict:
        available=[c for c in self.available(clock) if c['side']==side and c['action']==action]
        verified=sum(valid_profile(c.get('market_profile'),clock) for c in available)
        ready=bool(query_market and query_market.get('status')=='ready' and query_market.get('method')==MARKET_METHOD
                   and query_market.get('as_of')==clock)
        # Audit callers may query after the feature snapshot, but must use an exact
        # decision clock in production. No future or stale query snapshot is used.
        if query_market and isinstance(query_market.get('as_of'),int) and query_market['as_of']<=clock and clock-query_market['as_of']<300:
            ready=query_market.get('status')=='ready' and query_market.get('method')==MARKET_METHOD
        mode='market_and_operation' if ready and verified else 'operation_only'
        reason=('同方向與操作類型中，尚無已核實時間且盤面資料完整的歷史案例；以下只比較操作條件' if not verified else
                '本次多週期已收K棒不足或快照不合時，以下只比較操作條件' if not ready else
                '操作與盤面門檻都必須通過；不因沒有案例而放寬條件')
        return dict(mode=mode,verified_market_candidates=verified,
                    excluded_unverified_market=len(available)-verified,query_market_ready=ready,reason=reason)

    def _demo(self) -> list[dict]:
        base = int(datetime(2025,2,1,tzinfo=timezone.utc).timestamp())
        items = []
        for i in range(36):
            side = 'BUY' if i%2==0 else 'SELL'
            action = 'FIRST' if i%4<2 else 'ADD'
            lot = ['0.10','0.20','0.05'][i%3]
            pnl = ['-126.50','82.00','-47.20','153.10','0.00','-210.30'][i%6]
            px = D('2890')+i*D('0.75')
            close = px+D(pnl)/(D(lot)*100)*(1 if side=='BUY' else -1)
            opened = base+i*43200
            behavior = 'NO_OBSERVED_POSITION' if action=='FIRST' else ('ADD_ADVERSE' if i%3 else 'ADD_FAVORABLE')
            items.append(dict(id=f'DEMO-{i+1:03}',label=LABELS[behavior],side=side,action=action,
                              lot=lot,entry=str(px),exit=str(close.quantize(D('.01'))),
                              opened_at=datetime.fromtimestamp(opened,timezone.utc).isoformat(),
                              closed_at=datetime.fromtimestamp(opened+3600,timezone.utc).isoformat(),
                              available_at=opened+3600,profit=pnl,group=f'DEMO-G{i+1}',
                              source_kind='synthetic_demo',time_alignment='confirmed',behavior=behavior,
                              prior_count=0 if action=='FIRST' else 2,prior_lot='0' if action=='FIRST' else '0.20',
                              signed_distance='-0.20' if action=='ADD' else None,
                              market=None,sequence=[dict(index=1,side=side,lot=lot,entry=str(px),exit=str(close),profit=pnl,role=LABELS[behavior])]))
        return items

    def available(self, clock: int | None = None) -> list[dict]:
        cutoff = clock if clock is not None else getattr(self,'clock',0)
        return [c for c in self.items if c.get('available_at',10**20) <= cutoff]

    def rank(self, side: str, action: str, lot: D, clock: int,
             prior_count: int = 0, prior_lot: D = D(0), signed_distance: D | None = None,
             typical_lot: D | None = None, query_market: dict | None = None) -> list[dict]:
        if positive(lot) is None or (typical_lot is not None and positive(typical_lot) is None):
            raise ValueError('手數與平常手數必須大於零且有限')
        seen: set[str] = set()
        ranked = []
        context=self.market_context(side,action,clock,query_market)
        for c in self.available(clock):
            if c['side'] != side or c['action'] != action:
                continue
            result = compare(c,lot,action,prior_count,prior_lot,signed_distance,typical_lot)
            if result is None:
                continue
            result['operation_distance']=result['distance']
            result['operation_comparison']=dict(distance=result['distance'],strength='weak' if action=='FIRST' else 'limited',
                label='操作條件接近',reason='首筆只比較方向、可見首筆與手數；辨識力有限' if action=='FIRST' else '比較手數、既有部位及距均價位置；不是資金風險等價')
            if context['mode']=='market_and_operation':
                if not valid_profile(c.get('market_profile'),clock):continue
                market=compare_market(query_market,c['market_profile'])
                if market is None:continue
                result['market_comparison']=market
                result['distance']=round(.4*result['distance']+.6*market['distance'],6)
                result['match_reasons'].append('已核實時間的盤面條件通過比較門檻')
                result['differences']=[s for s in result['differences'] if '盤面與時區尚未核實' not in s]
                result['differences'].append(market['reason'])
            else:
                result['market_comparison']=dict(status='unavailable',label='盤面尚無法比較',distance=None,coverage=0,
                                                components=[],reason=context['reason'])
            safe = {k:v for k,v in c.items() if k not in ('size_profile','scope_private','market_profile')}
            ranked.append(dict(safe,**result))
        ranked.sort(key=lambda c:(c['distance'],c['id']))
        result = []
        for c in ranked:
            if c['group'] not in seen:
                seen.add(c['group'])
                result.append(c)
        return result

    def retrieve(self, side: str, action: str, lot: D, clock: int, **kwargs) -> dict:
        self.clock = clock
        if self.source == 'trader_history':
            self.ensure_candidate_profiles()
            if positive(lot) is None or (kwargs.get('typical_lot') is not None and positive(kwargs['typical_lot']) is None):
                raise ValueError('手數與平常手數必須大於零且有限')
            query = kwargs.get('query_candidate')
            status = getattr(self,'candidate_profile_status','MISSING')
            if status != 'READY' or not query or query.get('status') != 'candidate_only' or query.get('as_of') != clock:
                return candidate_unavailable(status if status != 'READY' else 'QUERY_UNAVAILABLE')
            tiers = rank_candidates(self.items,self.candidate_profiles,query,side,clock)
            return candidate_response(tiers,self.items)
        kwargs.pop('query_candidate',None)
        ranked = self.rank(side,action,lot,clock,**kwargs)
        context=self.market_context(side,action,clock,kwargs.get('query_market'))
        operation_count=len(self.rank(side,action,lot,clock,**{k:v for k,v in kwargs.items() if k!='query_market'}))
        context.update(operation_candidates=operation_count,market_matches=len(ranked) if context['mode']=='market_and_operation' else 0)
        if context['mode']=='market_and_operation' and not ranked:
            context['reason']='沒有同時通過操作與盤面條件的案例；不放寬條件硬湊。仍可查看目前盤面分析。'
        basis = 'relative_lot' if kwargs.get('typical_lot') is not None else 'absolute_lot'
        excluded = sum(not (c.get('size_profile') or {}).get('typical_lot')
                       for c in self.available(clock) if c['side']==side and c['action']==action) if basis=='relative_lot' else 0
        result = dict(**summarize(ranked,basis,excluded,market_context=context,source=self.source),limitations=['歷史描述，不是這筆新訂單的預測勝率','同一候選操作群最多一筆；首筆不等於已確認帳戶空手',
                    context['reason'],'來源含缺漏／跨帳戶對應未確認，僅供參考'] if self.source=='trader_history' else
                    ['合成案例供流程展示，數字不代表交易員績效',context['reason']])
        if getattr(self,'profile_status',None) == 'STALE':
            result['limitations'].append('案例資料已更新，平常手數基準需重建；相對比較暫不可用')
        if getattr(self,'market_profile_status',None) in ('STALE','INVALID'):
            result['limitations'].append('歷史盤面側檔或證據資料已變更，盤面比較停用，請重建並核對')
        return result

    def get(self, case_id: str) -> dict | None:
        c=next((c for c in self.items if c['id']==case_id),None)
        safe = {k:v for k,v in c.items() if k not in ('size_profile','scope_private','market_profile')} if c else None
        return dict(safe,sequence=self.group_sequences.get(c['group'],c.get('sequence',[]))) if c else None

    def get_candidate_detail(self, case_id: str, clock: int) -> dict | None:
        self.ensure_candidate_profiles()
        if self.source != 'trader_history' or getattr(self,'candidate_profile_status','MISSING') != 'READY':
            return None
        value = self.get(case_id)
        profile = self.candidate_profiles.get(case_id)
        if not value or value['available_at'] > clock or not profile or profile['as_of'] > clock:
            return None
        bars = profile['pre_entry_bars']['5m'][-60:]
        if not bars or any(bar['time'] + 300 > profile['as_of'] for bar in bars):
            return None
        chart_bars=[dict(time=bar['time'],**{key:float(bar[key]) for key in ('open','high','low','close')},volume=0) for bar in bars]
        return dict(value,bars=chart_bars,markers=[],distance=None,
                    candidate_tier=profile['tier'],clock_status='UNKNOWN',
                    chart_reason='參考行情＋候選 UTC，券商時鐘未核實；只顯示進場前已收盤 K 線')


def candidate_unavailable(status: str) -> dict:
    reason = f'候選盤面無法比較（{status}）；請檢查本機側檔與回放行情。沒有改用舊版操作權重。'
    return dict(total=0,wins=0,losses=0,flat=0,unknown=0,win_rate=None,cases=[],
                profit_cases=[],loss_cases=[],full_cases=[],five_minute_only_cases=[],
                five_minute_only_total=0,candidate_market_unavailable_reason=reason,
                similarity_sufficiency='NO_MATCH',
                comparison=dict(mode='candidate_market',clock_status='UNKNOWN',method='candidate_market_v1',
                                basis='direction_and_market',market_features_enabled=False,reason=reason),
                sufficiency=dict(status='insufficient',label='資料不足',reasons=[reason],matched_groups=0,
                                 is_success_probability=False),limitations=[reason,'券商時鐘尚未逐帳戶核實'])


def candidate_response(tiers: dict, cases: list[dict]) -> dict:
    lookup = {case['id']: case for case in cases}
    def make_rows(rows):
        result = []
        for row in rows:
            case = lookup[row['case_id']]
            safe = {key: value for key,value in case.items() if key not in (
                'size_profile','scope_private','market_profile','market','source_format','market_alignment_reason')}
            result.append(dict(safe,distance=None,candidate_tier=row['tier'],
                               shape_rank=round(row['shape_percentile'],4),
                               indicator_rank=round(row['indicator_percentile'],4),
                               indicator_differences={key:round(value,4) for key,value in row['indicator_differences'].items()},
                               clock_status='UNKNOWN',
                               match_reasons=['方向相同','候選盤面雙軸近鄰；尚未校準足夠相似門檻'],
                               differences=['券商時鐘未核實；只用於本機候選檢索']))
        return result
    summary = summarize_candidate_tier(tiers['full'],lookup)
    full = make_rows(tiers['full'][:6])
    limited = make_rows(tiers['five_minute_only'][:6])
    counts = summary['counts']
    known = counts['win']+counts['loss']+counts['flat']
    reason = tiers['reason']
    def profit_sign(row):
        try:
            value=D(str(row['profit']))
            return (1 if value>0 else -1 if value<0 else 0) if value.is_finite() else 0
        except Exception:
            return 0
    return dict(total=summary['total'],wins=counts['win'],losses=counts['loss'],flat=counts['flat'],
                unknown=counts['unknown'],win_rate=(str(round(100*counts['win']/known,1)) if known else None),
                cases=full,profit_cases=[row for row in full if profit_sign(row)>0],
                loss_cases=[row for row in full if profit_sign(row)<0],
                full_cases=full,five_minute_only_cases=limited,
                five_minute_only_total=len(tiers['five_minute_only']),candidate_market_unavailable_reason=None,
                similarity_sufficiency=tiers['similarity_sufficiency'],
                comparison=dict(mode='candidate_market',clock_status='UNKNOWN',method='candidate_market_v1',
                                basis='direction_and_market',market_features_enabled=True,
                                full_pool=tiers['counts']['full_pool'],
                                five_minute_only_pool=tiers['counts']['five_minute_only_pool'],reason=reason),
                sufficiency=dict(status='limited' if full or limited else 'insufficient',
                                 label='候選近鄰／未校準' if full or limited else '資料不足',
                                 reasons=[reason],matched_groups=len(full)+len(limited),is_success_probability=False),
                limitations=['候選 UTC 與券商時鐘未核實；案例 K 線不是已確認的交易盤面',
                             '雙軸分位只在各自候選池內排序，不是相似機率或預測勝率',
                             '獲利比例僅為完整三週期池的歷史結果分布；盈虧不參與排序'])
