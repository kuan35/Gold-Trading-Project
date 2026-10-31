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
from .position_management import PositionManagement


D = Decimal
JOURNAL = Path(__file__).resolve().parents[1] / 'private' / 'broker_demo_orders.sqlite3'
KNOWN_RESULTS = {'UNKNOWN','ACCEPTED','PARTIALLY_FILLED','FILLED','REJECTED','CANCELLED','EXPIRED','APPLIED'}

def _known_result(value):
    return isinstance(value,str) and value in KNOWN_RESULTS


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
    positions = sorted((p['id'], p['side'], p['volume_units'], p.get('entry'),p.get('sl'),p.get('tp'),p.get('trailing_stop_loss'),p.get('guaranteed_stop_loss'))
                       for p in account.get('positions', []))
    pending = sorted((p['id'], p['side'], p['volume_units'], p.get('limit_price'),p.get('intent'),p.get('position_id'),p.get('sl'),p.get('tp'))
                     for p in account.get('pending_orders', []))
    return json.dumps({'account_key':account.get('account_key'),'positions': positions, 'pending': pending}, separators=(',', ':'))


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


def _close_position(account: dict, position_id: str) -> tuple[dict, int]:
    if not account.get('account_key'):
        raise DomainError('DEMO 帳戶識別尚未就緒，無法核對平倉部位', 503)
    if not isinstance(position_id, str) or not position_id.isascii() or not position_id.isdigit() or not 0 < int(position_id) <= 2**63 - 1:
        raise DomainError('DEMO 部位識別碼無效')
    matches = [p for p in account.get('positions', []) if p.get('id') == position_id]
    if len(matches) != 1:
        raise DomainError('此 DEMO 黃金部位已不存在，請刷新持倉', 409)
    position = matches[0]
    if position.get('side') not in ('BUY', 'SELL'):
        raise DomainError('DEMO 部位方向無效', 503)
    volume = amount(position.get('volume_units'), '部位剩餘數量') * 100
    if volume != volume.to_integral_value() or volume > 2**63 - 1:
        raise DomainError('DEMO 部位剩餘數量無效', 503)
    return position, int(volume)


