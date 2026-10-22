"""Safety boundaries for the local ten-date evidence exporter."""
from copy import deepcopy

import pytest

from research.assistant_case_acceptance import select_real_queries, controlled_probe_queries
from research.test_context_similarity_ab import profile
from backend.context_rules import market_features


def records():
    return [dict(query_id=f'D{i:02}',cohort='broker_10_days',as_of=1700000000+i*604800)
            for i in range(1,11)]


def test_selection_preserves_all_ten_real_dates_regardless_of_output():
    rows=records()
    for i,r in enumerate(rows):r['methods']={'B_medium':{'rows':[] if i%2 else [dict(case_id='x')]}}
    assert [r['query_id'] for r in select_real_queries(list(reversed(rows)))]==[r['query_id'] for r in rows]
    assert len(select_real_queries(rows+[dict(query_id='M01',cohort='monthly_2021_2025',as_of=0)]))==10


def test_duplicate_dates_and_incomplete_broker_cohort_are_rejected():
    rows=records();rows[-1]['as_of']=rows[0]['as_of']
    with pytest.raises(ValueError,match='DISTINCT'):select_real_queries(rows)
    with pytest.raises(ValueError,match='TEN'):select_real_queries(records()[:-1])


def test_controlled_probes_do_not_mutate_or_mislabel_original_query():
    original=profile();before=deepcopy(original)
    probes=controlled_probe_queries(original)
    assert original==before
    assert set(probes)=={'missing_hour','uncertain_event'}
    assert probes['missing_hour']['pre_entry_bars']['1h']==[]
    assert market_features(probes['uncertain_event'])['event']=='BOUNDARY_UNKNOWN'
