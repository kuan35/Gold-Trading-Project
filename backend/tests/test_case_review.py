from copy import deepcopy
import base64,json
from backend.case_review import review_cases,review_facts
from backend.case_vision import preview
from backend.case_operations import build_case_operations
from backend.tests.test_case_context import retrieval
from backend.tests.test_case_analysis_api import market
from backend.case_analysis import prepare_analysis
from backend.holding_observation import summarize


def bundle():
    r=retrieval();r['cases']=[dict(deepcopy(r['cases'][0]),id='PRIVATE'+str(i),entry='2000',exit='2010',side='BUY') for i in range(5)]
    # The fixture retains its original validated aggregate denominators.
    r['total']=5;r['wins']=5;r['losses']=r['flat']=r['unknown']=0;r['comparison']['eligible_rows']=10
    return prepare_analysis(market(),'BUY',r)


def test_all_five_selected_cases_have_program_price_result_and_no_private_payload(monkeypatch):
    from backend import case_review
    b=bundle();facts=review_facts(b)
    assert len([f for f in facts if f['id'].startswith('history.case')])==5
    assert review_cases(b)['provider']=='program'
    calls=[]
    def fake(*a,**kw):
        calls.append((a,kw));return dict(status='ok',model='mock',text=json.dumps({'sections':[{
          'title':'歷史案例甲','text':'原單事後價格報酬{{c1_return}}%，價差{{c1_move}}美元／盎司；結果不代表此次進場。','fact_ids':['history.case1']}]}))
    monkeypatch.setattr(case_review,'explain_context',fake)
    r=review_cases(b,enabled=True)
    assert r['provider']=='groq_case_review' and '0.5%' in r['message']
    raw=json.dumps(calls,ensure_ascii=False)
    assert all(x not in raw for x in ('PRIVATE','ACCOUNT_SECRET','2010','2000','source_file','"closed_at":'))
    assert 'history.case5' in raw


def test_image_is_pre_entry_only_and_missing_vision_model_never_calls_provider(monkeypatch):
    from backend import case_review
    b=bundle();b['charts']['query']={'5m':[dict(time=1,open=2,high=3,low=1,close=2)],'1h':[]}
    p=preview(b['charts']);png=base64.b64decode(p['image_url'].split(',')[1])
    assert png.startswith(b'\x89PNG') and b'PRIVATE' not in png
    assert 'query_as_of' not in json.dumps(p)
    monkeypatch.delenv('GOLD_LLM_VISION_MODEL',raising=False)
    monkeypatch.setattr(case_review,'explain_context',lambda *a,**kw: (_ for _ in ()).throw(AssertionError('must not call')))
    assert review_cases(b,enabled=True,vision=True)['llm_status']=='vision_not_configured'
    assert review_cases(b,enabled=False,vision=True)['provider']=='program'


def test_png_invariant_to_real_price_scale_and_timestamp():
    a={'query':{'5m':[dict(time=111,open=100,high=110,low=90,close=100)],'1h':[]},'cases':[]}
    b=deepcopy(a);b['query']['5m'][0].update(time=999999,open=1000,high=1100,low=900,close=1000)
    assert preview(a)['image_url']==preview(b)['image_url']


def test_sell_price_down_is_positive_return_not_an_upward_price_claim():
    b=bundle()
    for exit_,label in [('1990','正價格報酬（未扣交易成本）'),('2010','負價格報酬（未扣交易成本）')]:
        for c in b['context']['case_comparison']['cases']:
            b['operations'][c['ref']]=build_case_operations({'side':'SELL','entry':'2000','exit':exit_})
        r=review_cases(b)
        assert label in r['message']
        assert '價格上升收益' not in r['message'] and '價格下跌損失' not in r['message']


def with_observation():
    b=bundle()
    b['charts']['cases'][0]['holding_observation']=summarize(dict(status='AVAILABLE',mode='FULL_HOLDING',coverage={'scope':'WHOLE_REFERENCE_HOLDING'},
        opened_at=300,closed_at=1500,bars=[dict(time=t,open=100,high=110,low=95,close=104) for t in (300,900,1200,1500)]),'BUY',cutoff=1800)
    return b


def test_case_review_uses_anonymous_observation_tokens_and_keeps_exact_values_local(monkeypatch):
    from backend import case_review
    b=with_observation();facts=review_facts(b)
    fact=next(f for f in facts if f['id']=='history.case1')
    assert fact['values']['c1_observed_mae']=='5'
    calls=[]
    def fake(*args,**kwargs):
        calls.append(kwargs)
        return dict(status='ok',model='mock',text=json.dumps({'sections':[dict(title='持倉參考',
            text='已知K棒最大逆向{{c1_observed_mae}}%，最大順向{{c1_observed_mfe}}%。{{c1_observation_basis_state}}。',fact_ids=['history.case1'])]}))
    monkeypatch.setattr(case_review,'explain_context',fake)
    result=review_cases(b,enabled=True)
    assert result['llm_status']=='ok' and '5%' in result['message'] and '時間間隔' in result['message']
    payload=json.dumps(calls[0]['catalog'],ensure_ascii=False)
    for forbidden in ('PRIVATE','ACCOUNT_SECRET','opened_at','anchor_price','"bars"','"100"','"110"'):
        assert forbidden not in payload
    assert '{{c1_observed_mae}}' in payload


