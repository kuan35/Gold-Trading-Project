from types import SimpleNamespace
from backend.tests.test_case_analysis_api import app,setup
from fastapi.testclient import TestClient

def test_interpret_is_local_pure_and_echoes_revision(monkeypatch):
    monkeypatch.setattr(app.demo_market_stream,'query_snapshot',lambda:(_ for _ in ()).throw(AssertionError('no market')))
    c=TestClient(app.app)
    r=c.post('/api/assistant/interpret',json={'message':'如果改做空呢？','draft':{'side':'BUY','lot':'.1'},'input_revision':7})
    assert r.status_code==200
    assert r.headers['cache-control']=='no-store'
    assert r.json()['patch']=={} and r.json()['analysis_side']=='SELL' and r.json()['input_revision']==7
    assert TestClient(app.app,base_url='http://public.example').post('/api/assistant/interpret',json={'message':'做多'}).status_code==403
    assert c.post('/api/assistant/interpret',json={'message':'做多','draft':{'confirmed':True}}).status_code==422

def test_checked_order_explanation_uses_same_captured_market_and_snapshot(monkeypatch):
    s,calls,c=setup(monkeypatch)
    monkeypatch.setattr(app,'broker_orders',SimpleNamespace(create=lambda snapshot,**kw:{'id':'workspace-check','side':kw['side']}))
    r=c.post('/api/broker/drafts',json={'side':'BUY','lot':'.1','order_type':'MARKET'})
    assert r.status_code==200
    d=r.json();assert calls==['market','retrieve']
    assert d['analysis_reply']['snapshot_id']==d['analysis_snapshot_id']
    assert d['analysis_reply']['as_of_utc']==d['analysis_as_of_utc']
    assert d['analysis_reply']['market_status']=='FROZEN'

def test_no_direction_analysis_does_not_retrieve(monkeypatch):
    s,calls,c=setup(monkeypatch)
    r=c.post('/api/assistant/live-chat',json={'message':'附近支撐壓力在哪？','include_cases':False})
    assert r.status_code==200 and calls==['market']
    assert not (r.json().get('case_comparison') or {}).get('cases')

def test_readonly_analysis_waits_for_small_source_lead_without_refresh_or_relaxed_checks(monkeypatch):
    from datetime import datetime,timezone
    s,calls,c=setup(monkeypatch)
    start=datetime.fromisoformat(s['quote']['source_time_utc']).timestamp()
    monkeypatch.setattr(app,'_analysis_now',lambda:start-.165 if not waits else start+.005,raising=False)
    waits=[]
    monkeypatch.setattr(app,'_analysis_clock_wait',lambda value:waits.append(value),raising=False)
    r=c.post('/api/assistant/live-chat',json={'message':'目前盤面','include_cases':False})
    assert r.status_code==200 and calls==['market']
    assert r.json()['market_status']=='CURRENT'
    assert len(waits)==1 and .16<waits[0]<.26

def test_readonly_analysis_never_waits_across_bar_boundary_or_large_clock_lead(monkeypatch):
    from datetime import datetime,timezone
    s,calls,c=setup(monkeypatch);s['quote']['source_time_utc']=datetime.fromtimestamp(1800003600.15,timezone.utc).isoformat()
    waits=[];monkeypatch.setattr(app,'_analysis_clock_wait',lambda value:waits.append(value),raising=False)
    for now in [1800003599.95,1800003599.8]:
        monkeypatch.setattr(app,'_analysis_now',lambda:now,raising=False)
        r=c.post('/api/assistant/live-chat',json={'message':'目前盤面','include_cases':False})
        assert r.json()['market_status']!='CURRENT'
    assert not waits
