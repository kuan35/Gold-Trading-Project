"""Fixture-only endpoint wiring, no broker connection or inference."""
from types import SimpleNamespace as N
import importlib
import pytest
from pydantic import ValidationError

def test_demo_management_routes_review_only_and_reject_remote(monkeypatch,tmp_path):
 app=importlib.import_module('backend.app')
 from backend.tests.test_broker_close import service
 s=service(tmp_path);monkeypatch.setattr(app,'broker_orders',s);monkeypatch.setattr(app,'demo_market_stream',s.stream)
 local=N(client=N(host='127.0.0.1'),url=N(hostname='127.0.0.1'),headers={})
 draft=app.broker_demo_close_draft(local,'123',app.BrokerCloseInput(order_type='LIMIT',limit_price='2505.00'))
 assert draft['intent']=='CLOSE' and draft['status']=='REVIEW' and not s.stream.calls
 s.stream.value['account']['positions'][0].update(sl='2480.00',tp='2520.00')
 draft=app.broker_protection_draft(local,'123',app.ProtectionInput(sl='2490.00'))
 assert draft['tp']=='2520.00' and not s.stream.calls
 remote=N(client=N(host='192.0.2.1'),url=N(hostname='127.0.0.1'),headers={})
 assert app.broker_protection_draft(remote,'123',app.ProtectionInput(sl='2490')).status_code==403
 assert app.broker_cancel_pending_draft(remote,'456').status_code==403

def test_dialogue_contract_caps_turns_and_rejects_execution_fields():
 app=importlib.import_module('backend.app')
 row=dict(thread_id='one',question='問題',answer='討論')
 assert len(app.LiveChatInput(message='追問',conversation_id='one',conversation=[row]*6).conversation)==6
 with pytest.raises(ValidationError):app.LiveChatInput(message='追問',conversation=[row]*7)
 with pytest.raises(ValidationError):app.LiveChatInput(message='追問',conversation=[dict(row,confirm=True)])
