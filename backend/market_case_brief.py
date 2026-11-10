"""Deterministic pre-entry descriptions for selected cases, never retrieval input.

Only closed OHLC bars and the existing rule labels enter this module. Original
orders/results belong to separate facts and cannot influence a shape label.
"""
from decimal import Decimal, InvalidOperation
from math import isfinite

from .context_retrieval import EVENT_LABELS, TAIL_LABELS

FRAMES=(('5m',300,60,'五分鐘'),('1h',3600,20,'一小時'))


def direction(value):
    return '上行' if value>0 else '下行' if value<0 else '持平'


def frame_description(rows, cutoff, span, count):
    empty=dict(status='UNAVAILABLE',reason='進場前完整已收棒不足或無效。',count=None,
        change_pct=None,direction='未知',segments=[])
    if type(cutoff) not in (int,float) or not isfinite(cutoff) or not isinstance(rows,list):
        return empty
    chosen=[row for row in rows if isinstance(row,dict) and type(row.get('time')) is int and row['time']+span<=cutoff][-count:]
    if len(chosen)!=count:return empty
    previous=-1
    try:
        prices=[]
        for row in chosen:
            if row['time']<=previous or row['time']%span:raise ValueError('invalid time')
            p={key:Decimal(str(row[key])) for key in ('open','high','low','close')}
            if any(not value.is_finite() or value<=0 for value in p.values()):raise ValueError('invalid price')
            if not p['low']<=min(p['open'],p['close'])<=max(p['open'],p['close'])<=p['high']:raise ValueError('invalid OHLC')
            prices.append(p);previous=row['time']
        def change(part):
            value=(part[-1]['close']/part[0]['open']-1)*100
            return dict(count=len(part),change_pct=format(value,'.4f'),direction=direction(value))
        # Fixed non-overlapping thirds: 20/20/20 and 7/7/6 observed bars.
        first=(count+2)//3;second=(count-first+1)//2
        segments=[change(prices[:first]),change(prices[first:first+second]),change(prices[first+second:])]
        return dict(status='AVAILABLE',reason=None,**change(prices),segments=segments)
    except (KeyError,TypeError,ValueError,InvalidOperation,ArithmeticError):return empty


def describe_pre_entry(frames,cutoff,*,event=None,tail=None):
    frames=frames if isinstance(frames,dict) else {}
    return dict(schema='pre_entry_brief_v1',basis='CLOSED_BARS_ONLY',
        event=event if event in EVENT_LABELS.values() else '未知',
        tail_direction=tail if tail in TAIL_LABELS.values() else '未知',
        frames={key:frame_description(frames.get(key),cutoff,span,count) for key,span,count,_ in FRAMES})


def shape_fact(description,number=None):
    prefix='qs_' if number is None else f'hs{number}_'
    label='查詢盤面' if number is None else '案例'+'甲乙丙丁戊'[number-1]+'進場前參考盤面'
    values={prefix+'event_state':description['event'],prefix+'tail_state':description['tail_direction']}
    def token(key):return '{{'+prefix+key+'}}'
    text=label+'：固定區間事件'+token('event_state')+'，末半小時方向'+token('tail_state')+'。'
    for key,_,_,period in FRAMES:
        frame=description['frames'][key];p={'5m':'f5_','1h':'h1_'}[key]
        if frame['status']!='AVAILABLE':
            text+=period+'形態資料不足，未推測三段走法。'
            continue
        values.update({prefix+p+'count':str(frame['count']),prefix+p+'change':frame['change_pct'],
            prefix+p+'d_state':frame['direction']})
        text+=period+token(p+'count')+'根首開至末收'+token(p+'d_state')+token(p+'change')+'%。'
        for i,segment in enumerate(frame['segments'],1):
            k=p+f's{i}_'
            values.update({prefix+k+'count':str(segment['count']),prefix+k+'change':segment['change_pct'],prefix+k+'d_state':segment['direction']})
            text+=('前段','中段','後段')[i-1]+token(k+'count')+'根'+token(k+'d_state')+token(k+'change')+'%；'
    text+='三段為各段首開至末收的描述，不等於完整路徑或已確認進場訊號；未使用出場與盈虧。'
    if number is not None:text+='原始券商時鐘未知，僅為PROJECT_REFERENCE參考形態。'
    return dict(id='history.query_shape' if number is None else f'history.shape{number}',text=text,values=values)


def comparison_fact(query,case,number):
    """Compare descriptive signs without adding a tolerance or a pass decision."""
    pieces=[]
    for key,_,_,period in FRAMES:
        q,c=query['frames'][key],case['frames'][key]
        if q['status']!='AVAILABLE' or c['status']!='AVAILABLE':
            pieces.append(period+'形態缺資料，不能比較三段方向')
            continue
        same=[a['direction']==b['direction'] for a,b in zip(q['segments'],c['segments'])]
        names=['前段','中段','後段']
        pieces.append(period+'：'+'、'.join(names[i]+'方向'+('相同' if value else '不同') for i,value in enumerate(same)))
    state='；'.join(pieces)+'。方向一致仍可能有路徑差異；定量差距另見同案例既有檢索事實，不重新判定符合。'
    return dict(id=f'history.shape_comparison{number}',text='案例'+'甲乙丙丁戊'[number-1]+'與查詢盤面：{{hist'+str(number)+'_shape_comparison_state}}。',
        values={f'hist{number}_shape_comparison_state':state})
