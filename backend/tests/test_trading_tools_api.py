"""Trading workflow APIs use only synthetic accounts and temporary storage."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import importlib
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from backend.analysis_snapshots import SnapshotStore
from backend.trade_alerts import AlertMonitor, LocalAlerts
from backend.trade_plans import TradePlanStore


app = importlib.import_module('backend.app')
SID = 'a' * 64


def iso(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


def draft():
    return dict(side='BUY', order_type='LIMIT', lot='0.5', limit_price='4000',
                sl='3990', tp='4020')


def forbidden(*args, **kwargs):
    raise AssertionError('Trading tools must not start a connection, send orders, or call a model')


@pytest.fixture
def api(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc).timestamp()
    stamp = iso(now)
    snapshot = dict(environment='demo', connection_status='CONNECTED', order_connection=True,
        quote=dict(status='CURRENT', bid='4000', ask='4000.20', source_time_utc=stamp, age_seconds=0),
        account=dict(account_key='synthetic-A', status='CURRENT', currency='USD', equity='10000',
            pnl_status='CURRENT', updated_at_utc=stamp, pnl_updated_at_utc=stamp,
            positions=[], pending_orders=[]),
        symbol=dict(lot_size_cents=10000, min_volume_cents=100, max_volume_cents=1000000,
                    step_volume_cents=100, digits=2), bars={'5m': []},
        history={'broker_deals': {'status': 'CURRENT', 'items': [], 'has_more': False}})
    calendar = dict(status='AVAILABLE', as_of_utc=stamp, sources=[dict(id='bls', status='CURRENT',
        url='https://www.bls.gov/schedule/news_release/bls.ics', fetched_at_utc=stamp, reason=None)], events=[
        dict(id='bls-official-1', title='Official Employment Situation', source='bls',
             source_url='https://www.bls.gov/schedule/news_release/bls.ics',
             scheduled_at_utc=iso(now + 3600), timing_precision='EXACT',
             status='SCHEDULED', freshness='CURRENT', fetched_at_utc=stamp)])
    calendar_calls = []

    def calendar_snapshot(*, refresh=False, **kwargs):
        assert refresh is False, 'Reminder APIs may only read the official calendar cache'
        calendar_calls.append('cache')
        return deepcopy(calendar)

    stream = SimpleNamespace(snapshot=lambda: deepcopy(snapshot), query_snapshot=forbidden,
        activity_snapshot=lambda: deepcopy(snapshot), expected_margin=lambda *a, **k: None,
        place_order=forbidden, _start=forbidden)
    broker = SimpleNamespace(create=forbidden, confirm=forbidden, status=forbidden,
        create_close=forbidden, create_cancel=forbidden, create_protection=forbidden,
        activity=lambda *a, **k: {'items': []})
    plans = TradePlanStore(tmp_path / 'plans.sqlite3')
    alerts = LocalAlerts(tmp_path / 'alerts.sqlite3')
    monitor = SimpleNamespace(running=False, last_error=None, start=forbidden, stop=lambda: None)
    monkeypatch.setattr(app, 'demo_market_stream', stream)
    monkeypatch.setattr(app, 'broker_orders', broker)
    monkeypatch.setattr(app, 'trade_plans', plans, raising=False)
    monkeypatch.setattr(app, 'trade_alerts', alerts, raising=False)
    monkeypatch.setattr(app, 'alert_monitor', monitor, raising=False)
    monkeypatch.setattr(app, 'macro_calendar', SimpleNamespace(snapshot=calendar_snapshot))
    monkeypatch.setattr(app, 'respond_context', forbidden)
    monkeypatch.setattr(app, 'analysis_snapshots', SnapshotStore())
    monkeypatch.setattr(AlertMonitor, 'start', forbidden)
    return SimpleNamespace(client=TestClient(app.app), snapshot=snapshot, now=now,
        plans=plans, alerts=alerts, monitor=monitor, stream=stream, broker=broker,
        calendar=calendar, calendar_calls=calendar_calls, monkeypatch=monkeypatch)


def seed_plan(api):
    context = dict(snapshot_id=SID, as_of_utc=iso(api.now), status='CURRENT',
                   marker='ORIGINAL_CONTEXT', case_comparison={'status': 'NO_MATCH', 'cases': []})
    charts = dict(snapshot_id=SID, query={'5m': [{'time': 100, 'close': '4000'}]}, cases=[])
    bundle = dict(snapshot_id=SID, context=context, charts=charts)
    return api.plans.capture('synthetic-A', dict(draft(), id='draft-original', revision=1),
        dict(snapshot_id=SID, message='Original evidence with no matching cases',
             case_comparison={'status': 'NO_MATCH', 'cases': []}),
        note='Original entry reason', conversation_id='chat-original', snapshot_bundle=bundle)


def alert_body():
    return dict(kind='PRICE', name='My bid reminder', field='bid', comparator='GTE', threshold='4000')


def test_risk_size_rounds_down_and_preview_returns_account_risk_without_trade_side_effects(api):
    response = api.client.post('/api/trading/risk-size', json={'draft': draft(), 'risk_usd': '105.99'})
    assert response.status_code == 200
    size = response.json()
    assert size['status'] == 'AVAILABLE' and Decimal(size['lot']) == Decimal('0.10')
    assert size['actual_risk_usd'] == '100.00' and size['budget_usd'] == '105.99'
    assert Decimal(size['actual_risk_usd']) <= Decimal(size['budget_usd'])
    preview = api.client.post('/api/broker/ticket-preview', json=draft())
    assert preview.status_code == 200
    risk = preview.json()['risk']
    assert risk['stop_loss_usd'] == '500.00' and risk['stop_equity_pct'] == '5.0000'
    assert risk['reward_risk_ratio'] == '2.0000' and risk['gold_total_risk_usd'] == '500.00'
    assert response.headers['cache-control'] == preview.headers['cache-control'] == 'no-store'
    assert api.plans.list('synthetic-A')['total'] == 0


def test_non_usd_equity_risk_is_unknown_but_nominal_usd_remains_visible(api):
    api.snapshot['account']['currency'] = 'EUR'
    result = api.client.post('/api/broker/ticket-preview', json=draft()).json()['risk']
    assert result['stop_loss_usd'] == '500.00'
    assert result['stop_equity_pct'] is None and result['gold_total_equity_pct'] is None
    response = api.client.post('/api/trading/risk-size', json={'draft': draft(), 'equity_pct': '1'})
    assert response.status_code == 200 and response.json()['status'] == 'UNAVAILABLE'
    assert response.json()['lot'] is None


@pytest.mark.parametrize('extra', [{'confirmed': True}, {'execute': True}, {'account_key': 'other'}])
def test_risk_size_rejects_unrequested_authority_and_account_fields(api, extra):
    body = dict(draft=draft(), risk_usd='100', **extra)
    assert api.client.post('/api/trading/risk-size', json=body).status_code == 422


def test_risk_size_rejects_authority_inside_draft(api):
    assert api.client.post('/api/trading/risk-size',
        json={'draft': dict(draft(), confirmed=True), 'risk_usd': '100'}).status_code == 422


def test_plan_detail_preserves_original_evidence_charts_and_unknown_receipt_after_restart(api, tmp_path):
    plan = seed_plan(api)
    api.plans.attach_receipt('synthetic-A', 'draft-original', {'status': 'UNKNOWN', 'position_id': 'p-1'})
    api.monkeypatch.setattr(app, 'trade_plans', TradePlanStore(tmp_path / 'plans.sqlite3'))
    listed = api.client.get('/api/trading/plans')
    assert listed.status_code == 200 and listed.json()['status'] == 'AVAILABLE'
    assert listed.json()['total'] == 1
    detail = api.client.get('/api/trading/plans/' + plan['id'])
    assert detail.status_code == 200 and detail.headers['cache-control'] == 'no-store'
    body = detail.json()
    assert body['note'] == 'Original entry reason'
    assert body['analysis']['case_comparison']['status'] == 'NO_MATCH'
    assert body['charts']['query']['5m'][0]['close'] == '4000'
    assert 'snapshot_bundle' not in body and 'synthetic-A' not in detail.text
    assert body['receipt']['status'] == 'UNKNOWN'
    assert body['broker_outcome']['fully_closed'] is None
    assert body['broker_outcome']['net_pnl'] is None


def test_plan_offline_read_uses_only_cached_account_and_never_crosses_account(api):
    plan = seed_plan(api)
    api.snapshot['connection_status'] = 'DISCONNECTED'
    api.snapshot['account']['status'] = 'STALE'
    assert api.client.get('/api/trading/plans/' + plan['id']).status_code == 200
    api.snapshot['account']['account_key'] = 'synthetic-B'
    assert api.client.get('/api/trading/plans').json()['items'] == []
    assert api.client.get('/api/trading/plans/' + plan['id']).status_code == 404


def test_review_revision_keeps_pretrade_reason_and_analysis_immutable(api):
    plan = seed_plan(api)
    url = '/api/trading/plans/' + plan['id'] + '/review'
    response = api.client.patch(url, json=dict(revision=1, note='Afterward review',
                                             adherence='PARTIAL', lesson='Reduce size next time'))
    assert response.status_code == 200
    reviewed = api.plans.get('synthetic-A', plan['id'])
    assert reviewed['revision'] == 2 and reviewed['review_note'] == 'Afterward review'
    assert reviewed['note'] == plan['note'] and reviewed['analysis'] == plan['analysis']
    assert reviewed['snapshot_bundle'] == plan['snapshot_bundle']
    assert api.client.patch(url, json={'revision': 1, 'note': 'stale'}).status_code == 409
    api.snapshot['account']['account_key'] = 'synthetic-B'
    assert api.client.patch(url, json={'revision': 2, 'note': 'other account'}).status_code == 404


def test_plan_discussion_passes_the_saved_context_frozen_without_fresh_market_or_model(api):
    plan = seed_plan(api)
    calls = []

    def answer(context, message, **options):
        calls.append((deepcopy(context), message, deepcopy(options)))
        return dict(message='Synthetic response', snapshot_id=SID, market_status='FROZEN',
                    draft=None, sections=[], provider='program', llm_status='disabled')

    api.monkeypatch.setattr(app, 'respond_context', answer)
    response = api.client.post('/api/trading/plans/' + plan['id'] + '/discuss',
        json=dict(message='Review the original evidence', llm_enabled=False, provider='program'))
    assert response.status_code == 200
    assert len(calls) == 1
    context, message, options = calls[0]
    assert context == plan['snapshot_bundle']['context']
    assert options['frozen'] is True and options['enabled'] is False and options['provider'] == 'program'
    assert message == 'Review the original evidence'
    assert api.plans.get('synthetic-A', plan['id'])['analysis'] == plan['analysis']


def test_alerts_crud_revision_and_single_persisted_event_are_account_scoped(api):
    response = api.client.post('/api/trading/alerts', json=alert_body())
    assert response.status_code == 200
    alert = response.json()
    api.snapshot['quote']['source_time_utc'] = iso(api.now + 1)
    assert len(api.alerts.evaluate(deepcopy(api.snapshot), now=api.now + 1)) == 1
    assert api.alerts.evaluate(deepcopy(api.snapshot), now=api.now + 2) == []
    api.snapshot['quote']['source_time_utc'] = iso(datetime.now(timezone.utc).timestamp())
    listing = api.client.get('/api/trading/alerts')
    assert listing.status_code == 200
    body = listing.json()
    assert body['status'] == 'AVAILABLE' and body['monitor_running'] is False
    assert len(body['events']) == 1 and body['events'][0]['alert_id'] == alert['id']
    assert 'synthetic-A' not in listing.text
    current = body['items'][0]
    url = '/api/trading/alerts/' + alert['id']
    assert api.client.patch(url, json={'revision': alert['revision'], 'enabled': False}).status_code == 409
    paused = api.client.patch(url, json={'revision': current['revision'], 'enabled': False})
    assert paused.status_code == 200 and paused.json()['state'] == 'PAUSED'
    api.snapshot['account']['account_key'] = 'synthetic-B'
    assert api.client.get('/api/trading/alerts').json()['items'] == []
    assert api.client.patch(url, json={'revision': paused.json()['revision'], 'enabled': True}).status_code == 404
    assert api.client.delete(url + '?revision=' + str(paused.json()['revision'])).status_code == 404
    api.snapshot['account']['account_key'] = 'synthetic-A'
    assert api.client.delete(url + '?revision=' + str(paused.json()['revision'])).status_code == 200
    assert api.client.get('/api/trading/alerts').json()['items'] == []
    assert len(api.client.get('/api/trading/alerts').json()['events']) == 1


def test_event_alert_uses_official_cached_time_and_rejects_frontend_forgery(api):
    body = dict(kind='EVENT', name='Employment reminder', event_id='bls-official-1', lead_minutes=15)
    forged = api.client.post('/api/trading/alerts', json=dict(body, event_time_utc=iso(api.now + 99999)))
    assert forged.status_code == 422
    response = api.client.post('/api/trading/alerts', json=body)
    assert response.status_code == 200
    expected = datetime.fromisoformat(api.calendar['events'][0]['scheduled_at_utc'])
    actual = datetime.fromisoformat(response.json()['event_time_utc'].replace('Z', '+00:00'))
    assert actual == expected and api.calendar_calls


@pytest.mark.parametrize('problem', ['stale_source', 'stale_event', 'date_only', 'cancelled', 'missing', 'late_lead'])
def test_event_alert_rejects_unverified_or_missed_official_schedule(api, problem):
    event = api.calendar['events'][0]
    if problem == 'stale_source': api.calendar['sources'][0]['status'] = 'STALE'
    if problem == 'stale_event': event['freshness'] = 'STALE'
    if problem == 'date_only': event.update(timing_precision='DATE_ONLY', scheduled_at_utc=None)
    if problem == 'cancelled': event['status'] = 'CANCELLED'
    if problem == 'missing': api.calendar['events'] = []
    if problem == 'late_lead': event['scheduled_at_utc'] = iso(api.now + 60)
    response = api.client.post('/api/trading/alerts',
        json=dict(kind='EVENT', name='Official release', event_id='bls-official-1', lead_minutes=15))
    assert response.status_code == 409
    assert api.alerts.list('synthetic-A')['items'] == []


def test_calendar_exposes_only_current_exact_future_events(api):
    api.calendar['events'].append(dict(api.calendar['events'][0], id='date-only', timing_precision='DATE_ONLY', scheduled_at_utc=None))
    response = api.client.get('/api/trading/calendar')
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    assert response.json()['events'] == [dict(id='bls-official-1', name='Official Employment Situation',
                                             time_utc=api.calendar['events'][0]['scheduled_at_utc'])]


@pytest.mark.parametrize('endpoint', ['plans', 'alerts'])
def test_no_account_lists_are_unavailable_instead_of_claiming_zero_records(api, endpoint):
    api.snapshot['account'] = None
    response = api.client.get('/api/trading/' + endpoint)
    assert response.status_code == 200
    assert response.json()['status'] == 'UNAVAILABLE'
    assert response.json().get('reason')


@pytest.mark.parametrize('problem', ['missing_account', 'stale_account', 'live_environment'])
def test_writes_require_a_current_demo_account(api, problem):
    plan = seed_plan(api)
    if problem == 'missing_account': api.snapshot['account'] = None
    if problem == 'stale_account': api.snapshot['account']['status'] = 'STALE'
    if problem == 'live_environment': api.snapshot['environment'] = 'live'
    assert api.client.post('/api/trading/alerts', json=alert_body()).status_code == 409
    assert api.client.patch('/api/trading/plans/' + plan['id'] + '/review',
        json={'revision': 1, 'note': 'must not save'}).status_code == 409
    assert api.client.post('/api/trading/risk-size',
        json={'draft': draft(), 'risk_usd': '100'}).status_code == 409
    assert api.plans.get('synthetic-A', plan['id'])['revision'] == 1


def test_all_trading_routes_reject_foreign_origin_and_public_host(api):
    plan = seed_plan(api)
    alert = api.alerts.create('synthetic-A', alert_body(), now=api.now)
    plan_url = '/api/trading/plans/' + plan['id']
    alert_url = '/api/trading/alerts/' + alert['id']
    requests = [
        ('POST', '/api/trading/risk-size', {'draft': draft(), 'risk_usd': '100'}),
        ('GET', '/api/trading/plans', None), ('GET', plan_url, None),
        ('PATCH', plan_url + '/review', {'revision': 1, 'note': 'forbidden'}),
        ('POST', plan_url + '/discuss', {'message': 'Review', 'llm_enabled': False}),
        ('GET', '/api/trading/alerts', None), ('POST', '/api/trading/alerts', alert_body()),
        ('PATCH', alert_url, {'revision': 1, 'enabled': False}),
        ('DELETE', alert_url + '?revision=1', None), ('GET', '/api/trading/calendar', None),
    ]
    for method, url, body in requests:
        response = api.client.request(method, url, json=body, headers={'Origin': 'https://evil.example'})
        assert response.status_code == 403, (method, url, response.text)
    public = TestClient(app.app, base_url='http://public.example')
    assert public.get('/api/trading/plans').status_code == 403
    assert public.post('/api/trading/alerts', json=alert_body()).status_code == 403
    assert api.plans.get('synthetic-A', plan['id'])['revision'] == 1
    assert api.alerts.list('synthetic-A')['items'][0]['state'] == 'ACTIVE'
