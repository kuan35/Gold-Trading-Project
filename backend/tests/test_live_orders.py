from copy import deepcopy

import pytest

from backend.engine import DomainError
from backend.live_orders import LiveBrokerOrders
from backend.live_risk import LiveLimits
from backend.tests.test_live_risk import snapshot, margin


class FakeLiveStream:
    def __init__(self):
        self.value = snapshot()
        self.calls = []

    def snapshot(self):
        return deepcopy(self.value)

    def expected_margin(self, _snapshot, _volume):
        return margin()

    def place_order(self, command):
        self.calls.append(command)
        return {'client_order_id': command['client_order_id'], 'status': 'ACCEPTED', 'order_id': '123'}

    def order_status(self, _ident):
        return None


def create(service, **changes):
    kwargs = dict(side='BUY', lot='0.10', order_type='MARKET', limit_price=None,
                  sl='2490.20', tp='2510.20', retrieval={'total': 0})
    kwargs.update(changes)
    return service.create(service.stream.snapshot(), **kwargs)


def service(tmp_path, stream=None):
    stream = stream or FakeLiveStream()
    return LiveBrokerOrders(stream, tmp_path / 'live.sqlite3', limits_provider=lambda: LiveLimits('200', '0.5'))


def test_live_order_requires_stop_and_no_send_before_human_confirm(tmp_path):
    orders = service(tmp_path)
    with pytest.raises(DomainError, match='停損'):
        create(orders, sl=None)
    reviewed = create(orders)
    assert reviewed['environment'] == 'live'
    assert reviewed['risk']['live']['stop_loss_usd'] == '100.00'
    assert orders.stream.calls == []
    result = orders.confirm(reviewed['id'], 1, 'human-confirm')
    assert result['status'] == 'ACCEPTED'
    assert len(orders.stream.calls) == 1
    assert orders.stream.calls[0]['client_order_id'].startswith('gd-live-')
    assert orders.confirm(reviewed['id'], 1, 'human-confirm')['status'] == 'ACCEPTED'
    assert len(orders.stream.calls) == 1


def test_live_does_not_accept_limit_close_or_changed_account(tmp_path):
    orders = service(tmp_path)
    with pytest.raises(DomainError, match='限價平倉'):
        orders.create_close(orders.stream.snapshot(), '1', order_type='LIMIT', limit_price='2510')
    reviewed = create(orders)
    orders.stream.value['account']['account_key'] = 'different'
    with pytest.raises(DomainError):
        orders.confirm(reviewed['id'], 1, 'human-confirm')
    assert orders.stream.calls == []


def test_live_fails_closed_if_margin_or_limits_disappear_at_confirmation(tmp_path):
    orders = service(tmp_path)
    reviewed = create(orders)
    orders.stream.expected_margin = lambda _snapshot, _volume: None
    with pytest.raises(DomainError, match='保證金'):
        orders.confirm(reviewed['id'], 1, 'human-confirm')
    assert orders.stream.calls == []
