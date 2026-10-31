from __future__ import annotations
import json
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal,Annotated
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse,FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from .engine import Engine, DomainError, amount
from .market import ROOT
from .cases import LABELS, candidate_unavailable
from .live_candidate_profile import profile_from_live_snapshot
from .dual_path_retrieval import profile_from_live_dual_snapshot, METHOD as DUAL_METHOD, unavailable as dual_unavailable
from .context_retrieval import METHOD as CONTEXT_METHOD, unavailable as context_unavailable
from .broker_orders import BrokerOrders
from .assistant import respond, llm_enabled, explain_draft, model_configuration
from .personal_rules import validate_rules, evaluate_rules
from .technical import analyze as technical_analysis
from .demo_market_stream import stream as demo_market_stream
from .live_readonly import stream as live_readonly_stream
from .execution_store import ExecutionStore
from .case_review import review_cases,selected_charts
from .tick_volume import tick_frame
from .case_vision import preview as case_vision_preview
from .live_assistant import respond_live,respond_context,build_live_context
from .case_analysis import prepare_analysis
from .analysis_snapshots import SnapshotStore
from .forward_outcomes import HistoricalOutcomeStore
from .conversation_intent import interpret_message
import os
import time as timing

app=FastAPI(title='Gold Trading Project',version='0.1.0')
engine=Engine()
broker_orders=BrokerOrders(demo_market_stream)
analysis_snapshots=SnapshotStore()
case_forward_store=HistoricalOutcomeStore(ROOT/'private')
case_execution_store=ExecutionStore(ROOT/'private')


class Body(BaseModel):
    model_config=ConfigDict(extra='forbid')


class ClaudeSelection(Body):
    model:Literal['sonnet','opus','haiku']|None=None
    effort:Literal['low','medium','high','xhigh','max']|None=None
    provider:Literal['claude_code','codex','openai_compatible','program']|None=None
    codex_model:str|None=Field(default=None,max_length=101,pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]*$')
    codex_effort:Literal['none','minimal','low','medium','high','xhigh','max','ultra']|None=None


def _model_options(body):
    selected=body.provider or os.getenv('GOLD_LLM_PROVIDER','openai_compatible')
    if selected=='codex':
        from .codex_local import configuration
        info=configuration();model=body.codex_model or info.get('model');effort=body.codex_effort or info.get('default_effort','low')
        if body.model or body.effort:raise HTTPException(status_code=422,detail='Codex請使用專用模型選項')
        if model:
            item=next((m for m in info.get('models',[]) if m['id']==model),None)
            if not item or effort not in item['efforts']:raise HTTPException(status_code=422,detail='所選Codex模型或程度目前不可用')
        return dict(provider='codex',model=model,effort=effort)
    if body.codex_model or body.codex_effort:raise HTTPException(status_code=422,detail='目前沒有選擇Codex')
    options={k:getattr(body,k) for k in ('model','effort') if getattr(body,k) is not None}
    if options and selected!='claude_code':
        raise HTTPException(status_code=422,detail='目前服務不是Claude Code，無法套用Claude模型選項')
    if body.provider:options['provider']=body.provider
    return options


class CaseReviewInput(ClaudeSelection):
    enabled:bool=False
    vision:bool=False
    case_ref:str|None=Field(default=None,min_length=1,max_length=64)


class DraftInput(Body):
    side:Literal['BUY','SELL']
    lot:str=Field(max_length=30)
    sl:str|None=None
    tp:str|None=None
    typical_lot:str|None=Field(default=None,max_length=30)
    order_type:Literal['MARKET','LIMIT']='MARKET'
    limit_price:str|None=None
    personal_rules:list[dict]=Field(default_factory=list,max_length=50)


class ConfirmInput(Body):
    revision:int
    idempotency_key:str=Field(min_length=1,max_length=128)
    personal_rules:list[dict]=Field(default_factory=list,max_length=50)


class BrokerDraftInput(Body):
    side:Literal['BUY','SELL']
    lot:str=Field(max_length=30)
    order_type:Literal['MARKET','LIMIT']='MARKET'
    limit_price:str|None=None
    sl:str|None=None
    tp:str|None=None
    retrieval_method:Literal['context_contract_v1','dual_path_structure_v1','path_indicator_pattern_v1']='context_contract_v1'
    input_revision:int|None=Field(default=None,ge=0)


