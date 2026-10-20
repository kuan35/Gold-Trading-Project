"""Read-only cTrader DEMO authentication check; never sends trading requests.

The only output is a small status object. Credentials, tokens, IDs and raw
server responses are intentionally excluded from logs and error messages.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
import time


ENV_FILE = Path(__file__).resolve().parents[1] / ".env.ctrader"
KEYS = {"CTRADER_CLIENT_ID", "CTRADER_CLIENT_SECRET", "CTRADER_ACCESS_TOKEN",
        "CTRADER_ACCOUNT_ID", "CTRADER_ENVIRONMENT"}


def load_local_config(path: Path = ENV_FILE) -> dict[str, str]:
    if not path.is_file():
        raise ValueError("CONFIG_FILE_MISSING")
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError("CONFIG_FORMAT_INVALID")
        key, value = (part.strip() for part in line.split("=", 1))
        if key not in KEYS or key in values:
            raise ValueError("CONFIG_KEY_INVALID_OR_DUPLICATE")
        values[key] = value.strip('"').strip("'")
    if values.get("CTRADER_ENVIRONMENT", "demo").lower() != "demo":
        raise ValueError("DEMO_ONLY")
    if not values.get("CTRADER_CLIENT_ID") or not values.get("CTRADER_CLIENT_SECRET"):
        raise ValueError("APP_CREDENTIALS_MISSING")
    account_id = values.get("CTRADER_ACCOUNT_ID", "")
    if account_id and (not account_id.isdecimal() or int(account_id) <= 0):
        raise ValueError("ACCOUNT_ID_INVALID")
    return values


def decode_spot_quote(bid: int, ask: int, source_timestamp_ms: int,
                      received_timestamp_ms: int) -> dict[str, object] | None:
    """Decode cTrader's 1/100000 prices without inventing a missing quote time."""
    if (type(bid) is not int or type(ask) is not int or bid <= 0 or ask < bid or
            type(received_timestamp_ms) is not int):
        return None
    result: dict[str, object] = {
        'bid': format(Decimal(bid) / 100000, 'f'),
        'ask': format(Decimal(ask) / 100000, 'f'),
        'source_time_utc': None, 'age_seconds': None,
        'freshness': 'TIMESTAMP_UNAVAILABLE',
    }
    if type(source_timestamp_ms) is int and source_timestamp_ms > 0:
        age = max(0, (received_timestamp_ms - source_timestamp_ms) / 1000)
        result.update(source_time_utc=datetime.fromtimestamp(
            source_timestamp_ms / 1000, timezone.utc).isoformat(),
            age_seconds=round(age, 3),
            freshness='CURRENT' if age <= 120 else 'STALE')
    return result


