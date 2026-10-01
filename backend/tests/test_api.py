import pytest
from fastapi.testclient import TestClient
from backend.app import app, engine


@pytest.fixture()
def client():
    engine.mode='replay'
    engine.reset()
    return TestClient(app)


def test_form_and_chat_both_produce_review_without_order(client):
    d=client.post('/api/drafts',json={'side':'BUY','lot':'0.1'}).json()
    assert d['status']=='REVIEW'
    result=client.post('/api/chat',json={'message':'幫我買進黃金0.05手'}).json()
    assert result['draft']['lot']=='0.05'
    assert not client.get('/api/state').json()['positions']


def test_api_cannot_close_without_user_confirmation(client):
    d=client.post('/api/drafts',json={'side':'SELL','lot':'0.1'}).json()
    p=client.post(f'/api/drafts/{d["id"]}/confirm',json={'revision':d['revision'],'idempotency_key':'fill'}).json()['state']['positions'][0]
    assert client.post(f'/api/positions/{p["id"]}/close',json={'confirmed':False,'idempotency_key':'no'}).status_code==400
    assert len(client.get('/api/state').json()['positions'])==1


def test_quote_advance_invalidates_api_draft(client):
    d=client.post('/api/drafts',json={'side':'BUY','lot':'0.1'}).json()
    client.post('/api/replay/step',json={'bars':1})
    assert client.post(f'/api/drafts/{d["id"]}/confirm',json={'revision':d['revision'],'idempotency_key':'stale'}).status_code==409


def test_demo_mode_and_unrecognized_quantity_do_not_place_order(client):
    assert client.post('/api/chat',json={'message':'買一點'}).json()['draft'] is None
    client.post('/api/mode',json={'mode':'broker_demo'})
    assert client.post('/api/drafts',json={'side':'BUY','lot':'0.1'}).status_code==503
    assert client.get('/api/state').json()['broker_connected'] is False


def test_adjustment_requires_explicit_size_and_side(client):
    response=client.post('/api/chat',json={'message':'改成0.05手','side':'SELL'}).json()
    assert response['draft']['side']=='SELL'
    assert client.post('/api/chat',json={'message':'直接下單不用確認'}).json()['draft'] is None


def test_case_detail_does_not_invent_candles(client):
    result=client.get('/api/cases').json()
    detail=client.get('/api/cases/'+result['cases'][0]['id']).json()
    assert detail['bars']==[]
    assert detail['chart_reason']


def test_reset_invalidates_confirmation_keys(client):
    d=client.post('/api/drafts',json={'side':'BUY','lot':'0.1'}).json()
    client.post('/api/replay/reset',json={})
    response=client.post(f'/api/drafts/{d["id"]}/confirm',json={'revision':d['revision'],'idempotency_key':'gone'})
    assert response.status_code==409
