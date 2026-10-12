"""Decision-time operation similarity, independent of outcomes and market clocks."""
from __future__ import annotations

import math
from collections import defaultdict, deque
from datetime import datetime
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any

D = Decimal
METHOD = 'operation_context_20261012'
MAX_DISTANCE = .65


def positive(value: Any) -> D | None:
    try:
        number = D(str(value))
        return number if number.is_finite() and number > 0 else None
    except (InvalidOperation, ValueError):
        return None


def build_size_profiles(rows: list[dict]) -> dict[str, dict]:
    """Last 20 completed local five-minute entry batches, per source, not account.

    Each batch contributes its earliest timestamp's median lot. This prevents
    later orders in the batch and large split-order counts from dominating.
    A new batch sees only earlier batches; neither close nor P/L is consulted.
    """
    sources: dict[str, dict[datetime, list[tuple]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        lot = positive(row.get('lot'))
        if not row.get('source') or not lot or not row.get('record_id'):
            continue
        try:
            opened = datetime.fromisoformat(row['open_time'])
        except (KeyError, ValueError, TypeError):
            continue
        # Only within-source order is required. Do not pretend a naive time is UTC.
        bucket = opened.replace(minute=opened.minute // 5 * 5, second=0, microsecond=0)
        sources[row['source']][bucket].append((opened, row['record_id'], lot))
    profiles = {}
    for buckets in sources.values():
        past: deque = deque(maxlen=20)
        for bucket, entries in sorted(buckets.items()):
            days = len({stamp.date() for stamp, _ in past})
            ready = len(past) >= 10 and days >= 3
            baseline = median([lot for _, lot in past]) if ready else None
            profile = dict(typical_lot=str(baseline) if baseline is not None else None,
                           status='READY' if ready else 'INSUFFICIENT_HISTORY',
                           count=len(past), days=days, window=20,
                           basis='source_prior_completed_5m_batches',
                           cutoff_local=bucket.isoformat(), timezone_status='UNKNOWN')
            for _, ident, _ in entries:
                profiles[ident] = dict(profile)
            earliest = min(t for t, _, _ in entries)
            batch_lot = median([lot for t, _, lot in entries if t == earliest])
            past.append((bucket, batch_lot))
    return profiles


def compare(case: dict, lot: D, action: str, prior_count: int,
            prior_lot: D, signed_distance: D | None, typical_lot: D | None) -> dict | None:
    """Hard guards plus weighted distance; missing ADD dimensions cost 1."""
    candidate_lot = positive(case.get('lot'))
    if candidate_lot is None:
        return None
    basis = 'relative_lot' if typical_lot is not None else 'absolute_lot'
    profile = case.get('size_profile') or {}
    reference = positive(profile.get('typical_lot')) if profile.get('status') == 'READY' else None
    if typical_lot is not None and reference is None:
        return None
    query_size = lot / typical_lot if typical_lot is not None else lot
    case_size = candidate_lot / reference if typical_lot is not None else candidate_lot
    components, missing = [], []
    reasons = ['買賣方向相同', '同為可見首筆' if action == 'FIRST' else '同為同向加倉']
    differences = ['盤面與時區尚未核實，未比較K線型態']
    if basis == 'absolute_lot':
        differences.append('未使用平常手數基準；僅比較絕對手數，不能推論相同風險承受度')
    else:
        differences.append('平常手數按各自來源過往紀錄估計；來源不等於已核實帳戶')

    def add(name: str, label: str, query: D | None, value: D | None,
            weight: float, distance: float | None) -> None:
        absent = distance is None
        if absent:
            missing.append(name)
            differences.append(f'{label}資料不足；已保留缺值懲罰')
        else:
            text = f'{label}：本次 {query:.3f}／案例 {value:.3f}'
            (reasons if distance <= .25 else differences).append(text)
        components.append(dict(feature=name, label=label,
                               query=str(query) if query is not None else None,
                               case=str(value) if value is not None else None,
                               weight=weight, distance=round(distance if distance is not None else 1, 6),
                               missing=absent))

    def ratio_gap(query: D, value: D) -> float:
        # Hard guard first; only convert a bounded, dimensionless ratio to float.
        if value > query * 2 or value * 2 < query:
            return 2
        return abs(math.log2(float(value / query)))

    gap = ratio_gap(query_size, case_size)
    if gap > 1 + 1e-12:  # Never compensate >2x size with other close dimensions.
        return None
    add('lot', '相對平常手數倍數' if reference and typical_lot else '下單手數',
        query_size, case_size, 1 if action == 'FIRST' else .35, gap)
    if action == 'ADD':
        count = case.get('prior_count')
        count_gap = min(abs(int(count) - prior_count) / max(prior_count, int(count), 1), 1) if count is not None else None
        add('prior_count','既有同向單數',D(prior_count),D(count) if count is not None else None,.2,count_gap)
        case_prior = positive(case.get('prior_lot'))
        query_exposure = lot / prior_lot if prior_lot > 0 else None
        case_exposure = candidate_lot / case_prior if case_prior else None
        exposure_gap = ratio_gap(query_exposure, case_exposure) if query_exposure and case_exposure else None
        if exposure_gap is not None and exposure_gap > 1 + 1e-12:
            return None
        add('exposure_ratio','加單占既有部位倍數',query_exposure,case_exposure,.25,exposure_gap)
        try:
            candidate_signed = D(str(case['signed_distance'])) if case.get('signed_distance') is not None else None
            if candidate_signed is not None and not candidate_signed.is_finite(): candidate_signed = None
        except InvalidOperation:
            candidate_signed = None
        signed_gap = None
        if signed_distance is not None and candidate_signed is not None:
            if abs(signed_distance) > D('.02') and abs(candidate_signed) > D('.02') and signed_distance * candidate_signed < 0:
                return None
            signed_gap = float(abs(candidate_signed - signed_distance) / D('.5'))
            if signed_gap > 1: return None
        add('signed_distance','方向調整後距均價百分比',signed_distance,candidate_signed,.2,signed_gap)
    distance = sum(c['weight'] * c['distance'] for c in components)
    if distance > MAX_DISTANCE: return None
    return dict(distance=round(distance,6), comparison_basis=basis, components=components,
                missing_features=missing, match_reasons=reasons, differences=differences)


def summarize(ranked: list[dict], basis: str, excluded: int = 0, *, market_context: dict | None = None,
              source: str = 'trader_history', parameters_validated: bool = False) -> dict:
    known = [c for c in ranked if c.get('profit') is not None]
    profit = [c for c in known if D(c['profit']) > 0]
    loss = [c for c in known if D(c['profit']) < 0]
    chosen = {c['id'] for c in profit[:3] + loss[:3]}
    for c in ranked:
        if len(chosen) >= 6: break
        chosen.add(c['id'])
    reasons = []
    if source=='synthetic_demo':reasons.append('合成資料僅供流程展示，不是真實交易證據')
    if any(c.get('independence_status')!='confirmed' for c in ranked):
        reasons.append('來源／帳戶獨立性尚未核實，候選群不等於獨立交易')
    if not parameters_validated:reasons.append('相似度權重與門檻尚未完成相關性驗證，不能宣稱準確率')
    if len(ranked) < 30: reasons.append('相似候選群少於30，統計描述有限')
    if basis == 'absolute_lot': reasons.append('未比較相對平常手數；不同來源資金規模未確認')
    if not market_context or market_context.get('mode')!='market_and_operation': reasons.append('尚無可用盤面比較證據，只能參考操作條件')
    if any(c.get('action')=='FIRST' for c in ranked) and (not market_context or market_context.get('mode')!='market_and_operation'):
        reasons.append('首筆僅以方向、可見首筆與手數比較，辨識力有限')
    if any(c.get('missing_features') for c in ranked): reasons.append('部分加倉條件缺漏')
    if len(known) != len(ranked): reasons.append('部分歷史結果未知')
    status = 'insufficient' if len(ranked) < 5 else 'limited' if reasons else 'usable'
    return dict(total=len(ranked),wins=len(profit),losses=len(loss),flat=len(known)-len(profit)-len(loss),unknown=len(ranked)-len(known),
                win_rate=str((D(len(profit))/len(known)*100).quantize(D('.1'))) if known else None,
                cases=[c for c in ranked if c['id'] in chosen], profit_cases=profit[:6],loss_cases=loss[:6],
                comparison=dict(method=METHOD,basis=basis,max_distance=MAX_DISTANCE,excluded_missing_profile=excluded,
                                 market_features_enabled=bool(market_context and market_context.get('mode')=='market_and_operation'),
                                 parameters_validated=parameters_validated,**(market_context or {})),
                sufficiency=dict(status=status,label={'usable':'可參考','limited':'有限參考','insufficient':'資料不足'}[status],
                                 reasons=reasons,matched_groups=len(ranked),is_success_probability=False))
