from decimal import Decimal
import numpy as np
import pytest
from research.five_minute_lookback import closed_window, normalise_closes, rank_windows
from backend.candidate_bars import complete_frames


def bars(n=10):
    return [dict(time=i*300,open='100',high='102',low='99',close=str(100+i/10)) for i in range(n)]


def test_three_five_minute_ohlc_aggregate_not_three_closes():
    data=bars(3)
    data[0].update(open='100',high='105',low='99',close='102')
    data[1].update(open='102',high='103',low='95',close='98')
    data[2].update(open='98',high='108',low='97',close='106')
    result=complete_frames(data,900,900)
    assert result==[dict(time=0,open='100',high='108',low='95',close='106')]
    assert complete_frames(data,899,900)==[]


def test_closed_window_excludes_forming_bar_and_requires_freshness():
    data=bars();times=[b['time'] for b in data]
    result,reason=closed_window(data,times,1801,5,set())
    assert reason is None and [b['time'] for b in result]==[300,600,900,1200,1500]
    result,reason=closed_window(data[:6],times[:6],2100,5,set())
    assert not result and reason=='STALE_LAST_CLOSED_BAR'


def test_gap_requires_exact_existing_evidence_and_never_fills():
    data=bars();data=[b for b in data if b['time']!=900];times=[b['time'] for b in data]
    result,reason=closed_window(data,times,2100,6,set())
    assert reason=='UNEXPLAINED_GAP'
    result,reason=closed_window(data,times,2100,6,{(900,1200)})
    assert reason is None and len(result)==6 and 900 not in [b['time'] for b in result]


def test_insufficient_history_not_padded():
    result,reason=closed_window(bars(3),[0,300,600],900,4,set())
    assert not result and reason=='INSUFFICIENT_HISTORY'


def test_invalid_ohlc_rejected():
    data=bars(5);data[0]['high']='90'
    with pytest.raises(ValueError):closed_window(data,[b['time'] for b in data],1500,5,set())


def test_close_path_is_scale_invariant_and_rebased_per_window():
    data=bars()
    scaled=[dict(b,close=str(Decimal(b['close'])*2)) for b in data]
    np.testing.assert_allclose(normalise_closes(data),normalise_closes(scaled))
    assert normalise_closes(data[-5:])[0]==0


def test_worst_axis_prevents_one_close_window_hiding_bad_long_window():
    pool=[dict(id='A',group='a'),dict(id='B',group='b'),dict(id='C',group='c')]
    desc={i:dict(structure='IN_RANGE',end_5m=n,end_1h=n) for n,i in enumerate(('A','B','C'))}
    # A best short but worst long; B balanced, C worst short but best long.
    distance=[np.array([0,1,2]),np.array([2,1,0])]
    ranked=rank_windows(pool,desc,dict(structure='IN_RANGE'),distance)
    assert ranked[0]['case_id']=='B'
    assert [x['case_id'] for x in rank_windows(list(reversed(pool)),desc,dict(structure='IN_RANGE'),[d[::-1] for d in distance])]==[x['case_id'] for x in ranked]
