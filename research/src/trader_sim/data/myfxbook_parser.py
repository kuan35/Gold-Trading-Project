"""Parser for locally saved Myfxbook statement HTML files."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path
import re
from typing import Iterable

from bs4 import BeautifulSoup

from .schemas import (
    PARSER_VERSION,
    ParseIssue,
    ParsedStatement,
    StatementMetadata,
    StatementRecord,
)


EXPECTED_HEADERS = (
    "開倉日期",
    "關閉日期",
    "符號",
    "行動",
    "手數",
    "SL",
    "TP",
    "開盤價",
    "收盤價",
    "點",
    "利潤 (USD)",
)

RECORD_FIELDS = (
    "open_time_raw",
    "close_time_raw",
    "instrument_raw",
    "action_raw",
    "lot",
    "sl",
    "tp",
    "open_price",
    "close_price",
    "pips",
    "profit_usd",
)

DATETIME_FORMATS = (
    "%m.%d.%Y %H:%M",
    "%m/%d/%Y %H:%M",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
)


def discover_statements(root: Path | str) -> list[Path]:
    """Return every statement*.html under root in deterministic path order."""
    root_path = Path(root)
    return sorted(
        (path for path in root_path.rglob("statement*.html") if path.is_file()),
        key=lambda path: path.as_posix().casefold(),
    )


def _text(node: object | None) -> str:
    if node is None or not hasattr(node, "get_text"):
        return ""
    return " ".join(node.get_text(" ", strip=True).split())


def _parse_datetime(raw: str) -> datetime | None:
    value = raw.strip()
    if not value:
        return None
    for date_format in DATETIME_FORMATS:
        try:
            return datetime.strptime(value, date_format)
        except ValueError:
            continue
    return None


def _parse_decimal(
    raw: str,
    *,
    field_name: str,
    source_file: str,
    row_number: int,
    issues: list[ParseIssue],
) -> Decimal | None:
    value = raw.replace(",", "").replace("$", "").replace("−", "-").strip()
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        issues.append(
            ParseIssue(
                code="INVALID_DECIMAL",
                message=f"Cannot parse {field_name} as Decimal.",
                severity="ERROR",
                source_file=source_file,
                source_row_number=row_number,
                field=field_name,
                raw_value=raw,
            )
        )
        return None


def _record_classification(action_raw: str, instrument_raw: str) -> tuple[str, str | None]:
    action = action_raw.strip().casefold()
    if action in {"買入", "buy"}:
        return "TRADE", "BUY"
    if action in {"賣出", "sell"}:
        return "TRADE", "SELL"
    if action in {"存款", "deposit"}:
        return "DEPOSIT", None
    if action in {"取款", "withdrawal", "withdraw"}:
        return "WITHDRAWAL", None
    return ("TRADE", None) if instrument_raw.strip() else ("OTHER_CASHFLOW", None)


def _instrument_family(instrument_raw: str) -> str:
    symbol = instrument_raw.strip().upper()
    if symbol in {"XAUUSD", "GOLD", "GOLD#"}:
        return "XAU/USD"
    return symbol


def _extract_header_rows(soup: BeautifulSoup) -> list[str]:
    header_table = soup.select_one("#statementExportHtml table")
    if header_table is None:
        return []
    return [_text(row) for row in header_table.find_all("tr", recursive=False)]


def _extract_label_value(rows: Iterable[str], labels: tuple[str, ...]) -> str | None:
    for row in rows:
        for label in labels:
            match = re.search(rf"{re.escape(label)}\s*[:：]\s*(.+)", row, re.IGNORECASE)
            if match:
                return match.group(1).strip()
    return None


def _extract_period(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    statement = soup.select_one("#statementExportHtml")
    text = _text(statement)
    match = re.search(
        r"(?:期間|Period)\s*[:：.]?\s*"
        r"(\d{1,2}/\d{1,2}/\d{4}\s+\d{2}:\d{2})\s*-\s*"
        r"(\d{1,2}/\d{1,2}/\d{4}\s+\d{2}:\d{2})",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1), match.group(2)
    return None, None


def parse_statement(path: Path | str) -> ParsedStatement:
    """Parse one statement while collecting row-level errors."""
    source_path = Path(path)
    source_file = source_path.as_posix()
    raw_bytes = source_path.read_bytes()
    source_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    issues: list[ParseIssue] = []

    try:
        html = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        issues.append(
            ParseIssue(
                code="INVALID_ENCODING",
                message=str(exc),
                severity="FATAL",
                source_file=source_file,
            )
        )
        html = raw_bytes.decode("utf-8", errors="replace")

    soup = BeautifulSoup(html, "html.parser")
    title = _text(soup.title).removesuffix(" | Myfxbook").strip()
    header_rows = _extract_header_rows(soup)
    account_number_value = _extract_label_value(header_rows, ("帳戶號碼", "Account Number"))
    account_number = None
    if account_number_value:
        account_number = re.split(r"[（(]", account_number_value, maxsplit=1)[0].strip()
    broker = _extract_label_value(header_rows, ("經紀人", "Broker"))
    currency = _extract_label_value(header_rows, ("貨幣", "Currency"))

    history_sort = soup.find(id="historyTableSort")
    account_oid = history_sort.get("accountoid") if history_sort else None
    total_raw = history_sort.get("total") if history_sort else None
    try:
        declared_total = int(total_raw) if total_raw not in (None, "") else None
    except ValueError:
        declared_total = None
        issues.append(
            ParseIssue(
                code="INVALID_DECLARED_TOTAL",
                message="historyTableSort.total is not an integer.",
                severity="ERROR",
                source_file=source_file,
                field="declared_total",
                raw_value=str(total_raw),
            )
        )

    statement_start_raw, statement_end_raw = _extract_period(soup)
    if statement_start_raw is None and history_sort:
        statement_start_raw = str(history_sort.get("start") or "").strip() or None
    if statement_end_raw is None and history_sort:
        statement_end_raw = str(history_sort.get("end") or "").split("&", 1)[0].strip() or None

    account_seed = account_oid or account_number or title or source_file
    account_id = "acct_" + hashlib.sha256(account_seed.encode("utf-8")).hexdigest()[:12]
    metadata = StatementMetadata(
        source_file=source_file,
        source_sha256=source_sha256,
        file_size=len(raw_bytes),
        parser_version=PARSER_VERSION,
        account_name=title,
        account_number=account_number,
        account_id=account_id,
        account_oid=account_oid,
        broker=broker,
        currency=currency,
        statement_start_raw=statement_start_raw,
        statement_end_raw=statement_end_raw,
        statement_start=_parse_datetime(statement_start_raw or ""),
        statement_end=_parse_datetime(statement_end_raw or ""),
        declared_total=declared_total,
    )

    table = soup.find("table", id="tradingHistoryTable")
    if table is None:
        issues.append(
            ParseIssue(
                code="MISSING_HISTORY_TABLE",
                message="Cannot find table#tradingHistoryTable.",
                severity="FATAL",
                source_file=source_file,
            )
        )
        return ParsedStatement(metadata=metadata, records=[], issues=issues, headers=())

    headers = tuple(_text(header) for header in table.find_all("th"))
    if headers != EXPECTED_HEADERS:
        issues.append(
            ParseIssue(
                code="UNEXPECTED_HEADERS",
                message=f"Expected {EXPECTED_HEADERS!r}, received {headers!r}.",
                severity="ERROR",
                source_file=source_file,
            )
        )

    tbody = table.find("tbody")
    if tbody is None:
        issues.append(
            ParseIssue(
                code="MISSING_TABLE_BODY",
                message="Trading history table has no tbody.",
                severity="FATAL",
                source_file=source_file,
            )
        )
        return ParsedStatement(metadata=metadata, records=[], issues=issues, headers=headers)

    records: list[StatementRecord] = []
    for source_row_number, row in enumerate(tbody.find_all("tr", recursive=False), start=1):
        cells = [_text(cell) for cell in row.find_all("td", recursive=False)]
        if not any(cells):
            continue
        if len(cells) != len(RECORD_FIELDS):
            issues.append(
                ParseIssue(
                    code="UNEXPECTED_COLUMN_COUNT",
                    message=f"Expected 11 cells, received {len(cells)}.",
                    severity="ERROR",
                    source_file=source_file,
                    source_row_number=source_row_number,
                    raw_value=" | ".join(cells),
                )
            )
            continue

        raw = dict(zip(RECORD_FIELDS, cells, strict=True))
        row_issues: list[ParseIssue] = []
        record_type, side = _record_classification(raw["action_raw"], raw["instrument_raw"])
        open_time = _parse_datetime(raw["open_time_raw"])
        close_time = _parse_datetime(raw["close_time_raw"])
        if raw["open_time_raw"] and open_time is None:
            row_issues.append(
                ParseIssue(
                    code="INVALID_DATETIME",
                    message="Cannot parse open_time.",
                    severity="ERROR",
                    source_file=source_file,
                    source_row_number=source_row_number,
                    field="open_time",
                    raw_value=raw["open_time_raw"],
                )
            )
        if raw["close_time_raw"] and close_time is None:
            row_issues.append(
                ParseIssue(
                    code="INVALID_DATETIME",
                    message="Cannot parse close_time.",
                    severity="ERROR",
                    source_file=source_file,
                    source_row_number=source_row_number,
                    field="close_time",
                    raw_value=raw["close_time_raw"],
                )
            )
        if record_type == "TRADE" and not raw["close_time_raw"]:
            row_issues.append(
                ParseIssue(
                    code="MISSING_TRADE_CLOSE_TIME",
                    message="Trade row has no close time.",
                    severity="WARNING",
                    source_file=source_file,
                    source_row_number=source_row_number,
                    field="close_time",
                )
            )

        numeric_values = {
            field_name: _parse_decimal(
                raw[field_name],
                field_name=field_name,
                source_file=source_file,
                row_number=source_row_number,
                issues=row_issues,
            )
            for field_name in ("lot", "sl", "tp", "open_price", "close_price", "pips", "profit_usd")
        }
        digest_input = "\x1f".join([source_sha256, str(source_row_number), *cells])
        record_id = "rec_" + hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:20]
        issues.extend(row_issues)
        records.append(
            StatementRecord(
                record_id=record_id,
                source_file=source_file,
                source_row_number=source_row_number,
                parser_version=PARSER_VERSION,
                account_id=account_id,
                account_name=title,
                open_time_raw=raw["open_time_raw"],
                close_time_raw=raw["close_time_raw"],
                open_time=open_time,
                close_time=close_time,
                instrument_raw=raw["instrument_raw"],
                instrument_family=_instrument_family(raw["instrument_raw"]),
                action_raw=raw["action_raw"],
                record_type=record_type,
                side=side,
                lot=numeric_values["lot"],
                sl=numeric_values["sl"],
                tp=numeric_values["tp"],
                open_price=numeric_values["open_price"],
                close_price=numeric_values["close_price"],
                pips=numeric_values["pips"],
                profit_usd=numeric_values["profit_usd"],
                parse_issues=tuple(issue.code for issue in row_issues),
            )
        )

    return ParsedStatement(metadata=metadata, records=records, issues=issues, headers=headers)

