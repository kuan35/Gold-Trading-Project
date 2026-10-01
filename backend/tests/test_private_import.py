import csv
import importlib.util
from pathlib import Path

SCRIPT=Path(__file__).resolve().parents[2]/'scripts'/'import_private_data.py'
spec=importlib.util.spec_from_file_location('private_import',SCRIPT)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_unknown_timezone_is_conservative_and_same_group_not_multiplied(tmp_path):
    path=tmp_path/'records.csv'
    base=dict(record_id='r1',source_format='CSV',scope='C1',behavior='NO_OBSERVED_POSITION',side='BUY',
              open_time='2025-01-01 00:00:00',close_time='2025-01-01 01:00:00',lot='0.1',open_price='2500',close_price='2490',
              profit='-100',currency='',observed_overlap_group='G1',identical_signature_candidate_count='1',cross_source_duplicate_candidate='False')
    duplicate=dict(base,record_id='r2',identical_signature_candidate_count='2')
    tie=dict(base,record_id='r3',behavior='TIME_TIE')
    cross=dict(base,record_id='r4',cross_source_duplicate_candidate='True')
    with path.open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(base));writer.writeheader();writer.writerows([base,duplicate,tie,cross])
    cases=module.load_cases(path)
    assert len(cases)==1
    assert cases[0]['time_alignment']=='unknown'
    assert cases[0]['available_at']==1735743660  # Jan1 15:01 UTC: unknown ±14h, minute upper bound
    assert cases[0]['currency']=='UNKNOWN'
    assert 'source' not in cases[0] and 'ticket_hash' not in cases[0]
    assert cases[0]['market'] is None
