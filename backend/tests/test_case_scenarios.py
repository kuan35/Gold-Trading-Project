from copy import deepcopy
from types import SimpleNamespace
from backend.case_analysis import prepare_analysis
from backend.live_assistant import respond_context,writer_facts
from backend.tests.test_case_analysis_api import market
from backend.tests.test_case_context import retrieval

def forward(case_id,cutoff):
    bars=[dict(time=300*i,open='100',high='101',low='99',close='100.5') for i in range(1,13)]
    return dict(status='AVAILABLE',reason='',anchor_price='100',anchor_time=300,case_as_of=299,side='BUY',source='HistData BID',basis='NEXT_COMPLETE_5M_OPEN',
        horizons={str(n):dict(status='AVAILABLE',reason='',minutes=n,end_time=300+n*60,bars=bars[:n//5],change_pct='0.5',mae_pct='1',mfe_pct='1') for n in (5,30,60)})

def bundle(r=None,draft=None,revision=1):
    snap=market();snap['symbol']=dict(lot_size_cents=10000,min_volume_cents=100,max_volume_cents=1000000,step_volume_cents=100)
    snap['quote'].update(bid='1999.8',ask='2000')
    return prepare_analysis(snap,'BUY',r or retrieval(),dict(as_of=1800000000,pre_entry_bars=snap['bars']),
        draft=draft or dict(side='BUY',lot='0.1',order_type='MARKET',sl='1990',tp='2020'),
        input_revision=revision,forward_store=SimpleNamespace(get=forward))

def test_outcomes_and_draft_are_attached_to_the_original_snapshot_without_reranking():
    b=bundle();a=b['context']['outcome_analysis']
    assert a['draft_risk']['stop_loss_usd']=='100.00'
    assert a['matched_cases']==2 and a['displayed_cases']==1
    assert a['cases'][0]['scenarios']['60']['mae_loss_usd']=='200.00'
    assert b['outcomes']['案例甲']['60']['history']['bars']
    assert len(b['outcomes']['案例甲']['5']['history']['bars'])==1
    assert a['cases'][0]['scenarios']['5']['mae_loss_usd']=='200.00'
    assert 'bars' not in a['cases'][0]['horizons']['60']
    assert a['input_revision']==1

def test_no_matches_still_has_risk_and_market_facts_but_no_fake_outcomes():
    b=bundle(retrieval('NO_RULE_MATCH'))
    assert b['context']['outcome_analysis']['cases']==[] and b['outcomes']=={}
    assert b['context']['outcome_analysis']['draft_risk']['status']=='AVAILABLE'
    reply=respond_context(b['context'],'停損與途中逆向風險如何？')
    assert '100.00' in reply['message'] and reply['sections']

def test_different_drafts_and_revisions_at_identical_market_data_have_distinct_snapshot_ids():
    # Use the identical input market, including quote timestamp.
    snap=market();q=dict(as_of=1800000000,pre_entry_bars=snap['bars'])
    from datetime import datetime
    now=datetime.fromisoformat(snap['quote']['source_time_utc']).timestamp()
    a=prepare_analysis(snap,'BUY',query=q,draft={'side':'BUY','lot':'.1'},input_revision=1,now=now)
    b=prepare_analysis(snap,'BUY',query=q,draft={'side':'BUY','lot':'.2'},input_revision=2,now=now)
    assert a['snapshot_id']!=b['snapshot_id']

def test_writer_payload_uses_templates_and_qualitative_basis_not_private_numbers():
    b=bundle();facts=[f for f in b['context']['facts'] if f['id'].startswith(('history.outcome','draft.'))]
    import json
    raw=json.dumps(writer_facts(facts),ensure_ascii=False)
    assert '{{' in raw and '100.00' not in raw and '1990' not in raw
    assert 'PRIVATE_CASE' not in raw and 'PRIVATE_GROUP' not in raw

def test_narrative_percentages_are_readable_without_changing_exact_api_metrics():
    b=bundle();fact=next(f for f in b['context']['facts'] if f['id']=='history.outcome')
    assert fact['values']['future_change']=='0.5000'
    assert b['context']['outcome_analysis']['cases'][0]['horizons']['60']['change_pct']=='0.5'

def test_missing_forward_data_is_explicit_and_does_not_disable_draft_risk():
    snap=market();b=prepare_analysis(snap,'BUY',retrieval(),query={},forward_store=None)
    a=b['context']['outcome_analysis']
    assert a['cases'][0]['horizons']['60']['status']!='AVAILABLE'
    assert a['cases'][0]['horizons']['60']['mae_pct'] is None
