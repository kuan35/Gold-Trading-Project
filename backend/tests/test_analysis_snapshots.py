from backend.analysis_snapshots import SnapshotStore,snapshot_fingerprint
from backend.engine import DomainError
import pytest


def test_snapshot_identity_excludes_accounts_and_changes_with_market_or_side():
    s={'quote':{'source_time_utc':'now','bid':'4000','ask':'4001'},'bars':{'5m':[{'close':'4000'}]},'account':{'key':'secret'}}
    a=snapshot_fingerprint(s,'BUY')
    s['account']['key']='changed'
    assert snapshot_fingerprint(s,'BUY')==a
    assert snapshot_fingerprint(s,'SELL')!=a
    s['bars']['5m'][0]['close']='4001'
    assert snapshot_fingerprint(s,'BUY')!=a


def test_frozen_store_copies_inputs_outputs_and_expiry_never_silently_refreshes():
    clock=[0];s=SnapshotStore(limit=2,ttl=10,clock=lambda:clock[0])
    bundle={'snapshot_id':'a','context':{'quote':'4000'}}
    s.put(bundle,draft_id='draft');bundle['context']['quote']='9000'
    assert s.for_draft('draft')['context']['quote']=='4000'
    s.get('a')['context']['quote']='9999'
    assert s.get('a')['context']['quote']=='4000'
    clock[0]=11
    with pytest.raises(DomainError):s.for_draft('draft')


def test_store_is_bounded_and_evicted_draft_explanation_is_unavailable():
    s=SnapshotStore(limit=1)
    s.put({'snapshot_id':'a'},draft_id='old');s.put({'snapshot_id':'b'})
    with pytest.raises(DomainError):s.for_draft('old')
    assert s.get('b')['snapshot_id']=='b'


def test_analysis_identity_separates_opt_out_and_stale_state_from_earlier_current():
    from backend.case_analysis import prepare_analysis
    from backend.tests.test_live_assistant import snapshot,NOW
    from backend.tests.test_case_context import retrieval
    s=snapshot();cache=SnapshotStore()
    first=prepare_analysis(s,'BUY',now=NOW);cache.put(first)
    compared=prepare_analysis(s,'BUY',retrieval(),now=NOW)
    assert compared['snapshot_id']!=first['snapshot_id']
    s['quote']['age_seconds']=10
    stale=prepare_analysis(s,'BUY',retrieval(),now=NOW+10)
    assert stale['snapshot_id']!=compared['snapshot_id']
    assert cache.put(stale)['context']['status']=='UNAVAILABLE'


def test_frozen_program_explanation_uses_historical_wording():
    from backend.live_assistant import build_live_context,respond_context
    from backend.tests.test_live_assistant import snapshot,NOW
    r=respond_context(build_live_context(snapshot(),now=NOW),'盤面如何',frozen=True)
    assert '最新Bid' not in r['message'] and '即時Bid' not in r['message'] and '目前報價' not in r['message']
    assert '草稿' in r['message'] and r['market_status']=='FROZEN'


def test_unavailable_frozen_quote_describes_capture_time_instead_of_current_connection():
    from backend.live_assistant import build_live_context,respond_context
    from backend.tests.test_live_assistant import snapshot,NOW
    s=snapshot();s['quote']['age_seconds']=10
    r=respond_context(build_live_context(s,now=NOW),'解釋草稿',frozen=True)
    assert r['llm_status']=='market_unavailable' and '草稿建立時' in r['message']
    assert '目前沒有' not in r['message'] and '先確認cTrader連線' not in r['message']
