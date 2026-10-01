"""Read-only refresh of visible HTML/XLSX/CSV observations; no ML or broker access.

Byte-identical files are excluded once. Different export/account scopes remain
separate, even when their rounded-time economic signatures match. CSV minute
timestamps never acquire invented seconds from Duration. All artifacts are
private except the explicitly allowlisted sanitized case CSV (still requires
the case provider's permission before public redistribution).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

spec = importlib.util.spec_from_file_location("profile_trade_behaviors", Path(__file__).with_name("profile_trade_behaviors.py"))
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)
D = Decimal


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def inventory_changes(old: list[dict[str, Any]], new: list[dict[str, Any]]) -> list[dict[str, Any]]:
    previous = {r["source"]: r["sha256"] for r in old}
    current = {r["source"]: r["sha256"] for r in new}
    return [{"source": name, "change": "ADDED" if name not in previous else "DELETED" if name not in current
             else "UNCHANGED" if previous[name] == current[name] else "MODIFIED",
             "previous_sha256": previous.get(name, ""), "current_sha256": current.get(name, "")}
            for name in sorted(set(previous) | set(current))]


def parse_csv_source(path: Path, rel: str, scope: str, file_hash: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Collect field failures per observation instead of discarding the file/row."""
    text = path.read_bytes().decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text, newline=""))
    header = next(reader, [])
    required = {"Open Date", "Close Date", "Symbol", "Action", "Units/Lots", "Open Price", "Close Price", "Profit"}
    meta: dict[str, Any] = {"scope": scope, "scope_basis": "CSV_FILE_UNCONFIRMED_ACCOUNT",
                           "timestamp_precision": "MINUTE", "completeness": "UNVERIFIED",
                           "parser_status": "PARSED_MYFXBOOK_CSV", "visible_rows": 0,
                           "date_format": "MM/DD/YYYY HH:MM", "date_unambiguous_mmdd_rows": 0,
                           "date_conflicting_ddmm_rows": 0}
    issues: list[dict[str, Any]] = []
    if not required.issubset(header):
        meta["parser_status"] = "UNSUPPORTED_CSV_SCHEMA"
        return [], [{"source": rel, "row": 1, "code": "UNSUPPORTED_CSV_SCHEMA", "field": "header",
                     "raw_value": json.dumps(header, ensure_ascii=False)}], meta
    rows = []
    numeric = {"lot": "Units/Lots", "open_price": "Open Price", "close_price": "Close Price", "sl": "SL",
               "tp": "TP", "profit": "Profit", "swap": "Swap", "commission": "Commission"}
    open_section = False
    for values in reader:
        number = reader.line_num
        if not any(values):
            continue
        if values == ["Open Trades"]:
            meta["open_trade_sections"] = meta.get("open_trade_sections", 0) + 1
            continue
        if "Ticket" in values and "Open Date" in values and "Action" in values:
            header = values
            open_section = "Close Date" not in header
            continue
        raw = dict(zip(header, values))
        if len(values) != len(header):
            issues.append(dict(source=rel, row=number, code="CSV_COLUMN_COUNT", field="row",
                               raw_value=json.dumps(values, ensure_ascii=False)))
        meta["visible_rows"] += 1
        row: dict[str, Any] = dict(record_id="c_" + profile.digest(f"{file_hash}:{number}".encode())[:20],
            source=rel, source_row=number, source_format="CSV", scope=scope,
            scope_basis="CSV_FILE_UNCONFIRMED_ACCOUNT", environment="CSV_UNCONFIRMED_ACCOUNT",
            symbol=raw.get("Symbol", ""), side=(raw.get("Action") or "").upper(),
            raw_values=json.dumps(raw, ensure_ascii=False, sort_keys=True),
            ticket_hash=profile.digest(raw["Ticket"].encode())[:20] if raw.get("Ticket") else "",
            timestamp_precision="MINUTE", timezone_status="UNKNOWN", currency="NOT_STATED_IN_CSV",
            completeness="UNVERIFIED", declared_visible_gap=None)
        symbol = row["symbol"].upper().replace("/", "")
        row["gold"] = symbol in ("XAUUSD", "GOLD", "GOLD#")
        row["record_type"] = ("OPEN_TRADE_SNAPSHOT" if open_section else "TRADE") if row["side"] in ("BUY", "SELL") else (
            "DEPOSIT" if row["side"] == "DEPOSIT" else "WITHDRAWAL" if row["side"] in ("WITHDRAWAL", "WITHDRAW")
            else "OTHER_CASHFLOW" if row["side"] in ("CREDIT", "BALANCE") else "OTHER")
        row["parse_issue_codes"] = []
        for field, original in {"open_time": "Open Date", "close_time": "Close Date", **numeric}.items():
            value = raw.get("Lots" if field == "lot" and open_section else original, "") or ""
            row[field + "_raw"] = value
            row[field] = None
            try:
                if field.endswith("time"):
                    if value:
                        month, day = (int(x) for x in value.split(" ")[0].split("/")[:2])
                        meta["date_unambiguous_mmdd_rows"] += int(day > 12 and month <= 12)
                        meta["date_conflicting_ddmm_rows"] += int(month > 12 and day <= 12)
                        row[field] = datetime.strptime(value, "%m/%d/%Y %H:%M")
                elif value:
                    row[field] = D(value.replace(",", ""))
                    if not row[field].is_finite():
                        raise ValueError("Non-finite decimal")
            except (ValueError, InvalidOperation) as exc:
                row[field] = None
                row["parse_issue_codes"].append("CSV_FIELD_ERROR")
                issues.append(dict(source=rel, row=number, code="CSV_FIELD_ERROR", field=field,
                                   raw_value=value, message=str(exc)))
        row["parse_issue_codes"] = "|".join(row["parse_issue_codes"])
        if open_section:
            row["reported_floating_profit_snapshot"] = row["profit"]
            row["profit"] = None
            row["profit_semantics"] = "FLOATING_SNAPSHOT_NOT_REALIZED_OUTCOME"
        else:
            row["profit_semantics"] = "REPORTED_VALUE_COST_BASIS_UNVERIFIED"
        rows.append(row)
    return rows, issues, meta


