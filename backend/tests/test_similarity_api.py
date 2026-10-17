from fastapi.testclient import TestClient
from backend.app import app, engine


def test_order_size_does_not_change_local_candidate_case_order():
    engine.mode='replay'
    engine.reset()
    with TestClient(app) as client:
        q=client.get('/api/cases',params={'lot':'.1','typical_lot':'.1'}).json()
        draft=client.post('/api/drafts',json={'side':'BUY','lot':'.1','typical_lot':'.1'}).json()
        expected='direction_and_market' if engine.cases.source == 'trader_history' else 'relative_lot'
        assert draft['retrieval']['comparison']['basis']==expected
        assert q['comparison']['basis']==expected
        assert q['total']==draft['retrieval']['total']
        assert [row['id'] for row in q['cases']]==[row['id'] for row in draft['retrieval']['cases']]
        assert not engine.positions


def test_invalid_baseline_returns_domain_error_not_silent_fallback():
    engine.mode='replay'
    engine.reset()
    with TestClient(app) as client:
        assert client.get('/api/cases?typical_lot=NaN').status_code==400
        assert client.post('/api/drafts',json={'side':'BUY','lot':'.1','typical_lot':'0'}).status_code==400
