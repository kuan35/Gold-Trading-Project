from backend.macro_knowledge import question_kind,knowledge
import json,pytest
from backend import claude_code
from backend.live_assistant import _check_model_topics
from backend.conversation_intent import interpret_message

def test_beginner_help_is_knowledge_and_explains_the_actual_workflow():
 assert question_kind('黃金交易新手要先了解什麼？')=='knowledge'
 info=knowledge('黃金交易新手要先了解什麼？')
 assert '市價' in info['explanation'] and '停損' in info['explanation']
 assert question_kind('黃金新手幫我買進0.1手') is None

@pytest.mark.parametrize('wrapped',[False,True])
def test_cli_exact_json_object_or_single_code_fence_is_accepted(monkeypatch,wrapped):
 monkeypatch.setattr(claude_code,'command',lambda:['synthetic-cli'])
 text='{"sections":[{"title":"合成","text":"只解釋給定資料","fact_ids":[]}]}'
 if wrapped:text='```json\n'+text+'\n```'
 class Process:
  returncode=0
  def __init__(self,*a,**k):pass
  def communicate(self,**k):return json.dumps(dict(type='result',subtype='success',is_error=False,result=text)),''
 monkeypatch.setattr(claude_code.subprocess,'Popen',Process)
 result=claude_code.complete('合成','合成',json_output=True)
 assert result['status']=='ok' and isinstance(json.loads(result['text']),dict)

@pytest.mark.parametrize('text',['hello ```json\n{}\n```','```json\n{}\n``` trailing','```json\n[]\n```','```json\n{}\n```\n```json\n{}\n```'])
def test_cli_does_not_extract_arbitrary_json_or_ignore_extra_prose(monkeypatch,text):
 monkeypatch.setattr(claude_code,'command',lambda:['synthetic-cli'])
 class Process:
  returncode=0
  def __init__(self,*a,**k):pass
  def communicate(self,**k):return json.dumps(dict(type='result',subtype='success',is_error=False,result=text)),''
 monkeypatch.setattr(claude_code.subprocess,'Popen',Process)
 assert claude_code.complete('合成','合成',json_output=True)['status']=='invalid_response'

def test_macro_support_word_is_not_a_technical_price_level():
 facts={'gold.relation':dict(text='美元走弱時可能支持黃金。',values={})}
 _check_model_topics(dict(title='條件式關聯',text='美元走弱時，黃金可能受到支撐。',fact_ids=['gold.relation']),facts)
 with pytest.raises(ValueError):
  _check_model_topics(dict(title='技術價位',text='這裡是支撐線。',fact_ids=['gold.relation']),facts)
 with pytest.raises(ValueError):
  _check_model_topics(dict(title='動能',text='RSI轉強。',fact_ids=['gold.relation']),facts)

def test_qualitative_two_sided_signal_question_is_discussion_not_conflicting_order():
 value=interpret_message('目前黃金盤面有哪些偏多與偏空訊號？')
 assert value['intent']=='DISCUSS' and value['analysis_side'] is None
 assert value['patch']=={} and value['proposal']=={}
 for q in ('幫我下單做多做空0.1手','把委託改成偏多或偏空','偏多偏空各買0.1手，分析盤面訊號'):
  assert interpret_message(q)['intent']=='CLARIFY'

def test_recent_macro_window_does_not_mean_sixty_future_days():
 from backend.tests.test_macro_assistant import feed
 from backend.macro_assistant import select_context
 s=feed();s['as_of_utc']='2026-11-01T01:00:00+00:00'
 event=s['events'][0]
 s['events']=[dict(event,id='near',date='2026-11-04',scheduled_at_utc='2026-11-04T13:30:00+00:00'),dict(event,id='far',date='2026-12-01',scheduled_at_utc='2026-12-01T13:30:00+00:00')]
 value=select_context(s,'最近有哪些總經事件會影響黃金？')
 assert [e['id'] for e in value['events']]==['near']
 assert '7天' in value['requested_window']
