from copy import deepcopy
from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from backend.broker_orders import BrokerOrders
from backend.engine import DomainError


class Stream:
    def __init__(self, side='BUY'):
        self.value = {
            'environment': 'demo', 'order_connection': True, 'token_scope': 'TRADE',
            'quote': {'status': 'CURRENT', 'bid': '2500.00', 'ask': '2500.30',
                      'source_time_utc': '2026-10-21T00:00:00Z', 'age_seconds': .1},
            'account': {'status': 'CURRENT', 'account_key': 'demo-A', 'currency': 'USD',
                        'updated_at_utc': '2026-10-21T00:00:00Z',
                        'positions': [{'id': '123', 'side': side, 'volume_units': '10.25',
                                       'entry': '2490.00'}], 'pending_orders': []},
            'symbol': {'lot_size_cents': 10000, 'min_volume_cents': 100,
                       'max_volume_cents': 1000000, 'step_volume_cents': 100, 'digits': 2}}
        self.calls = []
        self.journal = None

    def snapshot(self):
        return deepcopy(self.value)

    def place_order(self, command):
        # The irreversible transport must only run after the journal is durable.
        with sqlite3.connect(self.journal) as db:
            assert db.execute('SELECT status FROM submissions WHERE client_order_id=?',
                              (command['client_order_id'],)).fetchone() == ('UNKNOWN',)
        self.calls.append(command)
        return {'status': 'ACCEPTED', 'order_id': '456'}

    def order_status(self, ident):
        return None


def service(tmp_path, side='BUY'):
    stream = Stream(side)
    stream.journal = tmp_path / 'close.sqlite3'
    return BrokerOrders(stream, stream.journal)


@pytest.mark.parametrize(('side', 'price'), [('BUY', '2500.00'), ('SELL', '2500.30')])
def test_close_review_full_volume_uses_position_quote_side_and_only_close_command(tmp_path, side, price):
    orders = service(tmp_path, side)
    draft = orders.create_close(orders.stream.snapshot(), '123')
    assert draft['status'] == 'REVIEW'
    assert draft['intent'] == 'CLOSE'
    assert draft['position_id'] == '123'
    assert draft['side'] == side
    assert draft['lot'] == '0.1025'
    assert draft['price'] == price
    assert orders.stream.calls == []
    assert 'account_key' not in draft
    assert 'account_signature' not in draft
    result = orders.confirm(draft['id'], draft['revision'], 'close-key')
    assert result['status'] == 'ACCEPTED'
    assert result['intent'] == 'CLOSE'
    assert result['position_id'] == '123'
    assert orders.stream.calls == [{'client_order_id': result['client_order_id'],
                                   'intent': 'CLOSE', 'position_id': '123', 'volume_cents': 1025}]
    row = orders.activity(orders.stream.snapshot())['submissions']['items'][0]
    assert row['intent'] == 'CLOSE'
    assert row['position_id'] == '123'


@pytest.mark.parametrize('change', ['missing', 'volume', 'side', 'account', 'symbol'])
def test_close_confirmation_rejects_changed_position_or_account_before_journal(tmp_path, change):
    orders = service(tmp_path)
    draft = orders.create_close(orders.stream.snapshot(), '123')
    if change == 'missing':
        orders.stream.value['account']['positions'] = []
    elif change in ('volume', 'side'):
        orders.stream.value['account']['positions'][0][{'volume': 'volume_units', 'side': 'side'}[change]] = {'volume': '10.00', 'side': 'SELL'}[change]
    elif change == 'account':
        orders.stream.value['account']['account_key'] = 'demo-B'
    else:
        orders.stream.value['symbol']['lot_size_cents'] = 100000
    with pytest.raises(DomainError):
        orders.confirm(draft['id'], draft['revision'], 'blocked')
    assert orders.stream.calls == []
    with orders._db() as db:
        assert db.execute('SELECT COUNT(*) FROM submissions').fetchone()[0] == 0


@pytest.mark.parametrize('volume', ['0', '-1', 'NaN', 'Infinity', '0.001', 'bad'])
def test_close_rejects_invalid_or_nonintegral_broker_volume(tmp_path, volume):
    orders = service(tmp_path)
    orders.stream.value['account']['positions'][0]['volume_units'] = volume
    with pytest.raises(DomainError):
        orders.create_close(orders.stream.snapshot(), '123')


@pytest.mark.parametrize('problem', ['live', 'view', 'quote', 'account', 'identity', 'missing'])
def test_close_refuses_unready_or_unbound_source(tmp_path, problem):
    orders = service(tmp_path)
    if problem == 'live': orders.stream.value['environment'] = 'live'
    elif problem == 'view': orders.stream.value['token_scope'] = 'VIEW'
    elif problem == 'quote': orders.stream.value['quote']['age_seconds'] = 6
    elif problem == 'account': orders.stream.value['account']['status'] = 'STALE'
    elif problem == 'identity': orders.stream.value['account'].pop('account_key')
    elif problem == 'missing': orders.stream.value['account']['positions'] = []
    with pytest.raises(DomainError):
        orders.create_close(orders.stream.snapshot(), '123')
    assert orders.stream.calls == []


