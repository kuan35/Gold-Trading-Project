"""Synthetic evidence contracts; never call a model or broker."""
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
import json
import pytest

from backend import live_assistant as live
from backend.case_analysis import prepare_analysis
from backend.tests.test_case_context import retrieval
from backend.tests.test_live_assistant import NOW, snapshot


def query():
    return dict(as_of=NOW, pre_entry_bars=snapshot()['bars'])


def profile():
    return dict(query(), profit='123456', account='PRIVATE_ACCOUNT')


def test_fixed_shape_excludes_future_bars_and_is_independent_of_original_result():
    from backend.market_case_brief import describe_pre_entry
    source=profile()
    before=describe_pre_entry(source['pre_entry_bars'], NOW, event='區間內活動', tail='上行')
    source.update(profit='-999999', exit='1', closed_at='2099-01-01')
    source['pre_entry_bars']['5m'].append(dict(time=NOW, open='1', high='2', low='1', close='2'))
    after=describe_pre_entry(source['pre_entry_bars'], NOW, event='區間內活動', tail='上行')
    assert before==after
    assert before['frames']['5m']['count']==60
    assert [s['count'] for s in before['frames']['5m']['segments']]==[20,20,20]
    assert before['frames']['1h']['count']==20
    assert before['frames']['5m']['direction']=='上行'


def test_unknown_and_invalid_history_are_explicit_instead_of_zero_or_inferred_shape():
    from backend.market_case_brief import describe_pre_entry
    missing=describe_pre_entry({}, NOW)
    assert missing['frames']['5m']['status']=='UNAVAILABLE'
    assert missing['frames']['5m']['change_pct'] is None
    assert missing['event']=='未知' and missing['tail_direction']=='未知'
    broken=profile()['pre_entry_bars']
    broken['5m'][-1]['close']='NaN'
    assert describe_pre_entry(broken,NOW)['frames']['5m']['status']=='UNAVAILABLE'
    assert describe_pre_entry(broken,float('nan'))['frames']['1h']['status']=='UNAVAILABLE'


def test_frozen_buy_draft_keeps_side_distinct_from_bearish_market_and_sends_joint_evidence(monkeypatch):
    snap=snapshot()
    snap['symbol']=dict(lot_size_cents=10000,min_volume_cents=100,max_volume_cents=1000000,step_volume_cents=100)
    for bars in snap['bars'].values():
        for i,b in enumerate(bars):
            b.update(open=4500-i,high=4501-i,low=4498-i,close=4499-i)
    snap['quote'].update(bid='4380',ask='4380.2')
    raw=retrieval()
    from backend.case_statistics import summarize_original_trades
    # Build the actual aggregate via its public helper rather than inventing a fact.
    source=dict(id='PRIVATE_CASE',side='BUY',entry='1786.51',exit='1788.51',profit='12',currency='USD',
        available_at=NOW-100000,opened_at='2023-10-03T08:00:00',closed_at='2023-10-04T10:00:00')
    raw['original_performance']=summarize_original_trades([source,dict(source,id='other')])
    b=prepare_analysis(snap,'BUY',raw,dict(as_of=NOW,pre_entry_bars=snap['bars']),now=NOW,profiles={'PRIVATE_CASE':profile()},
        operation_sources={'PRIVATE_CASE':source},draft=dict(side='BUY',order_type='MARKET',lot='.1',sl='4370',tp='4400'),
        forward_store=SimpleNamespace(get=lambda *_:dict(reason='合成後續缺棒')))
    facts={f['id']:f for f in b['context']['facts']}
    assert facts['draft.risk']['values']['draft_side_state']=='做多'
    assert facts['draft.risk']['values']['draft_stop']=='4370'
    assert facts['draft.risk']['values']['draft_target']=='4400'
    assert facts['f5.trend']['values']['f5_bias']!= '偏多'
    assert 'history.outcome' in facts
    assert '方向不同' in facts['history.shape_comparison1']['values']['hist1_shape_comparison_state']
    def model(*a,**kw):
        payload=kw['catalog'];sent={f['id']:f for f in payload['facts']}
        assert {'f5.trend','history.query_shape','history.shape1','history.case1','history.trade1','history.aggregate','draft.risk'}<=sent.keys()
        assert sent['draft.risk']['basis']['draft_side_state']=='做多'
        serialized=json.dumps(payload,ensure_ascii=False)
        assert all(secret not in serialized for secret in ['PRIVATE_CASE','PRIVATE_ACCOUNT','1786.51','4370','4400','2023-10-03'])
        assert '草稿方向' in kw['system_prompt'] and '盤面偏向' in kw['system_prompt']
        assert '至少一個' in kw['system_prompt']
        return dict(status='ok',text=json.dumps({'sections':[dict(title='這筆委託評估',
            text='草稿方向{{draft_side_state}}；盤面偏向{{f5_bias}}是反證。雖同池{{pool_price_count}}筆有效原單平均價格報酬{{pool_mean_return}}%是歷史支持，但案例事件{{hist1_event_state}}仍須核對當時條件。',
            fact_ids=['draft.risk','f5.trend','history.aggregate','history.case1'])]}))
    monkeypatch.setattr(live,'explain_context',model)
    result=live.respond_context(b['context'],'這筆停損停利如何？',enabled=True,frozen=True)
    assert result['llm_status']=='ok'
    assert '草稿方向做多' in result['message']


