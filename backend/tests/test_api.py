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


def test_case_detail_shows_only_candidate_pre_entry_candles(client):
    result=client.get('/api/cases').json()
    detail=client.get('/api/cases/'+result['cases'][0]['id']).json()
    assert detail['markers']==[]
    assert detail['chart_reason']
    if engine.cases.source == 'trader_history':
        assert len(detail['bars'])==60
        assert detail['clock_status']=='UNKNOWN'
    else:
        assert detail['bars']==[]
        assert detail['source_kind']=='synthetic_demo'


def test_reset_invalidates_confirmation_keys(client):
    d=client.post('/api/drafts',json={'side':'BUY','lot':'0.1'}).json()
    client.post('/api/replay/reset',json={})
    response=client.post(f'/api/drafts/{d["id"]}/confirm',json={'revision':d['revision'],'idempotency_key':'gone'})
    assert response.status_code==409


def test_limit_api_places_pending_order_then_can_cancel(client):
    quote=client.get('/api/state').json()['quote']
    from decimal import Decimal
    limit=str(Decimal(quote['ask'])-Decimal('2.00'))
    draft=client.post('/api/drafts',json={'side':'BUY','lot':'0.10','order_type':'LIMIT','limit_price':limit}).json()
    assert draft['order_type']=='LIMIT'
    placed=client.post(f'/api/drafts/{draft["id"]}/confirm',json={'revision':draft['revision'],'idempotency_key':'limit-api'}).json()
    assert placed['status']=='PENDING'
    assert placed['state']['positions']==[]
    assert placed['state']['pending_orders'][0]['limit_price']==limit
    cancelled=client.post(f'/api/pending/{placed["order_id"]}/cancel',json={}).json()
    assert cancelled['status']=='CANCELLED'
    assert cancelled['state']['pending_orders']==[]
