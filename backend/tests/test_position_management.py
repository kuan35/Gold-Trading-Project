from copy import deepcopy
import pytest
from backend.engine import DomainError
from backend.tests.test_broker_close import service


@pytest.mark.parametrize(('side','limit','opposite'),[('BUY','2505.00','SELL'),('SELL','2495.00','BUY')])
def test_limit_close_is_bound_to_original_position_and_idempotent(tmp_path,side,limit,opposite):
    s=service(tmp_path,side)
    d=s.create_close(s.stream.snapshot(),'123',order_type='LIMIT',limit_price=limit)
    assert d['order_type']=='LIMIT' and d['limit_price']==limit and not s.stream.calls
    r=s.confirm(d['id'],1,'key');again=s.confirm(d['id'],1,'key')
    assert len(s.stream.calls)==1 and again['client_order_id']==r['client_order_id']
    cmd=s.stream.calls[0]
    assert cmd['intent']=='CLOSE' and cmd['position_id']=='123' and cmd['side']==opposite
    assert cmd['order_type']=='LIMIT' and cmd['volume_cents']==1025


def test_protection_preserves_untouched_tp_and_rejects_a_stale_protection_change(tmp_path):
    s=service(tmp_path);s.stream.value['account']['positions'][0].update(sl='2480.00',tp='2520.00')
    d=s.create_protection(s.stream.snapshot(),'123',{'sl':'2495.00'})
    assert d['sl']=='2495.00' and d['tp']=='2520.00' and not s.stream.calls
    s.stream.value['account']['positions'][0]['tp']='2525.00'
    with pytest.raises(DomainError):s.confirm(d['id'],1,'key')
    assert not s.stream.calls


def test_explicit_clear_is_different_from_keep_and_durable_submit_has_own_intent(tmp_path):
    s=service(tmp_path);s.stream.value['account']['positions'][0].update(sl='2480.00',tp='2520.00')
    d=s.create_protection(s.stream.snapshot(),'123',{'tp':None})
    assert d['sl']=='2480.00' and d['tp'] is None
    original=s.stream.place_order
    def applied(cmd):original(cmd);return dict(status='APPLIED',position_id='123')
    s.stream.place_order=applied
    r=s.confirm(d['id'],1,'key')
    assert r['status']=='APPLIED' and s.stream.calls[0]['intent']=='PROTECT'
    assert s.stream.calls[0]['expected_tp']=='2520.00'
    assert s.confirm(d['id'],1,'key')['status']=='APPLIED' and len(s.stream.calls)==1


def test_cancel_is_a_known_pending_order_and_does_not_require_an_open_position(tmp_path):
    s=service(tmp_path)
    order=dict(id='456',intent='CLOSE',position_id='123',side='SELL',order_type='LIMIT',volume_units='10.25',limit_price='2505.00')
    s.stream.value['account']['pending_orders']=[order]
    d=s.create_pending_cancel(s.stream.snapshot(),'456')
    s.confirm(d['id'],1,'key')
    assert s.stream.calls[0]['intent']=='CANCEL' and s.stream.calls[0]['order_id']=='456'
    s=service(tmp_path/'second');s.stream.value['account']['positions']=[]
    s.stream.value['account']['pending_orders']=[dict(order,intent='OPEN',position_id=None)]
    d=s.create_pending_cancel(s.stream.snapshot(),'456')
    original=s.stream.place_order
    def cancelled(cmd):original(cmd);return dict(status='CANCELLED',order_id='456')
    s.stream.place_order=cancelled
    assert s.confirm(d['id'],1,'cancel-open')['status']=='CANCELLED'
    assert s.confirm(d['id'],1,'cancel-open')['status']=='CANCELLED'
    assert len(s.stream.calls)==1 and s.stream.calls[0]['position_id'] is None
    assert s.stream.calls[0]['expected_order']['intent']=='OPEN'


@pytest.mark.parametrize('change',['filled','quantity','account','live'])
def test_pending_cancel_rechecks_the_target_and_never_cancels_another_order(tmp_path,change):
    s=service(tmp_path)
    s.stream.value['account']['pending_orders']=[dict(id='456',intent='OPEN',side='BUY',order_type='LIMIT',volume_units='10',limit_price='2490')]
    d=s.create_pending_cancel(s.stream.snapshot(),'456')
    if change=='filled':s.stream.value['account']['pending_orders']=[]
    elif change=='quantity':s.stream.value['account']['pending_orders'][0]['volume_units']='5'
    elif change=='account':s.stream.value['account']['account_key']='different-account'
    else:s.stream.value['environment']='live'
    with pytest.raises(DomainError):s.confirm(d['id'],1,'cancel-key')
    assert not s.stream.calls