class BrokerConfirmInput(Body):
    revision:int
    idempotency_key:str=Field(min_length=1,max_length=128)


class CloseInput(Body):
    confirmed:bool
    idempotency_key:str=Field(min_length=1,max_length=128)


class BrokerCloseInput(Body):
    order_type:Literal['MARKET','LIMIT']='MARKET'
    limit_price:str|None=Field(default=None,max_length=30)


class ReplayManagementInput(Body):
    kind:Literal['LIMIT','PROTECT']
    limit_price:str|None=Field(default=None,max_length=30)
    changes:dict[Literal['sl','tp'],str|None]=Field(default_factory=dict,max_length=2)


class ProtectionInput(Body):
    sl:str|None=Field(default=None,max_length=30)
    tp:str|None=Field(default=None,max_length=30)


class StepInput(Body):
    bars:Literal[1,6,12]=1


class ModeInput(Body):
    mode:Literal['replay','broker_demo']


class ChatInput(Body):
    message:str=Field(max_length=1500)
    side:Literal['BUY','SELL']|None=None
    lot:str|None=None
    typical_lot:str|None=Field(default=None,max_length=30)
    personal_rules:list[dict]=Field(default_factory=list,max_length=50)


class DialogueTurnInput(Body):
    thread_id:str=Field(min_length=1,max_length=80)
    question:str=Field(max_length=1500)
    answer:str=Field(max_length=1800)


class DialogueFields(ClaudeSelection):
    conversation_id:str|None=Field(default=None,min_length=1,max_length=80)
    conversation:list[DialogueTurnInput]=Field(default_factory=list,max_length=6)


class LiveChatInput(DialogueFields):
    message:str=Field(min_length=1,max_length=1500)
    llm_enabled:bool=False
    previous_questions:list[Annotated[str,Field(max_length=600)]]=Field(default_factory=list,max_length=4)
    side:Literal['BUY','SELL']='BUY'
    include_cases:bool=True
    draft:ConversationDraftInput|None=None
    input_revision:int|None=Field(default=None,ge=0)


class DraftChatInput(DialogueFields):
    draft_id:str=Field(min_length=1,max_length=64)
    message:str=Field(min_length=1,max_length=1500)
    llm_enabled:bool=False
    previous_questions:list[Annotated[str,Field(max_length=600)]]=Field(default_factory=list,max_length=4)


class ConversationDraftInput(Body):
    side:Literal['BUY','SELL']|None=None
    order_type:Literal['MARKET','LIMIT']|None=None
    lot:str=Field(default='',max_length=30)
    limit_price:str=Field(default='',max_length=30)
    sl:str=Field(default='',max_length=30)
    tp:str=Field(default='',max_length=30)


class InterpretInput(Body):
    message:str=Field(min_length=1,max_length=1500)
    draft:ConversationDraftInput|None=None
    analysis_side:Literal['BUY','SELL']|None=None
    input_revision:int=Field(default=0,ge=0)


def checked_rules(raw:list[dict]) -> list[dict]:
    try:return validate_rules(raw)
    except (ValueError,TypeError):raise DomainError('個人規則格式或門檻無效')


@app.exception_handler(DomainError)
async def domain_error(request:Request,exc:DomainError):
    return JSONResponse(status_code=exc.status,content={'detail':str(exc)})


@app.middleware('http')
async def local_origin(request:Request,call_next):
    origin=request.headers.get('origin')
    if request.method not in ('GET','HEAD','OPTIONS') and origin and origin not in (
        'http://127.0.0.1:8765','http://localhost:8765','http://127.0.0.1:5173','http://localhost:5173'):
        return JSONResponse(status_code=403,content={'detail':'此初版只接受本機交易台請求'})
    return await call_next(request)


@app.get('/api/state')
def state():
    with engine.lock:
        value=engine.state()
        value['llm_enabled']=llm_enabled()
        return value


@app.get('/api/bars')
def bars(interval:Literal['5m','15m','1h']='5m',focus:str|None=None):
    with engine.lock:
        return engine.chart(interval,focus)


@app.get('/api/broker/quote')
def broker_demo_quote(request: Request):
    if not _local_broker_access(request):
        return JSONResponse(status_code=403, content={'detail': 'DEMO 行情僅供本機查看'})
    # Legacy endpoint shares the persistent SDK session; never open a second
    # cTrader DEMO connection merely to answer a polling request.
    return JSONResponse(content=demo_market_stream.snapshot()['quote'],
                        headers={'Cache-Control': 'no-store'})


