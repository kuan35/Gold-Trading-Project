from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.live_candidate_profile import _closed_frame, profile_from_live_snapshot
from scripts.stream_ctrader_demo import decode_symbol_schedule


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


def test_broker_session_gap_is_allowed_without_inventing_candles():
    # The broker closes XAUUSD after Monday 16:59 New York time and reopens
    # at 18:01. cTrader has no 15m bars between 20:45 and 22:00 UTC.
    left = int(datetime(2026, 10, 19, 20, 45, tzinfo=timezone.utc).timestamp())
    right = int(datetime(2026, 10, 19, 22, 0, tzinfo=timezone.utc).timestamp())
    bars = [{'time': time, 'open': 4000, 'high': 4001, 'low': 3999,
             'close': 4000.5} for time in (left, right)]
    schedule = {'time_zone': 'America/New_York', 'intervals': [
        {'start_second': 64860, 'end_second': 147540},
        {'start_second': 151260, 'end_second': 233940}]}
    assert _closed_frame(bars, 900, 2, right + 900, schedule) == bars
    with pytest.raises(ValueError, match='BAR_GAP_OR_DUPLICATE'):
        _closed_frame(bars, 900, 2, right + 900, None)


def test_missing_broker_bar_during_open_session_still_blocks_retrieval():
    left = int(datetime(2026, 10, 20, 3, 0, tzinfo=timezone.utc).timestamp())
    right = left + 1800
    bars = [{'time': time, 'open': 4000, 'high': 4001, 'low': 3999,
             'close': 4000.5} for time in (left, right)]
    schedule = {'time_zone': 'America/New_York', 'intervals': [
        {'start_second': 151260, 'end_second': 233940}]}
    with pytest.raises(ValueError, match='BAR_GAP_OR_DUPLICATE'):
        _closed_frame(bars, 900, 2, right + 900, schedule)


def test_broker_session_gap_follows_new_york_dst_transition():
    # The same local Monday break shifts one UTC hour after DST ends.
    left = int(datetime(2026, 11, 2, 21, 45, tzinfo=timezone.utc).timestamp())
    right = int(datetime(2026, 11, 2, 23, 0, tzinfo=timezone.utc).timestamp())
    bars = [{'time': time, 'open': 4000, 'high': 4001, 'low': 3999,
             'close': 4000.5} for time in (left, right)]
    schedule = {'time_zone': 'America/New_York', 'intervals': [
        {'start_second': 64860, 'end_second': 147540},
        {'start_second': 151260, 'end_second': 233940}]}
    assert _closed_frame(bars, 900, 2, right + 900, schedule) == bars


def test_incomplete_broker_schedule_never_licenses_missing_candles():
    left = int(datetime(2026, 10, 19, 20, 45, tzinfo=timezone.utc).timestamp())
    right = int(datetime(2026, 10, 19, 22, 0, tzinfo=timezone.utc).timestamp())
    bars = [{'time': time, 'open': 4000, 'high': 4001, 'low': 3999,
             'close': 4000.5} for time in (left, right)]
    symbol = SimpleNamespace(scheduleTimeZone='America/New_York', schedule=[
        SimpleNamespace(startSecond=64860, endSecond=147540),
        SimpleNamespace(startSecond=151260, endSecond=233940),
        SimpleNamespace(startSecond=999999, endSecond=1000000),
    ])
    with pytest.raises(ValueError, match='BAR_GAP_OR_DUPLICATE'):
        _closed_frame(bars, 900, 2, right + 900, decode_symbol_schedule(symbol))
