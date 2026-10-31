import json
import pytest
from scripts import assistant_acceptance as acceptance


def reply(system,prompt,**kwargs):
    catalog=json.loads(prompt.split('\ncontext:\n',1)[1])
    if catalog.get('focus'):
        sections=[dict(title=title,text=text,fact_ids=['history.case1']) for title,text in zip(
            acceptance.case_review.COMPACT_TITLES,
            ['{{c1_similarities_state}}。','{{c1_differences_state}}。',
             '已知最大逆向{{c1_observed_mae}}%。{{c1_observation_basis_state}}。'])]
    else:
        sections=[dict(title='資料狀態',text='{{history_status_state}}；{{history_reason_state}}。',fact_ids=['history.status'])]
    return dict(status='ok',provider='claude_code',model='sonnet',requested_effort='medium',text=json.dumps({'sections':sections}))


def test_synthetic_preview_and_success_budget(tmp_path):
    payload=acceptance.preview(tmp_path)
    assert [e['scenario'] for e in payload['exchanges']]==['buy','sell','no_match','gapped','insufficient']
    assert payload['maximum_calls']==5 and payload['synthetic_only'] and not payload['images']
    for exchange in payload['exchanges']:
        for fact in exchange['catalog']['facts']:
            assert 'values' not in fact
        text=json.dumps(exchange['catalog'])
        assert 'opened_at' not in text and 'anchor_price' not in text and '"bars"' not in text
    result=acceptance.run(allowed=True,directory=tmp_path,infer=reply)
    assert result['attempted']==5 and not result['stopped']
    assert all(r['status']=='ok' for r in result['results'])
    assert '時間間隔' in result['results'][3]['response']['message']
    with pytest.raises(ValueError,match='already started'):
        acceptance.run(allowed=True,directory=tmp_path,infer=reply)


def test_failure_stops_without_retry_and_gate_never_calls(tmp_path):
    acceptance.preview(tmp_path);calls=[]
    def fail(*args,**kwargs):
        calls.append(1)
        return dict(status='timeout',provider='claude_code',model='sonnet')
    with pytest.raises(ValueError,match='explicit'):
        acceptance.run(directory=tmp_path,infer=fail)
    assert not calls
    result=acceptance.run(allowed=True,directory=tmp_path,infer=fail)
    assert len(calls)==result['attempted']==1 and result['stopped']
    assert result['results'][0]['status']=='timeout'


def test_changed_last_preview_rejected_before_any_call(tmp_path):
    acceptance.preview(tmp_path)
    target=tmp_path/'outgoing_payload_preview.json'
    payload=json.loads(target.read_text(encoding='utf-8'))
    payload['exchanges'][-1]['question']='changed'
    target.write_text(json.dumps(payload),encoding='utf-8')
    calls=[]
    def record(*a,**kw):
        calls.append(1);return reply(*a,**kw)
    with pytest.raises(ValueError,match='preview'):
        acceptance.run(allowed=True,directory=tmp_path,infer=record)
    assert calls==[]


def test_concurrent_start_claims_only_one_batch(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier,Lock
    from pathlib import Path
    acceptance.preview(tmp_path);marker=tmp_path/'acceptance_state.json'
    barrier=Barrier(2);lock=Lock();calls=[];original=Path.exists
    def racing_exists(path):
        if path==marker:
            barrier.wait(timeout=5)
            return False
        return original(path)
    monkeypatch.setattr(Path,'exists',racing_exists)
    def record(*a,**kw):
        with lock:calls.append(1)
        return reply(*a,**kw)
    def start():
        try:return acceptance.run(allowed=True,directory=tmp_path,infer=record)
        except ValueError as exc:return str(exc)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:start(),range(2)))
    assert len(calls)==5
    assert sum(isinstance(value,dict) for value in results)==1
    assert any(isinstance(value,str) and 'already started' in value for value in results)
