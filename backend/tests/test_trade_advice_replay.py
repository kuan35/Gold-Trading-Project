from collections import Counter
from decimal import Decimal

from backend.trade_advice_replay import _hours, _queries, replay, summarize


def profile(kind, side="BUY"):
    return {"status": "candidate_only", "kind": kind, "side": side}


def test_replay_freezes_decision_before_reading_outcomes_and_counts_onsets_once():
    events = []
    queries = [
        (0, profile(None, None)),
        (300, profile("ABOVE")),
        (600, profile("ABOVE")),
        (900, profile(None, None)),
        (1200, profile("BELOW", "SELL")),
        (1800, profile("ABOVE")),  # missing previous snapshot
    ]

    def decide(query):
        assert set(query) == {"status", "kind", "side"}
        events.append(("decide", query["kind"]))
        return {"action": "WAIT" if query["kind"] == "ABOVE" else "SELL",
                "reason_code": "COST_STRESS" if query["kind"] == "ABOVE" else "SUPPORTED"}

    def score(clock):
        events.append(("score", clock))
        return {"BUY": {"baseline_pct": Decimal("0.3"), "mae_pct": Decimal("0.02")},
                "SELL": {"baseline_pct": Decimal("-0.4"), "mae_pct": Decimal("0.5")}}

    records = replay(queries, 300, 2100, lambda query: query, decide, score)
    assert events == [("decide", "ABOVE"), ("score", 300), ("decide", "BELOW"), ("score", 1200)]
    result = summarize(records)
    assert result["overall"]["opportunities"] == 2
    assert result["overall"]["baseline"]["entries"] == 2
    assert result["overall"]["with_history"]["entries"] == 1
    assert result["overall"]["waiting"]["missed_positive"] == 1
    assert result["by_signal"]["BELOW"]["with_history"]["median_net_price_return_pct"] == "-0.4"


def test_missing_evaluation_window_preserves_opportunity_and_excludes_performance_denominator():
    queries = [(0, profile(None, None)), (300, profile("ABOVE"))]
    records = replay(queries, 300, 600, lambda query: query,
                     lambda query: {"action": "BUY", "reason_code": "SUPPORTED"}, lambda _: None)
    result = summarize(records)["overall"]
    assert result["opportunities"] == 1
    assert result["baseline"]["entries"] == 1
    assert result["with_history"]["entries"] == 1
    assert result["with_history"]["scored"] == 0
    assert result["with_history"]["median_net_price_return_pct"] is None


def test_native_profiles_only_use_closed_market_bars():
    start = 22 * 3600
    five = {}
    for stamp in range(0, start + 2 * 3600, 300):
        price = str(100 + stamp // 300)
        five[stamp] = dict(time=stamp, open=price, high=price, low=price, close=price, volume=20)
    coverage = Counter()
    queries = dict(_queries(five, _hours(five), "a" * 64, start, start + 600, coverage))
    before_hour = queries[start + 300]
    assert before_hour["status"] == "candidate_only"
    assert before_hour["pre_entry_bars"]["5m"][-1]["time"] == start
    assert before_hour["pre_entry_bars"]["1h"][-1]["time"] == start - 3600
    assert before_hour["tick_volume"]["last_closed_at"] == start + 300
    assert coverage == {"PROFILE_READY": 2}
