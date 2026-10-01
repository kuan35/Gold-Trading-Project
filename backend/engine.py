"""Single-session replay engine. In-memory prototype, Decimal accounting."""
from __future__ import annotations
import threading
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4
from .market import load_bars, aggregate
from .cases import CaseStore

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


class Engine:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.bars,self.data_source = load_bars()
        self.cases = CaseStore()
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
                    market=dict(change_pct=money((close-D(recent[0]['open']))/D(recent[0]['open'])*100),
                                range_pct=money((high-low)/close*100),high=money(high),low=money(low),
                                ma20=money(sum(D(b['close']) for b in recent[-20:])/20),
                                ma60=money(sum(D(b['close']) for b in recent)/len(recent))),
                    data_quality=['本機回放・固定價差0.30美元，合約100oz/lot，佣金及隔夜費未計',
                                  '目前案例依操作條件檢索；盤面對齊未核實',
                                  '成交不代表券商回報，demo API未連線'])

    def chart(self, interval: str = '5m') -> dict:
        seconds = {'5m':300,'15m':900,'1h':3600}.get(interval)
        if seconds is None:
            raise DomainError('不支援的K線週期')
        bars = aggregate(self.bars[:self.cursor],seconds,self.clock)
        times = {b['time'] for b in bars}
        markers = []
        for o in self.orders:
            # Trade happens at the start of the next bar: show only after it is closed.
            t = o['time']//seconds*seconds
            if t not in times:
                continue
            buy = o['side']=='BUY'
            markers.append(dict(time=t,position='belowBar' if buy else 'aboveBar',color='#44c4b0' if buy else '#e47c80',
                                shape='circle' if o['action']=='CLOSE' else ('arrowUp' if buy else 'arrowDown'),
                                text=('平倉' if o['action']=='CLOSE' else '首筆' if o['action']=='FIRST' else '加單')+' '+o['lot']))
        return dict(bars=bars,markers=sorted(markers,key=lambda x:x['time']),source=self.data_source,interval=interval)

    def action(self, side: str) -> str:
        if not self.positions:
            return 'FIRST'
        return 'ADD' if all(p['side']==side for p in self.positions) else 'OPPOSITE'

    def retrieve(self, side: str, action: str, lot: D) -> dict:
        same = [p for p in self.positions if p['side']==side]
        total = sum((D(p['lot']) for p in same),D(0))
        distance = None
        if total:
            avg = sum(D(p['lot'])*D(p['entry']) for p in same)/total
            price = D(self.quote()['ask' if side=='BUY' else 'bid'])
            distance = (price-avg)/avg*100*(1 if side=='BUY' else -1)
        return self.cases.retrieve(side,action,lot,self.clock,prior_count=len(same),prior_lot=total,signed_distance=distance)

    def create_draft(self, side: str, lot: str, sl: str | None, tp: str | None) -> dict:
        with self.lock:
            if self.mode != 'replay':
                raise DomainError('券商模擬帳戶未連線，不能送單；請切回歷史回放',503)
            if side not in ('BUY','SELL'):
                raise DomainError('請選BUY或SELL')
            qty = amount(lot,'手數')
            if qty>D(100) or qty%D('.01')!=0:
                raise DomainError('手數範圍0.01至100，間隔0.01')
            quote = self.quote()
            price = D(quote['ask' if side=='BUY' else 'bid'])
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
            if self.positions:
                warnings.append('加單增加總部位；均價改善不代表風險降低')
                if any(p.get('sl') is None for p in self.positions):
                    warnings.append('既有部位含未設定停損的訂單')
            if self.action(side)=='OPPOSITE':
                warnings.append('反向／混合持倉：此回放採逐筆持倉，不能當券商淨額模式')
            stop_loss = abs(price-stop)*qty*100 if stop is not None else None
            rr = abs(target-price)/abs(stop-price) if target is not None and stop is not None else None
            retrieval = self.retrieve(side,self.action(side),qty)
            draft = dict(id=uuid4().hex,revision=self.version,side=side,lot=str(qty),sl=str(stop) if stop else None,
                         tp=str(target) if target else None,price=money(price),action=self.action(side),status='REVIEW',
                         risk=dict(before_lot=str(before),after_lot=str(before+qty),average_entry=money(average),
                                   stop_loss_usd=money(stop_loss) if stop_loss is not None else None,
                                   reward_risk=money(rr) if rr is not None else None,scenarios=scenarios,warnings=warnings),
                         retrieval=retrieval,
                         explanation=f'已找到 {retrieval["total"]} 個相似操作候選。比較方向、操作種類與手數；盤面相似度尚未核實。新增後總部位為 {before+qty} 手。請核對下列風險後自行確認。')
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
            pos = dict(id=ident,side=draft['side'],lot=draft['lot'],entry=draft['price'],sl=draft['sl'],tp=draft['tp'],opened_at=self.clock)
            self.positions.append(pos)
            self.orders.append(dict(id=ident,side=pos['side'],lot=pos['lot'],price=pos['entry'],status='FILLED',time=self.clock,action=draft['action'],pnl=None))
            draft['status']='FILLED'
            self.version += 1
            result = dict(status='FILLED',order_id=ident,state=self.state())
            self.confirmations[cache_key]=result
            return result

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
        order=dict(id=uuid4().hex[:10],side='SELL' if p['side']=='BUY' else 'BUY',lot=p['lot'],price=money(price),
                   status='FILLED',time=self.clock,action='CLOSE',pnl=money(pnl),reason=reason)
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
                self.version+=1
            return self.state()
