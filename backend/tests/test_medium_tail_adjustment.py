from backend.context_rules import LIMITS,evaluate_rows


def row(identity,tail):
    return dict(case_id=identity,group=identity,d5=.01,d1h=.01,dtail=tail,vol_ratio=1,
        query_event='IN_RANGE',case_event='IN_RANGE',query_tail='U',case_tail='U')


def test_new_medium_tail_includes_exact_boundary_and_normalizes_ranking_by_point12():
    limits=LIMITS['medium']
    assert limits==dict(d5=.25,d1h=.5,dtail=.12,vol_ratio=2)
    rows=[row('inside',.11),row('edge',.12),row('outside',.120001)]
    descriptions={r['case_id']:dict(end_5m=i,end_1h=i) for i,r in enumerate(rows)}
    result=evaluate_rows(rows,descriptions,limits)
    assert result['_passed_ids']=={'inside','edge'}
    assert result['rows'][0]['score_max']==.11/.12
    assert result['rejections']['tail_path']==1
