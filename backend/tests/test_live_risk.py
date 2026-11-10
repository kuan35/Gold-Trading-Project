from copy import deepcopy
from datetime import datetime, timezone

import pytest

from backend.engine import DomainError
from backend.live_risk import LiveLimits, check_live_open


def snapshot():
    return {
        'environment': 'live', 'source': 'ctrader_live_xauusd',
        'order_connection': True, 'token_scope': 'TRADE',
        'quote': {'status': 'CURRENT', 'bid': '2500.00', 'ask': '2500.20',
                  'age_seconds': 0.1, 'source_time_utc': datetime.now(timezone.utc).isoformat()},
        'account': {'status': 'CURRENT', 'currency': 'USD', 'account_key': 'live-hash',
                    'equity': '10000', 'positions': [], 'pending_orders': [],
                    'all_positions_count': 0, 'all_pending_orders_count': 0},
        'symbol': {'lot_size_cents': 10000, 'min_volume_cents': 100,
                   'max_volume_cents': 1000000, 'step_volume_cents': 100, 'digits': 2},
    }


def draft():
    return {'environment': 'live', 'side': 'BUY', 'order_type': 'MARKET',
            'lot': '0.10', 'price': '2500.20', 'sl': '2490.20',
            'volume_cents': 1000, 'lot_size_cents': 10000,
            'account_key': 'live-hash'}


def margin():
    return {'status': 'AVAILABLE', 'currency': 'USD', 'buy': '850.00',
            'sell': '850.00'}


def limits():
    return LiveLimits('200.00', '0.50')


def test_live_open_requires_explicit_positive_limits_and_stop():
    with pytest.raises(DomainError, match='上限'):
        LiveLimits('', '0.50')
    with pytest.raises(DomainError, match='上限'):
        LiveLimits('200', '0')
    row = draft(); row['sl'] = None
    with pytest.raises(DomainError, match='停損'):
        check_live_open(snapshot(), row, limits(), margin())


def test_live_open_checks_stop_loss_gross_lots_and_broker_margin():
    result = check_live_open(snapshot(), draft(), limits(), margin())
    assert result['stop_loss_usd'] == '100.00'
    assert result['gross_after_lot'] == '0.10'
    assert result['broker_margin_usd'] == '850.00'
    row = draft(); row['sl'] = '2470.20'
    with pytest.raises(DomainError, match='單筆停損'):
        check_live_open(snapshot(), row, limits(), margin())
    state = snapshot(); state['account']['pending_orders'] = [{'volume_units': '50'}]
    state['account']['all_pending_orders_count'] = 1
    with pytest.raises(DomainError, match='總手數'):
        check_live_open(state, draft(), limits(), margin())
    with pytest.raises(DomainError, match='保證金'):
        check_live_open(snapshot(), draft(), limits(), None)


def test_live_open_fails_closed_on_environment_scope_account_and_unknown_exposure():
    for change in ('environment', 'token_scope', 'account_key', 'all_positions_count', 'currency'):
        state, row = snapshot(), draft()
        if change == 'account_key': row['account_key'] = 'other'
        elif change == 'all_positions_count': state['account'][change] = 1
        elif change == 'currency': state['account'][change] = 'EUR'
        else: state[change] = 'demo' if change == 'environment' else 'VIEW'
        with pytest.raises(DomainError):
            check_live_open(state, row, limits(), margin())
    state = deepcopy(snapshot()); state['account']['equity'] = '0'
    with pytest.raises(DomainError, match='淨值'):
        check_live_open(state, draft(), limits(), margin())


def test_live_open_fails_closed_on_malformed_quote_age():
    for age in ('NaN', 'not-a-time', None, -1, 6):
        state = snapshot()
        state['quote']['age_seconds'] = age
        with pytest.raises(DomainError, match='報價'):
            check_live_open(state, draft(), limits(), margin())
