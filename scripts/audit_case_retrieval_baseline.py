"""Read-only baseline of the existing retriever; public outputs are aggregates only."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.legacy_retriever import CaseStore

D = Decimal
DEFAULT_CLOCK = '2025-10-02T07:00:00Z'
Row = dict[str, Any]


@dataclass(frozen=True)
class Query:
    query_id: str
    side: str
    action: str
    lot: Decimal
    prior_count: int = 0
    signed_distance: Decimal | None = None


def parse_clock(value: str) -> int:
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('查詢時間必須包含時區，例如 Z 或 +00:00')
    return int(stamp.timestamp())


def clock_text(clock: int) -> str:
    return datetime.fromtimestamp(clock, timezone.utc).isoformat().replace('+00:00', 'Z')


def make_queries() -> list[Query]:
    result = []
    for action in ('FIRST', 'ADD'):
        for side in ('BUY', 'SELL'):
            for lot in ('0.05', '0.10', '0.50'):
                result.append(Query(f'Q{len(result)+1:02}', side, action, D(lot),
                                    1 if action == 'ADD' else 0,
                                    D('-0.2') if action == 'ADD' else None))
    return result


def query_row(q: Query, clock: int) -> Row:
    return dict(query_id=q.query_id, clock_utc=clock_text(clock), side=q.side,
                action=q.action, lot=str(q.lot), prior_count=q.prior_count,
                signed_distance_pct=str(q.signed_distance) if q.signed_distance is not None else None)


def percent(numerator: int, denominator: int) -> str | None:
    return str((D(numerator) / D(denominator) * 100).quantize(D('.01'))) if denominator else None


def jaccard(first: set[str], second: set[str]) -> str | None:
    return percent(len(first & second), len(first | second))


def load_metadata(path: Path) -> dict[str, Row]:
    """Join by the importer's existing hashed record key; never export source names."""
    result: dict[str, Row] = {}
    with path.open(encoding='utf-8-sig', newline='') as source:
        reader = csv.DictReader(source)
        if not {'record_id', 'source', 'open_time'} <= set(reader.fieldnames or []):
            raise ValueError('稽核表缺少 record_id/source/open_time，無法核對來源集中度')
        for row in reader:
            key = 'T-' + hashlib.sha256(row['record_id'].encode()).hexdigest()[:12]
            if key in result:
                raise ValueError('稽核 record ID 重複或雜湊衝突，停止來源對照')
            result[key] = dict(source=row['source'] or None,
                               year=row['open_time'][:4] if row['open_time'] else None)
    return result


def rank(store: CaseStore, q: Query, clock: int) -> list[Row]:
    # Preserve the current formula, rounding, threshold, stable ID tie-break and group handling.
    return CaseStore.rank(store, q.side, q.action, q.lot, clock,
                      prior_count=q.prior_count, signed_distance=q.signed_distance)


def evaluate_query(store: CaseStore, q: Query, clock: int,
                   metadata: dict[str, Row]) -> Row:
    eligible = [c for c in store.available(clock)
                if c['side'] == q.side and c['action'] == q.action]
    eligible_groups = {c['group'] for c in eligible}
    matched = rank(store, q, clock)
    groups = {c['group'] for c in matched}
    if len(matched) != len(groups) or not groups <= eligible_groups:
        raise AssertionError('候選群去重或查詢分母不一致')
    top = matched[:6]
    perturbed = rank(store, replace(q, lot=q.lot * D('1.10')), clock)
    changed_groups = {c['group'] for c in perturbed}
    ui = CaseStore.retrieve(store, q.side, q.action, q.lot, clock,
                        prior_count=q.prior_count, signed_distance=q.signed_distance)
    if ui['total'] != len(matched):
        raise AssertionError('檢索排名與介面匹配池數量不一致')
    top_groups = {c['group'] for c in top}
    ui_groups = {c['group'] for c in ui['cases']}
    sources = Counter(metadata[c['id']]['source'] for c in matched
                      if metadata.get(c['id'], {}).get('source'))
    years = Counter(metadata.get(c['id'], {}).get('year') or str(c.get('opened_at', ''))[:4]
                    for c in matched)
    years.pop('', None)
    ratios = [D(c['lot']) / q.lot for c in top]
    signed_deltas = [abs(D(c['signed_distance']) - q.signed_distance) for c in top
                     if q.signed_distance is not None and c.get('signed_distance') is not None]
    distances = [c['distance'] for c in matched]
    return dict(query_row(q, clock), eligible_rows=len(eligible), eligible_groups=len(eligible_groups),
                matched_groups=len(matched), matched_pct=percent(len(matched), len(eligible_groups)),
                pool_distance_median=str(median(distances)) if distances else None,
                best_distance_tied_groups=sum(c['distance'] == matched[0]['distance'] for c in matched) if matched else 0,
                top6_count=len(top), top6_distance_max=str(max(c['distance'] for c in top)) if top else None,
                top6_lot_ratio_min=str(min(ratios)) if ratios else None,
                top6_lot_ratio_max=str(max(ratios)) if ratios else None,
                top6_prior_count_delta_max=max(abs(c.get('prior_count', 0)-q.prior_count) for c in top)
                if top and q.action == 'ADD' else None,
                top6_signed_delta_max_pct=str(max(signed_deltas)) if signed_deltas else None,
                top6_signed_known_count=len(signed_deltas) if q.action == 'ADD' else None,
                matched_years=len(years),
                largest_year_share_pct=percent(max(years.values()), sum(years.values())) if years else None,
                known_sources=len(sources), source_coverage_pct=percent(sum(sources.values()), len(matched)),
                largest_source_share_pct=percent(max(sources.values()), sum(sources.values())) if sources else None,
                lot_plus10=str(q.lot * D('1.10')), matched_groups_lot_plus10=len(perturbed),
                pool_jaccard_pct_lot_plus10=jaccard(groups, changed_groups),
                top6_jaccard_pct_lot_plus10=jaccard(top_groups, {c['group'] for c in perturbed[:6]}),
                ui_top6_overlap_count=len(top_groups & ui_groups))


