"""Pure, display-only account returns and fixed-position equity scenarios.

This module does not place orders or predict stop-out. Account currency, quote
freshness and complete exposure are required; unknown exposure is never omitted.
"""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal

from .market_clock import SOURCE_CLOCK_SKEW_SECONDS


D = Decimal
ERRORS = (TypeError, ValueError, ArithmeticError, OverflowError)
RETURN_BASIS = ('價格報酬率＝方向調整後可平倉價差÷實際進場價×100，未扣費用；'
                '持倉報酬率（券商保證金）＝券商當前淨損益÷同幣別的目前占用保證金×100。'
                '目前占用不等於最初投入，會隨券商保證金及持倉變動；'
                '券商未實現淨損益尚未計潛在平倉佣金，非最終已實現報酬；'
                '預估保證金報酬率＝券商當前淨損益÷（實際進場價×盎司數÷試算槓桿）×100。'
                '僅券商保證金缺值時主欄才退回槓桿估計，非實際占用保證金；未核實商品動態槓桿。')
ZERO_BASIS = ('假設本筆已成交、持倉固定、買賣價差固定，推算帳戶淨值歸零的Bid價格；'
              '忽略其他掛單後續觸發、停損停利、強平、額外佣金、隔夜費與滑價。'
              '這是線性情境估算，不是精確爆倉價或券商強平價；券商可能先強平。')


def _number(raw, *, positive=False):
    if raw is None or isinstance(raw, bool):
        raise ValueError('missing decimal')
    value = D(str(raw))
    if not value.is_finite() or positive and value <= 0:
        raise ValueError('invalid decimal')
    return value


def _text(value):
    return format(value, 'f')


def _clock(now):
    return datetime.now(timezone.utc).timestamp() if now is None else now


def _fresh(stamp, clock, seconds, future=0):
    try:
        value = datetime.fromisoformat(stamp)
        return value.tzinfo is not None and -future <= clock-value.timestamp() <= seconds
    except ERRORS:
        return False


def _gold(snapshot, row=None):
    """Adapter source is evidence because the existing stream filters XAUUSD.

    Explicit non-gold metadata always overrides that source. Unnamed generic
    snapshots require a symbol name rather than guessing from price magnitude.
    """
    symbol = snapshot.get('symbol') or {}
    names = [symbol.get('name'), symbol.get('symbol'), symbol.get('symbol_name')]
    if row is not None:
        names += [row.get('symbol'), row.get('symbol_name')]
    names = [name for name in names if name is not None]
    if any(not isinstance(name, str) or name.upper() not in ('XAUUSD', 'GOLD', 'GOLD#') for name in names):
        return False
    return bool(names) or snapshot.get('source') in ('ctrader_demo_xauusd', 'ctrader_live_xauusd')


def _quote(snapshot, clock):
    quote = snapshot.get('quote') or {}
    try:
        if (not _gold(snapshot) or quote.get('status') != 'CURRENT'
                or not _fresh(quote.get('source_time_utc'), clock, 5, SOURCE_CLOCK_SKEW_SECONDS)
                or not 0 <= _number(quote.get('age_seconds')) <= 5):
            return None
        bid, ask = _number(quote.get('bid'), positive=True), _number(quote.get('ask'), positive=True)
        return (bid, ask) if ask >= bid else None
    except ERRORS:
        return None


def _account_current(account, clock):
    return account.get('status') == 'CURRENT' and _fresh(account.get('updated_at_utc'), clock, 10)


def _pnl_current(account, clock):
    return account.get('pnl_status') == 'CURRENT' and _fresh(account.get('pnl_updated_at_utc'), clock, 10)


