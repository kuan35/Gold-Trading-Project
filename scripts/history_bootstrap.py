"""Classmate-owned Pepperstone history setup; market data only, no orders."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

from backend.candidate_sidecar import load_candidate_sidecar
from scripts.check_ctrader_demo import load_local_config
from scripts.live_readonly_policy import load_live_config
from scripts.local_app import read_settings
from scripts.personal_history import (_second, plan_reference_download,
                                      public_reference_status, validate_references)

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'frontend/public/data'
PERSONAL = ROOT / 'private/personal_history'


def source_folder(environment: str) -> Path:
    config = load_local_config() if environment == 'demo' else load_live_config()
    account = config.get('CTRADER_ACCOUNT_ID', '')
    if not account.isdecimal() or int(account) <= 0:
        raise ValueError('ACCOUNT_ID_REQUIRED_FOR_PERSONAL_HISTORY')
    fingerprint = sha256((environment + ':' + account).encode()).hexdigest()
    return PERSONAL / fingerprint


def plan() -> tuple[list[dict], list[dict]]:
    index = json.loads((PUBLIC / 'trader-market-index.json').read_text(encoding='utf-8'))
    payload = json.loads((PUBLIC / 'trader-case-reference-times.json').read_text(encoding='utf-8'))
    rows = validate_references(payload, {case['id'] for case in index['cases']})
    return rows, plan_reference_download(rows)


def verify(folder: Path, *, personal_base: Path = PERSONAL) -> dict:
    folder = folder.resolve()
    if not folder.is_relative_to(Path(personal_base).resolve()):
        raise ValueError('PERSONAL_PRIVATE_FOLDER_REQUIRED')
    status_path = folder / 'personal_history_status.json'
    status = json.loads(status_path.read_text(encoding='utf-8'))
    if not isinstance(status.get('download_chunk_hashes'), dict) or not status['download_chunk_hashes']:
        raise ValueError('PERSONAL_DOWNLOAD_HASHES_MISSING')
    for name, digest in status['download_chunk_hashes'].items():
        path = (folder / 'native_history' / name).resolve()
        if path.parent != (folder / 'native_history').resolve() or sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('PERSONAL_VOLUME_CHUNK_CHANGED')
    profiles, state = load_candidate_sidecar(
        folder / 'cases.json', folder / 'case_candidate_market_profiles.json', folder)
    if (state != 'READY' or len(profiles) != status['usable_profiles']
            or status['status'] not in ('READY', 'PARTIAL')):
        raise ValueError('PERSONAL_HISTORY_VERIFICATION_FAILED')
    volume = json.loads((folder / 'native_history/case_volume_references_PRIVATE.json').read_text(encoding='utf-8'))
    if volume['source_key'] != status['source_key'] or set(profiles) != set(volume['cases']):
        raise ValueError('PERSONAL_VOLUME_SOURCE_MISMATCH')
    for name, digest in volume['chunk_hashes'].items():
        path = (folder / 'native_history' / name).resolve()
        if path.parent != (folder / 'native_history').resolve() or sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('PERSONAL_VOLUME_CHUNK_CHANGED')
    outcomes = json.loads((folder / 'case_forward_outcomes.json').read_text(encoding='utf-8'))
    executions = json.loads((folder / 'case_execution_bars_v2.json').read_text(encoding='utf-8'))
    if (outcomes['source'] != status['source'] + ' BID'
            or executions.get('price_source') != status['source'] + ' BID'
            or set(profiles) != set(outcomes['profiles']) or set(profiles) != set(executions['records'])):
        raise ValueError('PERSONAL_PRICE_SOURCE_MISMATCH')
    for payload in (outcomes, executions):
        for ref in payload['inputs'].values():
            path = (folder / ref['path']).resolve()
            if not path.is_relative_to(folder) or sha256(path.read_bytes()).hexdigest() != ref['sha256']:
                raise ValueError('PERSONAL_EVIDENCE_CHANGED')
    return {key: status[key] for key in ('status', 'source', 'usable_profiles',
                                         'missing_chunks', 'native_bars', 'native_volume_ready',
                                         'by_reference_year',
                                         'clock_status', 'alignment', 'ruleset')}


def activate(folder: Path) -> dict:
    summary = verify(folder)
    if summary['usable_profiles'] <= 0:
        raise ValueError('NO_USABLE_CASE_PROFILES')
    setting = ROOT / '.env.local'
    read_settings(setting)
    lines = [line for line in setting.read_text(encoding='utf-8').splitlines()
             if not line.startswith(('GOLD_CASE_DATA_FOLDER=', 'GOLD_NATIVE_VOLUME_FOLDER='))] if setting.exists() else []
    relative = folder.resolve().relative_to((ROOT / 'private').resolve()).as_posix()
    text = '\n'.join(lines + ['GOLD_CASE_DATA_FOLDER=' + relative,
                              'GOLD_NATIVE_VOLUME_FOLDER=native_history']) + '\n'
    temp = setting.with_suffix('.personal.tmp')
    temp.write_text(text, encoding='utf-8')
    temp.replace(setting)
    return dict(status='ACTIVATED', source=summary['source'],
                usable_profiles=summary['usable_profiles'], restart_required=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('plan', 'probe', 'download', 'build', 'verify', 'activate', 'all'))
    parser.add_argument('--environment', choices=('demo', 'live'), default='demo')
    parser.add_argument('--read-only', action='store_true', help='required for LIVE history data')
    parser.add_argument('--max-chunks', type=int, help='checkpoint after this many new weekly chunks')
    args = parser.parse_args(argv)
    if args.environment == 'live' and not args.read_only:
        raise ValueError('LIVE_READ_ONLY_FLAG_REQUIRED')
    if args.max_chunks is not None and args.max_chunks <= 0:
        raise ValueError('MAX_CHUNKS_MUST_BE_POSITIVE')
    rows, tasks = plan()
    if args.action == 'plan':
        years = dict(sorted(Counter(datetime.fromtimestamp(_second(row['candidate_open_utc']), timezone.utc).year
                                    for row in rows).items()))
        print(json.dumps(dict(status='PLAN', reference_cases=len(rows),
                              requested_chunks=len(tasks), by_reference_year=years,
                              source='own Pepperstone cTrader ' + args.environment.upper(),
                              orders_sent=0, note='先由本人在本機完成 cTrader 授權，再明確執行 download；各帳戶覆蓋可能不同。'),
                         ensure_ascii=False))
        return 0
    folder = source_folder(args.environment)
    chunks = folder / 'native_history'
    if args.action in ('probe', 'download', 'all'):
        from scripts.fetch_ctrader_history_volume import fetch
        chunks.mkdir(parents=True, exist_ok=True)
        chosen = tasks
        if args.action == 'probe':
            chosen = [item for frame in ('5m', '1h')
                      for group in ([t for t in tasks if t['interval'] == frame],)
                      for item in (group[0], group[len(group)//2], group[-1])]
        result = fetch(chosen, max_chunks=args.max_chunks, output_folder=chunks,
                       environment=args.environment)
        if result['status'] not in ('COMPLETE', 'CHECKPOINT'):
            raise ValueError('HISTORY_DOWNLOAD_INCOMPLETE_' + result['status'])
        if args.action != 'all':
            print(json.dumps({k: result[k] for k in ('status', 'source', 'requested_chunks',
                                                     'completed_chunks', 'empty_chunks', 'rows', 'orders_sent')},
                             ensure_ascii=False))
            return 0
    if args.action in ('build', 'all'):
        from scripts.build_personal_history import build
        result = build(folder, environment=args.environment)
        print(json.dumps(result, ensure_ascii=False))
        if args.action == 'all':
            print(json.dumps(activate(folder), ensure_ascii=False))
        return 0
    result = verify(folder) if args.action == 'verify' else activate(folder)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError) as error:
        # Only fixed local error codes reach stdout/stderr. Never print config,
        # account ID, token or raw broker response.
        code = str(error)
        if not code.isascii() or len(code) > 100 or any(ch in code for ch in '\r\n=:/\\'):
            code = type(error).__name__
        print(code, file=sys.stderr)
        raise SystemExit(1)
