"""Behavioral checks for the offline context-contract experiment."""
from copy import deepcopy
from decimal import Decimal
import pytest

from research.context_similarity_ab import market_features, pair_metrics, evaluate_rows, write_review_template, LIMITS


def profile(event_closes=None):
    clock=2000000400
    five=[]
    for i in range(60):
        close=Decimal(str((event_closes or [105]*6)[i-54])) if i>=54 else Decimal(105)
        five.append(dict(time=clock-(60-i)*300,open=str(close),close=str(close),
                         high=str(max(Decimal(110) if i<54 else close,close)),
                         low=str(min(Decimal(100) if i<54 else close,close))))
    hour=[dict(time=clock-(20-i)*3600,open='105',high='110',low='100',close='105') for i in range(20)]
    return dict(status='candidate_only',tier='full',as_of=clock,
                pre_entry_bars={'5m':five,'1h':hour},
                indicators={'5m_atr_pct':'1','1h_atr_pct':'1'})


def test_same_v_but_still_below_vs_reclaimed_are_distinct_stages():
    # Reference ATR=10, buffer=1; 98 is a confirmed close below 99.
    reclaimed=market_features(profile([101,98,98,101,103,105]))
    below=market_features(profile([101,98,97,97,98,98]))
    assert reclaimed['event']=='LOWER_RECLAIM'
    assert below['event']=='BELOW'
    assert reclaimed['reference_low']=='100'


def test_event_levels_do_not_move_with_event_extremes_and_wick_is_not_close_break():
    p=profile([105]*6);p['pre_entry_bars']['5m'][56]['low']='90'
    f=market_features(p)
    assert f['event']=='IN_RANGE' and f['reference_low']=='100'
    assert f['lower_wick_outside'] is True


def test_future_or_nonfinite_candles_are_not_silently_used():
    p=profile();p['pre_entry_bars']['5m'][-1]['time']=p['as_of']
    with pytest.raises(ValueError):market_features(p)
    p=profile();p['pre_entry_bars']['1h'][-1]['close']='NaN'
    with pytest.raises(ValueError):market_features(p)


def test_positive_price_scaling_does_not_change_comparison():
    p=profile([104,102,98,102,104,105]);scaled=deepcopy(p)
    for bars in scaled['pre_entry_bars'].values():
        for bar in bars:
            for k in ('open','high','low','close'):bar[k]=str(Decimal(bar[k])*3)
    a,b=market_features(p),market_features(scaled)
    m=pair_metrics(a,b)
    assert a['event']==b['event']
    assert m['d5']==pytest.approx(0) and m['d1h']==pytest.approx(0)
    assert m['dtail']==pytest.approx(0) and m['vol_ratio']==1


def row(cid='a',group='g',**kw):
    d=dict(case_id=cid,group=group,d5=.1,d1h=.2,dtail=.03,vol_ratio=1.2,
           query_event='IN_RANGE',case_event='IN_RANGE',query_tail='U',case_tail='U')
    d.update(kw);return d


def descriptions():
    return {'a':dict(end_5m=10,end_1h=0),'b':dict(end_5m=20,end_1h=0),
            'c':dict(end_5m=30,end_1h=0)}


def test_can_return_empty_and_no_fallback_when_path_or_stage_fails():
    result=evaluate_rows([row(d5=2),row('b','h',case_event='BELOW')],descriptions(),LIMITS['medium'])
    assert result['rows']==[] and result['passed_rows']==0
    assert result['rejections']['five_path']==1
    assert result['rejections']['event_stage']==1


def test_tail_opposition_is_not_hidden_by_good_long_window_fit():
    result=evaluate_rows([row(case_tail='D')],descriptions(),LIMITS['medium'])
    assert result['rows']==[] and result['rejections']['tail_direction']==1


def test_dedup_and_stable_ranking_ignore_profit_and_size():
    rows=[row('b','g'),row('a','g'),row('c','h')]
    result=evaluate_rows(rows,descriptions(),LIMITS['medium'])
    assert [r['case_id'] for r in result['rows']]==['a','c']
    altered=[dict(r,profit='-999999',size='300') for r in reversed(rows)]
    assert [r['case_id'] for r in evaluate_rows(altered,descriptions(),LIMITS['medium'])['rows']]==['a','c']


def test_ablation_is_explicit_and_boundary_unknown_never_means_match():
    r=row(case_event='BOUNDARY_UNKNOWN',case_tail='D',vol_ratio=3)
    assert evaluate_rows([r],descriptions(),LIMITS['medium'],components='paths')['rows']
    full=evaluate_rows([r],descriptions(),LIMITS['medium'])
    assert full['rows']==[] and full['rejections']['event_unknown']==1


def test_strict_passes_are_a_subset_of_loose_passes():
    rows=[row(),row('b','h',d5=.3),row('c','j',vol_ratio=2.4)]
    strict=evaluate_rows(rows,descriptions(),LIMITS['strict'])
    loose=evaluate_rows(rows,descriptions(),LIMITS['loose'])
    assert {r['case_id'] for r in strict['rows']} <= {r['case_id'] for r in loose['rows']}


def test_different_groups_with_same_reference_window_are_deduplicated():
    ds=descriptions();ds['b']=dict(ds['a'])
    result=evaluate_rows([row('b','h'),row('a','g'),row('c','j')],ds,LIMITS['medium'])
    assert [r['case_id'] for r in result['rows']]==['a','c']


def test_render_template_never_overwrites_completed_human_labels(tmp_path):
    target=tmp_path/'review.csv'
    records=[dict(query_id='Q',methods={m:dict(rows=[row()]) for m in ('A','B_medium')})]
    assert write_review_template(records,target) is True
    target.write_text('reviewer,answer\nKuan,comparable\n',encoding='utf-8')
    before=target.read_bytes()
    assert write_review_template(records,target) is False
    assert target.read_bytes()==before
