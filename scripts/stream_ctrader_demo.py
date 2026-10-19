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
from threading import Thread

from scripts.check_ctrader_demo import decode_spot_quote, load_local_config


PERIODS = {'5m': (5, 5, 2), '15m': (7, 15, 5), '1h': (9, 60, 12)}


def emit(kind: str, data: dict) -> None:
    print(json.dumps({'kind': kind, 'data': data}, separators=(',', ':')), flush=True)


def price(value: int, digits: int) -> str:
    return format((Decimal(value) / 100000).quantize(Decimal(1).scaleb(-digits)), 'f')


def decode_bar(bar, digits: int, minutes: int, now_ms: int) -> dict | None:
    opened = int(bar.utcTimestampInMinutes) * 60
    if not opened or (opened + minutes * 60) * 1000 > now_ms:
        return None  # A forming candle cannot enter case retrieval or the closed-bar chart.
    low = int(bar.low)
    values = [low + int(bar.deltaOpen), low + int(bar.deltaHigh), low,
              low + int(bar.deltaClose)]
    if min(values) <= 0 or values[1] < max(values):
        return None
    return {'time': opened, 'open': float(price(values[0], digits)),
            'high': float(price(values[1], digits)), 'low': float(price(values[2], digits)),
            'close': float(price(values[3], digits)), 'volume': int(bar.volume)}


def money(value: int, digits: int) -> str:
    if not 0 <= digits <= 12:
        raise ValueError('invalid money precision')
    return format(Decimal(value).scaleb(-digits), 'f')


