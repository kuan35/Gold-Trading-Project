from copy import deepcopy
from datetime import datetime,timezone
from decimal import Decimal

import pytest

from backend.dual_path_retrieval import DualPathIndex, profile_from_dual_frames, profile_from_live_dual_snapshot
from backend.compact_market import describe_compact

CLOCK=1800000000


def candles(seconds,count,clock=CLOCK):
    return [dict(time=clock-(count-i)*seconds,open=str(2500+i*.02),high=str(2501+i*.02),
                 low=str(2499+i*.02),close=str(2500.1+i*.02)) for i in range(count)]


def profile(clock=CLOCK):
    return profile_from_dual_frames(candles(300,61,clock),candles(3600,20,clock),clock)


def test_live_dual_requires_only_five_and_hour_and_closed_bars():
    snap=dict(connection_status='CONNECTED',quote=dict(status='CURRENT',source_time_utc=datetime.fromtimestamp(CLOCK+12,timezone.utc).isoformat()),
              bars={'5m':candles(300,61),'1h':candles(3600,20)})
    query=profile_from_live_dual_snapshot(snap)
    assert query['status']=='candidate_only' and query['as_of']==CLOCK
    assert set(query['pre_entry_bars'])=={'5m','1h'}
    assert len(query['pre_entry_bars']['5m'])==60
    assert describe_compact(query,'BUY')['end_1h']==CLOCK
    snap['quote']['status']='STALE'
    assert profile_from_live_dual_snapshot(snap)['status']=='insufficient'


def test_dual_rejects_future_and_open_session_gaps():
    five=candles(300,61);hour=candles(3600,20)
    five[-1]['time']=CLOCK
    assert profile_from_dual_frames(five,hour,CLOCK)['status']=='insufficient'
    five=candles(300,62);five.pop(-10)
    assert profile_from_dual_frames(five,hour,CLOCK)['status']=='insufficient'


def setup_index():
    old_clock=CLOCK-72*3600
    cases=[dict(id=i,group=g,side=s,available_at=available,profit='5',lot='0.1',action='FIRST',
                label=i,source_kind='trader_history',time_alignment='unknown')
           for i,g,s,available in [('A','a','BUY',CLOCK-1000),('B','b','BUY',CLOCK-1000),
                                    ('duplicate','b','BUY',CLOCK-1000),('future','f','BUY',CLOCK+1),
                                    ('sell','s','SELL',CLOCK-1000),('overlap','o','BUY',CLOCK-1)]]
    profiles={c['id']:profile(old_clock) for c in cases}
    profiles['overlap']=profile(CLOCK-3600)
    return cases,profiles


def test_rank_excludes_immature_opposite_overlapping_and_duplicate_windows():
    cases,profiles=setup_index()
    result=DualPathIndex(cases,profiles).retrieve(profile(), 'BUY')
    assert [c['id'] for c in result['cases']]==['A']
    assert result['comparison']['method']=='dual_path_structure_v1'
    assert result['similarity_sufficiency']=='UNCALIBRATED'
    assert result['cases'][0]['structure_match'] is True
    assert result['cases'][0]['hour_path_distance_pct']==pytest.approx(0)
    changed=[dict(c,profit='-99999',lot='99',action='ADD') for c in reversed(cases)]
    again=DualPathIndex(changed,profiles).retrieve(profile(),'BUY')
    assert [(c['id'],c['path_distance_pct'],c['hour_path_rank']) for c in again['cases']]==[(c['id'],c['path_distance_pct'],c['hour_path_rank']) for c in result['cases']]


def test_no_history_or_invalid_query_does_not_fallback_or_claim_match():
    result=DualPathIndex([],{}).retrieve(profile(),'BUY')
    assert result['cases']==[] and result['similarity_sufficiency']=='NO_MATCH'
    bad=profile();bad['pre_entry_bars']['1h']=[]
    result=DualPathIndex([],{}).retrieve(bad,'BUY')
    assert result['query_status']=='insufficient' and result['cases']==[]


@pytest.mark.parametrize('method',['dual_path_structure_v1','path_indicator_pattern_v1'])
def test_live_method_without_private_history_fails_closed(method):
    from backend.cases import CaseStore
    store=CaseStore.__new__(CaseStore)
    store.source='synthetic_demo'
    result=store.retrieve('BUY','FIRST',Decimal('.1'),CLOCK,
                          query_candidate=profile(),retrieval_method=method)
    assert result['cases']==[] and result['similarity_sufficiency']=='NO_MATCH'
    assert result['comparison']['method']==method


