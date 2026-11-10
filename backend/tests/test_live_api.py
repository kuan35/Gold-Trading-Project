import importlib
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.engine import DomainError
from backend.live_orders import LiveBrokerOrders
from backend.live_risk import LiveLimits
from backend.tests.test_live_orders import FakeLiveStream


app_module = importlib.import_module('backend.app')


def local_request():
    return SimpleNamespace(client=SimpleNamespace(host='127.0.0.1'),
                           url=SimpleNamespace(hostname='127.0.0.1'), headers={})


def test_live_market_and_drafts_use_distinct_route_and_manual_confirmation(monkeypatch, tmp_path):
    stream = FakeLiveStream()
    stream.value['connection_status'] = 'CONNECTED'
    stream.query_snapshot = stream.snapshot
    stream.activity_snapshot = lambda: dict(stream.snapshot(), history={})
    monkeypatch.setattr(app_module, 'live_trade_stream', stream)
    monkeypatch.setattr(app_module, 'live_broker_orders', LiveBrokerOrders(
        stream, tmp_path / 'live.sqlite3', limits_provider=lambda: LiveLimits('200', '0.5')))
    market = app_module.live_market(local_request())
    assert market.status_code == 200
    assert json.loads(market.body)['environment'] == 'live'
    response = app_module.broker_live_draft(local_request(), app_module.BrokerDraftInput(
        side='BUY', lot='0.1', order_type='MARKET', sl='2490.20', tp='2510.20'))
    assert response.status_code == 200
    draft = json.loads(response.body)
    assert stream.calls == []
    result = app_module.broker_live_confirm(local_request(), draft['id'],
        app_module.BrokerConfirmInput(revision=draft['revision'], idempotency_key='human-click'))
    assert result.status_code == 200
    assert len(stream.calls) == 1
    assert json.loads(app_module.live_activity(local_request()).body)['environment'] == 'live'


def test_live_endpoint_rejects_foreign_origin_and_never_uses_demo_stream():
    request = local_request()
    request.client.host = '10.1.2.3'
    with pytest.raises(HTTPException) as error:
        app_module.broker_live_draft(request, app_module.BrokerDraftInput(
            side='BUY', lot='0.1', sl='2490.20'))
    assert error.value.status_code == 403


def test_live_limit_close_is_unavailable(monkeypatch, tmp_path):
    stream = FakeLiveStream()
    monkeypatch.setattr(app_module, 'live_trade_stream', stream)
    monkeypatch.setattr(app_module, 'live_broker_orders', LiveBrokerOrders(
        stream, tmp_path / 'live.sqlite3', limits_provider=lambda: LiveLimits('200', '0.5')))
    with pytest.raises(DomainError, match='限價平倉'):
        app_module.broker_live_close_draft(local_request(), '1',
            app_module.BrokerCloseInput(order_type='LIMIT', limit_price='2510'))
    assert stream.calls == []
