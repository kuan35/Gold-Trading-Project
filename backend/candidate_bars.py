"""Candidate-only closed-bar assembly and evidence-gated coverage."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation


D = Decimal
FRAMES = (('5m', 300, 60), ('15m', 900, 60), ('1h', 3600, 20))


def _prices(bar):
    try:
        values = [D(str(bar[name])) for name in ('open', 'high', 'low', 'close')]
    except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError('invalid OHLC') from exc
    op, high, low, close = values
    if not all(value.is_finite() and value > 0 for value in values) or not low <= min(op, close) <= max(op, close) <= high:
        raise ValueError('invalid OHLC')
    return values


def complete_frames(bars, clock, seconds):
    if seconds < 300 or seconds % 300:
        raise ValueError('frame is not a multiple of five minutes')
    groups = defaultdict(list)
    seen = set()
    for bar in bars:
        time = bar['time']
        if not isinstance(time, int) or time % 300 or time in seen:
            raise ValueError('duplicate or non-aligned five-minute bar')
        seen.add(time)
        if time + 300 > clock:
            continue
        groups[time // seconds * seconds].append(bar)
    result = []
    for start, group in sorted(groups.items()):
        if start + seconds > clock:
            continue
        group.sort(key=lambda item: item['time'])
        if (len(group) != seconds // 300 or any(
                bar['time'] != start + index * 300 for index, bar in enumerate(group))):
            continue
        values = [_prices(bar) for bar in group]
        op = values[0][0]
        high = max(value[1] for value in values)
        low = min(value[2] for value in values)
        close = values[-1][3]
        result.append(dict(time=start, open=str(op), high=str(high),
                           low=str(low), close=str(close)))
    return result


def classify_gap(start, end, allowed_session_gaps):
    return ('SESSION_GAP' if (start, end) in allowed_session_gaps
            else 'UNEXPLAINED_GAP')


def classify_coverage(bars, clock, allowed_session_gaps, alternate=None):
    """Inspect a bounded pre-entry window; a rankable tier needs every mandatory frame."""
    result = dict(tier='none', status='OUTSIDE_SOURCE_RANGE', counts={},
                  latest_closed={}, gaps=[], source_conflicts=[])
    if not bars:
        return result
    visible = [bar for bar in bars if bar['time'] + 300 <= clock]
    if not visible:
        return result
    if any(next_bar['time'] <= bar['time'] for bar, next_bar in zip(visible, visible[1:])):
        raise ValueError('bars must be sorted and unique')
    all_frames = {}
    for label, seconds, minimum in FRAMES:
        frames = complete_frames(visible, clock, seconds)
        all_frames[label] = frames
        result['counts'][label] = len(frames)
        if frames:
            result['latest_closed'][label] = frames[-1]['time'] + seconds
        for left, right in zip(frames[-minimum:], frames[-minimum + 1:]):
            start, end = left['time'] + seconds, right['time']
            if end > start:
                result['gaps'].append(dict(frame=label, start=start, end=end,
                                           reason=classify_gap(start, end, allowed_session_gaps)))
    five = all_frames['5m']
    if len(five) < 60:
        result['status'] = 'INCOMPLETE_BUCKET'
        return result
    if clock - result['latest_closed']['5m'] >= 300:
        result['status'] = 'STALE_LAST_CLOSED_BAR'
        return result
    if any(gap['frame'] == '5m' and gap['reason'] == 'UNEXPLAINED_GAP'
           for gap in result['gaps']):
        result['status'] = 'UNEXPLAINED_GAP'
        return result
    result['tier'] = '5m_only'
    if any(len(all_frames[label]) < minimum for label, _, minimum in FRAMES[1:]):
        result['status'] = 'INCOMPLETE_BUCKET'
        return result
    if any(clock - result['latest_closed'][label] >= seconds for label, seconds, _ in FRAMES[1:]):
        result['status'] = 'STALE_LAST_CLOSED_BAR'
        return result
    alternate = alternate or {}
    for frame in all_frames['1h'][-20:]:
        other = alternate.get(frame['time'])
        if other and any(D(str(frame[key])) != D(str(other[key]))
                         for key in ('open', 'high', 'low', 'close')):
            result['source_conflicts'].append(dict(time=frame['time'],
                                                   primary=frame, alternate=other))
    if result['source_conflicts']:
        result['status'] = 'SOURCE_CONFLICT'
        return result
    if any(gap['reason'] == 'UNEXPLAINED_GAP' for gap in result['gaps']):
        result['status'] = 'UNEXPLAINED_GAP'
        return result
    result['tier'] = 'full'
    result['status'] = 'FULL_CANDIDATE'
    return result