def enrich_position_returns(snapshot, leverage='200', now=None):
    """Prefer net PnL/current broker margin in the same deposit currency.

    A missing broker denominator may use a clearly tagged USD leverage estimate.
    Known zero/invalid margin never turns into a primary estimated return.
    """
    result = deepcopy(snapshot)
    account = result.get('account') or {}
    clock = _clock(now)
    quote = _quote(result, clock)
    for row in account.get('positions') or []:
        if not isinstance(row, dict):
            continue
        row.update(price_return_pct=None, estimated_margin_roi_pct=None,
                   margin_roi_pct=None, actual_margin_roi_pct=None, return_currency=None,
                   return_basis=RETURN_BASIS, return_reason=None, margin_return_source='UNAVAILABLE')
        reasons = []
        if not _account_current(account, clock) or not _gold(result, row):
            row['return_reason'] = '商品或10秒內帳戶資料不足。'
            continue
        entry = None
        try:
            if row.get('side') not in ('BUY', 'SELL'):
                raise ValueError()
            entry = _number(row.get('entry'), positive=True)
            sign = D(1) if row['side'] == 'BUY' else D(-1)
            if quote is None:
                raise ValueError()
            executable = quote[0] if sign == 1 else quote[1]
            row['price_return_pct'] = _text((executable-entry)*sign/entry*100)
        except ERRORS:
            reasons.append('持倉方向、實際進場價或5秒內報價不足，價格報酬率未知。')
        net = None
        currency = account.get('currency')
        currency_known = isinstance(currency, str) and bool(currency.strip()) and currency not in ('UNKNOWN', 'UNAVAILABLE')
        try:
            if not currency_known or not _pnl_current(account, clock):
                raise ValueError()
            net = _number(row.get('net_pnl'))
            row['return_currency'] = currency
            if row.get('used_margin_source') != 'BROKER_POSITION':
                raise ValueError()
            used_margin = _number(row.get('used_margin'), positive=True)
            row['actual_margin_roi_pct'] = _text(net/used_margin*100)
            row['margin_roi_pct'] = row['actual_margin_roi_pct']
            row['margin_return_source'] = 'BROKER_POSITION'
        except ERRORS:
            pass
        try:
            if currency != 'USD' or net is None or entry is None or row.get('side') not in ('BUY', 'SELL'):
                raise ValueError()
            ratio = _number(leverage, positive=True)
            if not 1 <= ratio <= 10000:
                raise ValueError()
            quantity = _number(row.get('volume_units'), positive=True)
            row['estimated_margin_roi_pct'] = _text(net/(entry*quantity/ratio)*100)
            if row.get('used_margin') is None:
                row['margin_roi_pct'] = row['estimated_margin_roi_pct']
                row['margin_return_source'] = 'LEVERAGE_ESTIMATE'
        except ERRORS:
            pass
        if row['margin_roi_pct'] is None:
            reasons.append('幣別、10秒內淨損益或有效正券商占用保證金不足；僅缺值時可採USD槓桿估計，持倉報酬率未知。')
        row['return_reason'] = ''.join(reasons) or None
    return result


def equity_zero_scenario(snapshot, draft, preview, now=None):
    """Solve equity(Bid)=0 after hypothetical fill, with a constant spread.

    All numeric output is a decimal string. A hedged/negative-price solution
    does not become a valid zero price. No missing position is dropped.
    """
    result = dict(status='UNAVAILABLE', reason='有效USD帳戶、完整黃金持倉、當前淨值或報價不足，暫不估算。',
        zero_bid_price=None, direction=None, reference_bid_price=None, net_quantity_oz=None,
        equity_at_fill_usd=None, spread_usd=None, basis=ZERO_BASIS,
        source='FIXED_POSITION_LINEAR_SCENARIO', conditional_on_fill=preview.get('conditional_on_fill') is True)
    clock = _clock(now)
    account = snapshot.get('account') or {}
    quote = _quote(snapshot, clock)
    try:
        if (quote is None or account.get('currency') != 'USD' or not _account_current(account, clock)
                or not _pnl_current(account, clock) or preview.get('status') != 'AVAILABLE'
                or draft.get('side') not in ('BUY', 'SELL')):
            return result
        rows = account.get('positions')
        count = account.get('all_positions_count')
        if not isinstance(rows, list) or type(count) is not int or count != len(rows):
            return result
        equity = _number(account.get('equity'), positive=True)
        old_net = D(0)
        for row in rows:
            if not isinstance(row, dict) or not _gold(snapshot, row) or row.get('side') not in ('BUY', 'SELL'):
                return result
            # Reject a partially known row instead of making missing exposure zero.
            _number(row.get('entry'), positive=True)
            _number(row.get('net_pnl'))
            quantity = _number(row.get('volume_units'), positive=True)
            old_net += quantity if row['side'] == 'BUY' else -quantity
        bid, ask = quote
        spread = ask-bid
        entry = _number(preview.get('entry_price'), positive=True)
        quantity = _number(preview.get('quantity_oz'), positive=True)
        reference = entry-spread if draft['side'] == 'BUY' else entry
        if reference <= 0:
            return result
        equity_fill = equity + old_net*(reference-bid) - spread*quantity
        if equity_fill <= 0:
            return dict(result, reason='假設成交時淨值已不為正，沒有可解釋的成交後歸零價。')
        net = old_net + (quantity if draft['side'] == 'BUY' else -quantity)
        result.update(reference_bid_price=_text(reference), net_quantity_oz=_text(net),
                      equity_at_fill_usd=_text(equity_fill), spread_usd=_text(spread))
        if not net:
            return dict(result, status='NET_HEDGED', reason='固定價差與持倉假設下淨數量為零，沒有隨金價移動的有限歸零價。')
        result['direction'] = 'DOWN' if net > 0 else 'UP'
        zero = reference-equity_fill/net
        if zero <= 0:
            return dict(result, status='NO_POSITIVE_ZERO_PRICE', reason='此固定持倉線性情境沒有正數金價的淨值歸零解。')
        return dict(result, status='AVAILABLE', reason=None, zero_bid_price=_text(zero))
    except ERRORS:
        return result
