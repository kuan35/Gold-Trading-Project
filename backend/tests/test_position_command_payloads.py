from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from scripts.position_command_payloads import close_limit_args,protection_args,protection_ack,verify_close_ack


class Message(NS):
    def HasField(self,key):return hasattr(self,key)


def positions():return [dict(id='123',side='BUY',volume_units='10.25',sl='2480',tp='2520')]


def test_limit_request_binds_position_reverses_side_and_does_not_add_stops():
    cmd=dict(position_id='123',volume_cents=1025,side='SELL',limit_price='2505.00')
    args=close_limit_args(cmd,7,9,positions(),2)
    assert args['positionId']==123 and args['orderType']==2 and args['tradeSide']==2 and args['volume']==1025
    assert args['timeInForce']==1 and 'stopLoss' not in args
    with pytest.raises(ValueError):close_limit_args(dict(cmd,side='BUY'),7,9,positions(),2)


def test_protection_omits_only_explicitly_cleared_field_and_rechecks_current_values():
    cmd=dict(position_id='123',volume_cents=1025,expected_sl='2480',expected_tp='2520',sl='2490',tp=None)
    result=protection_args(cmd,7,positions(),2)
    assert result==dict(ctidTraderAccountId=7,positionId=123,stopLoss=2490.0)
    changed=positions();changed[0]['tp']='2530'
    with pytest.raises(ValueError):protection_args(cmd,7,changed,2)


def test_protection_ack_requires_original_position_and_both_actual_protection_fields():
    cmd=dict(position_id='123',sl='2490',tp=None)
    event=Message(ctidTraderAccountId=7,position=Message(positionId=123,stopLoss=2490.0),executionType=4)
    assert protection_ack(event,cmd,7)['status']=='APPLIED'
    event.position.takeProfit=2520.0
    assert protection_ack(event,cmd,7)['status']=='UNKNOWN'
    assert protection_ack(event,cmd,8)['status']=='UNKNOWN'


def test_limit_close_ack_cannot_accept_an_unbound_opposite_entry():
    cmd=dict(position_id='123',side='SELL',volume_cents=1025)
    event=Message(order=Message(positionId=123,closingOrder=True,orderType=2,tradeData=Message(tradeSide=2,volume=1025)))
    assert verify_close_ack(dict(status='ACCEPTED'),event,cmd)['status']=='ACCEPTED'
    event.order.closingOrder=False
    assert verify_close_ack(dict(status='ACCEPTED'),event,cmd)['status']=='UNKNOWN'


def test_global_worker_event_cannot_bypass_limit_close_binding_check():
    import ast
    from pathlib import Path
    tree=ast.parse((Path(__file__).resolve().parents[2]/'scripts/stream_ctrader_demo.py').read_text(encoding='utf-8'))
    fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='execution_result')
    env=dict(account_id=7,order_ids={},request_commands={'gd-x':dict(intent='CLOSE',order_type='LIMIT',position_id='123',side='SELL',volume_cents=1025)},verify_close_ack=verify_close_ack)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'<worker-test>','exec'),env)
    event=Message(ctidTraderAccountId=7,executionType=2,order=Message(orderId=456,positionId=123,closingOrder=False,clientOrderId='gd-x',orderType=2,tradeData=Message(tradeSide=2,volume=1025)))
    assert env['execution_result'](event)['status']=='UNKNOWN'
