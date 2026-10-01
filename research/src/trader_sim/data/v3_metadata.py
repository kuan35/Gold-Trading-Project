"""Conservative metadata for v3 pre-action datasets."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
import hashlib
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True, slots=True)
class EpisodeMetadata:
    record_id: str
    candidate_episode_id: str
    episode_order_index: int
    episode_ordering_uncertain: bool
    cross_account_candidate_group_id: str | None


def _stable_id(prefix: str, values: Iterable[str]) -> str:
    raw = "\x1f".join(values)
    return prefix + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _cross_account_groups(
    record_ids: set[str],
    pair_rows: list[dict[str, str]],
) -> dict[str, str]:
    parent = {record_id: record_id for record_id in record_ids}

    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(first: str, second: str) -> None:
        root_first = find(first)
        root_second = find(second)
        if root_first != root_second:
            parent[max(root_first, root_second)] = min(root_first, root_second)

    for row in pair_rows:
        first = row.get("record_a", "")
        second = row.get("record_b", "")
        if first in parent and second in parent:
            union(first, second)

    components: dict[str, list[str]] = {}
    for record_id in sorted(record_ids):
        root = find(record_id)
        components.setdefault(root, []).append(record_id)

    result: dict[str, str] = {}
    for members in components.values():
        if len(members) < 2:
            continue
        group_id = _stable_id("cross_group_", sorted(members))
        for member in members:
            result[member] = group_id
    return result


def build_episode_metadata(
    records: list[dict[str, str]],
    basket_rows: list[dict[str, str]],
    cross_account_rows: list[dict[str, str]],
) -> dict[str, EpisodeMetadata]:
    """Map visible records to provisional episode and cross-account groups."""
    records_by_id = {row["record_id"]: row for row in records}
    episode_members: dict[str, list[str]] = {}
    assigned: dict[str, str] = {}
    for basket in sorted(basket_rows, key=lambda row: row.get("candidate_id", "")):
        candidate_id = basket["candidate_id"]
        members = [item for item in basket.get("record_ids", "").split("|") if item in records_by_id]
        if not members:
            continue
        for record_id in members:
            if record_id in assigned and assigned[record_id] != candidate_id:
                raise ValueError(f"record appears in multiple basket candidates: {record_id}")
            assigned[record_id] = candidate_id
        episode_members[candidate_id] = members

    for record_id in sorted(records_by_id):
        if record_id not in assigned:
            candidate_id = _stable_id("singleton_", [record_id])
            assigned[record_id] = candidate_id
            episode_members[candidate_id] = [record_id]

    cross_groups = _cross_account_groups(set(records_by_id), cross_account_rows)
    result: dict[str, EpisodeMetadata] = {}
    for candidate_id, members in sorted(episode_members.items()):
        ordered = sorted(
            members,
            key=lambda record_id: (
                _parse_time(records_by_id[record_id]["open_time"]),
                record_id,
            ),
        )
        minute_counts: dict[datetime, int] = {}
        for record_id in ordered:
            minute = _parse_time(records_by_id[record_id]["open_time"]).replace(second=0, microsecond=0)
            minute_counts[minute] = minute_counts.get(minute, 0) + 1
        uncertain = any(count > 1 for count in minute_counts.values())
        for index, record_id in enumerate(ordered, start=1):
            result[record_id] = EpisodeMetadata(
                record_id=record_id,
                candidate_episode_id=candidate_id,
                episode_order_index=index,
                episode_ordering_uncertain=uncertain,
                cross_account_candidate_group_id=cross_groups.get(record_id),
            )
    return result


def classify_period(open_time: datetime) -> tuple[str, str]:
    """Return a deliberately provisional period label, never a claimed change point."""
    if open_time.year <= 2022:
        label = "EARLIER_VISIBLE_PERIOD_CANDIDATE"
    elif open_time.year == 2023:
        label = "TRANSITION_DATE_UNKNOWN"
    elif open_time.year <= 2025:
        label = "RECENT_VISIBLE_PERIOD_CANDIDATE"
    else:
        label = "OUTSIDE_VISIBLE_PERIOD"
    return label, "UNCONFIRMED"


def load_confirmed_error_record_ids(case_paths: Iterable[Path]) -> set[str]:
    record_ids: set[str] = set()
    for path in case_paths:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                if row.get("record_id"):
                    record_ids.add(row["record_id"])
    return record_ids


def _as_bool(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def build_daily_observation(
    days: list[date],
    statement_audits: list[dict[str, str]],
    visible_trades: list[dict[str, str]],
) -> list[dict[str, object]]:
    """Describe source coverage without claiming every unseen day is a no-trade decision."""
    visible_days = {row["trading_day_utc"] for row in visible_trades}
    intervals: list[tuple[date, date, bool]] = []
    for audit in statement_audits:
        if not audit.get("min_time") or not audit.get("max_time"):
            continue
        intervals.append(
            (
                _parse_time(audit["min_time"]).date(),
                _parse_time(audit["max_time"]).date(),
                _as_bool(audit.get("is_truncated", "")),
            )
        )

    rows: list[dict[str, object]] = []
    for day in sorted(days):
        day_text = day.isoformat()
        covering = [item for item in intervals if item[0] <= day <= item[1]]
        if day_text in visible_days:
            status = "VISIBLE_TRADE"
        elif not covering:
            status = "OUTSIDE_OBSERVED_RANGE"
        elif any(item[2] for item in covering):
            status = "NO_VISIBLE_TRADE_PARTIAL_SOURCE_COVERAGE"
        else:
            status = "NO_VISIBLE_TRADE_FULL_SOURCE_COVERAGE"
        rows.append(
            {
                "trading_day_utc": day_text,
                "observation_status": status,
                "covering_source_count": len(covering),
                "truncated_covering_source_count": sum(item[2] for item in covering),
                "eligible_for_direction_model": False,
            }
        )
    return rows

