from copy import deepcopy
from decimal import Decimal as D
import json

from backend.cases import CaseStore
from backend import market_similarity as m


def bars(n=1000):
    return [dict(time=1740960000+i*300,open=str(D(2000)+D(i)/10),
                 high=str(D(2001)+D(i)/10),low=str(D(1999)+D(i)/10),
                 close=str(D('2000.5')+D(i)/10),volume=100) for i in range(n)]


def snapshot():
    data=bars()
    result=m.snapshot(data,data[-1]['time']+300)
    result['features'].update(support_atr='1',resistance_atr='2')
    return result


def case(ident='a', verified=True, **changes):
    profile=snapshot()
    profile['alignment_status']='confirmed' if verified else 'unknown'
    result=dict(id=ident,group=ident,lot='.1',side='BUY',action='FIRST',available_at=10,
                time_alignment='confirmed' if verified else 'unknown',profit='1',
                market_profile=profile,size_profile=dict(status='READY',typical_lot='.1'))
    result.update(changes)
    return result


def store(items):
    s=CaseStore.__new__(CaseStore);s.items=items;s.source='trader_history'
    return s


def query(s):
    q=snapshot()
    return s.retrieve('BUY','FIRST',D('.1'),q['as_of']+100,typical_lot=D('.1'),query_market=q)


def test_market_snapshot_uses_closed_candles_and_is_invariant_to_future():
    data=bars();clock=data[899]['time']+300
    before=m.snapshot(data,clock)
    for b in data[900:]: b.update(high='999999',close='999998')
    assert m.snapshot(data,clock)==before
    assert all(t<=clock for t in before['latest_closed'].values())
    assert before['status']=='ready'


def test_market_features_compare_relative_price_structure_not_gold_price_level():
    data=bars();clock=data[-1]['time']+300
    scaled=deepcopy(data)
    for b in scaled:
        for key in ('open','high','low','close'): b[key]=str(D(b[key])*2)
    a,b=m.snapshot(data,clock),m.snapshot(scaled,clock)
    result=m.compare_market(a,b)
    assert result['distance']==m.compare_market(a,a)['distance']
    assert result['coverage']>=.8


def test_stale_or_short_history_cannot_be_ready():
    data=bars()
    assert m.snapshot(data[:30],data[29]['time']+300)['status']=='insufficient'
    assert m.snapshot(data,data[-1]['time']+300+7200)['status']=='insufficient'


def test_no_confirmed_cases_explicitly_returns_operation_only_not_market_matches():
    result=query(store([case(verified=False)]))
    assert result['total']==1
    assert result['comparison']['mode']=='operation_only'
    assert result['comparison']['market_matches']==0
    assert result['cases'][0]['market_comparison']['status']=='unavailable'
    assert result['cases'][0]['operation_comparison']['strength']=='weak'


def test_verified_pool_does_not_mix_unverified_or_future_market_profiles():
    a,b,c=case('a'),case('b',False),case('c')
    c['market_profile']['as_of']=snapshot()['as_of']+1000
    result=query(store([a,b,c]))
    assert [c['id'] for c in result['cases']]==['a']
    assert result['comparison']['mode']=='market_and_operation'
    assert result['comparison']['excluded_unverified_market']==2
    assert 'market_profile' not in json.dumps(result)


def test_opposite_hour_structure_abstains_instead_of_returning_same_size_case():
    item=case()
    item['market_profile']['features']['1h_ma_gap']='-9'
    result=query(store([item]))
    assert result['total']==0
    assert result['comparison']['market_matches']==0
    assert result['comparison']['mode']=='market_and_operation'
    assert result['comparison']['operation_candidates']==1
    assert result['comparison']['reason']


def test_missing_market_dimensions_have_penalty_and_cannot_look_perfect():
    a,b=snapshot(),snapshot()
    b['features']['support_atr']=None
    result=m.compare_market(a,b)
    assert result['distance']>0
    assert result['coverage']<1
    for key in ('5m_ma_gap','15m_ma_gap','1h_ma_gap'): b['features'][key]=None
    assert m.compare_market(a,b) is None


def test_profit_changes_never_change_market_ranking_or_membership():
    a,b=case('a'),case('b')
    b['market_profile']['features']['range_position']='.3'
    s=store([a,b]);before=[(c['id'],c['distance']) for c in query(s)['cases']]
    for c in s.items: c['profit']='-1000000'
    assert [(c['id'],c['distance']) for c in query(s)['cases']]==before


def test_many_verified_cases_still_disclose_unvalidated_parameters():
    result=query(store([case(str(i),independence_status='confirmed') for i in range(35)]))
    assert result['sufficiency']['status']=='limited'
    assert any('驗證' in r for r in result['sufficiency']['reasons'])