def _local_broker_access(request: Request) -> bool:
    if request.client is None or request.client.host not in ('127.0.0.1', '::1', 'testclient'):
        return False
    host = request.url.hostname
    if host not in ('127.0.0.1', 'localhost', '::1', 'testserver'):
        return False
    origin = request.headers.get('origin')
    return not origin or origin in ('http://127.0.0.1:8765', 'http://localhost:8765',
                                    'http://127.0.0.1:5173', 'http://localhost:5173')


@app.get('/api/live-readonly')
def live_readonly_market(request:Request):
    if not _local_broker_access(request):return JSONResponse(status_code=403,content={'detail':'LIVE唯讀僅限本機'})
    value=live_readonly_stream.query_snapshot()
    value.pop('tick_volume_source_key',None)
    return JSONResponse(content=value,headers={'Cache-Control':'no-store'})


@app.get('/api/broker/market')
def broker_demo_market(request: Request):
    if not _local_broker_access(request):
        return JSONResponse(status_code=403, content={'detail': 'DEMO 帳戶資料僅供本機查看'})
    return JSONResponse(content=demo_market_stream.snapshot(),
                        headers={'Cache-Control': 'no-store'})


@app.get('/api/broker/activity')
def broker_demo_activity(request: Request,limit:int=100,offset:int=0):
    if not _local_broker_access(request):
        return JSONResponse(status_code=403,content={'detail':'DEMO 交易紀錄僅供本機查看'})
    return JSONResponse(content=broker_orders.activity(demo_market_stream.activity_snapshot(),limit,offset),
                        headers={'Cache-Control':'no-store'})


@app.get('/api/broker/bars')
def broker_demo_bars(request: Request, interval: Literal['5m', '15m', '1h'] = '5m'):
    if not _local_broker_access(request):
        return JSONResponse(status_code=403, content={'detail': 'DEMO 行情僅供本機查看'})
    return JSONResponse(content=demo_market_stream.bars(interval),
                        headers={'Cache-Control': 'no-store'})


async def broker_chart_events(request:Request,interval:str):
    previous=None
    while not await request.is_disconnected():
        data=demo_market_stream.chart_snapshot(interval)
        encoded=json.dumps(data,separators=(',',':'),allow_nan=False)
        if encoded!=previous:
            yield 'data: '+encoded+'\n\n'
            previous=encoded
        else:
            yield ': keepalive\n\n'
        await asyncio.sleep(.25)


@app.get('/api/broker/chart-stream')
def broker_demo_chart_stream(request:Request,interval:Literal['5m','15m','1h']='5m'):
    if not _local_broker_access(request):
        return JSONResponse(status_code=403,content={'detail':'DEMO 行情僅供本機查看'})
    return StreamingResponse(broker_chart_events(request,interval),media_type='text/event-stream',
        headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})


@app.get('/api/broker/cases')
def broker_demo_cases(request: Request, side: Literal['BUY', 'SELL'] = 'BUY',
                      method:Literal['context_contract_v1','dual_path_structure_v1','path_indicator_pattern_v1']='context_contract_v1'):
    if not _local_broker_access(request):
        return JSONResponse(status_code=403, content={'detail': 'DEMO 案例查詢僅供本機查看'})
    result, query = _live_retrieval(demo_market_stream.query_snapshot(), side, method)
    result['query_source'] = 'ctrader_demo_xauusd'
    result['query_as_of_utc'] = query.get('as_of')
    result.setdefault('query_status', query['status'])
    result.setdefault('query_reason', query.get('reason'))
    return JSONResponse(content=result, headers={'Cache-Control': 'no-store'})


def _live_retrieval(snapshot: dict, side: str, method: str = CONTEXT_METHOD) -> tuple[dict, dict]:
    query = profile_from_live_dual_snapshot(snapshot) if method in (CONTEXT_METHOD,DUAL_METHOD) else profile_from_live_snapshot(snapshot)
    if query['status'] != 'candidate_only':
        unavailable=context_unavailable if method==CONTEXT_METHOD else dual_unavailable if method==DUAL_METHOD else candidate_unavailable
        result = unavailable(query.get('reason', 'QUERY_UNAVAILABLE'))
    else:
        if method==CONTEXT_METHOD:
            query['tick_volume']=tick_frame((snapshot.get('bars') or {}).get('5m',[]),query['as_of'],snapshot.get('tick_volume_source_key'))
        with engine.lock:
            result = engine.cases.retrieve(side, 'FIRST', Decimal('0.10'), query['as_of'],
                                           query_candidate=query,retrieval_method=method)
    result.update(query_source='ctrader_demo_xauusd',query_as_of_utc=query.get('as_of'),query_side=side)
    result.setdefault('query_status',query['status'])
    result.setdefault('query_reason',query.get('reason'))
    return result, query


