from datetime import datetime,timedelta,timezone
from types import SimpleNamespace as N
from copy import deepcopy
import ast
from pathlib import Path
import pytest

from scripts import ctrader_account_payloads as payload


class Proto(N):
    def HasField(self,name):return hasattr(self,name) and getattr(self,name) is not None


def test_broker_pnl_preserves_sign_and_precision_in_account_currency():
    a={'balance':'10000.00','currency':'EUR','positions':[{'id':'1'},{'id':'2'}]}
    rows=[Proto(positionId=1,grossUnrealizedPnL=123456,netUnrealizedPnL=112345),
          Proto(positionId=2,grossUnrealizedPnL=-98765,netUnrealizedPnL=-99999)]
    r=payload.apply_unrealized(a,rows,4,{'1','2'},'2026-10-21T00:00:00+00:00')
    assert r['positions'][0]['net_pnl']=='11.2345'
    assert r['positions'][1]['net_pnl']=='-9.9999'
    assert r['net_unrealized_pnl']=='1.2346' and r['equity']=='10001.2346'
    assert r['currency']=='EUR' and r['pnl_status']=='CURRENT'
    assert 'net_pnl' not in a['positions'][0]


def test_missing_pnl_row_does_not_become_zero_or_confirm_wrong_equity():
    a={'balance':'100','currency':'USD','positions':[{'id':'1'},{'id':'2'}]}
    r=payload.apply_unrealized(a,[Proto(positionId=1,grossUnrealizedPnL=10,netUnrealizedPnL=8)],2,{'1','2'},'now')
    assert r['positions'][1]['net_pnl'] is None
    assert r['equity'] is None and r['pnl_status']=='INCOMPLETE'


def test_xau_positions_and_pending_use_broker_contract_size_and_whitelisted_fields():
    td=Proto(symbolId=4,tradeSide=2,volume=1250,openTimestamp=1800000000000,comment='private')
    p=Proto(positionId=91,tradeData=td,price=4000.5,stopLoss=4010.0)
    rows=payload.decode_positions([p],4,10000)
    assert rows[0]['lot']=='0.125' and rows[0]['volume_units']=='12.50'
    assert rows[0]['side']=='SELL' and rows[0]['tp'] is None
    assert 'private' not in str(rows)
    assert payload.decode_positions([p],8,10000)==[]


def test_history_is_actual_execution_not_requested_volume_and_money_uses_own_precision():
    td=Proto(symbolId=4,tradeSide=1,volume=5000,openTimestamp=1800000000000)
    order=Proto(orderId=7,tradeData=td,orderType=2,orderStatus=2,executedVolume=2500,
        executionPrice=4001.25,clientOrderId='gd-example',utcLastUpdateTimestamp=1800000001000)
    r=payload.decode_order(order,4,10000)
    assert r['lot']=='0.5' and r['filled_lot']=='0.25' and r['status']=='FILLED'
    close=Proto(grossProfit=-12345,swap=10,commission=-50,moneyDigits=3)
    deal=Proto(dealId=8,orderId=7,positionId=9,symbolId=4,tradeSide=2,
        filledVolume=2500,executionPrice=4000.1,executionTimestamp=1800000002000,
        dealStatus=2,closePositionDetail=close)
    d=payload.decode_deal(deal,4,10000)
    assert d['lot']=='0.25' and d['realized_gross_pnl']=='-12.345'
    assert d['swap']=='0.010' and d['commission']=='-0.050'
    assert d['role']=='CLOSE' and 'net_pnl' not in d


def test_parent_marks_pnl_stale_independently_of_fresh_account_and_tick():
    from backend.demo_market_stream import DemoMarketStream
    stream=DemoMarketStream();stream._start=lambda:None;stream._status='CONNECTED'
    now=datetime.now(timezone.utc)
    stream._account={'status':'CURRENT','updated_at_utc':now.isoformat(),'positions':[{'id':'1','net_pnl':'5'}],
        'pnl_status':'CURRENT','pnl_updated_at_utc':(now-timedelta(seconds=20)).isoformat()}
    a=stream.snapshot()['account']
    assert a['status']=='CURRENT' and a['pnl_status']=='STALE'
    stream._status='DISCONNECTED'
    assert stream.snapshot()['account']['status']=='STALE'


def test_history_restores_status_after_restart_without_resending():
    from backend.demo_market_stream import DemoMarketStream
    stream=DemoMarketStream()
    stream._history={'broker_orders':{'status':'CURRENT','items':[
        {'client_order_id':'gd-saved','order_id':'12','status':'FILLED','execution_price':'4000.25'}]}}
    assert stream.order_status('gd-saved')['status']=='FILLED'
    assert stream.order_status('gd-other') is None
    assert stream._process is None


def test_entry_deal_preserves_its_commission():
    deal=Proto(dealId=8,orderId=7,positionId=9,symbolId=4,tradeSide=1,
        filledVolume=1000,dealStatus=2,commission=-123,moneyDigits=2)
    row=payload.decode_deal(deal,4,10000)
    assert row['commission']=='-1.23' and row['realized_gross_pnl'] is None


def test_old_pnl_reply_is_not_applied_to_a_reconciled_position_volume():
    # Exercise the real callback body without importing the SDK or opening sockets.
    tree=ast.parse(Path('scripts/stream_ctrader_demo.py').read_text(encoding='utf-8'))
    run=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run')
    callback=next(n for n in run.body if isinstance(n,ast.FunctionDef) and n.name=='pnl_received')
    refreshed=[]
    account={'positions':[{'id':'1','lot':'0.20'}]}
    scope={'pending':{'pnl':True},'account_generation':2,'account':account,
        'refresh_pnl':lambda:refreshed.append(True)}
    exec(compile(ast.Module(body=[callback],type_ignores=[]),'callback','exec'),scope)
    scope['pnl_received'](object(),1)
    assert account=={'positions':[{'id':'1','lot':'0.20'}]}
    assert refreshed==[True] and scope['pending']['pnl'] is False
