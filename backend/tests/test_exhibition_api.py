import importlib
from fastapi.testclient import TestClient
from backend.analysis_snapshots import SnapshotStore
from backend.tests.test_case_review import bundle

module=importlib.import_module('backend.app')


def test_new_routes_are_local_snapshot_bound_and_read_only(monkeypatch):
    b=bundle();store=SnapshotStore();store.put(b)
    monkeypatch.setattr(module,'analysis_snapshots',store)
    monkeypatch.setattr(module.live_readonly_stream,'query_snapshot',lambda:dict(environment='live',read_only=True,order_connection=False))
    c=TestClient(module.app);sid=b['snapshot_id']
    assert c.get('/api/live-readonly').json()['read_only'] is True
    assert c.post('/api/live-readonly',json={'action':'BUY'}).status_code==405
    assert c.get('/api/assistant/snapshots/'+sid+'/case-preview').json()['snapshot_id']==sid
    r=c.post('/api/assistant/snapshots/'+sid+'/case-review',json={})
    assert r.status_code==200 and r.json()['provider']=='program'
    assert c.post('/api/assistant/snapshots/missing/case-review',json={}).status_code==409
    assert c.post('/api/assistant/snapshots/'+sid+'/case-review',json={'confirm':True}).status_code==422
    foreign=TestClient(module.app,base_url='http://external.example')
    assert foreign.get('/api/live-readonly').status_code==403
    assert foreign.get('/api/assistant/snapshots/'+sid+'/case-preview').status_code==403


def test_selected_review_and_preview_echo_same_case_and_reject_unknown_ref(monkeypatch):
    b=bundle();store=SnapshotStore();store.put(b);monkeypatch.setattr(module,'analysis_snapshots',store)
    c=TestClient(module.app);base='/api/assistant/snapshots/'+b['snapshot_id']
    result=c.post(base+'/case-review',json={'case_ref':'案例乙'}).json()
    assert result['case_ref']=='案例乙' and len(result['sections'])==3
    image=c.get(base+'/case-preview',params={'case_ref':'案例乙'}).json()
    assert image['case_ref']=='案例乙' and image['rows']==['查詢','案例乙']
    assert c.post(base+'/case-review',json={'case_ref':'missing'}).status_code==404
    assert c.get(base+'/case-preview',params={'case_ref':'missing'}).status_code==404
