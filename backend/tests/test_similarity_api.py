from fastapi.testclient import TestClient
from backend.app import app, engine


def test_typical_size_is_used_consistently_in_list_and_draft():
    engine.mode='replay'
    engine.reset()
    with TestClient(app) as client:
        q=client.get('/api/cases',params={'lot':'.1','typical_lot':'.1'}).json()
        draft=client.post('/api/drafts',json={'side':'BUY','lot':'.1','typical_lot':'.1'}).json()
        assert draft['retrieval']['comparison']['basis']=='relative_lot'
        assert q['comparison']['basis']=='relative_lot'
        assert q['total']==draft['retrieval']['total']
        assert not engine.positions


def test_invalid_baseline_returns_domain_error_not_silent_fallback():
    engine.mode='replay'
    engine.reset()
    with TestClient(app) as client:
        assert client.get('/api/cases?typical_lot=NaN').status_code==400
        assert client.post('/api/drafts',json={'side':'BUY','lot':'.1','typical_lot':'0'}).status_code==400
