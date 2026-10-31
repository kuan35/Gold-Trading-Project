"""Frozen local presentation of visible operations; never ranking/model input."""
from decimal import Decimal,InvalidOperation
from .case_context import representative
from .trade_result import trade_result

MAX_ROWS=100

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
            ordering_uncertain=row.get('ordering_uncertain') is True,price_result=trade_result(row)))
    truncated=len(rows)>MAX_ROWS or total is not None and total>len(rows)
    coverage=('COUNT_CONFLICT' if total is not None and total<len(rows) else
              'PARTIAL' if truncated else 'VISIBLE_ONLY')
    return dict(status='AVAILABLE' if displayed else 'UNAVAILABLE',representative=dict(representative(source),
        entry=decimal_text(source.get('entry'),True),exit=decimal_text(source.get('exit'),True),price_result=trade_result(source)),rows=displayed,
        provided_rows=len(rows),displayed_rows=len(displayed),reported_total=total,truncated=truncated,coverage=coverage,
        limitations=['僅為來源可見的同群操作序列，不保證完整帳戶、獨立決策或完整群組。',
                    '每列結果是原報表單筆結果；幣別逐列判斷，未載不繼承或補零，不合計成全群淨損益。',
                    '群組與順序是資料整理出的參考，原始券商時鐘仍未獨立核實。'])
