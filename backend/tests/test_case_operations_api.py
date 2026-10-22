from copy import deepcopy
from fastapi.testclient import TestClient
from backend.tests.test_case_analysis_api import app,setup
from backend.tests.test_case_operations import case

def test_operations_are_frozen_with_original_analysis_and_never_reread_source(monkeypatch):
    s,calls,c=setup(monkeypatch);source=case()
    monkeypatch.setattr(app.engine.cases,'get',lambda ident:deepcopy(source) if ident=='PRIVATE_CASE' else None)
    reply=c.post('/api/assistant/live-chat',json={'message':'做多案例','side':'BUY'}).json()
    sid=reply['snapshot_id'];ref=reply['case_comparison']['cases'][0]['ref']
    source['sequence'][0]['profit']='999999'
    monkeypatch.setattr(app.engine.cases,'get',lambda *a:(_ for _ in ()).throw(AssertionError('no new source read')))
    monkeypatch.setattr(app.demo_market_stream,'query_snapshot',lambda:(_ for _ in ()).throw(AssertionError('no new market')))
    response=c.get(f'/api/assistant/snapshots/{sid}/operations',params={'case_ref':ref})
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    value=response.json();assert value['snapshot_id']==sid and value['as_of_utc']==reply['as_of_utc']
    assert value['rows'][0]['profit']=='20' and value['rows'][0]['currency'] is None
    assert value['representative']['profit']=='20'
    assert 'PRIVATE_ACCOUNT' not in response.text and 'PRIVATE_SOURCE' not in response.text and 'PRIVATE_CASE' not in response.text
    assert calls==['market','retrieve']
    assert c.get(f'/api/assistant/snapshots/{sid}/operations',params={'case_ref':'not-selected'}).status_code==404
    assert c.get('/api/assistant/snapshots/missing/operations',params={'case_ref':ref}).status_code==409
    assert TestClient(app.app,base_url='http://public.example').get(f'/api/assistant/snapshots/{sid}/operations',params={'case_ref':ref}).status_code==403

def test_missing_operations_do_not_substitute_representative_as_an_entire_sequence(monkeypatch):
    s,calls,c=setup(monkeypatch)
    monkeypatch.setattr(app.engine.cases,'get',lambda ident:None)
    reply=c.post('/api/assistant/live-chat',json={'message':'做多案例','side':'BUY'}).json()
    ref=reply['case_comparison']['cases'][0]['ref']
    value=c.get(f"/api/assistant/snapshots/{reply['snapshot_id']}/operations",params={'case_ref':ref}).json()
    assert value['status']=='UNAVAILABLE' and value['rows']==[]
