from backend.trade_result import trade_result
from backend.execution_overlay import execution_overlay
from scripts.live_readonly_policy import validate_request, load_live_config
from scripts.volume_similarity_probe import compare_volume
import pytest


def test_price_return_has_sell_sign_and_no_capital_assumption():
    assert trade_result({'side':'BUY','entry':'2000','exit':'2010'})['price_return_pct']=='0.5'
    result=trade_result({'side':'SELL','entry':'2000','exit':'1990'})
    assert result['move_per_oz']=='10' and result['margin_roi_pct'] is None
    assert trade_result({'side':'SELL','entry':'2000','exit':'2000'})['move_per_oz']=='0'
    assert trade_result({'side':'BUY','entry':'0','exit':'2'})['status']=='UNAVAILABLE'
    assert trade_result({'side':'BUY','entry':'NaN','exit':'2'})['status']=='UNAVAILABLE'


def test_overlay_never_moves_partial_entry_to_next_bar():
    source={'side':'BUY','entry':'2000','exit':'2010'}
    p={'as_of':601,'reference_open_utc':601,'reference_close_utc':1250,'reference_clock_basis':'source_model_scenario'}
    bars=[{'time':t,'open':2000,'high':2011,'low':1999,'close':2001} for t in (600,900,1200)]
    value=execution_overlay(source,p,bars,cutoff=2000)
    assert [m['time'] for m in value['markers']]==[600,1200]
    assert value['markers'][0]['executed_at']==601
    assert value['markers'][0]['price'] is None
    assert execution_overlay(source,p,[],cutoff=2000)['markers']==[]
    assert execution_overlay(source,p,bars,cutoff=1000)['status']=='UNAVAILABLE'


def test_live_policy_rejects_trade_even_with_trade_token(tmp_path):
    class ProtoOANewOrderReq: pass
    class ProtoOAReconcileReq: pass
    with pytest.raises(ValueError): validate_request(ProtoOANewOrderReq())
    validate_request(ProtoOAReconcileReq())
    p=tmp_path/'live.env'
    p.write_text('CTRADER_ENVIRONMENT=live\nCTRADER_CLIENT_ID=a\nCTRADER_CLIENT_SECRET=b\nCTRADER_ACCESS_TOKEN=c\n')
    with pytest.raises(ValueError,match='ACCOUNT_ID_REQUIRED'): load_live_config(p)
    p.write_text(p.read_text()+'CTRADER_ACCOUNT_ID=1\n')
    assert load_live_config(p)['CTRADER_ENVIRONMENT']=='live'


def test_live_wrapper_does_not_touch_transport_on_trade_or_wrong_account():
    from scripts.live_readonly_policy import ReadOnlyClient, select_live
    from backend.live_readonly import LiveReadOnlyStream
    from types import SimpleNamespace
    sent=[]
    client=ReadOnlyClient(SimpleNamespace(send=lambda *a,**kw:sent.append(a)))
    for name in ('ProtoOANewOrderReq','ProtoOAClosePositionReq','ProtoOACancelOrderReq','ProtoOAAmendOrderReq'):
        with pytest.raises(ValueError):client.send(type(name,(),{})())
    assert sent==[]
    with pytest.raises(ValueError):select_live([SimpleNamespace(isLive=False,ctidTraderAccountId=1)],'1')
    stream=LiveReadOnlyStream()
    assert stream._snapshot_locked()['order_connection'] is False
    assert stream._snapshot_locked()['environment']=='live'
    with pytest.raises(ValueError):stream.place_order({})


def test_volume_does_not_compare_missing_or_cross_source():
    rows=[{'volume':10}]*20+[{'volume':20}]
    assert compare_volume(rows,rows,'ctrader:a','ctrader:a',2)['passed'] is True
    assert compare_volume(rows,rows,'ctrader:a','histdata',2)['status']=='INCOMPARABLE_SOURCE'
    assert compare_volume([{}]*21,rows,'a','a',2)['status']=='MISSING_VOLUME'
