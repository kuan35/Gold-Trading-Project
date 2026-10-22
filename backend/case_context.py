"""Whitelisted explanations of existing context-rule results; never ranks cases."""
from decimal import Decimal,InvalidOperation
import re
from .context_retrieval import METHOD,EVENT_LABELS,TAIL_LABELS,REJECTION_LABELS,THRESHOLDS

STATES={
 'PASSED':('有符合條件的案例','歷史案例通過目前情境試驗條件；不是完全相同或未來勝率。'),
 'NO_RULE_MATCH':('有資料，但沒有符合案例','有可比較案例，但全部未通過條件；不補入未通過的近鄰。'),
 'NO_COMPARABLE_CASES':('沒有合格比較池','沒有同方向、已成熟且觀察窗口不重疊的完整雙週期案例。'),
 'UNCERTAIN_EVENT':('事件階段尚不明確','目前收盤接近固定區間邊界，暫不判定符合案例。'),
 'INSUFFICIENT_DATA':('盤面或案例資料不足','所需已收棒或案例索引不足，不能解讀為所有案例都不像。'),
}
AXES=[('d5','path_distance_pct','五分鐘完整路徑','%'),('d1h','hour_path_distance_pct','一小時完整路徑','%'),
      ('dtail','tail_path_distance_pct','最近半小時路徑','%'),('vol_ratio','volatility_ratio','波動倍率','倍')]


def number(value,places=5):
    try:
        d=Decimal(str(value))
        if not d.is_finite() or d<0:return None
        return f'{d:.{places}f}'
    except (InvalidOperation,ValueError,TypeError):return None


def count(value):return value if type(value) is int and value>=0 else None


def representative(case):
    """Local-only representative row; never a group sum or a net-profit claim."""
    try:
        amount=Decimal(str(case.get('profit')))
        if not amount.is_finite():raise InvalidOperation
        profit=format(amount,'f')
        result='WIN' if amount>0 else 'LOSS' if amount<0 else 'FLAT'
    except (InvalidOperation,ValueError,TypeError):
        result,profit='UNKNOWN',None
    currency=case.get('currency')
    currency=currency.strip().upper() if isinstance(currency,str) else None
    if currency is None or re.fullmatch('[A-Z]{3}',currency) is None:currency=None
    try:
        lot=Decimal(str(case.get('lot')))
        if not lot.is_finite() or lot<=0:raise InvalidOperation
        lot=format(lot,'f')
    except (InvalidOperation,ValueError,TypeError):lot=None
    return dict(result=result,profit=profit,currency=currency,currency_stated=currency is not None,
        side=case.get('side') if case.get('side') in ('BUY','SELL') else None,
        action=case.get('action') if case.get('action') in ('FIRST','ADD') else None,lot=lot)


def distribution(retrieval,status):
    """Use the complete ranked/deduplicated aggregate, never displayed rows."""
    keys=('total','wins','losses','flat','unknown')
    values={key:count(retrieval.get(key)) for key in keys}
    if (status=='INSUFFICIENT_DATA' or any(value is None for value in values.values()) or
            sum(values[key] for key in keys[1:])!=values['total'] or
            (status!='PASSED' and values['total']!=0)):
        values={key:None for key in keys}
    return dict(**values,basis='符合群代表單筆的歷史結果分布')


def valid_pass(retrieval,comparison):
    try:
        cases=retrieval['cases'];limits=comparison['thresholds']
        total=count(retrieval['total']);eligible=count(comparison['eligible_rows'])
        if not isinstance(cases,list) or not cases or total is None or eligible is None or not len(cases)<=total<=eligible:return False
        for key,expected in THRESHOLDS.items():
            if Decimal(str(limits[key]))!=Decimal(str(expected)):return False
        for case in cases:
            if not isinstance(case,dict) or not isinstance(case.get('id'),str) or not case['id']:return False
            check=case.get('context_check')
            if not isinstance(check,dict) or check.get('passed') is not True:return False
            for key,field,_,_ in AXES:
                actual=Decimal(str(case[field]));limit=Decimal(str(limits[key]))
                if not actual.is_finite() or actual<(1 if key=='vol_ratio' else 0) or actual>limit:return False
        return True
    except (KeyError,TypeError,ValueError,ArithmeticError):return False


