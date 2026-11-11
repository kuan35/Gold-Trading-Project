"""Build private case evidence from one account's native cTrader OHLCV chunks."""
from __future__ import annotations

from bisect import bisect_left
from collections import Counter
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from backend.candidate_profile import profile_before_entry
from backend.candidate_sidecar import load_candidate_sidecar
from backend.forward_outcomes import build_sidecar as build_outcomes
from backend.execution_store import build as build_execution
from scripts.build_native_volume_index import build as build_volume
from scripts.fetch_ctrader_history_volume import task_key
from scripts.personal_history import (plan_reference_download,
                                      validate_references, _second)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = {'demo': 'Pepperstone cTrader DEMO', 'live': 'Pepperstone cTrader LIVE'}


def _ref(root: Path, path: Path) -> dict:
    return dict(path=path.relative_to(root).as_posix(), sha256=sha256(path.read_bytes()).hexdigest())


def _json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True,
                               separators=(',', ':'), allow_nan=False) + '\n', encoding='utf-8')
    temp.replace(path)


def load_native_chunks(folder: Path, tasks: list[dict], environment: str) -> tuple[dict, str, list[str]]:
    """Keep gaps explicit; reject a different account or a modified chunk."""
    if environment not in SOURCE:
        raise ValueError('INVALID_ENVIRONMENT')
    by_frame = {'5m': {}, '1h': {}}
    identity = None
    missing = []
    for task in tasks:
        path = folder / (task_key(task) + '.json')
        if not path.is_file():
            missing.append(task_key(task))
            continue
        payload = json.loads(path.read_text(encoding='utf-8'))
        if (any(payload.get(key) != task[key] for key in ('interval', 'start', 'end'))
                or payload.get('source') != 'ctrader_' + environment + '_native'
                or payload.get('volume_basis') != 'broker_native_tick_count'
                or payload.get('status') not in ('AVAILABLE', 'EMPTY')):
            raise ValueError('CHUNK_SOURCE_OR_TASK_MISMATCH')
        key = payload.get('source_key')
        if not isinstance(key, str) or len(key) != 64:
            raise ValueError('INVALID_SOURCE_KEY')
        if identity is None:
            identity = key
        elif identity != key:
            raise ValueError('MIXED_SOURCE_IDENTITY')
        bars = payload.get('bars')
        if not isinstance(bars, list) or (payload['status'] == 'EMPTY') != (not bars):
            raise ValueError('INVALID_CHUNK_BARS')
        index = by_frame[task['interval']]
        previous = -1
        span = 300 if task['interval'] == '5m' else 3600
        for bar in bars:
            stamp = bar.get('time')
            if (type(stamp) is not int or stamp % span or not task['start'] <= stamp < task['end']
                    or stamp <= previous or type(bar.get('volume')) is not int or bar['volume'] < 0):
                raise ValueError('INVALID_NATIVE_BAR')
            from backend.forward_outcomes import _prices
            _prices(bar)
            if stamp in index and index[stamp] != bar:
                raise ValueError('CONFLICTING_NATIVE_BAR')
            index[stamp] = bar
            previous = stamp
    if identity is None:
        raise ValueError('NO_DOWNLOADED_CHUNKS')
    return by_frame, identity, missing


