from decimal import Decimal
import pytest
from backend.personal_rules import evaluate_rules, validate_rules, is_rule_message

def rule(kind='order_lot', value='0.1', op='gt', **kw):
    return dict(id='r1', kind=kind, value=value, op=op, enabled=True, side='ANY', **kw)

def test_decimal_boundary_and_disabled():
    draft={'side':'BUY','lot':'0.10','sl':None,'risk':{'after_lot':'0.30','stop_loss_usd':None}}
    state={'positions':[]}
    assert evaluate_rules([rule()],state,draft)['results'][0]['status']=='clear'
    assert evaluate_rules([rule(op='gte')],state,draft)['results'][0]['status']=='triggered'
    off=rule();off['enabled']=False
    assert evaluate_rules([off],state,draft)['results']==[]

def test_missing_values_remain_unknown():
    state={'positions':[]}
    assert evaluate_rules([rule()],state,None)['results'][0]['status']=='unknown'
    draft={'side':'BUY','lot':'.2','sl':None,'risk':{'after_lot':'.2','stop_loss_usd':None}}
    assert evaluate_rules([rule('stop_loss_usd','100')],state,draft)['results'][0]['status']=='unknown'
    assert evaluate_rules([rule('missing_sl',None,'is')],state,draft)['results'][0]['status']=='triggered'

def test_same_direction_existing_count_and_market():
    state={'positions':[{'side':'BUY'},{'side':'BUY'},{'side':'SELL'}]}
    draft={'side':'BUY','lot':'.2','sl':None,'risk':{}}
    assert evaluate_rules([rule('same_side_count','2','gte')],state,draft)['results'][0]['actual']=='2'
    r=rule('market_bias','bearish','is');r['side']='BUY'
    assert evaluate_rules([r],state,draft,{'bias':'bearish_rebound','label':'空方結構中的反彈'})['results'][0]['status']=='clear'
    assert evaluate_rules([r],state,draft,{'bias':'bearish','label':'短線偏空'})['results'][0]['status']=='triggered'

@pytest.mark.parametrize('value',['NaN','Infinity','0','-1','abc'])
def test_invalid_threshold_rejected(value):
    with pytest.raises(ValueError):validate_rules([rule(value=value)])

def test_duplicates_fractional_count_and_unknown_keys_rejected():
    for rules in ([rule(),rule()], [rule('same_side_count','1.5')], [dict(rule(),execute=True)]):
        with pytest.raises(ValueError):validate_rules(rules)

def test_rule_and_hypothetical_are_not_order_intent():
    assert is_rule_message('以後買進超過0.1手提醒我')
    assert is_rule_message('如果買進0.2手會怎麼樣')
    assert is_rule_message('不要買進0.2手')
    assert not is_rule_message('買進0.2手')

def test_chat_settings_do_not_create_draft(monkeypatch):
    from backend.assistant import respond
    from backend.engine import Engine
    monkeypatch.setenv('GOLD_ENABLE_LLM','false')
    engine=Engine()
    result=respond(engine,'以後買進超過0.1手提醒我')
    assert result['draft'] is None
    assert not engine.drafts and not engine.orders

def test_api_rules_check_and_changed_snapshot_require_new_draft(monkeypatch):
    from fastapi.testclient import TestClient
    from backend import app as api
    from backend.engine import Engine
    monkeypatch.setattr(api,'engine',Engine())
    monkeypatch.setenv('GOLD_ENABLE_LLM','false')
    client=TestClient(api.app)
    payload={'side':'BUY','lot':'0.20','personal_rules':[rule()]}
    draft=client.post('/api/drafts',json=payload).json()
    assert draft['personal_rules']['results'][0]['status']=='triggered'
    changed=client.post('/api/drafts/'+draft['id']+'/confirm',json={'revision':draft['revision'],'idempotency_key':'changed','personal_rules':[]})
    assert changed.status_code==409
    assert not api.engine.orders
    good=client.post('/api/drafts/'+draft['id']+'/confirm',json={'revision':draft['revision'],'idempotency_key':'good','personal_rules':[rule()]})
    assert good.status_code==200
    assert len(api.engine.orders)==1
