from datetime import datetime,timezone
from copy import deepcopy
from backend.ticket_preview import ticket_preview

NOW=1800000000
def snapshot():return dict(environment='demo',quote=dict(status='CURRENT',bid='4000',ask='4000.20',age_seconds=0,source_time_utc=datetime.fromtimestamp(NOW,timezone.utc).isoformat()),symbol=dict(lot_size_cents=10000,min_volume_cents=100,max_volume_cents=100000,step_volume_cents=100,digits=2))
def draft(**kw):return dict(side='BUY',lot='0.5',order_type='LIMIT',limit_price='4000',sl='3990',tp='4020',**kw)
def test_buy_and_sell_decimal_price_returns_and_nominal_usd():
 q=draft();r=ticket_preview(snapshot(),q,now=NOW)
 assert r['status']=='AVAILABLE' and r['quantity_oz']=='50.0'
 assert r['sl']['pnl_usd']=='-500.00' and r['sl']['price_return_pct']=='-0.2500'
 assert r['tp']['pnl_usd']=='1000.00' and r['tp']['price_return_pct']=='0.5000'
 q.update(side='SELL',sl='4020',tp='3990');r=ticket_preview(snapshot(),q,now=NOW)
 assert r['sl']['pnl_usd']=='-1000.00' and r['tp']['pnl_usd']=='500.00'
 assert r['margin_roi_pct'] is None
def test_market_uses_executable_side_and_limit_does_not_use_current_quote_as_entry():
 q=draft();q['order_type']='MARKET';r=ticket_preview(snapshot(),q,now=NOW);assert r['entry_price']=='4000.20'
 q['side']='SELL';r=ticket_preview(snapshot(),q,now=NOW);assert r['entry_price']=='4000'
 q['order_type']='LIMIT';q['limit_price']='3900';assert ticket_preview(snapshot(),q,now=NOW)['entry_price']=='3900'
def test_wrong_side_missing_stale_and_invalid_values_never_become_valid_profit():
 q=draft();q.update(sl='4010',tp='3990');r=ticket_preview(snapshot(),q,now=NOW)
 assert r['sl']['status']=='INVALID_SIDE' and r['sl']['pnl_usd'] is None
 assert r['tp']['status']=='INVALID_SIDE'
 for field,value in [('lot','NaN'),('lot','0'),('side',None),('order_type',None),('limit_price','')]:
  q=draft();q[field]=value;assert ticket_preview(snapshot(),q,now=NOW)['status']!='AVAILABLE'
 s=snapshot();s['quote']['status']='STALE';assert ticket_preview(s,draft(),now=NOW)['status']=='UNAVAILABLE'
 assert ticket_preview(snapshot(),draft(),now=NOW+6)['status']=='UNAVAILABLE'
def test_preview_is_pure_and_does_not_require_or_expose_account():
 s=snapshot();s['account']={'secret':'PRIVATE'};before=deepcopy(s)
 r=ticket_preview(s,draft(),now=NOW);assert s==before and 'PRIVATE' not in str(r)


def test_live_preview_uses_live_account_leverage_and_broker_margin_when_fresh():
 s=snapshot();s['environment']='live'
 row=draft()
 estimate=ticket_preview(s,row,now=NOW,leverage='30')
 assert estimate['status']=='AVAILABLE'
 assert estimate['margin']['leverage']=='30'
 assert estimate['margin']['source']=='LEVERAGE_ESTIMATE'
 expected=dict(status='AVAILABLE',currency='USD',buy='6000',sell='6000',
               updated_at_utc=datetime.fromtimestamp(NOW,timezone.utc).isoformat())
 broker=ticket_preview(s,row,now=NOW,leverage='30',expected_margin=expected)
 assert broker['margin']['source']=='BROKER_EXPECTED'
 assert broker['margin']['amount_usd']=='6000.00'
