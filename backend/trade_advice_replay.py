"""Compare entry advice against the same chronological market replay without orders."""

from argparse import ArgumentParser
from bisect import bisect_left
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
from statistics import median

from .candidate_sidecar import load_candidate_sidecar
from .context_retrieval import ContextIndex
from .dual_path_retrieval import profile_from_dual_frames
from .forward_outcomes import HistoricalOutcomeStore, build_case_outcome
from .tick_volume import BASIS, NativeTickStore, tick_frame


SIGNALS = ("ABOVE", "BELOW", "LOWER_RECLAIM", "UPPER_RECLAIM")
SIDES = ("BUY", "SELL")
STEP = 300
PRICE_FIELDS = ("open", "high", "low", "close")


def replay(queries, start, end, signal, decide, score):
    records = []
    prior_clock, prior_kind = None, None
    for clock, query in queries:
        if clock >= end:
            break
        if query["status"] != "candidate_only":
            prior_clock, prior_kind = None, None
            continue
        current = signal(query)
        kind, side = current["kind"], current["side"]
        if clock >= start and prior_clock == clock - STEP and kind != prior_kind and side in SIDES:
            advice = decide(query)
            result = score(clock)
            records.append(dict(as_of_utc=clock, signal=kind, baseline_side=side, advice_action=advice["action"],
                                reason=advice["reason_code"], result=result,
                                matched_pairs=(advice.get("simulations") or {}).get("count")))
        prior_clock, prior_kind = clock, kind
    return records


def _text(number):
    return format(number, "f")


def _returns(records, choose):
    selected = [(row, choose(row)) for row in records if choose(row) in SIDES]
    scored = [row["result"][side] for row, side in selected if row["result"] is not None]
    returns = [item["baseline_pct"] for item in scored]
    stress = [item["stress_pct"] for item in scored if "stress_pct" in item]
    adverse = [item["mae_pct"] for item in scored]
    rate = Decimal(len(selected)) * 100 / len(records) if records else None
    return dict(entries=len(selected), entry_rate_pct=_text(round(rate, 2)) if rate is not None else None,
                scored=len(scored), positive=sum(value > 0 for value in returns),
                median_net_price_return_pct=_text(median(returns)) if returns else None,
                mean_net_price_return_pct=_text(sum(returns) / len(returns)) if returns else None,
                median_stress_net_price_return_pct=_text(median(stress)) if stress else None,
                median_maximum_adverse_pct=_text(median(adverse)) if adverse else None,
                worst_maximum_adverse_pct=_text(max(adverse)) if adverse else None)


def _aggregate(records):
    waiting = [row for row in records if row["advice_action"] == "WAIT"]
    scores = [row["result"][row["baseline_side"]]["baseline_pct"] for row in waiting if row["result"] is not None]
    return dict(opportunities=len(records), with_complete_outcome=sum(row["result"] is not None for row in records),
                baseline=_returns(records, lambda row: row["baseline_side"]),
                with_history=_returns(records, lambda row: row["advice_action"]),
                waiting=dict(total=len(waiting), scored=len(scores), avoided_negative=sum(value < 0 for value in scores),
                             missed_positive=sum(value > 0 for value in scores), flat=sum(value == 0 for value in scores),
                             reasons=dict(sorted(Counter(row["reason"] for row in waiting).items()))))


def summarize(records):
    return dict(overall=_aggregate(records),
                by_signal={kind: _aggregate([row for row in records if row["signal"] == kind]) for kind in SIGNALS})


def _market_chunks(folder, start, end):
    rows = {}
    sources = set()
    digests = {}
    for path in sorted(folder.glob("5m-*.json")):
        try:
            chunk_start = int(path.stem.split("-", 1)[1])
        except ValueError:
            continue
        if chunk_start >= end + 1800 or chunk_start + 7 * 86400 <= start - 4 * 86400:
            continue
        raw = path.read_bytes()
        chunk = json.loads(raw)
        if (chunk.get("interval") != "5m" or chunk.get("volume_basis") != BASIS
                or chunk.get("source") != "ctrader_demo_native" or chunk.get("start") != chunk_start
                or type(chunk.get("end")) is not int or chunk["end"] <= chunk_start
                or chunk.get("status") not in ("AVAILABLE", "EMPTY")
                or not isinstance(chunk.get("bars"), list)
                or (chunk["status"] == "EMPTY") != (not chunk["bars"])
                or not isinstance(chunk.get("source_key"), str)):
            raise ValueError("歷史行情區塊無效")
        digests[path.name] = sha256(raw).hexdigest()
        sources.add(chunk["source_key"])
        for bar in chunk["bars"]:
            stamp = bar["time"]
            if type(stamp) is not int or stamp % STEP or not chunk_start <= stamp < chunk["end"] or stamp in rows:
                raise ValueError("歷史行情時間無效或重複")
            if not start - 4 * 86400 <= stamp < end + 1800:
                continue
            prices = [Decimal(str(bar[key])) for key in PRICE_FIELDS]
            if (any(not value.is_finite() for value in prices)
                    or not 0 < prices[2] <= min(prices[0], prices[3]) <= max(prices[0], prices[3]) <= prices[1]):
                raise ValueError("歷史行情價格無效")
            rows[stamp] = dict(bar, observed_minutes=5)
    if not rows or len(sources) != 1:
        raise ValueError("回放需要單一來源的原生五分行情")
    return rows, sources.pop(), digests


