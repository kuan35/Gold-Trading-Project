from copy import deepcopy
import json
from backend.macro_assistant import answer,augment_bundle,macro_facts
from backend.macro_knowledge import relationship

def feed():return dict(status='PARTIAL',snapshot_id='public-feed',as_of_utc='2026-11-01T01:00:00+00:00',coverage='官方來源',sources=[],news=[],consensus_status='NOT_PROVIDED',actual_values_status='NOT_FETCHED',events=[dict(id='one',title='CPI',topic='CPI',date='2026-11-10',scheduled_at_utc='2026-11-10T13:30:00+00:00',timing_precision='EXACT',status='SCHEDULED',freshness='CURRENT',source_url='https://www.bls.gov/schedule/',fetched_at_utc='2026-11-01T01:00:00+00:00',actual=None,consensus=None,previous=None,gold_relation=relationship('CPI'))])

def test_knowledge_works_without_quote_and_every_relation_is_two_sided():
 value=answer('CPI是什麼，對黃金有什麼影響？','knowledge',None)
 assert value['analysis_mode']=='gold_knowledge' and value['draft'] is None and value['snapshot_id'] is None
 text=json.dumps(value,ensure_ascii=False);assert '偏多' in text and '偏空' in text and '機制' in text
 assert '目前金價' not in text and '市場尚未' not in text

def test_calendar_does_not_call_absent_actual_a_surprise():
 value=answer('下次CPI有哪些重大事件？','calendar',feed())
 assert value['macro_context']['events'][0]['actual'] is None
 assert '未提供市場共識' in json.dumps(value,ensure_ascii=False)
 assert '高於預期' not in '\n'.join(s['text'] for s in value['sections'])

def test_model_receives_macro_facts_and_same_thread_memory_not_broker_secrets(monkeypatch):
 from backend import macro_assistant as module
 calls=[]
 def complete(*args,**kw):calls.append(kw);return dict(status='disabled',model=None)
 monkeypatch.setattr(module,'explain_context',complete)
 value=answer('那降息呢？','knowledge',None,enabled=True,provider='codex',conversation_id='a',conversation=[dict(thread_id='a',question='CPI4500',answer='SECRETKEY')])
 assert calls and calls[0]['provider_override']=='codex'
 assert '4500' not in str(calls[0]['catalog']['previous_dialogue'])
 assert value['draft'] is None

def test_macro_capture_changes_identity_without_mutating_old_bundle_or_retrieval():
 base=dict(snapshot_id='old',context=dict(snapshot_id='old',facts=[dict(id='limits',text='未提供新聞',values={})],case_comparison={'snapshot_id':'old','counts':{'passed':2}}),charts={'snapshot_id':'old'},operations={},outcomes={})
 original=deepcopy(base);updated=augment_bundle(base,feed())
 assert base==original and updated['snapshot_id']!='old'
 assert updated['context']['case_comparison']['counts']==original['context']['case_comparison']['counts']
 assert updated['charts']['snapshot_id']==updated['snapshot_id']==updated['context']['case_comparison']['snapshot_id']
 assert any(f['id'].startswith('macro.') for f in updated['context']['facts'])

def test_live_fallback_can_include_multiple_macro_events_without_oversized_sections():
 from backend.tests.test_live_assistant import snapshot,NOW
 from backend.live_assistant import build_live_context,respond_context
 context=build_live_context(snapshot(),now=NOW);context['snapshot_id']='x'
 public=feed();public['events']*=3
 bundle=augment_bundle(dict(snapshot_id='x',context=context,charts={}),public)
 response=respond_context(bundle['context'],'做多要留意什麼消息？',enabled=False)
 assert response['macro_context'] and any(i.startswith('macro.') for s in response['sections'] for i in s['fact_ids'])

def test_unsupported_macro_outcomes_are_rejected_in_standalone_and_live(monkeypatch):
 from backend import macro_assistant as module,live_assistant as live
 from backend.tests.test_live_assistant import snapshot,NOW
 malicious=dict(status='ok',provider='codex',model='fake',text=json.dumps({'sections':[dict(title='消息',text='本次CPI高於預期，聯準會已決定升息，美元正在走強。',fact_ids=['macro.coverage'])]}))
 monkeypatch.setattr(module,'explain_context',lambda *a,**k:malicious)
 value=answer('今天有什麼消息？','news',feed(),enabled=True)
 assert value['llm_status']=='invalid_grounding'
 assert '本次CPI高於預期' not in value['message']
 monkeypatch.setattr(live,'explain_context',lambda *a,**k:malicious)
 context=live.build_live_context(snapshot(),now=NOW);context['facts']+=macro_facts(feed());context['macro_context']=feed()
 assert live.respond_context(context,'盤面消息',enabled=True)['llm_status']=='invalid_grounding'

def test_calendar_filters_requested_taiwan_day_and_topic_before_limiting():
 from backend.macro_assistant import select_context
 s=feed();s['as_of_utc']='2026-11-01T01:00:00+00:00'
 for i in range(6):s['events'].insert(0,dict(s['events'][0],id='past'+str(i),date='2026-11-02',scheduled_at_utc='2026-11-02T13:30:00+00:00'))
 s['events'].append(dict(s['events'][0],id='fed',topic='FOMC',date='2026-12-09',scheduled_at_utc=None,timing_precision='DATE_ONLY',gold_relation=relationship('FOMC')))
 assert select_context(s,'今天有什麼事件')['events']==[]
 filtered=select_context(s,'下次FOMC何時');assert len(filtered['events'])==1 and filtered['events'][0]['topic']=='FOMC'

def test_conditional_model_explanation_is_retained_with_both_scenario_facts(monkeypatch):
 from backend import macro_assistant as module
 raw=dict(sections=[dict(title='政策與黃金',text='若通膨低於預期且實質利率回落，可能支持黃金；若政策比原先預期緊縮，則可能壓抑黃金。',fact_ids=['gold.relation'])])
 monkeypatch.setattr(module,'explain_context',lambda *a,**k:dict(status='ok',provider='codex',model='fake',text=json.dumps(raw)))
 value=answer('CPI是什麼','knowledge',None,enabled=True)
 assert value['provider']=='codex_market_analysis' and value['llm_status']=='ok'
 assert value['gold_relation']['bullish'] and value['gold_relation']['bearish']
