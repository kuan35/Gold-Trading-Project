"""Synthetic regression checks: no credentials and no external API."""
import httpx
from pathlib import Path
from backend import assistant


def test_scrub_other_provider_credentials(monkeypatch):
    monkeypatch.delenv('GOLD_LLM_API_KEY', raising=False)
    sample = 'gsk_syntheticSecret0123456789 hf_syntheticSecret0123456789 sk-syntheticSecret0123456789'
    cleaned = assistant.scrub(sample)
    assert 'syntheticSecret' not in cleaned


def test_groq_reasoning_configuration_hides_internal_reasoning(monkeypatch):
    monkeypatch.setenv('GOLD_ENABLE_LLM', 'true')
    monkeypatch.setenv('GOLD_LLM_API_KEY', 'synthetic-key')
    monkeypatch.setenv('GOLD_LLM_BASE_URL', 'https://api.groq.com/openai/v1')
    monkeypatch.setenv('GOLD_LLM_MODEL', 'openai/gpt-oss-120b')
    monkeypatch.setenv('GOLD_LLM_REASONING_EFFORT', 'low')
    monkeypatch.setenv('GOLD_LLM_MAX_TOKENS', '2048')
    def post(url, **kwargs):
        body = kwargs['json']
        assert body['reasoning_effort'] == 'low'
        assert body['include_reasoning'] is False
        assert 'tools' not in body
        return httpx.Response(200, json={'choices':[{'message':{'content':'這是歷史回放摘要。'},'finish_reason':'stop'}]})
    monkeypatch.setattr(httpx, 'post', post)
    assert assistant.explain_context({}, '分析')['status'] == 'ok'


def test_invalid_reasoning_setting_never_calls_provider(monkeypatch):
    monkeypatch.setenv('GOLD_ENABLE_LLM', 'true')
    monkeypatch.setenv('GOLD_LLM_API_KEY', 'synthetic-key')
    monkeypatch.setenv('GOLD_LLM_REASONING_EFFORT', 'unexpected')
    monkeypatch.setattr(httpx, 'post', lambda *a, **k: (_ for _ in ()).throw(AssertionError('network')))
    assert assistant.explain_context({}, '分析')['status'] == 'invalid_configuration'


def test_context_defines_statistic_windows_and_ma_units(monkeypatch):
    from backend import cases, market
    from backend.engine import Engine
    monkeypatch.setattr(cases, 'ROOT', Path('Z:/synthetic-fixture'))
    monkeypatch.setattr(market, 'ROOT', Path('Z:/synthetic-fixture'))
    engine = Engine()
    context = assistant.build_context(engine, side='BUY', lot='0.10')
    frame = context['market']['frames'][0]
    assert frame['window_start_utc'] < frame['last_closed_at']
    assert frame['ma_unit'] == 'bars_of_interval'
    assert frame['change_basis'] == 'first_open_to_last_close_in_window'
    assert frame['close_vs_ma20'] == 'below'
    assert frame['close_vs_ma60'] == 'below'
    assert context['historical_reference']['source_kind'] == 'synthetic_demo'


def test_history_distinguishes_pool_counts_from_displayed_cases(monkeypatch):
    from backend import cases, market
    from backend.engine import Engine
    monkeypatch.setattr(cases, 'ROOT', Path('Z:/synthetic-fixture'))
    monkeypatch.setattr(market, 'ROOT', Path('Z:/synthetic-fixture'))
    history = assistant.build_context(Engine(), side='BUY', lot='0.10')['historical_reference']
    assert history['count_labels']['flat'] == '持平候選群'
    assert history['displayed_case_count'] == len(history['cases'])
    assert history['pool_extrema_provided'] is False


def test_invented_ratios_and_pool_extrema_fall_back(monkeypatch):
    monkeypatch.setenv('GOLD_ENABLE_LLM','true')
    monkeypatch.setenv('GOLD_LLM_API_KEY','synthetic-key')
    monkeypatch.delenv('GOLD_LLM_REASONING_EFFORT',raising=False)
    context={'market':{'summary_5m':{'change_pct':'-0.03'}},
             'historical_reference':{'pool_extrema_provided':False}}
    for text in ('虧損比例超過四成。', '歷史勝率73.7%。', '最差-108.70，最佳39.30。'):
        monkeypatch.setattr(httpx,'post',lambda *a,**k:httpx.Response(200,json={'choices':[{'message':{'content':text},'finish_reason':'stop'}]}))
        result=assistant.explain_context(context,'分析')
        assert result['status']=='unverified_claim' and result['text'] is None
    monkeypatch.setattr(httpx,'post',lambda *a,**k:httpx.Response(200,json={'choices':[{'message':{'content':'窗口下跌0.03%，歷史結果不是勝率。'},'finish_reason':'stop'}]}))
    assert assistant.explain_context(context,'分析')['status']=='ok'
