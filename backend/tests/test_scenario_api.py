from types import SimpleNamespace
from fastapi.testclient import TestClient
from backend import app
from backend.tests.test_case_analysis_api import setup
from backend.tests.test_case_scenarios import forward

def configure(monkeypatch):
    snap,calls,client=setup(monkeypatch)
    snap['symbol']=dict(lot_size_cents=10000,min_volume_cents=100,max_volume_cents=1000000,step_volume_cents=100)
    snap['quote'].update(bid='1999.8',ask='2000')
    monkeypatch.setattr(app,'case_forward_store',SimpleNamespace(get=forward))
    return snap,calls,client

def test_outcomes_route_is_snapshot_scoped_local_guarded_and_never_refreshes(monkeypatch):
    snap,calls,c=configure(monkeypatch)
    reply=c.post('/api/assistant/live-chat',json=dict(message='歷史後續和草稿風險',side='BUY',input_revision=4,
        draft=dict(side='BUY',lot='.1',order_type='MARKET',sl='1990',tp='2020'))).json()
    assert reply['outcome_analysis']['draft_risk']['stop_loss_usd']=='100.00'
    sid=reply['snapshot_id'];url=f'/api/assistant/snapshots/{sid}/outcomes'
    monkeypatch.setattr(app.demo_market_stream,'query_snapshot',lambda:(_ for _ in ()).throw(AssertionError('not refresh')))
    response=c.get(url,params={'case_ref':'案例甲','minutes':30})
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert response.json()['scenario']['mae_loss_usd']=='200.00'
    assert response.json()['history']['minutes']==30
    five=c.get(url,params={'case_ref':'案例甲','minutes':5})
    assert five.status_code==200
    assert len(five.json()['history']['bars'])==1
    assert five.json()['history']['minutes']==5
    assert 'PRIVATE_CASE' not in response.text and 'ACCOUNT_SECRET' not in response.text
    assert c.get(url,params={'case_ref':'PRIVATE_CASE'}).status_code==404
    assert c.get(url,params={'case_ref':'案例甲','minutes':90}).status_code==422
    assert c.get('/api/assistant/snapshots/missing/outcomes',params={'case_ref':'案例甲'}).status_code==409
    assert TestClient(app.app,base_url='http://public.example').get(url,params={'case_ref':'案例甲'}).status_code==403

def test_checked_draft_attaches_scenario_and_reuses_frozen_context(monkeypatch):
    snap,calls,c=configure(monkeypatch)
    monkeypatch.setattr(app,'broker_orders',SimpleNamespace(create=lambda snapshot,**kw:dict(id='draft',revision=1,**kw)))
    d=c.post('/api/broker/drafts',json=dict(side='BUY',lot='.1',sl='1990',input_revision=9)).json()
    a=d['analysis_reply']['outcome_analysis']
    assert a['input_revision']==9 and a['draft_risk']['stop_loss_usd']=='100.00'
    snap['quote']['ask']='2500'
    again=c.post('/api/assistant/draft-chat',json=dict(draft_id='draft',message='之前風險')).json()
    assert again['outcome_analysis']==a
