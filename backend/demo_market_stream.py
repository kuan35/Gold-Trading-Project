"""Local cTrader DEMO market cache and explicitly confirmed order bridge.

One child owns the SDK connection; public snapshots contain sanitized data.
"""

from __future__ import annotations

import atexit
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import subprocess
import sys
from threading import Event, Lock, Thread
from time import monotonic

from .demo_quote_bridge import CONFIG, PRODUCT, sanitize_quote_result


_ORDER_PROGRESS = {'UNKNOWN': 0, 'ACCEPTED': 1, 'PARTIALLY_FILLED': 2,
                   'REJECTED': 3, 'CANCELLED': 3, 'EXPIRED': 3, 'FILLED': 4}


def _advance_order(previous: dict | None, incoming: dict) -> dict:
    """Keep late timeout/duplicate events from hiding a broker result."""
    if previous and _ORDER_PROGRESS.get(str(incoming.get('status')), 0) < _ORDER_PROGRESS.get(str(previous.get('status')), 0):
        return previous
    return {**(previous or {}), **{key: value for key, value in incoming.items() if value is not None}}


class DemoMarketStream:
    def __init__(self) -> None:
        self._lock = Lock()
        self._process: subprocess.Popen | None = None
        self._retry_after = 0.0
        self._status = 'NOT_CONFIGURED'
        self._scope = 'UNKNOWN'
        self._quote: dict | None = None
        self._account: dict | None = None
        self._bars: dict[str, list[dict]] = {}
        self._forming: dict[str, dict] = {}
        self._history: dict[str, dict] = {}
        self._symbol: dict | None = None
        self._orders_enabled = False
        self._order_results: dict[str, dict] = {}
        self._waiting: dict[str, Event] = {}

    def _start(self) -> None:
        if not CONFIG.is_file():
            self._status = 'NOT_CONFIGURED'
            return
        if self._process is not None and self._process.poll() is None:
            return
        now = monotonic()
        if now < self._retry_after:
            return
        self._retry_after = now + 8
        self._quote = None
        self._account = None
        self._bars = {}
        self._history = {}
        self._forming = {}
        self._symbol = None
        self._orders_enabled = False
        self._status = 'CONNECTING'
        try:
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            process = subprocess.Popen(
                [sys.executable, '-u', '-m', 'scripts.stream_ctrader_demo'],
                cwd=PRODUCT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding='utf-8', bufsize=1, creationflags=flags)
        except OSError:
            self._status = 'UNAVAILABLE'
            return
        self._process = process
        Thread(target=self._consume, args=(process,), daemon=True,
               name='ctrader-demo-reader').start()

    def _consume(self, process: subprocess.Popen) -> None:
        assert process.stdout is not None
        try:
            for line in process.stdout:
                try:
                    item = json.loads(line)
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(item, dict) or not isinstance(item.get('data'), dict):
                    continue
                with self._lock:
                    if self._process is not process:
                        break
                    kind, data = item.get('kind'), item['data']
                    if kind == 'status':
                        self._status = str(data.get('status', 'UNAVAILABLE'))
                        self._scope = str(data.get('scope', 'UNKNOWN'))
                        self._orders_enabled = bool(data.get('orders_enabled'))
                    elif kind == 'symbol':
                        self._symbol = data
                    elif kind == 'quote':
                        self._quote = sanitize_quote_result(
                            {'quote_status': data.get('freshness'), 'quote': data})
                    elif kind == 'account':
                        self._account = data
                    elif kind == 'forming' and data.get('interval') in ('5m','15m','1h'):
                        self._forming[data['interval']]=data['forming']
                    elif kind in ('broker_orders','broker_deals'):
                        self._history[kind] = {'items':[],'has_more':False,**self._history.get(kind,{}),**data}
                    elif kind == 'bars' and data.get('interval') in ('5m', '15m', '1h'):
                        self._bars[data['interval']] = data.get('bars', [])
                    elif kind in ('order_result', 'order_event'):
                        ident = str(data.get('client_order_id', ''))
                        if ident.startswith('gd-') and ident in self._waiting:
                            self._order_results[ident] = _advance_order(self._order_results.get(ident), data)
                            self._waiting[ident].set()
                        elif ident.startswith('gd-') and ident in self._order_results:
                            self._order_results[ident] = _advance_order(self._order_results[ident], data)
        finally:
            with self._lock:
                if self._process is process:
                    self._status = 'DISCONNECTED'
                    self._process = None
                    for waiting in self._waiting.values():
                        waiting.set()
            process.stdout.close()

    def _snapshot_locked(self) -> dict:
        quote = deepcopy(self._quote) if self._quote else sanitize_quote_result(
            {'quote_status': self._status})
        if quote['source_time_utc']:
            try:
                source_time = datetime.fromisoformat(quote['source_time_utc'])
                age = max(0.0, (datetime.now(timezone.utc) - source_time).total_seconds())
                quote['age_seconds'] = round(age, 3)
                quote['status'] = ('CURRENT' if age <= 120 and self._status == 'CONNECTED'
                                   else 'STALE')
            except ValueError:
                quote['status'] = 'UNAVAILABLE'
                quote['bid'] = quote['ask'] = None
        account = deepcopy(self._account)
        if account:
            try:
                updated = datetime.fromisoformat(account['updated_at_utc'])
                age = (datetime.now(timezone.utc) - updated).total_seconds()
                if self._status != 'CONNECTED' or age > 90 or age < -5:
                    account['status'] = 'STALE'
            except (KeyError, TypeError, ValueError):
                account['status'] = 'STALE'
            try:
                pnl_age=(datetime.now(timezone.utc)-datetime.fromisoformat(account['pnl_updated_at_utc'])).total_seconds()
                if self._status!='CONNECTED' or pnl_age>10 or pnl_age < -5:
                    account['pnl_status']='STALE'
            except (KeyError,TypeError,ValueError):
                account['pnl_status']='UNAVAILABLE'
        return {'source': 'ctrader_demo_xauusd', 'environment': 'demo',
                'connection_status': self._status, 'token_scope': self._scope,
                'order_connection': bool(self._orders_enabled and self._symbol and
                                         self._status == 'CONNECTED' and
                                         quote['status'] == 'CURRENT' and account and
                                         account.get('status') == 'CURRENT'),
                'quote': quote, 'account': account,
                'symbol': deepcopy(self._symbol)}

    def snapshot(self) -> dict:
        with self._lock:
            self._start()
            return self._snapshot_locked()

    def query_snapshot(self) -> dict:
        with self._lock:
            self._start()
            value = self._snapshot_locked()
            value['bars'] = deepcopy(self._bars)
            return value

    def place_order(self, command: dict, timeout: float = 15) -> dict:
        ident = str(command['client_order_id'])
        waiting = Event()
        with self._lock:
            self._start()
            if not self._snapshot_locked()['order_connection']:
                return {'client_order_id': ident, 'status': 'REJECTED',
                        'error_code': 'DEMO_TRADE_UNAVAILABLE'}
            if ident in self._waiting or ident in self._order_results:
                return self._order_results.get(ident, {'client_order_id': ident, 'status': 'UNKNOWN'})
            self._waiting[ident] = waiting
            try:
                assert self._process is not None and self._process.stdin is not None
                self._process.stdin.write(json.dumps(dict(command, kind='place_order')) + '\n')
                self._process.stdin.flush()
            except (OSError, ValueError, AssertionError):
                self._order_results[ident] = {'client_order_id': ident, 'status': 'UNKNOWN'}
                self._waiting.pop(ident, None)
                return self._order_results[ident]
        waiting.wait(timeout)
        with self._lock:
            self._waiting.pop(ident, None)
            result = self._order_results.get(ident)
            if result is None:
                result = {'client_order_id': ident, 'status': 'UNKNOWN'}
                self._order_results[ident] = result
            return deepcopy(result)

    def order_status(self, ident: str) -> dict | None:
        with self._lock:
            latest=self._order_results.get(ident)
            data=self._history.get('broker_orders',{})
            if data.get('status')=='CURRENT':
                row=next((r for r in data.get('items',[]) if r.get('client_order_id')==ident),None)
                if row:
                    history={key:row.get(key) for key in ('client_order_id','order_id','position_id','status','execution_price','updated_at_utc')}
                    latest=_advance_order(latest,history)
            return deepcopy(latest)

    def activity_snapshot(self) -> dict:
        with self._lock:
            self._start()
            value=self._snapshot_locked()
            history=deepcopy(self._history)
            for data in history.values():
                try:
                    age=(datetime.now(timezone.utc)-datetime.fromisoformat(data['updated_at_utc'])).total_seconds()
                    if self._status!='CONNECTED' or age>45 or age < -5:data['status']='STALE'
                except (KeyError,TypeError,ValueError):data['status']='UNAVAILABLE'
            value['history']=history
            return value

    def bars(self, interval: str) -> dict:
        if interval not in ('5m', '15m', '1h'):
            raise ValueError('unsupported interval')
        with self._lock:
            self._start()
            bars = deepcopy(self._bars.get(interval, []))
            return {'source': 'ctrader_demo_xauusd', 'environment': 'demo',
                    'status': ('CURRENT' if bars and self._status == 'CONNECTED'
                               else 'STALE' if bars else self._status), 'interval': interval,
                    'closed_only': True, 'bars': bars}

    def chart_snapshot(self,interval:str,now_ms:int|None=None) -> dict:
        """Forming bars are exposed only through the drawing stream."""
        value=self.bars(interval)
        with self._lock:
            forming=deepcopy(self._forming.get(interval))
            now_ms=now_ms if now_ms is not None else int(datetime.now(timezone.utc).timestamp()*1000)
            age=now_ms-forming.get('updated_at_ms',0) if forming else None
            span={'5m':300,'15m':900,'1h':3600}[interval]
            if self._status!='CONNECTED' or age is None or not -1000<=age<=5000 or forming['bar']['time']!=now_ms//(span*1000)*span:
                forming=None
            return dict(value,closed_only=False,forming=forming,
                forming_status='CURRENT' if forming else 'WAITING',price_basis='BID',volume_basis='observed_bid_updates')

    def stop(self) -> None:
        with self._lock:
            process, self._process = self._process, None
        if process and process.poll() is None:
            process.terminate()


stream = DemoMarketStream()
atexit.register(stream.stop)