def build_case_context(retrieval,query=None,*,snapshot_id=None):
    comparison=retrieval.get('comparison') or {};method=comparison.get('method')
    status=retrieval.get('rule_status')
    if method!=METHOD or status not in STATES:status='INSUFFICIENT_DATA'
    if status=='PASSED' and not valid_pass(retrieval,comparison):status='INSUFFICIENT_DATA'
    label,reason=STATES[status];query=query or {}
    result=dict(status=status,label=label,reason=reason,method=method,side=retrieval.get('query_side',query.get('side','未指定')),
        snapshot_id=snapshot_id,query_as_of_utc=retrieval.get('query_as_of_utc',query.get('as_of')),
        query_state=dict(event=comparison.get('query_event_label','未知'),tail_direction=comparison.get('query_tail_direction','未知')),
        counts=dict(eligible=count(comparison.get('eligible_rows')),passed=count(retrieval.get('total')) if status=='PASSED' else None if status=='INSUFFICIENT_DATA' else 0,displayed=0),
        cases=[],rejections=[],facts=[],distribution=distribution(retrieval,status))
    def fact(ident,text,values):result['facts'].append(dict(id=ident,text=text,values=values))
    fact('history.status','歷史案例判定：{{history_status_state}}。{{history_reason_state}}；操作方向{{history_side_state}}，通過{{history_count}}群。',
        dict(history_status_state=label,history_reason_state=reason,history_side_state=result['side'] if result['side'] in ('BUY','SELL') else '未指定',history_count=str(result['counts']['passed']) if result['counts']['passed'] is not None else '資料不足'))
    thresholds=comparison.get('thresholds') or {}
    if status=='PASSED':
        for n,case in enumerate((retrieval.get('cases') or [])[:5],1):
            ref='案例'+'甲乙丙丁戊'[n-1];metrics=[];values={};pieces=[];differences=[]
            for key,field,axis,unit in AXES:
                actual,tolerance=number(case.get(field)),number(thresholds.get(key))
                passed=None if actual is None or tolerance is None else Decimal(str(case[field]))<=Decimal(str(thresholds[key]))
                metrics.append(dict(key=key,label=axis,actual=actual,tolerance=tolerance,unit=unit,passed=passed))
                values[f'hist{n}_{key}']=actual if actual is not None else '資料不足'
                values[f'hist{n}_{key}_limit']=tolerance if tolerance is not None else '資料不足'
                pieces.append(axis+'差距{{hist'+str(n)+'_'+key+'}}'+unit+'，試驗容忍{{hist'+str(n)+'_'+key+'_limit}}'+unit+'。')
                differences.append(f'{axis}：{actual}{unit}／容忍{tolerance}{unit}' if actual is not None and tolerance is not None else axis+'資料不足')
            event=case.get('event_label') if case.get('event_label') in EVENT_LABELS.values() else '未知'
            tail=case.get('tail_direction') if case.get('tail_direction') in TAIL_LABELS.values() else '未知'
            qevent=result['query_state']['event'];qtail=result['query_state']['tail_direction']
            similarities=['買賣方向相同','案例與查詢事件階段相同' if event==qevent and event!='未知' else '事件資料需核對',
                '最近半小時方向不相反；不要求完全相同']
            result['cases'].append(dict(ref=ref,case_id=case.get('id'),metrics=metrics,event=event,tail_direction=tail,
                similarities=similarities,differences=differences,representative=representative(case)))
            if n<=2:
                values.update({f'hist{n}_event_state':event,f'hist{n}_tail_state':tail,f'hist{n}_query_tail_state':qtail})
                fact('history.case'+str(n),ref+'符合目前情境條件，事件為{{hist'+str(n)+'_event_state}}；案例末段{{hist'+str(n)+'_tail_state}}、目前末段{{hist'+str(n)+'_query_tail_state}}。'+''.join(pieces)+'仍有差距，不是完全重疊；容忍尚未人工校準。',values)
        result['counts']['displayed']=len(result['cases'])
    for key,value in sorted((comparison.get('rejections') or {}).items()):
        if key in REJECTION_LABELS and count(value) is not None and value>0:
            result['rejections'].append(dict(key=key,label=REJECTION_LABELS[key],count=value))
    if status=='NO_RULE_MATCH' and result['rejections']:
        values={};parts=[]
        for n,row in enumerate(result['rejections']):
            values['rejected_'+str(n)]=str(row['count'])
            parts.append(row['label']+'：{{rejected_'+str(n)+'}}列')
        fact('history.rejections','未通過原因（同一列可有多個原因，不能直接相加成案例數）：'+'；'.join(parts)+'。',values)
    fact('history.limits','以上僅依進場前已收棒與既定試驗條件比較；不以手數或盈虧排名，不作未來獲利判斷。原始案例時鐘尚未獨立核實。',{})
    return result
