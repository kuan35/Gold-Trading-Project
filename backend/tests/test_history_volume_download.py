from types import SimpleNamespace
import pytest
from scripts.fetch_ctrader_history_volume import plan,decode_page,next_cursor,WEEK


def test_plan_deduplicates_weeks_but_keeps_native_intervals():
    p={'a':{'pre_entry_bars':{'5m':[{'time':300},{'time':600}], '1h':[{'time':0}]}},'b':{'pre_entry_bars':{'5m':[{'time':WEEK}]}}}
    tasks=plan(p)
    assert [(t['interval'],t['start']) for t in tasks]==[('5m',0),('5m',WEEK),('1h',0)]


def test_native_tick_volume_is_integer_and_pagination_goes_back_without_overlap():
    bar=SimpleNamespace(utcTimestampInMinutes=5,low=200000000,deltaOpen=0,deltaHigh=10,deltaClose=5,volume=150)
    task={'interval':'5m','start':0,'end':WEEK}
    page=decode_page([bar],task,600)
    assert page[0]['volume']==150 and page[0]['open']=='2000'
    assert next_cursor(page,1000000)==299999
    with pytest.raises(ValueError):next_cursor([],1000000)
    with pytest.raises(ValueError):next_cursor(page,100)
    padded=dict(task,start=600)
    assert decode_page([bar],padded,900)==[]
    bar.volume=-1
    with pytest.raises(ValueError):decode_page([bar],task,600)


def test_native_volume_frame_uses_only_closed_bars_and_excludes_current_from_baseline():
    from scripts.build_native_volume_index import frame
    rows={i*3600:{'time':i*3600,'volume':10 if i<20 else 40} for i in range(22)}
    f=frame(rows,sorted(rows),21*3600,'1h')
    assert len(f['times'])==20 and f['times'][-1]==20*3600
    assert f['prior20_mean']=='10' and f['relative_volume_ratio']=='4'
    assert f['bars_closed_before_asof'] and f['gap_count']==0


def test_incomplete_volume_window_does_not_invent_a_baseline_or_gap():
    from scripts.build_native_volume_index import frame
    rows={i*3600:{'time':i*3600,'volume':10} for i in range(3)}
    f=frame(rows,sorted(rows),3*3600,'1h')
    assert f['status']=='INSUFFICIENT_OR_STALE'
    assert f['relative_volume_ratio'] is None and f['gap_count']==0


def test_volume_window_reports_market_breaks_and_staleness():
    from scripts.build_native_volume_index import frame
    rows={i*3600:{'time':i*3600,'volume':10} for i in range(23) if i!=10}
    f=frame(rows,sorted(rows),23*3600,'1h')
    assert f['status']=='AVAILABLE' and f['window_gap_count']==1 and f['gap_count']==1
    stale=frame(rows,sorted(rows),30*3600,'1h')
    assert stale['status']=='INSUFFICIENT_OR_STALE'
