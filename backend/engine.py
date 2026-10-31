"""Single-session replay engine. In-memory prototype, Decimal accounting."""
from __future__ import annotations
import threading
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4
from .market import load_bars, aggregate
from .cases import CaseStore
from .technical import analyze as technical_analysis
from .market_similarity import snapshot as market_snapshot
from .candidate_bars import classify_coverage
from .candidate_profile import profile_before_entry
from .replay_management import ReplayManagement
from pathlib import Path
import json

D = Decimal


class DomainError(ValueError):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def amount(raw: str, name: str) -> D:
    try:
        value = D(str(raw))
    except (InvalidOperation,ValueError):
        raise DomainError(f'{name}必須是有效數字')
    if not value.is_finite() or value <= 0:
        raise DomainError(f'{name}必須大於零且為有限數字')
    return value


def money(value: D) -> str:
    return str(value.quantize(D('.01')))


class Engine(ReplayManagement):
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.bars,self.data_source = load_bars()
        self.cases = CaseStore()
        self.candidate_session_gaps = None
        self.mode = 'replay'
        self.initial_cursor = min(360,len(self.bars)-1)
        self.version = 0
        self.reset()

    @property
    def clock(self) -> int:
        return self.bars[self.cursor-1]['time']+300

    def reset(self) -> dict:
        with self.lock:
            self.cursor = self.initial_cursor
            self.balance = D('10000')
            self.positions: list[dict] = []
            self.orders: list[dict] = []
            self.pending_orders: list[dict] = []
            self.drafts: dict[str,dict] = {}
            self.confirmations: dict[str,dict] = {}
            self.close_results: dict[str,dict] = {}
            self.version += 1
            return self.state()

    def quote(self) -> dict:
        price = D(self.bars[self.cursor-1]['close'])
        return dict(bid=money(price),ask=money(price+D('.30')),time=self.clock)

    def position_pnl(self, p: dict) -> D:
        quote = self.quote()
        current = D(quote['bid'] if p['side']=='BUY' else quote['ask'])
        return (current-D(p['entry']))*D(p['lot'])*100*(1 if p['side']=='BUY' else -1)

    def state(self) -> dict:
        quote = self.quote()
        recent = self.bars[max(0,self.cursor-60):self.cursor]
        high = max(D(b['high']) for b in recent)
        low = min(D(b['low']) for b in recent)
        close = D(recent[-1]['close'])
        pnl = sum((self.position_pnl(p) for p in self.positions),D(0))
        return dict(mode=self.mode,version=self.version,clock=self.clock,data_source=self.data_source,
                    broker_connected=False,llm_enabled=False,quote=quote,
                    account=dict(balance=money(self.balance),equity=money(self.balance+pnl)),
                    positions=[dict(p,pnl=money(self.position_pnl(p))) for p in self.positions],orders=list(reversed(self.orders)),
                    pending_orders=[dict(p) for p in self.pending_orders],
                    market=dict(change_pct=money((close-D(recent[0]['open']))/D(recent[0]['open'])*100),
                                range_pct=money((high-low)/close*100),high=money(high),low=money(low),
                                ma20=money(sum(D(b['close']) for b in recent[-20:])/20),
                                ma60=money(sum(D(b['close']) for b in recent)/len(recent))),
                    data_quality=['本機回放・固定價差0.30美元，合約100oz/lot，佣金及隔夜費未計',
                                  '目前案例依操作條件檢索；盤面對齊未核實',
                                  '成交不代表券商回報，demo API未連線'])

    def chart(self, interval: str = '5m', focus: str | None = None) -> dict:
        seconds = {'5m':300,'15m':900,'1h':3600}.get(interval)
        if seconds is None:
            raise DomainError('不支援的K線週期')
        bars = aggregate(self.bars[:self.cursor],seconds,self.clock,limit=None)
        last_complete = bars[-1]['time'] if bars else None
        selected = next((o for o in self.orders if o['id'] == focus),None) if focus else None
        if focus and selected is None:
            raise DomainError('成交紀錄不存在，請重新選擇',404)
        navigation = None
        if selected:
            position_id = selected.get('position_id') or (selected['id'] if selected['action'] != 'CLOSE' else None)
            related = [o for o in self.orders if o['id'] == selected['id'] or
                       (position_id and (o['id'] == position_id or o.get('position_id') == position_id))]
            indices = [i for i,b in enumerate(bars) if b['time'] <= min(o['time'] for o in related)-1]
            start = max(0,(indices[-1] if indices else 0)-100)
            indices = [i for i,b in enumerate(bars) if b['time'] <= max(o['time'] for o in related)-1]
            end = min(len(bars),(indices[-1] if indices else 0)+41)
            bars = bars[start:end]
            navigation = dict(selected_id=focus,order_ids=[o['id'] for o in related],
                              pairing='linked' if len(related)>1 else 'open' if selected['action']!='CLOSE' else 'unavailable',
                              orders=related,
                              note='箭頭標示買賣方向與時間，成交價看標籤與價格線；時間貼齊當時最後已收完的K棒。停損／停利只知道觸發K棒，並非精確成交秒。')
        else:
            bars = bars[-250:]
        times = {b['time'] for b in bars}
        markers = []
        for o in self.orders:
            # Boundary fills are visible immediately on the just-closed candle.
            # Higher frames may still be forming: anchor to the last CLOSED candle.
            eligible = [t for t in times if t <= (o['time']-1)//seconds*seconds]
            t = max(eligible) if eligible else -1
            if bars and o['time'] < bars[0]['time']:
                continue
            if bars and bars[-1]['time'] != last_complete and o['time'] > bars[-1]['time']+seconds:
                continue
            if t not in times:
                continue
            buy = o['side']=='BUY'
            markers.append(dict(id=o['id'],position_id=o.get('position_id'),action=o['action'],
                                price=o['price'],executed_at=o['time'],
                                time_precision='bar' if o.get('reason','').startswith(('STOP_', 'TAKE_')) else 'snapshot',
                                time=t,position='belowBar' if buy else 'aboveBar',color='#44c4b0' if buy else '#e47c80',
                                shape='arrowUp' if buy else 'arrowDown',
                                text=('平倉' if o['action']=='CLOSE' else '首筆' if o['action']=='FIRST' else '加單')+' '+o['lot']))
        return dict(bars=bars,markers=sorted(markers,key=lambda x:(x['time'],x['executed_at'],x['id'])),
                    source=self.data_source,interval=interval,focus=navigation,
                    analysis=technical_analysis(self.bars[:self.cursor],seconds,self.clock))

    def action(self, side: str) -> str:
        if not self.positions:
            return 'FIRST'
        return 'ADD' if all(p['side']==side for p in self.positions) else 'OPPOSITE'

    def retrieve(self, side: str, action: str, lot: D, typical_lot: D | None = None) -> dict:
        same = [p for p in self.positions if p['side']==side]
        total = sum((D(p['lot']) for p in same),D(0))
        distance = None
        if total:
            avg = sum(D(p['lot'])*D(p['entry']) for p in same)/total
            price = D(self.quote()['ask' if side=='BUY' else 'bid'])
            distance = (price-avg)/avg*100*(1 if side=='BUY' else -1)
        query_candidate = None
        if self.cases.source == 'trader_history' and '合成' not in self.data_source:
            self.cases.ensure_candidate_profiles()
            if self.candidate_session_gaps is None:
                self.candidate_session_gaps=set()
                if self.cases.candidate_profile_status == 'READY':
                    evidence=Path(__file__).resolve().parents[1]/'private'/'price_only_probe_20261013'/'candidate_session_evidence_PRIVATE.json'
                    if evidence.exists():
                        data=json.loads(evidence.read_text(encoding='utf-8'))
                        if data.get('method') == 'two_cache_scheduled_gap_candidate_v1' and data.get('production_enabled') is False:
                            self.candidate_session_gaps={(row['start_utc'],row['end_utc']) for row in data['intervals']}
            visible = self.bars[:self.cursor]
            coverage = classify_coverage(visible,self.clock,self.candidate_session_gaps)
            query_candidate = profile_before_entry(visible,self.clock,coverage)
        return self.cases.retrieve(side,action,lot,self.clock,prior_count=len(same),prior_lot=total,signed_distance=distance,typical_lot=typical_lot,
                                   query_market=market_snapshot(self.bars[:self.cursor],self.clock),query_candidate=query_candidate)

    def create_draft(self, side: str, lot: str, sl: str | None, tp: str | None, typical_lot: str | None = None,
                     order_type: str = 'MARKET', limit_price: str | None = None) -> dict:
        with self.lock:
            if self.mode != 'replay':
                raise DomainError('券商模擬帳戶未連線，不能送單；請切回歷史回放',503)
            if side not in ('BUY','SELL'):
                raise DomainError('請選BUY或SELL')
            qty = amount(lot,'手數')
            if qty>D(100) or qty%D('.01')!=0:
                raise DomainError('手數範圍0.01至100，間隔0.01')
            quote = self.quote()
            current = D(quote['ask' if side=='BUY' else 'bid'])
            if order_type not in ('MARKET','LIMIT'):
                raise DomainError('不支援的委託類型')
            if order_type == 'LIMIT':
                if limit_price in (None,''):
                    raise DomainError('限價單必須輸入限價')
                price = amount(limit_price,'限價')
                if price % D('.01'):
                    raise DomainError('限價須以0.01為單位')
                if side == 'BUY' and price >= current:
                    raise DomainError('買進限價須低於目前買進價')
                if side == 'SELL' and price <= current:
                    raise DomainError('賣出限價須高於目前賣出價')
            else:
                if limit_price not in (None,''):
                    raise DomainError('市價單不接受限價')
                price = current
            stop = amount(sl,'停損') if sl not in (None,'') else None
            target = amount(tp,'停利') if tp not in (None,'') else None
            sign = 1 if side=='BUY' else -1
            if stop is not None and (stop-price)*sign>=0:
                raise DomainError('停損必須在下單價格的不利方向')
            if target is not None and (target-price)*sign<=0:
                raise DomainError('停利必須在下單價格的有利方向')
            before = sum((D(p['lot']) for p in self.positions),D(0))
            same = [p for p in self.positions if p['side']==side]
            same_qty = sum((D(p['lot']) for p in same),D(0))
            average = (sum((D(p['entry'])*D(p['lot']) for p in same),D(0))+price*qty)/(same_qty+qty)
            scenarios = []
            for move in (D(-5)*sign,D(-10)*sign,D(-25)*sign):
                value = (move-D('.30')*sign)*qty*100*sign
                for p in self.positions:
                    close = D(quote['bid' if p['side']=='BUY' else 'ask'])+move
                    value += (close-D(p['entry']))*D(p['lot'])*100*(1 if p['side']=='BUY' else -1)
                scenarios.append(dict(move=money(move),loss=money(-value)))
            warnings = []
            if stop is None:
                warnings.append('未設定停損；價格情境不是損失上限')
            if order_type == 'LIMIT':
                warnings.append('限價單確認後先待成交；情境依指定限價試算，觸價前市場與持倉可能改變')
                warnings.append('回放以已收K棒高低價判斷觸價；無逐筆先後、排隊、滑價或同棒停損停利重建')
            if self.positions:
                warnings.append('加單增加總部位；均價改善不代表風險降低')
                if any(p.get('sl') is None for p in self.positions):
                    warnings.append('既有部位含未設定停損的訂單')
            if self.action(side)=='OPPOSITE':
                warnings.append('反向／混合持倉：此回放採逐筆持倉，不能當券商淨額模式')
            stop_loss = abs(price-stop)*qty*100 if stop is not None else None
            rr = abs(target-price)/abs(stop-price) if target is not None and stop is not None else None
            retrieval = self.retrieve(side,self.action(side),qty,amount(typical_lot,'平常手數') if typical_lot else None)
            explanation = (f'本次已收 K 線盤面列出完整三週期 {retrieval["total"]} 群、'
                           f'五分鐘限定 {retrieval.get("five_minute_only_total",0)} 群歷史近鄰；'
                           '先比較收盤路徑及指標，再按固定三段型態重排。足夠相似門檻尚未校準。'
                           if retrieval.get('comparison',{}).get('mode') == 'candidate_market' else
                           f'已找到 {retrieval["total"]} 個合成示範操作候選。此資料沒有歷史盤面相似度。')
            draft = dict(id=uuid4().hex,revision=self.version,side=side,lot=str(qty),sl=str(stop) if stop else None,
                         tp=str(target) if target else None,price=money(price),action=self.action(side),status='REVIEW',
                         order_type=order_type,limit_price=money(price) if order_type=='LIMIT' else None,
                         risk=dict(before_lot=str(before),after_lot=str(before+qty),average_entry=money(average),
                                   stop_loss_usd=money(stop_loss) if stop_loss is not None else None,
                                   reward_risk=money(rr) if rr is not None else None,scenarios=scenarios,warnings=warnings),
                         retrieval=retrieval,
                         explanation=explanation+f'新增後總部位為 {before+qty} 手。請核對下列風險後自行確認。')
            self.drafts[draft['id']] = draft
            return draft

    def confirm(self, draft_id: str, revision: int, key: str) -> dict:
        with self.lock:
            if not key or len(key)>128:
                raise DomainError('缺少有效確認識別碼')
            cache_key = draft_id+':'+key
            if cache_key in self.confirmations:
                return dict(self.confirmations[cache_key],state=self.state())
            if self.mode!='replay':
                raise DomainError('券商模擬帳戶未連線',503)
            draft = self.drafts.get(draft_id)
            if not draft or draft['status']!='REVIEW':
                raise DomainError('訂單已取消或確認，不能再次送出',409)
            if revision != self.version or draft['revision']!=self.version:
                raise DomainError('價格或帳戶已更新，請重新檢查訂單',409)
            ident = uuid4().hex[:10]
            if draft.get('order_type') == 'LIMIT':
                self.pending_orders.append(dict(id=ident,side=draft['side'],lot=draft['lot'],limit_price=draft['limit_price'],
                                                sl=draft['sl'],tp=draft['tp'],created_at=self.clock,action=draft['action'],status='PENDING'))
                draft['status']='PENDING'
                status='PENDING'
            else:
                pos = dict(id=ident,side=draft['side'],lot=draft['lot'],entry=draft['price'],sl=draft['sl'],tp=draft['tp'],opened_at=self.clock)
                self.positions.append(pos)
                self.orders.append(dict(id=ident,position_id=ident,side=pos['side'],lot=pos['lot'],price=pos['entry'],status='FILLED',time=self.clock,action=draft['action'],order_type='MARKET',pnl=None))
                draft['status']='FILLED'
                status='FILLED'
            self.version += 1
            result = dict(status=status,order_id=ident,state=self.state())
            self.confirmations[cache_key]=result
            return result

    def cancel_pending(self, order_id: str) -> dict:
        with self.lock:
            pending = next((p for p in self.pending_orders if p['id']==order_id),None)
            if not pending:
                raise DomainError('待成交限價單不存在或已觸價',409)
            self.pending_orders.remove(pending)
            self.version += 1
            return dict(status='CANCELLED',order_id=order_id,state=self.state())

    def cancel(self, draft_id: str) -> dict:
        with self.lock:
            draft=self.drafts.get(draft_id)
            if not draft or draft['status']!='REVIEW':
                raise DomainError('草稿已失效',409)
            draft['status']='CANCELLED'
            return dict(status='CANCELLED')

    def _close_at(self,p:dict,price:D,reason:str) -> dict:
        pnl=(price-D(p['entry']))*D(p['lot'])*100*(1 if p['side']=='BUY' else -1)
        self.balance+=pnl
        self.positions.remove(p)
        self.pending_orders[:]=[o for o in self.pending_orders if o.get('position_id')!=p['id']]
        order=dict(id=uuid4().hex[:10],side='SELL' if p['side']=='BUY' else 'BUY',lot=p['lot'],price=money(price),
                   position_id=p['id'],status='FILLED',time=self.clock,action='CLOSE',pnl=money(pnl),reason=reason)
        self.orders.append(order)
        self.version+=1
        return dict(status='FILLED',order_id=order['id'],state=self.state())

    def close(self, position_id:str,key:str) -> dict:
        with self.lock:
            if not key or len(key)>128:
                raise DomainError('缺少有效確認識別碼')
            cache=position_id+':'+key
            if cache in self.close_results:
                return dict(self.close_results[cache],state=self.state())
            if self.mode!='replay':
                raise DomainError('券商模擬帳戶未連線',503)
            p=next((p for p in self.positions if p['id']==position_id),None)
            if not p:
                raise DomainError('部位已平倉或不存在',409)
            result=self._close_at(p,D(self.quote()['bid' if p['side']=='BUY' else 'ask']),'MANUAL')
            self.close_results[cache]=result
            return result

    def step(self, count:int=1) -> dict:
        with self.lock:
            if self.mode!='replay':
                raise DomainError('只有回放模式可以推進時間')
            if count not in (1,6,12):
                raise DomainError('只可推進1、6或12根')
            if self.cursor+count>len(self.bars):
                raise DomainError('已到本次回放範圍末端')
            for _ in range(count):
                bar=self.bars[self.cursor]
                self.cursor+=1
                for p in list(self.positions):
                    buy=p['side']=='BUY'
                    # BID OHLC; derive sell ASK with the explicit constant spread model.
                    adjust=D(0) if buy else D('.30')
                    lo=D(bar['low'])+adjust; hi=D(bar['high'])+adjust; opening=D(bar['open'])+adjust
                    stop=D(p['sl']) if p['sl'] else None
                    target=D(p['tp']) if p['tp'] else None
                    if stop is not None and (lo<=stop if buy else hi>=stop):
                        px=min(stop,opening) if buy else max(stop,opening)
                        self._close_at(p,px,'STOP_LOSS_CONSERVATIVE')
                    elif target is not None and (hi>=target if buy else lo<=target):
                        self._close_at(p,target,'TAKE_PROFIT')
                for pending in list(self.pending_orders):
                    limit = D(pending['limit_price'])
                    if pending.get('intent')=='CLOSE':
                        p=next((p for p in self.positions if p['id']==pending['position_id']),None)
                        if p is None:
                            self.pending_orders.remove(pending);continue
                        adjustment=D(0) if p['side']=='BUY' else D('.30')
                        touched=D(bar['high'])>=limit if p['side']=='BUY' else D(bar['low'])+adjustment<=limit
                        if touched:self._close_at(p,limit,'LIMIT_CLOSE')
                        continue
                    touched = D(bar['low'])+D('.30') <= limit if pending['side']=='BUY' else D(bar['high']) >= limit
                    if not touched:
                        continue
                    self.pending_orders.remove(pending)
                    ident = pending['id']
                    action = self.action(pending['side'])
                    pos = dict(id=ident,side=pending['side'],lot=pending['lot'],entry=pending['limit_price'],
                               sl=pending['sl'],tp=pending['tp'],opened_at=self.clock)
                    self.positions.append(pos)
                    self.orders.append(dict(id=ident,position_id=ident,side=pos['side'],lot=pos['lot'],price=pos['entry'],
                                            requested_price=pending['limit_price'],status='FILLED',time=self.clock,action=action,
                                            order_type='LIMIT',pnl=None))
                self.version+=1
            return self.state()
