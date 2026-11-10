from copy import deepcopy
import json
from backend import case_statistics as stats


def rows():
    return [dict(id=f'PRIVATE{i}',side='BUY',entry='100',exit=str(100+p),profit=str(p),currency='USD',lot=str(i+1))
            for i,p in enumerate((10,-10,20,0,-20,100))]


def test_all_matched_representatives_are_used_not_just_the_first_five():
    source=rows();before=deepcopy(source);result=stats.summarize_original_trades(source)
    assert source==before and result['total']==6 and result['known_results']==6
    assert result['win_rate_pct']=='50.00' and result['wins']==3 and result['losses']==2
    assert result['mean_price_return_pct']=='16.6667'
    assert result['mean_move_per_oz']=='16.6667'
    assert result['pnl_by_currency'][0]['mean_pnl']=='16.67'
    assert 'PRIVATE' not in json.dumps(result)


def test_unknown_values_and_currencies_are_not_zero_filled_or_combined():
    source=rows()[:3];source[0]['currency']=None;source[1]['currency']='EUR';source[2]['profit']=None
    result=stats.summarize_original_trades(source)
    assert result['known_results']==2 and result['unknown_results']==1 and result['win_rate_pct']=='50.00'
    assert result['pnl_by_currency']==[dict(currency='EUR',count=1,mean_pnl='-10.00',mean_win=None,mean_loss='-10.00')]
    assert result['unknown_currency_results']==1
    assert stats.summarize_original_trades([])['win_rate_pct'] is None


def test_sell_returns_are_direction_adjusted_and_average_fact_masks_values():
    source=[dict(side='SELL',entry='100',exit='90',profit='7',currency='USD')]
    summary=stats.summarize_original_trades(source)
    assert summary['mean_price_return_pct']=='10.0000'
    from backend.live_assistant import writer_facts
    fact=stats.aggregate_fact(summary)
    assert '10.0000' not in json.dumps(writer_facts([fact]))
    assert '{{pool_mean_return}}' in fact['text']


def test_aggregate_fact_also_renders_when_a_model_is_unavailable():
    from backend.live_assistant import render_sections
    fact=stats.aggregate_fact(stats.summarize_original_trades(rows()))
    result=render_sections([dict(title='歷史整體表現',text=fact['text'],fact_ids=[fact['id']])],[fact])
    assert '16.6667%' in result[0]['text']


def test_cited_historical_win_rate_is_allowed_but_cannot_be_called_this_trades_probability():
    import pytest
    from backend.live_assistant import render_sections
    fact=stats.aggregate_fact(stats.summarize_original_trades(rows()))
    result=render_sections([dict(title='歷史結果',text='歷史勝率為{{pool_win_rate}}%。',fact_ids=[fact['id']])],[fact])
    assert '50.00%' in result[0]['text']
    with pytest.raises(ValueError):
        render_sections([dict(title='預測',text='本次勝率為{{pool_win_rate}}%。',fact_ids=[fact['id']])],[fact])
