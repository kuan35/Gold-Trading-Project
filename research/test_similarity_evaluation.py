import csv
import json
from datetime import datetime, timezone
import pytest
from research.similarity_evaluation import select_queries, blind_packet, write_review_csv, summarize_reviews


def candidates():
    base=int(datetime(2024,1,1,tzinfo=timezone.utc).timestamp())
    return [dict(case_id=f'private-{n}',group=f'g{n}',as_of=base+n*86400,
                 window_start=base+n*86400-20*3600,window_end=base+n*86400,
                 side='BUY' if n%2 else 'SELL') for n in range(140)]


def test_selection_stable_distinct_dates_windows_groups_and_excluded_date():
    rows=candidates();exclude={'2024-01-06'}
    a=select_queries(rows,exclude,30);b=select_queries(list(reversed(rows)),exclude,30)
    assert a==b and len(a)==30
    assert len({r['group'] for r in a})==30
    assert '2024-01-06' not in {datetime.fromtimestamp(r['as_of'],timezone.utc).date().isoformat() for r in a}
    ordered=sorted(a,key=lambda r:r['as_of'])
    assert all(x['window_end']<=y['window_start'] for x,y in zip(ordered,ordered[1:]))
    assert {r['side'] for r in a}=={'BUY','SELL'}


def test_insufficient_distinct_windows_does_not_silently_relax():
    rows=candidates()[:5]
    with pytest.raises(ValueError,match='INSUFFICIENT'):select_queries(rows,set(),30)


def test_blind_data_contains_no_dates_ids_method_profit_or_absolute_price():
    bars=[dict(time=1800000000+i*300,open='4000',high='4002',low='3999',close='4001') for i in range(60)]
    profile={'private_id':'SECRET','profit':'123','pre_entry_bars':{'5m':bars,'1h':bars[-20:]}}
    packet=blind_packet('P001',profile,profile,'BUY')
    text=json.dumps(packet)
    for forbidden in ['SECRET','profit','method','180000','4000','case_id','as_of']:assert forbidden not in text
    assert len(packet['query']['5m'])==60 and len(packet['candidate']['1h'])==20


def test_review_file_created_once_and_blank_scores_do_not_become_no(tmp_path):
    path=tmp_path/'review.csv';assert write_review_csv(path,['P1'],'reviewer_1')
    original=path.read_bytes();assert not write_review_csv(path,['P2'],'two')
    assert path.read_bytes()==original
    rows=list(csv.DictReader(path.open(encoding='utf-8-sig')))
    result=summarize_reviews([dict(pair_id='P1',methods=['current','baseline'])],rows)
    assert result['methods']['current']['rated']==0
    assert result['methods']['current']['yes_rate_decidable'] is None
    assert result['agreement']['kappa'] is None


def test_method_dedup_keeps_shared_pair_in_both_denominators_and_counts_insufficient():
    keys=[dict(pair_id='P1',methods=['current','baseline']),dict(pair_id='P2',methods=['baseline'])]
    rows=[dict(pair_id='P1',reviewer='reviewer_1',overall='yes'),dict(pair_id='P1',reviewer='reviewer_2',overall='yes'),
          dict(pair_id='P2',reviewer='reviewer_1',overall='insufficient')]
    result=summarize_reviews(keys,rows)
    assert result['methods']['current']['rated']==2
    assert result['methods']['baseline']['insufficient']==1
    assert result['agreement']['paired']==1 and result['agreement']['kappa'] is None
    with pytest.raises(ValueError,match='DUPLICATE'):summarize_reviews(keys,rows+[rows[0]])
    with pytest.raises(ValueError,match='UNKNOWN'):summarize_reviews(keys,[dict(pair_id='OTHER',reviewer='reviewer_1',overall='yes')])


def test_deleted_blank_rows_and_missing_reviewer_do_not_shrink_denominator():
    keys=[dict(pair_id='P1',methods=['current']),dict(pair_id='P2',methods=['current'])]
    result=summarize_reviews(keys,[dict(pair_id='P1',reviewer='reviewer_1',overall='yes')])
    assert result['methods']['current']['assigned']==4
    assert result['methods']['current']['unfilled']==3
