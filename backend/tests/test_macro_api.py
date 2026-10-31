from fastapi.testclient import TestClient
from backend import app as module
from backend.tests.test_macro_assistant import feed

def test_gold_api_is_local_readonly_and_knowledge_does_not_require_quote_or_calendar(monkeypatch):
 monkeypatch.setattr(module.macro_calendar,'snapshot',lambda **k:(_ for _ in ()).throw(AssertionError('knowledge should not fetch')))
 client=TestClient(module.app)
 r=client.post('/api/assistant/gold-chat',json={'message':'CPI是什麼','provider':'program'})
 assert r.status_code==200 and r.json()['draft'] is None and r.json()['market_status']=='INFORMATION'
 assert client.post('/api/assistant/gold-chat',json={'message':'幫我買進0.1手'}).status_code==400
 assert client.post('/api/assistant/gold-chat',headers={'Origin':'https://evil.example'},json={'message':'CPI是什麼'}).status_code==403

def test_calendar_api_preserves_missing_values_and_no_extra_urls(monkeypatch):
 monkeypatch.setattr(module.macro_calendar,'snapshot',lambda **k:feed())
 client=TestClient(module.app);r=client.get('/api/assistant/macro-calendar')
 assert r.status_code==200 and r.json()['events'][0]['consensus'] is None
 r=client.post('/api/assistant/gold-chat',json={'message':'本週重大經濟事件','provider':'program'})
 assert r.status_code==200 and r.json()['macro_context']['snapshot_id']!='public-feed'
 assert r.json()['macro_context']['events']==[] and '本週' in r.json()['macro_context']['requested_window']
 assert client.post('/api/assistant/gold-chat',json={'message':'CPI是什麼','url':'http://127.0.0.1/secret'}).status_code==422
