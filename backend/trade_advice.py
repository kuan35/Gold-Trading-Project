"""Deterministic pre-trade advice from frozen market evidence."""
from decimal import Decimal
from statistics import median

from .compact_market import distinct_rows
from .context_rules import market_features
from .forward_outcomes import _measure
from .trade_result import text, trade_result

SIDES = ('BUY', 'SELL')
MIN_SAMPLES = 10
SIGNALS = {
    'ABOVE': ('BUY', '向上突破'),
    'BELOW': ('SELL', '向下跌破'),
    'LOWER_RECLAIM': ('BUY', '跌破後收回'),
    'UPPER_RECLAIM': ('SELL', '突破後回落'),
}
SIDE_LABEL = {'BUY': '做多', 'SELL': '做空'}
ERRORS = (ArithmeticError, KeyError, TypeError, ValueError)


def signal_for_query(query):
    try:
        frame = market_features(query)
        kind = frame['event']
    except ERRORS:
        return dict(kind=None, side=None, label=None, high=None, low=None, buffer=None)
    side, label = SIGNALS.get(kind, (None, '區間訊號尚未明確'))
    return dict(kind=kind, side=side, label=label, high=frame.get('reference_high'),
                low=frame.get('reference_low'), buffer=frame.get('reference_buffer'))


def valid_costs(costs):
    try:
        baseline, stress = (Decimal(costs[k]) for k in ('baseline_usd_per_oz', 'stress_usd_per_oz'))
        if all(v.is_finite() for v in (baseline, stress)) and 0 <= baseline < stress <= 1000:
            return baseline, stress
    except ERRORS:
        pass
    return None


def measure_pair(outcome, costs):
    """Use one validated OHLC path and symmetric round-trip cost for both sides."""
    rates = valid_costs(costs)
    if rates is None:
        return None
    try:
        anchor = outcome['anchor_time']
        horizon = outcome['horizons']['30']
        if horizon['status'] != 'AVAILABLE' or horizon['end_time'] != anchor + 1800:
            return None
        bars = horizon['bars']
        result = {}
        for side in SIDES:
            measured = _measure(side, anchor, bars, 30)
            if measured['status'] != 'AVAILABLE':
                return None
            entry = Decimal(bars[0]['open'])
            gross = Decimal(measured['change_pct'])
            result[side] = dict(baseline_pct=gross-rates[0]/entry*100,
                                stress_pct=gross-rates[1]/entry*100,
                                mae_pct=Decimal(measured['mae_pct']))
        return result
    except ERRORS:
        return None


def scenario_result(bars, draft):
    try:
        side = draft['side']
        entry, stop, target = (Decimal(draft[k]) for k in ('entry', 'sl', 'tp'))
        if side not in SIDES or not all(v.is_finite() and v > 0 for v in (entry, stop, target)):
            return 'unknown'
        buy = side == 'BUY'
        if not (stop < entry < target if buy else target < entry < stop):
            return 'unknown'
        anchor = Decimal(bars[0]['open'])
        stop, target = anchor*stop/entry, anchor*target/entry
        for bar in bars:
            open_, high, low = (Decimal(bar[k]) for k in ('open', 'high', 'low'))
            if (open_ <= stop if buy else open_ >= stop):
                return 'stop'
            if (open_ >= target if buy else open_ <= target):
                return 'target'
            hit_stop = low <= stop if buy else high >= stop
            hit_target = high >= target if buy else low <= target
            if hit_stop and hit_target:
                return 'ambiguous'
            if hit_stop:
                return 'stop'
            if hit_target:
                return 'target'
        return 'expired'
    except (*ERRORS, IndexError):
        return 'unknown'


def _original(rows, index, side):
    available = []
    for row in rows:
        case = index.lookup[row['case_id']]
        if case['side'] != side:
            continue
        result = trade_result(case)
        if result['status'] == 'AVAILABLE':
            available.append(dict(row, pct=Decimal(result['price_return_pct'])))
    distinct = distinct_rows(available, index.descriptions, top_k=None) if available else []
    values = [r['pct'] for r in distinct]
    return dict(count=len(values), median_pct=text(median(values)) if values else None,
                positive=sum(v > 0 for v in values), negative=sum(v < 0 for v in values))


def _simulation(pairs, side):
    other = 'SELL' if side == 'BUY' else 'BUY'
    values = [pair[side]['baseline_pct'] for pair in pairs]
    stress = [pair[side]['stress_pct'] for pair in pairs]
    return dict(median_pct=text(median(values)) if values else None,
                stress_median_pct=text(median(stress)) if stress else None,
                positive=sum(v > 0 for v in values),
                better=sum(pair[side]['baseline_pct'] > pair[other]['baseline_pct'] for pair in pairs))


def _wait_condition(signal, side):
    if signal.get('side') and signal['side'] == side:
        return f'已出現{signal["label"]}，等下一根五分 K 收盤後重新比對。'
    high, low, buffer = (signal.get(k) for k in ('high', 'low', 'buffer'))
    if all(v is not None for v in (high, low, buffer)):
        if side == 'BUY':
            return f'等五分 K 收回區間，或收在向上突破門檻 {Decimal(high)+Decimal(buffer):.2f} 之上。'
        if side == 'SELL':
            return f'等五分 K 回落到區間，或收在向下跌破門檻 {Decimal(low)-Decimal(buffer):.2f} 之下。'
    return '等下一根五分 K 收盤，再重新確認訊號與案例。'


