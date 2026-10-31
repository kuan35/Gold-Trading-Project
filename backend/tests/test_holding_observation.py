from copy import deepcopy
import pytest
from backend.holding_observation import summarize


def bar(time,open=100,high=110,low=95,close=104):return dict(time=time,open=open,high=high,low=low,close=close)
def execution(opened=300,closed=900,bars=None):
    return dict(status='AVAILABLE',mode='FULL_HOLDING',coverage={'scope':'WHOLE_REFERENCE_HOLDING'},opened_at=opened,closed_at=closed,
        bars=bars if bars is not None else [bar(300),bar(600),bar(900)],result={'entry_price':'9999'})


@pytest.mark.parametrize('side,mae,mfe,change',[('BUY','5','10','4'),('SELL','10','5','-4')])
def test_buy_sell_use_reference_open_and_not_original_broker_price(side,mae,mfe,change):
    source=execution();old=deepcopy(source);value=summarize(source,side,cutoff=1200)
    assert value['status']=='AVAILABLE' and value['bars_used']==2
    assert value['observed_mae_pct']==mae and value['observed_mfe_pct']==mfe
    assert value['reference_return_pct']==change and value['anchor_price']=='100'
    assert value['anchor_time']==300 and value['last_bar_end']==900
    assert source==old


def test_partial_entry_and_exit_bars_do_not_pollute_observation_extremes():
    source=execution(301,1250,[bar(300,high=9999,low=1),bar(600),bar(900),bar(1200,high=9999,low=1)])
    value=summarize(source,'BUY',cutoff=1500)
    assert value['status']=='AVAILABLE' and value['bars_used']==2
    assert value['anchor_time']==600 and value['observed_mae_pct']=='5' and value['observed_mfe_pct']=='10'


def test_gaps_are_partial_observations_and_never_filled():
    value=summarize(execution(300,1500,[bar(300),bar(900),bar(1200),bar(1500)]),'BUY',cutoff=1800)
    assert value['status']=='PARTIAL' and value['bars_used']==3 and value['missing_closed_slots']==1
    assert value['observed_mae_pct']=='5' and '已知' in value['reason']


def test_no_complete_bar_missing_fixed_anchor_and_endpoint_only_do_not_become_zero():
    for source in [execution(301,599,[bar(300)]),execution(300,1200,[bar(600),bar(900),bar(1200)]),{**execution(),'coverage':{'scope':'ENDPOINT_WINDOWS'}}]:
        value=summarize(source,'BUY',cutoff=1500)
        assert value['status'] in ('INSUFFICIENT','UNAVAILABLE')
        assert value['observed_mae_pct'] is None and value['reference_return_pct'] is None


def test_bad_prices_duplicate_bars_and_invalid_or_premature_cutoff_fail_closed():
    for source in [execution(bars=[bar(300,high=90),bar(600)]),execution(bars=[bar(300),bar(300),bar(600)])]:
        assert summarize(source,'BUY',cutoff=1200)['status']=='UNAVAILABLE'
    for cutoff in [899,None,float('nan'),float('inf')]:
        assert summarize(execution(),'BUY',cutoff=cutoff)['status']=='UNAVAILABLE'
    assert summarize(execution(),'UNKNOWN',cutoff=1200)['status']=='UNAVAILABLE'


def test_prepared_observation_is_frozen_and_review_does_not_reload_market():
    from backend.case_analysis import prepare_analysis
    from backend.analysis_snapshots import SnapshotStore
    from backend.tests.test_case_context import retrieval
    from backend.tests.test_case_analysis_api import market
    from backend.case_review import review_cases
    source=execution()
    class Store:
        def get(self,*args):return source
    bundle=prepare_analysis(market(),'BUY',retrieval(),query={'as_of':1200},execution_store=Store())
    assert bundle['charts']['cases'][0]['holding_observation']['observed_mae_pct']=='5'
    frozen=SnapshotStore();frozen.put(bundle)
    source['bars'][0]['low']=1
    old=frozen.get(bundle['snapshot_id'])
    assert old['charts']['cases'][0]['holding_observation']['observed_mae_pct']=='5'
    result=review_cases(old,enabled=False)
    assert result['provider']=='program' and '已知K棒' in result['message']
