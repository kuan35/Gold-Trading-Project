"""Typed data structures used by the Myfxbook parser and audit."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


PARSER_VERSION = "1.0.0"


def serialise_value(value: Any) -> Any:
    """Convert dataclass values into deterministic CSV/JSON-friendly values."""
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, tuple):
        return "|".join(str(item) for item in value)
    if value is None:
        return ""
    return value


@dataclass(frozen=True, slots=True)
class ParseIssue:
    code: str
    message: str
    severity: str
    source_file: str
    source_row_number: int | None = None
    field: str | None = None
    raw_value: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {name: serialise_value(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class StatementMetadata:
    source_file: str
    source_sha256: str
    file_size: int
    parser_version: str
    account_name: str
    account_number: str | None
    account_id: str
    account_oid: str | None
    broker: str | None
    currency: str | None
    statement_start_raw: str | None
    statement_end_raw: str | None
    statement_start: datetime | None
    statement_end: datetime | None
    declared_total: int | None

    def public_dict(self) -> dict[str, Any]:
        """Return metadata safe for generated artifacts (no raw account number)."""
        excluded = {"account_number"}
        return {
            name: serialise_value(getattr(self, name))
            for name in self.__dataclass_fields__
            if name not in excluded
        }


@dataclass(frozen=True, slots=True)
class StatementRecord:
    record_id: str
    source_file: str
    source_row_number: int
    parser_version: str
    account_id: str
    account_name: str
    open_time_raw: str
    close_time_raw: str
    open_time: datetime | None
    close_time: datetime | None
    instrument_raw: str
    instrument_family: str
    action_raw: str
    record_type: str
    side: str | None
    lot: Decimal | None
    sl: Decimal | None
    tp: Decimal | None
    open_price: Decimal | None
    close_price: Decimal | None
    pips: Decimal | None
    profit_usd: Decimal | None
    parse_issues: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {name: serialise_value(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(slots=True)
class ParsedStatement:
    metadata: StatementMetadata
    records: list[StatementRecord]
    issues: list[ParseIssue]
    headers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StatementAudit:
    source_file: str
    account_id: str
    account_name: str
    broker: str
    currency: str
    declared_total: int | None
    parsed_rows: int
    trade_rows: int
    cashflow_rows: int
    xau_rows: int
    other_symbol_rows: int
    buy_rows: int
    sell_rows: int
    deposit_rows: int
    withdrawal_rows: int
    missing_close_time: int
    zero_sl: int
    zero_tp: int
    duplicate_rows: int
    invalid_chronology: int
    missing_lot: int
    zero_lot: int
    extreme_lot: int
    extreme_profit: int
    min_time: datetime | None
    max_time: datetime | None
    is_truncated: bool
    year_mismatch: bool
    parse_errors: int

    def to_dict(self) -> dict[str, Any]:
        return {name: serialise_value(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(slots=True)
class AuditBundle:
    statements: list[ParsedStatement]
    audits: list[StatementAudit]
    records: list[StatementRecord]
    issues: list[ParseIssue]
    same_close_basket_candidates: list[dict[str, Any]]
    cross_account_candidates: list[dict[str, Any]]

