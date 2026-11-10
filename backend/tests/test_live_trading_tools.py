"""LIVE trade plans, reminders and risk sizing stay in LIVE-only stores and never send."""
import importlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.live_orders import LiveBrokerOrders
from backend.live_risk import LiveLimits
from backend.trade_alerts import LocalAlerts
from backend.trade_plans import TradePlanStore
from backend.tests.test_live_api import local_request
from backend.tests.test_live_orders import FakeLiveStream


app = importlib.import_module('backend.app')


def iso(seconds=None):
    value = datetime.now(timezone.utc).timestamp() if seconds is None else seconds
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def forbidden(*args, **kwargs):
    raise AssertionError('LIVE trading tools must not use DEMO or read-only streams here')


def live_stream():
    stream = FakeLiveStream()
    stamp = iso()
    stream.value.update(connection_status='CONNECTED', bars={'5m': []},
                        history={'broker_deals': {'status': 'CURRENT', 'items': [], 'has_more': False}})
    stream.value['quote']['source_time_utc'] = stamp
    stream.value['account'].update(updated_at_utc=stamp, pnl_status='CURRENT', pnl_updated_at_utc=stamp)
    stream.query_snapshot = stream.snapshot
    stream.activity_snapshot = stream.snapshot
    return stream


@pytest.fixture
def live(monkeypatch, tmp_path):
    stream = live_stream()
    stamp = iso()
    demo = dict(environment='demo', connection_status='CONNECTED',
                quote=dict(status='CURRENT', bid='2500.00', ask='2500.20', source_time_utc=stamp, age_seconds=0),
                account=dict(account_key='demo-hash', status='CURRENT', currency='USD', equity='1000',
                             pnl_status='CURRENT', updated_at_utc=stamp, pnl_updated_at_utc=stamp,
                             positions=[], pending_orders=[]),
                symbol=dict(stream.value['symbol']), bars={'5m': []})
    monkeypatch.setattr(app, 'live_trade_stream', stream)
    monkeypatch.setattr(app, 'live_readonly_stream', SimpleNamespace(snapshot=forbidden, query_snapshot=forbidden,
                                                                    activity_snapshot=forbidden))
    monkeypatch.setattr(app, 'demo_market_stream', SimpleNamespace(snapshot=lambda: dict(demo),
                                                                  query_snapshot=forbidden, place_order=forbidden))
    monkeypatch.setattr(app, 'live_broker_orders', LiveBrokerOrders(
        stream, tmp_path / 'live-orders.sqlite3', limits_provider=lambda: LiveLimits('200', '0.5')))
    monkeypatch.setattr(app, 'trade_plans', TradePlanStore(tmp_path / 'demo-plans.sqlite'))
    monkeypatch.setattr(app, 'live_trade_plans', TradePlanStore(tmp_path / 'live-plans.sqlite'))
    monkeypatch.setattr(app, 'trade_alerts', LocalAlerts(tmp_path / 'demo-alerts.sqlite'))
    monkeypatch.setattr(app, 'live_trade_alerts', LocalAlerts(tmp_path / 'live-alerts.sqlite', environment='live'))
    return SimpleNamespace(stream=stream, demo=demo)


def body(response):
    return json.loads(response.body)


def test_live_draft_saves_plan_only_in_live_store_and_confirm_attaches_receipt(live):
    draft = body(app.broker_live_draft(local_request(), app.BrokerDraftInput(
        side='BUY', lot='0.1', order_type='MARKET', sl='2490.20', tp='2510.20',
        plan_note='突破後回測', conversation_id='chat-live')))
    assert draft.get('plan_id'), draft.get('plan_record_error')
    assert live.stream.calls == []
    saved = app.live_trade_plans.list('live-hash')
    assert saved['total'] == 1 and saved['items'][0]['note'] == '突破後回測'
    assert saved['items'][0]['environment'] == 'live'
    assert app.trade_plans.list('live-hash')['total'] == 0

    app.broker_live_confirm(local_request(), draft['id'], app.BrokerConfirmInput(
        revision=draft['revision'], idempotency_key='human-click'))
    assert len(live.stream.calls) == 1
    listed = body(app.live_trading_plan_list(local_request(), limit=50, offset=0))
    assert listed['status'] == 'AVAILABLE'
    assert listed['items'][0]['receipt']['status'] == 'ACCEPTED'
    assert body(app.trading_plan_list(local_request(), limit=50, offset=0))['total'] == 0


