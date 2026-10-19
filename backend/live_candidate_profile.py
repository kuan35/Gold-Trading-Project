"""Build a point-in-time query from one cTrader DEMO closed-bar snapshot."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from .candidate_bars import _prices
from .candidate_profile import _indicators, profile_before_entry


PERIODS = {'5m': (300, 61), '15m': (900, 60), '1h': (3600, 20)}


def _unavailable(reason: str) -> dict:
    return {'status': 'insufficient', 'reason': reason}


def _closed_frame(raw: list[dict], seconds: int, minimum: int, clock: int) -> list[dict]:
    frames = sorted(raw, key=lambda bar: bar['time'])
    if len(frames) < minimum:
        raise ValueError('HISTORY_INSUFFICIENT')
    frames = frames[-minimum:]
    if any(not isinstance(bar['time'], int) or bar['time'] % seconds or
           bar['time'] + seconds > clock for bar in frames):
        raise ValueError('FORMING_OR_UNALIGNED_BAR')
    if any(right['time'] - left['time'] != seconds
           for left, right in zip(frames, frames[1:])):
        raise ValueError('BAR_GAP_OR_DUPLICATE')
    if clock - (frames[-1]['time'] + seconds) >= seconds:
        raise ValueError('STALE_CLOSED_BAR')
    for bar in frames:
        _prices(bar)
    return frames


def profile_from_live_snapshot(snapshot: dict) -> dict:
    """Use no tick price as a candle; return an explicit insufficiency on gaps."""
    quote = snapshot.get('quote') or {}
    if snapshot.get('connection_status') != 'CONNECTED' or quote.get('status') != 'CURRENT':
        return _unavailable('BROKER_QUOTE_UNAVAILABLE')
    if quote.get('source_time_utc') is None:
        return _unavailable('BROKER_TIME_UNAVAILABLE')
    try:
        source_time = datetime.fromisoformat(quote['source_time_utc'])
        if source_time.tzinfo is None:
            raise ValueError('naive time')
        clock = int(source_time.astimezone(timezone.utc).timestamp()) // 300 * 300
        frames = {}
        for label, (seconds, minimum) in PERIODS.items():
            raw = (snapshot.get('bars') or {}).get(label)
            if not isinstance(raw, list):
                raise ValueError(label.upper() + '_MISSING')
            frames[label] = _closed_frame(raw, seconds, minimum, clock)
        if frames['5m'][-1]['time'] + 300 != clock:
            raise ValueError('FIVE_MINUTE_LAST_CLOSE_MISSING')
        profile = profile_before_entry(frames['5m'], clock, {'tier': '5m_only'})
        if profile['status'] != 'candidate_only':
            return profile
        for label in ('15m', '1h'):
            values, _ = _indicators(frames[label], label, momentum=label != '1h')
            if values is None:
                raise ValueError(label.upper() + '_INDICATORS_UNAVAILABLE')
            profile['indicators'].update({key: str(value) for key, value in values.items()})
            profile['pre_entry_bars'][label] = frames[label]
            profile['latest_closed'][label] = frames[label][-1]['time'] + PERIODS[label][0]
        profile['indicators'] = dict(sorted(profile['indicators'].items()))
        profile['tier'] = 'full'
        profile['source'] = 'ctrader_demo_xauusd'
        profile['query_clock_status'] = 'UTC_SOURCE_TIMESTAMP'
        return profile
    except (KeyError, TypeError, ValueError, OverflowError, ArithmeticError) as exc:
        return _unavailable(str(exc) or 'BROKER_BARS_INVALID')
