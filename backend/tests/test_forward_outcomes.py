"""Synthetic forward-window arithmetic and point-in-time/privacy invariants."""
import hashlib
import json

import pytest

from backend.forward_outcomes import HistoricalOutcomeStore, build_case_outcome, METHOD


def bars(start=600):
    result=[dict(time=start+i*300,open='100',high='104',low='97',close='102',observed_minutes=5) for i in range(12)]
    result[2].update(high='108',low='92')
    result[5].update(close='106',high='106')
    result[-1]['close']='99'
    return result


def test_buy_and_sell_use_next_full_bar_open_and_direction_adjusted_excursions():
    buy=build_case_outcome('BUY',301,bars())
    sell=build_case_outcome('SELL',301,bars())
    assert buy['anchor_time']==600 and buy['anchor_price']=='100'
    assert buy['basis']=='NEXT_COMPLETE_5M_OPEN' and buy['source']=='HistData BID'
    assert buy['horizons']['5']['change_pct']=='2'
    assert buy['horizons']['5']['mae_pct']=='3'
    assert sell['horizons']['5']['change_pct']=='-2'
    assert sell['horizons']['5']['mae_pct']=='4'
    assert len(buy['horizons']['5']['bars'])==1
    assert buy['horizons']['30']['change_pct']=='6'
    assert buy['horizons']['60']['change_pct']=='-1'
    assert buy['horizons']['30']['mae_pct']=='8'
    assert buy['horizons']['30']['mfe_pct']=='8'
    assert sell['horizons']['30']['change_pct']=='-6'
    assert sell['horizons']['60']['change_pct']=='1'
    assert sell['horizons']['60']['mae_pct']=='8'
    assert len(buy['horizons']['30']['bars'])==6
    assert len(buy['horizons']['60']['bars'])==12
    assert all(type(b[k]) is str for b in buy['horizons']['60']['bars'] for k in ('open','high','low','close'))


def test_aligned_reference_uses_that_boundary_and_no_price_move_remains_real_zero():
    source=bars()
    for b in source:b.update(open='100',high='100',low='100',close='100')
    value=build_case_outcome('BUY',600,source)
    assert value['anchor_time']==600
    assert value['horizons']['60']['change_pct']=='0'
    assert value['horizons']['60']['mae_pct']=='0'


@pytest.mark.parametrize('corrupt,expected',[
    (lambda r:r.pop(3),'GAPPED_WINDOW'),
    (lambda r:r[3].update(observed_minutes=4),'INCOMPLETE_MINUTES'),
    (lambda r:r[3].update(high='90'),'INVALID_OHLC'),
    (lambda r:r[3].update(close='NaN'),'INVALID_OHLC'),
    (lambda r:r[3].update(observed_minutes=None),'INCOMPLETE_MINUTES'),
])
def test_missing_or_partial_bars_are_unknown_not_zero(corrupt,expected):
    source=bars();corrupt(source)
    value=build_case_outcome('BUY',301,source)
    assert value['horizons']['5']['status']=='AVAILABLE'
    for h in [value['horizons'][n] for n in ('30','60')]:
        assert h['status']==expected
        assert h['bars']==[] and h['change_pct'] is None and h['mae_pct'] is None and h['mfe_pct'] is None


def test_later_incomplete_horizon_does_not_poison_complete_earlier_horizon():
    source=bars()[:7]
    value=build_case_outcome('BUY',301,source)
    assert value['horizons']['30']['status']=='AVAILABLE'
    assert value['horizons']['60']['status']=='GAPPED_WINDOW'


@pytest.mark.parametrize('side,clock',[('HOLD',301),('BUY',None),('BUY',True),('BUY',-1)])
def test_invalid_reference_does_not_create_a_zero_anchor(side,clock):
    value=build_case_outcome(side,clock,bars())
    assert value['status']!='AVAILABLE' and value['anchor_price'] is None
    assert all(h['mae_pct'] is None for h in value['horizons'].values())


