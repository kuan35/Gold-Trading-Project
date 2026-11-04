"""Pure display-only SL/TP arithmetic. No broker requests, drafts or trading authority."""
from datetime import datetime,timezone
from decimal import Decimal
from .engine import amount,DomainError
from .broker_orders import _volume,_price

def _margin(entry,quantity,side,kind,expected,clock,leverage):
 result=dict(source='UNAVAILABLE',amount_usd=None,leverage=None,
             reason='槓桿設定無效，暫不計算保證金ROI。')
 if kind=='MARKET' and expected and expected.get('status')=='AVAILABLE' and expected.get('currency')=='USD':
  try:
   age=clock-datetime.fromisoformat(expected['updated_at_utc']).timestamp()
   margin=amount(expected.get('buy' if side=='BUY' else 'sell'),'預估保證金')
   if not 0<=age<5:raise ValueError()
   return dict(result,source='BROKER_EXPECTED',amount_usd=format(margin,'.2f'),
               reason='券商依現價回傳的預估保證金；實際占用金額仍以成交回報為準。',_amount=margin)
  except (DomainError,KeyError,TypeError,ValueError,ArithmeticError):pass
 try:
  ratio=amount(leverage,'試算槓桿')
  if not 1<=ratio<=10000:raise ValueError()
  margin=entry*quantity/ratio
  return dict(result,source='LEVERAGE_ESTIMATE',amount_usd=format(margin,'.2f'),leverage=format(ratio,'f'),_amount=margin,
              reason='以擬進場價×盎司數÷槓桿估計；此槓桿是試算假設，未核實商品的動態槓桿。')
 except (DomainError,TypeError,ValueError,ArithmeticError):return result


def ticket_preview(snapshot,draft,*,now=None,leverage='200',expected_margin=None):
 result=dict(status='WAITING',reason='請先填寫方向、單型與有效手數。',entry_price=None,quantity_oz=None,sl=None,tp=None,margin_roi_pct=None,
             margin=None,basis='價格報酬率＝方向調整價差÷擬進場價；預估保證金ROI＝名目損益÷預估保證金。均未扣佣金、隔夜費與滑價。',quote_time_utc=(snapshot.get('quote') or {}).get('source_time_utc'))
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
 margin=_margin(entry,quantity,side,kind,expected_margin,clock,leverage)
 margin_amount=margin.pop('_amount',None)
 def level(key):
  row=dict(status='UNSET',reason='尚未設定',price=None,pnl_usd=None,price_return_pct=None,margin_roi_pct=None)
  if not draft.get(key):return row
  try:value=_price(draft[key],key,digits)
  except (DomainError,TypeError,ValueError,ArithmeticError):return dict(row,status='INVALID',reason='請輸入有效價格。')
  delta=(value-entry)*sign
  if (key=='sl' and delta>=0) or (key=='tp' and delta<=0):return dict(row,status='INVALID_SIDE',reason='停損須在虧損方向，停利須在獲利方向。')
  return dict(row,status='AVAILABLE',reason=None,price=str(value),pnl_usd=format(delta*quantity,'.2f'),price_return_pct=format(delta/entry*100,'.4f'),
              margin_roi_pct=format(delta*quantity/margin_amount*100,'.4f') if margin_amount else None)
 return dict(result,status='AVAILABLE',reason=None,entry_price=str(entry),quantity_oz=str(quantity),margin=margin,sl=level('sl'),tp=level('tp'),conditional_on_fill=kind=='LIMIT')
