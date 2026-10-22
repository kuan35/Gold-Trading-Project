import importlib
from datetime import datetime,timezone
from types import SimpleNamespace
from fastapi.testclient import TestClient
from backend.analysis_snapshots import SnapshotStore
from backend.tests.test_case_context import retrieval

app=importlib.import_module('backend.app')


def market():
    now=datetime.now(timezone.utc).timestamp()
    def bars(span):
        end=int(now)//span*span
        return [dict(time=end-(120-i)*span,open=4000+i,high=4002+i,low=3999+i,close=4001+i,volume=100) for i in range(120)]
    return dict(connection_status='CONNECTED',quote=dict(status='CURRENT',bid='4120.00',ask='4120.20',age_seconds=0,
        source_time_utc=datetime.fromtimestamp(now,timezone.utc).isoformat()),bars={i:bars(s) for i,s in [('5m',300),('15m',900),('1h',3600)]},account={'secret':'ACCOUNT_SECRET'})


def setup(monkeypatch):
    s=market();calls=[]
    monkeypatch.setattr(app,'analysis_snapshots',SnapshotStore())
    monkeypatch.setattr(app.demo_market_stream,'query_snapshot',lambda:(calls.append('market') or s))
    def retrieve(snapshot,side,*a):
        assert snapshot is s;calls.append('retrieve')
        r=retrieval();r.update(query_side=side)
        q=dict(as_of=int(datetime.now(timezone.utc).timestamp())//300*300,pre_entry_bars=s['bars'])
        return r,q
    monkeypatch.setattr(app,'_live_retrieval',retrieve)
    return s,calls,TestClient(app.app)


def test_live_chat_captures_once_and_returns_whitelisted_case_explanation_and_frozen_charts(monkeypatch):
    s,calls,c=setup(monkeypatch)
    r=c.post('/api/assistant/live-chat',json={'message':'有哪些相似案例？','side':'BUY'}).json()
    assert calls==['market','retrieve']
    assert r['case_comparison']['status']=='PASSED' and r['snapshot_id']
    assert '差距' in r['message'] and '容忍' in r['message']
    sid=r['snapshot_id'];s['bars']['5m'][-1]['close']=9999
    charts=c.get('/api/assistant/snapshots/'+sid+'/charts')
    assert charts.headers['cache-control']=='no-store'
    assert charts.json()['query']['5m'][-1]['close']==4120
    assert 'ACCOUNT_SECRET' not in charts.text and 'ACCOUNT_SECRET' not in str(r)
    assert TestClient(app.app,base_url='http://public.example').get('/api/assistant/snapshots/'+sid+'/charts').status_code==403


def test_draft_explanation_reuses_exact_analysis_without_another_market_read_or_retrieval(monkeypatch):
    s,calls,c=setup(monkeypatch)
    monkeypatch.setattr(app,'broker_orders',SimpleNamespace(create=lambda snapshot,**kw:{'id':'saved-draft','side':kw['side']}))
    d=c.post('/api/broker/drafts',json={'side':'BUY','lot':'.1'}).json()
    assert d['analysis_snapshot_id'] and calls==['market','retrieve']
    monkeypatch.setattr(app.demo_market_stream,'query_snapshot',lambda:(_ for _ in ()).throw(AssertionError('must not refresh')))
    monkeypatch.setattr(app,'_live_retrieval',lambda *a:(_ for _ in ()).throw(AssertionError('must not rerank')))
    r=c.post('/api/assistant/draft-chat',json={'draft_id':'saved-draft','message':'這筆草稿案例相似在哪？'}).json()
    assert r['snapshot_id']==d['analysis_snapshot_id'] and r['as_of_utc']==d['analysis_as_of_utc']
    assert r['analysis_mode']=='draft_snapshot' and r['market_status']=='FROZEN' and r['draft'] is None
    assert c.post('/api/assistant/draft-chat',json={'draft_id':'missing','message':'解釋'}).status_code==409
    assert c.post('/api/assistant/draft-chat',json={'draft_id':'saved-draft','message':'解釋','confirmed':True}).status_code==422


def test_stale_market_never_retrieves_or_calls_external_model(monkeypatch):
    s,calls,c=setup(monkeypatch);s['quote']['age_seconds']=10
    monkeypatch.setattr(app,'_live_retrieval',lambda *a:(_ for _ in ()).throw(AssertionError('stale')))
    r=c.post('/api/assistant/live-chat',json={'message':'相似案例','llm_enabled':True}).json()
    assert r['llm_status']=='market_unavailable' and r['case_comparison']['status']=='INSUFFICIENT_DATA'


def test_acceptance_gallery_exposes_only_local_html_and_named_charts(monkeypatch,tmp_path):
    # A clean clone has no private QA gallery. Exercise the real route with
    # temporary synthetic files instead of depending on the developer's data.
    gallery=tmp_path/'private'/'assistant_case_acceptance_20261022'
    gallery.mkdir(parents=True)
    (gallery/'index.html').write_text('<html>Synthetic gallery fixture</html>',encoding='utf-8')
    (gallery/'D01_2026-08-11.png').write_bytes(b'\x89PNG\r\n\x1a\n')
    for name in ['results_PRIVATE.json','manifest_PRIVATE.json','comparison.csv','unlisted.png']:
        (gallery/name).write_text('synthetic private fixture',encoding='utf-8')
    monkeypatch.setattr(app,'ROOT',tmp_path)
    c=TestClient(app.app)
    page=c.get('/api/assistant/acceptance/index.html')
    assert page.status_code==200 and page.headers['cache-control']=='no-store'
    assert c.get('/api/assistant/acceptance/D01_2026-08-11.png').headers['content-type']=='image/png'
    for name in ['results_PRIVATE.json','manifest_PRIVATE.json','comparison.csv','unlisted.png']:
        assert c.get('/api/assistant/acceptance/'+name).status_code==404
    assert TestClient(app.app,base_url='http://public.example').get('/api/assistant/acceptance/index.html').status_code==403
    (gallery/'index.html').unlink()
    assert c.get('/api/assistant/acceptance/index.html').status_code==404


def test_two_passed_cases_keep_both_explanations_and_only_pre_entry_chart_windows():
    from copy import deepcopy
    from backend.case_analysis import prepare_analysis
    from backend.live_assistant import respond_context
    s=market();end=int(datetime.now(timezone.utc).timestamp())//3600*3600
    q=dict(as_of=end,pre_entry_bars=s['bars'])
    r=retrieval();second=deepcopy(r['cases'][0]);second['id']='OTHER_PRIVATE';r['cases'].append(second)
    profiles={}
    for case in r['cases']:
        old=deepcopy(q);old['as_of']-=7*86400
        for rows in old['pre_entry_bars'].values():
            for bar in rows:bar['time']-=7*86400
        profiles[case['id']]=old
    bundle=prepare_analysis(s,'BUY',r,q,profiles=profiles)
    answer=respond_context(bundle['context'],'解釋盤面與案例差異')
    assert '案例甲' in answer['message'] and '案例乙' in answer['message']
    assert all(secret not in answer['message'] for secret in ['PRIVATE_CASE','OTHER_PRIVATE','ACCOUNT_SECRET'])
    assert len(bundle['charts']['cases'])==2
    for chart in bundle['charts']['cases']:
        assert len(chart['5m'])==60 and len(chart['1h'])==20
        for iv,span in [('5m',300),('1h',3600)]:
            assert all(b['time']+span<=chart['as_of_utc'] for b in chart[iv])