def _analysis_operation_sources(retrieval):
    getter=getattr(engine.cases,'get',None)
    if not callable(getter):return {}
    return {row['id']:getter(row['id']) for row in (retrieval or {}).get('cases',[])[:5]
            if isinstance(row,dict) and isinstance(row.get('id'),str)}


@app.post('/api/broker/drafts')
def broker_demo_draft(request: Request, body: BrokerDraftInput):
    if not _local_broker_access(request):
        return JSONResponse(status_code=403, content={'detail': 'DEMO 委託僅供本機確認'})
    snapshot = demo_market_stream.query_snapshot()
    captured_at=datetime.now(timezone.utc).timestamp()
    retrieval, query = _live_retrieval(snapshot, body.side, body.retrieval_method)
    draft=broker_orders.create(snapshot, side=body.side, lot=body.lot,
                                order_type=body.order_type, limit_price=body.limit_price,
                                sl=body.sl, tp=body.tp, retrieval=retrieval)
    bundle=prepare_analysis(snapshot,body.side,retrieval,query,profiles=getattr(engine.cases,'candidate_profiles',{}),now=captured_at,operation_sources=_analysis_operation_sources(retrieval),draft=body.model_dump(),input_revision=body.input_revision,forward_store=case_forward_store,execution_store=case_execution_store)
    saved=analysis_snapshots.put(bundle,draft_id=draft['id'])
    reply=respond_context(saved['context'],'說明草稿建立時的盤面支持與相反依據、案例差異',enabled=False,frozen=True)
    return JSONResponse(content=dict(draft,analysis_snapshot_id=saved['snapshot_id'],analysis_as_of_utc=saved['context']['as_of_utc'],analysis_reply=reply),headers={'Cache-Control':'no-store'})


@app.post('/api/broker/drafts/{draft_id}/confirm')
def broker_demo_confirm(request: Request, draft_id: str, body: BrokerConfirmInput):
    if not _local_broker_access(request):
        return JSONResponse(status_code=403, content={'detail': 'DEMO 委託僅供本機確認'})
    return broker_orders.confirm(draft_id, body.revision, body.idempotency_key)


@app.get('/api/broker/drafts/{draft_id}/status')
def broker_demo_order_status(request: Request, draft_id: str):
    if not _local_broker_access(request):
        return JSONResponse(status_code=403, content={'detail': 'DEMO 委託僅供本機查看'})
    return JSONResponse(content=broker_orders.status(draft_id), headers={'Cache-Control': 'no-store'})


@app.post('/api/broker/positions/{position_id}/close-draft')
def broker_demo_close_draft(request:Request,position_id:str,body:BrokerCloseInput|None=None):
    if not _local_broker_access(request):
        return JSONResponse(status_code=403,content={'detail':'DEMO 平倉僅供本機確認'})
    return broker_orders.create_close(demo_market_stream.snapshot(),position_id,**(body.model_dump() if body else {}))


@app.post('/api/broker/positions/{position_id}/protection-draft')
def broker_protection_draft(request:Request,position_id:str,body:ProtectionInput):
    if not _local_broker_access(request):return JSONResponse(status_code=403,content={'detail':'DEMO保護修改僅供本機確認'})
    return broker_orders.create_protection(demo_market_stream.snapshot(),position_id,body.model_dump(exclude_unset=True))


@app.post('/api/broker/pending/{order_id}/cancel-draft')
def broker_cancel_pending_draft(request:Request,order_id:str):
    if not _local_broker_access(request):return JSONResponse(status_code=403,content={'detail':'DEMO掛單取消僅供本機確認'})
    return broker_orders.create_pending_cancel(demo_market_stream.snapshot(),order_id)


@app.post('/api/broker/drafts/{draft_id}/cancel')
def broker_demo_cancel(request: Request, draft_id: str):
    if not _local_broker_access(request):
        return JSONResponse(status_code=403, content={'detail': 'DEMO 草稿僅供本機取消'})
    return broker_orders.cancel(draft_id)


