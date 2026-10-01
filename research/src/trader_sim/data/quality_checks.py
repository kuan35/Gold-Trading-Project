"""Data-quality checks and observable grouping candidates."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
import hashlib
from pathlib import Path
import re
from typing import Iterable

from .schemas import (
    AuditBundle,
    ParsedStatement,
    StatementAudit,
    StatementRecord,
    serialise_value,
)


EXTREME_LOT_THRESHOLD = Decimal("10")
EXTREME_PROFIT_THRESHOLD = Decimal("10000")
CROSS_ACCOUNT_TIME_TOLERANCE_SECONDS = 180
CROSS_ACCOUNT_PRICE_TOLERANCE = Decimal("0.001")


def _duplicate_key(record: StatementRecord) -> tuple[object, ...]:
    return (
        record.open_time_raw,
        record.close_time_raw,
        record.instrument_raw,
        record.action_raw,
        record.lot,
        record.sl,
        record.tp,
        record.open_price,
        record.close_price,
        record.pips,
        record.profit_usd,
    )


def _path_year(source_file: str) -> int | None:
    years = [
        int(part)
        for part in Path(source_file).parts
        if re.fullmatch(r"20(?:1[0-9]|2[0-9])", part)
    ]
    return years[-1] if years else None


def _statement_audit(statement: ParsedStatement) -> StatementAudit:
    records = statement.records
    trades = [record for record in records if record.record_type == "TRADE"]
    cashflows = [record for record in records if record.record_type != "TRADE"]
    keys = [_duplicate_key(record) for record in records]
    times = [
        value
        for record in records
        for value in (record.open_time, record.close_time)
        if value is not None
    ]
    expected_year = _path_year(statement.metadata.source_file)
    observed_years = {record.open_time.year for record in records if record.open_time}

    return StatementAudit(
        source_file=statement.metadata.source_file,
        account_id=statement.metadata.account_id,
        account_name=statement.metadata.account_name,
        broker=statement.metadata.broker or "",
        currency=statement.metadata.currency or "",
        declared_total=statement.metadata.declared_total,
        parsed_rows=len(records),
        trade_rows=len(trades),
        cashflow_rows=len(cashflows),
        xau_rows=sum(record.instrument_family == "XAU/USD" for record in trades),
        other_symbol_rows=sum(record.instrument_family != "XAU/USD" for record in trades),
        buy_rows=sum(record.side == "BUY" for record in trades),
        sell_rows=sum(record.side == "SELL" for record in trades),
        deposit_rows=sum(record.record_type == "DEPOSIT" for record in cashflows),
        withdrawal_rows=sum(record.record_type == "WITHDRAWAL" for record in cashflows),
        missing_close_time=sum(record.close_time is None for record in trades),
        zero_sl=sum(record.sl == 0 for record in trades),
        zero_tp=sum(record.tp == 0 for record in trades),
        duplicate_rows=len(keys) - len(set(keys)),
        invalid_chronology=sum(
            record.open_time is not None
            and record.close_time is not None
            and record.close_time < record.open_time
            for record in trades
        ),
        missing_lot=sum(record.lot is None for record in trades),
        zero_lot=sum(record.lot == 0 for record in trades),
        extreme_lot=sum(
            record.lot is not None and record.lot >= EXTREME_LOT_THRESHOLD
            for record in trades
        ),
        extreme_profit=sum(
            record.profit_usd is not None
            and abs(record.profit_usd) >= EXTREME_PROFIT_THRESHOLD
            for record in trades
        ),
        min_time=min(times) if times else None,
        max_time=max(times) if times else None,
        is_truncated=(
            statement.metadata.declared_total is not None
            and statement.metadata.declared_total > len(records)
        ),
        year_mismatch=(
            expected_year is not None
            and bool(observed_years)
            and any(year != expected_year for year in observed_years)
        ),
        parse_errors=sum(issue.severity in {"ERROR", "FATAL"} for issue in statement.issues),
    )


def _candidate_id(prefix: str, values: Iterable[object]) -> str:
    raw = "\x1f".join(str(value) for value in values)
    return prefix + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _same_close_candidates(
    records: list[StatementRecord],
    truncated_sources: set[str],
) -> list[dict[str, object]]:
    groups: dict[tuple[object, ...], list[StatementRecord]] = defaultdict(list)
    for record in records:
        if record.record_type != "TRADE" or record.close_time is None:
            continue
        groups[
            (
                record.account_id,
                record.instrument_family,
                record.side,
                record.close_time,
            )
        ].append(record)

    candidates: list[dict[str, object]] = []
    for key, group in groups.items():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=lambda record: (record.open_time or datetime.min, record.record_id))
        total_lot = sum((record.lot or Decimal("0")) for record in ordered)
        total_profit = sum((record.profit_usd or Decimal("0")) for record in ordered)
        sources = sorted({record.source_file for record in ordered})
        open_times = [record.open_time for record in ordered if record.open_time is not None]
        candidate_id = _candidate_id(
            "basket_",
            [key[0], key[1], key[2], key[3], *(record.record_id for record in ordered)],
        )
        candidates.append(
            {
                "candidate_id": candidate_id,
                "candidate_type": "SAME_CLOSE_BASKET",
                "account_id": key[0],
                "account_label": key[0],
                "instrument_family": key[1],
                "side": key[2] or "",
                "episode_start": serialise_value(min(open_times) if open_times else None),
                "episode_end": serialise_value(key[3]),
                "order_count": len(ordered),
                "total_lot": serialise_value(total_lot),
                "total_profit_usd": serialise_value(total_profit),
                "record_ids": "|".join(record.record_id for record in ordered),
                "source_files": "|".join(sources),
                "is_partial_source": any(source in truncated_sources for source in sources),
                "grouping_rule": "same account + instrument family + side + exact close time",
                "status": "CANDIDATE_REQUIRES_TRADER_CONFIRMATION",
            }
        )
    return sorted(
        candidates,
        key=lambda item: (
            str(item["episode_end"]),
            str(item["account_id"]),
            str(item["candidate_id"]),
        ),
    )


def _relative_difference(first: Decimal, second: Decimal) -> Decimal:
    denominator = max(abs(first), abs(second))
    return abs(first - second) / denominator if denominator else Decimal("0")


def _cross_account_candidates(records: list[StatementRecord]) -> list[dict[str, object]]:
    eligible = sorted(
        (
            record
            for record in records
            if record.record_type == "TRADE"
            and record.open_time is not None
            and record.close_time is not None
            and record.open_price is not None
            and record.close_price is not None
        ),
        key=lambda record: (record.open_time, record.record_id),
    )
    candidates: list[dict[str, object]] = []
    for index, first in enumerate(eligible):
        for second in eligible[index + 1 :]:
            open_delta = (second.open_time - first.open_time).total_seconds()
            if open_delta > CROSS_ACCOUNT_TIME_TOLERANCE_SECONDS:
                break
            if first.account_id == second.account_id or first.source_file == second.source_file:
                continue
            if first.instrument_family != second.instrument_family or first.side != second.side:
                continue
            close_delta = abs((second.close_time - first.close_time).total_seconds())
            if close_delta > CROSS_ACCOUNT_TIME_TOLERANCE_SECONDS:
                continue
            open_price_diff = _relative_difference(first.open_price, second.open_price)
            close_price_diff = _relative_difference(first.close_price, second.close_price)
            if open_price_diff > CROSS_ACCOUNT_PRICE_TOLERANCE:
                continue
            if close_price_diff > CROSS_ACCOUNT_PRICE_TOLERANCE:
                continue

            candidate_id = _candidate_id(
                "cross_",
                sorted((first.record_id, second.record_id)),
            )
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "candidate_type": "CROSS_ACCOUNT_SYNCHRONY",
                    "account_a": first.account_id,
                    "account_b": second.account_id,
                    "record_a": first.record_id,
                    "record_b": second.record_id,
                    "instrument_family": first.instrument_family,
                    "side": first.side or "",
                    "open_time_a": serialise_value(first.open_time),
                    "open_time_b": serialise_value(second.open_time),
                    "close_time_a": serialise_value(first.close_time),
                    "close_time_b": serialise_value(second.close_time),
                    "open_delta_seconds": int(abs(open_delta)),
                    "close_delta_seconds": int(close_delta),
                    "open_price_relative_difference": serialise_value(open_price_diff),
                    "close_price_relative_difference": serialise_value(close_price_diff),
                    "lot_a": serialise_value(first.lot),
                    "lot_b": serialise_value(second.lot),
                    "source_file_a": first.source_file,
                    "source_file_b": second.source_file,
                    "matching_rule": "different accounts; <=3m open/close; <=0.1% entry/exit price",
                    "status": "CANDIDATE_REQUIRES_TRADER_CONFIRMATION",
                }
            )
    return sorted(candidates, key=lambda item: str(item["candidate_id"]))


def audit_statements(statements: Iterable[ParsedStatement]) -> AuditBundle:
    """Audit parsed statements and construct explicitly provisional candidates."""
    statement_list = list(statements)
    audits = [_statement_audit(statement) for statement in statement_list]
    records = [record for statement in statement_list for record in statement.records]
    issues = [issue for statement in statement_list for issue in statement.issues]
    truncated_sources = {audit.source_file for audit in audits if audit.is_truncated}
    return AuditBundle(
        statements=statement_list,
        audits=audits,
        records=records,
        issues=issues,
        same_close_basket_candidates=_same_close_candidates(records, truncated_sources),
        cross_account_candidates=_cross_account_candidates(records),
    )
