import json
from backend import assistant,claude_code


def enable(monkeypatch):
    monkeypatch.setenv('GOLD_ENABLE_LLM','true')
    monkeypatch.setenv('GOLD_LLM_PROVIDER','claude_code')
    monkeypatch.delenv('GOLD_LLM_API_KEY',raising=False)
    monkeypatch.setattr(claude_code,'configuration',lambda:dict(installed=True,authenticated=True,reason='ready'))


def test_claude_uses_existing_redacted_catalog_without_api_key_or_http(monkeypatch):
    enable(monkeypatch)
    monkeypatch.setattr(assistant.httpx,'post',lambda *a,**k: (_ for _ in ()).throw(AssertionError('HTTP')))
    calls=[]
    def complete(system,prompt,**kw):
        calls.append((system,prompt,kw))
        return dict(status='ok',text='{"sections":[]}',model='sonnet',provider='claude_code')
    monkeypatch.setattr(claude_code,'complete',complete)
    assert assistant.llm_enabled()
    result=assistant.explain_context({},'分析 sk-private-test',catalog={'facts':[{'id':'f5.trend','text':'合成盤面'}]},request_opt_in=True)
    assert result['provider']=='claude_code' and result['status']=='ok'
    assert 'sk-private-test' not in calls[0][1] and '合成盤面' in calls[0][1] and calls[0][2]['json_output']


def test_disabled_or_not_logged_in_never_invokes_inference(monkeypatch):
    enable(monkeypatch)
    monkeypatch.setattr(claude_code,'complete',lambda *a,**k: (_ for _ in ()).throw(AssertionError('model')))
    monkeypatch.setenv('GOLD_ENABLE_LLM','false')
    assert assistant.explain_context({},'分析')['status']=='disabled'
    monkeypatch.setenv('GOLD_ENABLE_LLM','true')
    monkeypatch.setattr(claude_code,'configuration',lambda:dict(installed=True,authenticated=False,reason='authentication_required'))
    assert not assistant.llm_enabled()
    assert assistant.explain_context({},'分析',request_opt_in=True)['status']=='authentication_failed'
    status=assistant.model_configuration()
    assert not status['configured'] and status['provider_label']=='Claude Code'


def test_claude_image_is_rejected_explicitly_without_inference(monkeypatch):
    enable(monkeypatch)
    monkeypatch.setattr(claude_code,'complete',lambda *a,**k: (_ for _ in ()).throw(AssertionError('model')))
    r=assistant.explain_context({},'圖像',catalog={},image_url='data:image/png;base64,AAAA',request_opt_in=True)
    assert r['status']=='unsupported_image'


def test_invalid_provider_fails_closed_even_if_api_key_exists(monkeypatch):
    monkeypatch.setenv('GOLD_LLM_PROVIDER','mistyped')
    monkeypatch.setenv('GOLD_ENABLE_LLM','true')
    monkeypatch.setenv('GOLD_LLM_API_KEY','test-key')
    assert not assistant.llm_enabled()
    assert assistant.explain_context({},'q')['status']=='invalid_configuration'


def test_claude_free_text_still_passes_existing_grounding_check(monkeypatch):
    enable(monkeypatch)
    monkeypatch.setattr(claude_code,'complete',lambda *a,**k:dict(status='ok',text='勝率99%',model='sonnet',provider='claude_code'))
    assert assistant.explain_context({},'分析',request_opt_in=True)['status']=='unverified_claim'


def test_provider_identity_is_not_hardcoded_to_groq(monkeypatch):
    from backend import live_assistant
    from backend.tests.test_live_assistant import snapshot,NOW
    context=live_assistant.build_live_context(snapshot(),now=NOW)
    def complete(*a,**kw):
        fact=kw['catalog']['facts'][0]
        return dict(status='ok',text=json.dumps({'sections':[dict(title='盤面',text=fact['text'],fact_ids=[fact['id']])]}),model='sonnet',provider='claude_code')
    monkeypatch.setattr(live_assistant,'explain_context',complete)
    result=live_assistant.respond_context(context,'分析目前黃金盤面',enabled=True)
    assert result['provider']=='claude_market_analysis'


def test_status_route_has_claude_metadata_and_denies_remote_without_probing(monkeypatch):
    from starlette.requests import Request
    from backend.app import assistant_status
    enable(monkeypatch)
    def request(client,host):
        return Request({'type':'http','method':'GET','scheme':'http','path':'/api/assistant/status',
          'query_string':b'','headers':[(b'host',host.encode())],'client':(client,12345),'server':('127.0.0.1',8765)})
    response=assistant_status(request('127.0.0.1','127.0.0.1:8765'))
    body=json.loads(response.body)
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert body['provider']=='claude_code' and body['configured'] and body['supports_vision'] is False
    monkeypatch.setattr(claude_code,'configuration',lambda: (_ for _ in ()).throw(AssertionError('remote probe')))
    assert assistant_status(request('203.0.113.1','public.example')).status_code==403


def test_claude_requires_request_opt_in_even_if_server_is_enabled(monkeypatch):
    enable(monkeypatch)
    monkeypatch.setattr(claude_code,'complete',lambda *a,**k: (_ for _ in ()).throw(AssertionError('implicit external call')))
    assert assistant.explain_context({},'舊版回放自動摘要',catalog={})['status']=='disabled'
