from copy import deepcopy
from backend.context_retrieval import ContextIndex
from backend.tick_volume import tick_frame,NativeTickStore
from backend.tests.test_context_retrieval import profile,CLOCK
from backend.tests.test_tick_volume import bars,KEY


class Volumes:
    def reference(self,ident,p):
        q=tick_frame(bars(),6600,KEY)
        return dict(q,relative_volume_ratio={'a':'.5','b':'1','c':'2'}[ident])


def fixture():
    cases=[dict(id=i,group='g' if i in 'ab' else 'h',side='BUY',available_at=CLOCK-100,profit='-1' if i=='b' else '2') for i in 'abc']
    profiles={i:profile(CLOCK-(72+n)*3600) for n,i in enumerate('abc')}
    query=profile();query['tick_volume']=tick_frame(bars(),6600,KEY)
    return cases,profiles,query


def test_tick_filter_runs_before_dedupe_and_recomputes_entire_result_pool():
    cases,profiles,q=fixture();index=ContextIndex(cases,profiles,tick_volume_store=Volumes())
    result=index.retrieve(q,'BUY')
    assert [c['id'] for c in result['cases']]==['b','c']
    assert result['total']==2 and result['losses']==1 and result['wins']==1
    assert result['comparison']['tick_volume']['enabled'] is True
    assert result['comparison']['rejections']['tick_volume_ratio']==1
    assert result['cases'][0]['tick_comparison']['multiplier']=='2'
    assert result['comparison']['context_passed_rows']==3
    assert KEY not in str(result)


def test_missing_tick_query_is_insufficient_and_does_not_return_old_neighbors():
    cases,profiles,q=fixture();q.pop('tick_volume')
    r=ContextIndex(cases,profiles,tick_volume_store=Volumes()).retrieve(q,'BUY')
    assert r['rule_status']=='INSUFFICIENT_DATA' and r['total']==0 and not r['cases']
    assert r['comparison']['tick_volume']['query_reason']=='QUERY_VOLUME_UNAVAILABLE'
    # Frozen direct research baseline is still explicitly volume-free.
    baseline=ContextIndex(cases,profiles).retrieve(q,'BUY')
    assert baseline['rule_status']=='PASSED' and baseline['comparison']['tick_volume']['enabled'] is False


def test_missing_native_index_cannot_silently_disable_default_product_gate(tmp_path,monkeypatch):
    from backend import cases as module
    monkeypatch.setattr(module,'ROOT',tmp_path)
    product=module.CaseStore()
    assert isinstance(product.tick_volume_store,NativeTickStore)
    cases,profiles,q=fixture()
    r=ContextIndex(cases,profiles,tick_volume_store=product.tick_volume_store).retrieve(q,'BUY')
    assert r['total']==0 and r['comparison']['rejections']['tick_volume_unavailable']==3


def test_live_query_binds_native_volume_source_but_public_snapshot_does_not(monkeypatch):
    import importlib
    from datetime import datetime,timezone
    from threading import RLock
    from types import SimpleNamespace
    from backend.demo_market_stream import DemoMarketStream
    app=importlib.import_module('backend.app');seen=[]
    store=SimpleNamespace(retrieve=lambda *a,**kw:(seen.append(kw['query_candidate']) or {'comparison':{'method':'context_contract_v1'}}))
    monkeypatch.setattr(app,'engine',SimpleNamespace(lock=RLock(),cases=store))
    from backend.tests.test_dual_path_retrieval import candles
    p=profile();five=candles(300,61)
    for row in five:row['volume']=100
    snapshot=dict(connection_status='CONNECTED',quote={'status':'CURRENT','source_time_utc':datetime.fromtimestamp(CLOCK+5,timezone.utc).isoformat()},
        bars={'5m':five,'1h':p['pre_entry_bars']['1h']},tick_volume_source_key=KEY)
    app._live_retrieval(snapshot,'BUY')
    assert seen[0]['tick_volume']['relative_volume_ratio']=='1'
    stream=DemoMarketStream();stream._start=lambda:None;stream._tick_volume_source_key=KEY
    assert stream.query_snapshot()['tick_volume_source_key']==KEY
    assert 'tick_volume_source_key' not in stream.snapshot()


def test_no_result_with_some_unknown_volume_is_insufficient_not_a_negative_match():
    from backend.case_context import build_case_context
    class Mixed(Volumes):
        def reference(self,ident,p):
            return super().reference(ident,p) if ident=='a' else dict(status='UNAVAILABLE',reason='GAPPED_BASELINE')
    cases,profiles,q=fixture()
    r=ContextIndex(cases,profiles,tick_volume_store=Mixed()).retrieve(q,'BUY')
    assert r['rule_status']=='INSUFFICIENT_DATA'
    assert r['comparison']['rejections']=={'tick_volume_ratio':1,'tick_volume_unavailable':2}
    assert build_case_context(r)['distribution']['total'] is None
    class TooDifferent(Volumes):
        def reference(self,ident,p):return super().reference('a',p)
    r=ContextIndex(cases,profiles,tick_volume_store=TooDifferent()).retrieve(q,'BUY')
    assert r['rule_status']=='NO_RULE_MATCH'


def test_live_readonly_api_keeps_bars_but_never_exposes_private_volume_source(monkeypatch):
    import importlib
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    app=importlib.import_module('backend.app')
    monkeypatch.setattr(app,'live_readonly_stream',SimpleNamespace(query_snapshot=lambda:dict(source='ctrader_live_xauusd',read_only=True,
        tick_volume_source_key=KEY,bars={'5m':[dict(time=300)]})))
    response=TestClient(app.app).get('/api/live-readonly')
    assert response.status_code==200 and response.json()['bars']['5m'][0]['time']==300
    assert KEY not in response.text and 'tick_volume_source_key' not in response.json()
