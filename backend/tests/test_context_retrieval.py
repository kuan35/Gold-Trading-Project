from copy import deepcopy
from decimal import Decimal

import pytest

from backend.dual_path_retrieval import profile_from_dual_frames
from backend.tests.test_dual_path_retrieval import candles, CLOCK
from backend.cases import CaseStore


def profile(clock=CLOCK):
    return profile_from_dual_frames(candles(300,61,clock),candles(3600,20,clock),clock)


def store():
    s=CaseStore.__new__(CaseStore)
    s.source='trader_history';s.candidate_profile_status='READY'
    s.items=[dict(id='a',group='g',side='BUY',available_at=CLOCK-100,profit='10',lot='.1',action='FIRST'),
             dict(id='b',group='h',side='BUY',available_at=CLOCK-100,profit='-5',lot='8',action='ADD'),
             dict(id='future',group='f',side='BUY',available_at=CLOCK+1,profit='3'),
             dict(id='sell',group='s',side='SELL',available_at=CLOCK-100,profit='3')]
    s.candidate_profiles={c['id']:profile(CLOCK-72*3600) for c in s.items}
    return s


def retrieve(s,query=None,**kw):
    return s.retrieve('BUY','FIRST',Decimal('.1'),CLOCK,query_candidate=query or profile(),**kw)


def test_private_default_uses_context_rules_and_deduplicates():
    r=retrieve(store())
    assert r['comparison']['method']=='context_contract_v1'
    assert [c['id'] for c in r['cases']]==['a']
    assert r['rule_status']=='PASSED'
    assert r['total']==1 and r['wins']==1
    assert r['cases'][0]['context_check']['passed'] is True
    assert r['comparison']['thresholds']==dict(d5=.25,d1h=.5,dtail=.12,vol_ratio=2.)
    assert r['comparison']['parameters_validated'] is False


def test_no_rule_match_is_distinct_from_missing_data_and_never_falls_back():
    s=store()
    for p in s.candidate_profiles.values():p['indicators']['5m_atr_pct']='50'
    r=retrieve(s)
    assert r['cases']==[] and r['total']==0 and r['rule_status']=='NO_RULE_MATCH'
    assert r['comparison']['rejections']['volatility']==2
    assert r['candidate_market_unavailable_reason'] is None
    s=store();s.candidate_profile_status='MISSING'
    missing=retrieve(s)
    assert missing['rule_status']=='INSUFFICIENT_DATA'
    assert missing['comparison']['method']=='context_contract_v1'
    assert missing['candidate_market_unavailable_reason']


def test_rules_ignore_outcome_size_action_and_fail_when_query_has_no_hour():
    a=retrieve(store());s=store()
    s.items=[dict(c,lot='99',action='ADD',profit='-999') for c in reversed(s.items)]
    b=retrieve(s)
    assert [c['id'] for c in a['cases']]==[c['id'] for c in b['cases']]
    q=profile();q['pre_entry_bars']['1h']=[]
    assert retrieve(store(),q)['rule_status']=='INSUFFICIENT_DATA'


def test_context_method_without_private_history_preserves_method():
    s=CaseStore.__new__(CaseStore);s.source='synthetic_demo'
    r=retrieve(s,retrieval_method='context_contract_v1')
    assert r['rule_status']=='INSUFFICIENT_DATA' and r['cases']==[]
    assert r['comparison']['method']=='context_contract_v1'


def test_live_api_defaults_and_demo_draft_use_the_same_context_method(monkeypatch):
    import importlib
    from datetime import datetime,timezone
    from threading import RLock
    from types import SimpleNamespace
    app=importlib.import_module('backend.app');calls=[]
    class Store:
        def retrieve(self,*args,**kwargs):
            calls.append(kwargs);return {'comparison':{'method':kwargs['retrieval_method']}}
    monkeypatch.setattr(app,'engine',SimpleNamespace(lock=RLock(),cases=Store()))
    snap=dict(connection_status='CONNECTED',quote=dict(status='CURRENT',source_time_utc=datetime.fromtimestamp(CLOCK+12,timezone.utc).isoformat()),
              bars={'5m':candles(300,61),'1h':candles(3600,20)})
    r,q=app._live_retrieval(snap,'BUY')
    assert q['status']=='candidate_only' and r['comparison']['method']=='context_contract_v1'
    assert r['query_source']=='ctrader_demo_xauusd' and r['query_as_of_utc']==CLOCK
    assert app.BrokerDraftInput(side='BUY',lot='.1').retrieval_method=='context_contract_v1'
    snap['quote']['status']='STALE'
    r,q=app._live_retrieval(snap,'BUY')
    assert r['rule_status']=='INSUFFICIENT_DATA' and len(calls)==1


def test_invalid_direction_cannot_produce_passed_cases():
    from backend.context_retrieval import ContextIndex
    s=store()
    r=ContextIndex(s.items,s.candidate_profiles).retrieve(profile(),'HOLD')
    assert r['rule_status']=='INSUFFICIENT_DATA' and not r['cases']


@pytest.mark.parametrize('missing',[False,True])
def test_assistant_explains_context_decision_without_old_indicator_rank_or_identifiers(monkeypatch,missing):
    from backend.tests.test_assistant_context import synthetic_engine
    from backend import assistant
    from backend.evidence import build_catalog
    e=synthetic_engine(monkeypatch)
    r=retrieve(store())
    if missing:
        s=store();s.candidate_profile_status='MISSING';r=retrieve(s)
    monkeypatch.setattr(e,'retrieve',lambda *a,**kw:r)
    context=assistant.build_context(e,side='BUY',lot='.1')
    h=context['historical_reference']
    assert h['method']=='context_contract_v1' and h['rule_status']==r['rule_status']
    catalog=build_catalog(context)
    import json
    encoded=json.dumps(catalog,ensure_ascii=False)
    assert '前15' not in encoded and '指標池內' not in encoded
    assert '不能解讀為 K 線型態相似' not in encoded
    assert ('資料不足' in encoded) if missing else ('容忍' in encoded and '半小時' in encoded)
    assert all('id' not in c for c in h['cases'])


def test_live_route_does_not_overwrite_missing_history_with_ready_market_status(monkeypatch):
    import importlib,json
    from threading import RLock
    from types import SimpleNamespace
    from datetime import datetime,timezone
    app=importlib.import_module('backend.app')
    s=store();s.candidate_profile_status='MISSING'
    monkeypatch.setattr(app,'engine',SimpleNamespace(lock=RLock(),cases=s))
    snap=dict(connection_status='CONNECTED',quote=dict(status='CURRENT',source_time_utc=datetime.fromtimestamp(CLOCK+12,timezone.utc).isoformat()),
              bars={'5m':candles(300,61),'1h':candles(3600,20)})
    monkeypatch.setattr(app,'demo_market_stream',SimpleNamespace(query_snapshot=lambda:snap))
    request=SimpleNamespace(client=SimpleNamespace(host='127.0.0.1'),headers={'host':'127.0.0.1:8765'},url=SimpleNamespace(hostname='127.0.0.1'))
    response=app.broker_demo_cases(request,'BUY','context_contract_v1')
    result=json.loads(response.body)
    assert result['query_status']=='insufficient' and result['rule_status']=='INSUFFICIENT_DATA'
    assert result['query_reason']
