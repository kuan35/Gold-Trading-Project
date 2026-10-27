"""Attach already-selected cases' post-reference observations to one snapshot.

Nothing here participates in retrieval or supplies order execution authority.
"""
from decimal import Decimal
from .scenario_risk import draft_risk,project_scenario
from .forward_outcomes import HORIZONS

TOUCH_LABELS={'STOP_FIRST':'先觸及停損範圍','TARGET_FIRST':'先觸及停利範圍',
    'BOTH_SAME_BAR':'同根五分棒碰到停損與停利，先後未知','NEITHER':'觀察期內未觸及已設定價位',
    'NO_LEVELS':'未設定停損停利','UNAVAILABLE':'無法判定觸價'}

def missing(minutes,reason):
    return dict(status='UNAVAILABLE',reason=reason,minutes=minutes,end_time=None,bars=[],anchor_price=None,
        change_pct=None,mae_pct=None,mfe_pct=None)

def build_scenarios(snapshot,context,query,side,*,draft=None,input_revision=None,forward_store=None):
    risk=draft_risk(snapshot,draft,market_ready=context.get('status')=='CURRENT')
    comparison=context.get('case_comparison') or {}
    summary=dict(status='NO_MATCH' if not comparison.get('cases') else 'AVAILABLE',draft_risk=risk,
        input_revision=input_revision,matched_cases=comparison.get('counts',{}).get('passed'),
        displayed_cases=len(comparison.get('cases',[])),cases=[],
        basis='DISPLAYED_CASES_ONLY',note='只呈現本次展示案例，不代表完整匹配池的後續統計。')
    bundles={};facts=[]
    for item in comparison.get('cases',[]):
        ref=item['ref'];raw={}
        if forward_store is not None and type(query.get('as_of')) in (int,float):
            raw=forward_store.get(item['case_id'],query['as_of'])
        horizons={};scenarios={};bundles[ref]={}
        for minutes in HORIZONS:
            key=str(minutes);h=(raw.get('horizons') or {}).get(key)
            history=missing(minutes,raw.get('reason') or '尚未建立可用的歷史後續資料。') if not isinstance(h,dict) else {
                k:h.get(k) for k in ('status','reason','minutes','end_time','change_pct','mae_pct','mfe_pct')}
            if h is not None:
                history.update(bars=[{k:b[k] for k in ('time','open','high','low','close')} for b in h.get('bars',[])],
                    anchor_price=raw.get('anchor_price'))
            history.update(source=raw.get('source','HistData BID'),basis='NEXT_COMPLETE_5M_OPEN',
                anchor_time=raw.get('anchor_time'),case_as_of=raw.get('case_as_of'),side=raw.get('side',side),
                clock_status='UNKNOWN',alignment='PROJECT_REFERENCE')
            projected=project_scenario(history,risk,side)
            projected['touch_label']=TOUCH_LABELS.get(projected.get('touch_state'),'無法判定觸價')
            horizons[key]={k:v for k,v in history.items() if k not in ('bars','anchor_price')}
            scenarios[key]=projected
            bundles[ref][key]=dict(history=history,scenario=projected)
        summary['cases'].append(dict(ref=ref,horizons=horizons,scenarios=scenarios))
    # First displayed case only. The LLM receives a token ledger, not historical prices.
    if summary['cases']:
        first=summary['cases'][0];h=first['horizons']['60'];s=first['scenarios']['60']
        if h['status']=='AVAILABLE':
            values=dict(future_minutes=str(h['minutes']),future_change=f"{Decimal(h['change_pct']):.4f}",future_mae=f"{Decimal(h['mae_pct']):.4f}",future_mfe=f"{Decimal(h['mfe_pct']):.4f}")
            phrase='案例甲後續{{future_minutes}}分鐘：依操作方向調整後期末變動{{future_change}}%，途中最大逆向{{future_mae}}%、最大順向{{future_mfe}}%。這是固定期間的歷史走法，不是目前預測。'
            if s['status']=='AVAILABLE':
                values.update(future_loss=s['mae_loss_usd'],future_end=s['end_pnl_usd'],future_touch_state=s['touch_label'])
                phrase+='套入本筆草稿，未套退出的最大逆向情境損失{{future_loss}} USD、期末名目損益{{future_end}} USD；{{future_touch_state}}。觸價不等於成交，不含成本。'
            facts.append(dict(id='history.outcome',text=phrase,values=values))
        else:facts.append(dict(id='history.outcome',text='案例甲的固定後續觀察資料未能使用：{{future_unavailable_state}}。沒有補零或改挑其他結果。',values=dict(future_unavailable_state=h.get('reason') or '資料不足')))
    if risk['status']=='AVAILABLE':
        phrase='這筆新增草稿的擬進場價{{draft_entry}}、手數{{draft_lot}}，合約單位{{draft_units}}盎司。'
        values=dict(draft_entry=risk['entry_price'],draft_lot=risk['lot'],draft_units=risk['quantity_oz'])
        if risk['stop_loss_usd'] is not None:
            phrase+='停損距離對應的本筆名目損失{{draft_stop_loss}} USD。'
            values['draft_stop_loss']=risk['stop_loss_usd']
        else:phrase+='未設定停損，沒有已定義的停損損失上限。'
        phrase+='{{draft_assumption_state}}只算新增本筆，不含既有持倉、佣金、滑價或槓桿佔用資金。'
        values['draft_assumption_state']=risk['assumption']
        if risk.get('side')!=side:
            phrase+='討論與草稿方向不同，未套用歷史情境；原草稿沒有改動。'
        facts.append(dict(id='draft.risk',text=phrase,values=values))
    elif draft:facts.append(dict(id='draft.risk',text='草稿風險尚未能計算：{{draft_unavailable_state}}。未將缺值當成零風險。',values=dict(draft_unavailable_state=risk['reason'])))
    return summary,bundles,facts