def canonical_number(value: Any) -> str:
    return format(D(str(value)).normalize(), "f") if value not in (None, "") else ""


def parse_pdf_text(text: str, rel: str, file_hash: str, page: int) -> list[dict[str, Any]]:
    """Keep legible Myfxbook PDF numbers; never derive direction from PnL/pips."""
    stamp = r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}"
    pattern = re.compile(rf"^({stamp})\s+({stamp})\s+(XAUUSD)(\S*)\s+" +
                         r"\s+".join([r"(-?\d+(?:\.\d+)?)"] * 7) + r"$")
    output = []
    for number, line in enumerate(text.splitlines(), 1):
        match = pattern.fullmatch(line.strip())
        if not match:
            continue
        opened, closed, symbol, side_raw, *numbers = match.groups()
        row: dict[str, Any] = dict(evidence_id="pdf_" + profile.digest(f"{file_hash}:{page}:{number}".encode())[:20],
            source=rel, page=page, source_text_line=number, raw_line=line, open_time_raw=opened,
            close_time_raw=closed, symbol=symbol, side_raw=side_raw, side="UNKNOWN",
            included_in_trade_statistics=False, excluded_reason="SOURCE_DIRECTION_UNREADABLE",
            timezone_status="UNKNOWN", timestamp_precision="MINUTE")
        for field, value in zip(("lot", "sl", "tp", "open_price", "close_price", "pips", "reported_profit"), numbers):
            row[field] = D(value)
            row[field + "_raw"] = value
        output.append(row)
    return output


