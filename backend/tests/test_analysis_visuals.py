from copy import deepcopy
from datetime import datetime, timezone
import importlib

import pytest

from backend.case_analysis import prepare_analysis
from backend.live_assistant import build_live_context


NOW = 1800000000


def market():
    frames = {}
    for interval, span in [('5m', 300), ('15m', 900), ('1h', 3600)]:
        end = NOW // span * span
        rows = [dict(time=end - (120-i)*span, open='100', high='102', low='98', close='100')
                for i in range(120)]
        # Confirmed pivots, independently hand-checked against two bars each side.
        rows[-35]['low'] = '95'
        rows[-30]['high'] = '105'
        rows.append(dict(time=end, open='100', high='99999', low='1', close='500'))
        frames[interval] = rows
    return dict(connection_status='CONNECTED',
                quote=dict(status='CURRENT', bid='100', ask='100.2', age_seconds=0,
                           source_time_utc=datetime.fromtimestamp(NOW, timezone.utc).isoformat()),
                bars=frames)


def visuals(snapshot, context=None, now=NOW):
    module = importlib.import_module('backend.analysis_visuals')
    return module.build_analysis_visuals(snapshot, context or build_live_context(snapshot, now=NOW), now)


def test_analysis_uses_original_cutoff_and_keeps_sufficient_native_windows():
    snapshot = market()
    context = build_live_context(snapshot, now=NOW)
    result = visuals(snapshot, context, now=NOW+86400)
    assert result['as_of_utc'] == '2027-01-15T08:00:00+00:00'
    assert set(result['frames']) == {'5m', '15m', '1h'}
    for interval, span in [('5m', 300), ('15m', 900), ('1h', 3600)]:
        frame = result['frames'][interval]
        assert len(frame['bars']) == 90
        assert frame['bars'][-1] == dict(time=NOW//span*span-span, open=100, high=102, low=98, close=100)
        assert all(bar['time']+span <= NOW for bar in frame['bars'])
        assert 'source_volume_unknown' in frame['quality']['reasons']


def test_program_layers_keep_fixed_range_recent_six_and_existing_confirmed_pivots_separate():
    result = visuals(market())
    frame = result['frames']['5m']
    layers = {layer['id']: layer for layer in frame['layers']}
    assert layers['f5.fixed-range'] == dict(id='f5.fixed-range', kind='region',
        label='最近6棒之前20棒的固定高低區間', start_time=NOW-26*300,
        end_time=NOW-6*300, high='102', low='98')
    assert layers['f5.recent-six']['start_time'] == NOW-6*300
    assert layers['f5.recent-six']['end_time'] == NOW
    assert layers['f5.range-high']['price'] == '102'
    assert layers['f5.range-low']['price'] == '98'
    assert layers['f5.support.1']['price'] == '95.00'
    assert layers['f5.resistance.1']['price'] == '105.00'
    assert '轉折' in layers['f5.support.1']['label']
    assert layers['f5.event']['label'] == '區間內活動'
    assert layers['f5.event']['time'] == NOW-300
    assert all(layer['kind'] in ('line', 'region', 'marker') for layer in frame['layers'])
    assert not any('fixed-range' in layer['id'] for layer in result['frames']['15m']['layers'])


def test_wick_is_not_labelled_as_a_close_breakout_and_reclaim_is_explicit():
    snapshot = market()
    snapshot['bars']['5m'][-2]['high'] = '104'
    result = visuals(snapshot)
    event = next(layer for layer in result['frames']['5m']['layers'] if layer['id'] == 'f5.event')
    assert '影線' in event['label'] and '未形成收盤突破' in event['label']
    snapshot['bars']['5m'][-3].update(high='104', close='103')
    event = next(layer for layer in visuals(snapshot)['frames']['5m']['layers'] if layer['id'] == 'f5.event')
    assert event['label'] == '突破後退回區間'


@pytest.mark.parametrize('bad', ['NaN', None, '-1'])
def test_invalid_prices_do_not_create_zero_or_fixed_event_layers(bad):
    snapshot = market()
    snapshot['bars']['5m'][-3]['high'] = bad
    result = visuals(snapshot)['frames']['5m']
    assert not result['bars'] and not result['layers']
    assert result['quality']['status'] == 'invalid'


def test_unavailable_context_and_missing_interval_do_not_substitute_prices_or_levels():
    snapshot = market()
    context = build_live_context(snapshot, now=NOW)
    snapshot['bars'].pop('15m')
    assert visuals(snapshot, context)['frames']['15m']['bars'] == []
    context['status'] = 'UNAVAILABLE'
    assert all(not frame['bars'] and not frame['layers'] for frame in visuals(snapshot, context)['frames'].values())


def test_prepare_analysis_stores_visuals_without_changing_case_comparison_windows():
    snapshot = market()
    original = deepcopy(snapshot)
    bundle = prepare_analysis(snapshot, 'BUY', query=dict(as_of=NOW, pre_entry_bars=snapshot['bars']), now=NOW)
    assert len(bundle['charts']['analysis']['frames']['1h']['bars']) == 90
    assert len(bundle['charts']['query']['1h']) == 20
    assert len(bundle['charts']['query']['5m']) == 60
    assert snapshot == original


def test_extreme_decimal_prices_cannot_underflow_into_a_zero_chart():
    snapshot=market()
    for row in snapshot['bars']['5m']:
        row.update(open='1E-999',high='2E-999',low='1E-1000',close='1E-999')
    result=visuals(snapshot)['frames']['5m']
    assert not result['bars'] and not result['layers']
    assert result['quality']['status']=='invalid'


def test_missing_event_bar_keeps_observed_chart_but_does_not_invent_fixed_six_bar_window():
    snapshot=market()
    del snapshot['bars']['5m'][-4]
    frame=visuals(snapshot)['frames']['5m']
    assert frame['bars'] and frame['quality']['gap_count']==1
    assert not any(layer['id'].startswith('f5.range') or layer['id'] in ('f5.fixed-range','f5.recent-six','f5.event')
                   for layer in frame['layers'])


def test_old_completed_bars_are_labelled_stale_and_not_given_current_event_layers():
    snapshot=market()
    snapshot['bars']['5m']=snapshot['bars']['5m'][:-4]
    frame=visuals(snapshot)['frames']['5m']
    assert frame['bars'] and not frame['layers']
    assert frame['quality']['status']=='stale'


@pytest.mark.parametrize('bad_time', [NOW-900, NOW-299, -300, None])
def test_invalid_order_or_alignment_rejects_the_entire_frame(bad_time):
    snapshot=market()
    snapshot['bars']['5m'][-2]['time']=bad_time
    frame=visuals(snapshot)['frames']['5m']
    assert not frame['bars'] and not frame['layers']
    assert frame['quality']['status']=='invalid'
