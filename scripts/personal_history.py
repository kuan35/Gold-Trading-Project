"""Public reference-time validation and source-bound personal history planning.

This module never reads broker credentials or sends an order. Reference times
remain PROJECT_REFERENCE hypotheses; the trader's original clock is UNKNOWN.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path


SCHEMA = 'trader_case_reference_times_v1'
REFERENCE_FIELDS = frozenset({
    'case_id', 'candidate_open_utc', 'candidate_close_utc',
    'entry_bar_utc', 'exit_bar_utc', 'candidate_clock_basis',
    'marker_status', 'timezone_status', 'production_enabled',
    'frozen_boundary_policy_difference',
})
TOP_FIELDS = frozenset({'schema', 'alignment_scope', 'clock_status', 'cases'})
WEEK = 7 * 86400
PERIODS = {'5m': 300, '1h': 3600}


def _second(value: str) -> int:
    if not isinstance(value, str):
        raise ValueError('REFERENCE_TIME_NOT_UTC')
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise ValueError('REFERENCE_TIME_NOT_UTC') from error
    if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
        raise ValueError('REFERENCE_TIME_NOT_UTC')
    return int(stamp.timestamp())


def validate_references(payload: dict, public_case_ids: set[str]) -> list[dict]:
    """Reject added private fields and any ID outside the published case index."""
    if (not isinstance(payload, dict) or set(payload) != TOP_FIELDS
            or payload['schema'] != SCHEMA
            or payload['alignment_scope'] != 'PROJECT_REFERENCE'
            or payload['clock_status'] != 'UNKNOWN'
            or not isinstance(payload['cases'], list)):
        raise ValueError('INVALID_REFERENCE_HEADER')
    ids = set()
    for row in payload['cases']:
        if not isinstance(row, dict) or set(row) != REFERENCE_FIELDS:
            raise ValueError('REFERENCE_FIELD_NOT_ALLOWED')
        ident = row['case_id']
        if not isinstance(ident, str) or ident not in public_case_ids or ident in ids:
            raise ValueError('INVALID_REFERENCE_CASE_ID')
        ids.add(ident)
        opened, closed = _second(row['candidate_open_utc']), _second(row['candidate_close_utc'])
        entry, exit_ = _second(row['entry_bar_utc']), _second(row['exit_bar_utc'])
        if (closed < opened or entry != opened // 300 * 300
                or exit_ != closed // 300 * 300
                or row['marker_status'] != 'BOTH_MARKERS_AVAILABLE'
                or row['timezone_status'] != 'UNKNOWN'
                or row['production_enabled'] is not False
                or row['frozen_boundary_policy_difference'] is not False
                or row['candidate_clock_basis'] not in
                ('ledger_price_hypothesis', 'source_model_scenario')):
            raise ValueError('INVALID_REFERENCE_MARKER')
    if ids != public_case_ids:
        raise ValueError('REFERENCE_INDEX_COVERAGE_MISMATCH')
    return sorted(payload['cases'], key=lambda row: row['case_id'])


def export_references(alignment: list[dict], public_index: dict) -> dict:
    ids = {row['id'] for row in public_index['cases']}
    if len(ids) != len(public_index['cases']):
        raise ValueError('DUPLICATE_PUBLIC_INDEX_ID')
    rows = [{key: row[key] for key in REFERENCE_FIELDS}
            for row in alignment if row.get('case_id') in ids]
    payload = dict(schema=SCHEMA, alignment_scope='PROJECT_REFERENCE',
                   clock_status='UNKNOWN', cases=rows)
    payload['cases'] = validate_references(payload, ids)
    return payload


def plan_reference_download(references: list[dict], *, now: int | None = None,
                            max_holding_days: int = 60) -> list[dict]:
    """Deduplicate weekly M5/H1 requests over all usable reference windows."""
    if now is None:
        now = int(datetime.now(timezone.utc).timestamp())
    wanted = {interval: set() for interval in PERIODS}
    for row in references:
        opened = _second(row['candidate_open_utc'])
        closed = _second(row['candidate_close_utc'])
        if closed > now:
            continue
        # Session closures may interrupt the 60 complete 15m and 20 H1 bars.
        # Give the pre-entry indicators two calendar weeks of source history.
        start = opened - 14 * 86400
        end = min(now, max(opened + 3600, min(closed, opened + max_holding_days * 86400)) + 3600)
        for interval in PERIODS:
            for week in range(start // WEEK * WEEK, end // WEEK * WEEK + WEEK, WEEK):
                wanted[interval].add(week)
    return [dict(interval=interval, start=week, end=week + WEEK)
            for interval in PERIODS for week in sorted(wanted[interval])]


def public_reference_status(root: Path) -> dict:
    data = root / 'frontend/public/data'
    try:
        index = json.loads((data / 'trader-market-index.json').read_text(encoding='utf-8'))
        references = json.loads((data / 'trader-case-reference-times.json').read_text(encoding='utf-8'))
        rows = validate_references(references, {row['id'] for row in index['cases']})
        years = dict(sorted(Counter(datetime.fromtimestamp(_second(row['candidate_open_utc']), timezone.utc).year
                                    for row in rows).items()))
        return dict(status='READY', count=len(rows), by_reference_year=years,
                    sha256=sha256((data / 'trader-case-reference-times.json').read_bytes()).hexdigest())
    except (OSError, ValueError, KeyError, TypeError):
        return dict(status='UNAVAILABLE', count=0)
