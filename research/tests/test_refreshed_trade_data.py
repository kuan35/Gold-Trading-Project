"""Refresh guards: retain raw evidence, ambiguous identity, and minute ordering."""
from datetime import datetime
from decimal import Decimal as D
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "refresh_trade_case_data", Path(__file__).resolve().parents[1] / "scripts/refresh_trade_case_data.py")
refresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refresh)


def test_inventory_delta_distinguishes_modified_and_added():
    old = [{"source": "same", "sha256": "a"}, {"source": "edit", "sha256": "b"},
           {"source": "gone", "sha256": "c"}]
    new = [{"source": "same", "sha256": "a"}, {"source": "edit", "sha256": "d"},
           {"source": "new", "sha256": "e"}]
    changes = refresh.inventory_changes(old, new)
    assert {r["source"]: r["change"] for r in changes} == {
        "edit": "MODIFIED", "gone": "DELETED", "new": "ADDED", "same": "UNCHANGED"}


def test_csv_keeps_decimal_and_rejects_bad_rows_without_losing_next(tmp_path):
    path = tmp_path / "statement.csv"
    path.write_text(
        "Ticket,Open Date,Close Date,Symbol,Action,Units/Lots,SL,TP,Open Price,Close Price,Commission,Swap,Profit\n"
        "secret,09/25/2025 01:01,09/25/2025 01:04,XAUUSD,Buy,0.1234567890123456789,0,0,1234.567890123456789,1235,0,0,10\n"
        "bad,not-date,09/25/2025 01:04,XAUUSD,Buy,1,0,0,1234,1235,0,0,10\n"
        "next,09/25/2025 01:02,09/25/2025 01:04,XAUUSD,Buy,1,0,0,1234,1235,0,0,10\n", encoding="utf-8")
    rows, issues, metadata = refresh.parse_csv_source(path, "statement.csv", "C001", "hash")
    assert len(rows) == 3
    assert rows[0]["lot"] == D("0.1234567890123456789")
    assert rows[0]["open_price"] == D("1234.567890123456789")
    assert rows[0]["open_price_raw"] == "1234.567890123456789"
    assert rows[1]["open_time"] is None
    assert issues[0]["code"] == "CSV_FIELD_ERROR"
    assert metadata["timestamp_precision"] == "MINUTE"
    assert rows[2]["scope_basis"] == "CSV_FILE_UNCONFIRMED_ACCOUNT"


def test_csv_minute_ties_are_not_invented_seconds(tmp_path):
    path = tmp_path / "s.csv"
    path.write_text("Ticket,Open Date,Close Date,Symbol,Action,Units/Lots,Open Price,Close Price,Profit\n"
                    "a,09/25/2025 01:01,09/25/2025 01:04,XAUUSD,Buy,1,100,102,2\n"
                    "b,09/25/2025 01:01,09/25/2025 01:04,XAUUSD,Buy,1,99,102,3\n", encoding="utf-8")
    rows, _, _ = refresh.parse_csv_source(path, "s.csv", "C001", "hash")
    refresh.profile.classify_scope(rows)
    assert all(r["behavior"] == "TIME_TIE" for r in rows)


def test_csv_footer_or_partial_row_does_not_abort_file(tmp_path):
    path = tmp_path / "partial.csv"
    path.write_text("Ticket,Open Date,Close Date,Symbol,Action,Units/Lots,Open Price,Close Price,Profit\n"
                    "footer\n"
                    "a,09/25/2025 01:01,09/25/2025 01:04,XAUUSD,Buy,1,100,102,2\n", encoding="utf-8")
    rows, issues, _ = refresh.parse_csv_source(path, "partial.csv", "C001", "hash")
    assert len(rows) == 2
    assert rows[0]["record_type"] == "OTHER"
    assert any(r["code"] == "CSV_COLUMN_COUNT" for r in issues)
    assert rows[1]["record_type"] == "TRADE"


def test_cross_source_repeat_flags_preserve_both_accounts_and_numeric_scale():
    base = dict(symbol="XAUUSD", side="BUY", open_time=datetime(2025, 9, 25, 1, 1),
                close_time=datetime(2025, 9, 25, 1, 4), lot=D("1.00"), open_price=D("100.0"),
                close_price=D("102.0"), profit=D("2"), ticket_hash="")
    rows = [dict(base, record_id="a", source="a.html", scope="H001", source_format="HTML"),
            dict(base, record_id="b", source="b.csv", scope="C001", source_format="CSV", lot=D("1.000"))]
    candidates = refresh.flag_cross_source_candidates(rows)
    assert len(rows) == 2
    assert len(candidates) == 1
    assert all(r["cross_source_duplicate_candidate"] for r in rows)
    assert candidates[0]["identity_confirmed"] is False


def test_open_trades_section_uses_own_columns_and_floating_profit(tmp_path):
    path = tmp_path / "sections.csv"
    path.write_text("Tags,Ticket,Open Date,Close Date,Symbol,Action,Units/Lots,Open Price,Close Price,Profit\n"
                    ",a,09/25/2025 01:01,09/25/2025 01:04,XAUUSD,Buy,1,100,102,2\n"
                    "Open Trades\n"
                    "Tags,Ticket,Open Date,Symbol,Action,Lots,Open Price,TP,SL,Profit,Pips,Swap\n"
                    ",b,09/25/2025 01:01,GOLD#,Buy,0.25,1234,0,0,-10,-100,-2\n", encoding="utf-8")
    rows, issues, _ = refresh.parse_csv_source(path, "sections.csv", "C001", "hash")
    assert not issues
    assert len(rows) == 2
    assert rows[1]["record_type"] == "OPEN_TRADE_SNAPSHOT"
    assert rows[1]["gold"] is True
    assert rows[1]["lot"] == D("0.25")
    assert rows[1]["profit"] is None
    assert rows[1]["reported_floating_profit_snapshot"] == D("-10")


def test_public_case_allowlist_excludes_raw_paths_tickets_and_pnl_features():
    row = dict(record_id="private", scope="secret-account", source="private-path", raw_values="secret",
               ticket_hash="ticket", behavior="ADD_ADVERSE", lot=D("1"), profit=D("-10"),
               observed_overlap_group="private_G0001", timestamp_precision="MINUTE")
    sanitized = refresh.sanitize_cases([row])[0]
    assert "source" not in sanitized and "raw_values" not in sanitized and "ticket_hash" not in sanitized
    assert sanitized["case_id"] != "private"
    assert sanitized["scope_id"] != "secret-account"
    assert sanitized["outcome_reported_profit"] == D("-10")
    assert sanitized["timezone_status"] == "UNKNOWN"


def test_pdf_numbers_do_not_recover_corrupt_direction_from_positive_profit():
    text = "10/29/2025 22:20 10/29/2025 22:21 XAUUSD?? 0.01 0.00000 0.00000 3965.41000 3968.86000 345.0 3.41"
    rows = refresh.parse_pdf_text(text, "source.pdf", "hash", 1)
    assert len(rows) == 1
    assert rows[0]["open_price"] == D("3965.41000")
    assert rows[0]["side"] == "UNKNOWN"
    assert rows[0]["side_raw"] == "??"
    assert rows[0]["included_in_trade_statistics"] is False