@app.post('/api/replay/step')
def step(body:StepInput):
    return engine.step(body.bars)


@app.post('/api/replay/reset')
def reset():
    return engine.reset()


@app.post('/api/mode')
def mode(body:ModeInput):
    with engine.lock:
        engine.mode=body.mode
        engine.version+=1
        return state()


@app.post('/api/drafts')
def draft(body:DraftInput):
    rules=checked_rules(body.personal_rules)
    with engine.lock:
        value=engine.create_draft(body.side,body.lot,body.sl,body.tp,body.typical_lot,body.order_type,body.limit_price)
        reading=technical_analysis(engine.bars[:engine.cursor],300,engine.clock).get('reading')
        value['personal_rules']=evaluate_rules(rules,engine.state(),value,reading)
        engine.drafts[value['id']]['_rule_snapshot']=rules
    return explain_draft(engine,value)


@app.post('/api/drafts/{draft_id}/confirm')
def confirm(draft_id:str,body:ConfirmInput):
    rules=checked_rules(body.personal_rules)
    with engine.lock:
        saved=engine.drafts.get(draft_id)
        if saved and saved['status']=='REVIEW' and saved.get('_rule_snapshot',[])!=rules:
            raise DomainError('個人規則已更新，請重新檢查訂單',409)
        return engine.confirm(draft_id,body.revision,body.idempotency_key)


@app.post('/api/drafts/{draft_id}/cancel')
def cancel(draft_id:str):
    return engine.cancel(draft_id)


@app.post('/api/pending/{order_id}/cancel')
def cancel_pending(order_id:str):
    return engine.cancel_pending(order_id)


@app.post('/api/positions/{position_id}/close')
def close(position_id:str,body:CloseInput):
    if not body.confirmed:
        raise DomainError('需要使用者確認平倉')
    return engine.close(position_id,body.idempotency_key)


@app.post('/api/positions/{position_id}/management-draft')
def replay_management_draft(position_id:str,body:ReplayManagementInput):
    return engine.create_management(position_id,body.kind,body.limit_price,body.changes)


@app.post('/api/positions/management/{draft_id}/confirm')
def replay_management_confirm(draft_id:str,body:ConfirmInput):
    return engine.confirm_management(draft_id,body.revision,body.idempotency_key)


@app.post('/api/chat')
def chat(body:ChatInput):
    rules=checked_rules(body.personal_rules)
    return respond(engine,body.message,body.side,body.lot,body.typical_lot,rules)


@app.get('/api/assistant/status')
def assistant_status(request:Request,provider:Literal['claude_code','codex','openai_compatible','program']|None=None):
    if not _local_broker_access(request):
        return JSONResponse(status_code=403,content={'detail':'本機助手設定僅供本機查看'})
    return JSONResponse(content=dict(**model_configuration(provider),source='ctrader_demo_xauusd',read_only=True),headers={'Cache-Control':'no-store'})


@app.post('/api/assistant/live-chat')
def live_chat(request:Request,body:LiveChatInput):
    if not _local_broker_access(request):
        return JSONResponse(status_code=403,content={'detail':'即時盤面對話僅供本機使用'})
    snapshot=demo_market_stream.query_snapshot()
    now=_analysis_capture_time(snapshot);retrieval=None;query={}
    if body.include_cases:
        if build_live_context(snapshot,now=now)['status']=='CURRENT':retrieval,query=_live_retrieval(snapshot,body.side)
        else:retrieval=context_unavailable('BROKER_QUOTE_UNAVAILABLE')
        retrieval=dict(retrieval,query_side=body.side)
    bundle=prepare_analysis(snapshot,body.side,retrieval,query,profiles=getattr(engine.cases,'candidate_profiles',{}),now=now,operation_sources=_analysis_operation_sources(retrieval),draft=body.draft.model_dump() if body.draft else None,input_revision=body.input_revision,forward_store=case_forward_store,execution_store=case_execution_store)
    saved=analysis_snapshots.put(bundle)
    return JSONResponse(content=respond_context(saved['context'],body.message,enabled=body.llm_enabled,previous_questions=body.previous_questions,conversation_id=body.conversation_id,conversation=[row.model_dump() for row in body.conversation],**_model_options(body)),
        headers={'Cache-Control':'no-store'})


def _analysis_now():
    return datetime.now(timezone.utc).timestamp()


