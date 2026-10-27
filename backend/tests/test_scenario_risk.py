from copy import deepcopy
import pytest
from backend.scenario_risk import draft_risk,project_scenario

def market():
    return dict(quote=dict(status='CURRENT',bid='1999.8',ask='2000',age_seconds=0),
        symbol=dict(lot_size_cents=10000,min_volume_cents=100,max_volume_cents=1000000,step_volume_cents=100))

def draft(**changes):return dict(side='BUY',lot='0.10',order_type='MARKET',sl='1990',tp='2020',**changes)

def history(**changes):
    bars=[dict(time=300*(i+1),open='100',high='102',low='99.6',close='101') for i in range(6)]
    return dict(status='AVAILABLE',minutes=30,anchor_price='100',side='BUY',bars=bars,**changes)

def test_new_draft_only_decimal_contract_risk_and_relative_path_projection():
    base=draft_risk(market(),draft())
    assert base['status']=='AVAILABLE' and base['quantity_oz']=='10.00'
    assert base['stop_loss_usd']=='100.00' and base['entry_price']=='2000'
    r=project_scenario(history(),base,'BUY')
    assert r['status']=='AVAILABLE'
    assert r['end_pnl_usd']=='200.00' and r['mae_loss_usd']=='80.00' and r['mfe_profit_usd']=='400.00'
    assert r['touch_state']=='TARGET_FIRST'

def test_sell_projection_uses_bid_and_direction_correctly():
    d=dict(side='SELL',lot='0.2',order_type='MARKET',sl='2010',tp='1980')
    m=market();m['quote']['bid']='2000'
    r=project_scenario(history(),draft_risk(m,d),'SELL')
    assert r['end_pnl_usd']=='-400.00' and r['mae_loss_usd']=='800.00'
    assert r['mfe_profit_usd']=='160.00' and r['touch_state']=='STOP_FIRST'

def test_same_bar_double_touch_is_unknown_and_gap_does_not_promise_stop_fill():
    h=history();h['bars'][0].update(high='103',low='99',open='99')
    r=project_scenario(h,draft_risk(market(),draft()),'BUY')
    assert r['touch_state']=='BOTH_SAME_BAR' and r['gap_at_first_touch'] is True
    assert r['executed_pnl_usd'] is None

def test_missing_stop_is_unknown_not_zero_and_limit_is_conditional_on_fill():
    d=draft();d.update(sl='',order_type='LIMIT',limit_price='1995')
    r=draft_risk(market(),d)
    assert r['status']=='AVAILABLE' and r['stop_loss_usd'] is None
    assert r['entry_price']=='1995' and r['conditional_on_fill'] is True

@pytest.mark.parametrize('change',[dict(lot='NaN'),dict(lot='0'),dict(sl='0'),dict(tp='1990'),dict(lot='0.015')])
def test_invalid_inputs_never_turn_into_finite_zero_risk(change):
    d=draft();d.update(change)
    assert draft_risk(market(),d)['status']=='INVALID'

def test_missing_symbol_stale_quote_and_side_mismatch_do_not_fabricate_scenarios():
    m=market();m['symbol']=None
    assert draft_risk(m,draft())['status']=='UNAVAILABLE'
    m=market();m['quote']['age_seconds']=20
    assert draft_risk(m,draft())['status']=='UNAVAILABLE'
    assert project_scenario(history(),draft_risk(market(),draft()),'SELL')['status']=='SIDE_MISMATCH'
    h=history();h.update(status='GAPPED',bars=[])
    r=project_scenario(h,draft_risk(market(),draft()),'BUY')
    assert r['status']=='UNAVAILABLE' and r['mae_loss_usd'] is None

def test_price_gap_between_bars_is_accounted_as_open_beyond_stop():
    h=history();h['bars'][0].update(high='100.2',low='99.9',close='100')
    h['bars'][1].update(open='99',high='99.2',low='98',close='98.5')
    r=project_scenario(h,draft_risk(market(),draft()),'BUY')
    assert r['touch_state']=='STOP_FIRST' and r['gap_at_first_touch']
    assert r['first_touch_minutes']==10

def test_input_objects_are_not_mutated():
    m,d,h=market(),draft(),history();before=deepcopy((m,d,h))
    project_scenario(h,draft_risk(m,d),'BUY')
    assert (m,d,h)==before
