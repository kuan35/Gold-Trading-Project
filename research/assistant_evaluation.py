"""Bounded offline prompt comparison. No training, orders, retries or raw case upload."""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal
from html import escape
import json
from pathlib import Path
import sys
from time import perf_counter, sleep

PRODUCT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PRODUCT))
from backend.assistant import explain_context
from backend.case_context import build_case_context
from backend.compact_market import describe_compact, PHASES
from backend.context_rules import market_features
from backend.context_retrieval import EVENT_LABELS,TAIL_LABELS
from backend.live_assistant import LIVE_SYSTEM,writer_facts,render_sections,render_model_sections
from research.similarity_evaluation import OUTPUT,dump,digest

OFFLINE_NOTE='''\n這次是離線參考盤面評估，不是即時行情；「目前」僅指樣本當時，不得冒稱現在報價。只使用提供的sample與history事實，未提供即時Bid/Ask、MA、RSI、MACD、tick量及新聞就明說未提供，不套用它們的即時版指示。區間上／下緣只是指定窗口的高低參考，不能稱有效支撐壓力或保證會反彈。回答優先直接回應問題，簡短說明一致處、差異或缺資料；每段仍需合法fact_ids及占位符。'''
EXAMPLES='''\n以下只示範格式，真正回答需依本題facts，不可照抄範例的判斷：
例：問「目前情境是什麼？」→ {"sections":[{"title":"先看短線","text":"樣本當時五分鐘首尾{{sample_five_return}}%；末段{{sample_tail_state}}。整段與末段描述不同時間範圍，需要一起看。","fact_ids":["sample.five"]}]}
例：問「區間邊界在哪？」→ {"sections":[{"title":"參考區間","text":"樣本參考區間為{{sample_ref_low}}至{{sample_ref_high}}；{{sample_event_state}}。這些是觀察窗口的上下緣，不能單憑它們認定會反彈或受阻。","fact_ids":["sample.event"]}]}
'''
QUESTIONS=[
 '請用白話說明這個樣本的五分鐘走勢與一小時背景，有何差異？',
 '樣本當時的區間上下緣在哪？能直接稱為有效支撐壓力嗎？',
 '找出的案例有哪些相似與不同？如果沒有符合請直接說明。',
 '最近半小時方向與整段走勢一致嗎？',
 '這個樣本的量能與新聞是否支持突破？',
 '歷史案例有符合，是否代表這次一定會賺？',
]


def safe_catalog(facts):
    return dict(source='offline_project_reference',analysis_mode='offline_reference_evaluation',facts=writer_facts(facts))


def build_facts(profile,retrieval,side):
    feature=market_features(profile);desc=describe_compact(profile,side)
    def net(iv,n):
        bars=profile['pre_entry_bars'][iv][-n:]
        return format(((Decimal(str(bars[-1]['close']))/Decimal(str(bars[0]['close'])))-1)*100,'.4f')
    five_return=net('5m',60)
    five_state='淨上行' if Decimal(five_return)>0 else '淨下行' if Decimal(five_return)<0 else '首尾相同'
    facts=[dict(id='sample.five',text='樣本五分鐘已收窗口首尾{{sample_five_return}}%（{{sample_five_state}}）；最近半小時{{sample_tail_state}}。',
                values=dict(sample_five_return=five_return,sample_five_state=five_state,sample_tail_state=TAIL_LABELS[feature['tail_direction']])),
           dict(id='sample.hour',text='一小時已收窗口首尾{{sample_hour_return}}%；三段走勢為{{sample_hour_state}}。',
                values=dict(sample_hour_return=net('1h',20),sample_hour_state='→'.join(PHASES[c] for c in desc['pattern_1h']))),
           dict(id='sample.event',text='樣本參考區間下緣{{sample_ref_low}}、上緣{{sample_ref_high}}；事件{{sample_event_state}}。這是觀察窗口高低，尚未驗證為有效支撐壓力。',
                values=dict(sample_ref_low=feature['reference_low'],sample_ref_high=feature['reference_high'],sample_event_state=EVENT_LABELS[feature['event']])),
           dict(id='sample.limits',text='這是離線專題參考盤面，不是現在行情。未提供即時報價、新聞、成交量、資金流與完整均線動能指標。原始案例時鐘未獨立核實。',values={})]
    history=build_case_context(retrieval,{**profile,'side':side},snapshot_id='offline-evaluation')
    wanted={'history.status','history.case1','history.rejections','history.limits'}
    facts.extend(f for f in history['facts'] if f['id'] in wanted)
    return facts


def program_text(facts):
    sections=render_sections([dict(title='盤面依據',text=f['text'],fact_ids=[f['id']]) for f in facts],facts)
    return '\n\n'.join(s['text'] for s in sections)


