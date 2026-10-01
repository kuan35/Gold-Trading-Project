"""Read-only, descriptive trade-behavior audit; never a strategy/prediction model.

HTML copies are removed by byte hash. XLSX files are independent observation
scopes until their account mapping is confirmed. Prices and money stay Decimal.
"""
from __future__ import annotations

# IMPORT
import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from trader_sim.data import parse_statement

D = Decimal
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
GROUPS = {
    "NO_OBSERVED_POSITION": "可見紀錄中無既有黃金持倉",
    "ADD_ADVERSE": "價格逆向時同向加單",
    "ADD_FAVORABLE": "價格順向時同向加單",
    "ADD_FLAT": "接近既有均價同向加單（精確相等）",
    "OPPOSITE": "已有反向部位時下單",
    "MIXED": "已有雙向部位時下單",
    "TIME_TIE": "同一時間開平倉，順序待確認",
    "INVALID": "欄位不足或時間異常",
}


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fields or ["status"])
        writer.writeheader()
        writer.writerows(rows)


def xlsx_rows(path: Path) -> list[tuple[str, int, list[str]]]:
    """Read saved cell texts, including exact decimal XML, without float conversion."""
    result = []
    with ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = ["".join(n.itertext()) for n in ET.fromstring(
                archive.read("xl/sharedStrings.xml")).findall("s:si", NS)]
        for name in sorted(archive.namelist()):
            if not (name.startswith("xl/worksheets/sheet") and name.endswith(".xml")):
                continue
            sheet = ET.fromstring(archive.read(name))
            for row in sheet.findall("s:sheetData/s:row", NS):
                values: dict[int, str] = {}
                for cell in row.findall("s:c", NS):
                    letters = "".join(x for x in cell.attrib["r"] if x.isalpha())
                    col = 0
                    for letter in letters:
                        col = col * 26 + ord(letter) - 64
                    value = cell.findtext("s:v", default="", namespaces=NS)
                    if cell.get("t") == "s":
                        value = shared[int(value)]
                    elif cell.get("t") == "inlineStr":
                        node = cell.find("s:is", NS)
                        value = "".join(node.itertext()) if node is not None else ""
                    values[col - 1] = value
                if any(values.values()):
                    result.append((name, int(row.attrib["r"]),
                                   [values.get(i, "") for i in range(max(values) + 1)]))
    return result


def decimal_or_none(value: str) -> Decimal | None:
    return D(value) if value else None


