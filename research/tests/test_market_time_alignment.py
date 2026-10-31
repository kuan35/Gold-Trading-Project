"""Synthetic clock evidence; never require private trade files."""
import csv
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

SCRIPT=Path(__file__).resolve().parents[2]/'research/scripts/audit_market_time_alignment.py'
if not SCRIPT.exists():
    SCRIPT=Path(__file__).with_name('audit_market_time_alignment.py')
spec=importlib.util.spec_from_file_location('time_alignment_audit',SCRIPT)
mod=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=mod
spec.loader.exec_module(mod)


def test_us_eu_march_disagree():
    dt=datetime(2023,3,15,12)
    assert mod.offset_minutes('US_2_3',dt)==180
    assert mod.offset_minutes('EU_2_3',dt)==120


def test_us_eu_october_disagree():
    dt=datetime(2023,10,31,12)
    assert mod.offset_minutes('US_2_3',dt)==180
    assert mod.offset_minutes('EU_2_3',dt)==120


def test_trade_execution_bar_is_not_feature_bar():
    event=mod.Event(datetime(2025,1,6,12,4),Decimal('2600'))
    execution=mod.execution_bar(event,'FIXED:120')
    assert datetime.fromtimestamp(execution,timezone.utc).hour==10
    assert mod.latest_closed_bar(event,'FIXED:120')+300==execution
    assert mod.latest_closed_bar(mod.Event(datetime(2025,1,6,12,0),event.price),'FIXED:120')==execution-300


def test_price_gap_and_missing_bar():
    event=mod.Event(datetime(2025,1,6,12),Decimal('2602'))
    key=mod.execution_bar(event,'FIXED:120')
    assert mod.gap(event,'FIXED:120',{key:(Decimal('2600'),Decimal('2601'))})==Decimal(1)
    assert mod.gap(event,'FIXED:120',{}) is None


def test_all_offsets_and_boundary_buffer():
    assert len(mod.models())==107
    assert 'FIXED:480' in mod.models()
    assert mod.boundary_day(datetime(2023,3,13))
    assert not mod.boundary_day(datetime(2023,3,15))


def test_batches_and_profit_cannot_change_events(tmp_path):
    file=tmp_path/'rows.csv'
    fields=['source','source_format','record_type','side','open_time','open_price','profit']
    rows=[dict(source='PRIVATE',source_format='CSV',record_type='TRADE',side='BUY',
               open_time='2025-01-06T12:01:00',open_price='2600',profit='-999'),
          dict(source='PRIVATE',source_format='CSV',record_type='TRADE',side='BUY',
               open_time='2025-01-06T12:02:00',open_price='2601',profit='999')]
    def save():
        with file.open('w',newline='',encoding='utf-8') as stream:
            writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    save(); first=mod.read_events(file)
    rows[0]['profit']='100000';rows[1]['profit']='-100000'
    save(); second=mod.read_events(file)
    assert first==second
    assert len(first[0]['PRIVATE'])==1
    assert first[1]['same_local_5m_batch']==1


def test_common_coverage_and_heldout_split():
    events=[mod.Event(datetime(2025,1,6)+timedelta(days=i,hours=12),Decimal(2600+i)) for i in range(40)]
    bars={}
    for e in events:
        for m in mod.models():
            key=mod.execution_bar(e,m)
            expected=e.price if mod.offset_minutes(m,e.local)==120 else e.price+100
            bars[key]=(expected-Decimal('.1'),expected+Decimal('.1'))
    result,scores,_=mod.evaluate(events,bars)
    assert result['train_events']==24 and result['validation_events']==16
    assert result['status']=='STRONG_PRICE_CANDIDATE'
    assert result['production_enabled'] is False
    assert result['timezone_status']=='UNKNOWN'
    assert result['equivalent_models']==['FIXED:120','US_2_3','EU_2_3']


def test_wrong_later_period_fails_candidate():
    events=[mod.Event(datetime(2025,1,6)+timedelta(days=i,hours=12),Decimal(2600+i)) for i in range(40)]
    bars={}
    for i,e in enumerate(events):
        for m in mod.models():
            key=mod.execution_bar(e,m)
            target=120 if i<24 else 180
            value=e.price if mod.offset_minutes(m,e.local)==target else e.price+100
            bars[key]=(value,value)
    result,_,_=mod.evaluate(events,bars)
    assert result['status']=='PRICE_MISMATCH'


def test_no_market_does_not_confirm():
    result,_,_=mod.evaluate([mod.Event(datetime(2025,1,6),Decimal(2600))],{})
    assert result['status']=='NO_MARKET_COVERAGE'
    assert result['best_model'] is None


def test_missing_market_not_scored_as_zero_gap():
    e=mod.Event(datetime(2025,1,6),Decimal(2600))
    bars={mod.execution_bar(e,'FIXED:120'):(Decimal(2600),Decimal(2600))}
    result,_,_=mod.evaluate([e],bars)
    assert result['covered_events']==1 and result['common_events']==1
    assert result['status']=='INSUFFICIENT_COMPARABLE_EVENTS'


def test_missing_quotes_share_denominator():
    value=mod.metrics([Decimal(0),None,None,None])
    assert value['n']==4 and value['missing']==3
    assert mod.rate(value)==.25
    assert value['median_gap']=='0'