def evaluate_answer(facts,question,variant,*,call_model=False,provider=None):
    result=dict(variant=variant,api_status='not_requested',output_source='program',raw_fully_grounded=False,
                repaired=False,raw_text=None,display_text=program_text(facts),seconds=None,model=None)
    if variant=='program': return result
    if not call_model:return dict(result,output_source='not_run')
    provider=provider or explain_context
    prompt=LIVE_SYSTEM+OFFLINE_NOTE+(EXAMPLES if variant=='few_shot' else '')
    start=perf_counter()
    response=provider({},question,catalog=safe_catalog(facts),system_prompt=prompt)
    result.update(api_status=response['status'],seconds=perf_counter()-start,model=response.get('model'),raw_text=response.get('text'))
    if response['status']!='ok':return dict(result,output_source='program_fallback')
    try:
        raw=json.loads(response['text'])['sections']
        sections,repaired=render_model_sections(raw,facts)
        result.update(raw_fully_grounded=not repaired,repaired=repaired,
                      output_source='model_with_program_repair' if repaired else 'model',
                      display_text='\n\n'.join(s['title']+'\n'+s['text'] for s in sections))
    except (ValueError,KeyError,TypeError):result['output_source']='program_fallback'
    return result


def run_study(samples,out,*,call_model=False,provider=None,pause_seconds=0):
    if len(samples)>6:raise ValueError('MAX_SIX_SAMPLES_TWELVE_CALLS')
    out.mkdir(parents=True,exist_ok=True); rows=[]; stopped=False
    for n,sample in enumerate(samples):
        variants=('program','current_prompt','few_shot') if n%2==0 else ('program','few_shot','current_prompt')
        for variant in variants:
            if stopped and variant!='program':
                value=dict(variant=variant,api_status='not_attempted',output_source='not_run',raw_fully_grounded=False,
                           repaired=False,raw_text=None,display_text='',seconds=None,model=None)
            else:
                value=evaluate_answer(sample['facts'],sample['question'],variant,call_model=call_model,provider=provider)
                if call_model and variant!='program' and value['api_status']!='ok':stopped=True
            rows.append(dict(sample_id=sample['sample_id'],question=sample['question'],**value))
            dump(out/'assistant_results_PRIVATE.json',rows)
            if call_model and variant!='program' and not stopped and pause_seconds:sleep(pause_seconds)
    return rows


def summarize_answers(keys,ratings):
    from collections import Counter
    known={k['answer_id']:k for k in keys};seen=set();by_variant={}
    fields=['faithfulness_1_to_5','relevance_1_to_5','clarity_1_to_5']
    for row in ratings:
        ident=row.get('answer_id');reviewer=row.get('reviewer','')
        if ident not in known or reviewer not in ('reviewer_1','reviewer_2'):raise ValueError('UNKNOWN_ANSWER_OR_REVIEWER')
        if (ident,reviewer) in seen:raise ValueError('DUPLICATE_RATING')
        seen.add((ident,reviewer));raw=[row.get(f,'').strip() for f in fields]
        if any(s and s not in ('1','2','3','4','5') for s in raw):raise ValueError('INVALID_SCORE')
        if all(raw):
            if known[ident]['source']=='not_run':raise ValueError('UNAVAILABLE_ANSWER_CANNOT_BE_RATED')
            by_variant.setdefault(known[ident]['variant'],[]).append((known[ident],list(map(int,raw))))
    result={}
    for variant in sorted({k['variant'] for k in keys}):
        completed=by_variant.get(variant,[])
        assigned=2*sum(k['variant']==variant for k in keys)
        result[variant]=dict(assigned=assigned,completed=len(completed),unfilled_or_partial=assigned-len(completed),source_counts=dict(Counter(k['source'] for k,s in completed)))
        for n,label in enumerate(('faithfulness','relevance','clarity')):
            result[variant]['mean_'+label]=sum(s[n] for k,s in completed)/len(completed) if completed else None
    return result


