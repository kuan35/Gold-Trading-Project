"""Reviewed, position-bound management for the local replay account only."""
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from uuid import uuid4

class ReplayManagement:
 def create_management(self,position_id,kind,limit_price=None,changes=None):
  from .engine import DomainError,amount
  from .position_management import protection_values
  with self.lock:
   if self.mode!='replay':raise DomainError('只有本機回放可使用此操作',403)
   p=next((p for p in self.positions if p['id']==position_id),None)
   if not p:raise DomainError('原部位不存在',409)
   if kind not in ('LIMIT','PROTECT'):raise DomainError('操作類型無效')
   d=dict(id=uuid4().hex,revision=1,status='REVIEW',management=True,version=self.version,position=dict(p),kind=kind,
     expires=(datetime.now(timezone.utc)+timedelta(seconds=30)).isoformat())
   if kind=='LIMIT':
    target=amount(limit_price,'指定平倉價');q=amount(self.quote()['bid' if p['side']=='BUY' else 'ask'],'平倉參考價')
    if target.as_tuple().exponent < -2:raise DomainError('指定平倉價最多兩位小數')
    if (target<=q if p['side']=='BUY' else target>=q):raise DomainError('限價平倉須設在較有利的一側；立即平倉請選市價')
    if any(o.get('position_id')==position_id for o in self.pending_orders):raise DomainError('原部位已有待成交平倉單',409)
    d['limit_price']=str(target)
   else:d.update(protection_values(p,self.quote(),{'digits':2},changes or {}))
   self.drafts[d['id']]=d
   return dict(d)

 def confirm_management(self,draft_id,revision,key):
  from .engine import DomainError
  with self.lock:
   cache='management:'+draft_id+':'+key
   if cache in self.close_results:return dict(self.close_results[cache],state=self.state())
   d=self.drafts.get(draft_id)
   if self.mode!='replay' or not d or not d.get('management') or d['status']!='REVIEW' or d['revision']!=revision:raise DomainError('操作草稿已失效',409)
   if datetime.now(timezone.utc)>=datetime.fromisoformat(d['expires']):raise DomainError('草稿已過期',409)
   p=next((p for p in self.positions if p['id']==d['position']['id']),None)
   if self.version!=d['version'] or p!=d['position']:raise DomainError('帳戶已更新，請重建草稿',409)
   if not key or len(key)>128:raise DomainError('缺少有效確認識別碼')
   ident=uuid4().hex[:10]
   if d['kind']=='LIMIT':
    self.pending_orders.append(dict(id=ident,intent='CLOSE',position_id=p['id'],side='SELL' if p['side']=='BUY' else 'BUY',lot=p['lot'],
      limit_price=d['limit_price'],sl=None,tp=None,created_at=self.clock,action='CLOSE',status='PENDING'))
    status='PENDING'
   else:
    p.update(sl=d['sl'],tp=d['tp']);status='APPLIED'
   d['status']='SUBMITTED';self.version+=1
   result=dict(status=status,order_id=ident,state=self.state());self.close_results[cache]=result
   return result