def test_model_cannot_drop_reference_basis_when_quoting_holding_metrics(monkeypatch):
    from backend import case_review
    monkeypatch.setattr(case_review,'explain_context',lambda *a,**kw:dict(status='ok',model='mock',text=json.dumps({'sections':[
        dict(title='結果',text='最大逆向{{c1_observed_mae}}%。',fact_ids=['history.case1'])]})))
    result=review_cases(with_observation(),enabled=True)
    assert result['provider']=='program' and result['llm_status']=='invalid_grounding'
    assert '已知' in result['message'] and '時間間隔' in result['message']


def test_model_basis_in_another_paragraph_does_not_cover_a_metric_claim(monkeypatch):
    from backend import case_review
    monkeypatch.setattr(case_review,'explain_context',lambda *a,**kw:dict(status='ok',model='mock',text=json.dumps({'sections':[
        dict(title='持倉過程',text='最大逆向{{c1_observed_mae}}%。\n\n其他討論。\n\n{{c1_observation_basis_state}}。',fact_ids=['history.case1'])]})))
    result=review_cases(with_observation(),enabled=True)
    assert result['provider']=='program' and result['llm_status']=='invalid_grounding'


def test_selected_case_keeps_original_tokens_and_returns_compact_sections(monkeypatch):
    from backend import case_review
    b=bundle();facts=review_facts(b,case_ref='案例乙')
    assert [f['id'] for f in facts if f['id'].startswith('history.case')]==['history.case2']
    result=review_cases(b,case_ref='案例乙')
    assert result['case_ref']=='案例乙'
    assert [s['title'] for s in result['sections']]==['相同點','重要差異','持倉過程']
    assert '案例甲' not in result['message']
    monkeypatch.setattr(case_review,'explain_context',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('no model for bad ref')))
    import pytest
    from backend.engine import DomainError
    with pytest.raises(DomainError):review_cases(b,case_ref='案例不存在',enabled=True)


def test_selected_case_preview_excludes_other_cases_and_requires_chart_identity():
    from backend.case_review import selected_charts
    from backend.engine import DomainError
    import pytest
    b=bundle();chart=selected_charts(b,'案例乙')
    assert [row['ref'] for row in chart['cases']]==['案例乙']
    assert preview(chart)['rows']==['查詢','案例乙']
    b['charts']['snapshot_id']='other'
    with pytest.raises(DomainError):selected_charts(b,'案例乙')


def test_focused_model_gets_only_selected_history_and_must_keep_three_sections(monkeypatch):
    from backend import case_review
    calls=[]
    def fake(*a,**kwargs):
        calls.append(kwargs)
        return dict(status='ok',model='mock',text=json.dumps({'sections':[
            dict(title='相同點',text='{{c2_similarities_state}}。',fact_ids=['history.case2']),
            dict(title='重要差異',text='{{c2_differences_state}}。',fact_ids=['history.case2']),
            dict(title='持倉過程',text='原單價格報酬{{c2_return}}%，未扣交易成本。',fact_ids=['history.case2'])]}))
    monkeypatch.setattr(case_review,'explain_context',fake)
    result=review_cases(bundle(),case_ref='案例乙',enabled=True)
    assert result['llm_status']=='ok' and result['case_ref']=='案例乙'
    ids=[f['id'] for f in calls[0]['catalog']['facts'] if f['id'].startswith('history.case')]
    assert ids==['history.case2']
    monkeypatch.setattr(case_review,'explain_context',lambda *a,**kw:dict(status='ok',model='mock',text=json.dumps({'sections':[dict(title='自由長文',text='比較。',fact_ids=['history.case2'])]})))
    result=review_cases(bundle(),case_ref='案例乙',enabled=True)
    assert result['provider']=='program' and result['llm_status']=='invalid_grounding'
    assert [s['title'] for s in result['sections']]==['相同點','重要差異','持倉過程']


def test_focused_vision_preflight_keeps_compact_program_sections(monkeypatch):
    from backend import case_review
    monkeypatch.setattr(case_review,'explain_context',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('no inference')))
    monkeypatch.delenv('GOLD_LLM_VISION_MODEL',raising=False)
    first=review_cases(bundle(),case_ref='案例乙',enabled=True,vision=True)
    monkeypatch.setenv('GOLD_LLM_VISION_MODEL','mock-vision')
    second=review_cases(bundle(),case_ref='案例乙',enabled=True,vision=True)
    for result,status in [(first,'vision_not_configured'),(second,'vision_insufficient_data')]:
        assert result['llm_status']==status and result['provider']=='program'
        assert [s['title'] for s in result['sections']]==['相同點','重要差異','持倉過程']
        assert result['notice'] and '案例甲' not in result['message']


def test_comparison_state_tokens_are_documented_in_writer_template():
    facts=review_facts(bundle(),case_ref='案例乙')
    fact=next(f for f in facts if f['id']=='history.case2')
    assert '{{c2_similarities_state}}' in fact['text'] and '{{c2_differences_state}}' in fact['text']
