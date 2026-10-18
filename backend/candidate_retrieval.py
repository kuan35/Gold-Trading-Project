"""Deterministic candidate-market nearest neighbors, without outcome weights."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import math
from bisect import bisect_left, bisect_right
from statistics import median


FIVE = ('5m_ma_gap', '5m_atr_pct', '5m_rsi14', '5m_macd_hist',
        '5m_slope', 'range_position')
HIGH = ('15m_ma_gap', '15m_atr_pct', '15m_rsi14', '15m_macd_hist',
        '1h_ma_gap', '1h_atr_pct')


def _midrank(value, values):
    return (bisect_left(values,value) +
            (bisect_right(values,value)-bisect_left(values,value))/2) / len(values)


def _distance(query, profile, tier):
    shape_q = [float(value) for value in query['shape']]
    shape_c = [float(value) for value in profile['shape']]
    if len(shape_q) != 240 or len(shape_c) != 240:
        raise ValueError('shape vector must have 240 values')
    shape = math.sqrt(sum((a - b) ** 2 for a, b in zip(shape_q, shape_c)) / 240)
    keys = FIVE + HIGH if tier == 'full' else FIVE
    indicators = {key: abs(float(query['indicators'][key]) -
                           float(profile['indicators'][key])) for key in keys}
    if not math.isfinite(shape) or not all(math.isfinite(v) for v in indicators.values()):
        raise ValueError('nonfinite candidate distance')
    return shape, indicators


def _rank_pool(pool, profiles, query, tier):
    if not pool:
        return []
    measured = []
    for case in pool:
        shape, indicators = _distance(query, profiles[case['id']], tier)
        measured.append(dict(case_id=case['id'], group=case['group'], tier=tier,
                             shape_distance=shape, indicator_differences=indicators))
    shapes = sorted(row['shape_distance'] for row in measured)
    keys = FIVE + HIGH if tier == 'full' else FIVE
    by_feature = {key: sorted(row['indicator_differences'][key] for row in measured)
                  for key in keys}
    for row in measured:
        row['shape_percentile'] = _midrank(row['shape_distance'], shapes)
        row['indicator_percentile'] = median(_midrank(
            row['indicator_differences'][key], by_feature[key]) for key in keys)
    measured.sort(key=lambda row: (
        max(row['shape_percentile'], row['indicator_percentile']),
        row['shape_percentile'] + row['indicator_percentile'], row['case_id']))
    return measured


def rank_candidates(cases, profiles, query, side, clock):
    result = dict(full=[], five_minute_only=[], counts=dict(full_pool=0, five_minute_only_pool=0),
                  similarity_sufficiency='NO_MATCH', reason='沒有可比較的參考盤面')
    if side not in ('BUY', 'SELL') or query.get('status') != 'candidate_only' or query.get('as_of', 0) > clock:
        result['reason'] = '查詢盤面不可比較'
        return result
    if query.get('tier') not in ('full', '5m_only'):
        return result
    eligible = [case for case in cases if case.get('side') == side and
                isinstance(case.get('available_at'), int) and case['available_at'] <= clock and
                case.get('id') in profiles and
                profiles[case['id']].get('status') == 'candidate_only' and
                profiles[case['id']].get('as_of', 0) <= clock and
                profiles[case['id']].get('tier') in ('full', '5m_only')]
    if query['tier'] == 'full':
        full = [case for case in eligible if profiles[case['id']]['tier'] == 'full']
        limited = [case for case in eligible if profiles[case['id']]['tier'] == '5m_only']
    else:
        full = []
        limited = eligible
    result['counts']['full_pool'] = len(full)
    result['counts']['five_minute_only_pool'] = len(limited)
    full_rows = _rank_pool(full, profiles, query, 'full')
    limited_rows = _rank_pool(limited, profiles, query, '5m_only')
    groups = set()
    for name, rows in (('full', full_rows), ('five_minute_only', limited_rows)):
        for row in rows:
            if row['group'] in groups:
                continue
            groups.add(row['group'])
            row['rank'] = len(result[name]) + 1
            result[name].append(row)
    if groups:
        result.update(similarity_sufficiency='UNCALIBRATED',
                      reason='依本次可用參考盤面列出近鄰；是否足夠相似尚未盲評校準')
    return result


def summarize_candidate_tier(ranked, case_lookup):
    counts = dict(win=0, loss=0, flat=0, unknown=0)
    for row in ranked:
        try:
            amount = Decimal(str(case_lookup[row['case_id']]['profit']))
            if not amount.is_finite():
                raise InvalidOperation
        except (KeyError, InvalidOperation, TypeError, ValueError):
            counts['unknown'] += 1
            continue
        counts['win' if amount > 0 else 'loss' if amount < 0 else 'flat'] += 1
    known = counts['win'] + counts['loss'] + counts['flat']
    return dict(label='歷史結果分布', total=len(ranked), counts=counts,
                historical_profit_fraction=(str(Decimal(counts['win']) / known)
                                            if known else None),
                prediction_probability=None)
