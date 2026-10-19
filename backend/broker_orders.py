"""Local-only, DEMO-only order review and durable no-resubmit journal."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from contextlib import contextmanager
import json
import sqlite3
from threading import RLock
from uuid import uuid4

from .engine import DomainError, amount, money


D = Decimal
JOURNAL = Path(__file__).resolve().parents[1] / 'private' / 'broker_demo_orders.sqlite3'


def _positive_int(value, label: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise DomainError(f'{label}缺少券商資料', 503) from exc
    if number <= 0:
        raise DomainError(f'{label}缺少券商資料', 503)
    return number


def _checked_snapshot(snapshot: dict) -> tuple[dict, dict, dict]:
    if snapshot.get('environment') != 'demo' or not snapshot.get('order_connection') or snapshot.get('token_scope') != 'TRADE':
        raise DomainError('cTrader DEMO 未具備可用交易連線', 503)
    quote, account, symbol = snapshot.get('quote'), snapshot.get('account'), snapshot.get('symbol')
    if not quote or quote.get('status') != 'CURRENT' or not account or account.get('status') != 'CURRENT' or not symbol:
        raise DomainError('DEMO 報價、帳戶或商品規格尚未就緒', 503)
    if quote.get('age_seconds') is None or quote['age_seconds'] > 5:
        raise DomainError('DEMO 報價超過 5 秒，請等待最新 tick', 503)
    return quote, account, symbol


def _account_signature(account: dict) -> str:
    positions = sorted((p['id'], p['side'], p['volume_units'], p.get('entry'))
                       for p in account.get('positions', []))
    pending = sorted((p['id'], p['side'], p['volume_units'], p.get('limit_price'))
                     for p in account.get('pending_orders', []))
    return json.dumps({'positions': positions, 'pending': pending}, separators=(',', ':'))


def _price(raw: str | None, label: str, digits: int) -> D | None:
    if raw in (None, ''):
        return None
    value = amount(raw, label)
    tick = D(1).scaleb(-digits)
    if value % tick:
        raise DomainError(f'{label}須以 {tick} 為單位')
    return value


def _volume(lot: D, symbol: dict) -> tuple[int, D]:
    lot_cents = _positive_int(symbol.get('lot_size_cents'), '合約大小')
    minimum = _positive_int(symbol.get('min_volume_cents'), '最小手數')
    maximum = _positive_int(symbol.get('max_volume_cents'), '最大手數')
    step = _positive_int(symbol.get('step_volume_cents'), '手數級距')
    volume = lot * lot_cents
    if volume != volume.to_integral_value() or not minimum <= volume <= maximum or (int(volume) - minimum) % step:
        raise DomainError('手數不符合此 DEMO 券商的最小／最大／級距規格')
    return int(volume), D(lot_cents) / 100


class BrokerOrders:
    def __init__(self, stream, journal: Path = JOURNAL) -> None:
        self.stream = stream
        self.journal = journal
        self.lock = RLock()
        self.drafts: dict[str, dict] = {}

    @contextmanager
    def _db(self):
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.journal, timeout=10)
        db.execute('CREATE TABLE IF NOT EXISTS submissions ('
                   'draft_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL, '
                   'client_order_id TEXT NOT NULL UNIQUE, status TEXT NOT NULL, '
                   'result_json TEXT NOT NULL, created_at_utc TEXT NOT NULL)')
        db.commit()
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def create(self, snapshot: dict, *, side: str, lot: str, order_type: str,
               limit_price: str | None, sl: str | None, tp: str | None,
               retrieval: dict) -> dict:
        quote, account, symbol = _checked_snapshot(snapshot)
        if side not in ('BUY', 'SELL') or order_type not in ('MARKET', 'LIMIT'):
            raise DomainError('不支援的 DEMO 委託')
        qty = amount(lot, '手數')
        if qty > 100:
            raise DomainError('單筆最多 100 手')
        volume_cents, contract_units = _volume(qty, symbol)
        digits = int(symbol['digits'])
        if not 0 <= digits <= 8:
            raise DomainError('券商價格精度無效', 503)
        bid, ask = amount(quote['bid'], '賣出價'), amount(quote['ask'], '買進價')
        if ask < bid:
            raise DomainError('券商雙向報價無效', 503)
        reference = ask if side == 'BUY' else bid
        limit = _price(limit_price, '指定限價', digits)
        if order_type == 'LIMIT':
            if limit is None:
                raise DomainError('限價單須提供指定限價')
            if side == 'BUY' and limit >= ask or side == 'SELL' and limit <= bid:
                raise DomainError('限價須位於目前報價的非立即成交方向')
            price = limit
        elif limit is not None:
            raise DomainError('市價單不接受指定限價')
        else:
            price = reference
        stop = _price(sl, '停損', digits)
        target = _price(tp, '停利', digits)
        sign = D(1) if side == 'BUY' else D(-1)
        if stop is not None and (stop - price) * sign >= 0:
            raise DomainError('停損須在擬進場價的不利方向')
        if target is not None and (target - price) * sign <= 0:
            raise DomainError('停利須在擬進場價的有利方向')
        positions = account.get('positions', [])
        existing_units = sum((D(p['volume_units']) for p in positions), D(0))
        same = [p for p in positions if p['side'] == side and p.get('entry') is not None]
        same_units = sum((D(p['volume_units']) for p in same), D(0))
        average = (sum((D(p['entry']) * D(p['volume_units']) for p in same), D(0)) +
                   price * qty * contract_units) / (same_units + qty * contract_units)
        scenarios = [{'move': money(-D(step) * sign),
                      'loss': money(D(step) * qty * contract_units)} for step in (5, 10, 25)]
        warnings = ['cTrader DEMO 委託；風險為 XAUUSD 名目 USD 試算，未計佣金、隔夜費、滑價或券商保證金。',
                    '既有持倉以總曝險顯示；淨額帳戶的反向單可能沖銷，實際以券商回報為準。',
                    '確認時重新核對帳戶、商品規格與最新報價；行情變動後需重建草稿。']
        if order_type == 'MARKET' and (stop is not None or target is not None):
            warnings.append('市價單停損／停利以相對擬進場距離傳送，實際價格隨成交價移動。')
        if stop is None:
            warnings.append('未設定停損；價格情境不是損失上限。')
        if order_type == 'LIMIT':
            warnings.append('限價單被券商接受後仍待觸價；接受不等於成交。')
        now = datetime.now(timezone.utc)
        draft = dict(id=uuid4().hex, revision=1, source='ctrader_demo_xauusd',
                     environment='demo', status='REVIEW', side=side, lot=str(qty),
                     order_type=order_type, limit_price=str(limit) if limit else None,
                     price=str(price), sl=str(stop) if stop else None,
                     tp=str(target) if target else None,
                     action='FIRST' if not positions else 'ADD' if all(p['side'] == side for p in positions) else 'OPPOSITE',
                     created_at_utc=now.isoformat(), expires_at_utc=(now + timedelta(seconds=30)).isoformat(),
                     quote_time_utc=quote['source_time_utc'], account_signature=_account_signature(account),
                     volume_cents=volume_cents, lot_size_cents=int(symbol['lot_size_cents']),
                     symbol_rules=dict(symbol),
                     risk=dict(before_lot=str(existing_units / contract_units),
                               after_lot=str(existing_units / contract_units + qty),
                               average_entry=money(average),
                               stop_loss_usd=money(abs(price - stop) * qty * contract_units) if stop else None,
                               reward_risk=money(abs(target - price) / abs(stop - price)) if stop and target else None,
                               scenarios=scenarios, warnings=warnings),
                     retrieval=retrieval,
                     explanation='此為 cTrader DEMO 草稿。相似案例只比較已收盤面；請核對券商帳戶與風險後親自確認。')
        with self.lock:
            self.drafts[draft['id']] = draft
        return self._public_draft(draft)

    @staticmethod
    def _public_draft(draft: dict) -> dict:
        return {key: value for key, value in draft.items() if key not in (
            'account_signature', 'volume_cents', 'lot_size_cents', 'symbol_rules')}

    def cancel(self, draft_id: str) -> dict:
        with self.lock:
            draft = self.drafts.get(draft_id)
            if not draft or draft['status'] != 'REVIEW':
                raise DomainError('DEMO 草稿不存在或已送出', 409)
            draft['status'] = 'CANCELLED'
            return {'status': 'CANCELLED'}

    def confirm(self, draft_id: str, revision: int, key: str) -> dict:
        if not key or len(key) > 128:
            raise DomainError('缺少有效確認識別碼')
        with self.lock:
            with self._db() as db:
                existing = db.execute('SELECT idempotency_key,result_json FROM submissions WHERE draft_id=?',
                                      (draft_id,)).fetchone()
            if existing:
                if existing[0] != key:
                    raise DomainError('此草稿已使用另一個確認識別碼送出', 409)
                return self.status(draft_id)
            draft = self.drafts.get(draft_id)
            if not draft or draft['status'] != 'REVIEW' or revision != draft['revision']:
                raise DomainError('DEMO 草稿已失效，請重新檢查', 409)
            if datetime.now(timezone.utc) >= datetime.fromisoformat(draft['expires_at_utc']):
                raise DomainError('DEMO 草稿已超過 30 秒，請重新檢查', 409)
            snapshot = self.stream.snapshot()
            quote, account, symbol = _checked_snapshot(snapshot)
            if _account_signature(account) != draft['account_signature'] or symbol != draft['symbol_rules']:
                raise DomainError('券商帳戶或商品規格已變，請重建草稿', 409)
            now_price = amount(quote['ask' if draft['side'] == 'BUY' else 'bid'], '最新報價')
            if abs(now_price - D(draft['price'] if draft['order_type'] == 'MARKET' else
                                 draft['limit_price'])) > D('0.50') and draft['order_type'] == 'MARKET':
                raise DomainError('DEMO 報價變動超過 0.50 美元，請重建草稿', 409)
            if draft['order_type'] == 'LIMIT' and (
                draft['side'] == 'BUY' and D(draft['limit_price']) >= amount(quote['ask'], '買進價') or
                draft['side'] == 'SELL' and D(draft['limit_price']) <= amount(quote['bid'], '賣出價')):
                raise DomainError('指定限價與最新報價關係已變，請重建草稿', 409)
            ident = 'gd-' + uuid4().hex
            command = {'client_order_id': ident, 'side': draft['side'],
                       'order_type': draft['order_type'], 'volume_cents': draft['volume_cents'],
                       'limit_price': draft['limit_price'], 'sl': draft['sl'], 'tp': draft['tp']}
            if draft['order_type'] == 'MARKET':
                reference = D(draft['price'])
                for name, field in (('sl', 'relative_sl'), ('tp', 'relative_tp')):
                    if draft[name] is not None:
                        distance = abs(reference - D(draft[name])) * 100000
                        if distance != distance.to_integral_value() or distance <= 0:
                            raise DomainError('停損／停利相對距離無效')
                        command[field] = int(distance)
            initial = {'client_order_id': ident, 'status': 'UNKNOWN', 'order_id': None,
                       'message': '已保留防重送紀錄；券商回報待確認。'}
            with self._db() as db:
                db.execute('INSERT INTO submissions VALUES (?,?,?,?,?,?)',
                           (draft_id, key, ident, 'UNKNOWN', json.dumps(initial),
                            datetime.now(timezone.utc).isoformat()))
            draft['status'] = 'SUBMITTED'
            try:
                result = self.stream.place_order(command)
            except Exception:
                # After writing the journal we cannot prove whether the broker
                # received the request. Never turn this into a retriable draft.
                result = {'status': 'UNKNOWN', 'message': '無法確認券商是否收到委託；請在 cTrader 帳戶核對，勿重送。'}
            result = dict(initial, **result)
            with self._db() as db:
                db.execute('UPDATE submissions SET status=?, result_json=? WHERE draft_id=?',
                           (result['status'], json.dumps(result), draft_id))
            return result

    def status(self, draft_id: str) -> dict:
        with self.lock:
            with self._db() as db:
                row = db.execute('SELECT client_order_id,result_json FROM submissions WHERE draft_id=?',
                                 (draft_id,)).fetchone()
                if not row:
                    raise DomainError('找不到此 DEMO 委託', 404)
                stored = json.loads(row[1])
                latest = self.stream.order_status(row[0])
                if latest and latest.get('status') not in (None, 'UNKNOWN'):
                    from .demo_market_stream import _advance_order
                    stored = _advance_order(stored, latest)
                    db.execute('UPDATE submissions SET status=?, result_json=? WHERE draft_id=?',
                               (stored['status'], json.dumps(stored), draft_id))
            return stored
