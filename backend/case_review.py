"""Explain only already-retrieved anonymous cases; has no ranking authority."""
import json,os,re
from decimal import Decimal
from .assistant import explain_context,status_text
from .live_assistant import writer_facts,render_model_sections,render_sections,LIVE_SYSTEM
from .case_vision import preview
from .engine import DomainError

COMPACT_TITLES=('相同點','重要差異','持倉過程')


def _selected_cases(bundle,case_ref=None):
    cases=list(enumerate((bundle['context'].get('case_comparison') or {}).get('cases',[])[:5],1))
    if case_ref is None:return cases
    selected=[item for item in cases if item[1]['ref']==case_ref]
    if len(selected)!=1:raise DomainError('此原分析快照沒有選取的歷史案例，未改用其他案例。',404)
    return selected


def selected_charts(bundle,case_ref=None):
    _selected_cases(bundle,case_ref)
    charts=bundle['charts']
    if charts.get('snapshot_id')!=bundle['snapshot_id']:raise DomainError('案例圖像與原快照不一致。',409)
    if case_ref is None:return charts
    cases=[row for row in charts.get('cases',[]) if row.get('ref')==case_ref]
    if len(cases)!=1:raise DomainError('此快照沒有保留選取案例的圖表。',404)
    return dict(charts,cases=cases)


def review_facts(bundle,*,case_ref=None):
    context=bundle['context'];facts=[]
    charts=bundle.get('charts') or {}
    observations={row['ref']:row.get('holding_observation') for row in charts.get('cases',[])} if charts.get('snapshot_id')==bundle['snapshot_id'] else {}
    # Do not forward free questions, times, IDs, source filenames, or account data.
    for f in context['facts']:
        if f['id'] in ('f5.trend','f1.trend','f5.range','f1.range','f5.volume','history.status','history.tick_volume'):
            facts.append(f)
    for i,c in _selected_cases(bundle,case_ref):
        row=bundle.get('operations',{}).get(c['ref'],{}).get('representative',{})
        result=row.get('price_result') or {};values={f'c{i}_event_state':c.get('event','未知'),f'c{i}_tail_state':c.get('tail_direction','未知')}
        text=c['ref']+'的進場前事件{{c'+str(i)+'_event_state}}，末段{{c'+str(i)+'_tail_state}}。'
        for m in c.get('metrics',[]):
            key=f'c{i}_{m["key"]}'
            values[key]=m.get('actual') or '資料不足';values[key+'_limit']=m.get('tolerance') or '資料不足'
            text+=m['label']+'差距{{'+key+'}}'+m['unit']+'，容忍{{'+key+'_limit}}'+m['unit']+'。'
        if result.get('status')=='AVAILABLE':
            values.update({f'c{i}_return':result['price_return_pct'],f'c{i}_move':result['move_per_oz'],
                f'c{i}_result_state':'依交易方向計的正價格報酬（未扣交易成本）' if Decimal(result['price_return_pct'])>0 else '依交易方向計的負價格報酬（未扣交易成本）' if Decimal(result['price_return_pct'])<0 else '價格持平（未扣交易成本）'})
            text+='原單事後方向調整價格報酬{{c'+str(i)+'_return}}%，價差{{c'+str(i)+'_move}}美元／盎司；{{c'+str(i)+'_result_state}}。'
        if row.get('profit') is not None and row.get('currency') is not None:
            values[f'c{i}_reported_profit']=row['profit'];values[f'c{i}_ccy_state']=row['currency']
            text+='原報表單筆結果{{c'+str(i)+'_reported_profit}} {{c'+str(i)+'_ccy_state}}。'
        holding=observations.get(c['ref']) or {}
        if holding.get('status') in ('AVAILABLE','PARTIAL'):
            values.update({f'c{i}_observed_mae':holding['observed_mae_pct'],f'c{i}_observed_mfe':holding['observed_mfe_pct'],
                f'c{i}_reference_return':holding['reference_return_pct'],f'c{i}_observation_count':str(holding['bars_used']),
                f'c{i}_observation_basis_state':'以參考首根完整棒開盤起算，非原單實際損益；'+('期間有時間間隔，只涵蓋已知完整棒' if holding['status']=='PARTIAL' else '只涵蓋進出場之間已收完整棒')})
            text+='已知K棒中的最大逆向{{c'+str(i)+'_observed_mae}}%，最大順向{{c'+str(i)+'_observed_mfe}}%，觀察段收尾變動{{c'+str(i)+'_reference_return}}%。{{c'+str(i)+'_observation_basis_state}}。'
        else:
            text+='持倉過程資料不足，不推算途中最大逆向或順向。'
        text+='這是已選案例的事後結果，不是此次進場的預測；保證金ROI資料不足。'
        values[f'c{i}_similarities_state']='；'.join(c.get('similarities') or ['情境資料需核對'])
        different=[]
        for metric in c.get('metrics',[]):
            try:
                if Decimal(metric['actual'])>(1 if metric['key'] in ('vol_ratio','tick_ratio') else 0):different.append(metric['label'])
            except (KeyError,TypeError,ArithmeticError):pass
        values[f'c{i}_differences_state']='、'.join(different) if different else '目前比較項目沒有量到差距，仍不代表所有細節一致'
        text+='相同點{{c'+str(i)+'_similarities_state}}；仍有差距的項目{{c'+str(i)+'_differences_state}}。'
        facts.append(dict(id=f'history.case{i}',text=text,values=values))
    return facts


