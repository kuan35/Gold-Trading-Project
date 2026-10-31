"""Screen source-specific clock hypotheses; never confirm or rewrite trade timestamps.

Matching the execution candle is an OFFLINE calibration diagnostic, not a feature.
Production pre-order features must use bars closed BEFORE the earliest order instant.
Only aggregate reports may leave the private output directory.
"""
from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median
from typing import Any

D = Decimal
UTC = timezone.utc
TOLERANCES = (D('0'), D('.5'), D('1'), D('2'))


@dataclass(frozen=True)
class Event:
    local: datetime
    price: Decimal


def sunday(year: int, month: int, nth: int) -> int:
    days = [d for d in range(1, calendar.monthrange(year, month)[1]+1)
            if datetime(year, month, d).weekday() == 6]
    return days[nth-1] if nth > 0 else days[-1]


def offset_minutes(model: str, local: datetime) -> int:
    if model.startswith('FIXED:'):
        return int(model.split(':')[1])
    # DST boundaries are deliberately excluded from the evidence sample below.
    if model == 'US_2_3':
        start = datetime(local.year, 3, sunday(local.year, 3, 2))
        end = datetime(local.year, 11, sunday(local.year, 11, 1))
    elif model == 'EU_2_3':
        start = datetime(local.year, 3, sunday(local.year, 3, -1))
        end = datetime(local.year, 10, sunday(local.year, 10, -1))
    else:
        raise ValueError('Unknown time model')
    return 180 if start <= local < end else 120


def utc_stamp(event: Event, model: str) -> int:
    return int((event.local-timedelta(minutes=offset_minutes(model, event.local)))
               .replace(tzinfo=UTC).timestamp())


def execution_bar(event: Event, model: str) -> int:
    return utc_stamp(event, model)//300*300


def latest_closed_bar(event: Event, model: str) -> int:
    """Safe for minute precision: omit the whole candle containing the order."""
    return execution_bar(event, model)-300


def boundary_day(local: datetime) -> bool:
    boundaries = ((3, sunday(local.year, 3, 2)), (11, sunday(local.year, 11, 1)),
                  (3, sunday(local.year, 3, -1)), (10, sunday(local.year, 10, -1)))
    return any(abs((local.date()-datetime(local.year, m, d).date()).days) <= 1
               for m, d in boundaries)


def models() -> list[str]:
    # UTC-12 through UTC+14 in 15-minute increments; +8 is included explicitly.
    return [f'FIXED:{m}' for m in range(-720, 841, 15)]+['US_2_3', 'EU_2_3']


