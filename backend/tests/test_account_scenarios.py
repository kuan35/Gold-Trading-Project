from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.account_scenarios import enrich_position_returns, equity_zero_scenario

NOW = 1800000000


def stamp(offset=0):
    return datetime.fromtimestamp(NOW + offset, timezone.utc).isoformat()


def snapshot(positions=None):
    positions = [] if positions is None else positions
    return dict(source='ctrader_demo_xauusd', environment='demo',
        quote=dict(status='CURRENT', bid='4000', ask='4001', age_seconds=0, source_time_utc=stamp()),
        account=dict(status='CURRENT', currency='USD', equity='10000', pnl_status='CURRENT',
            updated_at_utc=stamp(), pnl_updated_at_utc=stamp(), positions=positions,
            all_positions_count=len(positions)))


def position(side='BUY', **kw):
    return dict(dict(id='1', side=side, entry='4000', volume_units='10', net_pnl='100'), **kw)


def scenario(s=None, side='BUY', entry='4001', quantity='10', conditional=False):
    return equity_zero_scenario(snapshot() if s is None else s,
        dict(side=side, order_type='LIMIT' if conditional else 'MARKET'),
        dict(status='AVAILABLE', entry_price=entry, quantity_oz=quantity, conditional_on_fill=conditional), now=NOW)


def test_returns_use_executable_side_entry_denominator_net_pnl_and_never_mutate():
    s = snapshot([position(entry='3980'), position('SELL', id='2', entry='4020', net_pnl='-22')])
    before = deepcopy(s)
    r = enrich_position_returns(s, now=NOW)
    buy, sell = r['account']['positions']
    assert Decimal(buy['price_return_pct']) == (Decimal('4000')-3980)/3980*100
    assert Decimal(sell['price_return_pct']) == (Decimal('4020')-4001)/4020*100
    assert Decimal(buy['estimated_margin_roi_pct']) == Decimal('100')/(Decimal('3980')*10/200)*100
    assert Decimal(sell['estimated_margin_roi_pct']) == Decimal('-22')/(Decimal('4020')*10/200)*100
    assert buy['margin_return_source'] == 'LEVERAGE_ESTIMATE'
    assert s == before and r is not s


@pytest.mark.parametrize('patch', [dict(currency='EUR'), dict(currency=None), dict(pnl_status='STALE'),
    dict(pnl_updated_at_utc=stamp(-11)), dict(updated_at_utc=stamp(-11))])
def test_margin_returns_fail_closed_for_currency_and_stale_account_pnl(patch):
    s = snapshot([position()]); s['account'].update(patch)
    row = enrich_position_returns(s, now=NOW)['account']['positions'][0]
    assert row['estimated_margin_roi_pct'] is None and row['return_reason']


@pytest.mark.parametrize('patch', [dict(entry=None), dict(entry='0'), dict(entry='NaN'),
    dict(volume_units='0'), dict(net_pnl=None), dict(net_pnl='Infinity'), dict(side='UNKNOWN')])
def test_margin_returns_do_not_substitute_zero_for_missing_position_values(patch):
    row = enrich_position_returns(snapshot([position(**patch)]), now=NOW)['account']['positions'][0]
    assert row['estimated_margin_roi_pct'] is None


def test_price_return_ignores_fees_and_remains_available_without_pnl_or_usd():
    s = snapshot([position(entry='4000', net_pnl=None)])
    s['account'].update(currency=None, pnl_status='UNAVAILABLE')
    r = enrich_position_returns(s, now=NOW)['account']['positions'][0]
    assert r['price_return_pct'] == '0' and r['estimated_margin_roi_pct'] is None
    s['quote']['age_seconds'] = 6
    assert enrich_position_returns(s, now=NOW)['account']['positions'][0]['price_return_pct'] is None
    s['quote']['age_seconds'] = 0
    assert enrich_position_returns(s, now=NOW+6)['account']['positions'][0]['price_return_pct'] is None


def test_current_zero_pnl_is_valid_and_unknown_leverage_only_disables_margin_return():
    s = snapshot([position(net_pnl='0')])
    row = enrich_position_returns(s, now=NOW)['account']['positions'][0]
    assert Decimal(row['estimated_margin_roi_pct']) == 0
    for leverage in ['0', 'NaN', None, '10001']:
        row = enrich_position_returns(s, leverage=leverage, now=NOW)['account']['positions'][0]
        assert row['estimated_margin_roi_pct'] is None and row['price_return_pct'] == '0'


