from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend import trade_advice as advice


def outcome(entry='100', close='102', *, end=1800, low='99', high='103'):
    return {'anchor_price': entry, 'anchor_time': end - 1800, 'horizons': {'30': {
        'status': 'AVAILABLE', 'end_time': end, 'bars': [
            {'time': end - 1800 + i * 300, 'open': entry, 'close': close,
             'high': high, 'low': low, 'observed_minutes': 5} for i in range(6)
        ],
    }}}


COSTS = {'baseline_usd_per_oz': '0.20', 'stress_usd_per_oz': '0.40'}


@pytest.mark.parametrize(('state', 'side'), [
    ('ABOVE', 'BUY'), ('LOWER_RECLAIM', 'BUY'), ('BELOW', 'SELL'),
    ('UPPER_RECLAIM', 'SELL'), ('BOTH_RECLAIM', None),
])
def test_signal_direction(monkeypatch, state, side):
    monkeypatch.setattr(advice, 'market_features', lambda _: {'event': state})
    assert advice.signal_for_query({})['side'] == side


def test_pair_shares_market_window_and_subtracts_cost():
    pair = advice.measure_pair(outcome(), COSTS)
    assert pair['BUY']['baseline_pct'] == Decimal('1.8')
    assert pair['SELL']['stress_pct'] == Decimal('-2.4')
    assert pair['SELL']['mae_pct'] == Decimal('3')


def advice_for(monkeypatch, *, count=10, loss=False, costs=COSTS, future=False, side=None, risk=None, close='102'):
    rows = [{'case_id': str(i), 'group': str(i)} for i in range(count)]
    index = SimpleNamespace(
        rank_for_advice=lambda query, exclude_group: rows,
        lookup={str(i): {'side': 'BUY', 'entry': '100', 'exit': '98' if loss else '101'} for i in range(count)},
        descriptions={str(i): {'end_5m': i, 'end_1h': i} for i in range(count)},
        tick_volume_store=object(),
    )
    monkeypatch.setattr(advice, 'market_features', lambda _: {'event': 'ABOVE'})
    store = SimpleNamespace(get=lambda ident, as_of: outcome(close=close, end=2001 if future else 1900))
    return advice.trade_advice(index, {'as_of': 2000}, store, costs, side=side, risk=risk)


def test_requires_ten_mature_pairs(monkeypatch):
    assert advice_for(monkeypatch)['action'] == 'BUY'
    assert advice_for(monkeypatch, count=9)['reason_code'] == 'INSUFFICIENT_PAIRS'
    assert advice_for(monkeypatch, future=True)['simulations']['count'] == 0


def test_waits_for_cost_and_conflicting_original(monkeypatch):
    assert advice_for(monkeypatch, costs=None)['reason_code'] == 'COST_UNAVAILABLE'
    assert advice_for(monkeypatch, close='100.30')['reason_code'] == 'STRESS_COST'
    assert advice_for(monkeypatch, loss=True)['reason_code'] == 'ORIGINAL_CONFLICT'
    assert advice_for(monkeypatch, side='SELL')['action'] == 'WAIT'


def test_adjust_preserves_direction(monkeypatch):
    assert advice_for(monkeypatch, side='BUY', risk={'over_budget': True, 'suggested_lot': '.01'})['action'] == 'ADJUST'


def test_draft_bar_with_both_levels_stays_ambiguous():
    rows = outcome(low='96', high='104')['horizons']['30']['bars']
    assert advice.scenario_result(rows, {'side': 'BUY', 'entry': '100', 'sl': '97', 'tp': '103'}) == 'ambiguous'
