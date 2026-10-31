"""Reproducible, local-only native OHLC/tick-count filter ablation.

No production data is rewritten. No network, model, account, or execution API is
used. All case identities, reference clocks, pools and hashes stay in private/.
"""
from __future__ import annotations

import bisect
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from math import log
from pathlib import Path
import sys

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))
from backend.candidate_profile import _indicators
from backend.compact_market import distinct_rows
from backend.context_retrieval import ContextIndex
from backend.context_rules import LIMITS, evaluate_rows, market_features, pair_metrics

OUTPUT = PRODUCT / 'private/native_volume_ablation_20261030'
LIMIT = dict(d5=.25, d1h=.50, dtail=.12, vol_ratio=2.)


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True,
                              indent=2, allow_nan=False) + '\n', encoding='utf8')


def volume_value(reference, source_key, *, interval='5m', exclude_gaps=False):
    if not reference:
        return None, 'MISSING_VOLUME_REFERENCE'
    if reference.get('source_key') != source_key:
        return None, 'SOURCE_MISMATCH'
    f = reference.get('frames', {}).get(interval, {})
    if f.get('status') != 'AVAILABLE':
        return None, 'INSUFFICIENT_OR_STALE'
    if f.get('volume_basis') != 'broker_native_tick_count':
        return None, 'VOLUME_BASIS_MISMATCH'
    if f.get('bars_closed_before_asof') is not True:
        return None, 'FUTURE_VOLUME_BAR'
    try:
        baseline = Decimal(str(f.get('prior20_mean')))
        if not baseline.is_finite() or baseline < 0:
            return None, 'INVALID_BASELINE'
        if baseline == 0:
            return None, 'ZERO_BASELINE'
        if f.get('relative_volume_ratio') is None:
            return None, 'MISSING_TICK_RATIO'
        ratio = Decimal(str(f['relative_volume_ratio']))
        if not ratio.is_finite() or ratio < 0:
            return None, 'INVALID_TICK_RATIO'
        if ratio == 0:
            return None, 'ZERO_TICK_RATIO'
    except (InvalidOperation, ValueError, TypeError):
        return None, 'INVALID_TICK_RATIO'
    if exclude_gaps and f.get('gap_count') != 0:
        return None, 'VOLUME_BASELINE_GAP'
    return ratio, None


def filter_passed(passed, descriptions, query_reference, references, limit,
                  *, exclude_gaps=False):
    """Apply volume before deduplication, retaining original context ordering."""
    rejected = Counter()
    source = (query_reference or {}).get('source_key')
    query_value, query_reason = volume_value(query_reference, source, exclude_gaps=exclude_gaps)
    retained = []
    if query_reason:
        rejected['QUERY_' + query_reason] = len(passed)
    else:
        for row in passed:
            value, reason = volume_value(references.get(row['case_id']), source,
                                         exclude_gaps=exclude_gaps)
            if reason:
                rejected[reason] += 1
                continue
            ratio = max(query_value / value, value / query_value)
            if ratio > limit:
                rejected['TICK_RATIO_EXCEEDS_LIMIT'] += 1
                continue
            retained.append(dict(row, tick_relative_volume_ratio=str(value),
                                 tick_comparison_multiplier=str(ratio)))
    unique = distinct_rows(retained, descriptions, top_k=None)
    return dict(rows=unique[:5], retained_rows=len(retained), unique_groups=len(unique),
                all_retained_ids=[r['case_id'] for r in retained],
                all_unique_ids=[r['case_id'] for r in unique],
                query_volume_reason=query_reason,
                rejections=dict(sorted(rejected.items())))


def native_volume_frame(index, times, as_of, interval):
    """Independently recalculate the saved ratio from its native tick counts."""
    span, count = (300, 60) if interval == '5m' else (3600, 20)
    end = bisect.bisect_right(times, as_of-span)
    available = times[max(0, end-max(count, 21)):end]
    chosen = available[-count:]
    baseline = available[-21:]
    volumes = [index[t]['volume'] for t in baseline]
    mean = sum(volumes[:-1], Decimal(0))/20 if len(volumes) == 21 else None
    ratio = Decimal(volumes[-1])/mean if mean is not None and mean > 0 else None
    return dict(status='AVAILABLE' if len(chosen) == count and
                as_of-(chosen[-1]+span) < span else 'INSUFFICIENT_OR_STALE',
                times=chosen, last_volume=volumes[-1] if volumes else None,
                prior20_mean=str(mean) if mean is not None else None,
                relative_volume_ratio=str(ratio) if ratio is not None else None,
                volume_basis='broker_native_tick_count',
                ratio_basis='LAST_CLOSED_OVER_PREVIOUS_20_AVAILABLE_BARS',
                gap_count=sum(b-a != span for a, b in zip(baseline, baseline[1:])),
                window_gap_count=sum(b-a != span for a, b in zip(chosen, chosen[1:])),
                bars_closed_before_asof=all(t+span <= as_of for t in chosen))


