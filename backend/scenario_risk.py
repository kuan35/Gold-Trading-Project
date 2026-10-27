"""Decimal, read-only risk of this draft under a historical price path.

These are hypothetical gross USD exposures, never execution prices or forecasts.
"""
from decimal import Decimal,InvalidOperation

D=Decimal

def number(raw,*,positive=True):
    if isinstance(raw,bool) or len(str(raw))>64:raise ValueError('數值格式無效')
    value=D(str(raw))
    if not value.is_finite() or positive and value<=0 or value.adjusted()>10 or value.as_tuple().exponent < -12:
        raise ValueError('數值須為有限正數')
    return value

def text(value):return format(value,'f')
def usd(value):return f'{value:.2f}'

def draft_risk(snapshot,draft,*,market_ready=True):
    base=dict(status='INCOMPLETE',reason='填入方向與手數後可試算本筆風險。',scope='THIS_DRAFT_ONLY',currency='USD',
        side=None,lot=None,order_type=None,entry_price=None,quantity_oz=None,contract_units_per_lot=None,
        stop_price=None,target_price=None,stop_loss_usd=None,reward_risk=None,conditional_on_fill=False,
        exclusions=['佣金','隔夜費','滑價','保證金','既有持倉'],basis='GROSS_NOTIONAL_XAUUSD')
    if not draft:return base
    try:
        side=draft.get('side');kind=draft.get('order_type')
        if side not in ('BUY','SELL') or kind not in ('MARKET','LIMIT') or not draft.get('lot'):return base
        base.update(side=side,order_type=kind,conditional_on_fill=kind=='LIMIT')
        quote=snapshot.get('quote') or {};symbol=snapshot.get('symbol') or {}
        if not market_ready or quote.get('status')!='CURRENT' or quote.get('age_seconds',99)>5:
            return dict(base,status='UNAVAILABLE',reason='報價未就緒，未使用舊價計算草稿風險。')
        rules=[symbol.get(k) for k in ('lot_size_cents','min_volume_cents','max_volume_cents','step_volume_cents')]
        if any(type(v) is not int or v<=0 for v in rules):
            return dict(base,status='UNAVAILABLE',reason='券商合約或手數規格不足，未假設每手盎司數。')
        lot=number(draft['lot']);lot_cents,minimum,maximum,step=rules
        volume=lot*lot_cents
        if lot>100 or volume!=volume.to_integral_value() or not minimum<=volume<=maximum or (volume-minimum)%step:
            raise ValueError('手數不符合券商最小值、上限或級距')
        bid,ask=number(quote['bid']),number(quote['ask'])
        if ask<bid:raise ValueError('雙向報價無效')
        entry=number(draft.get('limit_price')) if kind=='LIMIT' else ask if side=='BUY' else bid
        if kind=='LIMIT' and (side=='BUY' and entry>=ask or side=='SELL' and entry<=bid):
            raise ValueError('限價不在非立即成交方向')
        sign=D(1) if side=='BUY' else D(-1)
        stop=number(draft['sl']) if draft.get('sl') not in ('',None) else None
        target=number(draft['tp']) if draft.get('tp') not in ('',None) else None
        if stop is not None and (stop-entry)*sign>=0:raise ValueError('停損須在擬進場價不利方向')
        if target is not None and (target-entry)*sign<=0:raise ValueError('停利須在擬進場價有利方向')
        contract=D(lot_cents)/100;units=lot*contract
        return dict(base,status='AVAILABLE',reason='本筆新增委託的名目USD試算。',lot=text(lot),entry_price=text(entry),
            contract_units_per_lot=text(contract),quantity_oz=text(units),
            stop_price=text(stop) if stop is not None else None,target_price=text(target) if target is not None else None,
            stop_loss_usd=usd(abs(entry-stop)*units) if stop is not None else None,
            reward_risk=text(abs(target-entry)/abs(stop-entry)) if stop is not None and target is not None else None,
            assumption='假設指定限價已成交後的情境，不判定是否能成交。' if kind=='LIMIT' else '以同快照擬進場價計算，不是實際成交價。')
    except (InvalidOperation,ValueError,TypeError,KeyError,ArithmeticError) as exc:
        return dict(base,status='INVALID',reason=str(exc) if isinstance(exc,ValueError) else '草稿數值無效，請核對欄位。')

def project_scenario(history,risk,analysis_side):
    empty=dict(status='UNAVAILABLE',reason='歷史後續或草稿資料不足。',end_pnl_usd=None,mae_loss_usd=None,
        mfe_profit_usd=None,stop_nominal_loss_usd=risk.get('stop_loss_usd'),touch_state='UNAVAILABLE',
        first_touch_minutes=None,gap_at_first_touch=False,executed_pnl_usd=None,scope='THIS_DRAFT_ONLY',currency='USD')
    if risk.get('status')!='AVAILABLE':return dict(empty,reason=risk.get('reason',empty['reason']))
    if risk.get('side')!=analysis_side:return dict(empty,status='SIDE_MISMATCH',reason='討論方向與草稿方向不同，沒有套用歷史情境；草稿未改動。')
    if history.get('status')!='AVAILABLE' or not history.get('bars'):return dict(empty,reason=history.get('reason',empty['reason']))
    try:
        anchor=number(history['anchor_price']);entry=number(risk['entry_price']);units=number(risk['quantity_oz'])
        sign=D(1) if analysis_side=='BUY' else D(-1)
        mapped=[]
        for b in history['bars']:
            prices={k:number(b[k])/anchor*entry for k in ('open','high','low','close')}
            if not prices['low']<=min(prices['open'],prices['close'])<=max(prices['open'],prices['close'])<=prices['high']:
                raise ValueError('invalid OHLC')
            mapped.append(prices)
        low=min(p['low'] for p in mapped);high=max(p['high'] for p in mapped)
        adverse=max(D(0),(entry-low) if sign>0 else (high-entry))
        favorable=max(D(0),(high-entry) if sign>0 else (entry-low))
        stop=number(risk['stop_price']) if risk.get('stop_price') else None
        target=number(risk['target_price']) if risk.get('target_price') else None
        touch='NO_LEVELS' if stop is None and target is None else 'NEITHER';first=None;gap=False
        for n,b in enumerate(mapped,1):
            hit_stop=stop is not None and (b['low']<=stop if sign>0 else b['high']>=stop)
            hit_target=target is not None and (b['high']>=target if sign>0 else b['low']<=target)
            if hit_stop or hit_target:
                touch='BOTH_SAME_BAR' if hit_stop and hit_target else 'STOP_FIRST' if hit_stop else 'TARGET_FIRST'
                first=n*5
                gap=bool(hit_stop and (b['open']<stop if sign>0 else b['open']>stop))
                break
        return dict(empty,status='AVAILABLE',reason='將歷史百分比路徑平移到本筆擬進場價；未模擬雙邊價差或真實成交。',
            end_pnl_usd=usd((mapped[-1]['close']-entry)*sign*units),mae_loss_usd=usd(adverse*units),
            mfe_profit_usd=usd(favorable*units),touch_state=touch,first_touch_minutes=first,gap_at_first_touch=gap,
            conditional_on_fill=risk.get('conditional_on_fill',False),path_basis='RETURN_PCT_REBASED',
            mae_basis='FULL_PATH_WITHOUT_EXIT',execution_note='觸價不保證成交；同棒碰到停損停利先後未知，跳空可能超出停損價。')
    except (InvalidOperation,ValueError,TypeError,KeyError,ArithmeticError):return empty