def test_close_expiry_revision_cancel_and_fresh_quote_are_rechecked(tmp_path):
    orders = service(tmp_path)
    draft = orders.create_close(orders.stream.snapshot(), '123')
    with pytest.raises(DomainError):
        orders.confirm(draft['id'], 2, 'revision')
    orders.stream.value['quote']['bid'] = '2501.00'
    with pytest.raises(DomainError, match='報價變動'):
        orders.confirm(draft['id'], 1, 'moved')
    orders.stream.value['quote']['bid'] = '2500.00'
    orders.drafts[draft['id']]['expires_at_utc'] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    with pytest.raises(DomainError, match='30 秒'):
        orders.confirm(draft['id'], 1, 'expired')
    next_draft = orders.create_close(orders.stream.snapshot(), '123')
    orders.cancel(next_draft['id'])
    with pytest.raises(DomainError):
        orders.confirm(next_draft['id'], 1, 'cancelled')
    assert orders.stream.calls == []


def test_close_unknown_never_resubmits_after_restart_and_new_key_is_rejected(tmp_path):
    orders = service(tmp_path)
    def uncertain(command):
        orders.stream.calls.append(command)
        raise ConnectionError('lost response')
    orders.stream.place_order = uncertain
    draft = orders.create_close(orders.stream.snapshot(), '123')
    assert orders.confirm(draft['id'], 1, 'stable')['status'] == 'UNKNOWN'
    restarted = BrokerOrders(orders.stream, orders.journal)
    result = restarted.confirm(draft['id'], 1, 'stable')
    assert result['status'] == 'UNKNOWN'
    assert result['intent'] == 'CLOSE'
    assert result['position_id'] == '123'
    with pytest.raises(DomainError):
        restarted.confirm(draft['id'], 1, 'different')
    assert len(orders.stream.calls) == 1


@pytest.mark.parametrize('status', ['UNKNOWN', 'ACCEPTED', 'PARTIALLY_FILLED'])
def test_unresolved_close_blocks_new_draft_and_already_reviewed_draft_after_restart(tmp_path, status):
    orders = service(tmp_path)
    first = orders.create_close(orders.stream.snapshot(), '123')
    second = orders.create_close(orders.stream.snapshot(), '123')
    original = orders.stream.place_order
    orders.stream.place_order = lambda command: dict(original(command), status=status)
    orders.confirm(first['id'], 1, 'first')
    with pytest.raises(DomainError, match='平倉.*核對'):
        orders.confirm(second['id'], 1, 'second')
    restarted = BrokerOrders(orders.stream, orders.journal)
    with pytest.raises(DomainError, match='平倉.*核對'):
        restarted.create_close(orders.stream.snapshot(), '123')
    assert len(orders.stream.calls) == 1


@pytest.mark.parametrize('status', ['REJECTED', 'CANCELLED', 'EXPIRED'])
def test_explicit_terminal_failure_allows_a_new_review_for_same_position(tmp_path, status):
    orders = service(tmp_path)
    first = orders.create_close(orders.stream.snapshot(), '123')
    orders.confirm(first['id'], 1, 'first')
    orders.stream.order_status = lambda ident: {'status': status}
    assert orders.create_close(orders.stream.snapshot(), '123')['status'] == 'REVIEW'


def test_filled_close_requires_new_account_reconciliation_before_remaining_position_review(tmp_path):
    orders = service(tmp_path)
    first = orders.create_close(orders.stream.snapshot(), '123')
    orders.confirm(first['id'], 1, 'first')
    orders.stream.order_status = lambda ident: {'status': 'FILLED'}
    with pytest.raises(DomainError, match='帳戶.*更新'):
        orders.create_close(orders.stream.snapshot(), '123')
    # A new full reconcile may still have remaining volume (e.g. another addition).
    orders.stream.value['account']['updated_at_utc'] = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
    orders.stream.value['account']['positions'][0]['volume_units'] = '5.00'
    assert orders.create_close(orders.stream.snapshot(), '123')['lot'] == '0.05'


def test_unresolved_close_lock_is_scoped_to_account_and_position(tmp_path):
    orders = service(tmp_path)
    first = orders.create_close(orders.stream.snapshot(), '123')
    orders.confirm(first['id'], 1, 'first')
    orders.stream.value['account']['account_key'] = 'demo-B'
    assert orders.create_close(orders.stream.snapshot(), '123')['status'] == 'REVIEW'
    orders.stream.value['account']['account_key'] = 'demo-A'
    orders.stream.value['account']['positions'][0]['id'] = '124'
    assert orders.create_close(orders.stream.snapshot(), '124')['status'] == 'REVIEW'