class BrokerOrders(PositionManagement):
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
        if 'context_json' not in {row[1] for row in db.execute('PRAGMA table_info(submissions)')}:
            db.execute("ALTER TABLE submissions ADD COLUMN context_json TEXT NOT NULL DEFAULT '{}'")
        db.commit()
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def _refresh_result(self, db, draft_id: str, ident: str, stored: dict) -> dict:
        latest = self.stream.order_status(ident)
        if isinstance(latest,dict) and latest.get('history_reconciled'):
            from .order_binding import checked_close_history
            context=json.loads(db.execute('SELECT context_json FROM submissions WHERE draft_id=?',(draft_id,)).fetchone()[0])
            latest=checked_close_history(latest,latest,context)
        if isinstance(latest,dict) and _known_result(latest.get('status')) and latest['status']!='UNKNOWN':
            from .demo_market_stream import _advance_order
            updated = _advance_order(stored, latest)
            if updated.get('status') != stored.get('status'):
                updated['status_observed_at_utc'] = datetime.now(timezone.utc).isoformat()
            if updated != stored:
                db.execute('UPDATE submissions SET status=?, result_json=? WHERE draft_id=?',
                           (updated['status'], json.dumps(updated), draft_id))
            return updated
        return stored

    def _uncertain_submission(self, db, account: dict) -> str | None:
        """Unknown execution cannot be bypassed with another draft or browser.

        Known acknowledgements are not treated as unknown. A legacy journal
        without account provenance cannot prove it belongs to a different account.
        This runs again inside confirm's SQLite write transaction.
        """
        for draft_id,ident,raw_result,raw_context in db.execute(
                'SELECT draft_id,client_order_id,result_json,context_json FROM submissions').fetchall():
            try:
                context=json.loads(raw_context);stored=json.loads(raw_result)
                if not isinstance(context,dict) or not isinstance(stored,dict):raise ValueError('invalid journal')
            except (ValueError,TypeError):
                return '既有送單回報紀錄無法核對；請先至 cTrader 核對，勿重送'
            current,previous=account.get('account_key'),context.get('account_key')
            if current and previous and current!=previous:continue
            if stored.get('status')=='APPLIED':
                try:
                    if datetime.fromisoformat(account.get('updated_at_utc','').replace('Z','+00:00'))<=datetime.fromisoformat(stored.get('status_observed_at_utc','').replace('Z','+00:00')):
                        return '請等待帳戶更新後再修改停損停利'
                except (ValueError,TypeError):return '請等待帳戶更新後再修改停損停利'
            if _known_result(stored.get('status')) and stored['status']!='UNKNOWN':continue
            result=self._refresh_result(db,draft_id,ident,stored)
            if not _known_result(result.get('status')) or result['status']=='UNKNOWN':
                return '此帳戶已有送單回報待核對；請至持倉與紀錄或 cTrader 核對，勿重送'
        return None

    def _close_conflict(self, db, account: dict, position_id: str) -> str | None:
        rows = db.execute('SELECT draft_id,client_order_id,result_json,context_json FROM submissions').fetchall()
        for draft_id, ident, raw_result, raw_context in rows:
            context = json.loads(raw_context)
            if (context.get('intent') != 'CLOSE' or context.get('account_key') != account['account_key'] or
                    context.get('position_id') != position_id):
                continue
            result = self._refresh_result(db, draft_id, ident, json.loads(raw_result))
            if result.get('status') not in ('FILLED', 'REJECTED', 'CANCELLED', 'EXPIRED'):
                return '此部位已有平倉回報待核對；請至 cTrader 核對，勿重送'
            if result['status'] == 'FILLED':
                try:
                    refreshed = datetime.fromisoformat(account.get('updated_at_utc', '').replace('Z', '+00:00'))
                    observed = datetime.fromisoformat(result.get('status_observed_at_utc', '').replace('Z', '+00:00'))
                    current = refreshed > observed
                except (TypeError, ValueError):
                    current = False
                if not current:
                    return '平倉已成交，等待帳戶持倉更新後才能核對剩餘部位'
        return None

    def create(self, snapshot: dict, *, side: str, lot: str, order_type: str,
               limit_price: str | None, sl: str | None, tp: str | None,
               retrieval: dict) -> dict:
        quote, account, symbol = _checked_snapshot(snapshot)
        with self.lock:
            with self._db() as db:
                conflict=self._uncertain_submission(db,account)
            if conflict:raise DomainError(conflict,409)
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
                     environment='demo', status='REVIEW', intent='OPEN', side=side, lot=str(qty),
                     order_type=order_type, limit_price=str(limit) if limit else None,
                     price=str(price), sl=str(stop) if stop else None,
                     tp=str(target) if target else None,
                     action='FIRST' if not positions else 'ADD' if all(p['side'] == side for p in positions) else 'OPPOSITE',
                     created_at_utc=now.isoformat(), expires_at_utc=(now + timedelta(seconds=30)).isoformat(),
                     quote_time_utc=quote['source_time_utc'], account_signature=_account_signature(account),
                     account_key=account.get('account_key'),currency=account.get('currency'),
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

    def create_close(self, snapshot: dict, position_id: str, *,order_type='MARKET',limit_price=None) -> dict:
        quote, account, symbol = _checked_snapshot(snapshot)
        position, volume_cents = _close_position(account, position_id)
        lot_size_cents = _positive_int(symbol.get('lot_size_cents'), '合約大小')
        bid, ask = amount(quote['bid'], '賣出價'), amount(quote['ask'], '買進價')
        if ask < bid:
            raise DomainError('券商雙向報價無效', 503)
        if order_type not in ('MARKET','LIMIT'):raise DomainError('平倉單型無效')
        limit=_price(limit_price,'平倉限價',symbol['digits']) if order_type=='LIMIT' else None
        if order_type=='LIMIT' and (limit is None or (limit<=bid if position['side']=='BUY' else limit>=ask)):
            raise DomainError('限價平倉須設定優於目前平倉報價的目標價')
        now = datetime.now(timezone.utc)
        draft = dict(id=uuid4().hex, revision=1, source='ctrader_demo_xauusd',
                     environment='demo', status='REVIEW', intent='CLOSE', action='CLOSE',
                     position_id=position_id, side=position['side'],
                     lot=str(D(volume_cents) / lot_size_cents), order_type=order_type,
                     price=str(bid if position['side'] == 'BUY' else ask),
                     limit_price=str(limit) if limit is not None else None, sl=None, tp=None,
                     created_at_utc=now.isoformat(), expires_at_utc=(now + timedelta(seconds=30)).isoformat(),
                     quote_time_utc=quote['source_time_utc'], account_signature=_account_signature(account),
                     account_key=account['account_key'], currency=account.get('currency'),
                     volume_cents=volume_cents, lot_size_cents=lot_size_cents, symbol_rules=dict(symbol),
                     explanation='確認後將以市價平倉此 cTrader DEMO 部位的全部剩餘數量；參考報價不等於實際成交價。')
        with self.lock:
            if order_type=='LIMIT':draft['explanation']='確認後掛原部位綁定的反方向限價平倉單，等待指定價或更好價格；可於待成交區取消，實際接受與成交以券商回報為準。'
            with self._db() as db:
                db.execute('BEGIN IMMEDIATE')
                conflict = self._close_conflict(db, account, position_id)
            if conflict:
                raise DomainError(conflict, 409)
            self.drafts[draft['id']] = draft
        return self._public_draft(draft)

    @staticmethod
    def _public_draft(draft: dict) -> dict:
        return {key: value for key, value in draft.items() if key not in (
            'account_signature', 'account_key', 'volume_cents', 'lot_size_cents', 'symbol_rules')}

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
            if draft.get('intent') in ('PROTECT','CANCEL'):
                return self._confirm_management(draft,key,quote,account,symbol)
            closing = draft.get('intent') == 'CLOSE'
            if closing:
                position, volume_cents = _close_position(account, draft['position_id'])
                if volume_cents != draft['volume_cents'] or position['side'] != draft['side']:
                    raise DomainError('DEMO 部位剩餘數量或方向已變，請重建平倉草稿', 409)
            quote_side = ('bid' if draft['side'] == 'BUY' else 'ask') if closing else ('ask' if draft['side'] == 'BUY' else 'bid')
            now_price = amount(quote[quote_side], '最新報價')
            if abs(now_price - D(draft['price'] if draft['order_type'] == 'MARKET' else
                                 draft['limit_price'])) > D('0.50') and draft['order_type'] == 'MARKET':
                raise DomainError('DEMO 報價變動超過 0.50 美元，請重建草稿', 409)
            if closing and draft['order_type']=='LIMIT' and (D(draft['limit_price'])<=amount(quote['bid'],'賣出價') if draft['side']=='BUY' else D(draft['limit_price'])>=amount(quote['ask'],'買進價')):
                raise DomainError('平倉限價與最新報價關係已變，請重建草稿',409)
            if not closing and draft['order_type'] == 'LIMIT' and (
                draft['side'] == 'BUY' and D(draft['limit_price']) >= amount(quote['ask'], '買進價') or
                draft['side'] == 'SELL' and D(draft['limit_price']) <= amount(quote['bid'], '賣出價')):
                raise DomainError('指定限價與最新報價關係已變，請重建草稿', 409)
            ident = 'gd-' + uuid4().hex
            command = {'client_order_id': ident, 'side': draft['side'],
                       'order_type': draft['order_type'], 'volume_cents': draft['volume_cents'],
                       'limit_price': draft['limit_price'], 'sl': draft['sl'], 'tp': draft['tp']}
            if closing:
                command = {'client_order_id': ident, 'intent': 'CLOSE',
                           'position_id': draft['position_id'], 'volume_cents': draft['volume_cents']}
                if draft['order_type']=='LIMIT':command.update(order_type='LIMIT',limit_price=draft['limit_price'],side='SELL' if draft['side']=='BUY' else 'BUY')
            elif draft['order_type'] == 'MARKET':
                reference = D(draft['price'])
                for name, field in (('sl', 'relative_sl'), ('tp', 'relative_tp')):
                    if draft[name] is not None:
                        distance = abs(reference - D(draft[name])) * 100000
                        if distance != distance.to_integral_value() or distance <= 0:
                            raise DomainError('停損／停利相對距離無效')
                        command[field] = int(distance)
            initial = {'client_order_id': ident, 'status': 'UNKNOWN', 'order_id': None,
                       'intent': draft.get('intent', 'OPEN'), 'position_id': draft.get('position_id'),
                       'status_observed_at_utc': datetime.now(timezone.utc).isoformat(),
                       'message': '已保留防重送紀錄；券商回報待確認。'}
            with self._db() as db:
                db.execute('BEGIN IMMEDIATE')
                conflict = self._close_conflict(db,account,draft['position_id']) if closing else None
                if not conflict:conflict=self._uncertain_submission(db,account)
                context={key:draft.get(key) for key in ('intent','position_id','side','lot','volume_cents','order_type','price','limit_price','sl','tp','account_key','currency')}
                if not conflict:
                    db.execute('INSERT INTO submissions (draft_id,idempotency_key,client_order_id,status,result_json,created_at_utc,context_json) VALUES (?,?,?,?,?,?,?)',
                               (draft_id, key, ident, 'UNKNOWN', json.dumps(initial),
                                datetime.now(timezone.utc).isoformat(),json.dumps(context)))
            if conflict:
                raise DomainError(conflict, 409)
            draft['status'] = 'SUBMITTED'
            try:
                result = self.stream.place_order(command)
            except Exception:
                # After writing the journal we cannot prove whether the broker
                # received the request. Never turn this into a retriable draft.
                result = {'status': 'UNKNOWN', 'message': '無法確認券商是否收到委託；請在 cTrader 帳戶核對，勿重送。'}
            result = dict(initial, **(result if isinstance(result,dict) else {}))
            if not _known_result(result.get('status')):
                result.update(status='UNKNOWN',message='券商回報格式無法辨識；請至 cTrader 核對，勿重送。')
            result['status_observed_at_utc'] = datetime.now(timezone.utc).isoformat()
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
                stored = self._refresh_result(db, draft_id, row[0], stored)
            return stored

    def activity(self,snapshot:dict,limit:int=100,offset:int=0) -> dict:
        if type(limit) is not int or not 1<=limit<=200:raise DomainError('紀錄筆數範圍1至200')
        if type(offset) is not int or not 0<=offset<=1000000:raise DomainError('紀錄分頁位置無效')
        account_key=(snapshot.get('account') or {}).get('account_key')
        with self.lock:
            with self._db() as db:
                stored=db.execute('SELECT draft_id,client_order_id,created_at_utc,context_json FROM submissions ORDER BY created_at_utc DESC,draft_id DESC').fetchall()
            eligible=[]
            for draft_id,ident,created,raw_context in stored:
                ctx=json.loads(raw_context)
                if account_key and ctx.get('account_key') and account_key!=ctx['account_key']:continue
                eligible.append((draft_id,ident,created,ctx))
            rows=[]
            for draft_id,ident,created,ctx in eligible[offset:offset+limit]:
                result=self.status(draft_id)
                rows.append(dict(draft_id=draft_id,client_order_id=ident,created_at_utc=created,
                    **{key:ctx.get(key) for key in ('intent','side','lot','order_type','price','limit_price','sl','tp','currency')},
                    **{key:result.get(key) for key in ('status','order_id','execution_price','error_code','updated_at_utc')},
                    position_id=result.get('position_id') or ctx.get('position_id'),
                    account_scope='CURRENT' if account_key and ctx.get('account_key')==account_key else 'UNKNOWN'))
        history=snapshot.get('history') or {}
        return dict(source='ctrader_demo_xauusd',environment='demo',
            connection_status=snapshot.get('connection_status','UNAVAILABLE'),
            account_scope='CURRENT' if account_key else 'LOCAL_SAVED',
            submissions=dict(items=rows,total=len(eligible),offset=offset,limit=limit,has_more=len(eligible)>offset+limit),
            broker_orders=dict(status='LOADING',items=[],has_more=False) | (history.get('broker_orders') or {}),
            broker_deals=dict(status='LOADING',items=[],has_more=False) | (history.get('broker_deals') or {}),
            updated_at_utc=datetime.now(timezone.utc).isoformat())