def test_live_plan_detail_review_and_discussion_scope(live):
    draft = body(app.broker_live_draft(local_request(), app.BrokerDraftInput(
        side='BUY', lot='0.1', sl='2490.20', plan_note='計畫')))
    plan_id = draft['plan_id']
    detail = body(app.live_trading_plan_detail(local_request(), plan_id))
    assert detail['note'] == '計畫' and 'snapshot_bundle' not in detail
    reviewed = body(app.live_trading_plan_review(local_request(), plan_id, app.PlanReviewInput(
        revision=1, note='有照做', adherence='YES', lesson='停損合理')))
    assert reviewed['revision'] == 2 and reviewed['adherence'] == 'YES'
    live.stream.value['account']['account_key'] = 'other-live-account'
    with pytest.raises(Exception, match='找不到此交易計畫'):
        app.live_trading_plan_detail(local_request(), plan_id)


def test_live_alerts_use_live_store_and_only_live_snapshots_trigger(live):
    created = body(app.live_trading_alert_create(local_request(), app.AlertInput(
        name='突破', kind='PRICE', field='bid', comparator='GTE', threshold='2501.00')))
    listed = body(app.live_trading_alert_list(local_request()))
    assert listed['status'] == 'AVAILABLE' and [row['id'] for row in listed['items']] == [created['id']]
    assert app.trade_alerts.list('live-hash')['items'] == []
    paused = body(app.live_trading_alert_update(local_request(), created['id'], app.AlertUpdateInput(
        revision=created['revision'], enabled=False)))
    assert paused['state'] == 'PAUSED'
    app.live_trading_alert_delete(local_request(), created['id'], revision=paused['revision'])
    assert body(app.live_trading_alert_list(local_request()))['items'] == []


def test_alert_environment_gate(tmp_path):
    now = datetime.now(timezone.utc).timestamp()
    rule = dict(name='突破', kind='PRICE', field='bid', comparator='GTE', threshold='2501.00')
    snapshot = live_stream().snapshot()
    snapshot['quote'].update(bid='2502.00', source_time_utc=iso(now + 1))
    live_alerts = LocalAlerts(tmp_path / 'live.sqlite', environment='live')
    demo_alerts = LocalAlerts(tmp_path / 'demo.sqlite')
    live_alerts.create('live-hash', rule, now=now)
    demo_alerts.create('live-hash', rule, now=now)
    assert demo_alerts.evaluate(snapshot, now=now + 1) == []
    events = live_alerts.evaluate(snapshot, now=now + 1)
    assert [event['name'] for event in events] == ['突破']
    assert live_alerts.evaluate(dict(snapshot, environment='demo'), now=now + 2) == []


def test_live_risk_size_reads_live_account_not_demo(live):
    request = app.RiskSizeInput(draft=app.TicketPreviewInput(side='BUY', order_type='MARKET', lot='0.10',
                                                              sl='2490.20'), equity_pct='1')
    result = body(app.live_trading_risk_size(local_request(), request))
    assert result['budget_usd'] == '100.00'
    assert body(app.trading_risk_size(local_request(), request))['budget_usd'] == '10.00'


def test_live_trading_tools_reject_remote_requests(live):
    request = local_request()
    request.client.host = '10.1.2.3'
    for call in (lambda: app.live_trading_alert_list(request),
                 lambda: app.live_trading_plan_list(request, limit=50, offset=0)):
        with pytest.raises(HTTPException) as error:
            call()
        assert error.value.status_code == 403
