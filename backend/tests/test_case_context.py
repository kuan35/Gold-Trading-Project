import json
from copy import deepcopy
import pytest
from backend.case_context import build_case_context


def retrieval(status='PASSED'):
    return dict(rule_status=status,total=2,query_side='BUY',query_as_of_utc=1800000000,
        comparison=dict(method='context_contract_v1',eligible_rows=8,query_event_label='區間內活動',query_tail_direction='上行',
            thresholds=dict(d5=.25,d1h=.5,dtail=.1,vol_ratio=2),rejections={'five_path':3},reason='program reason'),
        cases=[dict(id='PRIVATE_CASE',group='PRIVATE_GROUP',profit='9999',account='ACCOUNT',side='BUY',
            path_distance_pct=.12,hour_path_distance_pct=.2,tail_path_distance_pct=.04,volatility_ratio=1.3,
            event_label='區間內活動',tail_direction='上行',context_check={'passed':True})] if status=='PASSED' else [])


def test_case_context_reports_actual_distances_without_leaking_private_fields_to_facts():
    r=build_case_context(retrieval(),snapshot_id='snapshot')
    assert r['status']=='PASSED' and r['counts']==dict(eligible=8,passed=2,displayed=1)
    assert r['cases'][0]['metrics'][0]['actual']=='0.12000'
    assert r['cases'][0]['metrics'][0]['tolerance']=='0.25000'
    assert r['cases'][0]['case_id']=='PRIVATE_CASE' # Local chart linkage only.
    encoded=json.dumps(r['facts'],ensure_ascii=False)
    assert all(value not in encoded for value in ['PRIVATE_CASE','PRIVATE_GROUP','9999','ACCOUNT'])
    assert 'snapshot' not in encoded
    assert r['snapshot_id']=='snapshot'


@pytest.mark.parametrize('status',['INSUFFICIENT_DATA','NO_COMPARABLE_CASES','UNCERTAIN_EVENT','NO_RULE_MATCH'])
def test_zero_states_have_distinct_meaning_and_no_fabricated_case(status):
    r=build_case_context(retrieval(status))
    assert r['status']==status and not r['cases']
    assert r['label'] and r['reason']
    assert r['counts']['passed'] is None if status=='INSUFFICIENT_DATA' else r['counts']['passed']==0


def test_missing_metric_is_unknown_and_does_not_become_zero_or_rule_pass():
    source=retrieval();del source['cases'][0]['path_distance_pct']
    r=build_case_context(source)
    assert r['status']=='INSUFFICIENT_DATA' and not r['cases']
    assert r['counts']['passed'] is None


def test_non_context_method_cannot_borrow_context_passed_wording():
    source=retrieval();source['comparison']['method']='path_indicator_pattern_v1'
    assert build_case_context(source)['status']=='INSUFFICIENT_DATA'


@pytest.mark.parametrize('metric',[None,'NaN','-1','0.250001'])
def test_passed_result_with_contradictory_metric_fails_closed(metric):
    r=retrieval();r['cases'][0]['path_distance_pct']=metric
    assert build_case_context(r)['status']=='INSUFFICIENT_DATA'


@pytest.mark.parametrize('case',[None,[],{'id':'broken','context_check':None}])
def test_malformed_case_row_fails_closed(case):
    r=retrieval();r['cases']=[case]
    assert build_case_context(r)['status']=='INSUFFICIENT_DATA'


def test_representative_is_original_single_row_and_distribution_uses_entire_deduplicated_pool():
    source=retrieval()
    source.update(total=7,wins=3,losses=2,flat=1,unknown=1)
    source['cases'][0].update(profit='-13.920',currency='NOT_STATED',action='ADD',lot='0.020',
        sequence=[dict(profit='1234.567'),dict(profit='7654.321')],group_profit='8888.888')
    r=build_case_context(source)
    assert r['cases'][0]['representative']==dict(result='LOSS',profit='-13.920',currency=None,
        currency_stated=False,side='BUY',action='ADD',lot='0.020')
    assert r['distribution']==dict(total=7,wins=3,losses=2,flat=1,unknown=1,
        basis='符合群代表單筆的歷史結果分布')
    encoded=json.dumps(r['facts'],ensure_ascii=False)
    assert all(secret not in encoded for secret in ['-13.920','0.020','PRIVATE_CASE','PRIVATE_GROUP','1234.567','7654.321','8888.888'])


@pytest.mark.parametrize('profit,result,expected', [('0','FLAT','0'),('17.30','WIN','17.30'),
    (None,'UNKNOWN',None),('NaN','UNKNOWN',None),('Infinity','UNKNOWN',None),('', 'UNKNOWN', None)])
def test_representative_missing_or_nonfinite_profit_stays_unknown(profit,result,expected):
    source=retrieval();source['cases'][0].update(profit=profit,currency='USD')
    representative=build_case_context(source)['cases'][0]['representative']
    assert representative['result']==result and representative['profit']==expected
    assert representative['currency']=='USD' and representative['currency_stated'] is True


def test_distribution_never_reconstructs_missing_or_contradictory_aggregate_from_displayed_cases():
    source=retrieval()
    expected=dict(total=None,wins=None,losses=None,flat=None,unknown=None,
        basis='符合群代表單筆的歷史結果分布')
    assert build_case_context(source)['distribution']==expected
    source.update(wins=1,losses=0,flat=0,unknown=0)
    assert build_case_context(source)['distribution']==expected
    source.update(total=0,wins=0,losses=0,flat=0,unknown=0,rule_status='NO_RULE_MATCH',cases=[])
    assert build_case_context(source)['distribution']['total']==0


def test_external_explanation_payload_does_not_include_new_local_representative_values(monkeypatch):
    from backend import live_assistant
    source=retrieval()
    source.update(wins=1,losses=1,flat=0,unknown=0)
    source['cases'][0].update(profit='-98765.4321',currency='USD',lot='0.03789',action='ADD')
    detail=build_case_context(source)
    facts=detail.pop('facts')
    context=dict(source='ctrader_demo_xauusd',as_of_utc='2027-01-15T08:00:00+00:00',
        quote_time_utc='2027-01-15T08:00:00+00:00',status='CURRENT',facts=facts,case_comparison=detail)
    payloads=[]
    def explain(_draft,_question,*,catalog,system_prompt):
        payloads.append(catalog)
        return dict(status='unavailable')
    monkeypatch.setattr(live_assistant,'explain_context',explain)
    answer=live_assistant.respond_context(context,'相似案例差距在哪？',enabled=True)
    assert answer['case_comparison']['cases'][0]['representative']['profit']=='-98765.4321'
    assert len(payloads)==1
    encoded=json.dumps(payloads[0],ensure_ascii=False)
    assert all(value not in encoded for value in ['-98765.4321','0.03789','PRIVATE_CASE','PRIVATE_GROUP','ACCOUNT'])
    assert 'representative' not in encoded and 'distribution' not in encoded