def _compact_program_sections(facts,index):
    prefix='c'+str(index);ident='history.case'+str(index)
    fact=next(f for f in facts if f['id']==ident);values=fact['values']
    holding='原單價格報酬{{'+prefix+'_return}}%（未扣交易成本）。' if prefix+'_return' in values else '原單價格報酬資料不足。'
    if prefix+'_observed_mae' in values:
        holding+='已知參考K棒最大逆向{{'+prefix+'_observed_mae}}%，最大順向{{'+prefix+'_observed_mfe}}%，觀察段收尾{{'+prefix+'_reference_return}}%。{{'+prefix+'_observation_basis_state}}。'
    else:holding+='持倉過程沒有足夠完整棒，暫不計途中波動。'
    texts=['{{'+prefix+'_similarities_state}}。案例事件{{'+prefix+'_event_state}}、末段{{'+prefix+'_tail_state}}。',
        '仍可見差距的項目：{{'+prefix+'_differences_state}}。',holding]
    return render_sections([dict(title=title,text=text,fact_ids=[ident]) for title,text in zip(COMPACT_TITLES,texts)],facts)


def _require_compact_sections(sections):
    if (not isinstance(sections,list) or len(sections)!=3 or
        [s.get('title') for s in sections if isinstance(s,dict)]!=list(COMPACT_TITLES) or
        any(not isinstance(s.get('text'),str) or len(s['text'])>360 for s in sections)):
        raise ValueError('invalid focused sections')


def _require_observation_basis(sections):
    if not isinstance(sections,list):raise ValueError('invalid sections')
    for section in sections:
        message=section.get('text','') if isinstance(section,dict) else ''
        if not isinstance(message,str):raise ValueError('invalid text')
        for paragraph in re.split(r'\n\s*\n|\u2029',message):
            cases=set(re.findall(r'\{\{c([1-5])_(?:observed_mae|observed_mfe|reference_return)\}\}',paragraph))
            if any('{{c'+index+'_observation_basis_state}}' not in paragraph for index in cases):
                raise ValueError('missing observation basis in paragraph')


