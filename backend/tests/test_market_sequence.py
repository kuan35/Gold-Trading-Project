import pytest

from backend.market_sequence import describe_market_sequence


def profile(anchors, *, as_of=60 * 300):
    closes = []
    for start, end, count in zip(anchors, anchors[1:], (19, 20, 20)):
        closes.extend(start + (end - start) * step / count for step in range(count))
    closes.append(anchors[-1])
    assert len(closes) == 60
    return {
        'status': 'candidate_only', 'tier': 'full', 'as_of': as_of,
        'timezone_status': 'UNKNOWN', 'profit': '9999',
        'indicators': {'5m_atr_pct': '1'},
        'pre_entry_bars': {'5m': [
            {'time': index * 300, 'close': str(close)}
            for index, close in enumerate(closes)]},
    }


def test_same_net_change_can_have_different_three_phase_sequence():
    first = describe_market_sequence(profile((100, 120, 90, 100)))
    second = describe_market_sequence(profile((100, 80, 110, 100)))
    assert first['pattern_code'] == 'UDU'
    assert second['pattern_code'] == 'DUD'
    assert '9999' not in first['text']
    assert '2026' not in first['text']


def test_small_segment_move_is_neutral_and_future_bar_is_rejected():
    quiet = describe_market_sequence(profile((100, 100.2, 100.4, 100.2)))
    assert quiet['pattern_code'] == 'SSS'
    invalid = profile((100, 120, 90, 100))
    invalid['pre_entry_bars']['5m'][-1]['time'] = invalid['as_of']
    with pytest.raises(ValueError, match='future'):
        describe_market_sequence(invalid)