def check_demo(config: dict[str, str], timeout_seconds: int = 40,
               *, spot: bool = False) -> dict[str, object]:
    # Delay import so configuration validation and tests do not initialize
    # Twisted's reactor or open a socket.
    from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
    from ctrader_open_api.messages.OpenApiMessages_pb2 import (
        ProtoOAAccountAuthReq, ProtoOAAccountAuthRes,
        ProtoOAApplicationAuthReq, ProtoOAApplicationAuthRes,
        ProtoOAErrorRes, ProtoOAGetAccountListByAccessTokenReq,
        ProtoOAGetAccountListByAccessTokenRes, ProtoOASymbolsListReq,
        ProtoOASymbolsListRes, ProtoOASubscribeSpotsReq,
        ProtoOASubscribeSpotsRes, ProtoOASpotEvent,
    )
    from twisted.internet import reactor

    status: dict[str, object] = {
        "environment": "demo", "transport": "UNTESTED",
        "application_auth": "UNTESTED", "account_auth": "NOT_REQUESTED",
        "demo_account_count": None, "token_scope": None,
        "symbol_list": "NOT_REQUESTED", "gold_symbols": [], "orders_sent": 0,
        "quote_status": "NOT_REQUESTED", "quote": None, "error_code": None,
        "failure_type": None,
    }
    token = config.get("CTRADER_ACCESS_TOKEN", "")
    client = Client(EndPoints.PROTOBUF_DEMO_HOST, EndPoints.PROTOBUF_PORT, TcpProtocol)
    selected_account_id = None
    selected_symbol_id = None
    spot_parts: dict[str, int] = {}

    def finish():
        if reactor.running:
            reactor.stop()

    def fail(stage: str):
        status[stage] = "FAILED"
        finish()

    def request_failed(stage, failure):
        name = type(getattr(failure, "value", failure)).__name__
        status["failure_type"] = name if re.fullmatch(r"[A-Za-z0-9_]{1,64}", name) else "UNRECOGNIZED"
        fail(stage)

    def send(request, stage, callback):
        deferred = client.send(request, responseTimeoutInSeconds=20)
        deferred.addCallbacks(callback, lambda failure: request_failed(stage, failure))

    def record_error_code(message):
        if message.payloadType == ProtoOAErrorRes().payloadType:
            code = Protobuf.extract(message).errorCode
            status["error_code"] = code if re.fullmatch(r"[A-Z0-9_]{1,64}", code) else "UNRECOGNIZED"

    def symbols_listed(message):
        nonlocal selected_symbol_id
        if message.payloadType != ProtoOASymbolsListRes().payloadType:
            record_error_code(message)
            fail("symbol_list")
            return
        response = Protobuf.extract(message)
        status["gold_symbols"] = sorted({item.symbolName for item in response.symbol
                                         if item.enabled and ("XAU" in item.symbolName.upper()
                                                              or "GOLD" in item.symbolName.upper())})
        status["symbol_list"] = "OK"
        if not spot:
            finish()
            return
        match = next((item for item in response.symbol if item.enabled and
                      item.symbolName.upper() == 'XAUUSD'), None)
        if match is None:
            status['quote_status'] = 'XAUUSD_NOT_AVAILABLE'
            finish()
            return
        selected_symbol_id = match.symbolId
        status['quote_status'] = 'PENDING'
        send(ProtoOASubscribeSpotsReq(ctidTraderAccountId=selected_account_id,
                                      symbolId=[selected_symbol_id],
                                      subscribeToSpotTimestamp=True),
             'quote_status', spots_subscribed)

    def spots_subscribed(message):
        if message.payloadType != ProtoOASubscribeSpotsRes().payloadType:
            fail('quote_status')

    def account_authorized(message):
        nonlocal selected_account_id
        if message.payloadType != ProtoOAAccountAuthRes().payloadType:
            fail("account_auth")
            return
        status["account_auth"] = "OK"
        response = Protobuf.extract(message)
        selected_account_id = response.ctidTraderAccountId
        status["symbol_list"] = "PENDING"
        send(ProtoOASymbolsListReq(ctidTraderAccountId=response.ctidTraderAccountId,
                                   includeArchivedSymbols=False), "symbol_list", symbols_listed)

    def accounts_listed(message):
        if message.payloadType != ProtoOAGetAccountListByAccessTokenRes().payloadType:
            fail("account_auth")
            return
        response = Protobuf.extract(message)
        status["token_scope"] = ("VIEW" if response.permissionScope == 0 else
                                 "TRADE" if response.permissionScope == 1 else "UNKNOWN")
        accounts = sorted((item for item in response.ctidTraderAccount if not item.isLive),
                          key=lambda item: item.ctidTraderAccountId)
        status["demo_account_count"] = len(accounts)
        if not accounts:
            status["account_auth"] = "NO_DEMO_ACCOUNT_IN_TOKEN"
            finish()
            return
        requested = config.get("CTRADER_ACCOUNT_ID", "")
        selected = (next((item for item in accounts
                          if str(item.ctidTraderAccountId) == requested), None)
                    if requested else accounts[0])
        if selected is None:
            status["account_auth"] = "REQUESTED_DEMO_ACCOUNT_NOT_IN_TOKEN"
            finish()
            return
        send(ProtoOAAccountAuthReq(ctidTraderAccountId=selected.ctidTraderAccountId,
                                   accessToken=token), "account_auth", account_authorized)

    def app_authorized(message):
        if message.payloadType != ProtoOAApplicationAuthRes().payloadType:
            fail("application_auth")
            return
        status["application_auth"] = "OK"
        if token:
            status["account_auth"] = "PENDING"
            send(ProtoOAGetAccountListByAccessTokenReq(accessToken=token),
                 "account_auth", accounts_listed)
        else:
            finish()

    def connected(_client):
        status["transport"] = "TLS_CONNECTED"
        send(ProtoOAApplicationAuthReq(clientId=config["CTRADER_CLIENT_ID"],
                                       clientSecret=config["CTRADER_CLIENT_SECRET"]),
             "application_auth", app_authorized)

    def message_received(_client, message):
        if message.payloadType == ProtoOASpotEvent().payloadType and spot:
            event = Protobuf.extract(message)
            if event.symbolId != selected_symbol_id or event.ctidTraderAccountId != selected_account_id:
                return
            if event.HasField('bid'):
                spot_parts['bid'] = event.bid
            if event.HasField('ask'):
                spot_parts['ask'] = event.ask
            if event.HasField('timestamp'):
                spot_parts['timestamp'] = event.timestamp
            if 'bid' in spot_parts and 'ask' in spot_parts:
                quote = decode_spot_quote(spot_parts['bid'], spot_parts['ask'],
                                          spot_parts.get('timestamp', 0),
                                          int(time.time() * 1000))
                if quote is not None:
                    status['quote'] = quote
                    status['quote_status'] = quote['freshness']
                    finish()
            return
        if message.payloadType == ProtoOAErrorRes().payloadType:
            # Never log raw descriptions; the response might contain account details.
            record_error_code(message)
            stage = ("application_auth" if status["application_auth"] != "OK" else
                     "account_auth" if status["account_auth"] != "OK" else
                     "symbol_list" if status["symbol_list"] != "OK" else "quote_status")
            fail(stage)

    client.setConnectedCallback(connected)
    client.setMessageReceivedCallback(message_received)
    def timed_out():
        if status["transport"] == "UNTESTED":
            status["transport"] = "TIMEOUT"
        elif status["application_auth"] == "UNTESTED":
            status["application_auth"] = "TIMEOUT"
        elif status["account_auth"] == "PENDING":
            status["account_auth"] = "TIMEOUT"
        elif status["symbol_list"] == "PENDING":
            status["symbol_list"] = "TIMEOUT"
        elif status['quote_status'] == 'PENDING':
            status['quote_status'] = 'TIMEOUT'
        finish()

    reactor.callLater(timeout_seconds, timed_out)
    client.startService()
    reactor.run(installSignalHandlers=False)
    return status


def main() -> int:
    try:
        config = load_local_config()
    except ValueError as error:
        print(json.dumps({"status": str(error), "orders_sent": 0}))
        return 2
    try:
        result = check_demo(config)
    except Exception:
        print(json.dumps({"status": "SDK_OR_CONNECTION_ERROR", "orders_sent": 0}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0 if result["application_auth"] == "OK" and result["symbol_list"] not in (
        "FAILED", "TIMEOUT") and result["account_auth"] not in (
        "FAILED", "TIMEOUT", "NO_DEMO_ACCOUNT_IN_TOKEN",
        "REQUESTED_DEMO_ACCOUNT_NOT_IN_TOKEN") else 1


if __name__ == "__main__":
    sys.exit(main())
