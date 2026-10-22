from copy import deepcopy
import json
from backend.case_operations import build_case_operations

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
