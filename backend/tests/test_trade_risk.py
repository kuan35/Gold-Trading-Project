from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.ticket_preview import ticket_preview
from backend.trade_risk import risk_summary, size_for_risk


NOW = 1800000000


def stamp(seconds=0):
    return datetime.fromtimestamp(NOW + seconds, timezone.utc).isoformat()


def snapshot():
    return dict(environment='demo', quote=dict(status='CURRENT', bid='4000', ask='4000.20',
        age_seconds=0, source_time_utc=stamp()), symbol=dict(lot_size_cents=10000,
        min_volume_cents=100, max_volume_cents=1000000, step_volume_cents=100, digits=2),
        account=dict(status='CURRENT', pnl_status='CURRENT', currency='USD', equity='10000',
        updated_at_utc=stamp(), pnl_updated_at_utc=stamp(), positions=[], pending_orders=[]))


def draft(**changes):
    return dict(dict(side='BUY', lot='0.5', order_type='LIMIT', limit_price='4000',
        sl='3990', tp='4020'), **changes)


def summary(s=None, d=None, **kw):
    s, d = s or snapshot(), d or draft()
    return risk_summary(s, d, ticket_preview(s, d, now=NOW), now=NOW, **kw)


def test_stop_equity_reward_ratio_and_empty_account_total():
    r = summary()
    assert r['status'] == 'AVAILABLE'
    assert r['stop_loss_usd'] == '500.00'
    assert r['stop_equity_pct'] == '5.0000'
    assert r['reward_risk_ratio'] == '2.0000'
    assert r['existing_positions_risk_usd'] == '0.00'
    assert r['pending_orders_risk_usd'] == '0.00'
    assert r['gold_total_risk_usd'] == '500.00'
    assert r['gold_total_equity_pct'] == '5.0000'
    assert not r['unprotected_positions'] and not r['unprotected_orders']
    assert '黃金' in r['scope']


def test_readonly_preview_and_sizing_accept_subsecond_source_clock_skew_only():
    s=snapshot();s['quote']['source_time_utc']=stamp(.15)
    assert summary(s)['stop_loss_usd']=='500.00'
    assert size_for_risk(s,draft(),risk_usd='50',now=NOW)['status']=='AVAILABLE'
    s['quote']['source_time_utc']=stamp(.3)
    assert size_for_risk(s,draft(),risk_usd='50',now=NOW)['status']=='UNAVAILABLE'


def test_positions_use_close_side_and_pending_open_uses_limit_without_hedge_offset():
    s = snapshot()
    s['account']['positions'] = [dict(id='buy', side='BUY', volume_units='10', sl='3995', entry='3980'),
        dict(id='sell', side='SELL', volume_units='5', sl='4010', entry='4020')]
    s['account']['pending_orders'] = [dict(id='open', intent='OPEN', side='BUY',
        volume_units='4', limit_price='3990', sl='3980'),
        dict(id='close', intent='CLOSE', side='SELL', volume_units='10', limit_price='4010')]
    r = summary(s)
    assert r['existing_positions_risk_usd'] == '99.00'
    assert r['pending_orders_risk_usd'] == '40.00'
    assert r['gold_total_risk_usd'] == '639.00'


@pytest.mark.parametrize('bad', [None, '', '0', '4000', '4010', 'NaN'])
def test_unprotected_or_crossed_position_stop_never_becomes_zero(bad):
    s = snapshot()
    s['account']['positions'] = [dict(id='p', side='BUY', volume_units='10', sl=bad)]
    r = summary(s)
    assert r['status'] == 'UNKNOWN'
    assert r['existing_positions_risk_usd'] is None and r['gold_total_risk_usd'] is None
    assert r['unprotected_positions'] == ['p']
    assert r['stop_loss_usd'] == '500.00'


@pytest.mark.parametrize('changes', [dict(sl=None), dict(volume_units=None), dict(intent=None),
    dict(limit_price=None), dict(sl='4000')])
def test_incomplete_pending_open_never_becomes_zero(changes):
    s = snapshot()
    s['account']['pending_orders'] = [dict(dict(id='o', intent='OPEN', side='BUY',
        volume_units='4', limit_price='3990', sl='3980'), **changes)]
    r = summary(s)
    assert r['pending_orders_risk_usd'] is None and r['gold_total_risk_usd'] is None
    assert r['unprotected_orders'] == ['o']


@pytest.mark.parametrize('changes', [dict(status='STALE'), dict(pnl_status='INCOMPLETE'),
    dict(currency='EUR'), dict(equity='0'), dict(equity='NaN'), dict(updated_at_utc=stamp(-11)),
    dict(pnl_updated_at_utc=stamp(-11)), dict(pnl_updated_at_utc=None), dict(updated_at_utc=stamp(1))])
def test_unverified_account_equity_omits_percentages_but_preserves_ticket_usd(changes):
    s = snapshot()
    s['account'].update(changes)
    r = summary(s)
    assert r['stop_loss_usd'] == '500.00'
    assert r['stop_equity_pct'] is None and r['gold_total_equity_pct'] is None
    assert r['reason']


def test_missing_account_or_exposure_lists_do_not_claim_zero():
    for field in ('account', 'positions', 'pending_orders'):
        s = snapshot()
        if field == 'account':
            s.pop(field)
        else:
            s['account'].pop(field)
        r = summary(s)
        assert r['gold_total_risk_usd'] is None