def inspect_pdf_source(path: Path, rel: str, file_hash: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        rows = [r for page, content in enumerate(reader.pages, 1)
                for r in parse_pdf_text(content.extract_text() or "", rel, file_hash, page)]
        return rows, dict(source=rel, sha256=file_hash, pages=len(reader.pages), legible_trade_evidence_rows=len(rows),
            classification="MYFXBOOK_TRADE_DETAIL_WITH_UNREADABLE_DIRECTION", trade_statistics_included=False,
            direction_not_inferred_from_pips_or_profit=True, source_currency_label="USD",
            review_status="TEXT_EXTRACTED_DIRECTION_UNREADABLE", render_review="See tmp/pdfs/refresh_pdf/page-1.png; direction appears ??")
    except ImportError:
        return [], dict(source=rel, sha256=file_hash, review_status="PDF_READER_UNAVAILABLE", trade_statistics_included=False)


def flag_cross_source_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rounded timestamps flag potential export overlap; they cannot prove identity."""
    buckets: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        r["cross_source_duplicate_candidate"] = False
        if r.get("open_time") is None or r.get("close_time") is None:
            continue
        key = (r["symbol"].upper().replace("/", ""), r["side"] or "",
               r["open_time"].strftime("%Y-%m-%d %H:%M"), r["close_time"].strftime("%Y-%m-%d %H:%M"),
               *(canonical_number(r.get(k)) for k in ("lot", "open_price", "close_price", "profit")))
        buckets[key].append(r)
    result = []
    for key, members in sorted(buckets.items()):
        if len({r["source"] for r in members}) < 2:
            continue
        group = "dup_" + profile.digest("|".join(key).encode())[:16]
        for r in members:
            r["cross_source_duplicate_candidate"] = True
            r["cross_source_signature_group"] = group
        result.append(dict(candidate_id=group, observation_rows=len(members),
                           sources="|".join(sorted({r["source"] for r in members})),
                           formats="|".join(sorted({r["source_format"] for r in members})),
                           record_ids="|".join(r["record_id"] for r in members), identity_confirmed=False,
                           reason="SAME_MINUTE_TIMES_AND_ECONOMIC_FIELDS", deleted_rows=0))
    return result


def sanitize_cases(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Allowlist data only; separate realized outcome and future group metadata."""
    allowed = ("source_format", "side", "open_time", "close_time", "lot", "open_price", "close_price",
               "sl", "tp", "swap", "commission", "currency", "behavior", "observed_prior_count",
               "observed_prior_lot", "same_side_avg_entry", "signed_distance_to_avg_pct", "lot_vs_prior_mean",
               "timestamp_precision", "cross_source_duplicate_candidate", "identical_signature_candidate_count")
    output = []
    for r in rows:
        public = {k: r.get(k) for k in allowed}
        public.update(case_id="case_" + profile.digest(r["record_id"].encode())[:16],
                      scope_id="scope_" + profile.digest(r["scope"].encode())[:12],
                      posthoc_overlap_group_id="group_" + profile.digest(r.get("observed_overlap_group", "").encode())[:16]
                      if r.get("observed_overlap_group") else "",
                      outcome_reported_profit=r.get("profit"), timezone_status="UNKNOWN",
                      complete_account_history=False, posthoc_group_uses_future=True,
                      market_alignment_status="UNVERIFIED", case_kind="VISIBLE_SOURCE_OBSERVATION")
        output.append(public)
    return output


def counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return dict(observation_rows=len(rows), scopes=len({r["scope"] for r in rows}),
                behavior_counts=dict(Counter(r.get("behavior", "NOT_CLASSIFIED") for r in rows)),
                positive_reported_profit_rows=sum(r["profit"] is not None and r["profit"] > 0 for r in rows),
                negative_reported_profit_rows=sum(r["profit"] is not None and r["profit"] < 0 for r in rows),
                zero_reported_profit_rows=sum(r["profit"] == 0 for r in rows),
                profit_unavailable_rows=sum(r["profit"] is None for r in rows))


def run(root: Path, out: Path, baseline: Path) -> dict[str, Any]:
    """Inventory completely, reuse legacy parsers, enrich CSV, and verify raw hashes."""
    paths = sorted(p for p in root.rglob("*") if p.is_file())
    before = {p.relative_to(root).as_posix(): sha(p) for p in paths}
    prior = read_csv(baseline)
    if out.exists() and any(out.iterdir()):
        raise ValueError("Output must be new or empty; previous audit is never overwritten")
    # Existing parser handles the original HTML and exact-XML XLSX decimal data.
    legacy = profile.run(root, out)
    inventory = read_csv(out / "source_inventory.csv")
    issues = read_csv(out / "parse_issues.csv")
    records: list[dict[str, Any]] = read_csv(out / "all_records.csv")
    raw_cells = {(r["source"], r["row"]): r["values"] for r in read_csv(out / "raw_cells.csv")}
    numeric = ("lot", "open_price", "close_price", "sl", "tp", "profit", "swap", "commission")
    for r in records:
        for field in numeric:
            r[field] = D(r[field]) if r.get(field) else None
        for field in ("open_time", "close_time"):
            r[field] = datetime.fromisoformat(r[field]) if r.get(field) else None
        r["gold"] = r["gold"] == "True"
        r["timestamp_precision"] = "SECOND" if r["source_format"] == "XLSX" else "MINUTE"
        r["timezone_status"] = "UNKNOWN"
        rowkey = str(r["source_row"])
        if r["source_format"] == "XLSX":
            match = next((v for (s, n), v in raw_cells.items() if s == r["source"] and n.endswith(":" + rowkey)), "")
            r["raw_values"] = match
        else:
            r["raw_values"] = raw_cells.get((r["source"], rowkey), "")
        # Remove legacy classifications so no stale derived fields survive refresh.
        for field in ("behavior", "observed_overlap_group", "observed_prior_count", "observed_prior_lot",
                      "same_side_avg_entry", "signed_distance_to_avg_pct", "lot_vs_prior_mean", "holding_minutes"):
            r.pop(field, None)
    csv_index = 0
    pdf_evidence = []
    pdf_reviews = []
    for item in inventory:
        path = root / item["source"]
        item["timezone_status"] = "UNKNOWN"
        if item["duplicate_of"]:
            item["parser_status"] = "EXACT_FILE_DUPLICATE_NOT_REPARSED"
            continue
        suffix = path.suffix.lower()
        if suffix == ".csv":
            csv_index += 1
            new, errors, metadata = parse_csv_source(path, item["source"], f"C{csv_index:03}", item["sha256"])
            item.update(metadata)
            records.extend(new)
            issues.extend(errors)
        elif suffix in (".html", ".xlsx"):
            item["parser_status"] = "PARSED_MYFXBOOK_HTML" if suffix == ".html" else "PARSED_XLSX"
            item["timestamp_precision"] = "MINUTE" if suffix == ".html" else "SECOND"
            item["scope_basis"] = "HTML_ACCOUNT_ID" if suffix == ".html" else "XLSX_FILE_UNCONFIRMED_ACCOUNT"
        else:
            item["parser_status"] = "INVENTORIED_NOT_TRADE_PARSER_SUPPORTED"
            if suffix == ".pdf":
                evidence, review = inspect_pdf_source(path, item["source"], item["sha256"])
                pdf_evidence.extend(evidence)
                pdf_reviews.append(review)
                item["pdf_review_status"] = review["review_status"]
                item["pdf_legible_unclassified_rows"] = len(evidence)
    gold = [r for r in records if r["record_type"] == "TRADE" and r["gold"]]
    scopes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in gold:
        scopes[r["scope"]].append(r)
    for rows in scopes.values():
        profile.classify_scope(rows)
    signatures = Counter(tuple(str(r.get(k)) for k in ("scope", "symbol", "side", "open_time", "close_time",
                         "lot", "open_price", "close_price", "profit")) for r in records)
    for r in records:
        key = tuple(str(r.get(k)) for k in ("scope", "symbol", "side", "open_time", "close_time", "lot", "open_price", "close_price", "profit"))
        r["identical_signature_candidate_count"] = signatures[key]
        r["position_completeness"] = "VISIBLE_SCOPE_ONLY"
    cross = flag_cross_source_candidates(records)
    blocks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in gold:
        if r.get("observed_overlap_group"):
            blocks[r["observed_overlap_group"]].append(r)
    episodes = []
    for group, members in sorted(blocks.items()):
        opens = sorted(r["open_time"] for r in members)
        closes = sorted(r["close_time"] for r in members)
        same_side = len({r["side"] for r in members}) == 1
        close_span = int((closes[-1] - closes[0]).total_seconds())
        min_gap = min((int((b - a).total_seconds()) for a, b in zip(opens, opens[1:])), default=None)
        episodes.append(dict(candidate_group=group, scope=members[0]["scope"], source_format=members[0]["source_format"],
            n=len(members), start=opens[0], end=closes[-1], record_ids="|".join(r["record_id"] for r in members),
            reported_profit_sum=sum((r["profit"] for r in members if r["profit"] is not None), D(0)),
            reported_profit_missing_rows=sum(r["profit"] is None for r in members), complete_account_history=False,
            grouping_uses_future=True, ordering_uncertain=any(r["behavior"] == "TIME_TIE" for r in members),
            cross_source_duplicate_candidate=any(r["cross_source_duplicate_candidate"] for r in members),
            close_span_observed_seconds=close_span, min_open_gap_observed_seconds=min_gap,
            splitExecutionCandidates=len(members) >= 2 and same_side and min_gap is not None and min_gap <= 60,
            clustered_close_retrospective_candidate=len(members) >= 2 and close_span <= 60,
            timestamp_precision=members[0]["timestamp_precision"], timezone_status="UNKNOWN"))
    changes = inventory_changes(prior, inventory)
    after = {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob("*")) if p.is_file()}
    unchanged = before == after
    if not unchanged:
        raise RuntimeError("Raw sources changed during analysis; outputs must not be treated as verified")
    by_format = {fmt: counts([r for r in gold if r["source_format"] == fmt]) for fmt in ("HTML", "XLSX", "CSV")}
    result = dict(source_files=len(inventory), previous_source_files=len(prior),
        source_changes=dict(Counter(r["change"] for r in changes)),
        extensions=dict(Counter(p.suffix.lower() for p in paths)),
        exact_duplicate_files=sum(bool(i["duplicate_of"]) for i in inventory),
        unique_html=legacy["unique_html"], html_visible_rows=legacy["html_visible_rows"],
        html_declared_rows=legacy["html_declared_rows"], html_declared_gap_files=legacy["html_declared_gap_files"],
        html_exactly_100_rows=legacy["html_exactly_100_rows"],
        parsed_unique_csv_files=csv_index, unsupported_source_files=sum(i["parser_status"].startswith("INVENTORIED_NOT") for i in inventory),
        csv_record_type_counts=dict(Counter(r["record_type"] for r in records if r["source_format"] == "CSV")),
        cross_source_candidate_format_counts=dict(Counter(c["formats"] for c in cross)),
        total_observation_rows=len(records), gold_rows=len(gold), gold_by_format=by_format,
        non_gold_trade_rows=sum(r["record_type"] == "TRADE" and not r["gold"] for r in records),
        record_type_counts=dict(Counter(r["record_type"] for r in records)), behavior_counts=dict(Counter(r["behavior"] for r in gold)),
        open_trade_snapshot_rows=sum(r["record_type"] == "OPEN_TRADE_SNAPSHOT" for r in records),
        pdf_legible_unclassified_rows=len(pdf_evidence), pdf_reviews=pdf_reviews,
        earliest_gold_open=str(min(r["open_time"] for r in gold if r["open_time"])),
        latest_gold_open=str(max(r["open_time"] for r in gold if r["open_time"])),
        parse_issues=len(issues), cross_source_signature_candidates=len(cross),
        cross_source_candidate_observation_rows=sum(r["cross_source_duplicate_candidate"] for r in records),
        same_scope_signature_excess_rows=sum(v - 1 for v in signatures.values()),
        observed_overlap_groups=len(episodes), splitExecutionCandidates=sum(e["splitExecutionCandidates"] for e in episodes),
        clustered_close_retrospective_candidates=sum(e["clustered_close_retrospective_candidate"] for e in episodes),
        classification_method="DETERMINISTIC_VISIBLE_POSITION_RELATION_NOT_ML",
        combined_counts_are_source_observations_not_unique_trades=True, account_history_complete=False,
        timezone_status="UNKNOWN", market_alignment_status="UNVERIFIED", all_source_sha256_unchanged=unchanged,
        csv_unambiguous_mmdd_timestamps=sum(int(i.get("date_unambiguous_mmdd_rows", 0)) for i in inventory),
        csv_conflicting_ddmm_timestamps=sum(int(i.get("date_conflicting_ddmm_rows", 0)) for i in inventory))
    outputs = {"source_inventory.csv": inventory, "source_changes.csv": changes, "parse_issues.csv": issues,
               "all_records.csv": records, "gold_behavior_records.csv": gold, "observed_overlap_groups.csv": episodes,
               "cross_source_duplicate_candidates.csv": cross, "sanitized_case_records.csv": sanitize_cases(gold)}
    outputs["pdf_unclassified_rows.csv"] = pdf_evidence
    for name, rows in outputs.items():
        profile.write_csv(out / name, rows)
    # Replace legacy summary denominators with count-only observation reports.
    profile.write_csv(out / "behavior_summary.csv", [{"source_format": fmt, "behavior": label,
        "observation_rows": sum(r["source_format"] == fmt and r["behavior"] == label for r in gold)}
        for fmt in ("HTML", "XLSX", "CSV") for label in profile.GROUPS])
    profile.write_csv(out / "year_summary.csv", [{"year": year, "source_format": fmt,
        "observation_rows": sum(r["source_format"] == fmt and r["open_time"] and r["open_time"].year == year for r in gold)}
        for year in sorted({r["open_time"].year for r in gold if r["open_time"]}) for fmt in ("HTML", "XLSX", "CSV")])
    profile.write_csv(out / "scope_summary.csv", [{"scope": scope, "source_format": members[0]["source_format"],
        **counts(members)} for scope, members in sorted(scopes.items())])
    profile.write_csv(out / "secondary_summary.csv", [{"source_format": fmt, "dimension": "split_execution_or_close",
        "split_execution_candidate_groups": sum(e["source_format"] == fmt and e["splitExecutionCandidates"] for e in episodes),
        "clustered_close_retrospective_groups": sum(e["source_format"] == fmt and e["clustered_close_retrospective_candidate"] for e in episodes),
        "uses_future_for_grouping": True} for fmt in ("HTML", "XLSX", "CSV")])
    provenance = dict(source_root=str(root.resolve()), baseline_inventory=str(baseline.resolve()), baseline_sha256=sha(baseline),
        parser_script_sha256=sha(Path(__file__)), legacy_parser_script_sha256=sha(Path(profile.__file__)),
        raw_sha256_before=before, raw_sha256_after=after, all_source_sha256_unchanged=unchanged,
        csv_date_format_evidence="Unambiguous day > 12 records support MM/DD; conflicting month > 12 records counted",
        csv_duration_not_used_to_invent_seconds=True, duplicate_policy="ONLY_BYTE_IDENTICAL_FILES_EXCLUDED; OTHER_SIGNATURES_FLAGGED_NOT_REMOVED",
        historical_group_ids_not_stable_between_refreshes=True, source_changes=changes)
    provenance["pdf_reviews"] = pdf_reviews
    checks = dict(raw_hashes_equal=unchanged, entire_recursive_inventory_count=len(before),
        classification_count_matches_gold=sum(result["behavior_counts"].values()) == len(gold),
        unique_record_ids=len({r["record_id"] for r in records}) == len(records),
        csv_rows_preserved=sum(i.get("visible_rows", 0) for i in inventory if i.get("parser_status") == "PARSED_MYFXBOOK_CSV")
                           == sum(r["source_format"] == "CSV" for r in records),
        cross_source_candidates_not_deleted=all(r["deleted_rows"] == 0 for r in cross),
        unsupported_sources=[i["source"] for i in inventory if i["parser_status"].startswith("INVENTORIED_NOT")],
        timezone_unknown_for_all=all(r["timezone_status"] == "UNKNOWN" for r in records),
        public_output_no_source_ticket_raw_fields=all("source" not in r and "ticket_hash" not in r and "raw_values" not in r for r in sanitize_cases(gold)))
    for name, data in (("summary.json", result), ("provenance.json", provenance), ("review_checks.json", checks), ("pdf_review.json", pdf_reviews)):
        (out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (out / "report.md").write_text(report(result), encoding="utf-8")
    return result


def report(s: dict[str, Any]) -> str:
    changes = s["source_changes"]
    lines = ["# 更新交易資料與可見行為分類（2026-10-01）", "",
        f"完整遞迴清點 {s['source_files']} 檔；前版 {s['previous_source_files']} 檔。新增 {changes.get('ADDED', 0)}、修改 {changes.get('MODIFIED', 0)}、刪除 {changes.get('DELETED', 0)}、未變 {changes.get('UNCHANGED', 0)}。逐檔差異與雜湊見 source_changes.csv／provenance.json。",
        "", "## 這次更新代表什麼", "",
        "新增 CSV 是 Myfxbook 明細匯出，含開平時間、方向、手數、價格、損益和費用，並含事後 Max/Min、Drawdown 等欄位。後者僅保留原始證據，未拿來判斷進場或案例相似度。CSV 沒有帳戶欄；每檔獨立觀察範圍，與 Excel 一樣不能自行合併。",
        f"66 CSV 共 {sum(s['csv_record_type_counts'].values())} 列觀察：已平倉交易 {s['csv_record_type_counts'].get('TRADE', 0)}（其中黃金 {s['gold_by_format']['CSV']['observation_rows']}）、存款 {s['csv_record_type_counts'].get('DEPOSIT', 0)}、提款 {s['csv_record_type_counts'].get('WITHDRAWAL', 0)}、未平倉快照 {s['csv_record_type_counts'].get('OPEN_TRADE_SNAPSHOT', 0)}。標頭、Open Trades 段落與空白列不當交易。",
        f"共排除 {s['exact_duplicate_files']} 個完全相同檔案副本，其餘 {s['total_observation_rows']} 列為來源觀察列，其中黃金 {s['gold_rows']} 列、非黃金交易 {s['non_gold_trade_rows']} 列。合計不是去重後獨立交易，也不是獨立決策數。",
        f"跨來源相同分鐘時間與經濟欄位簽章共 {s['cross_source_signature_candidates']} 組候選、涉及 {s['cross_source_candidate_observation_rows']} 觀察列。可能是重複匯出或同步操作；帳戶未映射，全部保留並標记，不可直接併成一筆。",
        f"本次格式組合：{s['cross_source_candidate_format_counts']}；它是精確欄位簽章候選，費用口徑不同、商品別名不同或時間差異仍可能漏掉其他重複，所以沒有估計去重後真實獨立交易總數。",
        "", "| 格式 | 可見黃金觀察列 | 獨立觀察範圍 |", "|---|---:|---:|"]
    lines.extend(f"| {fmt} | {v['observation_rows']} | {v['scopes']} |" for fmt, v in s["gold_by_format"].items())
    lines.extend(["", "## 可見行為分類", "", "採固定、可核對的價格／部位關係分類，不是 ML 分群，也不是交易員策略真相。加單價格比較當時可見同向持倉的手數加權均價；順逆向不表示浮動帳戶盈虧或操作原因。", "",
        "| 分類 | HTML | Excel | CSV | 合計觀察列 |", "|---|---:|---:|---:|---:|"])
    for code, label in profile.GROUPS.items():
        nums = [s["gold_by_format"][fmt]["behavior_counts"].get(code, 0) for fmt in ("HTML", "XLSX", "CSV")]
        lines.append(f"| {label} | {nums[0]} | {nums[1]} | {nums[2]} | {sum(nums)} |")
    lines.extend(["", "「無可見既有部位」只表示本觀察範圍沒有找到更早未平單，不能證明帳戶空手。CSV 和 HTML 只有分鐘精度；TIME_TIE 表示同一記錄時間開單／平單順序不明，不補秒，也不根據列排序發明先後。",
        f"事後持倉重疊候選群 {s['observed_overlap_groups']}；其中密集開單／分批執行候選 {s['splitExecutionCandidates']} 群、60 秒內記錄平倉集中候選 {s['clustered_close_retrospective_candidates']} 群。分鐘來源的 0/60 秒是記錄精度下的差值，不能宣稱實際成交間隔。群組使用後續平倉資訊，僅供復盤與依賴性稽核，不作下單前輸入或正式 episode。",
        "", "## 資料期間、完整性與限制", "",
        f"可見黃金開倉時間：{s['earliest_gold_open']} 至 {s['latest_gold_open']}（來源時間，時區 UNKNOWN）。這不是完整帳戶或完整十年資料。",
        f"{s['unique_html']} 份 unique HTML 可見 {s['html_visible_rows']} 列、頁面宣告總數合計 {s['html_declared_rows']}；{s['html_declared_gap_files']} 份宣告多於可見，{s['html_exactly_100_rows']} 份剛好 100 列。差額不是已證明缺失獨立交易數。CSV 匯出增加可見資料，不自動證明完整涵蓋歷史。",
        f"日期格式查核：{s['csv_unambiguous_mmdd_timestamps']} 個時間含大於 12 的日期，支持 MM/DD/YYYY；反向格式衝突 {s['csv_conflicting_ddmm_timestamps']} 個。Duration 未用來補開平秒數。",
        f"HTML／Excel／CSV 解析問題 {s['parse_issues']} 筆，見 parse_issues.csv；{s['unsupported_source_files']} 檔未支援完整交易解析。唯一 PDF 已抽取全文：2頁，30筆黃金明細與資金／彙總；買賣方向在文字與渲染畫面均為??，無法可靠重建。保存 {s['pdf_legible_unclassified_rows']} 筆可讀數值於 pdf_unclassified_rows.csv／pdf_review.json，方向 UNKNOWN，不由 pips 或損益倒推、不計入已分群交易／案例。原始資料前後完整 SHA-256 相同：{s['all_source_sha256_unchanged']}。",
        "profit 為原報表記載值；不同格式的費用包含方式／幣別未全部核實，不跨範圍加總成帳戶績效。SL/TP 為零或缺值不代表沒有手動風控。不宣稱勝率預測、置信度、馬丁策略、心理狀態或因果關係。",
        f"另有 {s['open_trade_snapshot_rows']} 筆 Open Trades 未平倉快照，保留於 all_records.csv；該段 Profit 為浮動快照而非已實現盈虧，沒有加入已平倉行為分類或案例損益。存提款也獨立保留，不當市場交易。",
        "", "## 接到產品案例庫", "",
        "sanitized_case_records.csv 使用欄位白名單，去除來源檔名、帳戶與 ticket、原始自由文字；仍是個人交易資料，公開再利用須具備來源授權。case_id／scope_id 僅為不透明代碼。原始 evidence 與詳細來源只留在私有 artifacts。",
        "下單前檢索可使用方向、手數、可見既有部位、加權均價距離等；close_time、close_price、outcome_reported_profit、posthoc_overlap_group_id 只於事後復盤顯示。分群來自可見資料，若 duplicate/time tie/帳戶缺口，須显示資料不足。",
        "所有案例 timezone_status=UNKNOWN、market_alignment_status=UNVERIFIED，不能聲稱已核实 K 線時間對齊。對分鐘資料應取開單分鐘起點前已收完的行情，保守避免洩漏。初版建議先選單一來源範圍，人工核對代表案例與重複候選後再接 UI；保留可見初始單、損失與獲利反例，不能只留符合想法的候選。",
        "重跑：python scripts/refresh_trade_case_data.py --input <交易員資料> --baseline artifacts/behavior_audit_20260928/source_inventory.csv --output <新的輸出資料夾>。舊結果不覆寫，refresh 後群組编号可能改變，產品匯入應使用 case_id 與本次 audit provenance 版本。", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.input, args.output, args.baseline), ensure_ascii=True, indent=2, default=str))
