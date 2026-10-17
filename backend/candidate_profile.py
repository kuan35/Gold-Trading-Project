"""Candidate-only pre-entry market profiles; never use an entry/future bar."""

from __future__ import annotations

from decimal import Decimal

from .candidate_bars import complete_frames
from .technical import ema, wilder


D = Decimal


def _indicators(candles, label, *, momentum):
    closes = [D(bar['close']) for bar in candles]
    highs = [D(bar['high']) for bar in candles]
    lows = [D(bar['low']) for bar in candles]
    if len(candles) < (34 if momentum else 20):
        return None, None
    ranges = [max(highs[index] - lows[index],
                  abs(highs[index] - closes[index - 1]),
                  abs(lows[index] - closes[index - 1]))
              for index in range(1, len(candles))]
    atr = wilder(ranges, 14)
    if atr is None or atr <= 0:
        return None, None
    ma = sum(closes[-20:], D(0)) / 20
    output = {label + '_ma_gap': (closes[-1] - ma) / atr,
              label + '_atr_pct': atr / closes[-1] * 100}
    if momentum:
        changes = [end - start for start, end in zip(closes, closes[1:])]
        gains = wilder([max(change, D(0)) for change in changes], 14)
        losses = wilder([max(-change, D(0)) for change in changes], 14)
        if gains is None or losses is None:
            return None, None
        rsi = (D(50) if gains == losses == 0 else D(100) if losses == 0
               else D(100) - D(100) / (D(1) + gains / losses))
        fast, slow = ema(closes, 12), ema(closes, 26)
        macd = [left - right for left, right in zip(fast[-len(slow):], slow)]
        signal = ema(macd, 9)
        if not signal:
            return None, None
        output[label + '_rsi14'] = rsi
        output[label + '_macd_hist'] = (macd[-1] - signal[-1]) / atr
    return output, atr


def profile_before_entry(bars, clock, coverage):
    unavailable = lambda reason: dict(status='insufficient', reason=reason)
    tier = coverage.get('tier')
    if tier not in ('full', '5m_only'):
        return unavailable(coverage.get('status', 'NO_CANDIDATE_COVERAGE'))
    frames = {'5m': complete_frames(bars, clock, 300)}
    if len(frames['5m']) < 61:
        return unavailable('FIVE_MINUTE_PREVIOUS_CLOSE_MISSING')
    if tier == 'full':
        frames.update({'15m': complete_frames(bars, clock, 900),
                       '1h': complete_frames(bars, clock, 3600)})
        if len(frames['15m']) < 60 or len(frames['1h']) < 20:
            return unavailable('HIGHER_FRAME_HISTORY_INSUFFICIENT')
    indicators = {}
    atr5 = None
    for label in frames:
        values, atr = _indicators(frames[label], label, momentum=label != '1h')
        if values is None:
            return unavailable(label.upper() + '_INDICATOR_HISTORY_INSUFFICIENT')
        indicators.update(values)
        if label == '5m':
            atr5 = atr
    five = frames['5m']
    closes = [D(bar['close']) for bar in five]
    if len(five) < 61 or atr5 is None or atr5 <= 0:
        return unavailable('FIVE_MINUTE_ATR_MISSING')
    current_ma = sum(closes[-20:], D(0)) / 20
    previous_ma = sum(closes[-25:-5], D(0)) / 20
    indicators['5m_slope'] = (current_ma - previous_ma) / 5 / atr5
    recent = five[-60:]
    low = min(D(bar['low']) for bar in recent)
    high = max(D(bar['high']) for bar in recent)
    if high <= low:
        return unavailable('FIVE_MINUTE_RANGE_MISSING')
    indicators['range_position'] = (D(recent[-1]['close']) - low) / (high - low)
    shape = []
    for previous, bar in zip(five[-61:-1], recent):
        op, high, low, close = (D(bar[key]) for key in ('open', 'high', 'low', 'close'))
        prev_close = D(previous['close'])
        shape.extend(str(value / atr5) for value in (
            op - prev_close, close - op, high - max(op, close), min(op, close) - low))
    if len(shape) != 240:
        return unavailable('FIVE_MINUTE_SHAPE_INCOMPLETE')
    latest = {label: frames[label][-1]['time'] + seconds
              for label, seconds in (('5m', 300), ('15m', 900), ('1h', 3600))
              if label in frames}
    if any(value > clock for value in latest.values()):
        return unavailable('FUTURE_BAR')
    return dict(status='candidate_only', timezone_status='UNKNOWN',
                production_enabled=False, tier=tier, as_of=clock,
                latest_closed=latest, shape=shape,
                indicators={key: str(value) for key, value in sorted(indicators.items())},
                pre_entry_bars={'5m': recent,
                                **({'15m': frames['15m'][-60:], '1h': frames['1h'][-20:]}
                                   if tier == 'full' else {})})
