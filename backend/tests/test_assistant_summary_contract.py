"""Full synthetic retrieval bundles, including the previously missed third case."""
from copy import deepcopy
from types import SimpleNamespace
import json
import pytest

from backend import live_assistant as live
from backend.case_analysis import prepare_analysis
from backend.case_statistics import summarize_original_trades
from backend.tests.test_case_context import retrieval
from backend.tests.test_live_assistant import NOW, snapshot


def full_bundle():
    snap=snapshot();snap['quote'].update(bid='4000.12',ask='4000.32')
    snap['symbol']=dict(lot_size_cents=10000,min_volume_cents=100,max_volume_cents=1000000,step_volume_cents=100)
    result=retrieval();seed=result['cases'][0]
    rows=[dict(seed,id=f'SYNTHETIC_CASE_{i}',side='BUY',entry='2000',exit='2003.074',profit=str(i+1),currency='USD',
        available_at=NOW-100000,opened_at='2023-10-03T08:00:00',closed_at='2023-10-04T10:00:00') for i in range(6)]
    result.update(total=6,cases=rows[:5],original_performance=summarize_original_trades(rows))
    query=dict(as_of=NOW,pre_entry_bars=snap['bars'])
    bundle=prepare_analysis(snap,'BUY',result,query,now=NOW,
        profiles={r['id']:deepcopy(query) for r in rows},operation_sources={r['id']:r for r in rows},
        draft=dict(side='BUY',lot='.1',order_type='MARKET',sl='3990',tp='4020'))
    return bundle


def first_model(reply):
    return next(s for s in reply['sections'] if s.get('source')=='model')


def test_five_displayed_six_pool_program_draft_never_runs_model_claim_guard():
    bundle=full_bundle()
    assert bundle['context']['case_comparison']['counts']['passed']==6
    assert len(bundle['context']['case_comparison']['cases'])==5
    fact=next(f for f in bundle['context']['facts'] if f['id']=='history.case3')
    assert '下次獲利機率' in fact['text']  # This trusted negative statement caused HTTP500.
    reply=live.respond_context(bundle['context'],'說明草稿建立時盤面支持與相反依據、案例差異',enabled=False,frozen=True)
    assert reply['llm_status']=='not_requested' and reply['market_status']=='FROZEN'
    assert '0.1537%' in reply['message'] and '100.00%' in reply['message']
    assert all(s['source']=='program' for s in reply['sections'])
    assert reply['case_comparison']['performance']['total']==6


def test_checked_order_returns_json_with_five_cases_instead_of_claim_guard_500(monkeypatch):
    from backend.tests.test_case_analysis_api import setup
    from backend import app
    from fastapi.testclient import TestClient
    setup(monkeypatch)
    monkeypatch.setattr(app,'_frozen_trade_advice',lambda *a:None)
    monkeypatch.setattr(app,'_analysis_operation_sources',lambda *a:{})
    monkeypatch.setattr(app,'prepare_analysis',lambda *a,**k:full_bundle())
    monkeypatch.setattr(app,'broker_orders',SimpleNamespace(create=lambda *a,**k:dict(id='synthetic-draft',revision=1,risk={})))
    response=TestClient(app.app,raise_server_exceptions=False).post('/api/broker/drafts',json=dict(side='BUY',lot='.1',sl='3990',tp='4020'))
    assert response.status_code==200,response.text
    assert response.headers['content-type'].startswith('application/json')
    assert response.json()['analysis_reply']['case_comparison']['performance']['total']==6


def test_model_claim_guard_still_rejects_fabricated_price_and_predicted_win_probability():
    facts=full_bundle()['context']['facts']
    for text in ['本次獲利機率為{{pool_win_rate}}%。','現價為4999。','本次勝率為{{pool_win_rate}}%。']:
        with pytest.raises(ValueError):
            live.render_sections([dict(title='綜合建議',text=text,fact_ids=['history.aggregate','f5.trend'])],facts)


def test_trusted_renderer_uses_only_fact_template_and_cannot_echo_rejected_model_prose():
    facts=[dict(id='history.case3',text='通過條件不等於下次獲利機率。',values={})]
    rendered=live.render_program_sections([dict(title='程式證據',text='價格會到4999，直接下單。',fact_ids=['history.case3'])],facts)
    assert rendered==[dict(title='程式證據',text=facts[0]['text'],fact_ids=['history.case3'],source='program')]


def test_invalid_model_with_full_cases_falls_back_without_500_or_false_model_attribution(monkeypatch):
    bundle=full_bundle()
    monkeypatch.setattr(live,'explain_context',lambda *a,**k:dict(status='ok',text=json.dumps({'sections':[
        dict(title='綜合建議',text='價格會到4999。',fact_ids=['history.case3'])]})))
    reply=live.respond_context(bundle['context'],'這筆委託怎麼看？',enabled=True,frozen=True)
    assert reply['llm_status']=='invalid_grounding'
    assert reply['summary_evidence_state']=='MODEL_REJECTED'
    assert reply['grounding_failure_code']=='no grounded narrative'
    assert reply['provider']=='local_market_rules'
    assert all(s['source']=='program' for s in reply['sections'])
    assert '4999' not in reply['message']


