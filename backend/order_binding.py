"""History can only confirm a reviewed closing order with matching identity."""
from decimal import Decimal,InvalidOperation

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
