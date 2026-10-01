"""Account state visible strictly before each order is placed."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from .account_state import TradeForAccountState, XAUUSD_CONTRACT_SIZE


ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class PreActionAccountState:
    record_id: str
    open_buy_count_before: int
    open_sell_count_before: int
    open_buy_lot_before: Decimal
    open_sell_lot_before: Decimal
    total_open_lot_before: Decimal
    net_lot_before: Decimal
    unrealized_pnl_before_usd: Decimal | None
    reference_price_utc: datetime | None


def _pnl(position: TradeForAccountState, reference_price: Decimal) -> Decimal:
    sign = Decimal("1") if position.side == "BUY" else Decimal("-1")
    return (reference_price - position.open_price) * sign * position.lot * XAUUSD_CONTRACT_SIZE


def compute_pre_action_states(
    trades: list[TradeForAccountState],
    *,
    reference_prices: dict[str, tuple[datetime, Decimal]],
) -> list[PreActionAccountState]:
    """Compute state from earlier open positions, excluding the current order."""
    by_account: dict[str, list[TradeForAccountState]] = {}
    for trade in trades:
        by_account.setdefault(trade.account_id, []).append(trade)

    states: dict[str, PreActionAccountState] = {}
    for account_trades in by_account.values():
        for trade in sorted(account_trades, key=lambda item: (item.open_time, item.record_id)):
            open_before = [
                other
                for other in account_trades
                if other.open_time < trade.open_time
                and (other.close_time is None or other.close_time > trade.open_time)
            ]
            buys = [other for other in open_before if other.side == "BUY"]
            sells = [other for other in open_before if other.side == "SELL"]
            buy_lot = sum((other.lot for other in buys), ZERO)
            sell_lot = sum((other.lot for other in sells), ZERO)
            reference = reference_prices.get(trade.record_id)
            unrealized = (
                sum((_pnl(other, reference[1]) for other in open_before), ZERO)
                if reference is not None
                else None
            )
            states[trade.record_id] = PreActionAccountState(
                record_id=trade.record_id,
                open_buy_count_before=len(buys),
                open_sell_count_before=len(sells),
                open_buy_lot_before=buy_lot,
                open_sell_lot_before=sell_lot,
                total_open_lot_before=buy_lot + sell_lot,
                net_lot_before=buy_lot - sell_lot,
                unrealized_pnl_before_usd=unrealized,
                reference_price_utc=reference[0] if reference is not None else None,
            )
    return [states[trade.record_id] for trade in trades]

