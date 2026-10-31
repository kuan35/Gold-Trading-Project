"""Per-trade fee-before price result; never infer invested capital."""
from decimal import Decimal, InvalidOperation


def text(value):
    if value==0:return '0'
    return format(value,'f').rstrip('0').rstrip('.') if '.' in format(value,'f') else format(value,'f')


def trade_result(source):
    result=dict(status='UNAVAILABLE',entry_price=None,exit_price=None,move_per_oz=None,price_return_pct=None,margin_roi_pct=None,
                basis='DIRECTION_ADJUSTED_PRICE_BEFORE_FEES',reason='缺少合法方向或正進出價；保證金ROI缺少單筆資金基準。')
    try:
        entry,exit_=Decimal(str(source.get('entry'))),Decimal(str(source.get('exit')))
        if source.get('side') not in ('BUY','SELL') or any(not n.is_finite() or n<=0 for n in (entry,exit_)):return result
        delta=(exit_-entry)*(1 if source['side']=='BUY' else -1)
        return dict(result,status='AVAILABLE',entry_price=text(entry),exit_price=text(exit_),move_per_oz=text(delta),price_return_pct=text(delta/entry*100),
                    reason='原單進出價的費前價格結果；未含佣金與隔夜費。保證金ROI缺少單筆實際資金基準。')
    except (InvalidOperation,TypeError,ValueError,ArithmeticError):return result