def write_csv(path: Path, rows: list[Row]) -> None:
    with path.open('w', encoding='utf-8-sig', newline='') as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def render_report(rows: list[Row], total: int, available: int, clock: int) -> str:
    base = next(r for r in rows if r['action'] == 'FIRST' and r['side'] == 'BUY' and D(r['lot']) == D('.1'))
    base_add = next(r for r in rows if r['action'] == 'ADD' and r['side'] == 'BUY' and D(r['lot']) == D('.1'))
    ui_different = sum(r['ui_top6_overlap_count'] != r['top6_count'] for r in rows)
    changed = min((D(r['pool_jaccard_pct_lot_plus10']) for r in rows
                   if r['pool_jaccard_pct_lot_plus10'] is not None), default=None)
    top_changed = min((D(r['top6_jaccard_pct_lot_plus10']) for r in rows
                       if r['top6_jaccard_pct_lot_plus10'] is not None), default=None)
    lines = [
        '# D 第一步：現行相似案例檢索體檢', '',
        f'查詢時點：{clock_text(clock)}。12 組固定條件；手數 0.05／0.10／0.50，首筆／加倉、BUY／SELL。',
        f'輸入候選案例 {total:,} 筆；依現行 available_at 可用 {available:,} 筆。這些都不是獨立交易數。', '',
        '## 先看結論', '',
        f'- 首筆 BUY 0.10 手：匹配 {base["matched_groups"]}／{base["eligible_groups"]} 個不同候選操作群（{base["matched_pct"]}%）。交接參考值 606／895；本次核對：'
        + ('重現一致。' if (base['matched_groups'], base['eligible_groups']) == (606, 895) else '不同，請先查資料版本／時點，不能宣稱已重現。'),
        f'- 加倉 BUY 0.10 手、已有 1 單、不利距離 −0.2%：匹配 {base_add["matched_groups"]}／{base_add["eligible_groups"]} 群（{base_add["matched_pct"]}%）。',
        '- 首筆只比較方向、類型及絕對手數；門檻允許約 5.28 倍內的手數差。匹配比例反映篩選寬窄，不能單獨證明找得準。',
        f'- 手數增加 10% 後，匹配群集合 Jaccard 最低 {changed if changed is not None else "資料不足"}%；最近六筆群集合最低 {top_changed if top_changed is not None else "資料不足"}%。',
        f'- {ui_different}／12 組的「距離最近六筆」與現行「虧損優先展示六筆」不同；相似度評估須用前者。', '',
        '## 12 組結果', '',
        '| 查詢 | 類型／方向 | 手數 | 可用群 | 匹配群 | 比例 | 手數+10%：匹配池重疊 |',
        '|---|---|---:|---:|---:|---:|---:|',
    ]
    for r in rows:
        lines.append(f'| {r["query_id"]} | {"首筆" if r["action"] == "FIRST" else "加倉"} {r["side"]} | {r["lot"]} | {r["eligible_groups"]} | {r["matched_groups"]} | {r["matched_pct"] or "—"}% | {r["pool_jaccard_pct_lot_plus10"] or "—"}% |')
    lines += ['', '## 怎麼讀、下一步', '',
              '- 分母＝查詢時點已成熟、同方向、同類型的不同候選操作群；分子＝通過現行距離門檻後的一群一筆。分母不使用全部案例池。',
              '- 加倉基準固定同向已有 1 單、方向調整後距離 −0.2%（BUY／SELL 都代表不利）；尚未涵蓋有利加倉與更多持倉。',
              '- queries.csv 是完整查詢設定；summary.csv 包含最近六筆手數比範圍、既有單數差／均價距離差、距離中位數、年份／來源集中度、擾動與介面展示差異。空白代表不適用或資料不足，不補零。',
              '- 手數+10% 指 0.05→0.055、0.10→0.110、0.50→0.550，是純檢索敏感度測試；未假設這些手數符合任何券商步進。Jaccard＝交集群數／聯集群數，僅量測重疊，不是準確率。',
              '- 集中度按匹配後每群代表案例計算；來源是匯出檔案，不是已核實帳戶。來源與年份占比以已知者為分母，需同時看 source_coverage_pct；不輸出來源名稱。',
              '- 同距離依現行 ID 排序；最近六筆的更替可能是同分邊界效應，需要結合完整匹配池判讀。',
              '- best_distance_tied_groups 顯示多少群並列第一名；首筆比較條件少，同手數群可能全部同分。展示排序不同是既有虧損優先設計的結果，不能直接當成程式錯誤。',
              '- 下一步先確認相對手數基準與冷啟動方式，再凍結 30 筆盲測查詢／評分表。參數不依盈虧調整，匹配更少不直接等於更好。',
              '- 本次未改相似度、未做 K 線比對／RAG／證據狀態判定；未核實時區，首筆不代表確定空手。歷史結果不是新訂單成功機率。',
              '- 完整性及輸入／核心程式 SHA-256 記錄只存本機 product/private/d_baseline_20261012/，不放公開報告。', '',
              '重跑（在 product/；輸出資料夾必須不存在）：', '',
              '```powershell',
              '.\\.venv\\Scripts\\python.exe scripts/audit_case_retrieval_baseline.py --output docs/d_baseline_20261012_new',
              '```', '']
    return '\n'.join(lines)


