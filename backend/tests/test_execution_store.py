import csv,json,hashlib
from datetime import datetime,timezone
from pathlib import Path
from backend import execution_store as module

SOURCE={'id':'case','side':'BUY','entry':'2000','exit':'2010'}


def fixture(tmp_path,monkeypatch,slots=303,missing=(),incomplete=()):
    opened=301;end=300+(slots-1)*300
    profile=dict(as_of=opened,reference_open_utc=opened,reference_close_utc=end+40,reference_clock_basis='source_model_scenario')
    (tmp_path/'cases.json').write_text(json.dumps({'cases':[SOURCE]}))
    (tmp_path/'ledger.json').write_text('[]')
    (tmp_path/'case_candidate_market_profiles.json').write_text(json.dumps({'inputs':{
        'bars':{'path':'bars.csv'},'alignment':{'path':'ledger.json'}}}))
    with (tmp_path/'bars.csv').open('w',newline='',encoding='utf-8') as handle:
        writer=csv.DictWriter(handle,fieldnames=['timestamp','open','high','low','close','observed_minutes','source','quote_side']);writer.writeheader()
        for t in range(300,end+300,300):
            if t in missing:continue
            writer.writerow(dict(timestamp=datetime.fromtimestamp(t,timezone.utc).isoformat(),open='2000',high='2011',low='1999',close='2001',observed_minutes=4 if t in incomplete else 5,source='HistData',quote_side='BID'))
    monkeypatch.setattr(module,'load_candidate_sidecar',lambda *a:({'case':profile},'READY'))
    return profile,end+300


def legacy(tmp_path,profile):
    paths={'cases':'cases.json','profiles':'case_candidate_market_profiles.json','bars':'bars.csv','alignment':'ledger.json'}
    a,b=profile['reference_open_utc']//300*300,profile['reference_close_utc']//300*300
    times=list(range(a,b+300,300))
    value={'method':'execution_reference_v1','inputs':{key:{'path':name,'sha256':hashlib.sha256((tmp_path/name).read_bytes()).hexdigest()} for key,name in paths.items()},
        'records':{'case':{'times':times,'close_times':[],'mode':'CONTIGUOUS'}},
        'bars':{str(t):dict(time=t,open=2000,high=2011,low=1999,close=2001) for t in times}}
    (tmp_path/'case_execution_bars.json').write_text(json.dumps(value))


def test_full_holding_builder_loads_long_middle_and_keeps_v1_file(tmp_path,monkeypatch):
    profile,cutoff=fixture(tmp_path,monkeypatch)
    old=tmp_path/'case_execution_bars.json';old.write_text('do-not-overwrite')
    summary=module.build(tmp_path)
    assert Path(summary['path']).name=='case_execution_bars_v2.json'
    assert old.read_text()=='do-not-overwrite'
    value=module.ExecutionStore(tmp_path).get('case',profile,SOURCE,cutoff)
    assert value['status']=='AVAILABLE' and value['mode']=='FULL_HOLDING'
    assert len(value['bars'])==303 and not value['close_bars']
    assert value['coverage']==dict(scope='WHOLE_REFERENCE_HOLDING',calendar_slots=303,available_bars=303,gap_slots=0)
    assert [m['action'] for m in value['markers']]==['ENTRY','CLOSE']


def test_internal_gaps_and_incomplete_minutes_are_not_synthesized(tmp_path,monkeypatch):
    profile,cutoff=fixture(tmp_path,monkeypatch,missing=(900,),incomplete=(1200,))
    module.build(tmp_path)
    value=module.ExecutionStore(tmp_path).get('case',profile,SOURCE,cutoff)
    assert value['status']=='AVAILABLE' and len(value['bars'])==301
    assert value['coverage']['gap_slots']==2
    assert not {900,1200}&{b['time'] for b in value['bars']}


def test_missing_endpoint_cutoff_and_invalid_query_time_fail_closed(tmp_path,monkeypatch):
    profile,cutoff=fixture(tmp_path,monkeypatch,missing=(300,))
    module.build(tmp_path);store=module.ExecutionStore(tmp_path)
    assert store.get('case',profile,SOURCE,cutoff)['status']=='UNAVAILABLE'
    profile,cutoff=fixture(tmp_path,monkeypatch)
    module.build(tmp_path);store=module.ExecutionStore(tmp_path)
    for boundary in (profile['reference_close_utc']-1,profile['reference_close_utc']+1,float('nan'),float('inf'),None):
        assert store.get('case',profile,SOURCE,boundary)['status']=='UNAVAILABLE'


def test_v2_input_changes_are_rejected_and_invalid_v2_never_falls_back(tmp_path,monkeypatch):
    profile,cutoff=fixture(tmp_path,monkeypatch,slots=3);legacy(tmp_path,profile)
    module.build(tmp_path);store=module.ExecutionStore(tmp_path)
    assert store.get('case',profile,SOURCE,cutoff)['status']=='AVAILABLE'
    with (tmp_path/'bars.csv').open('a') as handle:handle.write('\n')
    assert store.get('case',profile,SOURCE,cutoff)['status']=='UNAVAILABLE'
    # An intact v1 is used only if v2 does not exist, never if v2 is invalid.
    profile,cutoff=fixture(tmp_path,monkeypatch,slots=3);legacy(tmp_path,profile)
    (tmp_path/'case_execution_bars_v2.json').write_text('{"method":"wrong"}')
    assert module.ExecutionStore(tmp_path).get('case',profile,SOURCE,cutoff)['status']=='UNAVAILABLE'
    (tmp_path/'case_execution_bars_v2.json').unlink()
    assert module.ExecutionStore(tmp_path).get('case',profile,SOURCE,cutoff)['status']=='AVAILABLE'


def test_display_limit_explicitly_keeps_endpoint_windows(tmp_path,monkeypatch):
    monkeypatch.setattr(module,'MAX_HOLDING_SLOTS',4)
    profile,cutoff=fixture(tmp_path,monkeypatch,slots=19)
    module.build(tmp_path)
    value=module.ExecutionStore(tmp_path).get('case',profile,SOURCE,cutoff)
    assert value['status']=='AVAILABLE' and value['mode']=='SEPARATE_CLOSE'
    assert value['coverage']==dict(scope='ENDPOINT_WINDOWS',calendar_slots=19,available_bars=13,gap_slots=6)
    assert len(value['bars'])==1 and len(value['close_bars'])==12


def test_malformed_v2_roots_do_not_abort_analysis(tmp_path,monkeypatch):
    profile,cutoff=fixture(tmp_path,monkeypatch,slots=3)
    for malformed in (None,[],42,{'method':'execution_reference_v2','inputs':None}):
        (tmp_path/'case_execution_bars_v2.json').write_text(json.dumps(malformed))
        assert module.ExecutionStore(tmp_path).get('case',profile,SOURCE,cutoff)['status']=='UNAVAILABLE'


def test_v1_payload_under_v2_name_is_rejected_without_silent_downgrade(tmp_path,monkeypatch):
    profile,cutoff=fixture(tmp_path,monkeypatch,slots=3);legacy(tmp_path,profile)
    v1=(tmp_path/'case_execution_bars.json').read_text()
    (tmp_path/'case_execution_bars_v2.json').write_text(v1)
    assert module.ExecutionStore(tmp_path).get('case',profile,SOURCE,cutoff)['status']=='UNAVAILABLE'
    assert module.ExecutionStore(tmp_path,prefer_full=False).get('case',profile,SOURCE,cutoff)['status']=='AVAILABLE'
