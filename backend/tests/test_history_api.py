import importlib
from fastapi.testclient import TestClient
from backend.history_library import HistoryLibrary
from backend.tests.test_history_library import write_csv,T

def test_local_history_api_is_bounded_and_does_not_touch_replay(tmp_path,monkeypatch):
    app=importlib.import_module('backend.app');lib=HistoryLibrary(tmp_path);p=tmp_path/'bars.csv';write_csv(p);lib.build(reference=p)
    monkeypatch.setattr(app,'history_library',lib,raising=False);monkeypatch.setattr(lib,'refresh',lambda **kw:None)
    before=(app.engine.cursor,app.engine.version,list(app.engine.positions))
    client=TestClient(app.app,base_url='http://127.0.0.1:8765')
    m=client.get('/api/history/metadata');assert m.status_code==200;assert m.json()['status']=='AVAILABLE'
    response=client.get('/api/history/bars',params={'at':T,'interval':'5m','limit':10});assert response.status_code==200;assert len(response.json()['bars'])==10
    assert response.headers['cache-control']=='no-store'
    assert client.get('/api/history/bars',params={'at':T,'limit':999999}).status_code==422
    assert client.get('/api/history/bars',params={'at':T,'interval':'1s'}).status_code==422
    assert client.post('/api/history/refresh',headers={'Origin':'https://evil.invalid'}).status_code==403
    assert client.get('/api/history/bars',params={'at':T,'source':'secret'}).status_code==422
    assert before==(app.engine.cursor,app.engine.version,list(app.engine.positions))