def test_snapshot_mismatched_method_is_rejected():
    a,b=snapshot(),snapshot();b['method']='unknown_version'
    assert m.compare_market(a,b) is None


def test_future_or_not_finite_features_fail_closed():
    a,b=snapshot(),snapshot();b['features']['5m_ma_gap']='NaN'
    assert m.compare_market(a,b) is None
    c=case();c['available_at']=snapshot()['as_of']+101
    assert query(store([c]))['total']==0


def test_alignment_builder_never_promotes_price_candidates():
    rows=[dict(case_id='a',timezone_status='UNKNOWN',can_use_for_market_similarity=False,
               open_utc_candidate='2025-03-06T00:00:00+00:00',evidence_status='STRONG_PRICE_CANDIDATE')]
    result=m.build_profiles([dict(id='a')],rows,bars())
    assert result['profiles']=={}
    assert result['counts']['unconfirmed']==1


def test_invalid_market_sidecar_fails_closed_without_breaking_operation_search(tmp_path,monkeypatch):
    from backend import cases as module
    folder=tmp_path/'private';folder.mkdir()
    (folder/'cases.json').write_text(json.dumps(dict(cases=[case(verified=False)])),encoding='utf-8')
    (folder/'case_market_profiles.json').write_text('{broken',encoding='utf-8')
    monkeypatch.setattr(module,'ROOT',tmp_path)
    s=CaseStore()
    assert s.market_profile_status=='INVALID'
    r=query(s)
    assert r['comparison']['mode']=='operation_only'
    assert any('停用' in reason for reason in r['limitations'])


def test_market_profile_freshness_guard_requires_three_closed_frames():
    p=snapshot();p['alignment_status']='confirmed';p['latest_closed']={}
    assert not m.valid_profile(p,p['as_of'])


def test_duplicate_alignment_decisions_are_not_silently_overwritten():
    import pytest
    with pytest.raises(ValueError):m.build_profiles([dict(id='a')],[dict(case_id='a'),dict(case_id='a')],bars())


def test_confirmed_timezone_without_market_clock_evidence_does_not_enable_features():
    row=dict(case_id='a',timezone_status='CONFIRMED',can_use_for_market_similarity=True,evidence_ref='review',
             open_utc='2025-03-06T00:00:00+00:00')
    assert m.build_profiles([dict(id='a')],[row],bars())['profiles']=={}


def test_invalid_ohlc_is_not_a_valid_market_snapshot():
    data=bars();data[-1]['high']='1'
    assert m.snapshot(data,data[-1]['time']+300)['status']=='insufficient'


def test_hash_bound_profiles_disable_when_alignment_evidence_changes(tmp_path):
    import hashlib
    folder=tmp_path/'private';folder.mkdir()
    def put(name,data):
        p=folder/name;p.write_text(json.dumps(data),encoding='utf-8');return p
    cp=put('cases.json',dict(cases=[]));bp=put('bars.json',dict(bars=[]));ap=put('alignment.json',dict(cases=[]))
    ep=put('evidence.json',dict(reviewed=True))
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    sp=put('case_market_profiles.json',dict(method=m.METHOD,input_cases_sha256=sha(cp),profiles={'a':snapshot()},
            inputs={k:dict(path=p.name,sha256=sha(p)) for k,p in [('bars',bp),('alignment',ap),('evidence_0',ep)]}))
    assert m.load_sidecar(cp,sp,folder)[1]=='READY'
    ep.write_text('{}',encoding='utf-8')
    assert m.load_sidecar(cp,sp,folder)==({},'STALE')


def test_grounded_chat_receives_market_axes_without_raw_profile_or_private_evidence(monkeypatch):
    from backend.tests.test_assistant_context import synthetic_engine
    from backend.assistant import build_context
    from backend.evidence import build_catalog
    e=synthetic_engine(monkeypatch);e.bars=bars();e.cursor=len(e.bars)
    item=case();item.update(source_kind='trader_history',currency='USD',entry='1',exit='2')
    e.cases.items=[item];e.cases.source='trader_history'
    context=build_context(e,side='BUY',lot='.1',typical_lot='.1')
    assert context['historical_reference']['comparison']['mode']=='market_and_operation'
    facts=build_catalog(context)['sections']['history']['facts']
    assert any('操作＋已核實盤面' in f['text'] for f in facts)
    assert 'market_profile' not in json.dumps(context)


def test_synthetic_market_acceptance_mode_has_no_contradictory_unavailable_claim():
    s=store([case()]);s.source='synthetic_demo'
    result=query(s)
    assert result['comparison']['mode']=='market_and_operation'
    assert not any('尚未啟用' in r for r in result['limitations'])