def classify_scope(rows: list[dict[str, Any]]) -> None:
    """Only earlier opens and positions still open at t define the pre-action state.

    Same timestamp opens/closures are quarantined rather than inventing order.
    All state is explicitly conditional on the visible scope being sufficient.
    """
    valid = [r for r in rows if r["open_time"] and r["close_time"]
             and r["close_time"] >= r["open_time"] and r["lot"] is not None
             and r["lot"] > 0 and r["open_price"] is not None
             and r["open_price"] > 0 and r["side"] in ("BUY", "SELL")]
    for r in rows:
        r["behavior"] = "INVALID"
    opens = Counter(r["open_time"] for r in valid)
    ordered = sorted(valid, key=lambda r: (r["open_time"], r["record_id"]))
    active: list[dict[str, Any]] = []
    for r in ordered:
        t = r["open_time"]
        tied_close = any(p["close_time"] == t and p["open_time"] < t for p in active)
        active = [p for p in active if p["close_time"] >= t]
        prior = [p for p in active if p["open_time"] < t and p["close_time"] > t]
        same = [p for p in prior if p["side"] == r["side"]]
        other = [p for p in prior if p["side"] != r["side"]]
        r["observed_prior_count"] = len(prior)
        r["observed_prior_lot"] = sum((p["lot"] for p in prior), D(0))
        if same:
            lots = sum((p["lot"] for p in same), D(0))
            avg = sum((p["lot"] * p["open_price"] for p in same), D(0)) / lots
            delta = (r["open_price"] - avg) * (1 if r["side"] == "BUY" else -1)
            r["same_side_avg_entry"] = avg
            r["signed_distance_to_avg_pct"] = delta / avg * 100
            r["lot_vs_prior_mean"] = r["lot"] / (lots / len(same))
        if opens[t] > 1 or tied_close or r["close_time"] == t:
            r["behavior"] = "TIME_TIE"
        elif same and other:
            r["behavior"] = "MIXED"
        elif other:
            r["behavior"] = "OPPOSITE"
        elif not same:
            r["behavior"] = "NO_OBSERVED_POSITION"
        else:
            r["behavior"] = "ADD_ADVERSE" if delta < 0 else "ADD_FAVORABLE" if delta > 0 else "ADD_FLAT"
        r["holding_minutes"] = D(str((r["close_time"] - t).total_seconds())) / 60
        active.append(r)

    # Retrospective grouping for dependence auditing ONLY, never an entry feature.
    end = None
    group = 0
    for r in ordered:
        if end is None or r["open_time"] > end:
            group += 1
        end = max(end, r["close_time"]) if end is not None and r["open_time"] <= end else r["close_time"]
        r["observed_overlap_group"] = f'{r["scope"]}_G{group:04}'


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    profits = [r["profit"] for r in rows if r["profit"] is not None]
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]
    avgwin = sum(wins, D(0)) / len(wins) if wins else None
    avgloss = -sum(losses, D(0)) / len(losses) if losses else None
    holds = [r["holding_minutes"] for r in rows if "holding_minutes" in r]
    scope_pnl = defaultdict(list)
    for r in rows:
        if r["profit"] is not None:
            scope_pnl[r["scope"]].append(r["profit"])
    scope_rates = [D(sum(p > 0 for p in ps)) / len(ps) * 100 for ps in scope_pnl.values()]
    scope_mean = sum(scope_rates, D(0)) / len(scope_rates) if scope_rates else None
    scope_sd = (sum(((x-scope_mean)**2 for x in scope_rates), D(0)) /
                (len(scope_rates)-1)).sqrt() if len(scope_rates) > 1 else None
    return {
        "n": len(rows), "scopes": len({r["scope"] for r in rows}),
        "observed_overlap_groups": len({r.get("observed_overlap_group") for r in rows} - {None}),
        "wins": len(wins), "losses": len(losses), "zero": len(profits) - len(wins) - len(losses),
        "profit_available": len(profits),
        "win_pct_descriptive": D(len(wins)) / len(profits) * 100 if profits else None,
        "scope_win_pct_sd_descriptive": scope_sd,
        "reported_profit_sum": sum(profits, D(0)),
        "mean_win": avgwin, "mean_loss_abs": avgloss,
        "realized_mean_win_loss_ratio": avgwin / avgloss if avgwin is not None and avgloss else None,
        "median_holding_minutes": median(holds) if holds else None,
        "sl_missing_or_zero": sum(r["sl"] in (None, D(0)) for r in rows),
        "tp_missing_or_zero": sum(r["tp"] in (None, D(0)) for r in rows),
    }


