import json
import sqlite3
from copy import deepcopy
from types import SimpleNamespace
import pytest

from backend.broker_orders import BrokerOrders
from backend.tests.test_broker_orders import Stream,create


def test_durable_list_keeps_request_metadata_and_reads_fills_after_modal_close(tmp_path):
    stream=Stream();stream.value['account']['account_key']='demo-A'
    stream.value['account']['currency']='EUR'
    service=BrokerOrders(stream,tmp_path/'journal.sqlite3')
    d=create(service);r=service.confirm(d['id'],d['revision'],'do-not-expose')
    stream.order_status=lambda ident: {'client_order_id':ident,'status':'FILLED','order_id':'12345','execution_price':'2500.31'}
    restarted=BrokerOrders(stream,service.journal)
    payload=restarted.activity(stream.value)
    row=payload['submissions']['items'][0]
    assert row['status']=='FILLED' and row['side']=='BUY' and row['lot']=='0.10'
    assert row['execution_price']=='2500.31' and row['currency']=='EUR'
    assert row['order_type']=='MARKET' and row['account_scope']=='CURRENT'
    assert 'do-not-expose' not in json.dumps(payload) and 'demo-A' not in json.dumps(payload)
    assert len(stream.calls)==1


def test_old_sqlite_schema_remains_readable_and_unknown_fields_are_not_invented(tmp_path):
    path=tmp_path/'old.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE submissions (draft_id TEXT PRIMARY KEY,idempotency_key TEXT NOT NULL,client_order_id TEXT NOT NULL UNIQUE,status TEXT NOT NULL,result_json TEXT NOT NULL,created_at_utc TEXT NOT NULL)')
        db.execute('INSERT INTO submissions VALUES (?,?,?,?,?,?)',('old','private-key','gd-old','UNKNOWN','{"status":"UNKNOWN"}','2026-10-20T00:00:00+00:00'))
    s=BrokerOrders(Stream(),path)
    row=s.activity(s.stream.value)['submissions']['items'][0]
    assert row['side'] is None and row['lot'] is None and row['status']=='UNKNOWN'
    assert row['account_scope']=='UNKNOWN'
    assert 'private-key' not in json.dumps(row)


def test_known_other_account_is_not_shown_as_current_account(tmp_path):
    stream=Stream();stream.value['account']['account_key']='A'
    s=BrokerOrders(stream,tmp_path/'journal.sqlite3');d=create(s)
    s.confirm(d['id'],d['revision'],'one')
    stream.value['account']['account_key']='B'
    assert s.activity(stream.value)['submissions']['items']==[]
    assert len(stream.calls)==1


def test_first_history_failure_has_an_empty_collection_instead_of_missing_items(tmp_path):
    stream=Stream();s=BrokerOrders(stream,tmp_path/'journal.sqlite3')
    snapshot=dict(stream.value,history={'broker_deals':{'status':'UNAVAILABLE'}})
    result=s.activity(snapshot)
    assert result['broker_deals']=={'status':'UNAVAILABLE','items':[],'has_more':False}


def test_saved_submission_history_pages_are_stable_and_do_not_hide_older_rows(tmp_path):
    stream=Stream();s=BrokerOrders(stream,tmp_path/'journal.sqlite3')
    for i in range(3):
        d=create(s);s.confirm(d['id'],d['revision'],str(i))
    first=s.activity(stream.value,limit=1,offset=0)['submissions']
    second=s.activity(stream.value,limit=1,offset=1)['submissions']
    assert first['total']==3 and first['has_more'] and first['offset']==0
    assert second['items'][0]['draft_id']!=first['items'][0]['draft_id']
    assert s.activity(stream.value,limit=1,offset=2)['submissions']['has_more'] is False
    assert len(stream.calls)==3


def test_read_only_activity_endpoint_is_loopback_only_and_no_cache(monkeypatch,tmp_path):
    import importlib
    app=importlib.import_module('backend.app')
    stream=Stream();stream.activity_snapshot=lambda:dict(stream.value,history={})
    monkeypatch.setattr(app,'demo_market_stream',stream)
    monkeypatch.setattr(app,'broker_orders',BrokerOrders(stream,tmp_path/'j.sqlite3'))
    req=SimpleNamespace(client=SimpleNamespace(host='127.0.0.1'),url=SimpleNamespace(hostname='127.0.0.1'),headers={})
    response=app.broker_demo_activity(req)
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert json.loads(response.body)['source']=='ctrader_demo_xauusd'
    req.client.host='10.0.0.2'
    assert app.broker_demo_activity(req).status_code==403
    assert stream.calls==[]
