"""Frozen operations and whitelisted narrative facts; never ranking features."""
from datetime import datetime
from math import isfinite
from decimal import Decimal,InvalidOperation
from .case_context import representative
from .trade_result import trade_result

MAX_ROWS=100


def ledger_time(value):
    if not isinstance(value,str):return None
    try:return datetime.fromisoformat(value.replace('Z','+00:00')).isoformat(sep=' ',timespec='seconds')
    except ValueError:return None


def historical_trade_fact(source,ref,number,cutoff):
    """Keep ledger dates distinct from reference-chart timestamps.

    Exact values stay local: writer_facts exposes only placeholders and states.
    Caller has already selected a mature group; verify row availability too.
    """
    if type(number) is not int or not 1<=number<=5 or ref!='案例'+'甲乙丙丁戊'[number-1] or not isinstance(source,dict):return None
    available=source.get('available_at')
    if type(available) not in (int,float) or type(cutoff) not in (int,float):return None
    if not isfinite(available) or not isfinite(cutoff) or available>cutoff:return None
    result=trade_result(source)
    if result['status']!='AVAILABLE':return None
    try:
        opened=datetime.fromisoformat(source['opened_at'].replace('Z','+00:00'))
        closed=datetime.fromisoformat(source['closed_at'].replace('Z','+00:00'))
        if closed<opened:return None
    except (KeyError,TypeError,ValueError,AttributeError):return None
    p=f'hist{number}_'
    values={p+'opened_at':opened.strftime('%Y-%m-%d %H:%M:%S'),p+'closed_at':closed.strftime('%Y-%m-%d %H:%M:%S'),
        p+'opened_day':opened.strftime('%Y年%m月%d日'),p+'closed_day':closed.strftime('%Y年%m月%d日'),
        p+'entry':result['entry_price'],p+'exit':result['exit_price'],
        p+'price_return':format(Decimal(result['price_return_pct']),'.4f'),
        p+'side_state':'做多' if source['side']=='BUY' else '做空',
        p+'result_state':'價格報酬為正' if Decimal(result['move_per_oz'])>0 else '價格報酬為負' if Decimal(result['move_per_oz'])<0 else '價格報酬為零'}
    def token(name):return '{{'+p+name+'}}'
    text=(ref+'的原交易紀錄：交易員於'+token('opened_day')+'以'+token('entry')+'美元／盎司'+token('side_state')+
        '，於'+token('closed_day')+'以'+token('exit')+'平倉；這筆原單'+token('result_state')+'，價格報酬率'+token('price_return')+
        '%（未扣交易成本）。')
    rep=representative(source)
    if rep['profit'] is not None:
        values.update({p+'report_profit':rep['profit'],p+'currency':rep['currency'] or '幣別未載',
                       p+'report_result_state':{'WIN':'原報表獲利','LOSS':'原報表虧損','FLAT':'原報表損益為零'}.get(rep['result'],'原報表結果未知')})
        text+='原報表單筆損益'+token('report_profit')+' '+token('currency')+'。'
    text+='日期為原對帳單時間，時區未核實，與圖表參考時間分開。此結果是原單結果，不是當前交易預測。'
    return dict(id=f'history.trade{number}',text=text,values=values)

def decimal_text(value,positive=False):
    try:
        number=Decimal(str(value))
        if not number.is_finite() or (positive and number<=0):return None
        return format(number,'f')
    except (InvalidOperation,ValueError,TypeError):return None

def build_case_operations(source):
    source=source if isinstance(source,dict) else {}
    raw=source.get('sequence')
    rows=raw if isinstance(raw,list) else []
    total=source.get('sequence_total')
    total=total if type(total) is int and total>=0 else None
    displayed=[]
    for value in rows[:MAX_ROWS]:
        row=value if isinstance(value,dict) else {}
        rep=representative(row)
        displayed.append(dict(index=row.get('index') if type(row.get('index')) is int and row['index']>0 else None,
            side=rep['side'],lot=rep['lot'],entry=decimal_text(row.get('entry'),True),exit=decimal_text(row.get('exit'),True),
            profit=rep['profit'],currency=rep['currency'],result=rep['result'],
            role=row.get('role')[:80] if isinstance(row.get('role'),str) else None,
            ordering_uncertain=row.get('ordering_uncertain') is True,price_result=trade_result(row),
            opened_at=ledger_time(row.get('opened_at')),closed_at=ledger_time(row.get('closed_at'))))
    truncated=len(rows)>MAX_ROWS or total is not None and total>len(rows)
    coverage=('COUNT_CONFLICT' if total is not None and total<len(rows) else
              'PARTIAL' if truncated else 'VISIBLE_ONLY')
    return dict(status='AVAILABLE' if displayed else 'UNAVAILABLE',representative=dict(representative(source),
        entry=decimal_text(source.get('entry'),True),exit=decimal_text(source.get('exit'),True),price_result=trade_result(source),
        opened_at=ledger_time(source.get('opened_at')),closed_at=ledger_time(source.get('closed_at'))),rows=displayed,
        provided_rows=len(rows),displayed_rows=len(displayed),reported_total=total,truncated=truncated,coverage=coverage,
        limitations=['僅為來源可見的同群操作序列，不保證完整帳戶、獨立決策或完整群組。',
                    '每列結果是原報表單筆結果；幣別逐列判斷，未載不繼承或補零，不合計成全群淨損益。',
                    '群組與順序是資料整理出的參考，原始券商時鐘仍未獨立核實。'])
