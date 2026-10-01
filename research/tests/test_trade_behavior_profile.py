"""Behavior audit edge cases: no invented order inside tied timestamps."""
from datetime import datetime, timedelta
from decimal import Decimal as D
import importlib.util
from pathlib import Path
from zipfile import ZipFile

spec = importlib.util.spec_from_file_location(
    "profile_trade_behaviors", Path(__file__).resolve().parents[1] / "scripts/profile_trade_behaviors.py")
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


def trade(i, minute, price, side="BUY", close=100, lot="1"):
    base = datetime(2025, 1, 1)
    return dict(record_id=str(i), scope="TEST", open_time=base+timedelta(minutes=minute),
                close_time=base+timedelta(minutes=close), open_price=D(price),
                lot=D(lot), side=side, profit=D("10"))


def test_weighted_average_and_sell_direction():
    rows = [trade(1, 0, "100", lot="3"), trade(2, 1, "80"), trade(3, 2, "96")]
    profile.classify_scope(rows)
    assert [r["behavior"] for r in rows] == ["NO_OBSERVED_POSITION", "ADD_ADVERSE", "ADD_FAVORABLE"]
    assert rows[2]["same_side_avg_entry"] == D("95")
    sells = [trade(4, 0, "100", "SELL"), trade(5, 1, "101", "SELL")]
    profile.classify_scope(sells)
    assert sells[1]["behavior"] == "ADD_ADVERSE"


def test_timestamp_ties_and_closed_positions():
    rows = [trade(1, 0, "100", close=2), trade(2, 1, "99"), trade(3, 1, "98"), trade(4, 2, "97")]
    profile.classify_scope(rows)
    assert all(r["behavior"] == "TIME_TIE" for r in rows[1:])
    rows = [trade(1, 0, "100", close=1), trade(2, 2, "90")]
    profile.classify_scope(rows)
    assert rows[1]["behavior"] == "NO_OBSERVED_POSITION"
    assert rows[0]["observed_overlap_group"] != rows[1]["observed_overlap_group"]


def test_opposite_mixed_and_future_outcome_independence():
    rows = [trade(1, 0, "100"), trade(2, 1, "101", "SELL"), trade(3, 2, "99")]
    profile.classify_scope(rows)
    assert [r["behavior"] for r in rows] == ["NO_OBSERVED_POSITION", "OPPOSITE", "MIXED"]
    labels = [r["behavior"] for r in rows]
    for r in rows:
        r["profit"] = D("-99999")
    profile.classify_scope(rows)
    assert labels == [r["behavior"] for r in rows]


def test_xlsx_keeps_exact_numeric_xml(tmp_path):
    path = tmp_path / "raw.xlsx"
    with ZipFile(path, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", '''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Price</t></is></c><c r="C1"><v>1234.567890123456789</v></c></row></sheetData></worksheet>''')
    assert profile.xlsx_rows(path)[0][2] == ["Price", "", "1234.567890123456789"]