def fixture(tmp_path):
    root=tmp_path/'private';root.mkdir(parents=True)
    casepath=root/'cases.json';casepath.write_text(json.dumps({'cases':[{'id':'X','side':'BUY'}]}),encoding='utf8')
    csv=root/'bars.csv';csv.write_text('Synthetic fixture, not used for live data',encoding='utf8')
    reference=lambda p:dict(path=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    profiles=root/'case_candidate_market_profiles.json'
    profiles.write_text(json.dumps(dict(input_cases_sha256=reference(casepath)['sha256'],inputs={'bars':reference(csv)},profiles={'X':{'as_of':301}})),encoding='utf8')
    value=build_case_outcome('BUY',301,bars())
    payload=dict(method=METHOD,inputs={'cases':reference(casepath),'profiles':reference(profiles),'bars':reference(csv)},profiles={'X':value})
    path=root/'case_forward_outcomes.json';path.write_text(json.dumps(payload),encoding='utf8')
    return root,path,payload


def test_store_only_exposes_horizons_that_ended_before_query_and_returns_deep_copies(tmp_path):
    root,_,_=fixture(tmp_path);store=HistoricalOutcomeStore(root)
    assert store.get('X',899)['horizons']['5']['status']=='NOT_YET_KNOWN'
    first=store.get('X',900)
    assert first['horizons']['5']['status']=='AVAILABLE'
    assert first['horizons']['30']['bars']==[]
    partial=store.get('X',2400)
    assert partial['horizons']['30']['status']=='AVAILABLE'
    assert partial['horizons']['60']['status']=='NOT_YET_KNOWN'
    assert partial['horizons']['60']['bars']==[] and partial['horizons']['60']['mae_pct'] is None
    assert partial['horizons']['60']['change_pct'] is None
    complete=store.get('X',4200)
    assert complete['horizons']['60']['status']=='AVAILABLE'
    assert complete['horizons']['60']['end_time']==4200
    complete['horizons']['60']['bars'][0]['close']='999999'
    assert store.get('X',4200)['horizons']['60']['bars'][0]['close']=='102'
    unknown=store.get('X',None)
    assert unknown['horizons']['30']['status']=='INVALID_QUERY_TIME'


def test_store_missing_unknown_or_bad_inputs_never_returns_stale_usable_metrics(tmp_path):
    root,path,_=fixture(tmp_path);store=HistoricalOutcomeStore(root)
    assert store.get('unknown',10000)['status']=='CASE_NOT_FOUND'
    assert store.get('X',10000)['status']=='AVAILABLE'
    (root/'cases.json').write_text('{"cases":[]}',encoding='utf8')
    stale=store.get('X',10000)
    assert stale['status']=='STALE'
    assert stale['horizons']['60']['mae_pct'] is None
    assert str(root) not in json.dumps(stale)
    path.unlink()
    assert store.get('X',10000)['status']=='MISSING'


@pytest.mark.parametrize('target',['profiles','bars'])
def test_store_binds_profile_and_market_hashes(tmp_path,target):
    root,_,_=fixture(tmp_path)
    filename='case_candidate_market_profiles.json' if target=='profiles' else 'bars.csv'
    (root/filename).write_text('changed',encoding='utf8')
    assert HistoricalOutcomeStore(root).get('X',10000)['status']=='STALE'


def test_store_rejects_path_escape_and_corrupted_derived_metrics(tmp_path):
    root,path,payload=fixture(tmp_path)
    payload['inputs']['bars']['path']='../outside.csv'
    path.write_text(json.dumps(payload),encoding='utf8')
    assert HistoricalOutcomeStore(root).get('X',10000)['status']=='INVALID'
    root,path,payload=fixture(tmp_path/'again')
    payload['profiles']['X']['horizons']['60']['mae_pct']='0'
    path.write_text(json.dumps(payload),encoding='utf8')
    assert HistoricalOutcomeStore(root).get('X',10000)['status']=='INVALID'


def test_store_rejects_reference_identity_changed_without_other_input_changes(tmp_path):
    root,path,payload=fixture(tmp_path)
    payload['profiles']['X']['case_as_of']=600
    path.write_text(json.dumps(payload),encoding='utf8')
    assert HistoricalOutcomeStore(root).get('X',10000)['status']=='INVALID'


def test_store_rechecks_after_an_initial_stale_source_is_restored(tmp_path):
    root,_,_=fixture(tmp_path);csv=root/'bars.csv';original=csv.read_bytes()
    csv.write_text('changed',encoding='utf8')
    store=HistoricalOutcomeStore(root)
    assert store.get('X',10000)['status']=='STALE'
    csv.write_bytes(original)
    assert store.get('X',10000)['status']=='AVAILABLE'


@pytest.mark.parametrize('case_id',[None,[],{}])
def test_arbitrary_unknown_case_identity_fails_closed_without_raising(tmp_path,case_id):
    root,_,_=fixture(tmp_path)
    assert HistoricalOutcomeStore(root).get(case_id,10000)['status']=='CASE_NOT_FOUND'


def test_store_rejects_fake_available_bars_and_never_returns_their_prices(tmp_path):
    root,path,payload=fixture(tmp_path)
    payload['profiles']['X']['horizons']['60']['bars'][2]['close']='NaN'
    path.write_text(json.dumps(payload),encoding='utf8')
    result=HistoricalOutcomeStore(root).get('X',10000)
    assert result['status']=='INVALID' and result['horizons']['60']['bars']==[]
