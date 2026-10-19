"""Fixed, point-in-time language for the ordering of a pre-entry price path.

This is a coarse description of the same closed candles used by numerical
retrieval. It adds no independent market data and makes no trading prediction.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


_ANCHORS = (0, 19, 39, 59)
_LABELS = {'U': '上行', 'D': '下行', 'S': '盤整'}


def _positive_decimal(value: object) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError('invalid pre-entry price or volatility') from error
    if not number.is_finite() or number <= 0:
        raise ValueError('invalid pre-entry price or volatility')
    return number


def describe_market_sequence(profile: dict) -> dict:
    """Encode three chronological 5m phases with a frozen 1-ATR neutral band."""
    if profile.get('status') != 'candidate_only' or profile.get('tier') not in ('full', '5m_only'):
        raise ValueError('unavailable market profile')
    clock = profile.get('as_of')
    bars = (profile.get('pre_entry_bars') or {}).get('5m')
    if type(clock) is not int or not isinstance(bars, list) or len(bars) != 60:
        raise ValueError('sequence needs 60 closed five-minute bars')
    times = [bar.get('time') if isinstance(bar, dict) else None for bar in bars]
    if any(type(value) is not int for value in times):
        raise ValueError('sequence has invalid bar time')
    if any(value + 300 > clock for value in times):
        raise ValueError('sequence contains a future bar')
    if any(right <= left for left, right in zip(times, times[1:])):
        raise ValueError('sequence bars are not chronological')
    closes = [_positive_decimal(bar.get('close')) for bar in bars]
    atr_pct = _positive_decimal((profile.get('indicators') or {}).get('5m_atr_pct'))
    neutral_band = closes[-1] * atr_pct / 100
    phases = []
    for left, right in zip(_ANCHORS, _ANCHORS[1:]):
        delta = closes[right] - closes[left]
        phases.append('U' if delta > neutral_band else 'D' if delta < -neutral_band else 'S')
    code = ''.join(phases)
    sequence = ' → '.join(_LABELS[value] for value in code)
    return {
        'schema_version': 'pre_entry_sequence_v1',
        'as_of': clock,
        'timezone_status': profile.get('timezone_status', 'UNKNOWN'),
        'pattern_code': code,
        'text': f'60根已收5分鐘K線分三段：{sequence}；各段變動未超過當下1倍ATR時記為盤整。',
    }