def build(private_root: Path, *, public_root: Path = ROOT / 'frontend/public/data',
          environment: str = 'demo', now: int | None = None,
          personal_base: Path = ROOT / 'private/personal_history') -> dict:
    """Rebuild in an isolated private directory; caller activates it separately."""
    private_root = Path(private_root).resolve()
    if not private_root.is_relative_to(Path(personal_base).resolve()):
        raise ValueError('PERSONAL_PRIVATE_FOLDER_REQUIRED')
    public_root = Path(public_root)
    case_source = public_root / 'trader-cases.json'
    case_bytes = case_source.read_bytes()
    cases_payload = json.loads(case_bytes)
    public_index = json.loads((public_root / 'trader-market-index.json').read_text(encoding='utf-8'))
    references = json.loads((public_root / 'trader-case-reference-times.json').read_text(encoding='utf-8'))
    rows = validate_references(references, {item['id'] for item in public_index['cases']})
    reference_years = Counter(datetime.fromtimestamp(_second(row['candidate_open_utc']), timezone.utc).year
                              for row in rows)
    tasks = plan_reference_download(rows, now=now)
    chunks = private_root / 'native_history'
    indices, key, missing = load_native_chunks(chunks, tasks, environment)
    downloaded_hashes = {task_key(task) + '.json': sha256((chunks / (task_key(task) + '.json')).read_bytes()).hexdigest()
                         for task in tasks if (chunks / (task_key(task) + '.json')).is_file()}
    bars = indices['5m']
    times = sorted(bars)
    if not times:
        raise ValueError('NO_NATIVE_FIVE_MINUTE_BARS')
    # The public trader ledger remains the result source. Only price/volume
    # evidence under this root is broker-native; original clock stays UNKNOWN.
    cases_path = private_root / 'cases.json'
    cases_path.write_bytes(case_bytes)
    alignment_path = private_root / 'reference/alignment.json'
    _json(alignment_path, rows)
    bar_path = private_root / 'reference/bars.csv'
    bar_path.parent.mkdir(parents=True, exist_ok=True)
    with bar_path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=('timestamp', 'open', 'high', 'low',
                                                    'close', 'volume', 'observed_minutes',
                                                    'source', 'quote_side'))
        writer.writeheader()
        for stamp in times:
            bar = bars[stamp]
            writer.writerow(dict(timestamp=datetime.fromtimestamp(stamp, timezone.utc).isoformat(),
                                 open=bar['open'], high=bar['high'], low=bar['low'],
                                 close=bar['close'], volume=bar['volume'], observed_minutes=5,
                                 source=SOURCE[environment], quote_side='BID'))
    profiles = {}
    unavailable = Counter()
    usable_years = Counter()
    for row in rows:
        clock = _second(row['candidate_open_utc'])
        end = bisect_left(times, clock)
        prior = [bars[t] for t in times[max(0, end - 4000):end]]
        profile = profile_before_entry(prior, clock, {'tier': 'full'})
        if profile['status'] != 'candidate_only':
            profile = profile_before_entry(prior, clock, {'tier': '5m_only'})
        if profile['status'] == 'candidate_only':
            profiles[row['case_id']] = profile
            usable_years[datetime.fromtimestamp(clock, timezone.utc).year] += 1
        else:
            unavailable[profile['reason']] += 1
    inputs = dict(cases=_ref(private_root, cases_path),
                  bars=_ref(private_root, bar_path),
                  alignment=_ref(private_root, alignment_path))
    sidecar = dict(method='candidate_market_v1', timezone_status='UNKNOWN',
                   production_enabled=False, input_cases_sha256=inputs['cases']['sha256'],
                   source_key=key, price_source=SOURCE[environment] + ' BID',
                   inputs=inputs, profiles=profiles)
    profile_path = private_root / 'case_candidate_market_profiles.json'
    _json(profile_path, sidecar)
    ready, status = load_candidate_sidecar(cases_path, profile_path, private_root)
    if status != 'READY' or set(ready) != set(profiles):
        raise ValueError('CANDIDATE_PROFILE_VERIFICATION_FAILED')
    # Public case data has no original per-account size baseline; make its
    # absence explicit rather than fabricating a normal lot size.
    _json(private_root / 'case_size_profiles.json', dict(
        method='personal_public_cases_no_account_baseline',
        input_cases_sha256=inputs['cases']['sha256'],
        profiles={item['id']: dict(status='INSUFFICIENT_HISTORY', typical_lot=None,
                                   count=0, days=0) for item in cases_payload['cases']}))
    native_counts = {frame: len(index) for frame, index in indices.items()}
    del indices, bars, times, prior
    volume = build_volume(private_root, chunks, allow_missing=True)
    if volume != 0:
        raise ValueError('NATIVE_VOLUME_INDEX_INCOMPLETE')
    volume_summary = json.loads((chunks / 'download_summary_PRIVATE.json').read_text(encoding='utf-8'))
    outcome = build_outcomes(private_root)
    execution = build_execution(private_root)
    summary = dict(status='READY' if not missing else 'PARTIAL',
                   source=SOURCE[environment], source_key=key,
                   published_cases=len(cases_payload['cases']), references=len(rows),
                   usable_profiles=len(ready), unavailable=dict(unavailable),
                   missing_chunks=len(missing), native_bars=native_counts,
                   download_chunk_hashes=downloaded_hashes,
                   by_reference_year={str(year): dict(total=reference_years[year],
                                                       usable=usable_years[year])
                                      for year in sorted(reference_years)},
                   native_volume_ready=volume_summary['counts']['both_timeframes_ready'],
                   outcome_cases=outcome['total_cases'],
                   execution_cases=execution['profiles'],
                   clock_status='UNKNOWN', alignment='PROJECT_REFERENCE',
                   ruleset='context_contract_v1', orders_sent=0)
    _json(private_root / 'personal_history_status.json', summary)
    return summary
