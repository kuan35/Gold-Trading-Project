from copy import deepcopy
from datetime import datetime,timezone

from research.sample_live_dual_paths import selected_queries
from backend.tests.test_live_candidate_profile import CLOCK,frame


def test_ten_fixed_clocks_alternate_sides_and_do_not_read_later_candles():
    snapshot=dict(quote={'source_time_utc':datetime.fromtimestamp(CLOCK+12,timezone.utc).isoformat()},
                  bars={'5m':frame(300,119),'1h':frame(3600,119)})
    original=deepcopy(snapshot)
    result=list(selected_queries(snapshot))
    assert len(result)==10 and len({r['as_of'] for r in result})==10
    assert [r['side'] for r in result]==['BUY','SELL']*5
    assert result[-1]['as_of']==CLOCK and result[0]['as_of']==CLOCK-9*300
    for r in result:
        for iv,seconds in [('5m',300),('1h',3600)]:
            assert all(b['time']+seconds<=r['as_of'] for b in r['profile']['pre_entry_bars'][iv])
    assert snapshot==original
    future=dict(time=CLOCK,open=9999,high=10000,low=9998,close=9999)
    snapshot['bars']['5m'].append(future)
    assert list(selected_queries(snapshot))==result
