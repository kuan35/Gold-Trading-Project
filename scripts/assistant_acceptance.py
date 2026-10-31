"""Five fully synthetic Claude acceptance scenarios. Explicit gate, one batch, no retry."""
import argparse,hashlib,json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from backend import case_review,live_assistant
from backend.case_context import build_case_context
from backend.holding_observation import summarize
from backend.trade_result import trade_result
from backend.claude_code import complete,configuration
from backend.assistant import scrub

OUTPUT=Path(__file__).resolve().parents[1]/'private/focused_review_20261030/acceptance'


def scenarios():
    result=[]
    for name,side,status in [('buy','BUY','PASSED'),('sell','SELL','PASSED'),('no_match','BUY','NO_RULE_MATCH'),('gapped','BUY','PASSED'),('insufficient','BUY','INSUFFICIENT_DATA')]:
        tail='上行' if side=='BUY' else '下行'
        item=dict(id='SYNTHETIC',group='SYNTHETIC',side=side,path_distance_pct=.1,hour_path_distance_pct=.2,tail_path_distance_pct=.04,volatility_ratio=1.2,
            event_label='區間內活動',tail_direction=tail,context_check={'passed':True})
        matched=status=='PASSED'
        retrieval=dict(rule_status=status,total=1 if matched else 0,wins=1 if matched else 0,losses=0,flat=0,unknown=0,query_side=side,cases=[item] if matched else [],
            comparison=dict(method='context_contract_v1',eligible_rows=2,query_event_label='區間內活動',query_tail_direction=tail,thresholds=dict(d5=.25,d1h=.5,dtail=.12,vol_ratio=2),rejections={}))
        comparison=build_case_context(retrieval)
        facts=[dict(id='quote',text='這是合成測試報價，不提供真實即時價位。',values={}),
            dict(id='f5.trend',text='合成五分鐘趨勢{{f5_bias}}。',values={'f5_bias':tail}),
            dict(id='f1.missing' if name=='insufficient' else 'f1.trend',text='一小時背景{{f1_bias}}。',values={'f1_bias':'資料不足' if name=='insufficient' else tail}),
            dict(id='limits',text='合成驗收，沒有新聞、資金流或交易委託。',values={}),*comparison['facts']]
        context=dict(source='SYNTHETIC_ACCEPTANCE',status='CURRENT',as_of_utc='SYNTHETIC_TIME',quote_time_utc='SYNTHETIC_TIME',facts=facts,case_comparison=comparison,snapshot_id='synthetic-'+name)
        bundle=dict(snapshot_id=context['snapshot_id'],context=context,operations={},charts=dict(snapshot_id=context['snapshot_id'],query={'5m':[],'1h':[]},cases=[]))
        if matched:
            rows=[dict(time=t,open=100,high=105 if side=='SELL' else 110,low=90 if side=='SELL' else 95,close=96 if side=='SELL' else 104) for t in ((300,900,1200,1500) if name=='gapped' else (300,600,900))]
            observation=summarize(dict(status='AVAILABLE',mode='FULL_HOLDING',coverage={'scope':'WHOLE_REFERENCE_HOLDING'},opened_at=300,closed_at=1500 if name=='gapped' else 900,bars=rows),side,cutoff=1800)
            bundle['operations']['案例甲']=dict(representative=dict(price_result=trade_result(dict(side=side,entry='100',exit='96' if side=='SELL' else '104'))))
            bundle['charts']['cases']=[dict(ref='案例甲',holding_observation=observation,**{'5m':[],'1h':[]})]
        result.append(dict(name=name,bundle=bundle,matched=matched))
    return result


def execute(scenario,invoke):
    def bridge(context,question,**kwargs):
        exchange=dict(system=kwargs['system_prompt'],question=scrub(question),catalog=kwargs['catalog'])
        return invoke(exchange)
    with patch.object(case_review,'explain_context',bridge),patch.object(live_assistant,'explain_context',bridge):
        if scenario['matched']:
            return case_review.review_cases(scenario['bundle'],case_ref='案例甲',enabled=True,model='sonnet',effort='medium')
        return live_assistant.respond_context(scenario['bundle']['context'],'請說明合成盤面與案例資料狀態，不編造相似案例。',enabled=True,model='sonnet',effort='medium')


def build_preview():
    entries=[]
    for scenario in scenarios():
        captured=[]
        execute(scenario,lambda exchange:(captured.append(deepcopy(exchange)) or dict(status='preview_only',model='sonnet')))
        if len(captured)!=1:raise ValueError('expected exactly one synthetic exchange')
        entries.append(dict(scenario=scenario['name'],**captured[0]))
    return dict(destination='official Claude Code / Anthropic',model='sonnet',effort='medium',maximum_calls=5,
        synthetic_only=True,private_data=False,images=False,stop_on_non_ok=True,retry=False,exchanges=entries)


def preview(directory=OUTPUT):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    payload=build_preview()
    target=directory/'outgoing_payload_preview.json'
    target.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    return payload


def run(*,allowed=False,directory=OUTPUT,infer=None):
    directory=Path(directory)
    if not allowed:raise ValueError('explicit --allow-external is required')
    state_path=directory/'acceptance_state.json'
    if state_path.exists():raise ValueError('batch already started; no automatic repeat or resume')
    target=directory/'outgoing_payload_preview.json'
    payload=json.loads(target.read_text(encoding='utf-8'))
    if payload!=build_preview():raise ValueError('outgoing content changed after preview')
    state=dict(attempted=0,maximum_calls=5,results=[],stopped=False,preview_sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    # Claim the one permitted batch atomically before any provider invocation.
    try:
        with state_path.open('x',encoding='utf-8') as marker:json.dump(state,marker,ensure_ascii=False,indent=2)
    except FileExistsError:raise ValueError('batch already started; no automatic repeat or resume') from None
    inference=infer or complete
    for index,scenario in enumerate(scenarios()):
        def invoke(exchange):
            expected=payload['exchanges'][index]
            if expected!=dict(scenario=scenario['name'],**exchange):raise ValueError('outgoing content changed after preview')
            if state['attempted']>=5:raise ValueError('call budget exceeded')
            state['attempted']+=1
            state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
            return inference(exchange['system'],exchange['question']+'\ncontext:\n'+json.dumps(exchange['catalog'],ensure_ascii=False),json_output=True,model='sonnet',effort='medium')
        response=execute(scenario,invoke)
        state['results'].append(dict(scenario=scenario['name'],status=response['llm_status'],provider=response['provider'],response=response))
        state['stopped']=response['llm_status']!='ok'
        state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
        if state['stopped']:break
    return state


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-external',action='store_true',help='execute the previewed five synthetic scenarios at most once')
    args=parser.parse_args()
    if not args.allow_external:
        value=preview();print(json.dumps({key:value[key] for key in ('destination','model','effort','maximum_calls','synthetic_only','private_data','images','stop_on_non_ok','retry')},ensure_ascii=False));return 0
    info=configuration()
    if not info['authenticated']:print(json.dumps({'status':'authentication_required','attempted':0}));return 2
    result=run(allowed=True)
    print(json.dumps(dict(attempted=result['attempted'],stopped=result['stopped'],results=[{key:r[key] for key in ('scenario','status','provider')} for r in result['results']]),ensure_ascii=False))
    return 1 if result['stopped'] else 0


if __name__=='__main__':raise SystemExit(main())