def native_profile(indices, times, as_of, source_key):
    frames = {}
    indicators = {}
    for iv, span, count in (('5m', 300, 61), ('1h', 3600, 20)):
        end = bisect.bisect_right(times[iv], as_of - span)
        stamps = times[iv][max(0, end-count):end]
        if len(stamps) != count or as_of - (stamps[-1] + span) >= span:
            return dict(status='insufficient', reason=iv + '_INSUFFICIENT_OR_STALE')
        bars = [indices[iv][t] for t in stamps]
        if any(b['time'] + span > as_of for b in bars):
            raise ValueError('FUTURE_NATIVE_BAR')
        # Same Decimal Wilder ATR implementation; 61 M5 bars supply the previous
        # close, and only the last 60 enter context paths. H1 uses 20 native bars.
        values, _ = _indicators(bars, iv, momentum=False)
        if values is None:
            return dict(status='insufficient', reason=iv + '_ATR_UNAVAILABLE')
        indicators.update({k: str(v) for k, v in values.items()})
        frames[iv] = bars[-(60 if iv == '5m' else 20):]
    return dict(status='candidate_only', tier='full', as_of=as_of,
                source='ctrader_demo_native', source_key=source_key,
                timezone_status='UNKNOWN', reference_alignment='PROJECT_REFERENCE',
                production_enabled=False, indicators=indicators, pre_entry_bars=frames)


def summarize(records):
    if len(records) != 30:
        raise ValueError('FIXED_30_REQUIRED')
    summary = {}
    for method in sorted(records[0]['methods']):
        total_rows = groups = displayed = covered = changed = same = intersections = common = 0
        lost = gained = 0
        rejection_counts = Counter()
        for record in records:
            result = record['methods'][method]
            base = record['methods']['no_volume']['rows']
            rows = result['rows']
            total_rows += result['retained_rows']
            groups += result['unique_groups']
            displayed += len(rows)
            covered += bool(rows)
            rejection_counts.update(result.get('rejections', {}))
            lost += bool(base) and not rows
            gained += bool(rows) and not base
            if base and rows:
                common += 1
                different = base[0]['case_id'] != rows[0]['case_id']
                changed += different
                same += not different
                intersections += len({r['case_id'] for r in base} & {r['case_id'] for r in rows})
        summary[method] = dict(queries=30, queries_with_output=covered, coverage=covered/30,
            hit_count_definition='query has at least one rule-passed output; no relevance labels',
            retained_rows=total_rows, matched_groups=groups, displayed_pairs=displayed,
            both_output_queries=common, top1_changed_both_output=changed,
            top1_same_both_output=same, lost_output_queries=lost, gained_output_queries=gained,
            top5_intersection_total_both_output=intersections,
            top5_intersection_mean_both_output=intersections/common if common else None,
            rejections=dict(sorted(rejection_counts.items())))
    return summary


