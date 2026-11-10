"""Pure whitelisted DEMO position commands and acknowledgement validation."""
from decimal import Decimal
from scripts.ctrader_account_payloads import close_request_args


def pending_order_fingerprint(order):
    return {k:order.get(k) for k in ('id','side','volume_units','order_type','intent','position_id','limit_price','stop_price','sl','tp','filled_lot')}


def cancel_order_args(command,account_id,orders):
    matches=[o for o in orders if o.get('id')==command.get('order_id')]
    if len(matches)!=1:raise ValueError('pending order no longer available')
    pending=matches[0]
    if pending.get('intent') not in ('OPEN','CLOSE') or pending.get('order_type') not in ('LIMIT','STOP','STOP_LIMIT'):
        raise ValueError('unsupported pending order')
    if pending.get('status') not in (None,'ACCEPTED','PARTIALLY_FILLED'):raise ValueError('order no longer pending')
    if pending_order_fingerprint(pending)!=command.get('expected_order'):raise ValueError('pending order changed')
    order_id=int(command['order_id'])
    if order_id<=0:raise ValueError('invalid order id')
    return dict(ctidTraderAccountId=account_id,orderId=order_id)


def cancel_ack(event,command,account_id):
    result=dict(status='UNKNOWN',order_id=command['order_id'])
    if int(event.ctidTraderAccountId)!=account_id or not event.HasField('order') or str(event.order.orderId)!=command['order_id']:return result
    status={5:'CANCELLED',7:'REJECTED',8:'REJECTED'}.get(int(event.executionType),'UNKNOWN')
    return dict(result,status=status)


def price(value,digits):
    p=Decimal(str(value))
    if not p.is_finite() or p<=0 or p%Decimal(1).scaleb(-digits):raise ValueError('invalid price')
    return float(p)


def close_limit_args(command,account_id,symbol_id,positions,digits):
    args=close_request_args(command,account_id,positions)
    original=next(p for p in positions if p['id']==command['position_id'])
    side='SELL' if original['side']=='BUY' else 'BUY'
    if command.get('side')!=side:raise ValueError('not closing side')
    args.update(symbolId=symbol_id,orderType=2,tradeSide=2 if side=='SELL' else 1,
                limitPrice=price(command['limit_price'],digits),timeInForce=1)
    return args


def protection_args(command,account_id,positions,digits):
    args=close_request_args(command,account_id,positions);args.pop('volume')
    p=next(p for p in positions if p['id']==command['position_id'])
    if p.get('trailing_stop_loss') or p.get('guaranteed_stop_loss'):raise ValueError('advanced protection unsupported')
    for key,field in [('sl','stopLoss'),('tp','takeProfit')]:
        old,expected=p.get(key),command.get('expected_'+key)
        if (old is None)!=(expected is None) or old is not None and Decimal(old)!=Decimal(expected):raise ValueError('protection changed')
        if command[key] is not None:args[field]=price(command[key],digits)
    return args


def protection_ack(event,command,account_id):
    result=dict(status='UNKNOWN',position_id=command['position_id'])
    if int(event.ctidTraderAccountId)!=account_id or not event.HasField('position'):return result
    p=event.position
    if str(p.positionId)!=command['position_id'] or int(event.executionType) not in (2,4):return result
    for key,field in [('sl','stopLoss'),('tp','takeProfit')]:
        actual=Decimal(str(getattr(p,field))) if p.HasField(field) else None
        desired=Decimal(command[key]) if command[key] is not None else None
        if actual!=desired:return result
    return dict(result,status='APPLIED')


def verify_close_ack(result,event,command):
    if result.get('status') not in ('ACCEPTED','PARTIALLY_FILLED','FILLED'):return result
    order=event.order
    valid=(order.HasField('closingOrder') and order.closingOrder and order.HasField('positionId') and
        str(order.positionId)==command['position_id'] and int(order.orderType)==2 and
        int(order.tradeData.tradeSide)==(2 if command['side']=='SELL' else 1) and int(order.tradeData.volume)==command['volume_cents'])
    return result if valid else dict(result,status='UNKNOWN',error_code='UNVERIFIED_CLOSE_ORDER')
