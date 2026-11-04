from datetime import datetime,timezone
from fastapi.testclient import TestClient
from backend.tests.test_case_analysis_api import app
from backend.tests.test_ticket_preview import snapshot

def test_preview_is_readonly_local_and_rejects_trade_authority_fields(monkeypatch):
 s=snapshot();s['quote']['source_time_utc']=datetime.now(timezone.utc).isoformat()
 monkeypatch.setattr(app.demo_market_stream,'snapshot',lambda:s)
 monkeypatch.setattr(app.broker_orders,'create',lambda *a,**k:(_ for _ in ()).throw(AssertionError('preview must not create draft')))
 c=TestClient(app.app)
 body=dict(side='BUY',order_type='LIMIT',lot='0.5',limit_price='4000',sl='3990',tp='4020')
 r=c.post('/api/broker/ticket-preview',json=body)
 assert r.status_code==200 and r.json()['tp']['pnl_usd']=='1000.00'
 assert r.headers['cache-control']=='no-store' and 'id' not in r.json()
 assert c.post('/api/broker/ticket-preview',json=dict(body,confirmed=True)).status_code==422
 assert c.post('/api/broker/ticket-preview',headers={'Origin':'https://evil.example'},json=body).status_code==403

def test_market_uses_readonly_margin_and_configurable_assumption(monkeypatch):
 s=snapshot();s['quote']['source_time_utc']=datetime.now(timezone.utc).isoformat()
 monkeypatch.setattr(app.demo_market_stream,'snapshot',lambda:s)
 calls=[]
 def margin(snap,volume):
  calls.append(volume)
  return dict(status='AVAILABLE',currency='USD',buy='2000',sell='2500',updated_at_utc=s['quote']['source_time_utc'])
 monkeypatch.setattr(app.demo_market_stream,'expected_margin',margin)
 monkeypatch.setattr(app.demo_market_stream,'place_order',lambda *_:(_ for _ in ()).throw(AssertionError('no orders')))
 monkeypatch.setenv('GOLD_PREVIEW_LEVERAGE','100')
 c=TestClient(app.app)
 body=dict(side='BUY',order_type='MARKET',lot='0.5',sl='3990',tp='4020')
 r=c.post('/api/broker/ticket-preview',json=body).json()
 assert calls==[5000] and r['margin']['source']=='BROKER_EXPECTED'
 assert r['tp']['margin_roi_pct']=='49.5000'
 body.update(order_type='LIMIT',limit_price='4000')
 r=c.post('/api/broker/ticket-preview',json=body).json()
 assert calls==[5000] and r['margin']['leverage']=='100'
 assert r['tp']['margin_roi_pct']=='50.0000'
