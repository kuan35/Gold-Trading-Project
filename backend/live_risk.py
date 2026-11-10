"""Fail-closed, decimal LIVE entry limits. This module never sends an order."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .engine import DomainError


def _positive(raw, label: str) -> Decimal:
    try:
        if raw is None or isinstance(raw, bool):
            raise ValueError()
        value = Decimal(str(raw))
        if not value.is_finite() or value <= 0:
            raise ValueError()
        return value
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise DomainError(f'請先在本機設定有效的{label}上限', 503) from exc


@dataclass(frozen=True)
class LiveLimits:
    max_order_stop_loss_usd: Decimal
    max_gross_gold_lots: Decimal

    def __init__(self, max_order_stop_loss_usd, max_gross_gold_lots):
        object.__setattr__(self, 'max_order_stop_loss_usd', _positive(max_order_stop_loss_usd, '單筆停損'))
        object.__setattr__(self, 'max_gross_gold_lots', _positive(max_gross_gold_lots, '黃金總手數'))


def check_live_open(snapshot: dict, draft: dict, limits: LiveLimits, expected_margin: dict | None) -> dict:
    """Validate one account-bound LIVE entry against source facts and local caps."""
    if (snapshot.get('environment') != 'live' or snapshot.get('source') != 'ctrader_live_xauusd'
            or snapshot.get('token_scope') != 'TRADE' or not snapshot.get('order_connection')):
        raise DomainError('LIVE 交易連線或權限尚未就緒', 503)
    quote, account, symbol = (snapshot.get(name) or {} for name in ('quote', 'account', 'symbol'))
    try:
        age = Decimal(str(quote.get('age_seconds')))
        fresh_quote = age.is_finite() and 0 <= age <= 5
    except (InvalidOperation, TypeError, ValueError):
        fresh_quote = False
    if (quote.get('status') != 'CURRENT' or not fresh_quote
            or account.get('status') != 'CURRENT' or not symbol):
        raise DomainError('LIVE 報價、帳戶或商品規格尚未就緒', 503)
    if draft.get('environment') != 'live' or not account.get('account_key') or draft.get('account_key') != account['account_key']:
        raise DomainError('LIVE 草稿與目前帳戶不一致', 409)
    if account.get('currency') != 'USD':
        raise DomainError('LIVE 帳戶不是 USD，尚未取得可靠換匯資料', 503)
    positions, pending = account.get('positions'), account.get('pending_orders')
    if (not isinstance(positions, list) or not isinstance(pending, list)
            or account.get('all_positions_count') != len(positions)
            or account.get('all_pending_orders_count') != len(pending)):
        raise DomainError('LIVE 完整持倉或待成交資料不足', 503)
    if draft.get('sl') in (None, '', '0'):
        raise DomainError('LIVE 新增委託必須設定停損', 422)
    try:
        lot_size_cents = int(symbol['lot_size_cents'])
        volume_cents = int(draft['volume_cents'])
        if lot_size_cents <= 0 or volume_cents <= 0 or draft.get('lot_size_cents') != lot_size_cents:
            raise ValueError()
        lot = Decimal(volume_cents) / lot_size_cents
        old_volume = sum((Decimal(str(row['volume_units'])) for row in positions + pending), Decimal(0))
        if old_volume < 0 or not old_volume.is_finite():
            raise ValueError()
        gross_after = old_volume * 100 / lot_size_cents + lot
        entry, stop = Decimal(str(draft['price'])), Decimal(str(draft['sl']))
        if not entry.is_finite() or not stop.is_finite() or entry <= 0 or stop <= 0:
            raise ValueError()
        direction = 1 if draft.get('side') == 'BUY' else -1 if draft.get('side') == 'SELL' else 0
        if not direction or (entry - stop) * direction <= 0:
            raise ValueError()
        stop_loss = (entry - stop) * direction * volume_cents / 100
        equity = Decimal(str(account['equity']))
    except (KeyError, InvalidOperation, TypeError, ValueError, ArithmeticError) as exc:
        raise DomainError('LIVE 風險計算資料不足', 503) from exc
    if not equity.is_finite() or equity <= 0:
        raise DomainError('LIVE 帳戶淨值不足', 409)
    if gross_after > limits.max_gross_gold_lots:
        raise DomainError('LIVE 黃金持倉加待成交總手數超過本機上限', 409)
    if stop_loss > limits.max_order_stop_loss_usd:
        raise DomainError('LIVE 單筆停損情境損失超過本機上限', 409)
    try:
        if expected_margin is None or expected_margin.get('status') != 'AVAILABLE' or expected_margin.get('currency') != 'USD':
            raise ValueError()
        margin = Decimal(str(expected_margin['buy' if direction == 1 else 'sell']))
        if not margin.is_finite() or margin <= 0:
            raise ValueError()
    except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
        raise DomainError('LIVE 券商預估保證金尚未就緒', 503) from exc
    if equity < margin:
        raise DomainError('LIVE 帳戶淨值低於券商預估保證金', 409)
    return {'stop_loss_usd': f'{stop_loss:.2f}', 'gross_after_lot': f'{gross_after:.2f}',
            'broker_margin_usd': f'{margin:.2f}', 'equity_usd': format(equity, 'f')}
