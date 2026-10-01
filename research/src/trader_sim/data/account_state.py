"""Point-in-time account position state: cumulative same-direction lot, add count,
and an approximate unrealized P&L, computed from the account's own prior trades only.

Nothing here looks at a trade's own outcome or any trade opened after it - only
trades already open at the moment a given trade was placed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


ZERO = Decimal("0")
XAUUSD_CONTRACT_SIZE = Decimal("100")  # 100 oz/lot, standard XAU/USD convention


@dataclass(frozen=True, slots=True)
class TradeForAccountState:
    record_id: str
    account_id: str
    side: str  # "BUY" or "SELL"
    lot: Decimal
    open_price: Decimal
    open_time: datetime
    close_time: datetime | None
    trading_day_utc: date


@dataclass(frozen=True, slots=True)
class AccountStateFeature:
    record_id: str
    cumulative_same_direction_lot: Decimal
    add_count_same_direction: int
    unrealized_pnl_estimate_usd: Decimal | None  # None if no prior-day close is available yet


def _direction_sign(side: str) -> Decimal:
    return Decimal("1") if side == "BUY" else Decimal("-1")


def compute_account_state_features(
    trades: list[TradeForAccountState],
    *,
    prior_close_by_date: dict[date, Decimal],
) -> list[AccountStateFeature]:
    """One feature row per trade, in the same order as ``trades``.

    ``prior_close_by_date`` maps a UTC trading day to that day's close - used to find
    the most recent close STRICTLY BEFORE a trade's own trading day (point-in-time:
    a trade placed "today" cannot know today's own close yet).
    """
    sorted_dates = sorted(prior_close_by_date)

    def _most_recent_close_before(day: date) -> Decimal | None:
        candidates = [d for d in sorted_dates if d < day]
        return prior_close_by_date[max(candidates)] if candidates else None

    by_account: dict[str, list[TradeForAccountState]] = {}
    for trade in trades:
        by_account.setdefault(trade.account_id, []).append(trade)

    results_by_record_id: dict[str, AccountStateFeature] = {}
    for account_trades in by_account.values():
        ordered = sorted(account_trades, key=lambda t: (t.open_time, t.record_id))
        for trade in ordered:
            still_open_same_direction = [
                other
                for other in ordered
                if other.side == trade.side
                and other.open_time < trade.open_time
                and (other.close_time is None or other.close_time > trade.open_time)
            ]
            cumulative_lot = sum((t.lot for t in still_open_same_direction), ZERO) + trade.lot
            add_count = len(still_open_same_direction) + 1

            reference_close = _most_recent_close_before(trade.trading_day_utc)
            if reference_close is None:
                unrealized = None
            else:
                open_positions = still_open_same_direction + [trade]
                unrealized = sum(
                    (
                        (reference_close - pos.open_price)
                        * _direction_sign(pos.side)
                        * pos.lot
                        * XAUUSD_CONTRACT_SIZE
                        for pos in open_positions
                    ),
                    ZERO,
                )

            results_by_record_id[trade.record_id] = AccountStateFeature(
                record_id=trade.record_id,
                cumulative_same_direction_lot=cumulative_lot,
                add_count_same_direction=add_count,
                unrealized_pnl_estimate_usd=unrealized,
            )

    return [results_by_record_id[trade.record_id] for trade in trades]
