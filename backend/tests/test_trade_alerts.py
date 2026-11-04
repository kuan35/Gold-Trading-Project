from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from backend.trade_alerts import AlertError, AlertMonitor, LocalAlerts


NOW = 1800000000  # An exact five-minute boundary.


def stamp(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


def snapshot(at=NOW + 1, *, account='A', bid='4000.00', ask='4000.20'):
    return {'environment':'demo','account': {'status': 'CURRENT', 'account_key': account},
            'connection_status': 'CONNECTED',
            'quote': {'status': 'CURRENT', 'source_time_utc': stamp(at),
                      'bid': bid, 'ask': ask}, 'bars': {'5m': []}}


def price(**changes):
    return {'kind': 'PRICE', 'name': 'Bid reached level', 'field': 'bid',
            'comparator': 'GTE', 'threshold': '4000', **changes}


def test_price_is_persistent_once_and_does_not_expose_account(tmp_path):
    path = tmp_path / 'alerts.sqlite'
    store = LocalAlerts(path)
    alert = store.create('A', price(conversation_id='discussion-1'), now=NOW)
    original = snapshot()
    before = deepcopy(original)
    events = store.evaluate(original, now=NOW + 1)
    assert original == before
    assert len(events) == 1
    assert events[0]['alert_id'] == alert['id']
    assert events[0]['observed_value'] == '4000.00'
    assert events[0]['conversation_id'] == 'discussion-1'
    assert store.evaluate(snapshot(NOW + 2), now=NOW + 2) == []
    saved = LocalAlerts(path).list('A')
    assert saved['items'][0]['state'] == 'TRIGGERED'
    assert saved['events'] == events
    assert 'account_key' not in str(saved)
    assert '服務' in saved['monitoring_note']


@pytest.mark.parametrize('change', [
    {'threshold': 4000.0}, {'threshold': 'NaN'}, {'threshold': 'Infinity'},
    {'threshold': '0'}, {'threshold': '-1'}, {'field': 'mid'},
    {'comparator': 'GT'}, {'name': 'x' * 121}, {'name': ' '},
    {'kind': 'AUTO_ORDER'}, {'conversation_id': 123},
])
def test_invalid_conditions_are_rejected(tmp_path, change):
    with pytest.raises(AlertError) as error:
        LocalAlerts(tmp_path / 'a.sqlite').create('A', price(**change), now=NOW)
    assert error.value.status_code == 400


@pytest.mark.parametrize('problem', ['missing_account', 'other_account', 'account_stale',
                                   'quote_stale', 'quote_missing', 'old_quote',
                                   'future_quote', 'expired_quote', 'missing_price',
                                   'float_price', 'nan_price', 'disconnected'])
def test_invalid_or_old_sources_never_trigger(tmp_path, problem):
    store = LocalAlerts(tmp_path / 'a.sqlite')
    store.create('A', price(), now=NOW)
    value = snapshot()
    if problem == 'missing_account': value.pop('account')
    if problem == 'other_account': value['account']['account_key'] = 'B'
    if problem == 'account_stale': value['account']['status'] = 'STALE'
    if problem == 'quote_stale': value['quote']['status'] = 'STALE'
    if problem == 'quote_missing': value.pop('quote')
    if problem == 'old_quote': value['quote']['source_time_utc'] = stamp(NOW)
    if problem == 'future_quote': value['quote']['source_time_utc'] = stamp(NOW + 2)
    if problem == 'expired_quote': value['quote']['source_time_utc'] = stamp(NOW - 5)
    if problem == 'missing_price': value['quote'].pop('bid')
    if problem == 'float_price': value['quote']['bid'] = 4000.0
    if problem == 'nan_price': value['quote']['bid'] = 'NaN'
    if problem == 'disconnected': value['connection_status'] = 'DISCONNECTED'
    assert store.evaluate(value, now=NOW + 1) == []
    assert store.list('A')['events'] == []


def test_bid_ask_and_lte_are_evaluated_as_decimal_strings(tmp_path):
    store = LocalAlerts(tmp_path / 'a.sqlite')
    store.create('A', price(field='ask', comparator='LTE', threshold='4000.000000000000001'), now=NOW)
    assert store.evaluate(snapshot(ask='4000.000000000000002'), now=NOW + 1) == []
    assert len(store.evaluate(snapshot(NOW + 2, ask='4000.000000000000001'), now=NOW + 2)) == 1


def test_same_quote_is_not_reinterpreted_after_its_first_observation(tmp_path):
    store = LocalAlerts(tmp_path / 'a.sqlite')
    store.create('A', price(), now=NOW)
    assert store.evaluate(snapshot(bid='3999'), now=NOW + 1) == []
    assert store.evaluate(snapshot(bid='4001'), now=NOW + 2) == []
    assert len(store.evaluate(snapshot(NOW + 3, bid='4001'), now=NOW + 3)) == 1


def test_account_isolation_and_revision_lock(tmp_path):
    store = LocalAlerts(tmp_path / 'a.sqlite')
    alert = store.create('A', price(), now=NOW)
    assert store.list('B')['items'] == []
    for action in (lambda: store.update('B', alert['id'], 1, enabled=False),
                   lambda: store.delete('B', alert['id'], 1)):
        with pytest.raises(AlertError) as error: action()
        assert error.value.status_code == 404
    paused = store.update('A', alert['id'], alert['revision'], enabled=False)
    assert paused['state'] == 'PAUSED'
    with pytest.raises(AlertError) as error:
        store.update('A', alert['id'], alert['revision'], enabled=True)
    assert error.value.status_code == 409
    with pytest.raises(AlertError): store.delete('A', alert['id'], alert['revision'])
    store.delete('A', alert['id'], paused['revision'])
    assert store.list('A')['items'] == []


def test_resume_creates_new_generation_and_preserves_previous_event(tmp_path, monkeypatch):
    store = LocalAlerts(tmp_path / 'a.sqlite')
    alert = store.create('A', price(), now=NOW)
    assert len(store.evaluate(snapshot(), now=NOW + 1)) == 1
    triggered = store.list('A')['items'][0]
    monkeypatch.setattr('backend.trade_alerts.time.time', lambda: NOW + 2)
    active = store.update('A', alert['id'], triggered['revision'], enabled=True)
    assert active['generation'] == 2
    # Re-enabling cannot reuse a quote from the moment of resume.
    assert store.evaluate(snapshot(NOW + 2), now=NOW + 2) == []
    assert len(store.evaluate(snapshot(NOW + 3), now=NOW + 3)) == 1
    assert len(store.list('A')['events']) == 2
    store.delete('A', alert['id'], store.list('A')['items'][0]['revision'])
    assert len(store.list('A')['events']) == 2


def test_restart_takes_a_baseline_and_never_backfills_old_touch(tmp_path):
    path = tmp_path / 'a.sqlite'
    LocalAlerts(path).create('A', price(), now=NOW)
    restarted = LocalAlerts(path)
    assert restarted.evaluate(snapshot(), now=NOW + 1) == []
    assert restarted.evaluate(snapshot(), now=NOW + 2) == []
    assert len(restarted.evaluate(snapshot(NOW + 3), now=NOW + 3)) == 1


def test_closed_five_minute_condition_ignores_forming_old_and_stale_bars(tmp_path):
    store = LocalAlerts(tmp_path / 'a.sqlite')
    store.create('A', price(kind='CLOSE_5M'), now=NOW)
    # The first row ended before creation; the second has not closed.
    value = snapshot(NOW + 299)
    value['bars']['5m'] = [{'time': NOW - 300, 'close': '4100'},
                           {'time': NOW, 'close': '4100'}]
    assert store.evaluate(value, now=NOW + 299) == []
    value['quote']['source_time_utc'] = stamp(NOW + 300)
    events = store.evaluate(value, now=NOW + 300)
    assert len(events) == 1 and events[0]['observed_value'] == '4100'
    assert '收盤' in events[0]['message']
    assert '突破' not in events[0]['message']
    stale = LocalAlerts(tmp_path / 'stale.sqlite')
    stale.create('A', price(kind='CLOSE_5M'), now=NOW)
    value['quote']['source_time_utc'] = stamp(NOW + 606)
    assert stale.evaluate(value, now=NOW + 606) == []


def test_closed_bar_is_not_rechecked_with_changed_close_or_old_quote(tmp_path):
    store = LocalAlerts(tmp_path / 'a.sqlite')
    store.create('A', price(kind='CLOSE_5M'), now=NOW)
    value = snapshot(NOW + 300)
    value['bars']['5m'] = [{'time': NOW, 'close': '3999'}]
    assert store.evaluate(value, now=NOW + 300) == []
    value['bars']['5m'][0]['close'] = '4001'
    value['quote']['source_time_utc'] = stamp(NOW + 301)
    assert store.evaluate(value, now=NOW + 301) == []


def event_body(at=NOW + 600):
    return {'kind': 'EVENT', 'name': 'Official release', 'event_id': 'official-1',
            'event_time_utc': stamp(at), 'lead_minutes': 5}


def test_event_requires_continuous_monitor_crossing_and_never_backfills(tmp_path):
    store = LocalAlerts(tmp_path / 'a.sqlite')
    store.create('A', event_body(), now=NOW)
    assert store.evaluate(snapshot(NOW + 299), now=NOW + 299) == []
    assert len(store.evaluate(snapshot(NOW + 300), now=NOW + 300)) == 1
    assert store.evaluate(snapshot(NOW + 301), now=NOW + 301) == []
    other = LocalAlerts(tmp_path / 'late.sqlite')
    other.create('A', event_body(), now=NOW)
    assert other.evaluate(snapshot(NOW + 299), now=NOW + 299) == []
    assert other.evaluate(snapshot(NOW + 310), now=NOW + 310) == []
    assert other.evaluate(snapshot(NOW + 311), now=NOW + 311) == []
    fresh_process = LocalAlerts(tmp_path / 'restart.sqlite')
    fresh_process.create('A', event_body(), now=NOW)
    fresh_process = LocalAlerts(tmp_path / 'restart.sqlite')
    assert fresh_process.evaluate(snapshot(NOW + 301), now=NOW + 301) == []
    assert fresh_process.evaluate(snapshot(NOW + 600), now=NOW + 600) == []


@pytest.mark.parametrize('changes', [{'lead_minutes': -1}, {'lead_minutes': '5'},
                                     {'lead_minutes': 0},
                                     {'event_time_utc': stamp(NOW - 1)},
                                     {'event_time_utc': '2026-01-01'},
                                     {'event_id': ''}])
def test_invalid_event_time_and_lead_are_rejected(tmp_path, changes):
    with pytest.raises(AlertError):
        LocalAlerts(tmp_path / 'a.sqlite').create('A', {**event_body(), **changes}, now=NOW)


def test_event_cannot_be_rearmed_after_its_notification_time(tmp_path,monkeypatch):
    store=LocalAlerts(tmp_path/'rearm.sqlite')
    alert=store.create('A',event_body(),now=NOW)
    monkeypatch.setattr('backend.trade_alerts._clock',lambda now=None:NOW+301)
    with pytest.raises(AlertError):store.update('A',alert['id'],alert['revision'],enabled=True)
    assert store.list('A')['items'][0]['revision']==1


@pytest.mark.parametrize('environment',['live',None,'synthetic'])
def test_non_demo_snapshot_never_triggers(tmp_path,environment):
    store=LocalAlerts(tmp_path/'environment.sqlite')
    store.create('A',price(),now=NOW)
    value=snapshot();value['environment']=environment
    assert store.evaluate(value,now=NOW+1)==[]


def test_concurrent_evaluations_insert_only_one_event(tmp_path):
    store = LocalAlerts(tmp_path / 'a.sqlite')
    store.create('A', price(), now=NOW)
    with ThreadPoolExecutor(max_workers=8) as workers:
        results = list(workers.map(lambda _: store.evaluate(snapshot(), now=NOW + 1), range(16)))
    assert sum(map(len, results)) == 1
    assert len(store.list('A')['events']) == 1


def test_independent_sqlite_instances_cannot_duplicate_a_trigger(tmp_path):
    path = tmp_path / 'a.sqlite'
    first = LocalAlerts(path)
    first.create('A', price(), now=NOW)
    second = LocalAlerts(path)
    assert first.evaluate(snapshot(bid='3999'), now=NOW + 1) == []
    assert second.evaluate(snapshot(bid='3999'), now=NOW + 1) == []
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda store: store.evaluate(snapshot(NOW + 2), now=NOW + 2),
                                   [first, second]))
    assert sum(map(len, results)) == 1
    assert len(first.list('A')['events']) == 1


