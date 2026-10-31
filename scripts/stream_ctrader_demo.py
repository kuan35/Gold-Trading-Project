"""Single cTrader DEMO stream for local quotes and explicitly confirmed orders.

Stdout is newline-delimited, sanitized JSON. Stdin accepts only a validated
order command from the loopback parent. Credentials and raw responses never
leave this process. No live-account endpoint is used.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
import sys
import time
from hashlib import sha256
from threading import Thread

from scripts.check_ctrader_demo import decode_spot_quote, load_local_config
from scripts.ctrader_account_payloads import money, decode_positions, decode_order, decode_deal, apply_unrealized, close_request_args
from scripts.live_candles import LiveCandles
from scripts.position_command_payloads import close_limit_args,protection_args,protection_ack,verify_close_ack
from backend.order_binding import history_result


PERIODS = {'5m': (5, 5, 7), '15m': (7, 15, 21), '1h': (9, 60, 60)}


def emit(kind: str, data: dict) -> None:
    print(json.dumps({'kind': kind, 'data': data}, separators=(',', ':')), flush=True)


def price(value: int, digits: int) -> str:
    return format((Decimal(value) / 100000).quantize(Decimal(1).scaleb(-digits)), 'f')


def decode_bar(bar, digits: int, minutes: int, now_ms: int, *,closed_only:bool=True) -> dict | None:
    opened = int(bar.utcTimestampInMinutes) * 60
    if not opened or opened*1000>now_ms or closed_only and (opened + minutes * 60) * 1000 > now_ms:
        return None  # A forming candle cannot enter case retrieval or the closed-bar chart.
    low = int(bar.low)
    values = [low + int(bar.deltaOpen), low + int(bar.deltaHigh), low,
              low + int(bar.deltaClose)]
    if min(values) <= 0 or values[1] < max(values):
        return None
    return {'time': opened, 'open': float(price(values[0], digits)),
            'high': float(price(values[1], digits)), 'low': float(price(values[2], digits)),
            'close': float(price(values[3], digits)), 'volume': int(bar.volume)}


def decode_symbol_schedule(symbol) -> dict:
    """Carry the broker's own XAUUSD trading sessions with the candle snapshot."""
    intervals = sorted((int(item.startSecond), int(item.endSecond))
                       for item in symbol.schedule)
    return {'time_zone': str(symbol.scheduleTimeZone),
            'intervals': [{'start_second': start, 'end_second': end}
                          for start, end in intervals]}


