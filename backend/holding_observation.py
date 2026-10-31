"""Observed reference-market movement inside a matured trade; never a ranking input."""
import math
from decimal import Decimal
from .forward_outcomes import _prices
from .trade_result import text
from .execution_store import MAX_HOLDING_SLOTS


def summarize(execution,side,*,cutoff):
    base=dict(status='UNAVAILABLE',reason='未載入完整持倉參考資料，不能從首尾推算過程。',
        basis='REFERENCE_COMPLETE_BARS_WITHIN_HOLDING',scope='OBSERVED_REFERENCE_BARS_ONLY',
        source='HistData BID',clock_status='UNKNOWN',alignment='PROJECT_REFERENCE',side=side,
        anchor_time=None,anchor_price=None,last_bar_end=None,bars_used=0,expected_closed_slots=None,
        missing_closed_slots=None,reference_return_pct=None,observed_mae_pct=None,observed_mfe_pct=None,
        observed_mae_per_oz=None,observed_mfe_per_oz=None)
    try:
        if (not isinstance(execution,dict) or execution.get('status')!='AVAILABLE' or
            execution.get('mode')!='FULL_HOLDING' or (execution.get('coverage') or {}).get('scope')!='WHOLE_REFERENCE_HOLDING' or
            side not in ('BUY','SELL') or type(cutoff) not in (int,float) or not math.isfinite(cutoff)):return base
        opened,closed=execution.get('opened_at'),execution.get('closed_at')
        if type(opened) is not int or type(closed) is not int or closed<opened or closed>cutoff:return base
        start=(opened+299)//300*300;end=closed//300*300
        expected=max(0,(end-start)//300)
        if expected>MAX_HOLDING_SLOTS:return dict(base,reason='超出完整持倉的觀察上限。')
        if expected==0:return dict(base,status='INSUFFICIENT',expected_closed_slots=0,reason='進出場之間沒有完整收盤的五分K，不能推算途中波動。')
        selected=[];previous=-1
        for row in execution.get('bars',[]):
            t=row['time']
            if type(t) is not int or t%300 or t<=previous or t+300>cutoff:return dict(base,reason='參考K棒時間不合法或尚未收盤。')
            previous=t
            if start<=t and t+300<=closed:selected.append((t,_prices(row)))
        if not selected or selected[0][0]!=start:
            return dict(base,status='INSUFFICIENT',expected_closed_slots=expected,reason='固定觀察起點的完整參考棒缺漏，未移動起點或補值。')
        anchor=selected[0][1]['open'];last=selected[-1][1]['close']
        low=min(p['low'] for _,p in selected);high=max(p['high'] for _,p in selected)
        zero=Decimal(0);sign=Decimal(1 if side=='BUY' else -1)
        adverse=max(zero,anchor-low if side=='BUY' else high-anchor)
        favourable=max(zero,high-anchor if side=='BUY' else anchor-low)
        missing=expected-len(selected)
        return dict(base,status='PARTIAL' if missing else 'AVAILABLE',
            reason='僅涵蓋已知完整K棒；時間缺口可能含休市或來源缺漏，並非整段未知行情的真實最大幅度。' if missing else '只涵蓋進出場之間已完整收盤的參考棒，非原單實際損益。',
            anchor_time=start,anchor_price=text(anchor),last_bar_end=selected[-1][0]+300,bars_used=len(selected),
            expected_closed_slots=expected,missing_closed_slots=missing,reference_return_pct=text((last-anchor)/anchor*100*sign),
            observed_mae_pct=text(adverse/anchor*100),observed_mfe_pct=text(favourable/anchor*100),
            observed_mae_per_oz=text(adverse),observed_mfe_per_oz=text(favourable))
    except (KeyError,ValueError,TypeError,ArithmeticError,AttributeError):return dict(base,reason='參考行情欄位或價格無法計算，沒有補值。')