def test_a_second_cancellation_waits_for_the_cancelled_order_to_leave_the_account(tmp_path):
    s=service(tmp_path);s.stream.value['account']['pending_orders']=[dict(id='456',intent='OPEN',side='BUY',order_type='LIMIT',volume_units='10',limit_price='2490')]
    first=s.create_pending_cancel(s.stream.snapshot(),'456');second=s.create_pending_cancel(s.stream.snapshot(),'456')
    original=s.stream.place_order
    def cancelled(cmd):original(cmd);return dict(status='CANCELLED',order_id='456')
    s.stream.place_order=cancelled;s.confirm(first['id'],1,'one')
    with pytest.raises(DomainError,match='取消'):
        s.confirm(second['id'],1,'two')
    assert len(s.stream.calls)==1


def test_a_fill_event_is_not_a_successful_cancellation(tmp_path):
    s=service(tmp_path)
    s.stream.value['account']['pending_orders']=[dict(id='456',intent='OPEN',side='BUY',order_type='LIMIT',volume_units='10',limit_price='2490')]
    d=s.create_pending_cancel(s.stream.snapshot(),'456');s.confirm(d['id'],1,'key')
    s.stream.order_status=lambda _:dict(status='FILLED',order_id='456')
    assert s.status(d['id'])['status']=='UNKNOWN'


@pytest.mark.parametrize(('original_status','cancel_status'),[('CANCELLED','CANCELLED'),('FILLED','REJECTED'),('EXPIRED','REJECTED'),('REJECTED','REJECTED')])
def test_unknown_cancel_can_reconcile_original_order_after_worker_restart(tmp_path,original_status,cancel_status):
    from backend.broker_orders import BrokerOrders
    s=service(tmp_path);row=dict(id='456',order_id='456',intent='OPEN',position_id=None,side='BUY',order_type='LIMIT',volume_units='10',limit_price='2490')
    s.stream.value['account']['pending_orders']=[row]
    d=s.create_pending_cancel(s.stream.snapshot(),'456');s.confirm(d['id'],1,'key')
    def activity():return dict(account=s.stream.snapshot()['account'],history={'broker_orders':dict(status='CURRENT',items=[dict(row,status=original_status,client_order_id='gd-original')])})
    s.stream.activity_snapshot=activity
    restarted=BrokerOrders(s.stream,s.journal)
    assert restarted.status(d['id'])['status']==cancel_status
    assert restarted.confirm(d['id'],1,'key')['status']==cancel_status
    assert len(s.stream.calls)==1
    s.stream.value['account']['account_key']='different'
    # Another account must never resolve this account's cancel receipt.
    with s._db() as db:
        import json
        stored=dict(intent='CANCEL',order_id='456',status='UNKNOWN')
        db.execute('UPDATE submissions SET status=?,result_json=? WHERE draft_id=?',('UNKNOWN',json.dumps(stored),d['id']))
    assert restarted.status(d['id'])['status']=='UNKNOWN'


def test_applied_protection_waits_for_new_account_snapshot_before_another_mutation(tmp_path):
    s=service(tmp_path);s.stream.value['account']['positions'][0].update(sl='2480.00',tp='2520.00')
    original=s.stream.place_order
    def applied(cmd):original(cmd);return dict(status='APPLIED',position_id='123')
    s.stream.place_order=applied
    d=s.create_protection(s.stream.snapshot(),'123',{'sl':'2495.00'});s.confirm(d['id'],1,'first')
    another=s.create_protection(s.stream.snapshot(),'123',{'sl':'2496.00'})
    with pytest.raises(DomainError,match='更新'):s.confirm(another['id'],1,'second')
    assert len(s.stream.calls)==1


def test_history_reconciliation_after_restart_must_verify_reviewed_close_binding(tmp_path):
    from backend.broker_orders import BrokerOrders
    s=service(tmp_path);d=s.create_close(s.stream.snapshot(),'123',order_type='LIMIT',limit_price='2505.00')
    s.confirm(d['id'],1,'once')
    restarted=BrokerOrders(s.stream,s.journal)
    bad=dict(status='FILLED',order_id='456',position_id='999',intent='OPEN',side='SELL',order_type='LIMIT',volume_units='10.25',history_reconciled=True)
    s.stream.order_status=lambda ident:bad
    assert restarted.status(d['id'])['status']!='FILLED'
    s.stream.order_status=lambda ident:dict(bad,position_id='123',intent='CLOSE')
    assert restarted.status(d['id'])['status']=='FILLED'


def test_stream_history_cannot_clear_quarantined_close_without_binding():
    from backend.demo_market_stream import DemoMarketStream
    stream=DemoMarketStream();stream._order_results['gd-x']=dict(status='UNKNOWN',error_code='UNVERIFIED_CLOSE_ORDER',position_id='123')
    stream._history['broker_orders']=dict(status='CURRENT',items=[dict(client_order_id='gd-x',status='FILLED',position_id='999',intent='OPEN')])
    assert stream.order_status('gd-x')['status']=='UNKNOWN'
