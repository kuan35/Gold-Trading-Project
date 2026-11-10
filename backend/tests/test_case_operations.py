from copy import deepcopy
import json
from backend.case_operations import build_case_operations

def test_historical_trade_fact_is_bound_to_mature_ledger_and_masks_exact_values():
    from backend.case_operations import historical_trade_fact
    from backend.live_assistant import writer_facts,render_sections
    source=dict(case(),available_at=1700000000,opened_at='2023-10-03T08:00:00',closed_at='2023-10-04T10:00:00')
    before=deepcopy(source)
    fact=historical_trade_fact(source,'案例甲',1,1800000000)
    assert fact['id']=='history.trade1' and source==before
    payload=json.dumps(writer_facts([fact]),ensure_ascii=False)
    assert '{{hist1_entry}}' in payload
    assert all(s not in payload for s in ['PRIVATE_CASE','PRIVATE_ACCOUNT','PRIVATE_SOURCE','2023-10-03','4000'])
    rendered=render_sections([dict(title='歷史操作',text=fact['text'],fact_ids=[fact['id']])],[fact])[0]['text']
    assert '2023年10月03日' in rendered and '4000' in rendered and '0.0500%' in rendered
    assert fact['values']['hist1_opened_at']=='2023-10-03 08:00:00'
    assert '20 USD' in rendered
    assert '時區未核實' in rendered and '未扣交易成本' in rendered
    for patch in [dict(available_at=1900000000),dict(opened_at='bad'),dict(exit='NaN')]:
        assert historical_trade_fact(dict(source,**patch),'案例甲',1,1800000000) is None

def test_historical_sell_return_keeps_direction_without_margin_roi_or_execution_guess():
    from backend.case_operations import historical_trade_fact
    source=dict(case(),side='SELL',entry='4000',exit='4002',available_at=10,opened_at='2023-10-03',closed_at='2023-10-04')
    fact=historical_trade_fact(source,'案例乙',2,20)
    assert fact['values']['hist2_price_return']=='-0.0500'
    assert '為負' in fact['values']['hist2_result_state']
    assert fact['values']['hist2_report_result_state']=='原報表獲利'
    assert '保證金ROI' not in fact['text']

def case():
    return {'id':'PRIVATE_CASE','account':'PRIVATE_ACCOUNT','source_file':'PRIVATE_SOURCE','side':'BUY','action':'FIRST','lot':'.1','entry':'4000','exit':'4002','profit':'20','currency':'USD','sequence_total':3,
        'sequence':[{'index':1,'side':'BUY','lot':'.1','entry':'4000','exit':'4002','profit':'20','role':'可見首筆','ordering_uncertain':True},
                    {'index':2,'side':'BUY','lot':'.2','entry':'3999','exit':'4002','profit':'60','role':'加倉','currency':'USD'}]}

def test_visible_sequence_is_not_group_profit_and_currency_never_inherits_representative():
    source=case();before=deepcopy(source);result=build_case_operations(source)
    assert source==before
    assert result['representative']['currency']=='USD'
    assert result['rows'][0]['currency'] is None
    assert result['rows'][1]['currency']=='USD'
    assert result['reported_total']==3 and result['provided_rows']==2
    assert result['coverage']=='PARTIAL' and result['rows'][0]['ordering_uncertain']
    assert 'group_profit' not in result
    assert not any(x in json.dumps(result) for x in ['PRIVATE_CASE','PRIVATE_ACCOUNT','PRIVATE_SOURCE'])


def test_each_original_operation_keeps_its_ledger_entry_and_exit_time():
    source=case();source.update(opened_at='2023-10-03T08:00:00',closed_at='2023-10-04T09:30:00')
    source['sequence'][0].update(opened_at='2023-10-03T08:05:00',closed_at='2023-10-04T09:35:00')
    result=build_case_operations(source)
    assert result['representative']['opened_at']=='2023-10-03 08:00:00'
    assert result['rows'][0]['closed_at']=='2023-10-04 09:35:00'
    assert result['rows'][1]['opened_at'] is None

def test_invalid_values_and_missing_sequence_are_unknown_not_zero():
    source=case();source['sequence'][0].update(profit='NaN',entry='inf',lot='-1',currency='NOT_STATED')
    row=build_case_operations(source)['rows'][0]
    assert row['profit'] is None and row['entry'] is None and row['lot'] is None and row['currency'] is None
    source.pop('sequence');result=build_case_operations(source)
    assert result['status']=='UNAVAILABLE' and result['rows']==[]

def test_sequence_is_bounded_and_total_count_never_claims_complete_account():
    source=case();source['sequence']=source['sequence'][:1]*101;source['sequence_total']=101
    result=build_case_operations(source)
    assert len(result['rows'])==100 and result['truncated']
    assert result['provided_rows']==101 and result['coverage']=='PARTIAL'
    source=case();source['sequence_total']=1
    assert build_case_operations(source)['coverage']=='COUNT_CONFLICT'
    source['sequence_total']=2
    result=build_case_operations(source)
    assert result['coverage']=='VISIBLE_ONLY' and '完整帳戶' in ''.join(result['limitations'])
