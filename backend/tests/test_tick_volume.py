import hashlib,json
from pathlib import Path
from backend.tick_volume import tick_frame,NativeTickStore,compare_tick

KEY='a'*64


def bars():
    return [dict(time=i*300,open='100',high='101',low='99',close='100',volume=200 if i==21 else 100) for i in range(1,22)]


def store_files(root):
    folder=root/'ctrader_history_volume_20261030';folder.mkdir()
    profiles=root/'case_candidate_market_profiles.json';profiles.write_text('{}')
    payload=dict(source_key=KEY,interval='5m',start=0,end=7000,bars=bars(),volume_basis='broker_native_tick_count',status='AVAILABLE')
    chunk=folder/'5m-0.json';chunk.write_text(json.dumps(payload))
    manifest=dict(source_key=KEY,profiles_sha256=hashlib.sha256(profiles.read_bytes()).hexdigest(),chunk_hashes={chunk.name:hashlib.sha256(chunk.read_bytes()).hexdigest()},cases={'c':dict(as_of=6600,source_key=KEY)})
    (folder/'case_volume_references_PRIVATE.json').write_text(json.dumps(manifest))
    return chunk


def test_closed_tick_ratio_has_explicit_units_and_excludes_forming_bar():
    rows=bars();result=tick_frame(rows+[dict(rows[-1],time=6600,volume=99999)],6600,KEY)
    assert result['status']=='AVAILABLE' and result['relative_volume_ratio']=='2'
    assert result['last_volume']=='200' and result['prior20_mean']=='100'
    assert result['last_closed_at']==6600 and result['volume_basis']=='broker_native_tick_count'


def test_invalid_missing_zero_gap_and_source_are_not_zero_filled():
    for rows,key,reason in [(bars()[:-1],KEY,'INSUFFICIENT_HISTORY'),(bars()[1:],KEY,'INSUFFICIENT_HISTORY'),
        (bars()[:10]+bars()[11:],KEY,'INSUFFICIENT_HISTORY'),(bars(),None,'SOURCE_UNAVAILABLE')]:
        r=tick_frame(rows,6600,key);assert r['status']=='UNAVAILABLE' and r['reason']==reason and r['relative_volume_ratio'] is None
    rows=bars();rows[2]['time']-=300
    assert tick_frame(rows,6600,KEY)['reason']=='GAPPED_BASELINE'
    rows=bars();rows[-1]['volume']=None
    assert tick_frame(rows,6600,KEY)['reason']=='UNKNOWN_VOLUME'
    rows=bars()
    for b in rows[:-1]:b['volume']=0
    assert tick_frame(rows,6600,KEY)['reason']=='ZERO_BASELINE'
    rows=bars();rows[-1]['volume']=0
    assert tick_frame(rows,6600,KEY)['reason']=='ZERO_TICK_RATIO'


def test_volume_index_is_bound_to_native_chunks_profile_hash_and_case_time(tmp_path):
    chunk=store_files(tmp_path);store=NativeTickStore(tmp_path)
    r=store.reference('c',dict(as_of=6600))
    assert r['status']=='AVAILABLE' and r['relative_volume_ratio']=='2'
    assert store.reference('c',dict(as_of=6900))['reason']=='REFERENCE_TIME_MISMATCH'
    chunk.write_text('{}')
    assert store.reference('c',dict(as_of=6600))['reason']=='VOLUME_INDEX_UNAVAILABLE'


def test_bad_manifest_and_profile_change_fail_closed(tmp_path):
    store_files(tmp_path)
    (tmp_path/'case_candidate_market_profiles.json').write_text('{"changed":true}')
    assert NativeTickStore(tmp_path).reference('c',dict(as_of=6600))['status']=='UNAVAILABLE'
    (tmp_path/'ctrader_history_volume_20261030/case_volume_references_PRIVATE.json').write_text('[]')
    assert NativeTickStore(tmp_path).reference('c',dict(as_of=6600))['reason']=='VOLUME_INDEX_UNAVAILABLE'


def test_pair_volume_requires_same_source_and_two_x_is_inclusive():
    q=tick_frame(bars(),6600,KEY);c=dict(q,relative_volume_ratio='1')
    assert compare_tick(q,c)['passed'] and compare_tick(q,c)['multiplier']=='2'
    assert compare_tick(q,dict(c,relative_volume_ratio='.9'))['reason']=='TICK_RATIO_EXCEEDS_LIMIT'
    assert compare_tick(q,dict(c,source_key='b'*64))['reason']=='SOURCE_MISMATCH'