def read_events(path: Path) -> tuple[dict[str, list[Event]], Counter, dict[str, str]]:
    by_source: dict[str, list[Event]] = defaultdict(list)
    formats: dict[str, str] = {}
    rejected: Counter = Counter()
    with path.open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            if row.get('side') not in ('BUY', 'SELL') or row.get('record_type') != 'TRADE':
                rejected['not_trade'] += 1
                continue
            if int(row.get('identical_signature_candidate_count') or 1) != 1 or row.get('cross_source_duplicate_candidate', '').lower() in ('true', '1'):
                rejected['duplicate_candidate'] += 1
                continue
            try:
                local = datetime.fromisoformat(row['open_time'])
                price = D(row['open_price'])
                if local.tzinfo is not None:
                    rejected['explicit_timezone_requires_separate_path'] += 1
                    continue
                if not price.is_finite() or price <= 0:
                    raise ValueError('Invalid price')
                if boundary_day(local):
                    rejected['dst_boundary_buffer'] += 1
                    continue
            except (KeyError, ValueError, InvalidOperation):
                rejected['invalid_entry'] += 1
                continue
            source = row['source']
            formats[source] = row.get('source_format', 'UNKNOWN')
            by_source[source].append(Event(local, price))
    # One observed entry per source/local five-minute interval, to reduce batch bias.
    # No profit, close time, holding time or group outcome is consulted.
    for source, entries in by_source.items():
        entries.sort(key=lambda e: (e.local, e.price))
        distinct: dict[datetime, Event] = {}
        for event in entries:
            bucket = event.local.replace(minute=event.local.minute//5*5, second=0, microsecond=0)
            distinct.setdefault(bucket, event)
        rejected['same_local_5m_batch'] += len(entries)-len(distinct)
        by_source[source] = list(distinct.values())
    return dict(by_source), rejected, formats


def read_bars(path: Path) -> tuple[dict[int, tuple[Decimal, Decimal]], dict[str, Any]]:
    bars: dict[int, tuple[Decimal, Decimal]] = {}
    zero_volume = invalid = 0
    with path.open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            dt = datetime.fromisoformat(row['timestamp'])
            if dt.tzinfo is None:
                raise ValueError('Market timestamps must be explicitly timezone-aware')
            stamp = int(dt.timestamp())
            if stamp % 300:
                raise ValueError('Market timestamp is not a five-minute boundary')
            lo, hi, volume = (D(row[k]) for k in ('low', 'high', 'volume'))
            if not all(x.is_finite() for x in (lo, hi, volume)) or lo <= 0 or hi < lo:
                invalid += 1
                continue
            if stamp in bars:
                raise ValueError('Duplicate market timestamp')
            if volume <= 0:
                zero_volume += 1
                continue
            bars[stamp] = lo, hi
    if not bars:
        raise ValueError('No valid positive-volume market bars')
    return bars, dict(valid_bars=len(bars), invalid_bars=invalid, zero_volume_bars=zero_volume,
                      start=datetime.fromtimestamp(min(bars), UTC).isoformat(),
                      end=datetime.fromtimestamp(max(bars), UTC).isoformat(), quote_side='BID')


def gap(event: Event, model: str, bars: dict, interval_seconds: int = 300) -> Decimal | None:
    bar = bars.get(utc_stamp(event, model)//interval_seconds*interval_seconds)
    return max(bar[0]-event.price, event.price-bar[1], D(0)) if bar else None


def metrics(values: list[Decimal | None]) -> dict:
    # All hypotheses share the SAME event denominator. Missing quotes are failures,
    # not zeros or silently removed observations. Full +/-14h intersection is empty
    # around the daily trading break, so intersection would discard the whole sample.
    known = [v for v in values if v is not None]
    return dict(n=len(values), missing=len(values)-len(known),
                hits={str(t):sum(v <= t for v in known) for t in TOLERANCES},
                median_gap=str(median(known)) if known else None,
                mean_gap=str(sum(known, D(0))/len(known)) if known else None)


def rate(m: dict, tolerance: str = '0.5') -> float:
    return m['hits'][tolerance]/m['n'] if m['n'] else 0.0


def ordering(m: dict) -> tuple:
    return (-rate(m), m['missing']/m['n'] if m['n'] else 1,
            D(m['mean_gap']) if m['mean_gap'] is not None else D('Infinity'))


def evaluate(source_events: list[Event], bars: dict, interval_seconds: int = 300) -> tuple[dict, list[dict], list[dict]]:
    if interval_seconds not in (60,300):raise ValueError('Only 1m or 5m clock evidence supported')
    def matched_gap(event: Event, model: str) -> Decimal | None:
        return gap(event,model,bars,interval_seconds)
    candidates = models()
    covered = [e for e in source_events if any(utc_stamp(e,m)//interval_seconds*interval_seconds in bars for m in candidates)]
    common = covered  # Fixed union denominator; missing bars count as non-matches.
    # Split by calendar DAY so a batch/day cannot straddle calibration and validation.
    days = sorted({e.local.date() for e in common})
    split = max(1, min(len(days)-1, int(len(days)*.6))) if len(days)>1 else len(days)
    train_days = set(days[:split])
    train = [e for e in common if e.local.date() in train_days]
    valid = [e for e in common if e.local.date() not in train_days]
    # Hypotheses indistinguishable on all observed comparable timestamps are aliases.
    aliases: dict[tuple[int, ...], list[str]] = defaultdict(list)
    for model in candidates:
        aliases[tuple(offset_minutes(model,e.local) for e in common)].append(model)
    scored = []
    for equivalent in aliases.values():
        model = equivalent[0]
        scored.append(dict(model=model, aliases=equivalent,
                           train=metrics([matched_gap(e,model) for e in train]),
                           validation=metrics([matched_gap(e,model) for e in valid])))
    scored.sort(key=lambda s:(ordering(s['train']), s['model']))
    best = scored[0] if scored else None
    runner = scored[1] if len(scored)>1 else None
    train_margin = rate(best['train'])-rate(runner['train']) if runner else 0.0
    # Compare validation winner with EVERY distinct alternative, not only fit runner.
    alternative = max((rate(s['validation']) for s in scored[1:]), default=0.0)
    validation_margin = rate(best['validation'])-alternative if best else 0.0
    fit_days = len(train_days)
    val_days = len(days)-fit_days
    enough = len(common)>=30 and len(train)>=15 and len(valid)>=10 and fit_days>=5 and val_days>=5
    status = ('NO_MARKET_COVERAGE' if not covered else
              'INSUFFICIENT_COMPARABLE_EVENTS' if not enough else
              'PRICE_MISMATCH' if rate(best['validation'])<.5 else
              'STRONG_PRICE_CANDIDATE' if rate(best['train'])>=.8 and rate(best['validation'])>=.8
              and train_margin>=.10 and validation_margin>=.10 else 'AMBIGUOUS')
    row = dict(events=len(source_events), covered_events=len(covered), common_events=len(common),
               train_events=len(train), validation_events=len(valid), train_days=fit_days,
               validation_days=val_days, distinct_hypotheses=len(scored),
               best_model=best['model'] if common else None,
               equivalent_models=best['aliases'] if common else [], status=status,
               train_hit_rate=round(rate(best['train']),6), validation_hit_rate=round(rate(best['validation']),6),
               train_margin=round(train_margin,6), validation_margin=round(validation_margin,6),
               train_missing=best['train']['missing'], validation_missing=best['validation']['missing'],
               production_enabled=False, timezone_status='UNKNOWN')
    monthly = []
    groups: dict[str, list[Event]] = defaultdict(list)
    for event in common:
        groups[event.local.strftime('%Y-%m')].append(event)
    for month, events in sorted(groups.items()):
        scores = [(m, metrics([matched_gap(e,m) for e in events])) for m in candidates]
        scores.sort(key=lambda x:(ordering(x[1]),x[0]))
        monthly.append(dict(month=month, events=len(events), local_best_model=scores[0][0],
                            local_best_hit_rate=round(rate(scores[0][1]),6),
                            selected_model_hit_rate=round(rate(metrics([matched_gap(e,best['model']) for e in events])),6),
                            note='DESCRIPTIVE_ONLY_NOT_HELD_OUT'))
    return row, scored, monthly


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open('w',encoding='utf-8-sig',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(records: Path, market: Path, cases_path: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError('Output already exists; choose a fresh directory')
    inputs = {str(p):sha(p) for p in (records, market, cases_path)}
    events, rejected, formats = read_events(records)
    bars, market_info = read_bars(market)
    sources=[]; detail=[]; monthly=[]
    for source, entries in sorted(events.items()):
        summary, scores, months = evaluate(entries,bars)
        source_key = 'S-'+hashlib.sha256(source.encode()).hexdigest()[:12]
        sources.append(dict(source_key=source_key,source_private=source,format=formats[source],**summary))
        detail.extend(dict(source_key=source_key,**s) for s in scores)
        monthly.extend(dict(source_key=source_key,**m) for m in months)
    cases=json.loads(cases_path.read_text(encoding='utf-8'))['cases']
    coverage=Counter(); coverage_years: dict[str, Counter] = defaultdict(Counter)
    with records.open(encoding='utf-8-sig',newline='') as stream:
        source_by_case={'T-'+hashlib.sha256(r['record_id'].encode()).hexdigest()[:12]:r['source']
                        for r in csv.DictReader(stream)}
    source_status={s['source_private']:s['status'] for s in sources}
    cases_by_source_status=Counter()
    for c in cases:
        cases_by_source_status[source_status.get(source_by_case.get(c['id']), 'NO_RETAINED_EVENTS')]+=1
        try:
            event=Event(datetime.fromisoformat(c['opened_at']),D(c['entry']))
            covered=any(execution_bar(event,m) in bars for m in models())
            key='has_any_candidate_bar' if covered else 'no_candidate_bar'
            coverage[key]+=1
            coverage_years[c['opened_at'][:4]][key]+=1
        except (ValueError,InvalidOperation,KeyError):
            coverage['invalid']+=1
    summary=dict(sources=len(sources), statuses=dict(Counter(s['status'] for s in sources)),
                 formats=dict(Counter(s['format'] for s in sources)), market=market_info,
                 candidate_cases=len(cases),case_coverage=dict(coverage),excluded_events=dict(rejected),
                 case_coverage_by_year={k:dict(v) for k,v in sorted(coverage_years.items())},
                 cases_by_source_diagnostic=dict(cases_by_source_status),
                 strong_candidate_formats=dict(Counter(s['format'] for s in sources if s['status']=='STRONG_PRICE_CANDIDATE')),
                 strong_candidate_alias_counts=dict(Counter(len(s['equivalent_models']) for s in sources if s['status']=='STRONG_PRICE_CANDIDATE')),
                 retained_events=sum(s['events'] for s in sources),
                 common_events=sum(s['common_events'] for s in sources),
                 tested_clock_models=len(models()),tolerance_usd_per_oz=[str(x) for x in TOLERANCES],
                 production_enabled_sources=0, timezone_status='UNKNOWN')
    if any(sha(Path(p))!=value for p,value in inputs.items()):
        raise RuntimeError('Input changed during audit')
    output.mkdir(parents=True)
    write_csv(output/'sources_PRIVATE.csv',sources)
    write_csv(output/'hypotheses_PRIVATE.csv',detail)
    write_csv(output/'months_PRIVATE.csv',monthly)
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'provenance_PRIVATE.json').write_text(json.dumps(dict(inputs=inputs,script_sha256=sha(Path(__file__))),ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 歷史交易與行情時間對齊稽核','',
           '這是離線價格一致性檢查，不會改寫交易時間，也不會自動開啟產品盤面檢索。','',
           f"交易來源範圍：{summary['sources']} 個；保留 {summary['retained_events']} 個來源內五分鐘入場事件。",
           f"行情：{market_info['start']} 至 {market_info['end']}；{market_info['valid_bars']} 根正交易量 BID 棒。",
           f"產品候選 {len(cases)} 筆：任一時差有行情 {coverage['has_any_candidate_bar']} 筆、無行情 {coverage['no_candidate_bar']} 筆。此為粗略覆蓋，不等於已對齊。",'',
           '| 診斷狀態 | 來源數 |','|---|---:|']
    lines += [f'| {k} | {v} |' for k,v in sorted(summary['statuses'].items())]
    lines += ['','## 產品候選的行情覆蓋','',
              '| 年份 | 任一時間假設有棒 | 全部假設均無棒 |','|---|---:|---:|']
    lines += [f"| {year} | {counts.get('has_any_candidate_bar',0)} | {counts.get('no_candidate_bar',0)} |"
              for year,counts in summary['case_coverage_by_year'].items()]
    lines += ['','強價格候選所屬來源合計含 '+str(cases_by_source_status['STRONG_PRICE_CANDIDATE'])+' 筆產品候選；這是來源關聯數，不是已核實可用案例數。',
              '固定時差與美／歐DST若在觀察期間完全相同，會一起列為等價模型；不能據此推定其他季節也相同。']
    lines += ['','## 方法與限制','',
              '- 只用進場時間與成交價，不用盈虧、平倉時間或持有時間選時區。排除已標識的重複候選與美／歐 DST 切換日前後一天。',
              '- 同來源、同本地五分鐘只保留最早一筆，降低拆單重複投票；不同來源仍可能屬同帳戶，不把來源數當獨立帳戶數。',
              '- 掃描 UTC−12 至 UTC+14，每15分鐘一個固定偏移，另測美國／歐洲 GMT+2/+3，共107種假設。固定偏移指來源時間減UTC。',
              '- 比較成交價距離對應執行5分K高低區間的差距；列出0／0.5／1／2美元每盎司容許差。0.5不是已驗證券商價差，只是診斷敏感度設定。',
              '- 各假設使用相同事件分母：任一假設有行情的事件都納入，該假設缺棒就計為不吻合，不把缺棒當零價差，也不自行減少分母。每日休市使全部107種假設的行情交集可能為空，所以不採全假設交集。',
              '- 按交易日先60%選假設、後40%驗證；同日不跨兩邊。等價假設保留別名，不因排序挑一個就稱已確認DST。',
              '- 強價格候選要求共同事件至少30、前15／後10筆、兩邊各至少5天，前後吻合率皆≥80%，對其他不同假設領先皆≥10百分點；這些是篩檢條件，不是統計信心水準。',
              '- 月報只用來找來源內時差變化或混合期間，不作為驗證結果；來源跨時期異常需分段查證。',
              '- 5分K區間寬，跨券商BID／ASK及成交差異都可能造成歧義；強價格候選仍需原報表時間設定、券商對應日期公告或高精度行情等獨立證據。',
              '- 執行所在K棒用於離線對時，不能當下單前特徵；產品要取「最早可能下單時間之前已收完」的棒，缺棒不向未來補值。',
              '- 原有 broker_timezone.py 以歐洲DST推定部分券商，不是所有新增CSV／FTMO來源的核實證據，本次未沿用其已確認標籤。',
              '- 來源清單、逐來源偏移與月份結果均只保存在 product/private，不公開。','',
              '## 後續直接開發順序','',
              '1. 從強價格候選挑足量且跨月穩定的來源，以獨立時間設定證據完成核實。',
              '2. 補足缺行情期間；歧義來源改用小窗口1分BID／ASK或原券商成交行情，避免整批十年下載。',
              '3. 建立逐來源／逐期間UTC轉換與來源證據；未核實仍維持UNKNOWN。',
              '4. 依已收盤K線生成盤面條件，接進相似案例、案例圖表與差異說明，最後整體驗收。','',
              '官方資料：FTMO 2023/03/02公告顯示美國與歐洲DST切換曾相差兩週，不能共用同一切換規則。',
              'https://ftmo.com/en/blog/trading-updates/trading-update-02-mar-2023/']
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return summary


def main() -> None:
    root=Path(__file__).resolve().parents[3]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--records',type=Path,default=root/'artifacts/behavior_audit_20261001_final/gold_behavior_records.csv')
    parser.add_argument('--market',type=Path,default=root/'artifacts/market_data/xauusd_5m_bars.csv')
    parser.add_argument('--cases',type=Path,default=root/'product/private/cases.json')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(run(args.records,args.market,args.cases,args.output),ensure_ascii=False))


if __name__=='__main__':
    main()
