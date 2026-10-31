"""Reference execution markers. Call only after ledger validation, never rank."""
from .trade_result import trade_result


def execution_overlay(source,profile,bars,*,cutoff):
    opened,closed=profile.get('reference_open_utc'),profile.get('reference_close_utc')
    value=dict(status='UNAVAILABLE',markers=[],result=trade_result(source),clock_status='UNKNOWN',
               alignment='PROJECT_REFERENCE',reason='沒有可追溯的已完成參考進出時點。')
    if (type(opened) is not int or type(closed) is not int or closed<opened or
        profile.get('as_of')!=opened or profile.get('reference_clock_basis') not in ('source_model_scenario','ledger_price_hypothesis') or
        type(cutoff) not in (int,float) or closed>cutoff):return value
    available={b['time'] for b in bars if type(b.get('time')) is int and b['time']+300<=cutoff}
    markers=[]
    for action,t,side,label,color in [('ENTRY',opened,source.get('side'),'進場參考','#1ca88b'),('CLOSE',closed,source.get('side'),'平倉參考','#d16b72')]:
        floor=t//300*300
        if floor not in available:continue
        markers.append(dict(time=floor,executed_at=t,position='belowBar' if action=='ENTRY' else 'aboveBar',
            color=color,shape='arrowUp' if action=='ENTRY' else 'arrowDown',text=label,
            action=action,price=None,id='reference-'+action.lower(),side=side))
    return dict(value,status='AVAILABLE',markers=markers,opened_at=opened,closed_at=closed,
                reason='原單時間模型的參考棒；非整棒進場所在棒在當時尚未收盤，僅供事後觀看。')
