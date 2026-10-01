from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from trader_sim.data import parse_statement


HEADERS = (
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


def make_html(rows: list[list[str]], *, total: int | None = None) -> str:
    declared = len(rows) if total is None else total
    header_html = "".join(f"<th>{header}</th>" for header in HEADERS)
    row_html = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>測試帳戶 | Myfxbook</title></head>
<body>
<div id="statementExportHtml">
  <table>
    <tr><td>測試帳戶</td></tr>
    <tr><td>帳戶號碼：123456（真實）</td></tr>
    <tr><td>經紀人: Test Broker</td></tr>
    <tr><td>貨幣: USD</td></tr>
  </table>
  <table><tr><td>期間: 01/01/2025 00:00 - 01/31/2025 23:59</td></tr></table>
  <input id="historyTableSort" accountOid="oid-123" total="{declared}">
  <table id="tradingHistoryTable">
    <thead><tr>{header_html}</tr></thead>
    <tbody>{row_html}</tbody>
  </table>
</div>
</body>
</html>"""


def write_fixture(tmp_path: Path, rows: list[list[str]], *, total: int | None = None) -> Path:
    path = tmp_path / "statement.html"
    path.write_text(make_html(rows, total=total), encoding="utf-8")
    return path


def test_parses_buy_sell_and_metadata(tmp_path: Path) -> None:
    path = write_fixture(
        tmp_path,
        [
            [
                "01.01.2025 10:00",
                "01.01.2025 11:00",
                "XAUUSD",
                "買入",
                "0.10",
                "0",
                "0",
                "2,000.00",
                "2010",
                " 100 ",
                "100.00",
            ],
            [
                "01.02.2025 10:00",
                "01.02.2025 10:30",
                "GOLD#",
                "賣出",
                "0.20",
                "1990",
                "1980",
                "2000",
                "1995",
                "-50",
                "-100.50",
            ],
        ],
    )
    parsed = parse_statement(path)

    assert parsed.metadata.account_name == "測試帳戶"
    assert parsed.metadata.account_number == "123456"
    assert parsed.metadata.account_id.startswith("acct_")
    assert parsed.metadata.broker == "Test Broker"
    assert parsed.metadata.currency == "USD"
    assert parsed.metadata.declared_total == 2
    assert not parsed.issues

    buy, sell = parsed.records
    assert buy.record_type == "TRADE"
    assert buy.side == "BUY"
    assert buy.instrument_family == "XAU/USD"
    assert buy.open_price == Decimal("2000.00")
    assert buy.pips == Decimal("100")
    assert sell.side == "SELL"
    assert sell.instrument_raw == "GOLD#"
    assert sell.pips == Decimal("-50")
    assert sell.profit_usd == Decimal("-100.50")


def test_parses_deposit_withdrawal_and_non_gold(tmp_path: Path) -> None:
    path = write_fixture(
        tmp_path,
        [
            ["01.01.2025 09:00", "", "", "存款", "", "", "", "", "", "", "1,000"],
            ["01.02.2025 09:00", "", "", "取款", "", "", "", "", "", "", "-100"],
            [
                "01.03.2025 09:00",
                "01.03.2025 10:00",
                "EURUSD",
                "買入",
                "1",
                "0",
                "0",
                "1.1",
                "1.2",
                "10",
                "100",
            ],
        ],
    )
    parsed = parse_statement(path)

    assert [record.record_type for record in parsed.records] == [
        "DEPOSIT",
        "WITHDRAWAL",
        "TRADE",
    ]
    assert parsed.records[0].close_time is None
    assert parsed.records[2].instrument_family == "EURUSD"


def test_missing_trade_close_time_is_collected_not_fatal(tmp_path: Path) -> None:
    path = write_fixture(
        tmp_path,
        [
            [
                "01.01.2025 10:00",
                "",
                "XAUUSD",
                "買入",
                "0.1",
                "0",
                "0",
                "2000",
                "",
                "",
                "",
            ]
        ],
    )
    parsed = parse_statement(path)

    assert len(parsed.records) == 1
    assert parsed.records[0].close_time is None
    assert "MISSING_TRADE_CLOSE_TIME" in parsed.records[0].parse_issues
    assert any(issue.code == "MISSING_TRADE_CLOSE_TIME" for issue in parsed.issues)


def test_malformed_row_is_reported_and_later_rows_continue(tmp_path: Path) -> None:
    valid = [
        "01.01.2025 10:00",
        "01.01.2025 11:00",
        "XAUUSD",
        "買入",
        "0.1",
        "0",
        "0",
        "2000",
        "2010",
        "100",
        "100",
    ]
    path = write_fixture(tmp_path, [["too", "short"], valid], total=2)
    parsed = parse_statement(path)

    assert len(parsed.records) == 1
    assert any(issue.code == "UNEXPECTED_COLUMN_COUNT" for issue in parsed.issues)


def test_invalid_decimal_is_attached_to_record(tmp_path: Path) -> None:
    path = write_fixture(
        tmp_path,
        [
            [
                "01.01.2025 10:00",
                "01.01.2025 11:00",
                "XAUUSD",
                "買入",
                "not-a-number",
                "0",
                "0",
                "2000",
                "2010",
                "100",
                "100",
            ]
        ],
    )
    parsed = parse_statement(path)

    assert parsed.records[0].lot is None
    assert "INVALID_DECIMAL" in parsed.records[0].parse_issues

