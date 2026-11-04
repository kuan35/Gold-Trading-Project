"""Read-only nominal gold risk calculations; no order or model authority.

Account exposure lists are the existing broker adapter's XAUUSD-only lists.
Risk is additional adverse movement from executable prices, not entry PnL.
"""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR

from .broker_orders import _price, _volume, _positive_int
from .engine import DomainError, amount
from .ticket_preview import ticket_preview
from .market_clock import SOURCE_CLOCK_SKEW_SECONDS


D = Decimal
ERRORS = (DomainError, KeyError, TypeError, ValueError, ArithmeticError)
SCOPE = ('僅計黃金部位、待成交開倉單與本筆至停損的額外名目USD風險；'
         '不是帳戶所有商品風險或損失上限，不多空互抵，未計費用、滑價與跳空。')


def _clock(now):
    return datetime.now(timezone.utc).timestamp() if now is None else now


def _fresh(stamp, clock, seconds, future=0):
    try:
        parsed = datetime.fromisoformat(stamp)
        return parsed.tzinfo is not None and -future <= clock - parsed.timestamp() <= seconds
    except (TypeError, ValueError, OverflowError):
        return False


def _quote(snapshot, clock):
    quote = snapshot.get('quote') or {}
    try:
        if (snapshot.get('environment') != 'demo' or quote.get('status') != 'CURRENT'
                or not _fresh(quote.get('source_time_utc'), clock, 5,SOURCE_CLOCK_SKEW_SECONDS)
                or not 0 <= quote['age_seconds'] <= 5):
            return None
        bid, ask = amount(quote.get('bid'), 'Bid'), amount(quote.get('ask'), 'Ask')
        return (bid, ask) if bid <= ask else None
    except ERRORS:
        return None


def _equity(account, clock):
    try:
        if (account.get('status') != 'CURRENT' or account.get('pnl_status') != 'CURRENT'
                or account.get('currency') != 'USD'
                or not _fresh(account.get('updated_at_utc'), clock, 10)
                or not _fresh(account.get('pnl_updated_at_utc'), clock, 10)):
            return None
        return amount(account.get('equity'), '帳戶淨值')
    except ERRORS:
        return None


def _usd(value):
    """At least cents, retaining sub-cent precision rather than rounding budgets."""
    cents = value.quantize(D('.01'))
    return format(cents if cents == value else value, 'f')


def _pct(value, equity):
    return format(value / equity * 100, '.4f') if value is not None and equity else None


def _exposure(account, key, quote, clock):
    rows = account.get(key)
    if not isinstance(rows, list):
        return None, []
    total, unknown = D(0), []
    available = account.get('status') == 'CURRENT' and _fresh(account.get('updated_at_utc'), clock, 10)
    for row in rows:
        if key == 'pending_orders' and isinstance(row, dict) and row.get('intent') == 'CLOSE':
            continue  # A pending close has not reduced the existing position.
        try:
            if not available or not isinstance(row, dict):
                raise ValueError()
            side = row.get('side')
            if side not in ('BUY', 'SELL'):
                raise ValueError()
            if key == 'positions':
                if quote is None:
                    raise ValueError()
                reference = quote[0] if side == 'BUY' else quote[1]
            else:
                if row.get('intent') != 'OPEN':
                    raise ValueError()
                reference = amount(row.get('limit_price'), '掛單進場價')
            stop = amount(row.get('sl'), '停損')
            delta = (reference - stop) * (D(1) if side == 'BUY' else D(-1))
            if delta <= 0:
                raise ValueError()
            total += delta * amount(row.get('volume_units'), '數量')
        except ERRORS:
            unknown.append(str(row.get('id', 'UNKNOWN')) if isinstance(row, dict) else 'UNKNOWN')
    if not available:
        return None, sorted(unknown)
    return (None if unknown else total), sorted(unknown)