@pytest.mark.parametrize('currency', ['USD','EUR','JPY'])
def test_primary_position_return_prefers_broker_current_used_margin_in_account_currency(currency):
    s = snapshot([position(net_pnl='-12.34', used_margin='200', used_margin_source='BROKER_POSITION')])
    s['account']['currency'] = currency
    before = deepcopy(s)
    row = enrich_position_returns(s, now=NOW)['account']['positions'][0]
    assert Decimal(row['margin_roi_pct']) == Decimal('-6.17')
    assert row['margin_roi_pct'] == row['actual_margin_roi_pct']
    assert row['margin_return_source'] == 'BROKER_POSITION' and row['return_currency'] == currency
    assert '目前占用' in row['return_basis'] and '最初投入' in row['return_basis']
    assert s == before


def test_real_broker_margin_return_does_not_require_entry_quote_leverage_or_estimated_units():
    s = snapshot([position(entry=None, volume_units=None, net_pnl='0', used_margin='200', used_margin_source='BROKER_POSITION')])
    s['quote']['status'] = 'STALE'
    row = enrich_position_returns(s, leverage=None, now=NOW)['account']['positions'][0]
    assert Decimal(row['margin_roi_pct']) == 0 and row['margin_return_source'] == 'BROKER_POSITION'
    assert row['price_return_pct'] is None and row['estimated_margin_roi_pct'] is None


@pytest.mark.parametrize('patch', [dict(currency=None), dict(currency='UNKNOWN'), dict(pnl_status='STALE'),
    dict(pnl_updated_at_utc=stamp(-11)), dict(updated_at_utc=stamp(-11))])
def test_actual_margin_return_refuses_unknown_currency_and_stale_pnl(patch):
    s = snapshot([position(used_margin='200', used_margin_source='BROKER_POSITION')])
    s['account'].update(patch)
    row = enrich_position_returns(s, now=NOW)['account']['positions'][0]
    assert row['margin_roi_pct'] is None and row['actual_margin_roi_pct'] is None
    assert row['margin_return_source'] == 'UNAVAILABLE'


@pytest.mark.parametrize('used_margin', ['0','-1','NaN','Infinity'])
def test_known_nonpositive_or_invalid_margin_is_not_overwritten_by_primary_estimate(used_margin):
    s = snapshot([position(used_margin=used_margin, used_margin_source='BROKER_POSITION')])
    row = enrich_position_returns(s, now=NOW)['account']['positions'][0]
    assert row['margin_roi_pct'] is None and row['actual_margin_roi_pct'] is None
    assert row['margin_return_source'] == 'UNAVAILABLE'
    assert row['estimated_margin_roi_pct'] is not None


def test_only_missing_broker_margin_falls_back_to_explicit_estimate():
    s = snapshot([position(used_margin=None, used_margin_source='UNAVAILABLE')])
    row = enrich_position_returns(s, now=NOW)['account']['positions'][0]
    assert row['margin_roi_pct'] == row['estimated_margin_roi_pct']
    assert row['actual_margin_roi_pct'] is None and row['margin_return_source'] == 'LEVERAGE_ESTIMATE'


def test_quote_and_pnl_boundaries_accept_only_documented_source_clock_skew():
    s = snapshot()
    s['quote'].update(age_seconds=5, source_time_utc=stamp(-5))
    s['account'].update(updated_at_utc=stamp(-10), pnl_updated_at_utc=stamp(-10))
    assert scenario(s)['status'] == 'AVAILABLE'
    s['quote'].update(age_seconds=0, source_time_utc=stamp(.2))
    assert scenario(s)['status'] == 'AVAILABLE'
    s['quote']['source_time_utc'] = stamp(.3)
    assert scenario(s)['status'] == 'UNAVAILABLE'


def test_existing_short_and_net_short_result_moves_up_from_fill_reference():
    s = snapshot([position('SELL', volume_units='20')])
    r = scenario(s, entry='4101', conditional=True)
    assert r['equity_at_fill_usd'] == '7990' and r['net_quantity_oz'] == '-10'
    assert r['reference_bid_price'] == '4100' and r['zero_bid_price'] == '4899'
    assert r['direction'] == 'UP'


