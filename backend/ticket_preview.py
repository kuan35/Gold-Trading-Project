"""Pure display-only SL/TP arithmetic. No broker requests, drafts or trading authority."""
from datetime import datetime,timezone
from decimal import Decimal
from .engine import amount,DomainError
from .broker_orders import _volume,_price

def ticket_preview(snapshot,draft,*,now=None):
 result=dict(status='WAITING',reason='請先填寫方向、單型與有效手數。',entry_price=None,quantity_oz=None,sl=None,tp=None,margin_roi_pct=None,
             basis='方向調整價差／擬進場價；名目USD未扣佣金、隔夜費與滑價，非保證金ROI。',quote_time_utc=(snapshot.get('quote') or {}).get('source_time_utc'))
 side,kind=draft.get('side'),draft.get('order_type')
 if side not in ('BUY','SELL') or kind not in ('MARKET','LIMIT'):return result
 quote=snapshot.get('quote') or {};symbol=snapshot.get('symbol') or {}
 try:
  clock=datetime.now(timezone.utc).timestamp() if now is None else now
  stamp=datetime.fromisoformat(quote['source_time_utc']).timestamp()
  if snapshot.get('environment')!='demo' or quote.get('status')!='CURRENT' or not -.1<=clock-stamp<=5 or not 0<=quote['age_seconds']<=5:raise ValueError()
 except (KeyError,TypeError,ValueError,OverflowError):return dict(result,status='UNAVAILABLE',reason='報價未就緒或已過期，暫不試算。')
 try:
  lot=amount(draft.get('lot'),'手數');_,units=_volume(lot,symbol)
  digits=symbol['digits'];entry=amount(draft.get('limit_price') if kind=='LIMIT' else quote.get('ask' if side=='BUY' else 'bid'),'擬進場價')
  _price(str(entry),'擬進場價',digits)
 except (DomainError,KeyError,TypeError,ValueError,ArithmeticError):return dict(result,reason='手數、進場價格或券商商品規格尚未有效。')
 sign=Decimal(1) if side=='BUY' else Decimal(-1);quantity=lot*units
 def level(key):
  row=dict(status='UNSET',reason='尚未設定',price=None,pnl_usd=None,price_return_pct=None)
  if not draft.get(key):return row
  try:value=_price(draft[key],key,digits)
  except (DomainError,TypeError,ValueError,ArithmeticError):return dict(row,status='INVALID',reason='請輸入有效價格。')
  delta=(value-entry)*sign
  if (key=='sl' and delta>=0) or (key=='tp' and delta<=0):return dict(row,status='INVALID_SIDE',reason='停損須在虧損方向，停利須在獲利方向。')
  return dict(row,status='AVAILABLE',reason=None,price=str(value),pnl_usd=format(delta*quantity,'.2f'),price_return_pct=format(delta/entry*100,'.4f'))
 return dict(result,status='AVAILABLE',reason=None,entry_price=str(entry),quantity_oz=str(quantity),sl=level('sl'),tp=level('tp'),conditional_on_fill=kind=='LIMIT')