def run(config: dict[str, str], *, readonly_live: bool=False) -> None:
    from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
    from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import ProtoHeartbeatEvent
    from ctrader_open_api.messages.OpenApiMessages_pb2 import (
        ProtoOAAccountAuthReq, ProtoOAAccountAuthRes,
        ProtoOAApplicationAuthReq, ProtoOAApplicationAuthRes,
        ProtoOAAssetListReq, ProtoOAAssetListRes,
        ProtoOAGetAccountListByAccessTokenReq, ProtoOAGetAccountListByAccessTokenRes,
        ProtoOAGetPositionUnrealizedPnLReq, ProtoOAGetPositionUnrealizedPnLRes,
        ProtoOAGetTrendbarsReq, ProtoOAGetTrendbarsRes,
        ProtoOAReconcileReq, ProtoOAReconcileRes,
        ProtoOAOrderListReq, ProtoOAOrderListRes, ProtoOADealListReq, ProtoOADealListRes,
        ProtoOASubscribeLiveTrendbarReq, ProtoOASubscribeSpotsReq, ProtoOASubscribeSpotsRes,
        ProtoOASpotEvent, ProtoOASymbolByIdReq, ProtoOASymbolByIdRes,
        ProtoOASymbolsListReq, ProtoOASymbolsListRes,
        ProtoOATraderReq, ProtoOATraderRes,
        ProtoOANewOrderReq, ProtoOAClosePositionReq, ProtoOAAmendPositionSLTPReq, ProtoOACancelOrderReq,ProtoOAExecutionEvent, ProtoOAOrderErrorEvent,
    )
    from twisted.internet import reactor

    client = Client(EndPoints.PROTOBUF_LIVE_HOST if readonly_live else EndPoints.PROTOBUF_DEMO_HOST, EndPoints.PROTOBUF_PORT, TcpProtocol)
    if readonly_live:
        from scripts.live_readonly_policy import ReadOnlyClient
        client=ReadOnlyClient(client)
    account_id: int | None = None
    symbol_id: int | None = None
    digits = 2
    scope = 'UNKNOWN'
    selected_demo = False
    symbol_rules: dict = {}
    bars: dict[str, dict[int, dict]] = {period: {} for period in PERIODS}
    live_candles=LiveCandles()
    spot_parts: dict[str, int] = {}
    account: dict = {'status': 'LOADING', 'balance': None, 'equity': None,
                     'currency': None, 'positions': [], 'pending_orders': []}
    asset_names: dict[int, str] = {}
    order_ids: dict[int, str] = {}
    request_ids: set[str] = set()
    request_commands: dict[str,dict] = {}
    stopping = False
    position_ids: set[str] = set()
    account_generation = 0
    pending = {"account": False, "pnl": False, "orders": False, "deals": False}

    def failed(stage: str) -> None:
        nonlocal stopping
        if stopping:
            return
        stopping = True
        emit('status', {'status': 'UNAVAILABLE', 'stage': stage})
        # A timed-out startup request otherwise leaves a live child process in
        # UNAVAILABLE forever. Exiting lets the parent restart the DEMO stream.
        reactor.callLater(0, reactor.stop)

    def send(request, stage: str, callback) -> None:
        try:
            client.send(request, responseTimeoutInSeconds=20).addCallbacks(
                callback, lambda _failure: failed(stage))
        except Exception:
            failed(stage)

    def heartbeat() -> None:
        try:
            client.send(ProtoHeartbeatEvent())
        except Exception:
            failed('heartbeat')
        reactor.callLater(10, heartbeat)

    def optional_send(request, callback, on_error) -> None:
        def received(message):
            try: callback(message)
            except (KeyError, TypeError, ValueError, ArithmeticError): on_error()
        try:
            client.send(request, responseTimeoutInSeconds=10).addCallbacks(
                received, lambda _failure: on_error())
        except Exception:
            on_error()

    def refresh_account() -> None:
        nonlocal account_generation
        if account_id is None or pending['account']:return
        account_generation += 1
        pending['account']=True
        send(ProtoOATraderReq(ctidTraderAccountId=account_id), 'trader', trader_received)

    def trader_received(message) -> None:
        if message.payloadType != ProtoOATraderRes().payloadType:
            failed('trader');return
        trader=Protobuf.extract(message).trader
        precision=int(trader.moneyDigits) if trader.HasField('moneyDigits') else 2
        account['balance']=money(trader.balance,precision)
        account['currency']=asset_names.get(int(trader.depositAssetId))
        send(ProtoOAReconcileReq(ctidTraderAccountId=account_id), 'reconcile', reconciled)

    def reconciled(message) -> None:
        nonlocal position_ids
        pending['account']=False
        if message.payloadType != ProtoOAReconcileRes().payloadType:
            failed('reconcile');return
        response=Protobuf.extract(message)
        position_ids={str(p.positionId) for p in response.position}
        account['positions']=decode_positions(response.position,symbol_id,symbol_rules['lot_size_cents'])
        account['pending_orders']=[value for o in response.order
            if (value:=decode_order(o,symbol_id,symbol_rules['lot_size_cents']))]
        account['all_positions_count']=len(response.position)
        account['all_pending_orders_count']=len(response.order)
        account['status']='CURRENT'
        account['updated_at_utc']=datetime.now(timezone.utc).isoformat()
        account['account_key']=sha256(f'ctrader-{"live" if readonly_live else "demo"}:{account_id}'.encode()).hexdigest()[:24]
        account['pnl_status']='LOADING'
        account['equity']=account['net_unrealized_pnl']=account['xau_net_unrealized_pnl']=None
        if not position_ids:
            account.update(apply_unrealized(account,[],2,set(),datetime.now(timezone.utc).isoformat()))
        if not position_ids:emit('account',dict(account))
        refresh_pnl()

    def pnl_failed() -> None:
        pending['pnl']=False
        account['pnl_status']='UNAVAILABLE'
        emit('account',dict(account))

    def refresh_pnl() -> None:
        if account_id is None or not position_ids or pending['pnl'] or pending['account']:return
        pending['pnl']=True
        generation=account_generation
        optional_send(ProtoOAGetPositionUnrealizedPnLReq(ctidTraderAccountId=account_id),
            lambda message:pnl_received(message,generation),pnl_failed)

    def pnl_received(message,generation) -> None:
        pending['pnl']=False
        if generation!=account_generation:
            refresh_pnl();return
        if message.payloadType != ProtoOAGetPositionUnrealizedPnLRes().payloadType:
            pnl_failed();return
        response=Protobuf.extract(message)
        if int(response.ctidTraderAccountId)!=account_id:
            pnl_failed();return
        account.update(apply_unrealized(account,response.positionUnrealizedPnL,
            int(response.moneyDigits),position_ids,datetime.now(timezone.utc).isoformat()))
        emit('account',dict(account))

    def history_failed(kind) -> None:
        pending[kind]=False
        emit('broker_'+kind,{'status':'UNAVAILABLE','reason':'BROKER_HISTORY_UNAVAILABLE'})

    def history_received(message,kind,from_ms,to_ms) -> None:
        pending[kind]=False
        expected=ProtoOAOrderListRes if kind=='orders' else ProtoOADealListRes
        if message.payloadType!=expected().payloadType:
            history_failed(kind);return
        response=Protobuf.extract(message)
        if int(response.ctidTraderAccountId)!=account_id:
            history_failed(kind);return
        decode=decode_order if kind=='orders' else decode_deal
        rows=[value for item in getattr(response,'order' if kind=='orders' else 'deal')
              if (value:=decode(item,symbol_id,symbol_rules['lot_size_cents']))]
        rows.sort(key=lambda v:(v.get('updated_at_utc') or v.get('executed_at_utc') or v.get('created_at_utc') or '',v['id']),reverse=True)
        limited=bool(response.hasMore) or len(rows)>500
        emit('broker_'+kind,dict(status='CURRENT',items=rows[:500],has_more=limited,
            from_utc=datetime.fromtimestamp(from_ms/1000,timezone.utc).isoformat(),
            to_utc=datetime.fromtimestamp(to_ms/1000,timezone.utc).isoformat(),
            updated_at_utc=datetime.now(timezone.utc).isoformat()))
        if kind=='orders':
            for row in rows:
                if row['client_order_id']:
                    order_ids[int(row['order_id'])]=row['client_order_id']
                    command=request_commands.get(row['client_order_id'])
                    context=dict(command,closing_side=command.get('side')) if command else None
                    emit('order_event',history_result(row,context))

    def refresh_history() -> None:
        if account_id is None or symbol_id is None or not symbol_rules:return
        to_ms=int(time.time()*1000);from_ms=to_ms-30*86400000
        for kind,request_type in (('orders',ProtoOAOrderListReq),('deals',ProtoOADealListReq)):
            if pending[kind]:continue
            pending[kind]=True
            args=dict(ctidTraderAccountId=account_id,fromTimestamp=from_ms,toTimestamp=to_ms)
            if kind=='deals':args['maxRows']=500
            optional_send(request_type(**args),
                lambda message,k=kind:history_received(message,k,from_ms,to_ms),
                lambda k=kind:history_failed(k))

    def poll_account() -> None:
        refresh_account();reactor.callLater(5,poll_account)

    def poll_pnl() -> None:
        refresh_pnl();reactor.callLater(2,poll_pnl)

    def poll_history() -> None:
        refresh_history();reactor.callLater(15,poll_history)

    def refresh_bars() -> None:
        if account_id is None or symbol_id is None:
            return
        for label, (period, minutes, days) in PERIODS.items():
            now_ms = int(time.time() * 1000)
            request = ProtoOAGetTrendbarsReq(ctidTraderAccountId=account_id,
                symbolId=symbol_id, period=period, count=500,
                fromTimestamp=now_ms - days * 86400000, toTimestamp=now_ms)
            send(request, f'bars_{label}', lambda msg, key=label, span=minutes:
                 bars_received(msg, key, span))
        # A newly closed candle is not guaranteed to arrive in a spot event.
        # Refresh the three native windows soon after each 5m boundary.
        reactor.callLater(30, refresh_bars)

    def bars_received(message, label: str, minutes: int) -> None:
        if message.payloadType != ProtoOAGetTrendbarsRes().payloadType:
            failed(f'bars_{label}')
            return
        for item in Protobuf.extract(message).trendbar:
            now_ms=int(time.time()*1000)
            bar=decode_bar(item,digits,minutes,now_ms)
            if bar:
                bars[label][bar['time']] = bar
            else:
                seed=decode_bar(item,digits,minutes,now_ms,closed_only=False)
                if seed:
                    live_candles.seed(label,seed)
                    publish_forming(label)
        bars[label] = dict(sorted(bars[label].items())[-500:])
        emit('bars', {'interval': label, 'bars': list(bars[label].values()),
                      'source': 'ctrader_demo_xauusd', 'closed_only': True})

    def asset_listed(message) -> None:
        if message.payloadType == ProtoOAAssetListRes().payloadType:
            for asset in Protobuf.extract(message).asset:
                asset_names[int(asset.assetId)] = asset.name
        poll_account()
        poll_pnl()
        poll_history()
        refresh_bars()

    def symbol_received(message) -> None:
        nonlocal digits
        if message.payloadType == ProtoOASymbolByIdRes().payloadType:
            response = Protobuf.extract(message)
            if response.symbol:
                symbol = response.symbol[0]
                digits = max(0, min(8, int(symbol.digits)))
                if all(symbol.HasField(field) and int(getattr(symbol, field)) > 0
                       for field in ('lotSize', 'minVolume', 'maxVolume', 'stepVolume')):
                    symbol_rules.update(lot_size_cents=int(symbol.lotSize),
                                        min_volume_cents=int(symbol.minVolume),
                                        max_volume_cents=int(symbol.maxVolume),
                                        step_volume_cents=int(symbol.stepVolume), digits=digits)
                    symbol_rules['trading_schedule'] = decode_symbol_schedule(symbol)
                    emit('symbol', dict(symbol_rules))
                    emit('tick_volume_source',{'source_key':sha256(f'ctrader-{"live" if readonly_live else "demo"}:{account_id}:{symbol_id}'.encode()).hexdigest()})
                    emit('status', {'status': 'CONNECTED', 'scope': scope,
                                    'orders_enabled': selected_demo and scope == 'TRADE'})
        send(ProtoOAAssetListReq(ctidTraderAccountId=account_id), 'assets', asset_listed)

    def spots_subscribed(message) -> None:
        if message.payloadType != ProtoOASubscribeSpotsRes().payloadType:
            failed('spots')
            return
        for period, _, _ in PERIODS.values():
            send(ProtoOASubscribeLiveTrendbarReq(ctidTraderAccountId=account_id,
                 symbolId=symbol_id, period=period), 'live_bars', lambda _message: None)
        send(ProtoOASymbolByIdReq(ctidTraderAccountId=account_id,
             symbolId=[symbol_id]), 'symbol_detail', symbol_received)
        emit('status', {'status': 'CONNECTED', 'scope': scope, 'orders_enabled': False})

    def symbols_listed(message) -> None:
        nonlocal symbol_id
        if message.payloadType != ProtoOASymbolsListRes().payloadType:
            failed('symbols')
            return
        symbol = next((item for item in Protobuf.extract(message).symbol
                       if item.enabled and item.symbolName.upper() == 'XAUUSD'), None)
        if symbol is None:
            failed('xauusd_not_available')
            return
        symbol_id = int(symbol.symbolId)
        send(ProtoOASubscribeSpotsReq(ctidTraderAccountId=account_id,
             symbolId=[symbol_id], subscribeToSpotTimestamp=True), 'spots', spots_subscribed)

    def account_authorized(message) -> None:
        if message.payloadType != ProtoOAAccountAuthRes().payloadType:
            failed('account_auth')
            return
        send(ProtoOASymbolsListReq(ctidTraderAccountId=account_id,
             includeArchivedSymbols=False), 'symbols', symbols_listed)

    def accounts_listed(message) -> None:
        nonlocal account_id, scope, selected_demo
        if message.payloadType != ProtoOAGetAccountListByAccessTokenRes().payloadType:
            failed('account_list')
            return
        response = Protobuf.extract(message)
        scope = 'TRADE' if response.permissionScope == 1 else 'VIEW'
        demo = sorted((item for item in response.ctidTraderAccount if not item.isLive),
                      key=lambda item: item.ctidTraderAccountId)
        requested = config.get('CTRADER_ACCOUNT_ID', '')
        selected = next((item for item in demo if str(item.ctidTraderAccountId) == requested), None) if requested else (demo[0] if demo else None)
        if readonly_live:
            from scripts.live_readonly_policy import select_live
            try:selected=select_live(response.ctidTraderAccount,requested)
            except ValueError:
                failed('live_account_not_found');return
        if selected is None:
            failed('demo_account_not_found')
            return
        account_id = int(selected.ctidTraderAccountId)
        selected_demo = not selected.isLive
        send(ProtoOAAccountAuthReq(ctidTraderAccountId=account_id,
             accessToken=config['CTRADER_ACCESS_TOKEN']), 'account_auth', account_authorized)

    def app_authorized(message) -> None:
        if message.payloadType != ProtoOAApplicationAuthRes().payloadType:
            failed('application_auth')
            return
        send(ProtoOAGetAccountListByAccessTokenReq(accessToken=config['CTRADER_ACCESS_TOKEN']),
             'account_list', accounts_listed)

    def connected(_client) -> None:
        send(ProtoOAApplicationAuthReq(clientId=config['CTRADER_CLIENT_ID'],
             clientSecret=config['CTRADER_CLIENT_SECRET']), 'application_auth', app_authorized)

    def execution_result(event,request_ident=None) -> dict | None:
        command=request_commands.get(request_ident,{})
        if command.get('intent')=='PROTECT':
            return dict(protection_ack(event,command,account_id),client_order_id=request_ident)
        if int(event.ctidTraderAccountId) != account_id or not event.HasField('order'):
            return None
        order = event.order
        position_id=str(event.position.positionId) if event.HasField('position') else str(order.positionId) if order.HasField('positionId') else None
        client_order_id = request_ident or order_ids.get(int(order.orderId))
        if not client_order_id and order.HasField('closingOrder') and order.closingOrder:
            return None  # A manual/SL/TP close is not a response to our close request.
        if not client_order_id:
            client_order_id=str(order.clientOrderId) if order.HasField('clientOrderId') else ''
        if not client_order_id.startswith('gd-'):
            return None
        event_type = int(event.executionType)
        if event_type==8 and not request_ident:return None
        if command.get('intent')=='CANCEL':
            original=order_ids.get(int(order.orderId))
            if original and original!=request_ident and event_type in (3,11):
                prior=execution_result(event,original)
                if prior:emit('order_event',prior)
            status={5:'CANCELLED',7:'REJECTED',8:'REJECTED'}.get(event_type,'UNKNOWN')
            return dict(client_order_id=request_ident,status=status,order_id=str(order.orderId),position_id=position_id)
        order_ids[int(order.orderId)] = client_order_id
        status = {2: 'ACCEPTED', 3: 'FILLED', 5: 'CANCELLED', 6: 'EXPIRED',
                  7: 'REJECTED', 8:'REJECTED',11: 'PARTIALLY_FILLED'}.get(event_type, 'UNKNOWN')
        result={'client_order_id': client_order_id, 'status': status,
                'order_id': str(order.orderId),
                'position_id': position_id,
                'execution_price': str(order.executionPrice) if order.HasField('executionPrice') else None,
                'error_code': str(event.errorCode)[:80] if event.HasField('errorCode') else None}
        command=request_commands.get(client_order_id,{})
        if command.get('intent')=='CLOSE' and command.get('order_type')=='LIMIT':
            result=verify_close_ack(result,event,command)
        return result

    def handle_command(command: dict) -> None:
        ident = str(command.get('client_order_id', ''))
        if not ident.startswith('gd-') or len(ident) > 50:
            return
        if not selected_demo or scope != 'TRADE' or account_id is None or symbol_id is None or not symbol_rules:
            emit('order_result', {'client_order_id': ident, 'status': 'REJECTED',
                                  'error_code': 'DEMO_TRADE_UNAVAILABLE'})
            return
        try:
            volume = int(command['volume_cents'])
            closing=command.get('intent')=='CLOSE'
            protection=command.get('intent')=='PROTECT';cancelling=command.get('intent')=='CANCEL'
            limit_close=closing and command.get('order_type')=='LIMIT'
            cancelled_original=None
            if protection:
                request=ProtoOAAmendPositionSLTPReq(**protection_args(command,account_id,account['positions'],digits))
            elif cancelling:
                pending=next((o for o in account.get('pending_orders',[]) if o.get('id')==command.get('order_id') and o.get('position_id')==command.get('position_id') and o.get('intent')=='CLOSE' and o.get('order_type')=='LIMIT'),None)
                if pending is None:raise ValueError('pending order changed')
                cancelled_original=order_ids.get(int(command['order_id']))
                request=ProtoOACancelOrderReq(ctidTraderAccountId=account_id,orderId=int(command['order_id']))
            elif limit_close:
                request=ProtoOANewOrderReq(**close_limit_args(command,account_id,symbol_id,account['positions'],digits),clientOrderId=ident,label='Gold Desk DEMO close')
            elif closing:
                args=close_request_args(command,account_id,account['positions'])
                request=ProtoOAClosePositionReq(**args)
            else:
                request=build_open_request(command,ident,volume)
            request_ids.add(ident)
            request_commands[ident]=dict(command)
            def order_received(message):
                if message.payloadType == ProtoOAExecutionEvent().payloadType:
                    event=Protobuf.extract(message)
                    result = protection_ack(event,command,account_id) if protection else execution_result(event,ident)
                    if limit_close and result:
                        result=verify_close_ack(result,event,command)
                        if result.get('error_code')=='UNVERIFIED_CLOSE_ORDER' and event.HasField('order') and int(event.executionType)==2:
                            # Quarantine an unexpected non-closing pending order;
                            # never retry it as an ordinary reverse entry.
                            client.send(ProtoOACancelOrderReq(ctidTraderAccountId=account_id,orderId=int(event.order.orderId)),responseTimeoutInSeconds=12).addErrback(lambda _:None)
                    if cancelling and result:
                        if cancelled_original and result['status'] in ('CANCELLED','FILLED','PARTIALLY_FILLED','EXPIRED'):
                            emit('order_event',dict(result,client_order_id=cancelled_original))
                        if cancelled_original:order_ids[int(command['order_id'])]=cancelled_original
                        if result['status'] not in ('CANCELLED','REJECTED'):result=dict(result,status='UNKNOWN')
                    emit('order_result',dict(result or {'status':'UNKNOWN'},client_order_id=ident))
                    reactor.callLater(1,refresh_account);reactor.callLater(1,refresh_history)
                elif message.payloadType == ProtoOAOrderErrorEvent().payloadType:
                    event = Protobuf.extract(message)
                    emit('order_result', {'client_order_id': ident, 'status': 'REJECTED',
                                          'error_code': str(event.errorCode)[:80]})
                else:
                    emit('order_result', {'client_order_id': ident, 'status': 'UNKNOWN'})
            client.send(request, clientMsgId=ident, responseTimeoutInSeconds=12).addCallbacks(
                order_received, lambda _failure: emit('order_result',
                    {'client_order_id': ident, 'status': 'UNKNOWN'}))
        except (KeyError, TypeError, ValueError, OverflowError):
            emit('order_result', {'client_order_id': ident, 'status': 'REJECTED',
                                  'error_code': 'INVALID_DEMO_ORDER'})
        except Exception:
            emit('order_result', {'client_order_id': ident, 'status': 'UNKNOWN'})

    def build_open_request(command,ident,volume):
        if command.get('intent','OPEN')!='OPEN':raise ValueError('invalid intent')
        if volume < symbol_rules['min_volume_cents'] or volume > symbol_rules['max_volume_cents'] or \
                (volume - symbol_rules['min_volume_cents']) % symbol_rules['step_volume_cents']:
            raise ValueError('volume')
        side = {'BUY': 1, 'SELL': 2}[command['side']]
        order_type = {'MARKET': 1, 'LIMIT': 2}[command['order_type']]
        args = dict(ctidTraderAccountId=account_id, symbolId=symbol_id,
                    orderType=order_type, tradeSide=side, volume=volume,
                    clientOrderId=ident, label='GoldDesk-DEMO')
        if order_type == 2:
            args['limitPrice'] = float(command['limit_price'])
            if command.get('sl') is not None:
                args['stopLoss'] = float(command['sl'])
            if command.get('tp') is not None:
                args['takeProfit'] = float(command['tp'])
        else:
            if command.get('relative_sl') is not None:
                args['relativeStopLoss'] = int(command['relative_sl'])
            if command.get('relative_tp') is not None:
                args['relativeTakeProfit'] = int(command['relative_tp'])
        return ProtoOANewOrderReq(**args)


    def read_commands() -> None:
        for line in sys.stdin:
            try:
                command = json.loads(line)
                if isinstance(command, dict) and command.get('kind') == 'place_order':
                    reactor.callFromThread(handle_command, command)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

    def publish_forming(label=None) -> None:
        for key in ([label] if label else PERIODS):
            frame=live_candles.frame(key)
            if frame:emit('forming',{'interval':key,'forming':frame})

    def message_received(_client, message) -> None:
        if message.payloadType == ProtoOAExecutionEvent().payloadType:
            correlation=getattr(message,'clientMsgId','')
            result = execution_result(Protobuf.extract(message),correlation if correlation in request_ids else None)
            if result:
                emit('order_event', result)
                reactor.callLater(1, refresh_account)
                reactor.callLater(1, refresh_history)
            return
        if message.payloadType != ProtoOASpotEvent().payloadType:
            return
        event = Protobuf.extract(message)
        if event.ctidTraderAccountId != account_id or event.symbolId != symbol_id:
            return
        if event.HasField('bid'):
            spot_parts['bid'] = event.bid
        if event.HasField('ask'):
            spot_parts['ask'] = event.ask
        if event.HasField('timestamp'):
            spot_parts['timestamp'] = event.timestamp
        if event.HasField('bid') and event.HasField('timestamp'):
            live_candles.observe(int(event.bid),int(event.timestamp),digits,int(time.time()*1000))
            publish_forming()
        if 'bid' in spot_parts and 'ask' in spot_parts:
            quote = decode_spot_quote(spot_parts['bid'], spot_parts['ask'],
                                      spot_parts.get('timestamp', 0), int(time.time() * 1000))
            if quote:
                emit('quote', quote)
        for item in event.trendbar:
            label = next((name for name, (value, _, _) in PERIODS.items()
                          if value == item.period), None)
            if label:
                decoded = decode_bar(item, digits, PERIODS[label][1], int(time.time() * 1000))
                if decoded:
                    bars[label][decoded['time']] = decoded
                    bars[label] = dict(sorted(bars[label].items())[-500:])
                    emit('bars', {'interval': label, 'bars': list(bars[label].values()),
                                  'source': 'ctrader_demo_xauusd', 'closed_only': True})

    client.setConnectedCallback(connected)
    client.setMessageReceivedCallback(message_received)
    client.startService()
    if not readonly_live:
        Thread(target=read_commands, daemon=True, name='ctrader-demo-command-reader').start()
    reactor.callLater(10, heartbeat)
    reactor.run(installSignalHandlers=False)


def main() -> int:
    try:
        config = load_local_config()
        if not config.get('CTRADER_ACCESS_TOKEN'):
            raise ValueError('ACCESS_TOKEN_MISSING')
    except ValueError as error:
        emit('status', {'status': str(error)})
        return 2
    try:
        run(config)
    except Exception:
        emit('status', {'status': 'SDK_OR_CONNECTION_ERROR'})
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