def test_summary_contract_keeps_current_pool_and_shape_in_model_first_paragraph(monkeypatch):
    bundle=full_bundle()
    def provider(*a,**kw):
        catalog=kw['catalog'];facts={f['id']:f for f in catalog['facts']}
        assert {'f5.trend','history.aggregate','history.case1','history.shape1','history.trade1'}<=facts.keys()
        assert catalog['summary_contract']['pool_fact_id']=='history.aggregate'
        assert '第一段必須' in kw['system_prompt']
        assert not any(secret in json.dumps(catalog) for secret in ['2003.074','SYNTHETIC_CASE_0','2023-10-03'])
        return dict(status='ok',provider='claude_code',text=json.dumps({'sections':[
            dict(title='這筆委託評估',text='做多草稿有歷史支持：同池{{pool_price_count}}筆有效原單平均價格報酬{{pool_mean_return}}%；但當時{{f5_live_reading_state}}，案例事件{{hist1_event_state}}仍須比較反證。',
                 fact_ids=['draft.terms','history.aggregate','f5.trend','history.case1'])]}))
    monkeypatch.setattr(live,'explain_context',provider)
    reply=live.respond_context(bundle['context'],'這筆委託怎麼看？',enabled=True,frozen=True)
    assert reply['summary_evidence_state']=='COMPLETE'
    assert first_model(reply)['text'].startswith('做多草稿有歷史支持')
    assert '0.1537%' in first_model(reply)['text']
    assert '當時' in first_model(reply)['text']


def test_grounded_model_history_paragraph_is_promoted_without_inventing_linking_words(monkeypatch):
    bundle=full_bundle()
    first='先等當時{{f5_live_reading_state}}改善，再評估做多。'
    history='同池{{pool_known}}筆有效損益的歷史獲利比例{{pool_win_rate}}%是歷史支持，但案例末段{{hist1_tail_state}}不能當成本次結果。'
    monkeypatch.setattr(live,'explain_context',lambda *a,**k:dict(status='ok',text=json.dumps({'sections':[
        dict(title='這筆委託評估',text=first,fact_ids=['f5.trend']),
        dict(title='歷史參照',text=history,fact_ids=['history.aggregate','history.case1'])]})))
    reply=live.respond_context(bundle['context'],'這筆委託怎麼看？',enabled=True,frozen=True)
    summary=first_model(reply)
    assert reply['summary_evidence_state']=='COMPLETE'
    assert summary['source']=='model' and summary['text'].count('歷史獲利比例')==1
    assert '100.00%' in summary['text']
    assert {'f5.trend','history.aggregate','history.case1'}<=set(summary['fact_ids'])
    assert len([s for s in reply['sections'] if s['source']=='model'])==1


def test_model_missing_history_is_explicit_and_program_stats_do_not_become_model_summary(monkeypatch):
    bundle=full_bundle()
    monkeypatch.setattr(live,'explain_context',lambda *a,**k:dict(status='ok',text=json.dumps({'sections':[
        dict(title='這筆委託評估',text='當時{{f5_live_reading_state}}，先等價格位置改善再評估做多。',fact_ids=['f5.trend'])]})))
    reply=live.respond_context(bundle['context'],'這筆委託怎麼看？',enabled=True,frozen=True)
    assert reply['summary_evidence_state']=='INCOMPLETE_HISTORY'
    assert reply['llm_status']=='partial_grounding'
    assert reply['sections'][0]['source']=='model'
    assert '0.1537%' not in first_model(reply)['text']
    assert 'history.aggregate' not in first_model(reply)['fact_ids']
    assert any(s['source']=='program' and '0.1537%' in s['text'] for s in reply['sections'][1:])
    assert '未完成歷史關聯' in reply['message']


def test_pool_token_without_correct_denominator_is_not_complete(monkeypatch):
    bundle=full_bundle()
    monkeypatch.setattr(live,'explain_context',lambda *a,**k:dict(status='ok',text=json.dumps({'sections':[
        dict(title='這筆委託評估',text='當時{{f5_live_reading_state}}；同池平均報酬{{pool_mean_return}}%是支持，但案例{{hist1_event_state}}仍有反證。',
             fact_ids=['f5.trend','history.aggregate','history.case1'])]})))
    reply=live.respond_context(bundle['context'],'這筆委託怎麼看？',enabled=True,frozen=True)
    assert reply['summary_evidence_state']=='INCOMPLETE_HISTORY'
    assert 'pool_denominator' in reply['summary_evidence_missing']


def test_negative_prediction_warning_is_not_rejected_as_a_prediction():
    facts=full_bundle()['context']['facts']
    rows=live.render_sections([dict(title='歷史限制',text='這是歷史參照，不是這筆草稿的未來勝率。',fact_ids=['history.aggregate'])],facts)
    assert '不是這筆草稿' in rows[0]['text']
    for phrase in ['這筆草稿的未來勝率為{{pool_win_rate}}%。','本次獲利機率為{{pool_win_rate}}%。']:
        with pytest.raises(ValueError):live.render_sections([dict(title='歷史限制',text=phrase,fact_ids=['history.aggregate'])],facts)


def test_pool_percentage_tokens_always_display_their_unit_once():
    facts=full_bundle()['context']['facts']
    for suffix in ['', '%']:
        rows=live.render_sections([dict(title='歷史參照',text='歷史平均價格報酬{{pool_mean_return}}'+suffix+'；歷史獲利比例{{pool_win_rate}}'+suffix+'。',fact_ids=['history.aggregate'])],facts)
        assert '0.1537%' in rows[0]['text'] and '100.00%' in rows[0]['text']
        assert '%%' not in rows[0]['text']
