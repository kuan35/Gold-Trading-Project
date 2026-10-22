"""Fixed-template chart retrieval, kept separate from the production hybrid.

Category agreement is a descriptive count, not probability. All price arithmetic
uses Decimal; floats below are unitless comparison distances only.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from math import isfinite


METHOD = 'compact_market_v1'
STRUCTURES = {
    'CLOSE_ABOVE': '收盤突破前20棒高點',
    'CLOSE_BELOW': '收盤跌破前20棒低點',
    'UPPER_SWEEP_RETURN': '上刺前高後收回區間',
    'LOWER_SWEEP_RETURN': '下刺前低後收回區間',
    'BOTH_SWEEPS_RETURN': '上下皆刺穿後收回區間',
    'IN_RANGE': '前20棒區間內',
}
PHASES = {'U': '上行', 'D': '下行', 'S': '淨變動小'}
VARIANTS = {'five': ('five', 'volatility'),
            'hour': ('five', 'hour', 'volatility'),
            'full': ('five', 'hour', 'structure', 'volatility')}


def _number(raw) -> Decimal:
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ValueError('missing or invalid numeric value') from error
    if not value.is_finite():
        raise ValueError('non-finite numeric value')
    return value


def _candles(profile: dict, label: str, count: int, seconds: int) -> list[dict]:
    raw = (profile.get('pre_entry_bars') or {}).get(label)
    if not isinstance(raw, list) or len(raw) < count:
        raise ValueError(label + ' history insufficient')
    previous = None
    for bar in raw:
        if not isinstance(bar, dict) or type(bar.get('time')) is not int:
            raise ValueError('invalid bar timestamp')
        if bar['time'] + seconds > profile['as_of']:
            raise ValueError('future or forming bar')
        if previous is not None and bar['time'] <= previous:
            raise ValueError('unordered or duplicate bars')
        previous = bar['time']
        op, hi, lo, close = [_number(bar.get(key)) for key in ('open', 'high', 'low', 'close')]
        if lo <= 0 or lo > min(op, close) or hi < max(op, close):
            raise ValueError('invalid OHLC prices')
    return raw[-count:]


def _phases(bars: list[dict], anchors: tuple[int, ...], atr: Decimal,
            neutral: Decimal) -> tuple[str, list[float]]:
    values = [(_number(bars[right]['close']) - _number(bars[left]['close'])) / atr
              for left, right in zip(anchors, anchors[1:])]
    return ''.join('U' if v > neutral else 'D' if v < -neutral else 'S'
                   for v in values), [float(v) for v in values]


def _structure(bars: list[dict], atr: Decimal) -> dict:
    reference = bars[-21:-1]
    high = max(_number(b['high']) for b in reference)
    low = min(_number(b['low']) for b in reference)
    last = bars[-1]
    close, top, bottom = [_number(last[k]) for k in ('close', 'high', 'low')]
    if close > high:
        state = 'CLOSE_ABOVE'
    elif close < low:
        state = 'CLOSE_BELOW'
    elif top > high and bottom < low:
        state = 'BOTH_SWEEPS_RETURN'
    elif top > high:
        state = 'UPPER_SWEEP_RETURN'
    elif bottom < low:
        state = 'LOWER_SWEEP_RETURN'
    else:
        state = 'IN_RANGE'
    return dict(structure=state, reference_high=str(high), reference_low=str(low),
                high_gap_atr=float((close - high) / atr),
                low_gap_atr=float((close - low) / atr))


def describe_compact(profile: dict, side: str, *, neutral_atr='1') -> dict:
    if side not in ('BUY', 'SELL') or profile.get('status') != 'candidate_only':
        raise ValueError('unavailable profile or side')
    if type(profile.get('as_of')) is not int or profile.get('tier') not in ('full', '5m_only'):
        raise ValueError('invalid profile clock or tier')
    neutral = _number(neutral_atr)
    if neutral <= 0:
        raise ValueError('invalid neutral band')
    five = _candles(profile, '5m', 60, 300)
    pct5 = _number((profile.get('indicators') or {}).get('5m_atr_pct'))
    if pct5 <= 0:
        raise ValueError('invalid five-minute ATR')
    atr5 = _number(five[-1]['close']) * pct5 / 100
    code5, segments5 = _phases(five, (0, 19, 39, 59), atr5, neutral)
    result = dict(schema=METHOD, side=side, as_of=profile['as_of'], tier=profile['tier'],
                  pattern_5m=code5, phase_5m_atr=segments5,
                  pattern_1h=None, phase_1h_atr=None, atr_pct_5m=float(pct5),
                  window_start=five[0]['time'], window_end=five[-1]['time'] + 300,
                  end_5m=five[-1]['time'] + 300, end_1h=None,
                  **_structure(five, atr5))
    if profile['tier'] == 'full':
        hour = _candles(profile, '1h', 20, 3600)
        pct_hour = _number((profile.get('indicators') or {}).get('1h_atr_pct'))
        if pct_hour <= 0:
            raise ValueError('invalid hourly ATR')
        atr_hour = _number(hour[-1]['close']) * pct_hour / 100
        code, phases = _phases(hour, (0, 6, 12, 19), atr_hour, neutral)
        result.update(pattern_1h=code, phase_1h_atr=phases,
                      window_start=min(result['window_start'], hour[0]['time']),
                      window_end=max(result['window_end'], hour[-1]['time'] + 3600),
                      end_1h=hour[-1]['time'] + 3600)
    result['text'] = format_compact(result)
    return result


def format_compact(description: dict, volatility: str | None = None) -> str:
    def sequence(code):
        return '→'.join(PHASES[c] for c in code) if code else '資料不足'
    vol = {'LOW': '低', 'MID': '中', 'HIGH': '高'}.get(volatility, '待查詢池分級')
    return (f"{description['side']}｜5分：{sequence(description['pattern_5m'])}｜"
            f"1小時：{sequence(description['pattern_1h'])}｜"
            f"結構：{STRUCTURES[description['structure']]}｜"
            f"波動：{vol}（ATR/價格 {description['atr_pct_5m']:.4f}%）｜"
            f"距前高 {description['high_gap_atr']:+.2f} ATR，"
            f"距前低 {description['low_gap_atr']:+.2f} ATR")


def eligible_pool(cases: list[dict], descriptions: dict, query: dict, *,
                  exclude_group: str | None = None, purge_overlap: bool = True) -> tuple[list[dict], dict]:
    pool = []
    before_overlap = overlap = 0
    for case in cases:
        d = descriptions.get(case.get('id'))
        if (not d or case.get('side') != query['side'] or d['side'] != query['side']
                or not isinstance(case.get('group'), str)
                or case['group'] == exclude_group
                or type(case.get('available_at')) is not int
                or case['available_at'] > query['as_of'] or d['as_of'] > query['as_of']
                or d['window_end'] > query['as_of'] or d['tier'] != query['tier']):
            continue
        before_overlap += 1
        if purge_overlap and d['window_end'] > query['window_start']:
            overlap += 1
            continue
        pool.append(case)
    return pool, dict(eligible_before_overlap_rows=before_overlap,
                      excluded_overlap_rows=overlap, eligible_rows=len(pool))


def volatility_bounds(pool: list[dict], descriptions: dict) -> dict | None:
    if not pool:
        return None
    by_group = {}
    for case in sorted(pool, key=lambda c: (descriptions[c['id']]['as_of'], c['id'])):
        by_group.setdefault(case['group'], descriptions[case['id']]['atr_pct_5m'])
    values = sorted(by_group.values())
    return dict(low=values[int((len(values) - 1) * .25)],
                high=values[int((len(values) - 1) * .75)], groups=len(values))


def volatility_band(value: float, bounds: dict) -> str:
    return 'LOW' if value < bounds['low'] else 'HIGH' if value > bounds['high'] else 'MID'


def pair_measure(query: dict, candidate: dict, bounds: dict, variant: str = 'full') -> dict:
    if variant not in VARIANTS:
        raise ValueError('unknown compact variant')
    qvol = volatility_band(query['atr_pct_5m'], bounds)
    cvol = volatility_band(candidate['atr_pct_5m'], bounds)
    matches = dict(five=query['pattern_5m'] == candidate['pattern_5m'],
                   hour=query['pattern_1h'] == candidate['pattern_1h'],
                   structure=query['structure'] == candidate['structure'], volatility=qvol == cvol)
    fields = VARIANTS[variant]
    differences = [abs(a - b) for a, b in zip(query['phase_5m_atr'], candidate['phase_5m_atr'])]
    if variant in ('hour', 'full'):
        differences += [abs(a - b) for a, b in zip(query['phase_1h_atr'], candidate['phase_1h_atr'])]
    if variant == 'full':
        differences += [abs(query[k] - candidate[k]) for k in ('high_gap_atr', 'low_gap_atr')]
    ratio = max(query['atr_pct_5m'] / candidate['atr_pct_5m'],
                candidate['atr_pct_5m'] / query['atr_pct_5m'])
    if not all(isfinite(v) for v in differences + [ratio]):
        raise ValueError('non-finite descriptor distance')
    return dict(agreement_count=sum(matches[k] for k in fields), field_count=len(fields),
                field_matches={k: matches[k] for k in fields},
                max_difference_atr=max(differences), mean_difference_atr=sum(differences) / len(differences),
                volatility_ratio=ratio, query_volatility=qvol, candidate_volatility=cvol)


def distinct_rows(rows: list[dict], descriptions: dict, top_k: int | None = 5) -> list[dict]:
    seen_groups, seen_windows, result = set(), set(), []
    for row in rows:
        d = descriptions[row['case_id']]
        window = (d['end_5m'], d['end_1h'])
        if row['group'] in seen_groups or window in seen_windows:
            continue
        seen_groups.add(row['group'])
        seen_windows.add(window)
        result.append(row)
        if top_k is not None and len(result) >= top_k:
            break
    return result


def rank_pool(pool: list[dict], descriptions: dict, query: dict, bounds: dict,
              *, variant: str = 'full', top_k: int | None = 5) -> list[dict]:
    rows = [dict(case_id=c['id'], group=c['group'],
                 **pair_measure(query, descriptions[c['id']], bounds, variant)) for c in pool]
    rows.sort(key=lambda row: (-row['agreement_count'], row['max_difference_atr'],
                               row['mean_difference_atr'], row['volatility_ratio'], row['case_id']))
    return distinct_rows(rows, descriptions, top_k)


def rank_compact(cases: list[dict], descriptions: dict, query: dict, *, variant='full',
                 exclude_group: str | None = None, purge_overlap=True, top_k=5) -> dict:
    result = dict(method=METHOD, variant=variant, status='NO_MATCH', rows=[],
                  volatility_bounds=None, counts={})
    if query['tier'] != 'full' and variant != 'five':
        result['status'] = 'INSUFFICIENT_QUERY'
        return result
    pool, counts = eligible_pool(cases, descriptions, query, exclude_group=exclude_group,
                                 purge_overlap=purge_overlap)
    result['counts'] = counts
    bounds = volatility_bounds(pool, descriptions)
    if bounds is None:
        return result
    rows = rank_pool(pool, descriptions, query, bounds, variant=variant, top_k=top_k)
    result.update(rows=rows, volatility_bounds=bounds,
                  status='SAME_TEMPLATE' if rows and rows[0]['agreement_count'] ==
                  rows[0]['field_count'] else 'NEAREST_REFERENCE')
    return result