def load_native(folder, references):
    """Prove CSV rows equal hashed native chunks with one provider identity."""
    indices = {'5m': {}, '1h': {}}
    for iv in indices:
        with (folder / ('native_' + iv + '.csv')).open(encoding='utf8', newline='') as stream:
            for row in csv.DictReader(stream):
                row['time'] = int(row['time'])
                row['volume'] = int(row['volume'])
                stamp = row['time']
                if stamp in indices[iv] or row['volume'] < 0:
                    raise ValueError('DUPLICATE_OR_INVALID_NATIVE_CSV')
                indices[iv][stamp] = row
    verified = {iv: set() for iv in indices}
    for name, digest in sorted(references['chunk_hashes'].items()):
        path = folder / name
        if path.parent != folder or path.suffix != '.json':
            raise ValueError('INVALID_CHUNK_PATH')
        raw = path.read_bytes()
        if sha256(raw).hexdigest() != digest:
            raise ValueError('NATIVE_CHUNK_HASH_CHANGED')
        chunk = json.loads(raw)
        if (chunk['source_key'] != references['source_key'] or
                chunk['volume_basis'] != 'broker_native_tick_count'):
            raise ValueError('NATIVE_CHUNK_SOURCE_MISMATCH')
        iv = chunk['interval']
        if iv not in indices:
            raise ValueError('UNKNOWN_NATIVE_INTERVAL')
        span = 300 if iv == '5m' else 3600
        for bar in chunk['bars']:
            stamp = bar['time']
            if type(stamp) is not int or stamp % span or type(bar['volume']) is not int:
                raise ValueError('INVALID_NATIVE_BAR')
            if indices[iv].get(stamp) != bar:
                raise ValueError('CSV_CHUNK_MISMATCH')
            op, hi, lo, close = [Decimal(bar[k]) for k in ('open', 'high', 'low', 'close')]
            if not all(v.is_finite() for v in (op, hi, lo, close)) or not 0 < lo <= min(op, close) <= max(op, close) <= hi:
                raise ValueError('INVALID_NATIVE_OHLC')
            verified[iv].add(stamp)
    if any(set(indices[iv]) != verified[iv] for iv in indices):
        raise ValueError('UNVERIFIED_NATIVE_CSV_ROWS')
    return indices, {iv: sorted(index) for iv, index in indices.items()}