@pytest.mark.parametrize('interruption', ['account', 'disconnected', 'stale'])
def test_return_from_interruption_baselines_the_quote_instead_of_replaying_touch(tmp_path, interruption):
    store = LocalAlerts(tmp_path / 'a.sqlite')
    store.create('A', price(), now=NOW)
    assert store.evaluate(snapshot(bid='3999'), now=NOW + 1) == []
    interrupted = snapshot(NOW + 2)
    if interruption == 'account': interrupted['account']['account_key'] = 'B'
    if interruption == 'disconnected': interrupted['connection_status'] = 'DISCONNECTED'
    if interruption == 'stale': interrupted['quote']['status'] = 'STALE'
    assert store.evaluate(interrupted, now=NOW + 2) == []
    assert store.evaluate(snapshot(NOW + 2), now=NOW + 3) == []
    assert len(store.evaluate(snapshot(NOW + 4), now=NOW + 4)) == 1


def test_scheduler_gap_does_not_backfill_touch_even_when_last_quote_is_fresh(tmp_path):
    store = LocalAlerts(tmp_path / 'a.sqlite')
    store.create('A', price(), now=NOW)
    assert store.evaluate(snapshot(bid='3999'), now=NOW + 1) == []
    assert store.evaluate(snapshot(NOW + 19), now=NOW + 20) == []
    assert len(store.evaluate(snapshot(NOW + 21), now=NOW + 21)) == 1


def test_monitor_stop_requires_a_new_baseline_before_touch(tmp_path):
    store = LocalAlerts(tmp_path / 'a.sqlite')
    store.create('A', price(), now=NOW)
    value = snapshot(bid='3999')
    monitor = AlertMonitor(store, lambda: value)
    assert monitor.tick(now=NOW + 1) == []
    monitor.stop()
    value['quote'].update(bid='4000', source_time_utc=stamp(NOW + 2))
    assert monitor.tick(now=NOW + 3) == []
    value['quote']['source_time_utc'] = stamp(NOW + 4)
    assert len(monitor.tick(now=NOW + 4)) == 1


def test_monitor_is_explicit_and_tick_has_no_model_or_order_dependency(tmp_path):
    store = LocalAlerts(tmp_path / 'a.sqlite')
    store.create('A', price(), now=NOW)
    calls = []
    monitor = AlertMonitor(store, lambda: calls.append('snapshot') or snapshot())
    assert calls == [] and not monitor.running
    assert len(monitor.tick(now=NOW + 1)) == 1
    assert calls == ['snapshot']
    monitor.stop()