def run(root: Path, out: Path) -> dict[str, Any]:
    # LOAD DATA: inventory every source, verify all hashes again before returning.
    paths = sorted(p for p in root.rglob("*") if p.is_file())
    hashes = {p: digest(p.read_bytes()) for p in paths}
    out.mkdir(parents=True, exist_ok=True)
    inventory = []; issues = []; raw_cells = []; records = []; seen = {}
    expected = ["Ticket", "Open", "Type", "Volume", "Symbol", "Price", "SL", "TP", "Close", "Price", "Swap", "Commissions", "Profit", "Pips", "Trade duration in seconds"]
    scope_index = {}; raw_count = Counter()
    for path in paths:
        rel = path.relative_to(root).as_posix()
        h = hashes[path]
        item: dict[str, Any] = {"source": rel, "sha256": h, "bytes": path.stat().st_size,
                                "extension": path.suffix, "duplicate_of": seen.get(h, "")}
        inventory.append(item)
        if h in seen:
            continue
        seen[h] = rel
        if path.suffix.lower() == ".html":
            statement = parse_statement(path)
            scope_index.setdefault(statement.metadata.account_id, f"H{len(scope_index)+1:03}")
            scope = scope_index[statement.metadata.account_id]
            env = "HTML_DEMO_FOLDER" if "模擬倉" in path.parts else "HTML_OTHER_FOLDER" if "其他" in path.parts else "HTML_MAIN"
            item.update(scope=scope, environment=env, visible_rows=len(statement.records),
                        declared_rows=statement.metadata.declared_total,
                        declared_visible_gap=(statement.metadata.declared_total or len(statement.records))-len(statement.records),
                        completeness="UNVERIFIED")
            issues.extend({"source": rel, "row": i.source_row_number, "code": i.code,
                           "field": i.field, "raw_value": i.raw_value} for i in statement.issues)
            for r in statement.records:
                raw_count[r.record_type] += 1
                # Keep all non-gold records and cashflows, but no strategy labels for them.
                records.append(dict(record_id=r.record_id, source=rel, source_row=r.source_row_number,
                    source_format="HTML", scope=scope, scope_basis="HTML_ACCOUNT_ID",
                    environment=env, record_type=r.record_type, symbol=r.instrument_raw,
                    gold=r.instrument_family == "XAU/USD", side=r.side,
                    open_time=r.open_time, close_time=r.close_time,
                    open_time_raw=r.open_time_raw, close_time_raw=r.close_time_raw,
                    lot=r.lot, open_price=r.open_price, close_price=r.close_price,
                    sl=r.sl, tp=r.tp, profit=r.profit_usd, swap=None, commission=None,
                    currency=statement.metadata.currency,
                    declared_visible_gap=item["declared_visible_gap"], completeness="UNVERIFIED"))
            # Preserve exact original table text alongside normalized records.
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(path.read_bytes().decode("utf-8-sig"), "html.parser")
            for number, row in enumerate(soup.select("#tradingHistoryTable tbody > tr"), 1):
                raw_cells.append(dict(source=rel, row=number, values=json.dumps(
                    [c.get_text(" ", strip=True) for c in row.find_all("td", recursive=False)], ensure_ascii=False)))
        elif path.suffix.lower() == ".xlsx":
            scope = f"X{sum(1 for i in inventory if i.get('scope_basis') == 'XLSX_FILE_UNCONFIRMED_ACCOUNT')+1:03}"
            env = "XLSX_" + path.parent.name
            item.update(scope=scope, scope_basis="XLSX_FILE_UNCONFIRMED_ACCOUNT", environment=env,
                        completeness="UNVERIFIED", visible_rows=0)
            for sheet, number, values in xlsx_rows(path):
                raw_cells.append(dict(source=rel, row=f"{sheet}:{number}", values=json.dumps(values, ensure_ascii=False)))
                if number == 1:
                    if values != expected:
                        raise ValueError(f"Unexpected XLSX schema: {rel}")
                    continue
                item["visible_rows"] += 1
                values += [""] * (15-len(values))
                try:
                    opened = datetime.fromisoformat(values[1]); closed = datetime.fromisoformat(values[8])
                    nums = {k: decimal_or_none(values[i]) for k, i in
                            {"lot": 3, "open_price": 5, "sl": 6, "tp": 7, "close_price": 9,
                             "swap": 10, "commission": 11, "profit": 12}.items()}
                    side = values[2].upper()
                    if side not in ("BUY", "SELL"):
                        raise ValueError("Unexpected trade side")
                except Exception as exc:
                    issues.append(dict(source=rel, row=number, code="XLSX_ROW_ERROR", field="", raw_value=str(exc)))
                    continue
                # Tickets are opaque hashes, not account identifiers; do not infer cross-file identity.
                records.append(dict(record_id="x_"+digest(f"{h}:{sheet}:{number}".encode())[:20],
                    ticket_hash=digest(values[0].encode())[:20], source=rel, source_row=number,
                    source_format="XLSX", scope=scope, scope_basis="XLSX_FILE_UNCONFIRMED_ACCOUNT",
                    environment=env, record_type="TRADE", symbol=values[4], gold=values[4].upper() == "XAUUSD",
                    side=side, open_time=opened, close_time=closed,
                    open_time_raw=values[1], close_time_raw=values[8],
                    **nums, currency="NOT_STATED_IN_SHEET",
                    declared_visible_gap=None, completeness="UNVERIFIED"))
                raw_count["XLSX_TRADE"] += 1

    # DATASET PREPARATIONS: only exact file copies removed. Other suspected repeats flagged.
    gold = [r for r in records if r["record_type"] == "TRADE" and r["gold"]]
    scopes = defaultdict(list)
    for r in gold:
        scopes[r["scope"]].append(r)
    for rows in scopes.values():
        classify_scope(rows)
    signatures = Counter(tuple(str(r.get(k)) for k in (
        "scope", "symbol", "side", "open_time", "close_time", "lot", "open_price", "close_price", "profit")) for r in records)
    for r in records:
        key = tuple(str(r.get(k)) for k in (
            "scope", "symbol", "side", "open_time", "close_time", "lot", "open_price", "close_price", "profit"))
        r["identical_signature_candidate_count"] = signatures[key]
        if r.get("holding_minutes") is not None:
            m = r["holding_minutes"]
            r["posthoc_holding_band"] = ("0-5m" if m <= 5 else "5-60m" if m <= 60
                else "1-6h" if m <= 360 else "6-24h" if m <= 1440 else ">24h")
        if r["gold"] and r.get("behavior") in ("ADD_ADVERSE", "ADD_FAVORABLE", "ADD_FLAT"):
            r["lot_vs_prior_mean_band"] = ("SAME" if r["lot_vs_prior_mean"] == 1
                else "LARGER" if r["lot_vs_prior_mean"] > 1 else "SMALLER")
    tickets = Counter(r["ticket_hash"] for r in records if r.get("ticket_hash"))

    # DESCRIPTIVE STATISTICS / ANALYSIS: no inferential significance or model training.
    summaries = []
    for env in sorted({r["environment"] for r in gold}):
        subset = [r for r in gold if r["environment"] == env]
        summaries.append(dict(environment=env, behavior="ALL", **summarize(subset)))
        for group in GROUPS:
            part = [r for r in subset if r["behavior"] == group]
            if part:
                summaries.append(dict(environment=env, behavior=group, **summarize(part)))
    annual = []
    for year in sorted({r["open_time"].year for r in gold if r["open_time"]}):
        for fmt in ("HTML", "XLSX"):
            subset = [r for r in gold if r["open_time"] and r["open_time"].year == year and r["source_format"] == fmt]
            if subset:
                annual.append(dict(year=year, source_format=fmt, **summarize(subset)))
    blocks = defaultdict(list)
    for r in gold:
        if r.get("observed_overlap_group"):
            blocks[r["observed_overlap_group"]].append(r)
    episodes = []
    for group, rows in sorted(blocks.items()):
        episodes.append(dict(candidate_group=group, environment=rows[0]["environment"], scope=rows[0]["scope"],
            n=len(rows), start=min(r["open_time"] for r in rows), end=max(r["close_time"] for r in rows),
            reported_profit_sum=sum((r["profit"] for r in rows if r["profit"] is not None), D(0)),
            complete_account_history=False, grouping_uses_future=True))
    scope_summary = []
    for scope, rows in sorted(scopes.items()):
        scope_summary.append(dict(scope=scope, source=rows[0]["source"], environment=rows[0]["environment"],
            start=min(r["open_time"] for r in rows if r["open_time"]),
            end=max(r["open_time"] for r in rows if r["open_time"]), **summarize(rows)))

    # SAVE ADDITIONAL RESULTS: provenance, errors, all records, grouped gold and denominator tables.
    write_csv(out / "source_inventory.csv", inventory)
    write_csv(out / "raw_cells.csv", raw_cells)
    write_csv(out / "parse_issues.csv", issues)
    write_csv(out / "all_records.csv", records)
    write_csv(out / "gold_behavior_records.csv", gold)
    write_csv(out / "behavior_summary.csv", summaries)
    write_csv(out / "year_summary.csv", annual)
    write_csv(out / "scope_summary.csv", scope_summary)
    write_csv(out / "observed_overlap_groups.csv", episodes)
    secondary = []
    for fmt in ("HTML", "XLSX"):
        subset = [r for r in gold if r["source_format"] == fmt]
        for field in ("posthoc_holding_band", "lot_vs_prior_mean_band"):
            for band in sorted({r[field] for r in subset if field in r}):
                part = [r for r in subset if r.get(field) == band]
                secondary.append(dict(source_format=fmt, dimension=field, band=band, **summarize(part)))
    write_csv(out / "secondary_summary.csv", secondary)
    html = [i for i in inventory if i["extension"] == ".html" and not i["duplicate_of"]]
    result = dict(source_files=len(paths), extensions=dict(Counter(p.suffix for p in paths)),
        unique_html=len(html), exact_duplicate_files=sum(bool(i["duplicate_of"]) for i in inventory),
        html_visible_rows=sum(i["visible_rows"] for i in html),
        html_declared_rows=sum(i.get("declared_rows") or 0 for i in html),
        html_declared_gap_files=sum(i["declared_visible_gap"] > 0 for i in html),
        html_exactly_100_rows=sum(i["visible_rows"] == 100 for i in html),
        raw_record_types=dict(raw_count), total_rows=len(records), gold_rows=len(gold),
        gold_by_format=dict(Counter(r["source_format"] for r in gold)),
        behavior_counts=dict(Counter(r["behavior"] for r in gold)),
        earliest_gold_open=str(min(r["open_time"] for r in gold if r["open_time"])),
        latest_gold_open=str(max(r["open_time"] for r in gold if r["open_time"])),
        html_accounts=len(scope_index), xlsx_scopes=sum(i.get("scope_basis") == "XLSX_FILE_UNCONFIRMED_ACCOUNT" for i in inventory),
        parse_issues=len(issues), repeated_within_scope_signatures=sum(v-1 for v in signatures.values()),
        repeated_xlsx_ticket_hashes=sum(v-1 for v in tickets.values()),
        grouping_labels=GROUPS, summaries=summaries,
        all_source_sha256_unchanged=all(digest(p.read_bytes()) == h for p, h in hashes.items()))
    if not result["all_source_sha256_unchanged"]:
        raise RuntimeError("Source hash changed")
    (out / "summary.json").write_text(json.dumps(result, default=str, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.input, args.output)
    print(json.dumps({k: v for k, v in result.items() if k not in ("summaries", "grouping_labels")}, ensure_ascii=True, indent=2))