def protected_hashes():
    root = PRODUCT.parent
    paths = sorted([p for p in (root / '交易員資料').rglob('*') if p.is_file()] +
                   [p for p in root.iterdir() if p.is_file() and p.suffix.lower() in ('.pdf', '.png', '.docx', '.m4a')])
    return {str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest() for p in paths}


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    protected_before = protected_hashes()
    private = PRODUCT / 'private'
    folder = private / 'ctrader_history_volume_20261030'
    selection_path = private / 'similarity_evaluation_20261023/selection_PRIVATE.json'
    reference_path = folder / 'case_volume_references_PRIVATE.json'
    case_path = private / 'cases.json'
    profile_path = private / 'case_candidate_market_profiles.json'
    selection = json.loads(selection_path.read_text(encoding='utf8'))
    if len(selection['queries']) != 30 or len({datetime.fromtimestamp(q['as_of'], timezone.utc).date()
                                                for q in selection['queries']}) != 30:
        raise ValueError('FROZEN_30_DISTINCT_DATES_REQUIRED')
    for relative, expected in selection['inputs'].items():
        if sha256((PRODUCT / relative).read_bytes()).hexdigest() != expected:
            raise ValueError('FROZEN_SELECTION_INPUT_CHANGED')
    references = json.loads(reference_path.read_text(encoding='utf8'))
    if sha256(profile_path.read_bytes()).hexdigest() != references['profiles_sha256']:
        raise ValueError('REFERENCE_PROFILE_HASH_CHANGED')
    if LIMITS['medium'] != LIMIT:
        raise ValueError('MEDIUM_RULES_CHANGED')
    indices, times = load_native(folder, references)
    cases = json.loads(case_path.read_text(encoding='utf8'))['cases']
    lookup = {c['id']: c for c in cases}
    group_maturity = defaultdict(int)
    for case in cases:
        group_maturity[case['group']] = max(group_maturity[case['group']], case['available_at'])
    cases = [dict(c, available_at=group_maturity[c['group']]) for c in cases]
    profiles = {}
    missing = Counter()
    volume_reasons = Counter()
    gaps = Counter()
    recomputed_frames = 0
    for cid, ref in sorted(references['cases'].items()):
        if ref['source_key'] != references['source_key']:
            raise ValueError('REFERENCE_SOURCE_MISMATCH')
        for iv in ('5m', '1h'):
            actual_frame = native_volume_frame(indices[iv], times[iv], ref['as_of'], iv)
            if actual_frame != ref['frames'][iv]:
                raise ValueError('NATIVE_VOLUME_REFERENCE_MISMATCH')
            recomputed_frames += 1
        profile = native_profile(indices, times, ref['as_of'], references['source_key'])
        if profile['status'] != 'candidate_only':
            missing[profile['reason']] += 1
            continue
        for iv, span in (('5m', 300), ('1h', 3600)):
            actual = [b['time'] for b in profile['pre_entry_bars'][iv]]
            if actual != ref['frames'][iv]['times']:
                raise ValueError('NATIVE_FRAME_REFERENCE_MISMATCH')
            if not ref['frames'][iv]['bars_closed_before_asof']:
                raise ValueError('FUTURE_REFERENCE_BAR')
            gaps[iv + '_profiles_with_window_gaps'] += bool(ref['frames'][iv]['window_gap_count'])
            gaps[iv + '_profiles_with_volume_gaps'] += bool(ref['frames'][iv]['gap_count'])
            _, reason = volume_value(ref, references['source_key'], interval=iv)
            if reason:
                volume_reasons[iv + '_' + reason] += 1
        profiles[cid] = profile
    index = ContextIndex(cases, profiles)
    method_names = ['no_volume'] + ['tick_' + str(k) + suffix for suffix in ('', '_gap_free') for k in ('1.5', '2', '3')]
    inputs = {str(p.relative_to(PRODUCT)): sha256(p.read_bytes()).hexdigest() for p in
              (selection_path, reference_path, case_path, profile_path, folder/'native_5m.csv', folder/'native_1h.csv',
               Path(__file__), PRODUCT/'backend/context_rules.py', PRODUCT/'backend/context_retrieval.py',
               PRODUCT/'backend/dual_path_retrieval.py', PRODUCT/'backend/compact_market.py',
               PRODUCT/'backend/candidate_profile.py', Path(__file__).with_name('test_native_volume_ablation.py'),
               PRODUCT/'backend/technical.py')}
    manifest = dict(schema='native_volume_ablation_v1', inputs=inputs,
        source_key=references['source_key'], native_chunks=len(references['chunk_hashes']),
        thresholds=LIMIT, fixed_queries=30, methods=method_names,
        ratio='max(query_relative_volume/case_relative_volume, inverse)',
        volume_basis='broker_native_tick_count', production_enabled=False,
        alignment='PROJECT_REFERENCE', original_trade_clock='UNKNOWN',
        native_frames=dict(M5_path=60, M5_ATR_input=61, H1_path_and_ATR_input=20),
        gap_policy='main keeps observed gaps flagged; sensitivity excludes any 21-bar M5 volume-baseline gap',
        group_maturity='max existing conservative available_at across all 11902 product candidates',
        outcome_fields_used_for_filter_or_ranking=False, human_relevance_accuracy=None)
    records = []
    temporal_checked = 0
    query_missing = Counter()
    query_statuses = Counter()
    query_gaps = Counter()
    full_pools = []
    for n, frozen in enumerate(selection['queries'], 1):
        cid = frozen['case_id']
        case = lookup[cid]
        if case['side'] != frozen['side'] or case['group'] != frozen['group']:
            raise ValueError('FROZEN_QUERY_IDENTITY_CHANGED')
        ref = references['cases'].get(cid)
        profile = profiles.get(cid)
        if ref and ref['as_of'] != frozen['as_of']:
            raise ValueError('FROZEN_QUERY_CLOCK_CHANGED')
        methods = {}
        record = dict(query_number=n, query_case_id=cid, as_of=frozen['as_of'],
            side=frozen['side'], group=frozen['group'], methods=methods,
            query_volume_reference=ref)
        if profile is None or cid not in index.features:
            reason = 'NATIVE_QUERY_PROFILE_UNAVAILABLE'
            query_missing[reason] += 1
            for name in method_names:
                methods[name] = dict(rows=[], retained_rows=0, unique_groups=0,
                                     status=reason, rejections={})
            records.append(record)
            continue
        qf = market_features(profile)
        for iv in ('5m', '1h'):
            query_gaps[iv + '_window_gap_queries'] += bool(ref['frames'][iv]['window_gap_count'])
            query_gaps[iv + '_volume_baseline_gap_queries'] += bool(ref['frames'][iv]['gap_count'])
        pool, counts = index.eligible(profile, frozen['side'], frozen['group'])
        query_start = index.descriptions[cid]['window_start']
        metrics = []
        for c in pool:
            desc = index.descriptions[c['id']]
            assert c['side'] == frozen['side'] and c['group'] != frozen['group']
            assert group_maturity[c['group']] <= frozen['as_of']
            assert desc['window_end'] <= query_start
            assert profiles[c['id']]['source_key'] == profile['source_key'] == references['source_key']
            temporal_checked += 1
            metrics.append(dict(case_id=c['id'], group=c['group'], **pair_metrics(qf, index.features[c['id']])))
        evaluated = evaluate_rows(metrics, index.descriptions, LIMIT, top_k=len(metrics) or 1)
        # _passed_ids includes rows suppressed by group/window dedupe. Restore
        # ALL passed rows so a filtered representative can be replaced.
        passed = [r for r in metrics if r['case_id'] in evaluated['_passed_ids']]
        for r in passed:
            r['score_max'] = max(r['d5']/.25, r['d1h']/.50, r['dtail']/.12,
                                 log(r['vol_ratio'])/log(2))
            r['score_sum'] = r['d5']/.25 + r['d1h']/.50 + r['dtail']/.12 + log(r['vol_ratio'])/log(2)
        passed.sort(key=lambda r: (r['score_max'], r['score_sum'], r['case_id']))
        unique = distinct_rows(passed, index.descriptions, top_k=None)
        assert [r['case_id'] for r in unique] == [r['case_id'] for r in evaluated['rows']]
        parity = index.retrieve(profile, frozen['side'], exclude_group=frozen['group'])
        query_statuses[parity['rule_status']] += 1
        assert [r['case_id'] for r in unique[:5]] == [c['id'] for c in parity['cases']]
        methods['no_volume'] = dict(rows=unique[:5], retained_rows=len(passed), unique_groups=len(unique),
            all_retained_ids=[r['case_id'] for r in passed], all_unique_ids=[r['case_id'] for r in unique],
            status=parity['rule_status'], rejections={})
        for name in method_names[1:]:
            methods[name] = filter_passed(passed, index.descriptions, ref, references['cases'],
                Decimal(name.split('_')[1]), exclude_gaps=name.endswith('_gap_free'))
        for suffix in ('', '_gap_free'):
            idsets = [set(methods['tick_' + k + suffix]['all_retained_ids']) for k in ('1.5', '2', '3')]
            assert idsets[0] <= idsets[1] <= idsets[2] <= set(methods['no_volume']['all_retained_ids'])
        record.update(eligible_rows=len(pool), eligibility_counts=counts,
            raw_context_passed_rows=len(passed), context_rejections=evaluated['rejections'],
            query_event=qf['event'], query_native_window_start=query_start,
            hourly_volume_diagnostic=volume_value(ref, references['source_key'], interval='1h')[1])
        full_pools.append(dict(query_number=n, eligible_context_metrics=metrics))
        records.append(record)
        print(f'Native fixed query {n}/30 complete', flush=True)
    summary = summarize(records)
    protected_after = protected_hashes()
    if protected_before != protected_after:
        raise ValueError('PROTECTED_INPUTS_CHANGED')
    validation = dict(fixed_queries=30, built_native_profiles=len(profiles),
        context_index_profiles=len(index.cases), invalid_context_profiles=index.invalid_profiles,
        product_candidates=len(cases), native_reference_candidates=len(references['cases']),
        candidates_without_native_reference=len(cases)-len(references['cases']),
        missing_native_profiles=dict(missing), query_missing=dict(query_missing),
        no_volume_query_statuses=dict(query_statuses), query_gap_counts=dict(query_gaps),
        volume_unavailable=dict(volume_reasons), gap_counts=dict(gaps),
        recomputed_volume_reference_frames=recomputed_frames,
        temporal_and_source_checked_eligible_pairs=temporal_checked,
        context_top5_parity_queries=30-sum(query_missing.values()), nested_pre_dedupe_filter_sets=True,
        protected_files=len(protected_before), protected_hashes_unchanged=True,
        group_maturity_normalized_rows=sum(c['available_at'] != lookup[c['id']]['available_at'] for c in cases))
    dump(OUTPUT/'manifest_PRIVATE.json', manifest)
    dump(OUTPUT/'results_PRIVATE.json', records)
    dump(OUTPUT/'eligible_pools_PRIVATE.json', full_pools)
    dump(OUTPUT/'protected_inputs_PRIVATE.json', protected_before)
    dump(OUTPUT/'validation_PRIVATE.json', validation)
    # Public-facing docs contain only anonymous aggregate counters, no case IDs,
    # source identities, exact clocks, input hashes, prices, lots or outcomes.
    aggregate = dict(methods=summary, validation=validation,
        production_changed=False, human_accuracy=None, source='cTrader DEMO native OHLC and tick count',
        original_trade_clock='UNKNOWN', alignment='PROJECT_REFERENCE')
    dump(PRODUCT/'docs/native_volume_ablation_20261030.json', aggregate)
    write_report(aggregate)
    print(json.dumps(aggregate, ensure_ascii=False), flush=True)
    return 0


