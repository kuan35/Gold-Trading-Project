from decimal import Decimal
import pytest
from backend.engine import Engine, DomainError


def test_first_fill_cancel_and_duplicate_do_not_create_extra_positions():
    e = Engine()
    d = e.create_draft('BUY', '0.1', None, None)
    assert d['risk']['stop_loss_usd'] is None
    assert d['risk']['reward_risk'] is None
    assert d['action'] == 'FIRST'
    a = e.confirm(d['id'], d['revision'], 'one')
    assert a['status'] == 'FILLED'
    assert e.confirm(d['id'], d['revision'], 'one')['order_id'] == a['order_id']
    assert len(e.positions) == 1
    with pytest.raises(DomainError):
        e.confirm(d['id'], d['revision'], 'two')
    other = e.create_draft('BUY', '0.1', None, None)
    e.cancel(other['id'])
    with pytest.raises(DomainError):
        e.confirm(other['id'], other['revision'], 'cancelled')


def test_add_updates_size_and_stale_quote_cannot_fill():
    e = Engine()
    d = e.create_draft('SELL', '0.1', None, None)
    e.confirm(d['id'], d['revision'], 'first')
    d = e.create_draft('SELL', '0.2', None, None)
    assert d['action'] == 'ADD'
    assert Decimal(d['risk']['after_lot']) == Decimal('0.3')
    e.step(1)
    with pytest.raises(DomainError, match='更新'):
        e.confirm(d['id'], d['revision'], 'stale')


@pytest.mark.parametrize('lot', ['0', '-1', 'NaN', 'Infinity', '0.001', 'abc', '101'])
def test_invalid_quantity_never_enters_review(lot):
    with pytest.raises(DomainError):
        Engine().create_draft('BUY', lot, None, None)


def test_stop_direction_and_reward_ratio_are_decimal():
    e = Engine()
    px = Decimal(e.state()['quote']['ask'])
    d = e.create_draft('BUY', '0.10', str(px-10), str(px+20))
    assert Decimal(d['risk']['stop_loss_usd']) == Decimal('100.00')
    assert Decimal(d['risk']['reward_risk']) == Decimal('2.00')
    with pytest.raises(DomainError):
        e.create_draft('BUY', '0.1', str(px+1), None)


def test_manual_close_realizes_pnl_and_is_idempotent():
    e = Engine()
    d = e.create_draft('BUY', '0.1', None, None)
    e.confirm(d['id'], d['revision'], 'open')
    p = e.positions[0]
    expected = (Decimal(e.state()['quote']['bid'])-Decimal(p['entry']))*10
    result = e.close(p['id'], 'close-key')
    assert Decimal(result['state']['account']['balance']) == Decimal('10000')+expected
    assert not e.positions
    assert e.close(p['id'], 'close-key')['order_id'] == result['order_id']


def test_broker_mode_never_falls_back_to_local_fill():
    e = Engine()
    e.mode = 'broker_demo'
    with pytest.raises(DomainError, match='未連線'):
        e.create_draft('BUY', '0.1', None, None)
    assert not e.positions


def test_retry_receipt_keeps_current_account_state_after_another_fill():
    e=Engine()
    first=e.create_draft('BUY','0.1',None,None)
    receipt=e.confirm(first['id'],first['revision'],'first')
    second=e.create_draft('BUY','0.1',None,None)
    e.confirm(second['id'],second['revision'],'second')
    retry=e.confirm(first['id'],first['revision'],'first')
    assert retry['order_id']==receipt['order_id']
    assert len(retry['state']['positions'])==2


def test_future_cases_and_profit_ranking_are_excluded():
    e = Engine()
    results = e.retrieve('BUY', 'FIRST', Decimal('0.1'))
    assert results['total'] == results['wins']+results['losses']+results['flat']+results['unknown']
    assert all(c['available_at'] <= e.clock for c in e.cases.available())
    ranked_before = e.cases.rank('BUY', 'FIRST', Decimal('0.1'), e.clock)
    ids_before = [(c['id'], c['distance']) for c in ranked_before]
    for c in e.cases.items:
        c['profit'] = str(-Decimal(c['profit']))
    assert [(c['id'], c['distance']) for c in e.cases.rank('BUY', 'FIRST', Decimal('0.1'), e.clock)] == ids_before


def test_candles_all_end_before_replay_clock():
    e = Engine()
    for interval, seconds in [('5m',300),('15m',900),('1h',3600)]:
        bars = e.chart(interval)['bars']
        assert bars
        assert max(b['time']+seconds for b in bars) <= e.clock


def test_time_step_and_reset_do_not_preserve_old_orders():
    e = Engine()
    d = e.create_draft('BUY','0.1',None,None)
    e.confirm(d['id'],d['revision'],'first')
    original = e.clock
    e.step(6)
    assert e.clock == original+1800
    e.reset()
    assert not e.positions
    assert not e.orders
    assert e.clock == original
