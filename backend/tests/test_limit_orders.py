from decimal import Decimal

import pytest

from backend.engine import DomainError, Engine


def test_buy_limit_waits_for_ask_touch_and_only_fills_once():
    engine = Engine()
    ask = Decimal(engine.quote()['ask'])
    limit = ask - Decimal('2.00')
    draft = engine.create_draft('BUY', '0.10', None, None, None, 'LIMIT', str(limit))
    receipt = engine.confirm(draft['id'], draft['revision'], 'place-once')
    assert receipt['status'] == 'PENDING'
    assert not engine.positions
    assert len(engine.state()['pending_orders']) == 1
    assert engine.confirm(draft['id'], draft['revision'], 'place-once')['order_id'] == receipt['order_id']

    first = engine.bars[engine.cursor]
    first.update(open=str(limit + 3), high=str(limit + 4), low=str(limit + 1), close=str(limit + 2))
    engine.step(1)
    assert not engine.positions

    touch = engine.bars[engine.cursor]
    touch.update(open=str(limit + 1), high=str(limit + 2), low=str(limit - Decimal('.30')), close=str(limit))
    engine.step(1)
    assert len(engine.positions) == 1
    assert engine.positions[0]['entry'] == str(limit)
    assert not engine.state()['pending_orders']
    assert len([o for o in engine.orders if o['action'] == 'FIRST']) == 1


def test_sell_limit_cancel_and_invalid_prices():
    engine = Engine()
    bid = Decimal(engine.quote()['bid'])
    with pytest.raises(DomainError, match='高於'):
        engine.create_draft('SELL', '0.10', None, None, None, 'LIMIT', str(bid))
    with pytest.raises(DomainError, match='限價'):
        engine.create_draft('BUY', '0.10', None, None, None, 'LIMIT', None)
    draft = engine.create_draft('SELL', '0.10', None, None, None, 'LIMIT', str(bid + 2))
    receipt = engine.confirm(draft['id'], draft['revision'], 'sell')
    engine.cancel_pending(receipt['order_id'])
    assert not engine.state()['pending_orders']
    engine.bars[engine.cursor].update(open=str(bid), high=str(bid + 3), low=str(bid - 1), close=str(bid + 2))
    engine.step(1)
    assert not engine.positions
