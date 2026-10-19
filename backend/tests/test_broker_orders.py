from copy import deepcopy

import pytest

from backend.broker_orders import BrokerOrders
from backend.engine import DomainError


def market():
    return {'environment': 'demo', 'order_connection': True, 'token_scope': 'TRADE',
            'quote': {'status': 'CURRENT', 'bid': '2500.00', 'ask': '2500.30',
                      'source_time_utc': '2026-10-20T00:00:00+00:00', 'age_seconds': 0.1},
            'account': {'status': 'CURRENT', 'currency': 'USD', 'positions': [], 'pending_orders': []},
            'symbol': {'lot_size_cents': 10000, 'min_volume_cents': 100,
                       'max_volume_cents': 1000000, 'step_volume_cents': 100, 'digits': 2}}


class Stream:
    def __init__(self):
        self.value = market()
        self.calls = []

    def snapshot(self):
        return deepcopy(self.value)

    def place_order(self, command):
        self.calls.append(command)
        return {'client_order_id': command['client_order_id'], 'status': 'ACCEPTED',
                'order_id': '12345'}

    def order_status(self, ident):
        return None


def create(service, **changes):
    kwargs = dict(side='BUY', lot='0.10', order_type='MARKET',
                  limit_price=None, sl='2490.00', tp='2510.00', retrieval={'total': 0})
    kwargs.update(changes)
    return service.create(service.stream.snapshot(), **kwargs)


def test_demo_review_converts_broker_lot_size_and_never_sends_before_confirmation(tmp_path):
    stream = Stream()
    service = BrokerOrders(stream, tmp_path / 'journal.sqlite3')
    draft = create(service)
    assert draft['status'] == 'REVIEW'
    assert stream.calls == []
    assert draft['risk']['stop_loss_usd'] == '103.00'
    result = service.confirm(draft['id'], draft['revision'], 'one-key')
    assert result['status'] == 'ACCEPTED'
    assert stream.calls[0]['volume_cents'] == 1000
    assert stream.calls[0]['relative_sl'] == 1030000
    assert stream.calls[0]['relative_tp'] == 970000
    assert service.confirm(draft['id'], draft['revision'], 'one-key')['order_id'] == '12345'
    assert len(stream.calls) == 1
    with pytest.raises(DomainError):
        service.confirm(draft['id'], draft['revision'], 'different-key')


def test_limit_order_uses_absolute_protection_and_rejects_bad_volume(tmp_path):
    stream = Stream()
    service = BrokerOrders(stream, tmp_path / 'journal.sqlite3')
    draft = create(service, order_type='LIMIT', limit_price='2499.50',
                   sl='2490.00', tp='2510.00')
    service.confirm(draft['id'], draft['revision'], 'limit-key')
    assert stream.calls[0]['limit_price'] == '2499.50'
    assert stream.calls[0]['sl'] == '2490.00'
    assert 'relative_sl' not in stream.calls[0]
    with pytest.raises(DomainError):
        create(service, lot='0.105')


def test_demo_order_rechecks_account_quote_and_trade_scope(tmp_path):
    stream = Stream()
    service = BrokerOrders(stream, tmp_path / 'journal.sqlite3')
    draft = create(service)
    stream.value['quote']['ask'] = '2501.00'
    with pytest.raises(DomainError, match='報價變動'):
        service.confirm(draft['id'], draft['revision'], 'not-sent')
    assert stream.calls == []
    stream.value['token_scope'] = 'VIEW'
    with pytest.raises(DomainError, match='交易連線'):
        create(service)


def test_unknown_result_is_durable_and_never_resent_after_restart(tmp_path):
    stream = Stream()
    stream.place_order = lambda command: stream.calls.append(command) or {
        'client_order_id': command['client_order_id'], 'status': 'UNKNOWN'}
    journal = tmp_path / 'journal.sqlite3'
    service = BrokerOrders(stream, journal)
    draft = create(service)
    assert service.confirm(draft['id'], draft['revision'], 'same')['status'] == 'UNKNOWN'
    restarted = BrokerOrders(stream, journal)
    assert restarted.confirm(draft['id'], draft['revision'], 'same')['status'] == 'UNKNOWN'
    assert len(stream.calls) == 1


def test_transport_exception_after_journal_is_unknown_and_never_resubmitted(tmp_path):
    stream = Stream()
    def uncertain(command):
        stream.calls.append(command)
        raise ConnectionError('lost after send')
    stream.place_order = uncertain
    journal = tmp_path / 'journal.sqlite3'
    service = BrokerOrders(stream, journal)
    draft = create(service)
    result = service.confirm(draft['id'], draft['revision'], 'same')
    assert result['status'] == 'UNKNOWN'
    assert '勿重送' in result['message']
    assert BrokerOrders(stream, journal).confirm(draft['id'], draft['revision'], 'same')['status'] == 'UNKNOWN'
    assert len(stream.calls) == 1
