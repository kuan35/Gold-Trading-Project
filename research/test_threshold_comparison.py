from math import isclose

from research.threshold_comparison import configurations, compare_outputs, fixed_score, summarize


def row(cid,group,**kwargs):
    return dict(case_id=cid,group=group,d5=.10,d1h=.20,dtail=.04,vol_ratio=1.2,**kwargs)


def record(qid,split,medium,variant):
    return dict(query_id=qid,split=split,methods={
        'medium':dict(rows=medium,passed_unique=len(medium),status='PASSED' if medium else 'NO_RULE_MATCH'),
        'test':dict(rows=variant,passed_unique=len(variant),status='PASSED' if variant else 'NO_RULE_MATCH')})


def test_thirteen_frozen_variants_and_one_at_a_time():
    configs=configurations();assert len(configs)==13
    base=configs['medium']['limits']
    for name,c in configs.items():
        if c['kind']=='single':assert sum(base[k]!=c['limits'][k] for k in base)==1
    assert isclose(configs['minus10']['limits']['vol_ratio'],1.9)
    assert isclose(configs['plus10']['limits']['dtail'],.11)


def test_no_outputs_do_not_count_as_perfect_stability():
    m=compare_outputs([],[])
    assert m['top1_same_case'] is None and m['top5_group_jaccard'] is None
    assert compare_outputs([row('a','g')],[])['top1_same_group'] is None


def test_group_stability_is_not_confused_with_identical_order():
    c=compare_outputs([row('a','g1'),row('b','g2')],[row('a2','g1'),row('c','g3')])
    assert c['top1_same_case'] is False and c['top1_same_group'] is True
    assert isclose(c['top5_group_jaccard'],1/3)


def test_fixed_score_uses_medium_scale_not_current_variant():
    r=row('x','g');r.update(d5=.25,d1h=.50,dtail=.10,vol_ratio=2)
    assert fixed_score(r)==1
    r['d5']=.30;assert isclose(fixed_score(r),1.2)


def test_full_denominator_and_common_queries_separate():
    a=row('a','g');b=row('b','h');b['d5']=.20
    records=[record('q1','development',[a],[b]),record('q2','development',[],[a]),
             record('q3','reserved_review',[],[]),record('q4','reserved_review',[a],[])]
    s=summarize(records,{'medium':{},'test':{}})['all']['test']
    assert s['queries']==4 and s['with_output']==2 and s['coverage']==.5
    assert s['common_queries']==1 and s['only_variant']==1 and s['only_medium']==1
    assert s['common_variant']['d5']==.20 and s['common_medium']['d5']==.10
    assert s['top1_group_agreement']==0
    assert summarize(records,{'medium':{},'test':{}})['reserved_review']['test']['queries']==2


def test_common_metrics_missing_when_no_joint_outputs():
    s=summarize([record('q','development',[row('a','g')],[])],{'medium':{},'test':{}})['all']['test']
    assert s['common_variant'] is None and s['top1_group_agreement'] is None
