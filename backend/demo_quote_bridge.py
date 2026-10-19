"""Local read-only bridge to a single cTrader DEMO XAUUSD snapshot.

The SDK runs in a child process because its Twisted reactor cannot be safely
restarted inside the FastAPI process. No order messages are available here.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import subprocess
import sys
from threading import Lock
from time import monotonic


PRODUCT = Path(__file__).resolve().parents[1]
CONFIG = PRODUCT / '.env.ctrader'
_lock = Lock()
_cache: tuple[float, dict] | None = None


def sanitize_quote_result(payload: dict) -> dict:
    result = {'source': 'ctrader_demo_xauusd', 'environment': 'demo',
              'status': str(payload.get('quote_status', 'UNAVAILABLE')),
              'bid': None, 'ask': None, 'source_time_utc': None,
              'age_seconds': None, 'order_connection': False}
    if result['status'] not in ('CURRENT', 'STALE', 'TIMESTAMP_UNAVAILABLE'):
        return result
    quote = payload.get('quote')
    if not isinstance(quote, dict):
        result['status'] = 'UNAVAILABLE'
        return result
    try:
        bid, ask = Decimal(str(quote['bid'])), Decimal(str(quote['ask']))
        if not bid.is_finite() or not ask.is_finite() or bid <= 0 or ask < bid:
            raise ValueError('invalid bid/ask')
        source_time = quote.get('source_time_utc')
        if source_time is not None:
            datetime.fromisoformat(source_time)
        age = quote.get('age_seconds')
        if age is not None and (not isinstance(age, (int, float)) or age < 0 or age > 864000):
            raise ValueError('invalid quote age')
    except (KeyError, InvalidOperation, TypeError, ValueError):
        result['status'] = 'UNAVAILABLE'
        return result
    result.update(bid=str(bid), ask=str(ask), source_time_utc=source_time,
                  age_seconds=age)
    return result


def read_demo_quote() -> dict:
    global _cache
    if not CONFIG.is_file():
        return sanitize_quote_result({'quote_status': 'NOT_CONFIGURED'})
    with _lock:
        now = monotonic()
        if _cache and now < _cache[0]:
            return dict(_cache[1])
        try:
            completed = subprocess.run(
                [sys.executable, '-m', 'scripts.check_ctrader_spot'],
                cwd=PRODUCT, capture_output=True, text=True, timeout=32, check=False)
            payload = json.loads(completed.stdout)
            result = sanitize_quote_result(payload)
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, TypeError):
            result = sanitize_quote_result({'quote_status': 'UNAVAILABLE'})
        _cache = (monotonic() + 10, result)
        return dict(result)