def _analysis_clock_wait(seconds):
    timing.sleep(seconds)


def _analysis_capture_time(snapshot):
    """Wait briefly for an already received tick; never advance the clock or bars.

    Only read-only conversation uses this. The original quote checks still run
    afterwards. Cross-boundary and large leads fail normally, without waiting.
    """
    now=_analysis_now()
    try:
        source=datetime.fromisoformat(snapshot['quote']['source_time_utc'].replace('Z','+00:00'))
        if source.tzinfo is None:return now
        lead=source.timestamp()-now
        if .1<lead<=.25 and int(source.timestamp())//300==int(now)//300:
            _analysis_clock_wait(lead+.005)
            return _analysis_now()
    except (KeyError,TypeError,ValueError,AttributeError):pass
    return now


@app.post('/api/assistant/interpret')
def interpret_conversation(request:Request,body:InterpretInput):
    if not _local_broker_access(request):return JSONResponse(status_code=403,content={'detail':'委託想法解析僅供本機使用'})
    result=interpret_message(body.message,body.draft.model_dump() if body.draft else None,body.analysis_side)
    return JSONResponse(content=dict(result,input_revision=body.input_revision),headers={'Cache-Control':'no-store'})


@app.post('/api/assistant/draft-chat')
def draft_chat(request:Request,body:DraftChatInput):
    if not _local_broker_access(request):return JSONResponse(status_code=403,content={'detail':'草稿盤面對話僅供本機使用'})
    bundle=analysis_snapshots.for_draft(body.draft_id)
    return JSONResponse(content=respond_context(bundle['context'],body.message,enabled=body.llm_enabled,
        previous_questions=body.previous_questions,frozen=True,conversation_id=body.conversation_id,conversation=[row.model_dump() for row in body.conversation],**_model_options(body)),headers={'Cache-Control':'no-store'})


@app.get('/api/assistant/snapshots/{snapshot_id}/charts')
def analysis_charts(request:Request,snapshot_id:str):
    if not _local_broker_access(request):return JSONResponse(status_code=403,content={'detail':'分析圖表僅供本機查看'})
    return JSONResponse(content=analysis_snapshots.get(snapshot_id)['charts'],headers={'Cache-Control':'no-store'})


@app.get('/api/assistant/snapshots/{snapshot_id}/case-preview')
def case_preview(request:Request,snapshot_id:str,case_ref:str|None=Query(default=None,min_length=1,max_length=64)):
    if not _local_broker_access(request):return JSONResponse(status_code=403,content={'detail':'案例圖像僅供本機'})
    bundle=analysis_snapshots.get(snapshot_id)
    return JSONResponse(content=dict(case_vision_preview(selected_charts(bundle,case_ref)),snapshot_id=snapshot_id,case_ref=case_ref),headers={'Cache-Control':'no-store'})


@app.post('/api/assistant/snapshots/{snapshot_id}/case-review')
def case_review(request:Request,snapshot_id:str,body:CaseReviewInput):
    if not _local_broker_access(request):return JSONResponse(status_code=403,content={'detail':'案例解讀僅供本機'})
    return JSONResponse(content=review_cases(analysis_snapshots.get(snapshot_id),enabled=body.enabled,vision=body.vision,case_ref=body.case_ref,**_model_options(body)),headers={'Cache-Control':'no-store'})


@app.get('/api/assistant/snapshots/{snapshot_id}/operations')
def analysis_operations(request:Request,snapshot_id:str,case_ref:str=Query(min_length=1,max_length=64)):
    if not _local_broker_access(request):return JSONResponse(status_code=403,content={'detail':'歷史操作明細僅供本機查看'})
    bundle=analysis_snapshots.get(snapshot_id)
    row=bundle.get('operations',{}).get(case_ref)
    if row is None:return JSONResponse(status_code=404,content={'detail':'此快照未保留該案例操作明細；請重新提問，不會改讀新資料。'})
    return JSONResponse(content=dict(row,snapshot_id=snapshot_id,case_ref=case_ref,
        as_of_utc=bundle['context']['as_of_utc'],clock_status='UNKNOWN',source='trader_history'),headers={'Cache-Control':'no-store'})