def run(config: dict[str, str]) -> None:
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
        ProtoOASubscribeLiveTrendbarReq, ProtoOASubscribeSpotsReq, ProtoOASubscribeSpotsRes,
        ProtoOASpotEvent, ProtoOASymbolByIdReq, ProtoOASymbolByIdRes,
        ProtoOASymbolsListReq, ProtoOASymbolsListRes,
        ProtoOATraderReq, ProtoOATraderRes,
        ProtoOANewOrderReq, ProtoOAExecutionEvent, ProtoOAOrderErrorEvent,
    )
    from twisted.internet import reactor

    client = Client(EndPoints.PROTOBUF_DEMO_HOST, EndPoints.PROTOBUF_PORT, TcpProtocol)
    account_id: int | None = None
    symbol_id: int | None = None
    digits = 2
    scope = 'UNKNOWN'
    selected_demo = False
    symbol_rules: dict = {}
    bars: dict[str, dict[int, dict]] = {period: {} for period in PERIODS}
    spot_parts: dict[str, int] = {}
    account: dict = {'status': 'LOADING', 'balance': None, 'equity': None,
                     'currency': None, 'positions': [], 'pending_orders': []}
    asset_names: dict[int, str] = {}
    order_ids: dict[int, str] = {}

    def failed(stage: str) -> None:
        emit('status', {'status': 'UNAVAILABLE', 'stage': stage})

    def send(request, stage: str, callback) -> None:
        try:
            client.send(request, responseTimeoutInSeconds=10).addCallbacks(
                callback, lambda _failure: failed(stage))
        except Exception:
            failed(stage)

    def heartbeat() -> None:
        try:
            client.send(ProtoHeartbeatEvent())
        except Exception:
            failed('heartbeat')
        reactor.callLater(10, heartbeat)

    def refresh_account() -> None:
        if account_id is None:
            return
        send(ProtoOATraderReq(ctidTraderAccountId=account_id), 'trader', trader_received)

    def trader_received(message) -> None:
        if message.payloadType != ProtoOATraderRes().payloadType:
            failed('trader')
            return
        trader = Protobuf.extract(message).trader
        precision = int(trader.moneyDigits) if trader.HasField('moneyDigits') else 2
        account['balance'] = money(trader.balance, precision)
        account['currency'] = asset_names.get(int(trader.depositAssetId))
        account['status'] = 'CURRENT'
        account['updated_at_utc'] = datetime.now(timezone.utc).isoformat()
        send(ProtoOAReconcileReq(ctidTraderAccountId=account_id), 'reconcile', reconciled)

    def reconciled(message) -> None:
        if message.payloadType != ProtoOAReconcileRes().payloadType:
            failed('reconcile')
            return
        response = Protobuf.extract(message)
        account['positions'] = [
            {'id': str(p.positionId), 'side': 'BUY' if p.tradeData.tradeSide == 1 else 'SELL',
             'volume_units': money(p.tradeData.volume, 2),
             'entry': str(p.price) if p.HasField('price') else None,
             'sl': str(p.stopLoss) if p.HasField('stopLoss') else None,
             'tp': str(p.takeProfit) if p.HasField('takeProfit') else None}
            for p in response.position if p.tradeData.symbolId == symbol_id]
        account['pending_orders'] = [
            {'id': str(o.orderId), 'side': 'BUY' if o.tradeData.tradeSide == 1 else 'SELL',
             'volume_units': money(o.tradeData.volume, 2),
             'limit_price': str(o.limitPrice) if o.HasField('limitPrice') else None}
            for o in response.order if o.tradeData.symbolId == symbol_id]
        account['all_positions_count'] = len(response.position)
        account['all_pending_orders_count'] = len(response.order)
        if not response.position:
            account['equity'] = account['balance']
            emit('account', dict(account))
        else:
            send(ProtoOAGetPositionUnrealizedPnLReq(ctidTraderAccountId=account_id),
                 'unrealized_pnl', pnl_received)
        reactor.callLater(30, refresh_account)

    def pnl_received(message) -> None:
        if message.payloadType != ProtoOAGetPositionUnrealizedPnLRes().payloadType:
            account['equity'] = None
            emit('account', dict(account))
            return
        response = Protobuf.extract(message)
        precision = int(response.moneyDigits)
        net = sum(int(p.netUnrealizedPnL) for p in response.positionUnrealizedPnL)
        account['equity'] = str(Decimal(account['balance']) + Decimal(money(net, precision)))
        emit('account', dict(account))

    def refresh_bars() -> None:
        if account_id is None or symbol_id is None:
            return
        for label, (period, minutes, days) in PERIODS.items():
            now_ms = int(time.time() * 1000)
            request = ProtoOAGetTrendbarsReq(ctidTraderAccountId=account_id,
                symbolId=symbol_id, period=period, count=120,
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
        decoded = [decode_bar(item, digits, minutes, int(time.time() * 1000))
                   for item in Protobuf.extract(message).trendbar]
        for bar in decoded:
            if bar:
                bars[label][bar['time']] = bar
        bars[label] = dict(sorted(bars[label].items())[-120:])
        emit('bars', {'interval': label, 'bars': list(bars[label].values()),
                      'source': 'ctrader_demo_xauusd', 'closed_only': True})

    def asset_listed(message) -> None:
        if message.payloadType == ProtoOAAssetListRes().payloadType:
            for asset in Protobuf.extract(message).asset:
                asset_names[int(asset.assetId)] = asset.name
        refresh_account()
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
                    emit('symbol', dict(symbol_rules))
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

    def execution_result(event) -> dict | None:
        if int(event.ctidTraderAccountId) != account_id or not event.HasField('order'):
            return None
        order = event.order
        client_order_id = (str(order.clientOrderId) if order.HasField('clientOrderId')
                           else order_ids.get(int(order.orderId), ''))
        if not client_order_id.startswith('gd-'):
            return None
        order_ids[int(order.orderId)] = client_order_id
        event_type = int(event.executionType)
        status = {2: 'ACCEPTED', 3: 'FILLED', 5: 'CANCELLED', 6: 'EXPIRED',
                  7: 'REJECTED', 11: 'PARTIALLY_FILLED'}.get(event_type, 'UNKNOWN')
        return {'client_order_id': client_order_id, 'status': status,
                'order_id': str(order.orderId),
                'position_id': str(event.position.positionId) if event.HasField('position') else None,
                'execution_price': str(order.executionPrice) if order.HasField('executionPrice') else None,
                'error_code': str(event.errorCode)[:80] if event.HasField('errorCode') else None}

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
            request = ProtoOANewOrderReq(**args)
            def order_received(message):
                if message.payloadType == ProtoOAExecutionEvent().payloadType:
                    result = execution_result(Protobuf.extract(message))
                    emit('order_result', result or {'client_order_id': ident, 'status': 'UNKNOWN'})
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

    def read_commands() -> None:
        for line in sys.stdin:
            try:
                command = json.loads(line)
                if isinstance(command, dict) and command.get('kind') == 'place_order':
                    reactor.callFromThread(handle_command, command)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

    def message_received(_client, message) -> None:
        if message.payloadType == ProtoOAExecutionEvent().payloadType:
            result = execution_result(Protobuf.extract(message))
            if result:
                emit('order_event', result)
                reactor.callLater(1, refresh_account)
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
                    bars[label] = dict(sorted(bars[label].items())[-120:])
                    emit('bars', {'interval': label, 'bars': list(bars[label].values()),
                                  'source': 'ctrader_demo_xauusd', 'closed_only': True})

    client.setConnectedCallback(connected)
    client.setMessageReceivedCallback(message_received)
    client.startService()
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
