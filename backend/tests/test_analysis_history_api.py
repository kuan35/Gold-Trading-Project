from fastapi.testclient import TestClient
from backend import app as module
from backend.analysis_snapshots import SnapshotStore
from backend.tests.test_analysis_history import capture,SID

def test_readonly_history_restores_reply_charts_and_does_not_restore_order_draft(monkeypatch):
 r,b=capture();saved=module.analysis_history.save(r,b)
 monkeypatch.setattr(module,'analysis_snapshots',SnapshotStore())
 client=TestClient(module.app)
 response=client.get('/api/assistant/analyses/'+saved['analysis_ref'])
 assert response.status_code==200 and response.json()['draft'] is None
 assert response.json()['sections'][0]['text']=='全部段落'
 charts=client.get('/api/assistant/snapshots/'+SID+'/charts')
 assert charts.status_code==200 and charts.json()==b['charts']
 assert client.post('/api/assistant/draft-chat',json={'draft_id':'expired-order','message':'繼續說明'}).status_code!=200
 assert client.delete('/api/assistant/analyses/'+saved['analysis_ref']).status_code==200
 assert client.get('/api/assistant/analyses/'+saved['analysis_ref']).status_code==404

def test_knowledge_replies_are_archived_and_write_failure_is_explicit(monkeypatch):
 client=TestClient(module.app)
 response=client.post('/api/assistant/gold-chat',json={'message':'什麼是停損','provider':'program'})
 assert response.status_code==200 and response.json().get('analysis_ref')
 original=response.json();restored=client.get('/api/assistant/analyses/'+original['analysis_ref']).json()
 assert original['sections']==restored['sections']
 monkeypatch.setattr(module.analysis_history,'save',lambda *a,**k:(_ for _ in ()).throw(OSError('disk unavailable')))
 failed=client.post('/api/assistant/gold-chat',json={'message':'什麼是停損','provider':'program'}).json()
 assert not failed.get('analysis_ref') and failed.get('analysis_history_error')
