import importlib.util
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

def load(name):
    path=Path(__file__).with_name(name+'.py')
    if not path.exists():path=Path(__file__).parents[1]/'scripts'/ (name+'.py')
    assert path.exists(), 'Missing authorized alignment implementation'
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module
    spec.loader.exec_module(module)
    return module

def test_histdata_fixed_est_even_in_summer():
    m=load('expand_time_alignment')
    dt,bar=m.parse_histdata_line('20250701 120000;3300.10;3301;3299;3300.50;0')
    assert dt==datetime(2025,7,1,17,tzinfo=timezone.utc)
    assert bar['open']==Decimal('3300.10')
    assert bar['volume'] is None

def test_histdata_invalid_ohlc_rejected():
    m=load('expand_time_alignment')
    with pytest.raises(ValueError):m.parse_histdata_line('20250701 120000;3300;3290;3299;3300;0')

def test_duplicate_local_events_do_not_inflate_source_evidence():
    m=load('expand_time_alignment')
    rows=[dict(source='s',record_type='TRADE',gold='True',side='BUY',open_time='2025-01-06 12:01:00',open_price='2600'),
          dict(source='s',record_type='TRADE',gold='True',side='BUY',open_time='2025-01-06 12:02:00',open_price='2600')]*100
    events=m.calibration_events(rows)
    assert len(events['s'])==1

def test_bad_close_never_silently_repaired():
    m=load('expand_time_alignment')
    row=dict(record_type='TRADE',symbol='XAUUSD',gold='True',source='s',record_id='r',open_time='2025-01-06 12:01:00',close_time='2025-01-06 11:59:00',open_price='2600',close_price='2601',timestamp_precision='MINUTE')
    result=m.align_row(row,{'models':['FIXED:120'],'status':'STRONG_PRICE_CANDIDATE'}, {}, {})
    assert 'INVALID_LOCAL_CHRONOLOGY' in result['issues']
    assert result['production_enabled'] is False

def test_equivalent_entry_models_can_disagree_on_exit():
    m=load('expand_time_alignment')
    row=dict(record_type='TRADE',symbol='XAUUSD',gold='True',source='s',record_id='r',open_time='2023-03-15 12:01:00',close_time='2023-04-15 12:01:00',open_price='2600',close_price='2601',timestamp_precision='MINUTE')
    result=m.align_row(row,{'models':['FIXED:120','EU_2_3'],'status':'STRONG_PRICE_CANDIDATE'}, {}, {})
    assert result['open_utc_candidate']=='2023-03-15T10:01:00+00:00'
    assert result['close_utc_candidate']==''
    assert result['close_utc_options_count']==2
    assert result['timezone_status']=='UNKNOWN'

def test_dst_boundary_is_not_forced():
    m=load('expand_time_alignment')
    row=dict(record_type='TRADE',symbol='XAUUSD',gold='True',source='s',record_id='r',open_time='2023-03-12 02:01:00',close_time='2023-03-13 12:01:00',open_price='2600',close_price='2601',timestamp_precision='MINUTE')
    result=m.align_row(row,{'models':['US_2_3'],'status':'STRONG_PRICE_CANDIDATE'}, {}, {})
    assert result['open_utc_candidate']==''
    assert 'DST_BOUNDARY_REQUIRES_EXACT_RULE' in result['issues']

def test_weak_source_does_not_receive_single_utc_candidate():
    m=load('expand_time_alignment')
    row=dict(record_type='TRADE',symbol='XAUUSD',gold='True',source='s',record_id='r',open_time='2025-01-06 12:01:00',close_time='2025-01-06 12:05:00',open_price='2600',close_price='2601',timestamp_precision='MINUTE')
    result=m.align_row(row,{'models':['FIXED:120'],'status':'INSUFFICIENT_COMPARABLE_EVENTS'}, {}, {})
    assert result['open_utc_candidate']==''
    assert result['production_enabled'] is False

def test_no_future_bar_in_candidate_preorder_cutoff():
    m=load('expand_time_alignment')
    row=dict(record_type='TRADE',symbol='XAUUSD',gold='True',source='s',record_id='r',open_time='2025-01-06 12:00:00',close_time='2025-01-06 12:05:00',open_price='2600',close_price='2601',timestamp_precision='MINUTE')
    result=m.align_row(row,{'models':['FIXED:120'],'status':'STRONG_PRICE_CANDIDATE'}, {}, {})
    assert result['last_closed_5m_candidate']=='2025-01-06T09:55:00+00:00'
    assert result['production_enabled'] is False

def test_download_form_ignores_other_forms():
    m=load('expand_time_alignment');form=m.DownloadForm()
    form.feed('<form id="payment"><input name="secret" value="BAD"></form><form id="file_down"><input name="fxpair" value="XAUUSD"></form>')
    assert form.fields=={'fxpair':'XAUUSD'}

def test_unknown_volume_must_not_discard_real_histdata_quotes(tmp_path):
    import zipfile
    m=load('expand_time_alignment');cache=tmp_path/'cache';cache.mkdir()
    with zipfile.ZipFile(cache/'synthetic.zip','w') as z:
        z.writestr('synthetic.csv','20250701 120000;3300;3302;3299;3301;0\n20250701 120100;3301;3303;3300;3302;0\n')
    bars,info=m.build_5m(cache,tmp_path)
    key=int(datetime(2025,7,1,17,tzinfo=timezone.utc).timestamp())
    assert bars[key]==(Decimal(3299),Decimal(3303))
    assert info['partial_5m_bars']==1
    assert info['volume_status']=='UNAVAILABLE'