def test_stale_quote_cannot_value_existing_position_or_market_entry():
    s = snapshot()
    s['quote']['source_time_utc'] = stamp(-6)
    s['account']['positions'] = [dict(id='p', side='BUY', volume_units='10', sl='3990')]
    r = summary(s, draft(order_type='MARKET'))
    assert r['stop_loss_usd'] is None and r['gold_total_risk_usd'] is None
    assert r['existing_positions_risk_usd'] is None


def test_missing_or_wrong_side_ticket_stop_omits_total_and_ratio():
    for sl in (None, '4010'):
        r = summary(d=draft(sl=sl))
        assert r['stop_loss_usd'] is None
        assert r['gold_total_risk_usd'] is None
        assert r['reward_risk_ratio'] is None


def test_size_uses_budget_and_rounds_down_by_broker_step_without_mutation():
    s, d = snapshot(), draft(lot='nonsense')
    before = deepcopy((s, d))
    r = size_for_risk(s, d, risk_usd='123.45', now=NOW)
    assert r['status'] == 'AVAILABLE'
    assert r['lot'] == '0.12'
    assert r['actual_risk_usd'] == '120.00' and r['budget_usd'] == '123.45'
    assert r['stop_equity_pct'] == '1.2000'
    assert (s, d) == before


def test_size_supports_equity_percent_and_sell_bid_or_buy_ask():
    r = size_for_risk(snapshot(), draft(), equity_pct='1', now=NOW)
    assert r['lot'] == '0.1' and r['budget_usd'] == '100.00'
    r = size_for_risk(snapshot(), draft(order_type='MARKET'), risk_usd='102', now=NOW)
    assert r['lot'] == '0.1' and r['actual_risk_usd'] == '102.00'
    r = size_for_risk(snapshot(), draft(order_type='MARKET', side='SELL', sl='4010'), risk_usd='100', now=NOW)
    assert r['lot'] == '0.1' and r['actual_risk_usd'] == '100.00'


@pytest.mark.parametrize('kwargs', [{}, dict(risk_usd='100', equity_pct='1'), dict(risk_usd='0'),
    dict(risk_usd='-1'), dict(risk_usd='Infinity'), dict(equity_pct='NaN')])
def test_size_requires_one_positive_finite_budget(kwargs):
    r = size_for_risk(snapshot(), draft(), now=NOW, **kwargs)
    assert r['status'] == 'UNAVAILABLE' and r['lot'] is None


def test_size_does_not_round_up_small_budget_or_unverified_equity():
    r = size_for_risk(snapshot(), draft(), risk_usd='9.99', now=NOW)
    assert r['status'] == 'UNAVAILABLE' and r['lot'] is None
    s = snapshot()
    s['account']['currency'] = 'EUR'
    assert size_for_risk(s, draft(), equity_pct='1', now=NOW)['lot'] is None
    r = size_for_risk(s, draft(), risk_usd='100', now=NOW)
    assert r['lot'] == '0.1' and r['stop_equity_pct'] is None


def test_size_respects_broker_min_offset_max_and_hard_100_lot_limit():
    s = snapshot()
    s['symbol'].update(min_volume_cents=125, step_volume_cents=50, max_volume_cents=525)
    r = size_for_risk(s, draft(), risk_usd='100', now=NOW)
    assert r['lot'] == '0.0525' and r['actual_risk_usd'] == '52.50'
    s['symbol'].update(min_volume_cents=100, step_volume_cents=100, max_volume_cents=2000000)
    assert size_for_risk(s, draft(), risk_usd='200000', now=NOW)['lot'] == '100'


@pytest.mark.parametrize('field,value', [('sl', None), ('sl', '4000'), ('sl', 'NaN'),
    ('sl', '3990.001'), ('side', 'HOLD'), ('limit_price', None)])
def test_size_rejects_invalid_stop_entry_or_side(field, value):
    assert size_for_risk(snapshot(), draft(**{field: value}), risk_usd='100', now=NOW)['lot'] is None


def test_size_rejects_stale_or_crossed_quote_and_broken_contract():
    for changes in (dict(source_time_utc=stamp(-6)), dict(bid='4001'), dict(ask='NaN')):
        s = snapshot()
        s['quote'].update(changes)
        assert size_for_risk(s, draft(order_type='MARKET'), risk_usd='100', now=NOW)['lot'] is None
    s = snapshot()
    s['symbol']['step_volume_cents'] = 0
    assert size_for_risk(s, draft(), risk_usd='100', now=NOW)['lot'] is None


def test_precision_never_suggests_more_actual_risk_than_budget():
    r = size_for_risk(snapshot(), draft(sl='3999.97'), risk_usd='0.10', now=NOW)
    assert r['lot'] == '0.03'
    assert Decimal(r['actual_risk_usd']) <= Decimal(r['budget_usd'])


def test_summary_is_pure_and_does_not_expose_account_identifiers():
    s, d = snapshot(), draft()
    s['account']['account_key'] = 'PRIVATE_ACCOUNT'
    preview = ticket_preview(s, d, now=NOW)
    before = deepcopy((s, d, preview))
    r = risk_summary(s, d, preview, now=NOW)
    assert (s, d, preview) == before and 'PRIVATE_ACCOUNT' not in str(r)