def test_all_displayed_cases_keep_pre_entry_shape_and_original_operation_separate():
    from backend.case_operations import historical_trade_fact
    source=dict(side='SELL',entry='2000',exit='1990',available_at=NOW-100000,
        opened_at='2023-10-03T08:00:00',closed_at='2023-10-04T10:00:00')
    for number,ref in enumerate(['案例甲','案例乙','案例丙','案例丁','案例戊'],1):
        fact=historical_trade_fact(source,ref,number,NOW)
        assert fact['id']==f'history.trade{number}'
    assert historical_trade_fact(source,'案例甲',1,NOW-100001) is None


def test_unavailable_risk_does_not_erase_draft_direction_or_filled_protection():
    # No broker contract specifications: calculation unavailable, entered terms known.
    b=prepare_analysis(snapshot(),'BUY',query=query(),now=NOW,
        draft=dict(side='BUY',order_type='LIMIT',lot='.1',limit_price='4000',sl='3990',tp='4020'))
    facts={f['id']:f for f in b['context']['facts']}
    assert facts['draft.terms']['values']['draft_side_state']=='做多'
    assert facts['draft.terms']['values']['draft_stop']=='3990'
    assert facts['draft.terms']['values']['draft_target']=='4020'
    assert b['context']['outcome_analysis']['draft_risk']['status']=='UNAVAILABLE'


def test_model_cannot_relabel_buy_draft_as_bearish_but_can_describe_market_conflict():
    facts=[dict(id='draft.terms',text='草稿方向{{draft_side_state}}',values=dict(draft_side_state='做多')),
           dict(id='f5.trend',text='盤面{{f5_bias}}',values=dict(f5_bias='偏空'))]
    with pytest.raises(ValueError):
        live.render_model_sections([dict(title='委託',text='這筆草稿方向偏空。',fact_ids=['draft.terms','f5.trend'])],facts)
    result,_=live.render_model_sections([dict(title='委託',text='做多草稿與盤面偏空有衝突。',fact_ids=['draft.terms','f5.trend'])],facts)
    assert result[0]['source']=='model'


def test_historical_shape_with_reference_after_query_is_unavailable():
    late=profile();late['as_of']=NOW+3600
    b=prepare_analysis(snapshot(),'BUY',retrieval(),query(),now=NOW,profiles={'PRIVATE_CASE':late})
    fact=next(f for f in b['context']['facts'] if f['id']=='history.shape1')
    assert '五分鐘形態資料不足' in fact['text']
    assert 'hs1_f5_change' not in fact['values']
