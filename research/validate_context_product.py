"""Compare product retrieval against the frozen 51-query offline B results.

Reads private fixtures only, writes an aggregate receipt. No API/model/orders.
"""
from pathlib import Path
from hashlib import sha256
import json
import sys
from time import perf_counter

PRODUCT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PRODUCT))
from backend.context_retrieval import ContextIndex
from backend.candidate_sidecar import load_candidate_sidecar


def main():
    frozen=PRODUCT/'private/context_similarity_ab_20261021'
    cases_path=PRODUCT/'private/cases.json'
    profile_path=PRODUCT/'private/case_candidate_market_profiles.json'
    profiles,status=load_candidate_sidecar(cases_path,profile_path,PRODUCT/'private')
    assert status=='READY',status
    cases=json.loads(cases_path.read_text(encoding='utf8'))['cases']
    records=json.loads((frozen/'queries_PRIVATE.json').read_text(encoding='utf8'))
    queries=json.loads((frozen/'plot_profiles_PRIVATE.json').read_text(encoding='utf8'))['queries']
    start=perf_counter();index=ContextIndex(cases,profiles);lookup={c['id']:c for c in cases}
    checked=passed=shown=0;query_seconds=[]
    for record in records:
        before=perf_counter()
        group=lookup[record['query_case_id']]['group'] if record['query_case_id'] else None
        result=index.retrieve(queries[record['query_id']],record['side'],exclude_group=group)
        query_seconds.append(perf_counter()-before)
        expected=record['methods']['B_medium']
        assert [c['id'] for c in result['cases']]==[c['case_id'] for c in expected['rows']],record['query_id']
        assert result['total']==expected['passed_unique']
        assert result['comparison']['rejections']==expected['rejections']
        for actual,old in zip(result['cases'],expected['rows']):
            for new_key,old_key in [('path_distance_pct','d5'),('hour_path_distance_pct','d1h'),('tail_path_distance_pct','dtail'),('volatility_ratio','vol_ratio')]:
                assert abs(actual[new_key]-old[old_key])<1e-10
            checked+=1
        passed+=bool(result['cases']);shown+=len(result['cases'])
    receipt=dict(status='PASS',method='context_contract_v1',queries=len(records),queries_with_output=passed,
        displayed_pairs_checked=checked,shown=shown,elapsed_seconds=perf_counter()-start,
        max_query_seconds=max(query_seconds),mean_query_seconds=sum(query_seconds)/len(query_seconds),
        frozen_results_sha256=sha256((frozen/'queries_PRIVATE.json').read_bytes()).hexdigest(),
        tolerance_calibrated=False,network_calls=0,order_calls=0,
        source_sha256={name:sha256((PRODUCT/name).read_bytes()).hexdigest() for name in (
            'backend/context_rules.py','backend/context_retrieval.py','backend/cases.py','backend/app.py',
            'research/validate_context_product.py')})
    (PRODUCT/'private/context_product_validation_20261021.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
    print(json.dumps(receipt),flush=True)


if __name__=='__main__':main()