def trade_advice(index, query, forward_store, costs, *, side=None, draft=None, risk=None, exclude_group=None):
    signal = signal_for_query(query)
    as_of = query.get('as_of')
    rates = valid_costs(costs)
    normalized = dict(zip(('baseline_usd_per_oz', 'stress_usd_per_oz'), map(text, rates))) if rates else None
    rows = []
    if index is not None and type(as_of) is int:
        try:
            rows = index.rank_for_advice(query, exclude_group)
        except ERRORS:
            pass
    original = {s: _original(rows, index, s) for s in SIDES}
    complete = []
    if forward_store is not None and (rates is not None or draft is not None):
        for row in rows:
            outcome = forward_store.get(row['case_id'], as_of)
            horizon = outcome.get('horizons', {}).get('30') or {}
            end = horizon.get('end_time')
            if type(end) is not int or end > as_of:
                continue
            pair = measure_pair(outcome, normalized) if rates is not None else None
            if pair is not None or (rates is None and horizon.get('status') == 'AVAILABLE'):
                complete.append(dict(row, pair=pair, bars=horizon['bars']))
    unique = distinct_rows(complete, index.descriptions, top_k=None) if complete else []
    pairs = [row['pair'] for row in unique if row['pair'] is not None]
    simulations = dict(count=len(pairs), **{s: _simulation(pairs, s) for s in SIDES})
    draft_result = None
    if draft is not None or risk is not None:
        risk = risk or {}
        scenario = None
        if draft is not None:
            scenario = dict.fromkeys(('stop', 'target', 'ambiguous', 'expired', 'unknown'), 0)
            for row in unique:
                scenario[scenario_result(row['bars'], draft)] += 1
        draft_result = dict(**{k: risk.get(k) for k in ('stop_loss_usd', 'equity_pct', 'budget_usd', 'suggested_lot')},
                            scenario=scenario)
    result = dict(action='WAIT', side=side or signal['side'], signal=signal['label'],
                  signal_code=signal['kind'], as_of=as_of, original=original, simulations=simulations,
                  costs=normalized, draft=draft_result)

    def wait(code, reason):
        return dict(result, headline='建議先等待', reason_code=code, reason=reason)

    if rates is None:
        return wait('COST_UNAVAILABLE', '尚未設定有效的基準與較高交易成本。')
    if signal['kind'] is None:
        return wait('SIGNAL_UNAVAILABLE', '缺少有效的已收盤面，等行情更新再檢查。')
    if len(pairs) < MIN_SAMPLES:
        return wait('INSUFFICIENT_PAIRS', f'有 {len(pairs)} 組完整配對，方向建議需至少 {MIN_SAMPLES} 組。'
                    + _wait_condition(signal, side or signal['side']))
    supported = next((s for s in SIDES if Decimal(simulations[s]['median_pct']) > 0
                      and simulations[s]['better']*2 > len(pairs)), None)
    if supported is None:
        return wait('NO_HISTORICAL_EDGE', '目前的配對結果未形成扣成本後的方向優勢。')
    if side is not None and side != supported:
        return wait('OTHER_SIDE_SUPPORTED', f'歷史試算較支持{SIDE_LABEL[supported]}，建議暫緩這筆{SIDE_LABEL[side]}草稿。')
    result['side'] = supported
    if Decimal(simulations[supported]['stress_median_pct']) <= 0:
        return wait('STRESS_COST', f'基準成本下偏向{SIDE_LABEL[supported]}，較高成本下中位數已降至零或負值。')
    if signal['side'] != supported:
        return wait('SIGNAL_NOT_CONFIRMED', f'歷史試算偏向{SIDE_LABEL[supported]}，' + _wait_condition(signal, supported))
    observed = original[supported]
    if (observed['count'] >= MIN_SAMPLES and Decimal(observed['median_pct']) < 0
            and observed['negative']*2 > observed['count']):
        return wait('ORIGINAL_CONFLICT', f'30 分鐘試算偏向{SIDE_LABEL[supported]}，但相似交易員原單多數虧損。')
    if side == supported and risk and risk.get('over_budget'):
        lot = risk.get('suggested_lot')
        bias = '偏多' if supported == 'BUY' else '偏空'
        return dict(result, action='ADJUST', headline=f'盤面{bias}，建議先調整手數',
                    reason_code='RISK_BUDGET', reason=f'停損損失超過預算。建議手數 {lot}，調整後重新檢查。'
                    if lot else '停損損失超過預算，請調整草稿後重新檢查。')
    return dict(result, action=supported, headline=f'可以考慮{SIDE_LABEL[supported]}',
                reason_code='SUPPORTED', reason=f'已收五分 K 出現{signal["label"]}，同盤面試算在兩組成本下均支持此方向。')
