"""Program-owned chart coordinates for one immutable analysis snapshot.

Prices use Decimal until converted to plotting coordinates. These layers carry
no model output, order authority, or claim that candidate pivots are validated.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from math import isfinite

from .context_retrieval import EVENT_LABELS
from .technical import analyze_native


PERIODS = {'5m': (300, 'f5'), '15m': (900, 'f15'), '1h': (3600, 'f1')}


def _fixed_event_layers(bars):
    """Use the same fixed 20-before-6 range and close buffer as context rules."""
    window = bars[-26:]
    if len(window) != 26 or any(b['time']-a['time'] != 300 for a, b in zip(window, window[1:])):
        return []
    reference, recent = window[:20], window[20:]
    high = max(Decimal(str(b['high'])) for b in reference)
    low = min(Decimal(str(b['low'])) for b in reference)
    ranges = [max(Decimal(str(b['high']))-Decimal(str(b['low'])),
                  abs(Decimal(str(b['high']))-Decimal(str(a['close']))),
                  abs(Decimal(str(b['low']))-Decimal(str(a['close']))))
              for a, b in zip(reference, reference[1:])]
    atr = sum(ranges[-14:], Decimal(0))/14
    if atr <= 0:
        return []
    buffer = atr*Decimal('.1')

    def zone(close):
        if close > high+buffer:
            return 'ABOVE'
        if close < low-buffer:
            return 'BELOW'
        if low+buffer < close < high-buffer:
            return 'INSIDE'
        return 'BOUNDARY_UNKNOWN'

    zones = [zone(Decimal(str(b['close']))) for b in recent]
    state = zones[-1]
    if state == 'INSIDE':
        above, below = 'ABOVE' in zones[:-1], 'BELOW' in zones[:-1]
        state = ('BOTH_RECLAIM' if above and below else 'UPPER_RECLAIM' if above
                 else 'LOWER_RECLAIM' if below else 'IN_RANGE')
    label = EVENT_LABELS[state]
    wick = any(Decimal(str(b['high'])) > high+buffer or Decimal(str(b['low'])) < low-buffer for b in recent)
    if state == 'IN_RANGE' and wick:
        label += '（影線越界，未形成收盤突破）'
    return [
        dict(id='f5.fixed-range', kind='region', label='最近6棒之前20棒的固定高低區間',
             start_time=reference[0]['time'], end_time=recent[0]['time'], high=str(high), low=str(low)),
        dict(id='f5.range-high', kind='line', label='固定事件區間上緣（前20棒）', price=str(high)),
        dict(id='f5.range-low', kind='line', label='固定事件區間下緣（前20棒）', price=str(low)),
        dict(id='f5.recent-six', kind='region', label='最近6根已收棒事件觀察範圍',
             start_time=recent[0]['time'], end_time=recent[-1]['time']+300,
             high=str(max(Decimal(str(b['high'])) for b in recent)),
             low=str(min(Decimal(str(b['low'])) for b in recent))),
        dict(id='f5.event', kind='marker', label=label, time=recent[-1]['time'],
             price=str(Decimal(str(recent[-1]['close'])))),
    ]


def build_analysis_visuals(snapshot: dict, context: dict, now: float) -> dict:
    """Return only native completed bars and deterministic snapshot layers.

    The saved context time owns the cutoff, even if read much later. Invalid
    prices reject that chart frame; absent frames are never resampled or filled.
    """
    result = dict(as_of_utc=context.get('as_of_utc'), frames={})
    try:
        stamp = datetime.fromisoformat(context['as_of_utc'].replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            raise ValueError('missing timezone')
        cutoff = stamp.timestamp()
        if not isfinite(cutoff) or not isfinite(now) or cutoff > now:
            raise ValueError('invalid snapshot cutoff')
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        cutoff = None
    for interval, (span, prefix) in PERIODS.items():
        frame = dict(bars=[], layers=[], quality=dict(status='unavailable', reasons=['analysis_unavailable']))
        result['frames'][interval] = frame
        if cutoff is None or context.get('status') != 'CURRENT':
            continue
        raw = (snapshot.get('bars') or {}).get(interval) or []
        if not isinstance(raw, list):
            frame['quality'] = dict(status='invalid', reasons=['native_bars_must_be_a_list'])
            continue
        technical = analyze_native(raw, span, int(cutoff))
        quality = dict(technical['data_quality'])
        frame['quality'] = quality
        if quality['status'] == 'invalid' or quality['rejected_price_count']:
            quality['status'] = 'invalid'
            continue
        chosen = [b for b in raw if b['time']+span <= cutoff][-90:]
        try:
            bars = [dict(time=b['time'], **{k: float(Decimal(str(b[k]))) for k in ('open', 'high', 'low', 'close')}) for b in chosen]
            if any(not isfinite(b[k]) or b[k] <= 0 for b in bars for k in ('open', 'high', 'low', 'close')):
                raise ValueError('unplottable price')
        except (KeyError, TypeError, ValueError, InvalidOperation, OverflowError):
            quality.update(status='invalid', reasons=quality['reasons']+['unplottable_ohlc'])
            continue
        frame['bars'] = bars
        if not bars:
            continue
        if cutoff-technical['last_closed_at'] > span+30:
            quality.update(status='stale', reasons=quality['reasons']+['closed_bars_stale_at_snapshot'])
            continue
        levels = technical['levels']
        for side, label in [('support', '支撐'), ('resistance', '壓力')]:
            for n, level in enumerate(levels[side], 1):
                if level['confirmed_at'] <= cutoff and Decimal(level['price']) > 0:
                    frame['layers'].append(dict(id=f'{prefix}.{side}.{n}', kind='line',
                        label=f'已收棒轉折{label}候選（非固定事件區間）', price=level['price']))
        if interval == '5m':
            # Keep Decimal source values for event coordinates and classifications.
            frame['layers'].extend(_fixed_event_layers(chosen))
    return result
