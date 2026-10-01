"""Transparent distances; profit never enters retrieval ranking."""
from __future__ import annotations
import json
import math
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
             prior_count: int = 0, prior_lot: D = D(0), signed_distance: D | None = None) -> list[dict]:
        seen: set[str] = set()
        ranked = []
        for c in self.available(clock):
            if c['side'] != side or c['action'] != action:
                continue
            distance = abs(math.log2(float(D(c['lot'])/lot)))/3
            reasons = ['買賣方向相同','同為首筆' if action=='FIRST' else '同為同向加倉']
            differences = ['盤面未完成時區對齊，未納入盤面相似度']
            if distance == 0:
                reasons.append('下單手數相同')
            else:
                differences.append('下單手數不同')
            if action == 'ADD':
                distance = (distance+abs(c.get('prior_count',0)-prior_count)/5)/2
                reasons.append('比較可見既有訂單數')
                if signed_distance is not None and c.get('signed_distance') is not None:
                    distance = (distance*2+min(float(abs(D(c['signed_distance'])-signed_distance)/D('.5')),3))/3
                    reasons.append('比較價格相對既有均價的距離')
            if distance > .8:
                continue
            ranked.append(dict(c,distance=round(distance,4),match_reasons=reasons,differences=differences))
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
        known = [c for c in ranked if c.get('profit') is not None]
        wins = sum(D(c['profit'])>0 for c in known)
        losses = sum(D(c['profit'])<0 for c in known)
        flat = len(known)-wins-losses
        # Display losses first only AFTER constructing the complete matched pool.
        display = sorted(ranked,key=lambda c:(0 if c.get('profit') is not None and D(c['profit'])<0 else 1,c['distance'],c['id']))[:6]
        return dict(total=len(ranked),wins=wins,losses=losses,flat=flat,unknown=len(ranked)-len(known),
                    win_rate=str((D(wins)/len(known)*100).quantize(D('.1'))) if known else None,
                    cases=display,limitations=['歷史描述，不是這筆新訂單的預測勝率','同一候選操作群最多一筆；首筆不等於已確認帳戶空手',
                    '未知時區案例採保守可用時間；市場特徵目前不參與相似度','來源含缺漏／跨帳戶對應未確認，僅供參考'] if self.source=='trader_history' else
                    ['合成案例供流程展示，數字不代表交易員績效','盤面相似度尚未啟用，目前比較操作條件'])

    def get(self, case_id: str) -> dict | None:
        c=next((c for c in self.items if c['id']==case_id),None)
        return dict(c,sequence=self.group_sequences.get(c['group'],c.get('sequence',[]))) if c else None
