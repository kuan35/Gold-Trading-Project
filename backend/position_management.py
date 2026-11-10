"""Reviewed DEMO-only protection/cancellation intents sharing the durable journal."""
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from uuid import uuid4
import json


def protection_values(position,quote,symbol,changes):
    from .broker_orders import _price
    from .engine import DomainError,amount
    if position.get('trailing_stop_loss') or position.get('guaranteed_stop_loss'):raise DomainError('此部位含移動／保證停損，請於cTrader原介面管理')
    if not changes or set(changes)-{'sl','tp'}:raise DomainError('請選擇要新增、修改或移除的停損停利')
    values={key:position.get(key) for key in ('sl','tp')}
    for key,raw in changes.items():
        price=_price(raw,'停損' if key=='sl' else '停利',symbol['digits'])
        values[key]=str(price) if price is not None else None
    reference=amount(quote['bid' if position['side']=='BUY' else 'ask'],'目前平倉報價')
    for key,value in values.items():
        if value is None:continue
        price=amount(value,'停損停利')
        below=(position['side']=='BUY')==(key=='sl')
        if (price>=reference if below else price<=reference):raise DomainError('停損／停利與目前平倉報價的位置不符')
    if all(values[k]==position.get(k) for k in values):raise DomainError('停損停利沒有變更')
    return values