def test_new_method_preserved_when_private_sidecar_missing():
    from backend.cases import CaseStore
    store=CaseStore.__new__(CaseStore)
    store.source='trader_history';store.candidate_profile_status='MISSING'
    result=store.retrieve('BUY','FIRST',Decimal('.1'),CLOCK,
                          query_candidate=profile(),retrieval_method='dual_path_structure_v1')
    assert result['cases']==[] and result['comparison']['method']=='dual_path_structure_v1'


def test_same_structure_wins_even_when_other_structure_has_smaller_path_distance():
    cases,profiles=setup_index();cases=cases[:2]
    for iv in ('5m','1h'):
        for b in profiles['B']['pre_entry_bars'][iv]:b['time']-=3600
    profiles['B']['as_of']-=3600
    for b in profiles['A']['pre_entry_bars']['5m'][:40]:b['close']=str(Decimal(b['close'])-Decimal('.5'))
    last=profiles['B']['pre_entry_bars']['5m'][-1]
    high=max(Decimal(b['high']) for b in profiles['B']['pre_entry_bars']['5m'][-21:-1])
    last.update(close=str(high+Decimal('.01')),high=str(high+Decimal('.02')))
    result=DualPathIndex(cases,profiles).retrieve(profile(),'BUY')
    assert [c['id'] for c in result['cases']]==['A','B']
    assert result['cases'][0]['structure_match'] is True
    assert result['cases'][1]['structure_match'] is False
    assert result['cases'][0]['path_distance_pct']>result['cases'][1]['path_distance_pct']


def test_live_api_routes_selected_method_without_order_side_effect(monkeypatch):
    import importlib
    from threading import RLock
    from types import SimpleNamespace
    app_module=importlib.import_module('backend.app')
    calls=[]
    class Store:
        def retrieve(self,*args,**kwargs):
            calls.append(kwargs)
            return {'comparison':{'method':kwargs['retrieval_method']}}
    monkeypatch.setattr(app_module,'engine',SimpleNamespace(lock=RLock(),cases=Store()))
    snapshot=dict(connection_status='CONNECTED',quote=dict(status='CURRENT',source_time_utc=datetime.fromtimestamp(CLOCK+12,timezone.utc).isoformat()),
                  bars={'5m':candles(300,61),'1h':candles(3600,20)})
    result,query=app_module._live_retrieval(snapshot,'BUY','dual_path_structure_v1')
    assert query['status']=='candidate_only' and calls[0]['retrieval_method']=='dual_path_structure_v1'
    assert result['comparison']['method']=='dual_path_structure_v1'
    result,query=app_module._live_retrieval(snapshot,'BUY','path_indicator_pattern_v1')
    assert query['status']=='insufficient' and len(calls)==1
    snapshot['quote']['status']='STALE'
    result,query=app_module._live_retrieval(snapshot,'BUY','dual_path_structure_v1')
    assert query['status']=='insufficient' and len(calls)==1
    assert result['comparison']['method']=='dual_path_structure_v1'


def test_structure_priority_precedes_distance_and_matches_frozen_offline_order():
    np=pytest.importorskip('numpy')
    from research.path_similarity_experiment import order_candidates
    cases,profiles=setup_index();cases=cases[:3]
    query=profile()
    for offset,c in enumerate(cases):
        p=profiles[c['id']]
        for interval in ('5m','1h'):
            for j,b in enumerate(p['pre_entry_bars'][interval]):
                if j==len(p['pre_entry_bars'][interval])-1:continue
                b['close']=str(Decimal(b['close'])+Decimal(offset)/10)
    index=DualPathIndex(cases,profiles)
    result=index.retrieve(query,'BUY')
    q=describe_compact(query,'BUY')
    pool=index.eligible(query,'BUY')[0]
    def distance(c,iv):
        a=query['pre_entry_bars'][iv];b=profiles[c['id']]['pre_entry_bars'][iv]
        ap=np.array([float(x['close'])/float(a[0]['close'])*100-100 for x in a])
        bp=np.array([float(x['close'])/float(b[0]['close'])*100-100 for x in b])
        return float(np.sqrt(np.mean((ap-bp)**2)))
    expected=order_candidates(pool,index.descriptions,q,np.array([distance(c,'5m') for c in pool]),
                               np.array([distance(c,'1h') for c in pool]),structure_first=True)
    assert [c['id'] for c in result['cases']]==[c['case_id'] for c in expected]
