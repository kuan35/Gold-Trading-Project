from backend.case_context import build_case_context
from backend.tests.test_tick_context import fixture,Volumes
from backend.context_retrieval import ContextIndex


def retrieval():
    cases,profiles,q=fixture()
    return ContextIndex(cases,profiles,tick_volume_store=Volumes()).retrieve(q,'BUY')


def test_tick_gate_is_fifth_condition_and_numeric_values_stay_local():
    from backend.live_assistant import writer_facts
    import json
    result=build_case_context(retrieval())
    assert result['status']=='PASSED' and result['tick_volume']['enabled']
    case=result['cases'][0]
    assert case['metrics'][-1]['key']=='tick_ratio' and case['metrics'][-1]['actual']=='2.00000'
    assert case['tick_activity']==dict(query_relative='2',case_relative='1',multiplier='2',limit='2')
    assert 'history.tick_volume' in [f['id'] for f in result['facts']]
    payload=json.dumps(writer_facts(result['facts']),ensure_ascii=False)
    assert '非成交量' in payload and 'hist1_tick_ratio' in payload and 'source_key' not in payload


def test_claimed_volume_pass_is_rejected_if_fifth_condition_missing_or_over_limit():
    for value in (None,dict(passed=True,multiplier='2.01'),dict(passed=False,multiplier='1')):
        r=retrieval();r['cases'][0]['tick_comparison']=value
        assert build_case_context(r)['status']=='INSUFFICIENT_DATA'
