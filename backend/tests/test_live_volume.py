from decimal import Decimal
from copy import deepcopy
from backend import live_assistant as live
from backend.technical import analyze_native
from backend.tests.test_live_assistant import snapshot,NOW

def test_tick_volume_has_closed_count_prior_twenty_mean_and_program_relation():
 s=snapshot()
 for b in s['bars']['5m'][-21:-1]:b['volume']=100
 s['bars']['5m'][-1]['volume']=200
 a=analyze_native(s['bars']['5m'],300,NOW)['volume_activity']
 assert a['status']=='AVAILABLE' and a['last']=='200' and a['mean20']=='100'
 assert Decimal(a['ratio'])==2 and a['relation']=='ABOVE'
 context=live.build_live_context(s,now=NOW);fact=next(f for f in context['facts'] if f['id']=='f5.volume')
 assert fact['values']['f5_volume_count']=='200' and fact['values']['f5_volume_state']=='高於前20根均量'
 assert 'tick' in fact['text'] and 'f5.volume' in live.relevant_ids(context,'目前盤面如何')

def test_zero_is_a_real_count_but_unknown_and_zero_baseline_have_no_fake_ratio():
 s=snapshot()
 for b in s['bars']['5m'][-21:-1]:b['volume']=100
 s['bars']['5m'][-1]['volume']=0
 a=analyze_native(s['bars']['5m'],300,NOW)['volume_activity']
 assert a['last']=='0' and Decimal(a['ratio'])==0 and a['relation']=='BELOW'
 s['bars']['5m'][-1]['volume']=None
 a=analyze_native(s['bars']['5m'],300,NOW)['volume_activity'];assert a['last'] is None and a['ratio'] is None
 for b in s['bars']['5m'][-21:]:b['volume']=0
 a=analyze_native(s['bars']['5m'],300,NOW)['volume_activity'];assert a['status']=='ZERO_BASELINE' and a['ratio'] is None

def test_volume_baseline_needs_contiguous_closed_bars_and_excludes_forming_bar():
 s=snapshot();expected=analyze_native(s['bars']['5m'],300,NOW)['volume_activity']
 s['bars']['5m'].append(dict(s['bars']['5m'][-1],time=NOW,volume=999999))
 assert analyze_native(s['bars']['5m'],300,NOW)['volume_activity']==expected
 del s['bars']['5m'][-4]
 a=analyze_native(s['bars']['5m'],300,NOW)['volume_activity'];assert a['status']=='GAPPED_BASELINE' and a['ratio'] is None

def test_volume_question_selects_volume_not_atr_and_writer_receives_no_raw_numbers():
 context=live.build_live_context(snapshot(),now=NOW);ids=live.relevant_ids(context,'五分鐘成交量如何')
 assert 'f5.volume' in ids and 'f5.range' not in ids and 'f1.volume' not in ids
 facts=live.writer_facts([f for f in context['facts'] if f['id']=='f5.volume'])
 assert 'values' not in facts[0] and 'f5_volume_count' in facts[0]['tokens']
 assert facts[0]['basis']['f5_volume_state'] in ('高於前20根均量','低於前20根均量','等於前20根均量')


def test_model_can_explain_volume_using_only_frozen_tokens(monkeypatch):
 import json
 def provider(*args,**kwargs):
  facts=kwargs['catalog']['facts'];volume=next(f for f in facts if f['id']=='f5.volume')
  assert 'values' not in volume and 'f5_volume_count' in volume['tokens']
  return dict(status='ok',model='test',text=json.dumps({'sections':[dict(title='量能',text='券商tick量{{f5_volume_count}}次，量比{{f5_volume_ratio}}倍；{{f5_volume_state}}。',fact_ids=['f5.volume'])]}))
 monkeypatch.setattr(live,'explain_context',provider)
 answer=live.respond_live(snapshot(),'五分鐘成交量如何',enabled=True,now=NOW)
 assert answer['llm_status']=='ok' and '219' in answer['message'] and '{{' not in answer['message']
 assert answer['draft'] is None