@pytest.mark.parametrize('precision',[60,300])
def test_end_to_end_all_rows_preserved_and_no_auto_confirmation(tmp_path,precision):
    import csv,json,zipfile
    from datetime import timedelta
    m=load('expand_time_alignment');root=tmp_path/'root'
    raw=root/'交易員資料';raw.mkdir(parents=True);(raw/'raw.txt').write_text('READ ONLY')
    audit=root/'artifacts/behavior_audit_20261001_final';audit.mkdir(parents=True)
    market=root/'artifacts/market_data';market.mkdir(parents=True)
    private=root/'product/private';private.mkdir(parents=True)
    rows=[];market_rows=[];lines=[]
    for i in range(40):
        utc=datetime(2025,1,6,10,tzinfo=timezone.utc)+timedelta(days=i)
        local=utc.replace(tzinfo=None)+timedelta(hours=2)
        rows.append(dict(record_id=str(i),source='SECRET_SOURCE',source_format='CSV',record_type='TRADE',symbol='XAUUSD',gold='True',side='BUY',open_time=local.isoformat(),close_time=(local+timedelta(minutes=1)).isoformat(),open_price='2600',close_price='2601',timestamp_precision='MINUTE'))
        market_rows.append(dict(timestamp=utc.isoformat(),low='2599',high='2602',volume='1'))
        for j in range(2):
            est=utc.replace(tzinfo=None)-timedelta(hours=5)+timedelta(minutes=j)
            lines.append(est.strftime('%Y%m%d %H%M%S')+';2600;2602;2599;2601;0\n')
    rows.append(dict(rows[0],record_id='nongold',gold='False',symbol='EURUSD'))
    rows.append(dict(rows[0],record_id='cash',gold='False',symbol='',record_type='DEPOSIT'))
    for file,data in [(audit/'all_records.csv',rows),(audit/'gold_behavior_records.csv',rows[:40]),(market/'xauusd_5m_bars.csv',market_rows)]:
        with file.open('w',encoding='utf-8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)
    (private/'cases.json').write_text(json.dumps({'cases':[]}),encoding='utf-8')
    output=private/'expanded';cache=output/'histdata_archives';cache.mkdir(parents=True)
    with zipfile.ZipFile(cache/'synthetic.zip','w') as z:z.writestr('synthetic.csv',''.join(lines))
    (output/'integrity_before_PRIVATE.json').write_text(json.dumps(m.snapshot(root)),encoding='utf-8')
    result=output/'result';summary=m.run(root,output,result,calibration_interval=precision)
    saved=list(csv.DictReader((result/'all_records_UTC_candidates_PRIVATE.csv').open(encoding='utf-8-sig')))
    assert len(saved)==len(rows)==summary['record_rows']
    assert summary['row_statuses']['gold_candidate_both_1m_match']==40
    assert summary['confirmed_timezone_rows']==0
    assert all(r['production_enabled']=='False' and r['timezone_status']=='UNKNOWN' for r in saved)
    assert 'SECRET_SOURCE' not in json.dumps(summary)
    assert (raw/'raw.txt').read_text()=='READ ONLY'

def test_empirical_market_clock_correction_is_explicit_and_seasonal():
    m=load('expand_time_alignment')
    summer=datetime(2024,7,11,13,30,tzinfo=timezone.utc)
    winter=datetime(2024,1,11,13,30,tzinfo=timezone.utc)
    assert m.correct_histdata_timestamp(summer,'EST_CLAIM_ONLY')==summer
    assert m.correct_histdata_timestamp(summer,'EMPIRICAL_EU_SHIFT')==datetime(2024,7,11,12,30,tzinfo=timezone.utc)
    assert m.correct_histdata_timestamp(winter,'EMPIRICAL_EU_SHIFT')==winter
    with pytest.raises(ValueError):m.correct_histdata_timestamp(summer,'GUESS')

def test_limited_evidence_has_separate_review_column():
    m=load('expand_time_alignment')
    row=dict(record_type='TRADE',symbol='XAUUSD',gold='True',source='s',record_id='r',open_time='2025-01-06 12:01:00',close_time='2025-01-06 12:05:00',open_price='2600',close_price='2601',timestamp_precision='MINUTE')
    result=m.align_row(row,{'models':['FIXED:120'],'status':'LIMITED_PRICE_CANDIDATE'}, {}, {})
    assert result['open_utc_candidate']==''
    assert result['open_utc_review_candidate']=='2025-01-06T10:01:00+00:00'
    assert result['timezone_status']=='UNKNOWN'
    assert result['production_enabled'] is False

def test_one_minute_recalibration_uses_minute_bucket_not_five_minute():
    from datetime import timedelta
    m=load('expand_time_alignment');events=[];bars={}
    for i in range(30):
        e=m.base.Event(datetime(2025,1,6,12,2)+timedelta(days=i),Decimal(2600))
        events.append(e);t=m.base.utc_stamp(e,'FIXED:120');bars[t]=(Decimal(2599),Decimal(2601))
    summary,_,_=m.base.evaluate(events,bars,interval_seconds=60)
    assert summary['status']=='STRONG_PRICE_CANDIDATE'
    assert summary['best_model']=='FIXED:120'
    assert m.base.evaluate(events,bars)[0]['status']=='NO_MARKET_COVERAGE'
