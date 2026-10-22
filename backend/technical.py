"""Descriptive closed-candle indicators, not a trade signal or trader-drawn line."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

D = Decimal


def formatted(value: D | None, digits: int = 2) -> str | None:
    return f'{value:.{digits}f}' if value is not None else None


def ema(values: list[D], period: int) -> list[D]:
    if len(values) < period:
        return []
    value = sum(values[:period],D(0))/period
    result = [value]
    alpha = D(2)/(period+1)
    for current in values[period:]:
        value += alpha*(current-value)
        result.append(value)
    return result


def wilder(values: list[D], period: int) -> D | None:
    if len(values)<period:
        return None
    value=sum(values[:period],D(0))/period
    for current in values[period:]:
        value=(value*(period-1)+current)/period
    return value


def interpret(values: dict[str, D | None]) -> dict:
    """Describe the current frame; engineering rules, not a forecast or vote."""
    close,ma20,ma60=(values.get(k) for k in ('close','ma20','ma60'))
    relation=lambda a,b: '高於' if a>b else '低於' if a<b else '等於'
    bias='insufficient'
    structure='完整已收K棒不足60根，無法同時比較MA20與MA60。'
    if close is not None and ma20 is not None and ma60 is not None:
        if ma20>ma60 and close>ma60:
            bias='bullish' if close>=ma20 else 'bullish_pullback'
        elif ma20<ma60 and close<ma60:
            bias='bearish' if close<=ma20 else 'bearish_rebound'
        else:
            bias='mixed'
        structure=(f'末根收盤 {close:.2f} {relation(close,ma20)} MA20 {ma20:.2f}、'
                   f'{relation(close,ma60)} MA60 {ma60:.2f}；MA20 {relation(ma20,ma60)} MA60。')
    labels={'bullish':'短線偏多','bearish':'短線偏空','bullish_pullback':'多方結構中的回檔',
            'bearish_rebound':'空方結構中的反彈','mixed':'多空結構尚不一致','insufficient':'方向資料不足'}
    indicators={}
    rsi=values.get('rsi14')
    if rsi is None:
        indicators['rsi']='RSI衡量近期漲跌動能；根數不足，暫不判讀。'
    else:
        state='買方動能較強' if rsi>55 else '賣方動能較強' if rsi<45 else '動能接近平衡'
        indicators['rsi']=f'RSI {rsi:.2f}：{state}。看近期上漲與下跌的相對力道。'
        if rsi>=70:
            indicators['rsi']+='已在常見強勢／超買區，不代表下一根必跌。'
        elif rsi<=30:
            indicators['rsi']+='已在常見弱勢／超賣區，不代表下一根必漲。'
    line,hist=(values.get(k) for k in ('macd_line','macd_histogram'))
    if line is None or hist is None:
        indicators['macd']='MACD比較快慢均線與動能差；根數不足，暫不判讀。'
    else:
        base=f'12期快均線{relation(line,D(0))}26期慢均線（MACD {line:.4f}）'
        signal=f'MACD{relation(hist,D(0))}訊號線（柱 {hist:.4f}）'
        hint=('偏空背景中出現反彈動能' if line<0 and hist>0 else
              '偏多背景中動能弱於訊號平均' if line>0 and hist<0 else
              '快慢均線與訊號差同偏多' if line>0 and hist>0 else
              '快慢均線與訊號差同偏空' if line<0 and hist<0 else '訊號差或快慢均線處於平衡')
        indicators['macd']=f'{base}；{signal}，{hint}。'
    atr=values.get('atr14')
    indicators['atr']=('ATR是近期每根K棒真實波幅的平滑平均；根數不足。' if atr is None else
                       f'ATR {atr:.2f} 美元/oz：近期每根K棒真實波幅的平滑平均，只看波動，不分多空。')
    middle,lower,upper=(values.get(k) for k in ('boll_middle','boll_lower','boll_upper'))
    if close is None or middle is None or lower is None or upper is None:
        indicators['bollinger']='布林通道描述價格相對20期均線與波動範圍；根數不足。'
    else:
        location='上軌之外' if close>upper else '下軌之外' if close<lower else '通道上半部' if close>middle else '通道下半部' if close<middle else '中軌附近'
        indicators['bollinger']=f'收盤 {close:.2f} 在{location}，{relation(close,middle)}中軌 {middle:.2f}。通道描述相對位置，不代表碰軌必反轉。'
    ratio=values.get('source_volume_ratio')
    indicators['volume']=('來源量資料不足，暫不比較活躍程度。' if ratio is None else
                          f'來源量為平常的 {ratio:.2f} 倍，{relation(ratio,D(1))}前20根平均；只代表此來源活躍程度，不能單獨判斷方向。')
    return dict(bias=bias,label=labels[bias],reasons=[structure,indicators['rsi'],indicators['macd']],
                indicators=indicators,
                method='結構先看收盤與MA20／MA60位置：均線同向且價格同側才稱偏多／空；仍在MA60同側但越過MA20稱回檔／反彈，其他為不一致。RSI以45–55作中性緩衝，MACD分別看零軸與訊號差；不以ATR或量比投票。這是描述性工程規則，非已驗證預測模型。')


def analyze(bars: list[dict], seconds: int, clock: int) -> dict:
    groups: dict[int,list[dict]]={}
    for b in bars:
        start=b['time']//seconds*seconds
        if b['time']+300<=clock and start+seconds<=clock:
            groups.setdefault(start,[]).append(b)
    candles=[]
    for start,group in sorted(groups.items()):
        if len(group)!=seconds//300 or any(b['time']!=start+i*300 for i,b in enumerate(group)):
            continue
        candles.append(dict(time=start,close=D(group[-1]['close']),
                            high=max(D(b['high']) for b in group),low=min(D(b['low']) for b in group),
                            volume=sum((D(str(b.get('volume',0))) for b in group),D(0))))
    return _analyze_candles(candles, seconds)


def analyze_native(bars: list[dict], seconds: int, clock: int) -> dict:
    """Analyze native completed bars without reconstructing smaller intervals.

    Times must be unique, ascending UTC bucket starts. Invalid ordering rejects
    the complete frame rather than silently changing its sequence. Invalid OHLC
    rows are excluded and counted; unknown volume does not discard valid prices.
    Gaps are reported, never filled or classified as a known market closure here.
    Indicators count observed valid bars, as in the existing replay calculation.
    """
    if seconds not in (300, 900, 3600):
        raise ValueError('unsupported native candle interval')
    quality = dict(status='ok', input_count=len(bars), rejected_price_count=0,
                   excluded_unclosed_count=0, unknown_volume_count=0,
                   gap_count=0, missing_interval_count=0, reasons=[])
    candles = []
    previous = None
    for bar in bars:
        start = bar.get('time') if isinstance(bar, dict) else None
        if (type(start) is not int or start < 0 or start % seconds or
                (previous is not None and start <= previous)):
            quality['status'] = 'invalid'
            quality['reasons'].append('native_times_must_be_sorted_unique_aligned_integers')
            result = _analyze_candles([], seconds, include_prices=True)
            result['data_quality'] = quality
            return result
        previous = start
        if start + seconds > clock:
            quality['excluded_unclosed_count'] += 1
            continue
        try:
            prices = {key: D(str(bar[key])) for key in ('open', 'high', 'low', 'close')}
            if (any(not value.is_finite() or value <= 0 for value in prices.values()) or
                    not (prices['low'] <= min(prices['open'], prices['close']) <=
                         max(prices['open'], prices['close']) <= prices['high'])):
                raise ValueError('invalid OHLC')
        except (KeyError, InvalidOperation, ValueError, TypeError):
            quality['rejected_price_count'] += 1
            continue
        try:
            volume = D(str(bar.get('volume')))
            if not volume.is_finite() or volume < 0:
                raise ValueError('invalid volume')
        except (InvalidOperation, ValueError, TypeError):
            volume = None
            quality['unknown_volume_count'] += 1
        candles.append(dict(time=start, **prices, volume=volume))
    for left, right in zip(candles, candles[1:]):
        missing = (right['time'] - left['time']) // seconds - 1
        if missing:
            quality['gap_count'] += 1
            quality['missing_interval_count'] += missing
    for field, reason in (
        ('rejected_price_count', 'invalid_or_missing_ohlc_excluded'),
        ('excluded_unclosed_count', 'forming_or_future_bars_excluded'),
        ('unknown_volume_count', 'source_volume_unknown'),
        ('gap_count', 'native_time_gaps_not_filled_or_classified'),
    ):
        if quality[field]:
            quality['reasons'].append(reason)
    if quality['rejected_price_count'] or quality['unknown_volume_count'] or quality['gap_count']:
        quality['status'] = 'partial'
    elif len(candles) < 60:
        quality['status'] = 'insufficient'
    if len(candles) < 60:
        quality['reasons'].append('fewer_than_60_valid_closed_bars_for_ma60')
    result = _analyze_candles(candles, seconds, include_prices=True)
    result['data_quality'] = quality
    return result


def _analyze_candles(candles: list[dict], seconds: int, *, include_prices: bool = False) -> dict:
    """Shared Decimal formulas for already selected completed candles."""
    closes=[b['close'] for b in candles]
    changes=[b-a for a,b in zip(closes,closes[1:])]
    gains=wilder([max(v,D(0)) for v in changes],14)
    losses=wilder([max(-v,D(0)) for v in changes],14)
    rsi=None if gains is None else D(50) if gains==0 and losses==0 else D(100) if losses==0 else 100-100/(1+gains/losses)
    fast,slow=ema(closes,12),ema(closes,26)
    macd=[a-b for a,b in zip(fast[-len(slow):],slow)] if slow else []
    signal=ema(macd,9)
    ranges=[max(b['high']-b['low'],abs(b['high']-a['close']),abs(b['low']-a['close'])) for a,b in zip(candles,candles[1:])]
    atr=wilder(ranges,14)
    middle=sum(closes[-20:],D(0))/20 if len(closes)>=20 else None
    sd=(sum(((v-middle)**2 for v in closes[-20:]),D(0))/20).sqrt() if middle is not None else None
    volumes=[b['volume'] for b in candles]
    baseline=candles[-21:-1] if len(candles)>=21 else []
    last_volume=volumes[-1] if volumes else None
    prior_volume=(sum((b['volume'] for b in baseline),D(0))/20
                  if len(baseline)==20 and all(b['volume'] is not None for b in baseline) else None)
    contiguous=len(candles)>=21 and all(b['time']-a['time']==seconds for a,b in zip(candles[-21:],candles[-20:]))
    volume_status=('INSUFFICIENT_HISTORY' if len(candles)<21 else 'GAPPED_BASELINE' if not contiguous else
                   'UNKNOWN_VOLUME' if last_volume is None or prior_volume is None else
                   'ZERO_BASELINE' if prior_volume==0 else 'AVAILABLE')
    ratio=last_volume/prior_volume if volume_status=='AVAILABLE' else None
    volume_activity=dict(status=volume_status,last=format(last_volume,'f') if last_volume is not None else None,
                         mean20=format(prior_volume,'f') if prior_volume is not None else None,
                         ratio=formatted(ratio,4),baseline_count=len(baseline),
                         relation=('ABOVE' if last_volume>prior_volume else 'BELOW' if last_volume<prior_volume else 'EQUAL') if ratio is not None else None)
    levels=[]
    recent=candles[-120:]
    for i in range(2,len(recent)-2):
        b=recent[i]
        neighbours=recent[i-2:i]+recent[i+1:i+3]
        for side,field,compare in [('support','low',min),('resistance','high',max)]:
            bound=compare(n[field] for n in neighbours)
            if (side=='support' and b[field]<bound) or (side=='resistance' and b[field]>bound):
                levels.append(dict(kind=side,value=b[field],confirmed_at=recent[i+2]['time']+seconds))
    # Group nearby CONFIRMED pivots; the average is a candidate reference, not a
    # validated bounce probability. Keep support-low and resistance-high separate.
    tolerance=max((atr or D(0))/4,D('.20'))
    clustered=[]
    for item in sorted(levels,key=lambda x:(x['kind'],x['value'],x['confirmed_at'])):
        if clustered and item['kind']==clustered[-1]['kind'] and item['value']-clustered[-1]['value']<=tolerance:
            group=clustered[-1]; n=group['pivot_count']
            group['value']=(group['value']*n+item['value'])/(n+1)
            group['pivot_count']+=1
            group['confirmed_at']=max(group['confirmed_at'],item['confirmed_at'])
        else:
            clustered.append(dict(item,pivot_count=1))
    last=closes[-1] if closes else None
    ma60=sum(closes[-60:],D(0))/60 if len(closes)>=60 else None
    reading=interpret(dict(close=last,ma20=middle,ma60=ma60,
                           rsi14=rsi,macd_line=macd[-1] if macd else None,
                           macd_histogram=macd[-1]-signal[-1] if signal else None,atr14=atr,
                           boll_middle=middle,boll_lower=middle-2*sd if middle is not None else None,
                           boll_upper=middle+2*sd if middle is not None else None,source_volume_ratio=ratio))
    def nearest(kind: str) -> list[dict]:
        valid=[v for v in clustered if v['kind']==kind and last is not None and
               (v['value']<last if kind=='support' else v['value']>last)]
        return [dict(price=formatted(v['value']),pivot_count=v['pivot_count'],confirmed_at=v['confirmed_at'])
                for v in sorted(valid,key=lambda v:abs(v['value']-last))[:2]]
    result = dict(interval={300:'5m',900:'15m',3600:'1h'}[seconds],count=len(candles),reading=reading,
                last_closed_at=candles[-1]['time']+seconds if candles else None,
                rsi14=formatted(rsi),macd_line=formatted(macd[-1] if macd else None,4),
                macd_signal=formatted(signal[-1] if signal else None,4),
                macd_histogram=formatted(macd[-1]-signal[-1] if signal else None,4),
                atr14=formatted(atr),boll_middle=formatted(middle),
                boll_upper=formatted(middle+2*sd if middle is not None else None),
                boll_lower=formatted(middle-2*sd if middle is not None else None),
                source_volume_ratio=formatted(ratio),volume_activity=volume_activity,
                levels=dict(status='candidate',lookback_count=len(recent),support=nearest('support'),resistance=nearest('resistance'),
                            tolerance=formatted(tolerance),method='已收K棒左右各2根確認轉折；同類價位按ATR14四分之一（至少0.20）合併。僅候選，非交易員畫線或有效支撐壓力認證。'),
                definitions='RSI/ATR用Wilder14；MACD為EMA12/26/9，EMA以首段SMA起算；布林20根、母體標準差2倍；量比為末根來源量÷前20根平均，非全球成交量。')
    if include_prices:
        result.update(close=formatted(last), ma20=formatted(middle), ma60=formatted(ma60))
    return result