def test_new_buy_sell_scenarios_include_spread_and_explain_conditional_fill():
    buy = scenario()
    assert buy['status'] == 'AVAILABLE' and buy['zero_bid_price'] == '3001'
    assert buy['reference_bid_price'] == '4000' and buy['equity_at_fill_usd'] == '9990'
    assert buy['direction'] == 'DOWN' and buy['net_quantity_oz'] == '10'
    sell = scenario(side='SELL', entry='4000')
    assert sell['zero_bid_price'] == '4999' and sell['direction'] == 'UP'
    limit = scenario(entry='3901', conditional=True)
    assert limit['reference_bid_price'] == '3900' and limit['zero_bid_price'] == '2901'
    assert limit['conditional_on_fill'] is True
    assert '強平' in limit['basis'] and '固定' in limit['basis']


def test_existing_position_revalues_at_limit_fill_and_hedge_is_not_a_zero_price():
    s = snapshot([position(volume_units='20')])
    r = scenario(s, entry='3901', conditional=True)
    assert r['equity_at_fill_usd'] == '7990' and r['net_quantity_oz'] == '30'
    zero = Decimal(r['zero_bid_price'])
    assert abs(Decimal('7990') + 30*(zero-3900)) < Decimal('0.00000000000000000001')
    hedge = scenario(s, side='SELL', entry='4000', quantity='20')
    assert hedge['status'] == 'NET_HEDGED' and hedge['zero_bid_price'] is None
    assert hedge['net_quantity_oz'] == '0'


def test_large_equity_long_has_no_positive_zero_price_and_nonpositive_fill_equity_refuses():
    s = snapshot(); s['account']['equity'] = '50000'
    assert scenario(s)['status'] == 'NO_POSITIVE_ZERO_PRICE'
    s = snapshot([position(volume_units='200')]); s['account']['equity'] = '100'
    assert scenario(s, entry='3901', conditional=True)['status'] == 'UNAVAILABLE'


@pytest.mark.parametrize('patch', [dict(currency='EUR'), dict(currency=None), dict(pnl_status='STALE'),
    dict(status='LOADING'), dict(pnl_updated_at_utc=stamp(-11)), dict(updated_at_utc=stamp(-11)),
    dict(pnl_updated_at_utc=stamp(1)), dict(equity=None), dict(equity='NaN'), dict(equity='0'),
    dict(all_positions_count=1), dict(all_positions_count=None), dict(all_positions_count=True)])
def test_zero_scenario_refuses_unknown_account_or_other_product_exposure(patch):
    s = snapshot(); s['account'].update(patch)
    r = scenario(s)
    assert r['status'] == 'UNAVAILABLE' and r['zero_bid_price'] is None


@pytest.mark.parametrize('row', [position(side='UNKNOWN'), position(volume_units=None),
    position(volume_units='NaN'), position(volume_units='0'), position(entry=None),
    position(net_pnl=None), position(symbol='EURUSD'), None])
def test_zero_scenario_never_silently_omits_an_invalid_position(row):
    assert scenario(snapshot([row]))['status'] == 'UNAVAILABLE'


def test_zero_scenario_rejects_bad_quotes_symbols_and_preview_and_keeps_input_untouched():
    s = snapshot(); before = deepcopy(s)
    assert scenario(s)['status'] == 'AVAILABLE' and s == before
    for patch in [dict(status='STALE'), dict(bid='0'), dict(ask='3999'), dict(age_seconds=6),
                  dict(source_time_utc=stamp(-6)), dict(source_time_utc=stamp(1))]:
        changed = deepcopy(s); changed['quote'].update(patch)
        assert scenario(changed)['status'] == 'UNAVAILABLE'
    s['symbol'] = {'name':'EURUSD'}
    assert scenario(s)['status'] == 'UNAVAILABLE'
    s = snapshot(); s.pop('source')
    assert scenario(s)['status'] == 'UNAVAILABLE'
    s['symbol'] = {'name':'XAUUSD'}
    assert scenario(s)['status'] == 'AVAILABLE'
    for key, val in [('status','WAITING'), ('entry_price',None), ('quantity_oz','0')]:
        preview = dict(status='AVAILABLE', entry_price='4001', quantity_oz='10')
        preview[key] = val
        assert equity_zero_scenario(snapshot(), {'side':'BUY'}, preview, now=NOW)['status'] == 'UNAVAILABLE'
