import json
import pytest
from research.assistant_evaluation import evaluate_answer, run_study, safe_catalog, summarize_answers, summarize_model_results


FACTS=[dict(id='sample.five',text='樣本窗口淨變動{{sample_change}}%。',values={'sample_change':'0.42'})]


def test_catalog_has_only_fact_templates_no_values_or_account_or_ids():
    payload=safe_catalog(FACTS)
    assert 'values' not in json.dumps(payload) and '0.42' not in json.dumps(payload)
    assert payload['analysis_mode']=='offline_reference_evaluation'


def test_opt_in_false_makes_no_provider_call():
    def provider(*a,**k):raise AssertionError('external call')
    result=evaluate_answer(FACTS,'說明','current_prompt',call_model=False,provider=provider)
    assert result['api_status']=='not_requested' and not result['raw_fully_grounded']


def test_invented_number_is_not_counted_as_original_grounded_answer():
    def provider(*a,**k):return dict(status='ok',text=json.dumps({'sections':[
        dict(title='盤面',text='價格5000。',fact_ids=['sample.five'])]}))
    result=evaluate_answer(FACTS,'說明','current_prompt',call_model=True,provider=provider)
    assert result['api_status']=='ok' and not result['raw_fully_grounded']
    assert result['output_source']=='program_fallback' and '5000' not in result['display_text']


def test_valid_tokens_substitute_locally_and_raw_output_is_kept():
    raw=json.dumps({'sections':[dict(title='盤面',text='樣本變動{{sample_change}}%。',fact_ids=['sample.five'])]})
    def provider(*a,**k):return dict(status='ok',text=raw,model='fake')
    result=evaluate_answer(FACTS,'說明','current_prompt',call_model=True,provider=provider)
    assert result['raw_fully_grounded'] and '0.42' in result['display_text']
    assert result['raw_text']==raw


def test_rate_limit_stops_without_retry_and_marks_remaining_not_attempted(tmp_path):
    calls=[]
    def provider(*a,**k):calls.append(1);return dict(status='rate_limited',text=None)
    samples=[dict(sample_id='S1',question='說明',facts=FACTS),dict(sample_id='S2',question='說明',facts=FACTS)]
    result=run_study(samples,tmp_path,call_model=True,provider=provider)
    assert len(calls)==1
    assert sum(r['api_status']=='not_attempted' for r in result)==3
    assert len(result)==6


@pytest.mark.parametrize('status',['invalid_response','truncated','provider_error'])
def test_any_failed_provider_response_stops_remaining_calls(tmp_path,status):
    calls=[]
    def provider(*a,**k):calls.append(1);return dict(status=status,text=None)
    samples=[dict(sample_id='S1',question='說明',facts=FACTS)]
    rows=run_study(samples,tmp_path,call_model=True,provider=provider)
    assert len(calls)==1 and rows[-1]['api_status']=='not_attempted'


def test_human_answer_summary_keeps_missing_and_final_output_source_separate():
    keys=[dict(answer_id='A1',variant='current_prompt',split='development',source='program_fallback'),
          dict(answer_id='A2',variant='few_shot',split='reserved_review',source='model')]
    rows=[dict(answer_id='A1',reviewer='reviewer_1',faithfulness_1_to_5='4',relevance_1_to_5='3',clarity_1_to_5='5'),
          dict(answer_id='A2',reviewer='reviewer_1',faithfulness_1_to_5='',relevance_1_to_5='',clarity_1_to_5='')]
    result=summarize_answers(keys,rows)
    assert result['current_prompt']['completed']==1 and result['current_prompt']['source_counts']=={'program_fallback':1}
    assert result['few_shot']['completed']==0 and result['few_shot']['mean_clarity'] is None
    with pytest.raises(ValueError,match='DUPLICATE'):summarize_answers(keys,rows+[rows[0]])


def test_fast_rate_limit_is_not_treated_as_fast_successful_answer():
    rows=[dict(variant='few_shot',seconds=4,api_status='ok',raw_fully_grounded=True,repaired=False,output_source='model'),
          dict(variant='few_shot',seconds=.1,api_status='rate_limited',raw_fully_grounded=False,repaired=False,output_source='program_fallback')]
    result=summarize_model_results(rows)['few_shot']
    assert result['mean_seconds_api_ok']==4
    assert result['mean_seconds_all_attempts']==2.05
