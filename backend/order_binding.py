"""History can only confirm a reviewed closing order with matching identity."""
from decimal import Decimal,InvalidOperation

def cancellation_history_result(stored,context,activity):
 """Resolve an uncertain cancel from this account's explicit original terminal order."""
 account=activity.get('account') or {};history=(activity.get('history') or {}).get('broker_orders') or {}
 expected=context.get('expected_order')
 if (account.get('status')!='CURRENT' or history.get('status')!='CURRENT' or
     not context.get('account_key') or account.get('account_key')!=context['account_key'] or not isinstance(expected,dict)):
  return None
 matches=[row for row in history.get('items',[]) if row.get('order_id',row.get('id'))==stored.get('order_id')]
 if len(matches)!=1:return None
 row=matches[0]
 try:
  for k in ('side','intent','order_type','position_id'):
   if row.get(k)!=expected.get(k):return None
  if Decimal(str(row.get('volume_units')))!=Decimal(str(expected.get('volume_units'))):return None
  for k in ('limit_price','stop_price'):
   if (row.get(k) is None)!=(expected.get(k) is None):return None
   if expected.get(k) is not None and Decimal(str(row[k]))!=Decimal(str(expected[k])):return None
 except (InvalidOperation,TypeError,ValueError,KeyError):return None
 status=row.get('status')
 if status=='CANCELLED':return dict(stored,status='CANCELLED',history_reconciled=True)
 if status in ('FILLED','EXPIRED','REJECTED'):
  return dict(stored,status='REJECTED',error_code='ORIGINAL_ORDER_'+status,history_reconciled=True)
 return None

def checked_close_history(result,row,context):
 if context.get('intent')!='CLOSE' or context.get('order_type')!='LIMIT':return result
 if result.get('status') not in ('ACCEPTED','PARTIALLY_FILLED','FILLED'):return result
 try:
  # Journal side is the ORIGINAL position side, worker side is the closing side.
  closing=context.get('closing_side') or ('SELL' if context['side']=='BUY' else 'BUY')
  valid=row.get('intent')=='CLOSE' and row.get('order_type')=='LIMIT' and row.get('position_id')==context.get('position_id') and row.get('side')==closing and Decimal(str(row.get('volume_units')))*100==Decimal(str(context['volume_cents']))
 except (KeyError,ValueError,TypeError,InvalidOperation):valid=False
 return dict(result,binding_verified=True) if valid else dict(result,status='UNKNOWN',error_code='UNVERIFIED_CLOSE_ORDER')

def history_result(row,context=None):
 result={k:row.get(k) for k in ('client_order_id','order_id','position_id','status','execution_price','updated_at_utc','intent','side','order_type','volume_units')}
 result['history_reconciled']=True
 return checked_close_history(result,row,context) if context else result
