from decimal import Decimal
import pytest
from backend.engine import Engine,DomainError

def opened():
 e=Engine();d=e.create_draft('BUY','0.1',None,None);e.confirm(d['id'],1,'open');return e,e.positions[0]

def test_limit_exit_waits_then_closes_original_without_opening_reverse_position():
 e,p=opened();limit=Decimal(e.quote()['bid'])+10
 d=e.create_management(p['id'],'LIMIT',str(limit))
 assert not e.pending_orders
 result=e.confirm_management(d['id'],1,'exit');assert result['status']=='PENDING'
 assert e.confirm_management(d['id'],1,'exit')['order_id']==result['order_id']
 e.bars[e.cursor].update(open=str(limit-2),high=str(limit-1),low=str(limit-3),close=str(limit-2));e.step()
 assert len(e.positions)==1 and len(e.pending_orders)==1
 e.bars[e.cursor].update(open=str(limit-1),high=str(limit+1),low=str(limit-2),close=str(limit));e.step()
 assert not e.positions and not e.pending_orders and e.orders[-1]['position_id']==p['id']
 assert e.orders[-1]['reason']=='LIMIT_CLOSE'

def test_cancel_and_other_close_remove_bound_exit_and_stale_review_rejected():
 e,p=opened();limit=str(Decimal(e.quote()['bid'])+10)
 d=e.create_management(p['id'],'LIMIT',limit);e.step()
 with pytest.raises(DomainError):e.confirm_management(d['id'],1,'stale')
 d=e.create_management(p['id'],'LIMIT',limit);r=e.confirm_management(d['id'],1,'exit')
 e.cancel_pending(r['order_id']);assert e.positions and not e.pending_orders
 d=e.create_management(p['id'],'LIMIT',limit);e.confirm_management(d['id'],1,'exit2')
 e.close(p['id'],'market');assert not e.pending_orders

def test_protection_keep_clear_and_version_recheck():
 e,p=opened();q=Decimal(e.quote()['bid']);p['tp']=str(q+20)
 d=e.create_management(p['id'],'PROTECT',changes={'sl':str(q-10)})
 assert d['tp']==p['tp'];e.confirm_management(d['id'],1,'protect')
 assert Decimal(e.positions[0]['sl'])==q-10
 d=e.create_management(p['id'],'PROTECT',changes={'tp':None});e.confirm_management(d['id'],1,'clear')
 assert e.positions[0]['tp'] is None
