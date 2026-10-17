"""Closed-bar and evidence-gated candidate coverage."""

from backend.candidate_bars import classify_coverage, classify_gap, complete_frames


def bars_for_hours(hours: int, missing: set[int] | None = None):
    missing = missing or set()
    return [dict(time=t, open='2000', high='2001', low='1999', close='2000.5')
            for t in range(0, hours * 3600, 300) if t not in missing]


def test_hour_requires_all_twelve_closed_constituents():
    bars = bars_for_hours(1)
    assert complete_frames(bars, 3599, 3600) == []
    assert len(complete_frames(bars, 3600, 3600)) == 1
    assert complete_frames(bars[:-1], 3600, 3600) == []


def test_session_gap_needs_exact_independent_evidence():
    gap = set(range(8 * 3600, 9 * 3600, 300))
    bars = bars_for_hours(22, gap)
    clock = 22 * 3600
    assert classify_gap(8 * 3600, 9 * 3600, []) == 'UNEXPLAINED_GAP'
    assert classify_gap(8 * 3600, 9 * 3600, [(8 * 3600, 9 * 3600)]) == 'SESSION_GAP'
    no_evidence = classify_coverage(bars, clock, [])
    approved = classify_coverage(bars, clock, [(8 * 3600, 9 * 3600)])
    assert no_evidence['status'] == 'UNEXPLAINED_GAP'
    assert approved['tier'] == 'full'
    assert any(g['reason'] == 'SESSION_GAP' for g in approved['gaps'])


def test_conflicting_native_hour_is_not_silently_selected():
    bars = bars_for_hours(22)
    alternate = {21 * 3600: dict(time=21 * 3600, open='2000', high='2001',
                                  low='1999', close='1999.5')}
    result = classify_coverage(bars, 22 * 3600, [], alternate)
    assert result['status'] == 'SOURCE_CONFLICT'
    assert result['tier'] != 'full'
    assert result['source_conflicts']