def run(cases_path: Path, audit_path: Path, output: Path, clock_value: str) -> list[Row]:
    if output.exists():
        raise FileExistsError('輸出資料夾已存在，請使用新路徑，保留先前體檢')
    clock = parse_clock(clock_value)
    payload = json.loads(cases_path.read_text(encoding='utf-8'))
    items = payload['cases']
    if len({c['id'] for c in items}) != len(items):
        raise ValueError('案例 ID 重複，停止體檢')
    metadata = load_metadata(audit_path)
    store = CaseStore.__new__(CaseStore)
    store.items = items
    store.source = 'trader_history'
    store.group_sequences = {}
    queries = make_queries()
    rows = [evaluate_query(store, q, clock, metadata) for q in queries]
    report = render_report(rows, len(items), len(store.available(clock)), clock)
    output.mkdir(parents=True, exist_ok=False)
    write_csv(output / 'queries.csv', [query_row(q, clock) for q in queries])
    write_csv(output / 'summary.csv', rows)
    (output / 'report.md').write_text(report, encoding='utf-8')
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, default=ROOT / 'private/cases.json')
    parser.add_argument('--audit', type=Path,
                        default=ROOT.parent / 'artifacts/behavior_audit_20261001_final/gold_behavior_records.csv')
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/d_baseline_20261012')
    parser.add_argument('--clock', default=DEFAULT_CLOCK)
    args = parser.parse_args()
    output = args.output.resolve()
    if not any(output.is_relative_to(folder) for folder in ((ROOT / 'docs').resolve(), (ROOT / 'private').resolve())):
        parser.error('輸出只能放在 product/docs 或 product/private 的新資料夾')
    rows = run(args.cases, args.audit, output, args.clock)
    base = next(r for r in rows if r['query_id'] == 'Q02')
    print(json.dumps(dict(queries=len(rows), first_buy_010_matched=base['matched_groups'],
                          first_buy_010_eligible=base['eligible_groups'], output_files=3), ensure_ascii=False))


if __name__ == '__main__':
    main()