def write_report(aggregate):
    lines = ['# 原生 tick 相對量離線比較（2026-10-30）', '',
        '本實驗只完成離線消融，沒有改動正式檢索或公開資料。沿用既有30個不同日期，不因缺資料或結果不好另選查詢；這些日期以前已檢視，並非新的盲測。', '',
        '查詢與歷史案例都從同一份 cTrader DEMO 原生 OHLC 重建5分鐘60根／1小時20根盤面；5分鐘 ATR 使用額外一根前收。沿用 ContextIndex 同方向、全群成熟、窗口不重疊、自群排除及中檔0.25／0.50／0.12／2。參考時點沿原來源模型，保留 PROJECT_REFERENCE／原始交易時鐘 UNKNOWN；不能聲稱精確還原交易員當時盤面。', '',
        '主軸為最後一根已收5分鐘 tick count ÷ 前20根可用棒平均；查詢與案例量比取較大／較小，分別限制1.5、2、3倍。這是券商 tick 次數，不是成交手數或全球成交量。一小時量僅存私人輔助欄，不加入權重。零量比、零基準、缺量、陳舊與來源不一致都不能比較。', '',
        '所有情境通過列先保存，再做量能篩選，沿原情境分數排序，最後才重新群／參考時點去重及取前五；後面的候選可補位。量不改情境分數，手數、盈虧及未來結果不選門檻。', '',
        '|方法|有輸出／30|保留列數|匹配群次數|前五配對|共同輸出|Top1變動|前五平均交集|',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for name, r in aggregate['methods'].items():
        mean = r['top5_intersection_mean_both_output']
        lines.append(f"|{name}|{r['queries_with_output']}/30|{r['retained_rows']}|{r['matched_groups']}|{r['displayed_pairs']}|{r['both_output_queries']}|{r['top1_changed_both_output']}|{mean:.3f}|" if mean is not None else
                     f"|{name}|{r['queries_with_output']}/30|{r['retained_rows']}|{r['matched_groups']}|{r['displayed_pairs']}|0|0|未定義|")
    lines += ['', '有輸出只表示至少一個案例通過規則，並非人評命中；覆蓋率固定除以30。Top1變動、前五交集只在兩法都有輸出的子集合計算，分母另列；雙方皆空不算完美穩定。匹配群次數為各查詢群／時點去重後數量加總，不是跨30查詢再次去重的獨立交易群。', '',
        '`gap_free` 為敏感度檢查：查詢或案例的21根5分鐘量能基準存在任何非5分鐘間隔即排除。主實驗保留觀測到的跳棒並標記；未取得逐時歷史交易時段證據，gap不能一概判定為正常休市，也不補棒。兩法都使用固定30個日期；敏感度檢查不縮分母。', '',
        '缺漏與驗證彙總：', '', '```json', json.dumps(aggregate['validation'], ensure_ascii=False, indent=2), '```', '',
        '逐方法排除原因（列數，查詢缺量可同時排除整個通過池；不是查詢數）：', '', '```json',
        json.dumps({k: v['rejections'] for k, v in aggregate['methods'].items()}, ensure_ascii=False, indent=2), '```', '',
        '結論界線：本表量化篩選後覆蓋與名單穩定度，沒有人工相關性標籤，無法判定哪個量能門檻改善相似品質；不根據歷史盈虧、勝率或報酬選門檻。應保留量能為離線對照，待新日期盲評才評估是否接正式檢索。', '',
        '重跑（product目錄）：`.\\.venv\\Scripts\\python.exe -X utf8 -m research.native_volume_ablation`。輸入檔與核心程式SHA-256、原生chunk來源驗證、完整通過與合格池、逐案原因和查詢時點只寫在 `private/native_volume_ablation_20261030/`；匿名彙總另見同名JSON。此程式沒有網路或LLM呼叫。', '']
    (PRODUCT/'docs/native_volume_ablation_20261030.md').write_text('\n'.join(lines), encoding='utf8')


if __name__ == '__main__':
    raise SystemExit(main())
