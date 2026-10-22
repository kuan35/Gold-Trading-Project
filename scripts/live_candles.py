"""Display-only candles from observed BID updates. Never a retrieval source."""
from copy import deepcopy
from decimal import Decimal

SPANS={'5m':300,'15m':900,'1h':3600}


class LiveCandles:
    def __init__(self):
        self.current={}
        self.pending={key:[] for key in SPANS}
        self.seeds={}
        self.last=None
        self.last_ms=None

    def observe(self,bid,timestamp_ms,digits,now_ms):
        if not isinstance(bid,int) or bid<=0 or not isinstance(timestamp_ms,int):return
        if not 0<=now_ms-timestamp_ms<=5000:return
        if self.last_ms is not None and timestamp_ms<self.last_ms:return
        if self.last==(timestamp_ms,bid):return
        gap=self.last_ms is not None and timestamp_ms-self.last_ms>5000
        self.last=(timestamp_ms,bid);self.last_ms=timestamp_ms
        value=float((Decimal(bid)/100000).quantize(Decimal(1).scaleb(-digits)))
        for key,span in SPANS.items():
            opened=timestamp_ms//(span*1000)*span
            current=self.current.get(key)
            if current is None or current['bar']['time']!=opened:
                if current:
                    self.pending[key]=(self.pending[key]+[current['bar'].copy()])[-3:]
                # A first connection or a gap cannot prove full-period tick coverage.
                partial=current is None or opened-current['bar']['time']!=span
                current=dict(bar=dict(time=opened,open=value,high=value,low=value,close=value,volume=0),
                    partial=partial,price_basis='observed_bid_ticks',volume_basis='observed_bid_updates')
                self.current[key]=current
                seed=self.seeds.get(key)
                if seed and seed['time']==opened:self._apply_seed(current,seed)
            b=current['bar'];b['close']=value;b['high']=max(b['high'],value);b['low']=min(b['low'],value);b['volume']+=1
            if gap:current['partial']=True
            current['updated_at_ms']=timestamp_ms

    @staticmethod
    def _apply_seed(current,seed):
        b=current['bar'];b['open']=seed['open'];b['high']=max(b['high'],seed['high']);b['low']=min(b['low'],seed['low'])
        current['price_basis']='broker_seed_and_bid_ticks'

    def seed(self,interval,bar):
        if interval not in SPANS:return
        self.seeds[interval]=bar.copy()
        current=self.current.get(interval)
        if current and current['bar']['time']==bar['time']:self._apply_seed(current,bar)

    def frame(self,interval):
        if interval not in SPANS:raise ValueError('unsupported interval')
        current=deepcopy(self.current.get(interval))
        return dict(current,pending_bars=deepcopy(self.pending[interval])) if current else None
