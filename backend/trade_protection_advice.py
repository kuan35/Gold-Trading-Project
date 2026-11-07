"""Price levels for a prospective entry, using only the frozen signal."""
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR


def protection_advice(signal, *, entry, digits, recent_low=None, recent_high=None):
    unavailable = dict(status='UNAVAILABLE', entry=None, stop=None, target=None,
                       reward_risk_ratio=None, stop_basis=None, target_basis=None)
    kind, side = signal.get('kind'), signal.get('side')
    if kind not in ('ABOVE', 'BELOW', 'LOWER_RECLAIM', 'UPPER_RECLAIM') or side not in ('BUY', 'SELL'):
        return dict(unavailable, reason='等已收五分 K 出現該方向的突破或收回訊號，再試算建議價位。')
    try:
        high, low, buffer = (Decimal(signal[k]) for k in ('high', 'low', 'buffer'))
        price = Decimal(str(entry))
        if not all(v.is_finite() and v > 0 for v in (price, high, low, buffer)) or high <= low:
            raise ValueError()
        if type(digits) is not int or not 0 <= digits <= 8:
            raise ValueError()
        step = Decimal(1).scaleb(-digits)
        if price != price.quantize(step):
            raise ValueError()
        if kind == 'ABOVE':
            stop, target = high-buffer, high+(high-low)
            stop_basis, target_basis = '突破上緣下方留一段緩衝', '從突破上緣向上推算一個原區間高度'
        elif kind == 'BELOW':
            stop, target = low+buffer, low-(high-low)
            stop_basis, target_basis = '跌破下緣上方留一段緩衝', '從跌破下緣向下推算一個原區間高度'
        elif kind == 'LOWER_RECLAIM':
            stop, target = Decimal(str(recent_low))-buffer, high
            stop_basis, target_basis = '最近六根已收棒的低點下方留一段緩衝', '原區間上緣'
        else:
            stop, target = Decimal(str(recent_high))+buffer, low
            stop_basis, target_basis = '最近六根已收棒的高點上方留一段緩衝', '原區間下緣'
        rounding = ROUND_FLOOR if side == 'BUY' else ROUND_CEILING
        stop, target = (v.quantize(step, rounding=rounding) for v in (stop, target))
        sign = 1 if side == 'BUY' else -1
        risk, reward = (price-stop)*sign, (target-price)*sign
        if min(stop, target, risk, reward) <= 0:
            return dict(unavailable, reason='進場基準已越過結構停損或目標，等價位回到有效區間再試算。')
    except (KeyError, ValueError, TypeError, ArithmeticError):
        return dict(unavailable, reason='進場價、商品價格級距或盤面區間資料不足。')
    return dict(status='AVAILABLE', entry=format(price.quantize(step), 'f'), stop=format(stop, 'f'),
                target=format(target, 'f'), reward_risk_ratio=format(reward/risk, '.2f'),
                stop_basis=stop_basis, target_basis=target_basis, reason=None)
