"""Local reminders with no model, broker-write, or network dependencies.

The local service must keep running. A restarted evaluator takes a baseline
before considering saved alerts, and never reconstructs missed price touches.
Official event identity and schedule must be verified by the API before create.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sqlite3
from threading import Event, RLock, Thread
import time
from uuid import uuid4
from .market_clock import SOURCE_CLOCK_SKEW_SECONDS


MONITORING_NOTE = '本機服務必須持續執行；停止或行情中斷時不持續監控，恢復後不補過去觸價。提醒不會呼叫模型或送單。'
FRESH_SECONDS = 5


class AlertError(ValueError):
    def __init__(self, code, message, status_code=400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _clock(now=None):
    if now is None:
        return time.time()
    if isinstance(now, datetime):
        if now.tzinfo is None:
            raise AlertError('invalid_time', 'Time must include a timezone')
        return now.timestamp()
    return float(now)


def _stamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace('+00:00', 'Z')


def _source_time(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.timestamp() if parsed.tzinfo is not None else None
    except (ValueError, TypeError, OverflowError):
        return None


def _positive_decimal(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = Decimal(value)
        return parsed if parsed.is_finite() and parsed > 0 else None
    except InvalidOperation:
        return None


def _text(value, maximum=120):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def _body(body, clock):
    if not isinstance(body, dict):
        raise AlertError('invalid_condition', 'Reminder must be an object')
    kind = body.get('kind')
    if kind not in ('PRICE', 'CLOSE_5M', 'EVENT') or not _text(body.get('name')):
        raise AlertError('invalid_condition', 'Valid reminder kind and name (1–120 characters) required')
    result = {'kind': kind, 'name': body['name'].strip()}
    if body.get('conversation_id') is not None:
        if not _text(body['conversation_id'], 200):
            raise AlertError('invalid_condition', 'Invalid conversation reference')
        result['conversation_id'] = body['conversation_id']
    if kind in ('PRICE', 'CLOSE_5M'):
        if body.get('comparator') not in ('GTE', 'LTE') or _positive_decimal(body.get('threshold')) is None:
            raise AlertError('invalid_condition', 'Positive decimal-string threshold and GTE/LTE required')
        field = body.get('field', 'bid')
        if field not in ('bid', 'ask') or (kind == 'CLOSE_5M' and field != 'bid'):
            raise AlertError('invalid_condition', 'Select bid/ask; five-minute closes use bid')
        result.update(field=field, comparator=body['comparator'], threshold=body['threshold'])
    else:
        event_at = _source_time(body.get('event_time_utc'))
        lead = body.get('lead_minutes')
        if (not _text(body.get('event_id'), 200) or event_at is None or event_at <= clock
                or type(lead) is not int or not 1 <= lead <= 10080):
            raise AlertError('invalid_condition', 'Future timezone-aware event and lead minutes (1–10080) required')
        result.update(event_id=body['event_id'], event_time_utc=_stamp(event_at), lead_minutes=lead)
    return result


class LocalAlerts:
    """Account-scoped SQLite reminder storage and deterministic evaluator.

    Each process instance must evaluate continuously. The first observation of
    alerts loaded from disk is a baseline, not an alert. Callers verify official
    calendar entries before passing EVENT bodies; this class performs no I/O
    beyond its local database.
    """

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._observations = {}
        self._active_account = None
        with self._connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS local_alerts (
                    id TEXT PRIMARY KEY, account_key TEXT NOT NULL,
                    body TEXT NOT NULL, state TEXT NOT NULL,
                    revision INTEGER NOT NULL, generation INTEGER NOT NULL,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL,
                    armed_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS local_alerts_account ON local_alerts(account_key);
                CREATE TABLE IF NOT EXISTS local_alert_events (
                    id TEXT PRIMARY KEY, alert_id TEXT NOT NULL,
                    account_key TEXT NOT NULL, generation INTEGER NOT NULL,
                    created_at REAL NOT NULL, body TEXT NOT NULL,
                    UNIQUE(alert_id, generation)
                );
                CREATE INDEX IF NOT EXISTS local_alert_events_account ON local_alert_events(account_key);
            ''')

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _account(account_key):
        if not _text(account_key, 300):
            raise AlertError('account_unavailable', 'Current account identity is required', 409)

    @staticmethod
    def _dto(row):
        return {**json.loads(row['body']), 'id': row['id'], 'state': row['state'],
                'enabled': row['state'] == 'ACTIVE', 'revision': row['revision'],
                'generation': row['generation'], 'created_at_utc': _stamp(row['created_at']),
                'updated_at_utc': _stamp(row['updated_at'])}

    def create(self, account_key, body, *, now=None):
        self._account(account_key)
        clock = _clock(now)
        body = _body(body, clock)
        ident = uuid4().hex
        with self._lock, self._connect() as db:
            db.execute('INSERT INTO local_alerts VALUES(?,?,?, ?,1,1,?,?,?)',
                       (ident, account_key, json.dumps(body, ensure_ascii=False), 'ACTIVE', clock, clock, clock))
            self._observations[(ident, 1)] = {'quote': clock, 'bar': clock, 'at': None}
            row = db.execute('SELECT * FROM local_alerts WHERE id=?', (ident,)).fetchone()
            return self._dto(row)

    def list(self, account_key):
        self._account(account_key)
        with self._lock, self._connect() as db:
            rows = db.execute('SELECT * FROM local_alerts WHERE account_key=? ORDER BY created_at DESC,id',
                              (account_key,)).fetchall()
            events = db.execute('SELECT body FROM local_alert_events WHERE account_key=? ORDER BY created_at DESC,id',
                                (account_key,)).fetchall()
            return {'items': [self._dto(row) for row in rows],
                    'events': [json.loads(row['body']) for row in events], 'monitoring_note': MONITORING_NOTE}

    def has_active(self):
        """Avoid starting a market connection when no local reminder needs it."""
        with self._lock, self._connect() as db:
            return db.execute("SELECT 1 FROM local_alerts WHERE state='ACTIVE' LIMIT 1").fetchone() is not None

    def _checked(self, db, account_key, ident, revision):
        row = db.execute('SELECT * FROM local_alerts WHERE id=? AND account_key=?', (ident, account_key)).fetchone()
        if row is None:
            raise AlertError('not_found', 'Reminder not found', 404)
        if type(revision) is not int or revision != row['revision']:
            raise AlertError('revision_conflict', 'Reminder changed; reload before modifying', 409)
        return row

    def update(self, account_key, ident, revision, *, enabled):
        self._account(account_key)
        if type(enabled) is not bool:
            raise AlertError('invalid_condition', 'enabled must be a boolean')
        clock = _clock()
        with self._lock, self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self._checked(db, account_key, ident, revision)
            body=json.loads(row['body'])
            if enabled and body['kind']=='EVENT' and _source_time(body['event_time_utc'])-body['lead_minutes']*60<=clock:
                raise AlertError('invalid_condition','Event reminder time has passed; select a future event',409)
            generation = row['generation'] + (1 if enabled else 0)
            db.execute('UPDATE local_alerts SET state=?,revision=revision+1,generation=?,updated_at=?,armed_at=? WHERE id=?',
                       ('ACTIVE' if enabled else 'PAUSED', generation, clock, clock, ident))
            self._observations.pop((ident, row['generation']), None)
            if enabled:
                self._observations[(ident, generation)] = {'quote': clock, 'bar': clock, 'at': None}
            return self._dto(db.execute('SELECT * FROM local_alerts WHERE id=?', (ident,)).fetchone())

    def delete(self, account_key, ident, revision):
        self._account(account_key)
        with self._lock, self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self._checked(db, account_key, ident, revision)
            db.execute('DELETE FROM local_alerts WHERE id=?', (ident,))
            self._observations.pop((ident, row['generation']), None)

    def reset_baseline(self):
        """Discard monitoring continuity after stopping or losing the source."""
        with self._lock:
            self._observations.clear()
            self._active_account = None

    @staticmethod
    def _closed_bar(snapshot, clock):
        bars = (snapshot.get('bars') or {}).get('5m') or []
        eligible = []
        for bar in bars:
            if not isinstance(bar, dict):
                continue
            start = bar.get('time')
            try:
                end = float(start) + 300
            except (ValueError, TypeError, OverflowError):
                continue
            if end <= clock:
                eligible.append((end, bar))
        return max(eligible, key=lambda item: item[0]) if eligible else (None, None)

    def evaluate(self, snapshot, *, now=None):
        """Return newly persisted events; never call a model or broker operation."""
        clock = _clock(now)
        account = snapshot.get('account') or {}
        key = account.get('account_key')
        if (snapshot.get('environment')!='demo' or account.get('status') != 'CURRENT' or not _text(key, 300)
                or snapshot.get('connection_status') not in (None, 'CONNECTED')):
            self.reset_baseline()
            return []
        quote = snapshot.get('quote') or {}
        source = _source_time(quote.get('source_time_utc'))
        fresh = quote.get('status') == 'CURRENT' and source is not None and -SOURCE_CLOCK_SKEW_SECONDS <= clock - source <= FRESH_SECONDS
        if not fresh:
            self.reset_baseline()
            return []
        bar_end, bar = self._closed_bar(snapshot, clock)
        events = []
        with self._lock, self._connect() as db:
            if self._active_account is not None and self._active_account != key:
                self._observations.clear()
            self._active_account = key
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute("SELECT * FROM local_alerts WHERE account_key=? AND state='ACTIVE' ORDER BY created_at,id",
                              (key,)).fetchall()
            for row in rows:
                identity = (row['id'], row['generation'])
                previous = self._observations.get(identity)
                if (previous is None or (previous['at'] is not None
                                         and not 0 <= clock - previous['at'] <= FRESH_SECONDS)):
                    # A saved alert sees the current quote/bar only as a baseline.
                    self._observations[identity] = {'quote': source or clock, 'bar': bar_end or clock,
                                                    'at': clock if fresh else None}
                    continue
                before = previous.copy()
                previous['at'] = clock if fresh else None
                if not fresh or clock < row['armed_at']:
                    continue
                body = json.loads(row['body'])
                observed = None
                match = False
                if body['kind'] == 'EVENT':
                    event_at = _source_time(body['event_time_utc'])
                    due = event_at - body['lead_minutes'] * 60
                    match = (before['at'] is not None and 0 <= clock - before['at'] <= FRESH_SECONDS
                             and before['at'] < due <= clock and clock < event_at)
                elif source > before['quote']:
                    previous['quote'] = source
                    if body['kind'] == 'PRICE':
                        observed = quote.get(body['field'])
                    elif (bar_end is not None and bar_end > before['bar']
                          and bar_end > row['armed_at'] and 0 <= clock - bar_end <= FRESH_SECONDS):
                        previous['bar'] = bar_end
                        observed = bar.get('close')
                    value = _positive_decimal(observed)
                    if value is not None:
                        threshold = Decimal(body['threshold'])
                        match = value >= threshold if body['comparator'] == 'GTE' else value <= threshold
                if not match:
                    continue
                event = {'id': uuid4().hex, 'alert_id': row['id'], 'name': body['name'],
                         'kind': body['kind'], 'created_at_utc': _stamp(clock)}
                if body.get('conversation_id'):
                    event['conversation_id'] = body['conversation_id']
                if observed is not None:
                    event['observed_value'] = observed
                if body['kind'] == 'EVENT':
                    event['message'] = f"{body['name']}：官方事件預定於 {body['event_time_utc']}，提前 {body['lead_minutes']} 分鐘提醒。"
                else:
                    label = '五分鐘 Bid 收盤' if body['kind'] == 'CLOSE_5M' else body['field'].capitalize()
                    operator = '>=' if body['comparator'] == 'GTE' else '<='
                    event['message'] = f"{body['name']}：{label} {observed} {operator} {body['threshold']}。"
                # State transition and unique generation event commit together.
                inserted = db.execute('INSERT OR IGNORE INTO local_alert_events VALUES(?,?,?,?,?,?)',
                                      (event['id'], row['id'], key, row['generation'], clock,
                                       json.dumps(event, ensure_ascii=False)))
                db.execute("UPDATE local_alerts SET state='TRIGGERED',revision=revision+1,updated_at=? WHERE id=? AND generation=?",
                           (clock, row['id'], row['generation']))
                if inserted.rowcount == 1:
                    events.append(event)
        return events


class AlertMonitor:
    """Explicit daemon lifecycle; snapshot_callable must be a read-only cache read."""

    def __init__(self, store, snapshot_callable, *, interval=1):
        if interval <= 0:
            raise ValueError('Monitor interval must be positive')
        self.store = store
        self.snapshot_callable = snapshot_callable
        self.interval = interval
        self._stop = Event()
        self._thread = None
        self._lock = RLock()
        self.last_error = None

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def tick(self, *, now=None):
        return self.store.evaluate(self.snapshot_callable(), now=now)

    def start(self):
        with self._lock:
            if self.running:
                return
            self.store.reset_baseline()
            self._stop.clear()
            self._thread = Thread(target=self._run, name='gold-local-alerts', daemon=True)
            self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                self.tick()
                self.last_error = None
            except Exception:
                # Keep local monitoring alive; never expose snapshot/account data.
                self.store.reset_baseline()
                self.last_error = 'Reminder evaluation unavailable'
            self._stop.wait(self.interval)

    def stop(self):
        with self._lock:
            self._stop.set()
            if self._thread is not None:
                self._thread.join(timeout=2)
            self.store.reset_baseline()
