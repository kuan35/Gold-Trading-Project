from copy import deepcopy
import pytest
from backend.broker_orders import BrokerOrders
from backend.engine import DomainError
from backend.tests.test_broker_orders import Stream,create

def uncertain_stream():
    stream=Stream();stream.value['account']['account_key']='demo-A'
    stream.place_order=lambda command:stream.calls.append(deepcopy(command)) or {'status':'UNKNOWN'}
    return stream

def test_unknown_blocks_new_draft_after_restart_without_another_send(tmp_path):
    stream=uncertain_stream();journal=tmp_path/'orders.sqlite3';service=BrokerOrders(stream,journal)
    first=create(service);service.confirm(first['id'],first['revision'],'first')
    restarted=BrokerOrders(stream,journal)
    with pytest.raises(DomainError,match='回報.*核對'):
        create(restarted)
    assert len(stream.calls)==1
    assert restarted.confirm(first['id'],first['revision'],'first')['status']=='UNKNOWN'

def test_unknown_is_rechecked_for_a_previously_prepared_second_draft(tmp_path):
    stream=uncertain_stream();service=BrokerOrders(stream,tmp_path/'orders.sqlite3')
    first=create(service);second=create(service)
    service.confirm(first['id'],first['revision'],'first')
    with pytest.raises(DomainError,match='回報.*核對'):
        service.confirm(second['id'],second['revision'],'second')
    assert len(stream.calls)==1

def test_different_known_account_and_known_accepted_limit_are_not_unknown(tmp_path):
    stream=uncertain_stream();service=BrokerOrders(stream,tmp_path/'orders.sqlite3')
    first=create(service);service.confirm(first['id'],first['revision'],'first')
    stream.value['account']['account_key']='demo-B'
    assert create(service)['status']=='REVIEW'
    stream.value['account']['account_key']='demo-A'
    stream.order_status=lambda ident:{'status':'ACCEPTED','order_id':'12345'}
    assert create(service,order_type='LIMIT',limit_price='2499.50')['status']=='REVIEW'

@pytest.mark.parametrize('status',['NOT_RECOGNIZED',None,['ACCEPTED'],{'unexpected':'ACCEPTED'}])
def test_missing_or_unknown_status_does_not_unlock_another_draft(tmp_path,status):
    stream=uncertain_stream();stream.place_order=lambda command:stream.calls.append(command) or {'status':status}
    service=BrokerOrders(stream,tmp_path/'orders.sqlite3');first=create(service)
    service.confirm(first['id'],first['revision'],'first')
    with pytest.raises(DomainError):create(service)
    assert len(stream.calls)==1

def test_malformed_status_refresh_preserves_unknown_and_safe_lookup(tmp_path):
    stream=uncertain_stream();service=BrokerOrders(stream,tmp_path/'orders.sqlite3')
    first=create(service);service.confirm(first['id'],first['revision'],'first')
    stream.order_status=lambda ident:{'status':{'unexpected':'ACCEPTED'}}
    assert service.status(first['id'])['status']=='UNKNOWN'
    with pytest.raises(DomainError):create(service)
    assert len(stream.calls)==1