def _hours(five):
    output = {}
    for start in (stamp for stamp in five if stamp % 3600 == 0):
        bars = [five.get(start + STEP * i) for i in range(12)]
        if not all(bars):
            continue
        output[start] = dict(time=start, open=bars[0]["open"], close=bars[-1]["close"],
                             high=max((bar["high"] for bar in bars), key=Decimal),
                             low=min((bar["low"] for bar in bars), key=Decimal), observed_minutes=60)
    return output


def _queries(five, hour, source, start, end, coverage):
    f_times, h_times = sorted(five), sorted(hour)
    for stamp in f_times:
        clock = stamp + STEP
        if clock < start - STEP:
            continue
        if clock >= end:
            break
        f_end, h_end = bisect_left(f_times, clock), bisect_left(h_times, clock // 3600 * 3600)
        bars = [five[t] for t in f_times[max(0, f_end - 61):f_end]]
        hours = [hour[t] for t in h_times[max(0, h_end - 20):h_end]]
        query = profile_from_dual_frames(bars, hours, clock)
        if query["status"] == "candidate_only":
            query["tick_volume"] = tick_frame(bars, clock, source)
        if clock >= start:
            coverage[query.get("reason", "PROFILE_READY")] += 1
        yield clock, query


class _TrainingOutcomes:
    def __init__(self, store, cutoff):
        self.store = store
        self.cutoff = cutoff

    def get(self, case_id, query_as_of):
        return self.store.get(case_id, min(self.cutoff, query_as_of))


def run(root, start, end, costs):
    from .trade_advice import measure_pair, signal_for_query, trade_advice

    cases_path, profiles_path = root / "cases.json", root / "case_candidate_market_profiles.json"
    profiles, status = load_candidate_sidecar(cases_path, profiles_path, root)
    if status != "READY":
        raise ValueError(f"歷史案例盤面不可用（{status}）")
    cases = json.loads(cases_path.read_text(encoding="utf-8"))["cases"]
    training = [case for case in cases if case["id"] in profiles and profiles[case["id"]]["as_of"] < start
                and type(case.get("available_at")) is int and case["available_at"] <= start]
    if not training:
        raise ValueError("保留期間以前沒有已成熟的案例")
    store = NativeTickStore(root)
    five, source, chunks = _market_chunks(root / "history_native", start, end)
    # All case ticks are validated by the same production store. Archive
    # queries have their own native source key and go through the same check.
    index = ContextIndex(training, profiles, tick_volume_store=store)
    forward = HistoricalOutcomeStore(root)
    frozen = _TrainingOutcomes(forward, start)
    coverage = Counter()

    def decide(query):
        return trade_advice(index, query, frozen, costs)

    def score(clock):
        next_bars = [five[t] for t in range(clock, clock + 1800, STEP) if t in five]
        return measure_pair(build_case_outcome("BUY", clock, next_bars), costs)

    records = replay(_queries(five, _hours(five), source, start, end, coverage),
                     start, end, signal_for_query, decide, score)
    source_files = (cases_path, profiles_path, forward.path, store.path)
    policy = Path(__file__).resolve().parent
    policy_files = ("trade_advice.py", "trade_advice_replay.py", "context_retrieval.py", "context_rules.py")
    return dict(method="gold_trade_advice_holdout_v1",
                start_utc=datetime.fromtimestamp(start, timezone.utc).isoformat(),
                end_exclusive_utc=datetime.fromtimestamp(end, timezone.utc).isoformat(),
                query_source="cTrader DEMO archive, native BID, M5 and complete aggregated H1",
                historical_source="HistData BID project reference and source-bound native tick counts",
                results_basis="30-minute net returns as a percentage of entry price. Overlapping horizons count as separate opportunities.",
                costs=dict(costs), training_case_rows=len(training),
                profile_coverage=dict(sorted(coverage.items())),
                inputs_sha256={path.name: sha256(path.read_bytes()).hexdigest() for path in source_files if path.is_file()},
                policy_sha256={name: sha256((policy / name).read_bytes()).hexdigest() for name in policy_files},
                market_chunks_sha256=chunks, **summarize(records), records=records)


def _date(value):
    return int(datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, default=Path(__file__).resolve().parents[1] / "private")
    parser.add_argument("--start", required=True, help="UTC YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="Exclusive UTC YYYY-MM-DD")
    parser.add_argument("--baseline", required=True, help="Round-trip scenario cost, USD/oz")
    parser.add_argument("--stress", required=True, help="Higher round-trip scenario cost, USD/oz")
    parser.add_argument("--output", required=True, type=Path, help="New JSON report path relative to private root")
    args = parser.parse_args(argv)
    root = args.private_root.resolve()
    output = (root / args.output).resolve()
    try:
        start, end = _date(args.start), _date(args.end)
        baseline, stress = Decimal(args.baseline), Decimal(args.stress)
        if not 0 < end - start <= 31 * 86400:
            raise ValueError("每次回放使用最多 31 日的正向日期區間")
        if not all(value.is_finite() for value in (baseline, stress)) or not 0 <= baseline < stress <= 1000:
            raise ValueError("成本須符合 0 ≤ 基準 < 較高 ≤ 1000 USD/oz")
        if not output.is_relative_to(root) or output.suffix.lower() != ".json" or output.exists():
            raise ValueError("請指定私有資料夾內尚未存在的 JSON 報告")
        report = run(root, start, end, dict(baseline_usd_per_oz=_text(baseline), stress_usd_per_oz=_text(stress)))
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, default=_text, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
    except (OSError, ValueError, InvalidOperation) as exc:
        parser.error(str(exc))
    print(json.dumps(dict(start_utc=report["start_utc"], end_exclusive_utc=report["end_exclusive_utc"],
                          profile_coverage=report["profile_coverage"], **report["overall"]), ensure_ascii=True))


if __name__ == "__main__":
    main()
