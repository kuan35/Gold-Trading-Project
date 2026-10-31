"""Sanitized broker account payloads. No SDK import, connection or order actions."""
from copy import deepcopy
from datetime import datetime,timezone
from decimal import Decimal


def money(value,digits):
    if not 0<=digits<=12:raise ValueError('invalid money precision')
    return format(Decimal(value).scaleb(-digits),'f')


def close_request_args(command,account_id,positions):
    """Whitelist a full position close; never create an opposite entry."""
    ident=command.get('position_id')
    volume=command.get('volume_cents')
    if not isinstance(ident,str) or not ident.isascii() or not ident.isdigit() or not 0<int(ident)<2**63:
        raise ValueError('invalid position')
    if type(volume) is not int or not 0<volume<2**63:raise ValueError('invalid volume')
    row=next((p for p in positions if p['id']==ident),None)
    if row is None or Decimal(row['volume_units'])*100!=volume:raise ValueError('position changed')
    return dict(ctidTraderAccountId=account_id,positionId=int(ident),volume=volume)


def optional(item,name):
    return getattr(item,name) if item.HasField(name) else None


def stamp(value):
    return datetime.fromtimestamp(int(value)/1000,timezone.utc).isoformat() if value else None


def quantity(volume,lot_size):
    if lot_size<=0 or volume<0:raise ValueError('invalid contract volume')
    return format(Decimal(volume)/lot_size,'f')


def decode_positions(positions,symbol_id,lot_size):
    return [dict(id=str(p.positionId),side={1:'BUY',2:'SELL'}[p.tradeData.tradeSide],
        volume_units=money(p.tradeData.volume,2),lot=quantity(p.tradeData.volume,lot_size),
        entry=str(p.price) if p.HasField('price') else None,
        sl=str(p.stopLoss) if p.HasField('stopLoss') else None,
        tp=str(p.takeProfit) if p.HasField('takeProfit') else None,
        trailing_stop_loss=bool(p.trailingStopLoss) if p.HasField('trailingStopLoss') else False,
        guaranteed_stop_loss=bool(p.guaranteedStopLoss) if p.HasField('guaranteedStopLoss') else False,
        opened_at_utc=stamp(optional(p.tradeData,'openTimestamp')),
        gross_pnl=None,net_pnl=None) for p in positions
        if p.tradeData.symbolId==symbol_id and p.tradeData.tradeSide in (1,2)]


def decode_order(order,symbol_id,lot_size):
    td=order.tradeData
    if td.symbolId!=symbol_id or td.tradeSide not in (1,2):return None
    status={1:'ACCEPTED',2:'FILLED',3:'REJECTED',4:'EXPIRED',5:'CANCELLED'}.get(order.orderStatus,'UNKNOWN')
    executed=optional(order,'executedVolume')
    if status=='ACCEPTED' and executed and executed<td.volume:status='PARTIALLY_FILLED'
    client_id=optional(order,'clientOrderId')
    return dict(id=str(order.orderId),order_id=str(order.orderId),
        client_order_id=client_id if client_id and client_id.startswith('gd-') else None,
        position_id=str(order.positionId) if order.HasField('positionId') else None,
        intent='CLOSE' if order.HasField('closingOrder') and order.closingOrder else 'OPEN',
        side={1:'BUY',2:'SELL'}[td.tradeSide],lot=quantity(td.volume,lot_size),
        volume_units=money(td.volume,2),filled_lot=quantity(executed,lot_size) if executed is not None else None,
        order_type={1:'MARKET',2:'LIMIT',3:'STOP',4:'PROTECTION',5:'MARKET_RANGE',6:'STOP_LIMIT'}.get(order.orderType,'OTHER'),
        status=status,limit_price=str(order.limitPrice) if order.HasField('limitPrice') else None,
        execution_price=str(order.executionPrice) if order.HasField('executionPrice') else None,
        sl=str(order.stopLoss) if order.HasField('stopLoss') else None,
        tp=str(order.takeProfit) if order.HasField('takeProfit') else None,
        created_at_utc=stamp(optional(td,'openTimestamp')),
        updated_at_utc=stamp(optional(order,'utcLastUpdateTimestamp')),
        source='ctrader_demo_xauusd')


def decode_deal(deal,symbol_id,lot_size):
    if deal.symbolId!=symbol_id or deal.tradeSide not in (1,2):return None
    close=optional(deal,'closePositionDetail')
    digits=int(close.moneyDigits) if close and close.HasField('moneyDigits') else int(deal.moneyDigits) if deal.HasField('moneyDigits') else 2
    return dict(id=str(deal.dealId),order_id=str(deal.orderId),position_id=str(deal.positionId),
        side={1:'BUY',2:'SELL'}[deal.tradeSide],lot=quantity(deal.filledVolume,lot_size),
        execution_price=str(deal.executionPrice) if deal.HasField('executionPrice') else None,
        executed_at_utc=stamp(optional(deal,'executionTimestamp')),
        status={2:'FILLED',3:'PARTIALLY_FILLED',4:'REJECTED',5:'REJECTED',6:'ERROR',7:'MISSED'}.get(deal.dealStatus,'UNKNOWN'),
        role='CLOSE' if close else 'OPEN',
        realized_gross_pnl=money(close.grossProfit,digits) if close else None,
        swap=money(close.swap,digits) if close and close.HasField('swap') else None,
        commission=money(close.commission,digits) if close and close.HasField('commission') else
            money(deal.commission,int(deal.moneyDigits) if deal.HasField('moneyDigits') else 2) if deal.HasField('commission') else None,
        source='ctrader_demo_xauusd')


def apply_unrealized(account,rows,digits,expected_ids,now):
    result=deepcopy(account)
    by_id={str(p.positionId):p for p in rows}
    complete=set(by_id)==set(expected_ids)
    for p in result['positions']:
        row=by_id.get(p['id'])
        p['gross_pnl']=money(row.grossUnrealizedPnL,digits) if row else None
        p['net_pnl']=money(row.netUnrealizedPnL,digits) if row else None
    result['pnl_status']='CURRENT' if complete else 'INCOMPLETE'
    result['pnl_updated_at_utc']=now
    result['net_unrealized_pnl']=money(sum(p.netUnrealizedPnL for p in rows),digits) if complete else None
    result['equity']=format(Decimal(result['balance'])+Decimal(result['net_unrealized_pnl']),'f') if complete and result.get('balance') is not None else None
    xau_complete=all(p['net_pnl'] is not None for p in result['positions'])
    result['xau_net_unrealized_pnl']=format(sum((Decimal(p['net_pnl']) for p in result['positions']),Decimal(0)),'f') if xau_complete and complete else None
    return result
