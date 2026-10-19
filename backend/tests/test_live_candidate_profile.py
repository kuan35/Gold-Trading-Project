from datetime import datetime, timezone

from backend.live_candidate_profile import profile_from_live_snapshot


CLOCK = 1800000000


def frame(seconds, count):
    result = []
    for index in range(count):
        close = 2500 + index * 0.04 + (index % 7) * 0.02
        result.append({'time': CLOCK - (count - index) * seconds,
                       'open': close - 0.1, 'high': close + 0.3,
                       'low': close - 0.3, 'close': close, 'volume': 1})
    return result


def snapshot():
    return {'connection_status': 'CONNECTED',
            'quote': {'status': 'CURRENT',
                      'source_time_utc': datetime.fromtimestamp(CLOCK + 10, timezone.utc).isoformat()},
            'bars': {'5m': frame(300, 100), '15m': frame(900, 70), '1h': frame(3600, 30)}}


def test_live_profile_uses_only_closed_native_frames_and_same_hybrid_schema():
    value = profile_from_live_snapshot(snapshot())
    assert value['status'] == 'candidate_only'
    assert value['source'] == 'ctrader_demo_xauusd'
    assert value['as_of'] == CLOCK
    assert value['tier'] == 'full'
    assert len(value['pre_entry_bars']['5m']) == 60
    assert len(value['pre_entry_bars']['15m']) == 60
    assert len(value['pre_entry_bars']['1h']) == 20
    assert all(end <= CLOCK for end in value['latest_closed'].values())
    assert '15m_rsi14' in value['indicators']
    assert '1h_atr_pct' in value['indicators']


def test_live_profile_rejects_missing_or_forming_bar_instead_of_filling_zero():
    source = snapshot()
    source['bars']['5m'].pop(-10)
    assert profile_from_live_snapshot(source)['reason'] == 'BAR_GAP_OR_DUPLICATE'
    source = snapshot()
    source['bars']['1h'][-1]['time'] = CLOCK
    assert profile_from_live_snapshot(source)['reason'] == 'FORMING_OR_UNALIGNED_BAR'


def test_live_profile_requires_current_quote_and_last_five_minute_close():
    source = snapshot()
    source['quote']['status'] = 'STALE'
    assert profile_from_live_snapshot(source)['reason'] == 'BROKER_QUOTE_UNAVAILABLE'
    source = snapshot()
    source['bars']['5m'].pop()
    assert profile_from_live_snapshot(source)['reason'] == 'STALE_CLOSED_BAR'
