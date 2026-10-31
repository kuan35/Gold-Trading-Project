"""Capture a single read-only market/retrieval bundle for chat and draft review."""
from datetime import datetime,timezone
from decimal import Decimal
from math import isfinite
from .analysis_snapshots import snapshot_fingerprint
from .live_assistant import build_live_context
from .case_context import build_case_context
from .analysis_visuals import build_analysis_visuals
from .case_operations import build_case_operations
from .case_scenarios import build_scenarios
from .holding_observation import summarize as summarize_holding


def chart_bars(rows,span,cutoff,count):
    if not isinstance(cutoff,(int,float)):return []
    chosen=[b for b in rows if isinstance(b,dict) and type(b.get('time')) is int and b['time']+span<=cutoff][-count:]
    result=[];previous=-1
    try:
        for b in chosen:
            if b['time']<=previous or b['time']%span:raise ValueError('invalid time')
            prices={key:Decimal(str(b[key])) for key in ('open','high','low','close')}
            if any(not d.is_finite() or d<=0 for d in prices.values()) or not prices['low']<=min(prices['open'],prices['close'])<=max(prices['open'],prices['close'])<=prices['high']:raise ValueError('invalid price')
            mapped={key:float(v) for key,v in prices.items()}
            if not all(isfinite(v) for v in mapped.values()):raise ValueError('unplottable price')
            result.append(dict(time=b['time'],**mapped));previous=b['time']
    except (KeyError,TypeError,ValueError,ArithmeticError):return []
    return result


def prepare_analysis(snapshot,side,retrieval=None,query=None,*,profiles=None,now=None,operation_sources=None,draft=None,input_revision=None,forward_store=None,execution_store=None):
    context=build_live_context(snapshot,now=now,retrieval=retrieval)
    if retrieval is not None and 'case_comparison' not in context:
        detail=build_case_context(retrieval)
        context['facts'].extend(detail.pop('facts'));context['case_comparison']=detail
    method=(retrieval or {}).get('comparison',{}).get('method','context_contract_v1')
    ruleset=(retrieval or {}).get('comparison',{}).get('ruleset')
    sid=snapshot_fingerprint(snapshot,side,method+(':'+ruleset if ruleset else ''),analysis_time=context['as_of_utc'],include_cases=retrieval is not None,validity=context['status'],draft=draft,input_revision=input_revision);query=query or {}
    context.update(snapshot_id=sid,query_as_of_utc=query.get('as_of'))
    if context.get('case_comparison') is not None:
        context['case_comparison'].update(snapshot_id=sid,query_as_of_utc=query.get('as_of'))
    frames=query.get('pre_entry_bars') or {};cutoff=query.get('as_of')
    charts=dict(snapshot_id=sid,query_as_of_utc=cutoff,source='ctrader_demo_xauusd',query={},cases=[])
    charts['analysis']=build_analysis_visuals(snapshot,context,now if now is not None else datetime.now(timezone.utc).timestamp())
    for interval,span,n in [('5m',300,60),('1h',3600,20)]:
        charts['query'][interval]=chart_bars(frames.get(interval,[]),span,cutoff,n)
    operations={}
    for item in (context.get('case_comparison') or {}).get('cases',[]):
        source=(operation_sources or {}).get(item['case_id'])
        if source is None:source=next((row for row in (retrieval or {}).get('cases',[]) if row.get('id')==item['case_id']),{})
        operations[item['ref']]=build_case_operations(source)
        profile=(profiles or {}).get(item['case_id']) or {};bars=profile.get('pre_entry_bars') or {}
        execution=execution_store.get(item['case_id'],profile,source,cutoff) if execution_store else None
        charts['cases'].append(dict(ref=item['ref'],as_of_utc=profile.get('as_of'),clock_status='UNKNOWN',alignment='PROJECT_REFERENCE',
            execution=execution,holding_observation=summarize_holding(execution,source.get('side'),cutoff=cutoff),
            **{interval:chart_bars(bars.get(interval,[]),span,profile.get('as_of'),n) for interval,span,n in [('5m',300,60),('1h',3600,20)]}))
    summary,outcomes,facts=build_scenarios(snapshot,context,query,side,draft=draft,input_revision=input_revision,forward_store=forward_store)
    context['outcome_analysis']=summary
    context['facts'].extend(facts)
    return dict(snapshot_id=sid,context=context,charts=charts,operations=operations,outcomes=outcomes)
