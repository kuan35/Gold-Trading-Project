from decimal import Decimal
import pytest
from backend.engine import Engine, DomainError


def fill(e):
    d = e.create_draft('BUY', '0.10', None, None)
    return e.confirm(d['id'], d['revision'], 'open')['order_id']


def test_fill_marker_immediate_and_at_executed_price_without_future_candle():
    e = Engine()
    ident = fill(e)
    chart = e.chart()
    marker = next(m for m in chart['markers'] if m['id'] == ident)
    assert Decimal(marker['price']) == Decimal(e.orders[-1]['price'])
    assert marker['executed_at'] == e.clock
    assert marker['time'] == e.clock - 300
    assert marker['shape']=='arrowUp' and marker['position']=='belowBar'
    assert all(b['time'] + 300 <= e.clock for b in chart['bars'])


def test_close_focus_includes_linked_entry_even_outside_latest_window():
    e = Engine()
    ident = fill(e)
    for _ in range(25):
        e.step(12)
    exit_id = e.close(ident, 'close')['order_id']
    assert e.orders[-1]['position_id'] == ident
    chart = e.chart('5m', exit_id)
    assert set(chart['focus']['order_ids']) == {ident, exit_id}
    assert {m['id'] for m in chart['markers']} >= {ident, exit_id}
    assert chart['focus']['pairing'] == 'linked'
    exit_marker=next(m for m in chart['markers'] if m['id']==exit_id)
    assert exit_marker['shape']=='arrowDown' and exit_marker['position']=='aboveBar'
    assert all(b['time'] + 300 <= e.clock for b in chart['bars'])


def test_legacy_exit_not_guessed_and_unknown_focus_rejected():
    e = Engine()
    e.orders.append(dict(id='old', time=e.clock, side='SELL', lot='0.1',
                         price='2900', action='CLOSE', pnl='0', status='FILLED'))
    assert e.chart('5m', 'old')['focus']['pairing'] == 'unavailable'
    with pytest.raises(DomainError):
        e.chart('5m', 'does-not-exist')


def test_stop_exit_timestamp_precision_is_disclosed():
    e = Engine()
    ident = fill(e)
    e._close_at(e.positions[0], Decimal('2900'), 'STOP_LOSS_CONSERVATIVE')
    exit_marker = next(m for m in e.chart()['markers'] if m['action'] == 'CLOSE')
    assert exit_marker['time_precision'] == 'bar'
    assert exit_marker['position_id'] == ident


def test_old_focus_does_not_project_later_unrelated_trade_onto_old_candle():
    e = Engine()
    ident = fill(e)
    e.close(ident,'first-close')
    for _ in range(25):
        e.step(12)
    late = fill(e)
    assert late not in {m['id'] for m in e.chart('5m',ident)['markers']}


def test_api_focus_does_not_mutate_account_and_analysis_is_same_snapshot(monkeypatch):
    from fastapi.testclient import TestClient
    from backend import app as api
    e = Engine()
    ident = fill(e)
    before = e.state()
    monkeypatch.setattr(api,'engine',e)
    response=TestClient(api.app).get('/api/bars',params={'focus':ident})
    assert response.status_code==200
    result=response.json()
    assert result['focus']['selected_id']==ident
    assert result['analysis']['last_closed_at']==e.clock
    assert e.state()==before
