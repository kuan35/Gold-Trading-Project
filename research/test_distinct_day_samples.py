from datetime import datetime,timezone
from types import SimpleNamespace

from scripts.fetch_ctrader_review_days import sample_clocks,decode_closed
from research.distinct_day_samples import queries


def test_fixed_ten_weeks_are_nonoverlapping_and_predeclared():
    clocks=sample_clocks()
    assert len(clocks)==11 and len(set(clocks))==11
    assert all(b-a==7*86400 for a,b in zip(clocks,clocks[1:]))
    assert datetime.fromtimestamp(clocks[-1],timezone.utc).isoformat()=='2026-10-20T15:00:00+00:00'


def test_decode_preserves_decimal_and_excludes_forming_candle():
    raw=SimpleNamespace(utcTimestampInMinutes=30000000,low=250000001,
                        deltaOpen=10,deltaHigh=30,deltaClose=20,volume=5)
    opened=raw.utcTimestampInMinutes*60
    assert decode_closed(raw,300,opened+299) is None
    bar=decode_closed(raw,300,opened+300)
    assert bar['low']=='2500.00001' and bar['close']=='2500.00021'
    assert bar['time']==opened


def test_ten_query_windows_are_distinct_and_future_bars_ignored():
    from backend.tests.test_dual_path_retrieval import candles
    packet={'status':'COMPLETE','records':[dict(as_of=c,bars={'5m':candles(300,80,c),'1h':candles(3600,30,c)}) for c in sample_clocks()]}
    from decimal import Decimal
    for number,r in enumerate(packet['records']):
        for bars in r['bars'].values():
            for j,b in enumerate(bars):
                for key in ('open','high','low','close'):
                    b[key]=str(Decimal(b[key])+Decimal(number*j)/1000)
    packet['records'][4]['bars']['1h'].pop(-5)
    result=list(queries(packet))
    assert len(result)==10
    assert [r['side'] for r in result]==['BUY','SELL']*5
    for prev,nxt in zip(result,result[1:]):
        assert prev['query_description']['window_end']<nxt['query_description']['window_start']
    import copy
    future=copy.deepcopy(packet)
    for r in future['records']:
        for iv,seconds in [('5m',300),('1h',3600)]:
            r['bars'][iv]+=candles(seconds,1,r['as_of']+seconds)
    assert list(queries(future))==result
