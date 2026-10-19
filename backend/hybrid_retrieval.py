"""Point-in-time numerical retrieval with a bounded, deterministic pattern rerank.

The pattern is a coarse encoding of the same closed candles. It is not an
independent signal, a calibrated similarity threshold, or a prediction.
"""

from __future__ import annotations

from math import isfinite, sqrt
from statistics import median

from .candidate_retrieval import FIVE, HIGH, _midrank
from .market_sequence import describe_market_sequence
from .market_state_description import describe_market_state

METHOD = 'path_indicator_pattern_v1'
WINDOW = 15


def _path(profile: dict) -> list[float]:
    bars = profile['pre_entry_bars']['5m']
    first = float(bars[0]['close'])
    if not isfinite(first) or first <= 0:
        raise ValueError('invalid path base')
    values = [(float(bar['close']) / first - 1) * 100 for bar in bars]
    if len(values) != 60 or not all(isfinite(value) for value in values):
        raise ValueError('invalid close path')
    return values


def _description(profile: dict) -> str | None:
    try:
        return describe_market_state(profile)['text']
    except (KeyError, TypeError, ValueError):
        return None


def rerank_pattern_window(rows: list[dict], query_code: str, *, window: int = WINDOW) -> list[dict]:
    """Keep one representative per group; exact codes lead only inside the window."""
    if window < 5 or len(query_code) != 3:
        raise ValueError('invalid pattern window or query code')
    seen = set()
    distinct = []
    for row in rows:
        if row['group'] not in seen:
            seen.add(row['group'])
            distinct.append(dict(row, pattern_match=row['pattern_code'] == query_code))
    head, tail = distinct[:window], distinct[window:]
    return ([row for row in head if row['pattern_match']] +
            [row for row in head if not row['pattern_match']] + tail)


def _rank_tier(pool: list[dict], profiles: dict, query: dict, tier: str,
               query_path: list[float]) -> list[dict]:
    keys = FIVE + HIGH if tier == 'full' else FIVE
    measured = []
    for case in pool:
        candidate = profiles[case['id']]
        try:
            pattern = describe_market_sequence(candidate)['pattern_code']
            path = _path(candidate)
            distance = sqrt(sum((a - b) ** 2 for a, b in zip(query_path, path)) / 60)
            differences = {key: abs(float(query['indicators'][key]) -
                                    float(candidate['indicators'][key])) for key in keys}
            if not isfinite(distance) or not all(isfinite(value) for value in differences.values()):
                continue
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            continue
        described = (dict(candidate, tier='5m_only',
                          pre_entry_bars={'5m': candidate['pre_entry_bars']['5m']},
                          latest_closed={'5m': (candidate.get('latest_closed') or {}).get('5m')})
                     if tier == '5m_only' and candidate['tier'] == 'full' else candidate)
        measured.append(dict(case_id=case['id'], group=case['group'], tier=tier,
                             pattern_code=pattern, path_distance_pct=distance,
                             indicator_differences=differences,
                             market_state_text=_description(described)))
    if not measured:
        return []
    path_values = sorted(row['path_distance_pct'] for row in measured)
    feature_values = {key: sorted(row['indicator_differences'][key] for row in measured)
                      for key in keys}
    for row in measured:
        row['path_percentile'] = _midrank(row['path_distance_pct'], path_values)
        row['shape_percentile'] = row['path_percentile']  # legacy API field
        row['indicator_percentile'] = median(
            _midrank(row['indicator_differences'][key], feature_values[key]) for key in keys)
    measured.sort(key=lambda row: (
        max(row['path_percentile'], row['indicator_percentile']),
        row['path_percentile'] + row['indicator_percentile'], row['case_id']))
    return measured


def rank_hybrid_candidates(cases: list[dict], profiles: dict, query: dict,
                           side: str, clock: int) -> dict:
    result = dict(full=[], five_minute_only=[], counts=dict(full_pool=0, five_minute_only_pool=0),
                  similarity_sufficiency='NO_MATCH', reason='沒有可比較的參考盤面',
                  method=METHOD, query_pattern_code=None, query_market_text=None,
                  rerank_window=WINDOW)
    if side not in ('BUY', 'SELL') or query.get('status') != 'candidate_only' or query.get('as_of') != clock:
        result['reason'] = '查詢盤面不可比較'
        return result
    if query.get('tier') not in ('full', '5m_only'):
        result['reason'] = '查詢盤面週期資料不足'
        return result
    try:
        query_pattern = describe_market_sequence(query)['pattern_code']
        query_path = _path(query)
        if not all(isfinite(float(query['indicators'][key])) for key in FIVE):
            raise ValueError('invalid query indicators')
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        result['reason'] = '查詢時點缺少已收盤 K 線或有效指標'
        return result
    result['query_pattern_code'] = query_pattern
    result['query_market_text'] = _description(query)
    eligible = [case for case in cases if case.get('side') == side and
                type(case.get('available_at')) is int and case['available_at'] <= clock and
                case.get('id') in profiles and
                profiles[case['id']].get('status') == 'candidate_only' and
                type(profiles[case['id']].get('as_of')) is int and
                profiles[case['id']]['as_of'] <= clock and
                profiles[case['id']].get('tier') in ('full', '5m_only')]
    full_pool = [case for case in eligible if profiles[case['id']]['tier'] == 'full'] if query['tier'] == 'full' else []
    limited_pool = [case for case in eligible if profiles[case['id']]['tier'] == '5m_only'] if query['tier'] == 'full' else eligible
    result['counts'] = dict(full_pool=len(full_pool), five_minute_only_pool=len(limited_pool))
    seen = set()
    for name, tier, pool in (('full', 'full', full_pool),
                             ('five_minute_only', '5m_only', limited_pool)):
        ranked = _rank_tier(pool, profiles, query, tier, query_path)
        ranked = [row for row in ranked if row['group'] not in seen]
        rows = rerank_pattern_window(ranked, query_pattern)
        result[name] = rows
        seen.update(row['group'] for row in rows)
    if seen:
        result.update(similarity_sufficiency='UNCALIBRATED',
                      reason='數值路徑與指標近鄰經固定型態重排；是否足夠相似尚未盲評校準')
    return result
