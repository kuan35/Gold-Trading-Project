"""No external API or private fixtures; inspect grounded summaries and failure modes."""
import json
import httpx
from backend import assistant
from backend.engine import Engine
from backend.market import load_bars


def synthetic_engine(monkeypatch):
    # Avoid local private files even when running inside the desktop checkout.
    from backend import engine, cases, market
    monkeypatch.setattr(market, 'ROOT', __import__('pathlib').Path('/nonexistent-fixtures'))
    monkeypatch.setattr(cases, 'ROOT', __import__('pathlib').Path('/nonexistent-fixtures'))
    monkeypatch.setattr(engine, 'load_bars', load_bars)
    return Engine()


def enable(monkeypatch):
    monkeypatch.setenv('GOLD_ENABLE_LLM', 'true')
    monkeypatch.setenv('GOLD_LLM_API_KEY', 'test-key')
    monkeypatch.setenv('GOLD_LLM_BASE_URL', 'https://portal.genai.nchc.org.tw/api/v1/')
    monkeypatch.setenv('GOLD_LLM_MODEL', 'Gemma-3-TAIDE-12b-Chat-2602')


def chosen_facts(catalog):
    return json.dumps({key: section['defaults'] for key, section in catalog['sections'].items()})


def test_context_has_only_closed_frames_and_no_identifiers(monkeypatch):
    engine=synthetic_engine(monkeypatch)
    engine.cases.items=[]
    draft=engine.create_draft('BUY','0.10',None,None)
    context=assistant.build_context(engine, draft=draft)
    assert context['historical_reference']['status']=='no_matches'
    assert context['market']['mode']=='replay'
    assert context['market']['is_live'] is False
    assert {x['interval'] for x in context['market']['frames']}=={'5m','15m','1h'}
    assert all(x['last_closed_at']<=context['market']['as_of_utc'] for x in context['market']['frames'])
    assert draft['id'] not in json.dumps(context)
    assert 'global_volume' in context['market']['missing_data']


def test_custom_provider_and_empty_cases_still_explains_market(monkeypatch):
    enable(monkeypatch)
    engine=synthetic_engine(monkeypatch)
    engine.cases.items=[]
    def post(url, **kwargs):
        assert url=='https://portal.genai.nchc.org.tw/api/v1/chat/completions'
        body=json.dumps(kwargs['json'],ensure_ascii=False)
        assert '沒有符合' in body and 'MA20' in body
        assert 'test-key' not in body and 'sk-secret123' not in body
        assert kwargs['json']['response_format']=={'type':'json_object'}
        catalog=json.loads(kwargs['json']['messages'][1]['content'].split('\ncontext:\n',1)[1])
        return httpx.Response(200,json={'choices':[{'message':{'content':chosen_facts(catalog)},'finish_reason':'stop'}]},request=httpx.Request('POST',url))
    monkeypatch.setattr(httpx,'post',post)
    reply=assistant.respond(engine,'分析目前盤面 sk-secret123','BUY','0.10')
    assert reply['provider']=='configured_llm'
    assert reply['llm_status']=='ok' and reply['draft'] is None
    assert '沒有符合' in reply['message'] and engine.orders==[]
    assert reply['explanation_card']['origin']=='model_selection'


def test_expired_key_is_reported_without_leak(monkeypatch):
    enable(monkeypatch)
    def post(url, **kwargs):
        return httpx.Response(400,json={'message':{'error':{'type':'expired_key','param':'test-key'}}},request=httpx.Request('POST',url))
    monkeypatch.setattr(httpx,'post',post)
    result=assistant.explain_context({'market':{}},'分析')
    assert result['status']=='expired_key' and 'test-key' not in json.dumps(result)
    assert result['text'] is None


def test_disabled_never_calls_provider(monkeypatch):
    monkeypatch.setenv('GOLD_ENABLE_LLM','false')
    monkeypatch.setattr(httpx,'post',lambda *a,**k: (_ for _ in ()).throw(AssertionError('network')))
    assert assistant.explain_context({},'分析')['status']=='disabled'


def test_form_draft_attaches_explanation_without_execution(monkeypatch):
    enable(monkeypatch)
    engine=synthetic_engine(monkeypatch)
    draft=engine.create_draft('SELL','0.10',None,None)
    monkeypatch.setattr(assistant,'explain_context',lambda *a,**k:dict(status='ok',text=chosen_facts(k['catalog']),model='test-model'))
    result=assistant.explain_draft(engine,draft)
    assert result['llm']['status']=='ok' and '盤面依據' in result['explanation']
    assert result['status']=='REVIEW' and engine.orders==[]


def test_empty_or_truncated_provider_response_does_not_count_as_success(monkeypatch):
    enable(monkeypatch)
    for content,reason in [('', 'stop'),('半句', 'length')]:
        monkeypatch.setattr(httpx,'post',lambda url,**k:httpx.Response(200,json={'choices':[{'message':{'content':content},'finish_reason':reason}]},request=httpx.Request('POST',url)))
        result=assistant.explain_context({},'分析')
        assert result['status'] in ('invalid_response','truncated') and result['text'] is None


def test_future_candles_do_not_change_explanation_context(monkeypatch):
    engine=synthetic_engine(monkeypatch)
    before=assistant.build_context(engine)
    engine.bars[engine.cursor]['close']='99999.99'
    engine.bars[engine.cursor]['high']='99999.99'
    assert assistant.build_context(engine)==before


def test_form_api_uses_llm_and_quote_change_during_wait_invalidates_draft(monkeypatch):
    from fastapi.testclient import TestClient
    from backend import app as module
    enable(monkeypatch)
    engine=synthetic_engine(monkeypatch)
    monkeypatch.setattr(module,'engine',engine)
    def post(url, **kwargs):
        engine.step(1)
        catalog=json.loads(kwargs['json']['messages'][1]['content'].split('\ncontext:\n',1)[1])
        return httpx.Response(200,json={'choices':[{'message':{'content':chosen_facts(catalog)},'finish_reason':'stop'}]},request=httpx.Request('POST',url))
    monkeypatch.setattr(httpx,'post',post)
    with TestClient(module.app) as client:
        draft=client.post('/api/drafts',json={'side':'BUY','lot':'0.10'}).json()
        assert draft['llm']['status']=='ok'
        assert '歷史回放' in draft['explanation']
        response=client.post('/api/drafts/'+draft['id']+'/confirm',json={'revision':draft['revision'],'idempotency_key':'stale-llm'})
        assert response.status_code==409
        assert not engine.positions and not engine.orders
