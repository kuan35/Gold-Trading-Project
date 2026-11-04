from datetime import datetime,timezone
from decimal import Decimal
import csv,json
import pytest
from backend.history_library import HistoryLibrary,HistoryError

T=int(datetime(2024,1,2,tzinfo=timezone.utc).timestamp())
def write_csv(path,times=None):
    with path.open('w',encoding='utf8',newline='') as f:
        w=csv.writer(f);w.writerow(['timestamp','open','high','low','close','observed_minutes','volume','source','quote_side','volume_status'])
        for i,t in enumerate(times if times is not None else range(T,T+3600*3,300)):
            w.writerow([datetime.fromtimestamp(t,timezone.utc).isoformat(),'2000','2002.01','1999.99',str(Decimal('2000')+Decimal(i)/100),5,'','HistData','BID','UNAVAILABLE'])
def library(tmp_path):
    p=tmp_path/'reference.csv';write_csv(p);lib=HistoryLibrary(tmp_path);lib.build(reference=p);return lib

def test_metadata_and_decimal_aggregate_missing_volume(tmp_path):
    lib=library(tmp_path);m=lib.metadata();assert m['status']=='AVAILABLE';assert m['sources'][0]['count']==36
    r=lib.window(T+3600,interval='1h',limit=10)
    assert len(r['bars'])==3;assert r['bars'][0]['close']==2000.11;assert 'volume' not in r['bars'][0]
    assert r['source']=='reference' and r['quote_side']=='BID'

def test_incomplete_hour_is_not_synthesized_and_gap_is_explicit(tmp_path):
    p=tmp_path/'b.csv';write_csv(p,[T+i*300 for i in range(36) if i!=14]);lib=HistoryLibrary(tmp_path);lib.build(reference=p)
    assert len(lib.window(T,interval='1h',limit=10)['bars'])==2
    r=lib.window(T+14*300,limit=20);assert r['anchor_time']==T+15*300;assert r['shifted'] is True;assert r['gaps']

def test_paging_and_range_do_not_silently_snap_outside_bounds(tmp_path):
    lib=library(tmp_path);first=lib.window(T,limit=10);assert len(first['bars'])==10 and not first['has_before'] and first['has_after']
    after=lib.window(first['bars'][-1]['time'],direction='after',limit=10);assert after['bars'][0]['time']>first['bars'][-1]['time']
    before=lib.window(after['bars'][0]['time'],direction='before',limit=10);assert before['bars']==first['bars']
    assert lib.window(T-86400)['status']=='OUT_OF_RANGE'
    with pytest.raises(HistoryError):lib.window(T,limit=100000)
    with pytest.raises(HistoryError):lib.window(T,interval='1s')

def test_native_and_reference_never_mix_and_live_future_is_excluded(tmp_path):
    p=tmp_path/'b.csv';write_csv(p);folder=tmp_path/'history_native';folder.mkdir()
    bars=[dict(time=T+3600*i,open='3000',high='3002',low='2999',close='3001',volume=20) for i in range(3)]
    (folder/'5m-1.json').write_text(json.dumps(dict(interval='5m',status='AVAILABLE',source_key='private-source',bars=bars)))
    lib=HistoryLibrary(tmp_path);lib.build(reference=p,native=folder,now=T+3600+299)
    r=lib.window(T,source='ctrader_demo');assert len(r['bars'])==1 and r['bars'][0]['open']==3000
    assert 'private-source' not in str(lib.metadata())
    assert lib.window(T,source='reference')['bars'][0]['open']==2000

def test_empty_or_invalid_source_does_not_destroy_previous_index(tmp_path):
    lib=library(tmp_path);old=lib.metadata();p=tmp_path/'bad.csv';p.write_text('bad\nnot a bar\n')
    with pytest.raises(HistoryError):lib.build(reference=p)
    assert lib.metadata()['sources']==old['sources']
    assert HistoryLibrary(tmp_path/'empty').metadata()['status']=='UNAVAILABLE'

def test_latest_hour_only_uses_complete_group_and_labels_shift(tmp_path):
    p=tmp_path/'b.csv';write_csv(p,range(T,T+39*300,300));lib=HistoryLibrary(tmp_path);lib.build(reference=p)
    r=lib.window(T+38*300,interval='1h')
    assert r['status']=='AVAILABLE' and r['anchor_time']==T+7200 and r['shifted']

def test_concurrent_source_change_rolls_back_instead_of_marking_unread_files_indexed(tmp_path,monkeypatch):
    lib=library(tmp_path);old=lib.metadata()['sources'];calls=iter(['before','changed'])
    monkeypatch.setattr(lib,'_fingerprint',lambda *a:next(calls))
    with pytest.raises(HistoryError):lib.build(reference=tmp_path/'reference.csv')
    assert lib.metadata()['sources']==old

def test_all_invalid_rows_preserve_old_index(tmp_path):
    lib=library(tmp_path);old=lib.metadata()['sources'];p=tmp_path/'bad.csv'
    p.write_text('timestamp,open,high,low,close\n2024-01-02T00:00:00Z,2000,1000,100,2000\n')
    with pytest.raises(HistoryError):lib.build(reference=p)
    assert lib.metadata()['sources']==old

def test_metadata_window_interleaving_cannot_mix_index_generations(tmp_path,monkeypatch):
    lib=library(tmp_path);original=lib.metadata;changed=False
    folder=tmp_path/'native';folder.mkdir();(folder/'5m-1.json').write_text(json.dumps(dict(interval='5m',status='AVAILABLE',source_key='private',bars=[dict(time=T,open='3000',high='3002',low='2999',close='3001',volume=1)])))
    def interleave():
        nonlocal changed
        old=original()
        if not changed:
            changed=True;lib.build(reference=tmp_path/'reference.csv',native=folder)
        return old
    monkeypatch.setattr(lib,'metadata',interleave)
    assert lib.window(T)['bars'][0]['open']==3000

def test_unavailable_volume_is_not_reported_as_zero():
    from backend.history_library import bar
    row=dict(time=T,open='2000',high='2001',low='1999',close='2000',volume='0',volume_status='UNAVAILABLE')
    assert bar(row,T+300)[-1] is None

def test_malformed_native_structure_preserves_original_index(tmp_path):
    lib=library(tmp_path);old=lib.metadata()['sources'];folder=tmp_path/'native';folder.mkdir()
    (folder/'5m-1.json').write_text(json.dumps(dict(interval='5m',status='AVAILABLE',source_key='private',bars=None)))
    with pytest.raises(HistoryError):lib.build(reference=tmp_path/'reference.csv',native=folder)
    assert lib.metadata()['sources']==old