def review_cases(bundle,*,enabled=False,vision=False,model=None,effort=None,case_ref=None,provider=None):
    selected=_selected_cases(bundle,case_ref)
    facts=review_facts(bundle,case_ref=case_ref);base=dict(snapshot_id=bundle['snapshot_id'],case_ref=case_ref,provider='program',llm_status='disabled',sections=[])
    def vision_unavailable(status,notice):
        sections=_compact_program_sections(facts,selected[0][0]) if case_ref is not None else []
        return dict(base,llm_status=status,notice=notice,sections=sections,message=notice+'\n\n'+'\n\n'.join(s['title']+'\n'+s['text'] for s in sections))
    if not (bundle['context'].get('case_comparison') or {}).get('cases'):
        return dict(base,message='本次沒有可供分析的歷史案例，請查看原盤面摘要與草稿風險。')
    if enabled:
        kwargs={k:v for k,v in dict(model_override=model,effort_override=effort).items() if v is not None}
        if provider:kwargs['provider_override']=provider
        if vision:
            model=os.getenv('GOLD_LLM_VISION_MODEL','').strip()
            if not model:return vision_unavailable('vision_not_configured','尚未設定支援圖像的GOLD_LLM_VISION_MODEL；可先使用文字案例分析。')
            image=preview(selected_charts(bundle,case_ref))
            if image['complete_panels']!=len(image['rows'])*2:return vision_unavailable('vision_insufficient_data','雙週期進場前K棒不足，圖像未送出；可先使用文字案例分析。')
            kwargs.update(image_url=image['image_url'],model_override=model)
        payload={'mode':'selected_historical_case_review','facts':writer_facts(facts)}
        if case_ref is not None:payload['focus']=dict(case_ref=case_ref,section_titles=list(COMPACT_TITLES))
        if vision:payload['image_layout']={k:v for k,v in image.items() if k!='image_url'}
        system=LIVE_SYSTEM+'\n本次專門分析已檢索案例：比較查詢與歷史進場前情境、說明仍有何差異，以及原單事後價格結果。持倉過程只解釋程式提供的已知參考K棒觀察值，不是原單實際損益；不能用事後結果判斷目前該進場。凡引用cN_observed_mae、cN_observed_mfe或cN_reference_return，必須在同一段原樣保留{{cN_observation_basis_state}}（N換成該案例編號），不得省略缺口及參考起點限制；沒有程式順序資料，不能宣稱先虧後賺或同棒先後。圖像若有附上仍只有進場前畫面，按image_layout對應列，不用它核實持倉後續，不增加數字或新支撐／買賣訊號。'
        if case_ref is not None:system+='\n只分析focus指定案例，固定依序輸出相同點、重要差異、持倉過程三個sections，每段簡短、不超過三百六十字；不列其他案例或逐項重述演算法門檻。差距不要自行排序；使用程式提供的定性比較與占位符。'
        response=explain_context({},'比較這次選出的歷史案例與查詢盤面，並解釋歷史單筆結果。',catalog=payload,system_prompt=system,request_opt_in=enabled,**kwargs)
        base.update(llm_status=response['status'],model=response.get('model'),requested_effort=response.get('requested_effort',effort))
        if response['status']=='ok':
            try:
                raw=json.loads(response['text'])['sections'];_require_observation_basis(raw)
                if case_ref is not None:_require_compact_sections(raw)
                sections,repaired=render_model_sections(raw,facts)
                if case_ref is not None and (repaired or any(len(s['text'])>450 for s in sections)):raise ValueError('focused narrative not grounded')
                return dict(base,llm_status='partial_grounding' if repaired else 'ok',provider='claude_case_review' if response.get('provider')=='claude_code' else 'codex_case_review' if response.get('provider')=='codex' else 'groq_case_review',sections=sections,
                    message=('部分段落由程式依據補充。\n\n' if repaired else '')+'\n\n'.join(s['title']+'\n'+s['text'] for s in sections))
            except (ValueError,KeyError,TypeError):base['llm_status']='invalid_grounding'
    sections=[]
    if case_ref is not None:
        sections=_compact_program_sections(facts,selected[0][0])
        return dict(base,sections=sections,message='\n\n'.join(s['title']+'\n'+s['text'] for s in sections))
    for f in facts:
        if f['id'].startswith('history.case'):
            sections.extend(render_sections([dict(title='歷史案例'+'甲乙丙丁戊'[int(f['id'][-1])-1],text=f['text'],fact_ids=[f['id']])],[f]))
    return dict(base,sections=sections,message=(status_text(base['llm_status'])+'\n' if enabled else '')+'\n\n'.join(s['text'] for s in sections))