def render_review(samples,rows,out):
    keyed={s['sample_id']:s for s in samples}; review_keys=[]; cards=[]
    for row in sorted(rows,key=lambda r:digest(r['sample_id']+r['variant'])):
        ident='A'+digest(row['sample_id']+row['variant'])[:9].upper()
        review_keys.append(dict(answer_id=ident,sample_id=row['sample_id'],variant=row['variant'],source=row['output_source'],split=keyed[row['sample_id']].get('split')))
        facts=program_text(keyed[row['sample_id']]['facts'])
        text=row['display_text'] if row['output_source']!='not_run' else '本版本尚未取得回答，請勿評分。'
        cards.append('<section><h2>'+ident+'</h2><p><strong>問題：</strong>'+escape(row['question'])+'</p><details><summary>本題資料依據</summary><pre>'+escape(facts)+'</pre></details><pre>'+escape(text)+'</pre></section>')
    dump(out/'assistant_blinding_key_PRIVATE.json',review_keys)
    for reviewer in ('1','2'):
        path=out/f'assistant_reviewer_{reviewer}.csv'
        if not path.exists():
            with path.open('x',encoding='utf-8-sig',newline='') as f:
                writer=csv.writer(f);writer.writerow(['answer_id','reviewer','faithfulness_1_to_5','relevance_1_to_5','clarity_1_to_5','unsupported_claim','reason'])
                for key in review_keys:writer.writerow([key['answer_id'],'reviewer_'+reviewer,'','','','',''])
    (out/'assistant_review.html').write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>助手回答評估</title><style>body{font:18px/1.7 system-ui;background:#f3f5f7;color:#223445;max-width:1000px;margin:24px auto;padding:0 20px}section{background:white;padding:24px;margin:20px 0;border:1px solid #d8dfe5;border-radius:8px}pre{white-space:pre-wrap;font:inherit}summary{cursor:pointer}</style><h1>固定盤面事實：助手回答評估</h1><p>請對照資料，獨立評忠實、切題與易懂各1–5分，填入 assistant_reviewer CSV。這裡評的是產品最後呈現文字，可能包含程式補正，不能當模型原始語意正確率。方法名稱已遮，但文風仍可能被辨認；未取得回答不評分。請勿先讀解盲鍵。</p>'+''.join(cards)+'</html>',encoding='utf8')


def summarize_saved(out):
    keys=json.loads((out/'assistant_blinding_key_PRIVATE.json').read_text(encoding='utf8'));ratings=[]
    for p in sorted(out.glob('assistant_reviewer_*.csv')):
        with p.open(encoding='utf-8-sig',newline='') as f:ratings.extend(csv.DictReader(f))
    summary=dict(all=summarize_answers(keys,ratings),by_split={})
    for split in ('development','reserved_review'):
        subset=[k for k in keys if k.get('split')==split];ids={k['answer_id'] for k in subset}
        summary['by_split'][split]=summarize_answers(subset,[r for r in ratings if r['answer_id'] in ids])
    dump(out/'assistant_human_summary.json',summary)
    if (out/'assistant_results_PRIVATE.json').exists():
        rows=json.loads((out/'assistant_results_PRIVATE.json').read_text(encoding='utf8'))
        dump(out/'assistant_summary.json',summarize_model_results(rows))
    return summary


def summarize_model_results(rows):
    from collections import Counter
    summary={}
    for variant in ('program','current_prompt','few_shot'):
        selected=[r for r in rows if r['variant']==variant]
        attempts=[r for r in selected if r['seconds'] is not None]
        successful=[r for r in attempts if r['api_status']=='ok']
        summary[variant]=dict(samples=len(selected),attempted=len(attempts),api_ok=len(successful),
            raw_fully_grounded=sum(r['raw_fully_grounded'] for r in selected),repaired=sum(r['repaired'] for r in selected),
            fallback=sum(r['output_source']=='program_fallback' for r in selected),statuses=dict(Counter(r['api_status'] for r in selected)),
            mean_seconds_all_attempts=sum(r['seconds'] for r in attempts)/len(attempts) if attempts else None,
            mean_seconds_api_ok=sum(r['seconds'] for r in successful)/len(successful) if successful else None,
            human_semantic_accuracy=None)
    return summary


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--call-llm',action='store_true');parser.add_argument('--summarize',action='store_true');args=parser.parse_args(argv)
    out=args.output.resolve()
    if not out.is_relative_to((PRODUCT/'private').resolve()):raise ValueError('PRIVATE_OUTPUT_REQUIRED')
    if args.summarize:print(json.dumps(summarize_saved(out),ensure_ascii=False));return
    records=json.loads((out/'results_PRIVATE.json').read_text(encoding='utf8'))
    profiles=json.loads((out/'query_profiles_PRIVATE.json').read_text(encoding='utf8'))
    samples=[]
    for n,record in enumerate(records[::5]):
        samples.append(dict(sample_id='S'+str(n+1),query_id=record['query_id'],split=record['split'],question=QUESTIONS[n],
                            facts=build_facts(profiles[record['query_id']],record['current'],record['side'])))
    sample_path=out/'assistant_samples_PRIVATE.json'
    if sample_path.exists() and json.loads(sample_path.read_text(encoding='utf8'))!=samples:raise ValueError('FROZEN_ASSISTANT_INPUT_CHANGED')
    dump(sample_path,samples)
    result_path=out/'assistant_results_PRIVATE.json'
    if result_path.exists():
        old=json.loads(result_path.read_text(encoding='utf8'))
        if any(r['api_status'] not in ('not_requested','not_attempted') for r in old):raise ValueError('EXISTING_MODEL_RUN_PRESERVED_USE_NEW_OUTPUT')
    rows=run_study(samples,out,call_model=args.call_llm,pause_seconds=2 if args.call_llm else 0)
    render_review(samples,rows,out)
    summary=summarize_model_results(rows)
    dump(out/'assistant_summary.json',summary);summarize_saved(out);print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
