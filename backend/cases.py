"""Transparent distances; profit never enters retrieval ranking."""
from __future__ import annotations
import json
from .similarity import build_size_profiles, compare, positive, summarize
from .market_similarity import valid_profile, compare_market, load_sidecar, METHOD as MARKET_METHOD
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
