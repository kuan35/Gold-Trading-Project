from decimal import Decimal

from backend.candidate_bars import classify_coverage
from backend.candidate_profile import profile_before_entry


def trending_bars(count=264):
    rows = []
    for index in range(count):
        price = Decimal('1900') + Decimal(index) / 10
        rows.append(dict(time=index * 300, open=str(price), high=str(price + 1),
                         low=str(price - 1), close=str(price + Decimal('.25'))))
    return rows


def scaled(bars, factor):
    return [dict(bar, **{key: str(Decimal(bar[key]) * factor)
                         for key in ('open', 'high', 'low', 'close')}) for bar in bars]


def test_closed_profile_is_scale_invariant_and_ignores_future_bars():
    bars = trending_bars()
    clock = 264 * 300
    coverage = classify_coverage(bars, clock, [])
    profile = profile_before_entry(bars, clock, coverage)
    assert profile['status'] == 'candidate_only'
    assert profile['tier'] == 'full'
    assert len(profile['shape']) == 240
    assert profile['latest_closed']['5m'] <= clock
    assert '1h_ma_gap' in profile['indicators']
    assert '1h_macd_hist' not in profile['indicators']
    future = dict(time=clock, open='9999', high='10000', low='9998', close='9999')
    assert profile_before_entry(bars + [future], clock, coverage) == profile
    doubled = profile_before_entry(scaled(bars, 2), clock, coverage)
    assert all(abs(Decimal(a) - Decimal(b)) < Decimal('1e-18')
               for a, b in zip(doubled['shape'], profile['shape']))
    assert all(abs(Decimal(doubled['indicators'][key]) - Decimal(value)) < Decimal('1e-18')
               for key, value in profile['indicators'].items())


def test_missing_atr_or_first_previous_close_fails_closed():
    bars = trending_bars()
    clock = 264 * 300
    coverage = classify_coverage(bars, clock, [])
    assert profile_before_entry(bars[-60:], clock, coverage)['status'] == 'insufficient'
    flat = [dict(bar, open='2000', high='2000', low='2000', close='2000') for bar in bars]
    assert profile_before_entry(flat, clock, coverage)['status'] == 'insufficient'
    assert profile_before_entry(bars, clock, dict(coverage, tier='none'))['status'] == 'insufficient'
