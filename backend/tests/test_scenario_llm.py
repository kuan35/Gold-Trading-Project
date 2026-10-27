import json
from backend import live_assistant
from backend.tests.test_case_scenarios import bundle

def test_llm_explains_program_values_with_tokens_and_receives_no_raw_scenario_data(monkeypatch):
    calls=[]
    def explain(*args,**kw):
        calls.append(kw['catalog'])
        return dict(status='ok',model='test',text=json.dumps(dict(sections=[
            dict(title='歷史情境',text='案例甲後續{{future_minutes}}分鐘的最大逆向為{{future_mae}}%；套入本筆後，未退出的最大情境損失{{future_loss}} USD。',fact_ids=['history.outcome']),
            dict(title='草稿風險',text='停損距離對應的名目損失為{{draft_stop_loss}} USD；歷史情境不是未來預測。',fact_ids=['draft.risk'])])))
    monkeypatch.setattr(live_assistant,'explain_context',explain)
    r=live_assistant.respond_context(bundle()['context'],'後續情境與停損風險',enabled=True)
    assert r['llm_status']=='ok' and r['provider']=='groq_market_analysis'
    assert '200.00 USD' in r['message'] and '100.00 USD' in r['message']
    sent=json.dumps(calls,ensure_ascii=False)
    for secret in ('200.00','100.00','1990','PRIVATE_CASE','PRIVATE_GROUP','ACCOUNT_SECRET','anchor_price','bars'):
        assert secret not in sent
    assert len(calls)==1

def test_invented_scenario_number_is_rejected_without_provider_retry(monkeypatch):
    calls=[]
    def bad(*args,**kw):
        calls.append(1)
        return dict(status='ok',model='test',text=json.dumps(dict(sections=[dict(title='風險',text='一定只會損失777美元。',fact_ids=['draft.risk'])])))
    monkeypatch.setattr(live_assistant,'explain_context',bad)
    r=live_assistant.respond_context(bundle()['context'],'後續風險',enabled=True)
    assert r['provider']=='local_market_rules' and '777' not in r['message'] and len(calls)==1

def test_all_periods_two_cases_and_draft_keep_program_fallback_available(monkeypatch):
    from copy import deepcopy
    from backend.tests.test_case_context import retrieval
    source=retrieval();second=deepcopy(source['cases'][0]);second['id']='ANOTHER_CASE';source['cases'].append(second)
    b=bundle(source)
    monkeypatch.setattr(live_assistant,'explain_context',lambda *a,**kw:dict(status='rate_limited',model='test'))
    for enabled in (False,True):
        r=live_assistant.respond_context(b['context'],'五分鐘、十五分鐘與一小時走勢有沒有衝突？',enabled=enabled)
        assert r['provider']=='local_market_rules' and len(r['sections'])>=9
        assert '100.00' in r['message'] and '案例乙' in r['message']
