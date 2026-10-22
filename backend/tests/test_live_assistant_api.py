import importlib
from datetime import datetime,timezone
from fastapi.testclient import TestClient

module=importlib.import_module('backend.app')


def test_status_is_local_and_never_returns_credentials(monkeypatch):
    monkeypatch.setenv('GOLD_ENABLE_LLM','true')
    monkeypatch.setenv('GOLD_LLM_API_KEY','SECRET_TEST_CREDENTIAL')
    c=TestClient(module.app)
    r=c.get('/api/assistant/status')
    assert r.status_code==200 and r.headers['cache-control']=='no-store'
    assert r.json()['enabled'] and r.json()['read_only']
    assert 'SECRET_TEST' not in r.text
    assert TestClient(module.app,base_url='http://public.example').get('/api/assistant/status').status_code==403


def test_live_api_defaults_to_local_explanation_and_preserves_snapshot_source(monkeypatch):
    monkeypatch.setattr(module.demo_market_stream,'query_snapshot',lambda:dict(connection_status='CONNECTED',bars={},
        quote=dict(status='CURRENT',bid='4100.00',ask='4100.30',age_seconds=0,source_time_utc=datetime.now(timezone.utc).isoformat())))
    monkeypatch.setattr(module,'_live_retrieval',lambda *a:(_ for _ in ()).throw(AssertionError('not requested')))
    c=TestClient(module.app)
    r=c.post('/api/assistant/live-chat',json={'message':'分析目前黃金盤面','include_cases':False})
    assert r.status_code==200 and r.headers['cache-control']=='no-store'
    assert r.json()['provider']=='local_market_rules' and r.json()['draft'] is None
    assert r.json()['source']=='ctrader_demo_xauusd'
    assert '4100.00' in r.json()['message']
    assert '完整已收棒不足' in r.json()['message']


def test_live_api_filters_inputs_and_does_not_accept_order_confirmation(monkeypatch):
    monkeypatch.setattr(module.demo_market_stream,'query_snapshot',lambda:dict(connection_status='DISCONNECTED'))
    c=TestClient(module.app)
    assert c.post('/api/assistant/live-chat',json={'message':'分析','confirmed':True}).status_code==422
    assert c.post('/api/assistant/live-chat',json={'message':'分析','previous_questions':['x'*601]}).status_code==422
    assert c.post('/api/assistant/live-chat',json={'message':'分析','previous_questions':['x']*5}).status_code==422
    assert TestClient(module.app,base_url='http://public.example').post('/api/assistant/live-chat',json={'message':'分析'}).status_code==403
    assert c.post('/api/assistant/live-chat',headers={'Origin':'https://evil.example'},json={'message':'分析'}).status_code==403


def test_case_question_passes_only_deidentified_aggregate_to_responder(monkeypatch):
    s={'connection_status':'CONNECTED','quote':dict(status='CURRENT',bid='4100',ask='4100.2',age_seconds=0,source_time_utc=datetime.now(timezone.utc).isoformat())}
    monkeypatch.setattr(module.demo_market_stream,'query_snapshot',lambda:s)
    monkeypatch.setattr(module,'_live_retrieval',lambda snap,side:({'total':2,'rule_status':'MATCHED','cases':[{'account':'SECRET'}]}, {'private_query':'SECRET'}))
    def respond(context,question,**kwargs):
        assert 'SECRET' not in str(context)
        return {'draft':None,'message':'aggregate'}
    monkeypatch.setattr(module,'respond_context',respond)
    assert TestClient(module.app).post('/api/assistant/live-chat',json={'message':'相似案例有幾筆','side':'SELL'}).json()['draft'] is None