@app.get('/api/assistant/snapshots/{snapshot_id}/outcomes')
def analysis_outcomes(request:Request,snapshot_id:str,case_ref:str=Query(min_length=1,max_length=64),minutes:int=Query(default=60)):
    if not _local_broker_access(request):return JSONResponse(status_code=403,content={'detail':'歷史後續情境僅供本機查看'})
    if minutes not in (5,30,60):raise DomainError('觀察期僅支援5、30或60分鐘',422)
    bundle=analysis_snapshots.get(snapshot_id)
    row=bundle.get('outcomes',{}).get(case_ref,{}).get(str(minutes))
    if row is None:return JSONResponse(status_code=404,content={'detail':'此原快照沒有該案例後續資料；未改挑其他案例。'})
    # Decimal strings stay authoritative. Only chart coordinates become floats.
    history=dict(row['history'])
    history['bars']=[dict(time=b['time'],**{k:float(b[k]) for k in ('open','high','low','close')}) for b in history.get('bars',[])]
    return JSONResponse(content=dict(row,history=history,snapshot_id=snapshot_id,case_ref=case_ref,
        query_as_of_utc=bundle['context'].get('query_as_of_utc')),headers={'Cache-Control':'no-store'})


@app.get('/api/assistant/acceptance/{filename}')
def case_acceptance_file(request:Request,filename:str):
    if not _local_broker_access(request):return JSONResponse(status_code=403,content={'detail':'驗收圖集僅供本機查看'})
    dates=['2026-08-11','2026-08-18','2026-08-25','2026-09-01','2026-09-15','2026-09-22','2026-09-29','2026-10-06','2026-10-13','2026-10-20']
    allowed={'index.html'}|{f'D{i:02}_{date}.png' for i,date in enumerate(dates,1)}
    path=ROOT/'private'/'assistant_case_acceptance_20261022'/filename
    if filename not in allowed or not path.is_file():raise DomainError('此驗收檔案未提供',404)
    return FileResponse(path,media_type='text/html' if filename=='index.html' else 'image/png',headers={'Cache-Control':'no-store'})


@app.get('/api/cases')
def cases(side:Literal['BUY','SELL']='BUY',action:Literal['FIRST','ADD','OPPOSITE']='FIRST',lot:str='0.1',typical_lot:str|None=None):
    with engine.lock:
        return engine.retrieve(side,action,amount(lot,'手數'),amount(typical_lot,'平常手數') if typical_lot else None)


@app.get('/api/cases/{case_id}')
def case(case_id:str):
    value=engine.cases.get(case_id)
    if not value or value['available_at']>engine.clock:
        raise DomainError('案例不存在或在回放當時尚不可用',404)
    if engine.cases.source == 'trader_history':
        candidate=engine.cases.get_candidate_detail(case_id,engine.clock)
        if candidate:
            return dict(candidate,match_reasons=[],differences=['參考盤面依來源時間模型定位；券商時鐘尚未獨立核實'])
    return dict(value,bars=[],markers=[],match_reasons=[],differences=['案例圖表時區未核實，盤面相似度未啟用'],distance=None,
                chart_reason='交易紀錄與行情時區尚未逐來源核實，暫不畫歷史進出場位置' if value['source_kind']=='trader_history' else '此為合成流程案例，沒有真實歷史K線')


@app.get('/api/broker/cases/{case_id}')
def broker_demo_case(request: Request, case_id: str):
    if not _local_broker_access(request):
        return JSONResponse(status_code=403, content={'detail': 'DEMO 案例僅供本機查看'})
    with engine.lock:
        value = engine.cases.get_candidate_detail(case_id, int(datetime.now(timezone.utc).timestamp()))
    if not value:
        raise DomainError('案例不存在或尚未成熟', 404)
    return JSONResponse(content=dict(value, match_reasons=[],
                                     differences=['參考盤面依來源時間模型定位；券商時鐘尚未獨立核實']),
                        headers={'Cache-Control': 'no-store'})


@app.get('/api/audit')
def audit():
    path=ROOT/'private'/'audit.json'
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    return dict(source_files=0,total_gold_records=36,period='合成示範',refreshed_at='2026-10-01',source='synthetic_demo',
                groups=[dict(code=k,label=v,count=sum(c['behavior']==k for c in engine.cases.items),description='合成示範操作類別') for k,v in LABELS.items()],
                limitations=['請用匯入程式載入已稽核的交易員資料','合成示範分布不是交易員統計'])


dist=ROOT/'frontend'/'dist'
if dist.exists():
    app.mount('/',StaticFiles(directory=dist,html=True),name='terminal')
