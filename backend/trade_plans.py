"""Account-isolated, private trade plans with immutable pre-trade evidence.

This journal has no broker or model authority. Callers choose a path under their
private runtime directory; constructing the store does not create a database.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
from threading import RLock
from uuid import uuid4

from .engine import DomainError


_DRAFT_FIELDS = (
    'id', 'revision', 'source', 'environment', 'status', 'intent', 'action',
    'position_id', 'order_id', 'side', 'lot', 'order_type', 'price', 'limit_price',
    'sl', 'tp', 'currency', 'created_at_utc', 'expires_at_utc', 'quote_time_utc',
    'risk', 'retrieval', 'explanation', 'snapshot_id', 'analysis_ref',
)
_RECEIPT_FIELDS = (
    'status', 'order_id', 'position_id', 'client_order_id', 'intent',
    'execution_price', 'executed_volume_units', 'volume_units', 'error_code',
    'message', 'status_observed_at_utc', 'updated_at_utc', 'binding_verified',
)
_PROGRESS = {'UNKNOWN': 0, 'ACCEPTED': 1, 'PARTIALLY_FILLED': 2,
             'REJECTED': 3, 'CANCELLED': 3, 'EXPIRED': 3, 'FILLED': 4, 'APPLIED': 4}
_SUMMARY_FIELDS = ('id', 'draft_id', 'created_at_utc', 'updated_at_utc',
                   'conversation_id', 'note', 'revision', 'review_note',
                   'adherence', 'lesson', 'reviewed_at_utc', 'receipt')


def _now():
    return datetime.now(timezone.utc).isoformat()


def _identifier(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        raise DomainError(f'{label}無效', 422)
    return value


def _text(value, label, limit=20000):
    if not isinstance(value, str) or len(value) > limit:
        raise DomainError(f'{label}無效或過長', 422)
    return value


def _safe(value):
    """Copy JSON values and discard credentials even inside immutable evidence."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise DomainError('交易計畫欄位名稱無效', 422)
            lower = key.lower()
            if (lower in ('account_key', 'account_signature', 'account_id', 'account_number',
                          'idempotency_key', 'authorization', 'api_key', 'secret')
                    or any(word in lower for word in ('token', 'password', 'credential'))):
                continue
            result[key] = _safe(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise DomainError('交易計畫數值無效', 422)
        return str(value)
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise DomainError('交易計畫資料必須可保存為JSON', 422)


def _encode(value):
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    except (TypeError, ValueError):
        raise DomainError('交易計畫資料必須是有效JSON', 422) from None


def _summary(plan):
    result = {key: plan.get(key) for key in _SUMMARY_FIELDS}
    result.update({key: plan['draft'].get(key) for key in (
        'side', 'lot', 'order_type', 'price', 'limit_price', 'sl', 'tp',
        'intent', 'action', 'source', 'environment', 'currency')})
    return result


def enrich(plan, activity):
    """Attach read-only closing-deal evidence from an account-scoped snapshot.

    The caller must scope ``activity`` to the same account as ``plan``. A broker
    position can combine several entries, and its absence does not prove an exit.
    Consequently this function never allocates net PnL or infers full closure.
    """
    result = _safe(plan)
    activity = activity if isinstance(activity, dict) else {}
    history = activity.get('history') or activity
    history = history if isinstance(history, dict) else {}
    deals = history.get('broker_deals') or {}
    deals = deals if isinstance(deals, dict) else {}
    position_id = (result.get('receipt') or {}).get('position_id')
    if not position_id:
        position_id = (result.get('draft') or {}).get('position_id')
    fields = ('id', 'order_id', 'position_id', 'role', 'status', 'side', 'lot',
              'execution_price', 'executed_at_utc', 'realized_gross_pnl',
              'commission', 'swap', 'currency')
    linked = []
    if position_id and deals.get('status') == 'CURRENT':
        for row in deals.get('items') or []:
            if (isinstance(row, dict) and row.get('position_id') == position_id
                    and row.get('role') == 'CLOSE'
                    and row.get('status') in ('FILLED', 'PARTIALLY_FILLED')):
                linked.append({key: _safe(row[key]) for key in fields if key in row})
    linked.sort(key=lambda row: (str(row.get('executed_at_utc') or ''), str(row.get('id') or '')))
    result['broker_outcome'] = dict(
        status='CLOSE_DEALS_OBSERVED' if linked else 'UNKNOWN',
        history_status=deals.get('status', 'UNAVAILABLE'),
        position_id=position_id, closing_deals=linked,
        history_has_more=bool(deals.get('has_more')), fully_closed=None,
        net_pnl=None, roi_pct=None,
        reason='僅關聯此部位的已確認平倉成交；可能含部分成交或共用淨額部位，不能推定本筆已全部平倉或單筆淨報酬。',
    )
    return result


class TradePlanStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = RLock()

    @contextmanager
    def _db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=15)
        try:
            db.execute('''CREATE TABLE IF NOT EXISTS trade_plans (
                id TEXT PRIMARY KEY, account_key TEXT NOT NULL,
                draft_id TEXT NOT NULL, created_at_utc TEXT NOT NULL,
                payload_json TEXT NOT NULL, UNIQUE(account_key, draft_id))''')
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _get(db, account_key, plan_id):
        row = db.execute('SELECT payload_json FROM trade_plans WHERE account_key=? AND id=?',
                         (account_key, plan_id)).fetchone()
        if row is None:
            raise DomainError('找不到此交易計畫', 404)
        return json.loads(row[0])

    def capture(self, account_key, draft, analysis, *, note='', conversation_id=None,
                risk=None, snapshot_bundle=None):
        _identifier(account_key, '帳戶識別')
        if not isinstance(draft, dict) or not isinstance(analysis, dict):
            raise DomainError('交易草稿與原始分析必須是物件', 422)
        draft_id = _identifier(draft.get('id'), '草稿識別')
        _text(note, '原始理由')
        if conversation_id is not None:
            _identifier(conversation_id, '對話識別')
        with self.lock, self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT payload_json FROM trade_plans WHERE account_key=? AND draft_id=?',
                             (account_key, draft_id)).fetchone()
            if row is not None:
                return json.loads(row[0])
            now = _now()
            plan = _safe(dict(
                id=uuid4().hex, draft_id=draft_id, created_at_utc=now, updated_at_utc=now,
                conversation_id=conversation_id, revision=1, note=note,
                review_note='', adherence='UNKNOWN', lesson='', reviewed_at_utc=None,
                draft={key: draft[key] for key in _DRAFT_FIELDS if key in draft},
                analysis=analysis, risk=draft.get('risk') if risk is None else risk,
                snapshot_bundle=snapshot_bundle, receipt=None,
            ))
            encoded = _encode(plan)
            db.execute('INSERT INTO trade_plans VALUES (?,?,?,?,?)',
                       (plan['id'], account_key, draft_id, now, encoded))
            return json.loads(encoded)

    def list(self, account_key, *, limit=50, offset=0):
        _identifier(account_key, '帳戶識別')
        if type(limit) is not int or not 1 <= limit <= 200:
            raise DomainError('交易計畫筆數範圍1至200', 422)
        if type(offset) is not int or not 0 <= offset <= 1000000:
            raise DomainError('交易計畫分頁位置無效', 422)
        with self.lock, self._db() as db:
            total = db.execute('SELECT COUNT(*) FROM trade_plans WHERE account_key=?',
                               (account_key,)).fetchone()[0]
            rows = db.execute('''SELECT payload_json FROM trade_plans WHERE account_key=?
                ORDER BY created_at_utc DESC, id DESC LIMIT ? OFFSET ?''',
                              (account_key, limit, offset)).fetchall()
            return dict(items=[_summary(json.loads(row[0])) for row in rows],
                        total=total, limit=limit, offset=offset)

    def get(self, account_key, plan_id):
        _identifier(account_key, '帳戶識別')
        _identifier(plan_id, '計畫識別')
        with self.lock, self._db() as db:
            return self._get(db, account_key, plan_id)

    def update_review(self, account_key, plan_id, revision, *, note='',
                      adherence='UNKNOWN', lesson=''):
        _identifier(account_key, '帳戶識別')
        _identifier(plan_id, '計畫識別')
        if type(revision) is not int or revision < 1:
            raise DomainError('復盤版本無效', 422)
        if adherence not in ('UNKNOWN', 'YES', 'NO', 'PARTIAL'):
            raise DomainError('遵守計畫判斷無效', 422)
        _text(note, '復盤筆記')
        _text(lesson, '復盤心得')
        with self.lock, self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            plan = self._get(db, account_key, plan_id)
            if plan['revision'] != revision:
                raise DomainError('交易計畫復盤版本已變，請重新載入', 409)
            now = _now()
            plan.update(review_note=note, adherence=adherence, lesson=lesson,
                        reviewed_at_utc=now, updated_at_utc=now, revision=revision + 1)
            db.execute('UPDATE trade_plans SET payload_json=? WHERE account_key=? AND id=?',
                       (_encode(plan), account_key, plan_id))
            return plan

    def attach_receipt(self, account_key, draft_id, receipt):
        _identifier(account_key, '帳戶識別')
        _identifier(draft_id, '草稿識別')
        if not isinstance(receipt, dict):
            raise DomainError('券商回報必須是物件', 422)
        incoming = _safe({key: receipt[key] for key in _RECEIPT_FIELDS if key in receipt})
        if incoming.get('status') not in _PROGRESS:
            incoming['status'] = 'UNKNOWN'
        with self.lock, self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT payload_json FROM trade_plans WHERE account_key=? AND draft_id=?',
                             (account_key, draft_id)).fetchone()
            if row is None:
                return None
            plan = json.loads(row[0])
            previous = plan['receipt'] or {}
            if _PROGRESS[incoming['status']] < _PROGRESS.get(previous.get('status'), 0):
                return plan
            plan['receipt'] = dict(previous, **{key: value for key, value in incoming.items()
                                               if value is not None})
            plan['updated_at_utc'] = _now()
            db.execute('UPDATE trade_plans SET payload_json=? WHERE account_key=? AND draft_id=?',
                       (_encode(plan), account_key, draft_id))
            return plan