class PositionManagement:
    def _management_draft(self,snapshot,position_id):
        from .broker_orders import _checked_snapshot,_close_position,_account_signature,_positive_int
        quote,account,symbol=_checked_snapshot(snapshot);position,volume=_close_position(account,position_id)
        now=datetime.now(timezone.utc);lot_size=_positive_int(symbol.get('lot_size_cents'),'合約大小')
        draft=dict(id=uuid4().hex,revision=1,status='REVIEW',environment='demo',source='ctrader_demo_xauusd',
            position_id=position_id,side=position['side'],lot=str(Decimal(volume)/lot_size),price=quote['bid' if position['side']=='BUY' else 'ask'],
            sl=position.get('sl'),tp=position.get('tp'),limit_price=None,volume_cents=volume,lot_size_cents=lot_size,
            expected_sl=position.get('sl'),expected_tp=position.get('tp'),account_key=account['account_key'],currency=account.get('currency'),
            account_signature=_account_signature(account),symbol_rules=dict(symbol),created_at_utc=now.isoformat(),
            expires_at_utc=(now+timedelta(seconds=30)).isoformat(),quote_time_utc=quote['source_time_utc'])
        return draft,quote,account,symbol,position

    def create_protection(self,snapshot,position_id,changes):
        with self.lock:
            draft,quote,_,symbol,position=self._management_draft(snapshot,position_id)
            draft.update(protection_values(position,quote,symbol,changes),intent='PROTECT',action='PROTECT',order_type='PROTECT',
                explanation='確認後修改此DEMO原部位的停損停利；未編輯欄位保留，移除欄位已明確列出。以券商回報及持倉更新為準。')
            self.drafts[draft['id']]=draft
            return self._public_draft(draft)

    def create_pending_cancel(self,snapshot,order_id):
        from .broker_orders import _checked_snapshot,_account_signature,_positive_int
        from scripts.position_command_payloads import pending_order_fingerprint,cancel_order_args
        from .engine import DomainError
        with self.lock:
            quote,account,symbol=_checked_snapshot(snapshot)
            pending=next((o for o in account.get('pending_orders',[]) if o.get('id')==order_id),None)
            if not pending:raise DomainError('掛單已成交、取消或變更，請刷新紀錄',409)
            expected=pending_order_fingerprint(pending)
            try:cancel_order_args(dict(order_id=order_id,expected_order=expected),0,account.get('pending_orders',[]))
            except (ValueError,TypeError):raise DomainError('找不到可取消的黃金待成交委託',409)
            volume=Decimal(pending['volume_units'])*100
            if not volume.is_finite() or volume<=0 or volume!=volume.to_integral_value() or volume>2**63-1:raise DomainError('掛單數量無效',503)
            now=datetime.now(timezone.utc);lot_size=_positive_int(symbol.get('lot_size_cents'),'合約大小')
            draft=dict(id=uuid4().hex,revision=1,status='REVIEW',environment='demo',source='ctrader_demo_xauusd',
                intent='CANCEL',action='CANCEL',order_type='CANCEL',order_id=order_id,position_id=pending.get('position_id'),
                side=pending['side'],lot=str(volume/lot_size),volume_cents=int(volume),price=pending.get('limit_price'),
                limit_price=pending.get('limit_price'),stop_price=pending.get('stop_price'),pending_intent=pending['intent'],pending_order_type=pending['order_type'],sl=pending.get('sl'),tp=pending.get('tp'),expected_order=expected,
                account_key=account['account_key'],currency=account.get('currency'),account_signature=_account_signature(account),
                symbol_rules=dict(symbol),created_at_utc=now.isoformat(),expires_at_utc=(now+timedelta(seconds=30)).isoformat(),
                quote_time_utc=quote['source_time_utc'],
                explanation='確認後要求券商取消這筆待成交委託；若已有部分成交，只取消剩餘掛單，不會平掉已成交部位。')
            self.drafts[draft['id']]=draft
            return self._public_draft(draft)

    def _confirm_management(self,draft,key,quote,account,symbol):
        from .broker_orders import _close_position,_known_result
        from .engine import DomainError
        ident='gd-'+uuid4().hex
        command=dict(client_order_id=ident,intent=draft['intent'],position_id=draft.get('position_id'),volume_cents=draft['volume_cents'])
        if draft['intent']=='PROTECT':
            position,volume=_close_position(account,draft['position_id'])
            if volume!=draft['volume_cents'] or position['side']!=draft['side']:raise DomainError('原部位已改變，請重建草稿',409)
            protection_values(position,quote,symbol,{k:draft[k] for k in ('sl','tp')})
            command.update({k:draft[k] for k in ('sl','tp','expected_sl','expected_tp')})
        else:
            from scripts.position_command_payloads import cancel_order_args
            command.update(order_id=draft['order_id'],expected_order=draft['expected_order'])
            try:cancel_order_args(command,0,account.get('pending_orders',[]))
            except (ValueError,TypeError):raise DomainError('掛單已成交、取消或變更，請刷新紀錄',409)
        initial=dict(client_order_id=ident,intent=draft['intent'],position_id=draft['position_id'],order_id=draft.get('order_id'),status='UNKNOWN',status_observed_at_utc=datetime.now(timezone.utc).isoformat())
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE');conflict=self._uncertain_submission(db,account)
            if conflict:raise DomainError(conflict,409)
            if draft['intent']=='CANCEL':
                for raw_result,raw_context in db.execute('SELECT result_json,context_json FROM submissions').fetchall():
                    prior,ctx=json.loads(raw_result),json.loads(raw_context)
                    if (ctx.get('account_key')==draft['account_key'] and ctx.get('intent')=='CANCEL' and
                        ctx.get('order_id')==draft['order_id'] and prior.get('status')=='CANCELLED'):
                        raise DomainError('取消已回報，等待券商更新待成交清單，請勿重送',409)
            context={k:draft.get(k) for k in ('intent','position_id','order_id','side','lot','order_type','sl','tp','account_key','currency','expected_order')}
            db.execute('INSERT INTO submissions (draft_id,idempotency_key,client_order_id,status,result_json,created_at_utc,context_json) VALUES (?,?,?,?,?,?,?)',
                (draft['id'],key,ident,'UNKNOWN',json.dumps(initial),datetime.now(timezone.utc).isoformat(),json.dumps(context)))
        draft['status']='SUBMITTED'
        try:result=self.stream.place_order(command)
        except Exception:result=dict(status='UNKNOWN')
        result=dict(initial,**(result if isinstance(result,dict) else {}))
        allowed={'APPLIED','REJECTED','UNKNOWN'} if draft['intent']=='PROTECT' else {'CANCELLED','REJECTED','UNKNOWN'}
        if not _known_result(result.get('status')) or result['status'] not in allowed:result['status']='UNKNOWN'
        result['status_observed_at_utc']=datetime.now(timezone.utc).isoformat()
        with self._db() as db:db.execute('UPDATE submissions SET status=?,result_json=? WHERE draft_id=?',(result['status'],json.dumps(result),draft['id']))
        return result