def risk_summary(snapshot, draft, preview, *, now=None):
    clock = _clock(now)
    account = snapshot.get('account') or {}
    equity = _equity(account, clock)
    quote = _quote(snapshot, clock)
    positions, unknown_positions = _exposure(account, 'positions', quote, clock)
    pending, unknown_orders = _exposure(account, 'pending_orders', quote, clock)
    stop_risk = ratio = None
    try:
        if preview.get('status') != 'AVAILABLE' or quote is None:
            raise ValueError()
        sl = preview.get('sl') or {}
        if sl.get('status') != 'AVAILABLE' or draft.get('side') not in ('BUY', 'SELL'):
            raise ValueError()
        entry = amount(preview.get('entry_price'), '擬進場價')
        quantity = amount(preview.get('quantity_oz'), '數量')
        sign = D(1) if draft['side'] == 'BUY' else D(-1)
        distance = (entry - amount(sl.get('price'), '停損')) * sign
        if distance <= 0:
            raise ValueError()
        stop_risk = distance * quantity
        tp = preview.get('tp') or {}
        if tp.get('status') == 'AVAILABLE':
            reward = (amount(tp.get('price'), '停利') - entry) * sign * quantity
            if reward > 0:
                ratio = format(reward / stop_risk, '.4f')
    except ERRORS:
        pass
    total = stop_risk + positions + pending if all(v is not None for v in (stop_risk, positions, pending)) else None
    status = 'AVAILABLE' if total is not None else 'UNKNOWN'
    reason = None
    if total is None:
        reason = '停損、行情或持倉／掛單資料不足；黃金合計風險未知，不能當作零。'
    elif equity is None:
        reason = 'USD正淨值或帳戶／PnL的10秒有效資料不足，暫不計淨值比例。'
    return dict(status=status, reason=reason, stop_loss_usd=_usd(stop_risk) if stop_risk is not None else None,
        stop_equity_pct=_pct(stop_risk, equity), reward_risk_ratio=ratio,
        existing_positions_risk_usd=_usd(positions) if positions is not None else None,
        pending_orders_risk_usd=_usd(pending) if pending is not None else None,
        gold_total_risk_usd=_usd(total) if total is not None else None,
        gold_total_equity_pct=_pct(total, equity), unprotected_positions=unknown_positions,
        unprotected_orders=unknown_orders, scope=SCOPE)


def size_for_risk(snapshot, draft, *, risk_usd=None, equity_pct=None, now=None):
    result = dict(status='UNAVAILABLE', reason='請選擇一種有效風險預算，並填妥方向、進場與停損。',
                  lot=None, actual_risk_usd=None, budget_usd=None, stop_equity_pct=None)
    clock = _clock(now)
    equity = _equity(snapshot.get('account') or {}, clock)
    try:
        if (risk_usd is None) == (equity_pct is None):
            return result
        if equity_pct is not None:
            if equity is None:
                return dict(result, reason='淨值反算需要USD正淨值與10秒內有效帳戶／PnL。')
            budget = equity * amount(equity_pct, '風險比例') / 100
        else:
            budget = amount(risk_usd, '風險USD')
        result['budget_usd'] = _usd(budget)
        symbol = snapshot.get('symbol') or {}
        lot_cents = _positive_int(symbol.get('lot_size_cents'), '合約大小')
        minimum = _positive_int(symbol.get('min_volume_cents'), '最小手數')
        maximum = _positive_int(symbol.get('max_volume_cents'), '最大手數')
        step = _positive_int(symbol.get('step_volume_cents'), '手數級距')
        digits = symbol.get('digits')
        if type(digits) is not int or not 0 <= digits <= 8 or maximum < minimum:
            return result
        # The current lot may be blank/invalid: validate with a valid minimum lot.
        checked = dict(draft, lot=format(D(minimum) / lot_cents, 'f'))
        preview = ticket_preview(snapshot, checked, now=clock)
        quote = _quote(snapshot, clock)
        if preview.get('status') != 'AVAILABLE' or quote is None or (preview.get('sl') or {}).get('status') != 'AVAILABLE':
            return dict(result, reason='報價、商品規格或停損無效，暫不反算手數。')
        entry = amount(preview['entry_price'], '擬進場價')
        stop = _price(draft.get('sl'), '停損', digits)
        distance = (entry - stop) * (D(1) if draft['side'] == 'BUY' else D(-1))
        if distance <= 0:
            return result
        # volume is in hundredths of an ounce; apply broker's minimum-offset lattice.
        ceiling = min(budget * 100 / distance, D(maximum), D(100) * lot_cents)
        if ceiling < minimum:
            return dict(result, reason='預算低於券商最小手數所需風險，未強補最小手數。')
        volume = D(minimum) + ((ceiling - minimum) / step).to_integral_value(rounding=ROUND_FLOOR) * step
        lot = volume / lot_cents
        _volume(lot, symbol)
        actual = distance * volume / 100
        if actual > budget or lot > 100:
            return result
        return dict(result, status='AVAILABLE', reason=None, lot=format(lot, 'f'),
                    actual_risk_usd=_usd(actual), stop_equity_pct=_pct(actual, equity))
    except ERRORS:
        return result
