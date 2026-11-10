from __future__ import annotations
import json
import sqlite3
import asyncio
from datetime import datetime, timezone
from contextlib import asynccontextmanager
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
from .live_trade_stream import stream as live_trade_stream
from .live_orders import LiveBrokerOrders
from .execution_store import ExecutionStore
from .case_review import review_cases,selected_charts
from .tick_volume import tick_frame
from .ticket_preview import ticket_preview
from .account_scenarios import enrich_position_returns,equity_zero_scenario
from .trade_risk import risk_summary,size_for_risk
from .trade_advice import signal_for_query, trade_advice
from .trade_protection_advice import protection_advice
from .trade_plans import TradePlanStore,enrich as enrich_trade_plan
from .trade_alerts import LocalAlerts,AlertMonitor,AlertError
from .market_clock import SOURCE_CLOCK_SKEW_SECONDS
from .history_library import HistoryLibrary,HistoryError,START as HISTORY_START
from .dialogue_memory import mask_context_text
from .case_vision import preview as case_vision_preview
from .live_assistant import respond_live,respond_context,build_live_context,QUOTE_CLOCK_TOLERANCE_MS
from .case_analysis import prepare_analysis
from .analysis_snapshots import SnapshotStore
from .analysis_history import AnalysisHistory
from .forward_outcomes import HistoricalOutcomeStore
from .conversation_intent import interpret_message
from .macro_calendar import MacroCalendar
from .macro_assistant import answer as gold_answer,augment_bundle,select_context
from .macro_knowledge import question_kind
import os
import time as timing
import atexit

@asynccontextmanager
async def _local_lifespan(_app):
    alert_monitor.start()
    try:yield
    finally:alert_monitor.stop()


app=FastAPI(title='Gold Trading Project',version='0.1.0',lifespan=_local_lifespan)
engine=Engine()
broker_orders=BrokerOrders(demo_market_stream)
live_broker_orders=LiveBrokerOrders(live_trade_stream)
analysis_snapshots=SnapshotStore()
analysis_history=AnalysisHistory(ROOT/'private'/'analysis_history')
case_forward_store=HistoricalOutcomeStore(ROOT/'private')
case_execution_store=ExecutionStore(ROOT/'private')
macro_calendar=MacroCalendar(ROOT/'private'/'macro')
trade_plans=TradePlanStore(ROOT/'private'/'trade_plans.sqlite')
trade_alerts=LocalAlerts(ROOT/'private'/'trade_alerts.sqlite')
alert_monitor=AlertMonitor(trade_alerts,lambda:demo_market_stream.query_snapshot() if trade_alerts.has_active() else {})
atexit.register(alert_monitor.stop)
history_library=HistoryLibrary(ROOT/'private')

def _save_analysis_reply(reply,bundle=None):
    try:return analysis_history.save(reply,bundle)
    except (OSError,ValueError,TypeError,KeyError,DomainError):
        return dict(reply,analysis_history_error='完整分析未能存入本機，切換後可能只能回看文字；請確認本機儲存空間。')

def _read_analysis_snapshot(snapshot_id):
    try:return analysis_snapshots.get(snapshot_id)
    except DomainError as expired:
        try:return analysis_history.snapshot(snapshot_id)
        except DomainError:raise expired


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


class TicketPreviewInput(Body):
    side:Literal['BUY','SELL']|None=None
    order_type:Literal['MARKET','LIMIT']|None=None
    lot:str=Field(default='',max_length=30)
    limit_price:str|None=Field(default=None,max_length=30)
    sl:str|None=Field(default=None,max_length=30)
    tp:str|None=Field(default=None,max_length=30)

class BrokerDraftInput(Body):
    side:Literal['BUY','SELL']
    lot:str=Field(max_length=30)
    order_type:Literal['MARKET','LIMIT']='MARKET'
    limit_price:str|None=None
    sl:str|None=None
    tp:str|None=None
    retrieval_method:Literal['context_contract_v1','dual_path_structure_v1','path_indicator_pattern_v1']='context_contract_v1'
    input_revision:int|None=Field(default=None,ge=0)
    plan_note:str=Field(default='',max_length=2000)
    conversation_id:str|None=Field(default=None,min_length=1,max_length=80)
    risk_usd:str|None=Field(default=None,max_length=30)
    equity_pct:str|None=Field(default=None,max_length=30)


class RiskSizeInput(Body):
    draft:TicketPreviewInput
    risk_usd:str|None=Field(default=None,max_length=30)
    equity_pct:str|None=Field(default=None,max_length=30)


class PlanReviewInput(Body):
    revision:int=Field(ge=1)
    note:str=Field(default='',max_length=10000)
    adherence:Literal['YES','NO','PARTIAL','UNKNOWN']='UNKNOWN'
    lesson:str=Field(default='',max_length=10000)


class AlertInput(Body):
    name:str=Field(min_length=1,max_length=120)
    kind:Literal['PRICE','CLOSE_5M','EVENT']
    field:Literal['bid','ask']='bid'
    comparator:Literal['GTE','LTE']='GTE'
    threshold:str|None=Field(default=None,max_length=30)
    conversation_id:str|None=Field(default=None,min_length=1,max_length=80)
    event_id:str|None=Field(default=None,max_length=200)
    lead_minutes:int|None=Field(default=None,ge=1,le=10080)


class AlertUpdateInput(Body):
    revision:int=Field(ge=1)
    enabled:bool


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
    include_macro:bool=False
    draft:ConversationDraftInput|None=None
    input_revision:int|None=Field(default=None,ge=0)
    advice_mode:Literal['COMPARE','SIDE']|None=None


class DraftChatInput(DialogueFields):
    draft_id:str=Field(min_length=1,max_length=64)
    message:str=Field(min_length=1,max_length=1500)
    llm_enabled:bool=False
    previous_questions:list[Annotated[str,Field(max_length=600)]]=Field(default_factory=list,max_length=4)


class GoldChatInput(DialogueFields):
    message:str=Field(min_length=1,max_length=1500)
    llm_enabled:bool=False


class PlanDiscussInput(ClaudeSelection):
    message:str=Field(default='回看當時盤面支持、相反訊號，對照我的復盤心得。',min_length=1,max_length=1500)
    llm_enabled:bool=False


class ConversationDraftInput(Body):
    side:Literal['BUY','SELL']|None=None
    order_type:Literal['MARKET','LIMIT']|None=None
    lot:str=Field(default='',max_length=30)
    limit_price:str=Field(default='',max_length=30)
    sl:str=Field(default='',max_length=30)
    tp:str=Field(default='',max_length=30)
    risk_usd:str|None=Field(default=None,max_length=30)
    equity_pct:str|None=Field(default=None,max_length=30)


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
        'http://127.0.0.1:8765','http://localhost:8765','http://127.0.0.1:8766','http://localhost:8766','http://127.0.0.1:5173','http://localhost:5173'):
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
                                    'http://127.0.0.1:8766', 'http://localhost:8766',
                                    'http://127.0.0.1:5173', 'http://localhost:5173')


@app.get('/api/live-readonly')
def live_readonly_market(request:Request):
    if not _local_broker_access(request):return JSONResponse(status_code=403,content={'detail':'LIVE唯讀僅限本機'})
    value=live_readonly_stream.query_snapshot()
    value.pop('tick_volume_source_key',None)
    return JSONResponse(content=value,headers={'Cache-Control':'no-store'})


def _live_read_snapshot(*, query=False):
    """Prefer the separately enabled trading connection; otherwise keep LIVE read-only."""
    getter='query_snapshot' if query else 'snapshot'
    trading=getattr(live_trade_stream,getter)()
    if trading.get('connection_status')=='CONNECTED':
        return trading
    return getattr(live_readonly_stream,getter)()


@app.get('/api/live/market')
def live_market(request:Request):
    if not _local_broker_access(request):raise HTTPException(403,'LIVE帳戶僅供本機查看')
    snapshot=_live_read_snapshot()
    leverage=(snapshot.get('account') or {}).get('account_leverage')
    value=enrich_position_returns(snapshot,leverage=leverage)
    value['read_only']=not bool(value.get('order_connection'))
    return JSONResponse(content=value,headers={'Cache-Control':'no-store'})


@app.get('/api/live/activity')
def live_activity(request:Request,limit:int=100,offset:int=0):
    if not _local_broker_access(request):raise HTTPException(403,'LIVE紀錄僅供本機查看')
    snapshot=live_trade_stream.activity_snapshot()
    if snapshot.get('connection_status')!='CONNECTED':snapshot=live_readonly_stream.activity_snapshot()
    return JSONResponse(content=live_broker_orders.activity(snapshot,limit,offset),headers={'Cache-Control':'no-store'})


@app.get('/api/live/bars')
def live_bars(request:Request,interval:Literal['5m','15m','1h']='5m'):
    if not _local_broker_access(request):raise HTTPException(403,'LIVE行情僅供本機查看')
    stream=live_trade_stream if live_trade_stream.snapshot().get('connection_status')=='CONNECTED' else live_readonly_stream
    return JSONResponse(content=stream.bars(interval),headers={'Cache-Control':'no-store'})


@app.post('/api/live/ticket-preview')
def live_ticket_preview(request:Request,body:TicketPreviewInput):
    if not _local_broker_access(request):raise HTTPException(403,'LIVE委託試算僅供本機查看')
    snapshot=_live_read_snapshot()
    leverage=(snapshot.get('account') or {}).get('account_leverage')
    values=body.model_dump()
    preview=ticket_preview(snapshot,values,leverage=leverage)
    if preview['status']=='AVAILABLE' and snapshot.get('order_connection'):
        volume=int(Decimal(preview['quantity_oz'])*100)
        broker_margin=live_trade_stream.expected_margin(snapshot,volume)
        preview=ticket_preview(snapshot,values,leverage=leverage,expected_margin=broker_margin)
    preview['risk']=risk_summary(snapshot,values,preview)
    preview['account_zero']=equity_zero_scenario(snapshot,values,preview)
    return JSONResponse(content=preview,headers={'Cache-Control':'no-store'})


@app.get('/api/broker/market')
def broker_demo_market(request: Request):
    if not _local_broker_access(request):
        return JSONResponse(status_code=403, content={'detail': 'DEMO 帳戶資料僅供本機查看'})
    return JSONResponse(content=enrich_position_returns(demo_market_stream.snapshot(),leverage=os.environ.get('GOLD_PREVIEW_LEVERAGE','200')),
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


async def broker_chart_events(request:Request,interval:str,market_stream=None):
    previous=None
    while not await request.is_disconnected():
        data=(market_stream or demo_market_stream).chart_snapshot(interval)
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


@app.get('/api/live/chart-stream')
def broker_live_chart_stream(request:Request,interval:Literal['5m','15m','1h']='5m'):
    if not _local_broker_access(request):raise HTTPException(403,'LIVE行情僅供本機查看')
    stream=live_trade_stream if live_trade_stream.snapshot().get('connection_status')=='CONNECTED' else live_readonly_stream
    return StreamingResponse(broker_chart_events(request,interval,stream),media_type='text/event-stream',
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


@app.get('/api/live/cases')
def broker_live_cases(request: Request, side: Literal['BUY', 'SELL'] = 'BUY',
                      method:Literal['context_contract_v1','dual_path_structure_v1','path_indicator_pattern_v1']='context_contract_v1'):
    if not _local_broker_access(request):
        raise HTTPException(403, 'LIVE 案例查詢僅供本機查看')
    result, query = _live_retrieval(_live_read_snapshot(query=True), side, method)
    result['query_source'] = 'ctrader_live_xauusd'
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


def _advice_costs():
    totals = {}
    try:
        for scenario in ('baseline', 'stress'):
            prefix = f'GOLD_ADVICE_{scenario.upper()}'
            values = [Decimal(os.environ[f'{prefix}_{kind}_USD_PER_OZ'])
                      for kind in ('SPREAD', 'COMMISSION', 'SLIPPAGE')]
            if any(not v.is_finite() or not 0 <= v <= 1000 for v in values):
                return None
            totals[scenario + '_usd_per_oz'] = str(sum(values))
    except (KeyError, ArithmeticError, ValueError):
        return None
    return totals


def _frozen_trade_advice(snapshot, query, side, draft, now):
    risk = scenario = None
    if draft and draft.get('side') in ('BUY', 'SELL') and (side is None or draft['side'] == side):
        preview = ticket_preview(snapshot, draft, now=now)
        current = risk_summary(snapshot, draft, preview, now=now)
        sizing = size_for_risk(snapshot, draft, risk_usd=draft.get('risk_usd'),
                               equity_pct=draft.get('equity_pct'), now=now)
        loss, budget = current['stop_loss_usd'], sizing['budget_usd']
        exceeds = loss is not None and budget is not None and Decimal(loss) > Decimal(budget)
        risk = dict(stop_loss_usd=loss, equity_pct=current['stop_equity_pct'], budget_usd=budget,
                    over_budget=exceeds, suggested_lot=sizing['lot'] if exceeds else None)
        if preview['status'] == 'AVAILABLE':
            scenario = dict(side=draft['side'], entry=preview['entry_price'],
                            sl=(preview.get('sl') or {}).get('price'), tp=(preview.get('tp') or {}).get('price'))
    index = getattr(engine.cases, 'context_index', None)
    advice = trade_advice(index, query, case_forward_store, _advice_costs(), side=side, draft=scenario, risk=risk)
    signal = signal_for_query(query)
    direction = side or advice['side'] or signal['side']
    if direction != signal['side']:
        signal = {}
    use_limit = bool(draft and draft.get('side') == direction and draft.get('order_type') == 'LIMIT')
    quote = snapshot.get('quote') or {}
    if use_limit:
        entry = draft.get('limit_price')
    else:
        entry = quote.get('ask' if direction == 'BUY' else 'bid')
    bars = (query['pre_entry_bars']['5m'][-6:]
            if signal.get('kind') in ('LOWER_RECLAIM','UPPER_RECLAIM') else ())
    levels = protection_advice(signal, entry=entry, digits=(snapshot.get('symbol') or {}).get('digits'),
                               recent_low=min((Decimal(str(b['low'])) for b in bars), default=None),
                               recent_high=max((Decimal(str(b['high'])) for b in bars), default=None))
    advice['protection'] = dict(levels, entry_basis='草稿限價' if use_limit else '查詢快照報價',
                                conditional=advice['action'] not in ('BUY','SELL'))
    return advice


def _analysis_operation_sources(retrieval):
    getter=getattr(engine.cases,'get',None)
    if not callable(getter):return {}
    return {row['id']:getter(row['id']) for row in (retrieval or {}).get('cases',[])[:5]
            if isinstance(row,dict) and isinstance(row.get('id'),str)}


@app.post('/api/broker/ticket-preview')
def broker_ticket_preview(request:Request,body:TicketPreviewInput):
    if not _local_broker_access(request):return JSONResponse(status_code=403,content={'detail':'委託試算僅供本機查看'})
    snapshot=demo_market_stream.snapshot();draft=body.model_dump()
    leverage=os.environ.get('GOLD_PREVIEW_LEVERAGE','200')
    preview=ticket_preview(snapshot,draft,leverage=leverage)
    if preview['status']=='AVAILABLE' and body.order_type=='MARKET':
        volume=int(Decimal(preview['quantity_oz'])*100)
        margin=demo_market_stream.expected_margin(snapshot,volume)
        preview=ticket_preview(snapshot,draft,leverage=leverage,expected_margin=margin)
    preview['risk']=risk_summary(snapshot,draft,preview)
    preview['account_zero']=equity_zero_scenario(snapshot,draft,preview)
    return JSONResponse(content=preview,headers={'Cache-Control':'no-store'})


def _trade_account(request:Request,*,write=False):
    if not _local_broker_access(request):raise HTTPException(403,'交易工具僅供本機使用')
    snapshot=demo_market_stream.snapshot();account=snapshot.get('account') or {}
    key=account.get('account_key') if snapshot.get('environment')=='demo' else None
    if write:
        try:
            age=datetime.now(timezone.utc).timestamp()-datetime.fromisoformat(account['updated_at_utc']).timestamp()
            if not key or account.get('status')!='CURRENT' or not 0<=age<=10:raise ValueError()
        except (KeyError,TypeError,ValueError):raise HTTPException(409,'請先連線並同步自己的DEMO帳戶。')
    return snapshot,key


@app.exception_handler(AlertError)
async def trading_alert_error(_request,exc):
    messages={'not_found':'找不到此帳戶的提醒。','revision_conflict':'提醒已被變更，請重新載入。','invalid_condition':'提醒條件無效，請核對價位、條件及事件時間。','account_unavailable':'DEMO帳戶尚未就緒。'}
    return JSONResponse(status_code=exc.status_code,content={'detail':messages.get(exc.code,'提醒操作無法完成，請重新載入。'),'code':exc.code})


@app.post('/api/trading/risk-size')
def trading_risk_size(request:Request,body:RiskSizeInput):
    snapshot,_key=_trade_account(request,write=True)
    return JSONResponse(content=size_for_risk(snapshot,body.draft.model_dump(),risk_usd=body.risk_usd,equity_pct=body.equity_pct),headers={'Cache-Control':'no-store'})


def _plan_refresh(account_key,plan):
    try:
        ident=(plan.get('receipt') or {}).get('client_order_id')
        getter=getattr(demo_market_stream,'order_status',None)
        if ident and callable(getter):
            receipt=getter(ident)
            if receipt:trade_plans.attach_receipt(account_key,plan['draft_id'],receipt)
            plan=trade_plans.get(account_key,plan['id'])
    except DomainError:pass
    return plan


@app.get('/api/trading/plans')
def trading_plan_list(request:Request,limit:int=Query(default=50,ge=1,le=100),offset:int=Query(default=0,ge=0,le=100000)):
    _snapshot,key=_trade_account(request)
    if not key:return JSONResponse(content=dict(status='UNAVAILABLE',reason='連線DEMO帳戶後可查看這個帳戶的交易計畫。',items=[],total=None),headers={'Cache-Control':'no-store'})
    value=trade_plans.list(key,limit=limit,offset=offset)
    for row in value['items']:_plan_refresh(key,row)
    return JSONResponse(content=dict(trade_plans.list(key,limit=limit,offset=offset),status='AVAILABLE'),headers={'Cache-Control':'no-store'})


@app.get('/api/trading/plans/{plan_id}')
def trading_plan_detail(request:Request,plan_id:str):
    snapshot,key=_trade_account(request)
    if not key:raise HTTPException(409,'帳戶識別尚未就緒。')
    plan=_plan_refresh(key,trade_plans.get(key,plan_id))
    activity=demo_market_stream.activity_snapshot()
    if (activity.get('account') or {}).get('account_key')==key:plan=enrich_trade_plan(plan,activity)
    bundle=plan.pop('snapshot_bundle',None) or {};plan['charts']=bundle.get('charts',{})
    return JSONResponse(content=plan,headers={'Cache-Control':'no-store'})


@app.patch('/api/trading/plans/{plan_id}/review')
def trading_plan_review(request:Request,plan_id:str,body:PlanReviewInput):
    _snapshot,key=_trade_account(request,write=True)
    value=trade_plans.update_review(key,plan_id,body.revision,note=body.note,adherence=body.adherence,lesson=body.lesson)
    value.pop('snapshot_bundle',None)
    return JSONResponse(content=value,headers={'Cache-Control':'no-store'})


def _trading_calendar(*,refresh=False):
    data=macro_calendar.snapshot(refresh=refresh,days=14);now=datetime.now(timezone.utc).timestamp()
    sources={s['id'] for s in data.get('sources',[]) if s.get('status')=='CURRENT'}
    events=[]
    for row in data.get('events',[]):
        try:
            stamp=datetime.fromisoformat(row['scheduled_at_utc']).timestamp()
            if (row.get('source') in sources and row.get('status')=='SCHEDULED' and stamp>now
                and row.get('freshness','CURRENT')=='CURRENT' and row.get('timing_precision') in ('EXACT','MINUTE','SECOND')):
                events.append(dict(id=row['id'],name=row['title'],time_utc=row['scheduled_at_utc']))
        except (KeyError,ValueError,TypeError):continue
    return dict(status=data['status'],events=events)


@app.get('/api/trading/calendar')
def trading_calendar(request:Request,refresh:bool=False):
    _trade_account(request)
    return JSONResponse(content=_trading_calendar(refresh=refresh),headers={'Cache-Control':'no-store'})


@app.get('/api/history/metadata')
def history_metadata(request:Request):
    if not _local_broker_access(request):raise HTTPException(403,'歷史看盤僅供本機使用')
    history_library.refresh()
    return JSONResponse(content=history_library.metadata(),headers={'Cache-Control':'no-store'})

@app.post('/api/history/refresh')
def history_refresh(request:Request):
    if not _local_broker_access(request):raise HTTPException(403,'歷史看盤僅供本機使用')
    history_library.refresh(force=True)
    return JSONResponse(content=history_library.metadata(),headers={'Cache-Control':'no-store'})

@app.get('/api/history/bars')
def history_bars(request:Request,at:int=Query(ge=HISTORY_START,lt=4102444800),interval:Literal['5m','15m','1h']='5m',source:Literal['auto','reference','ctrader_demo']='auto',limit:int=Query(default=600,ge=10,le=1200),direction:Literal['around','before','after']='around'):
    if not _local_broker_access(request):raise HTTPException(403,'歷史看盤僅供本機使用')
    try:value=history_library.window(at,interval=interval,source=source,limit=limit,direction=direction)
    except HistoryError as exc:raise HTTPException(422,str(exc))
    return JSONResponse(content=value,headers={'Cache-Control':'no-store'})


@app.get('/api/trading/alerts')
def trading_alert_list(request:Request):
    snapshot,key=_trade_account(request)
    if not key:return JSONResponse(content=dict(status='UNAVAILABLE',reason='請先連線自己的DEMO帳戶。',items=[],events=[],monitor_running=False),headers={'Cache-Control':'no-store'})
    return JSONResponse(content=dict(trade_alerts.list(key),status='AVAILABLE',monitor_running=alert_monitor.running,monitor_error=alert_monitor.last_error),headers={'Cache-Control':'no-store'})


@app.post('/api/trading/alerts')
def trading_alert_create(request:Request,body:AlertInput):
    snapshot,key=_trade_account(request,write=True);value=body.model_dump(exclude_none=True)
    if body.kind=='EVENT':
        event=next((e for e in _trading_calendar()['events'] if e['id']==body.event_id),None)
        if not event or not body.lead_minutes or datetime.fromisoformat(event['time_utc']).timestamp()-body.lead_minutes*60<=datetime.now(timezone.utc).timestamp():raise HTTPException(409,'請選擇來源仍有效、提醒時間尚未到的官方事件。')
        value['event_time_utc']=event['time_utc']
    else:
        quote=snapshot.get('quote') or {}
        try:
            age=datetime.now(timezone.utc).timestamp()-datetime.fromisoformat(quote['source_time_utc']).timestamp()
            if quote.get('status')!='CURRENT' or not -SOURCE_CLOCK_SKEW_SECONDS<=age<=5:raise ValueError()
            threshold=amount(body.threshold,'提醒價位');digits=(snapshot.get('symbol') or {})['digits']
            if threshold%Decimal(1).scaleb(-digits):raise ValueError()
        except (KeyError,TypeError,ValueError):raise HTTPException(409,'請等待有效新報價，並核對提醒價位的小數級距。')
    result=trade_alerts.create(key,value)
    return JSONResponse(content=result,headers={'Cache-Control':'no-store'})


@app.patch('/api/trading/alerts/{alert_id}')
def trading_alert_update(request:Request,alert_id:str,body:AlertUpdateInput):
    _snapshot,key=_trade_account(request,write=True)
    return JSONResponse(content=trade_alerts.update(key,alert_id,body.revision,enabled=body.enabled),headers={'Cache-Control':'no-store'})


@app.delete('/api/trading/alerts/{alert_id}')
def trading_alert_delete(request:Request,alert_id:str,revision:int=Query(ge=1)):
    _snapshot,key=_trade_account(request,write=True);trade_alerts.delete(key,alert_id,revision)
    return JSONResponse(content=dict(status='DELETED'),headers={'Cache-Control':'no-store'})

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
    values=body.model_dump(exclude={'plan_note','conversation_id'})
    advice=_frozen_trade_advice(snapshot,query,body.side,values,captured_at) if body.retrieval_method==CONTEXT_METHOD else None
    bundle=prepare_analysis(snapshot,body.side,retrieval,query,profiles=getattr(engine.cases,'candidate_profiles',{}),now=captured_at,operation_sources=_analysis_operation_sources(retrieval),draft=values,input_revision=body.input_revision,forward_store=case_forward_store,execution_store=case_execution_store,advice=advice)
    saved=analysis_snapshots.put(bundle,draft_id=draft['id'])
    reply=respond_context(saved['context'],'說明草稿建立時的盤面支持與相反依據、案例差異',enabled=False,frozen=True)
    reply=_save_analysis_reply(reply,saved)
    recording={}
    try:
        key=snapshot['account']['account_key']
        preview=ticket_preview(snapshot,body.model_dump(),leverage=os.environ.get('GOLD_PREVIEW_LEVERAGE','200'))
        draft['risk']['account_zero']=equity_zero_scenario(snapshot,body.model_dump(),preview)
        plan=trade_plans.capture(key,draft,reply,note=body.plan_note,conversation_id=body.conversation_id,risk=risk_summary(snapshot,body.model_dump(),preview),snapshot_bundle=saved)
        recording['plan_id']=plan['id']
    except (OSError,sqlite3.Error,ValueError,TypeError,KeyError,DomainError):recording['plan_record_error']='本次交易計畫未能保存，請確認本機儲存空間。'
    return JSONResponse(content=dict(draft,analysis_snapshot_id=saved['snapshot_id'],analysis_as_of_utc=saved['context']['as_of_utc'],analysis_reply=reply,**recording),headers={'Cache-Control':'no-store'})


@app.post('/api/live/drafts')
def broker_live_draft(request:Request,body:BrokerDraftInput):
    if not _local_broker_access(request):raise HTTPException(403,'LIVE委託僅供本機確認')
    snapshot=live_trade_stream.query_snapshot()
    captured_at=datetime.now(timezone.utc).timestamp()
    retrieval,query=_live_retrieval(snapshot,body.side,body.retrieval_method)
    draft=live_broker_orders.create(snapshot,side=body.side,lot=body.lot,
        order_type=body.order_type,limit_price=body.limit_price,sl=body.sl,tp=body.tp,retrieval=retrieval)
    values=body.model_dump(exclude={'plan_note','conversation_id'})
    advice=_frozen_trade_advice(snapshot,query,body.side,values,captured_at) if body.retrieval_method==CONTEXT_METHOD else None
    bundle=prepare_analysis(snapshot,body.side,retrieval,query,
        profiles=getattr(engine.cases,'candidate_profiles',{}),now=captured_at,
        operation_sources=_analysis_operation_sources(retrieval),draft=values,
        input_revision=body.input_revision,forward_store=case_forward_store,
        execution_store=case_execution_store,advice=advice)
    saved=analysis_snapshots.put(bundle,draft_id=draft['id'])
    reply=respond_context(saved['context'],'說明LIVE草稿建立時的盤面、歷史案例與相反依據',enabled=False,frozen=True)
    reply=_save_analysis_reply(reply,saved)
    return JSONResponse(content=dict(draft,analysis_snapshot_id=saved['snapshot_id'],
        analysis_as_of_utc=saved['context']['as_of_utc'],analysis_reply=reply),
        headers={'Cache-Control':'no-store'})


@app.post('/api/live/drafts/{draft_id}/confirm')
def broker_live_confirm(request:Request,draft_id:str,body:BrokerConfirmInput):
    if not _local_broker_access(request):raise HTTPException(403,'LIVE委託僅供本機確認')
    return JSONResponse(content=live_broker_orders.confirm(draft_id,body.revision,body.idempotency_key),
        headers={'Cache-Control':'no-store'})


@app.get('/api/live/drafts/{draft_id}/status')
def broker_live_status(request:Request,draft_id:str):
    if not _local_broker_access(request):raise HTTPException(403,'LIVE委託僅供本機查看')
    return JSONResponse(content=live_broker_orders.status(draft_id),headers={'Cache-Control':'no-store'})


@app.post('/api/live/drafts/{draft_id}/cancel')
def broker_live_cancel_draft(request:Request,draft_id:str):
    if not _local_broker_access(request):raise HTTPException(403,'LIVE草稿僅供本機取消')
    return JSONResponse(content=live_broker_orders.cancel(draft_id),headers={'Cache-Control':'no-store'})


@app.post('/api/live/positions/{position_id}/close-draft')
def broker_live_close_draft(request:Request,position_id:str,body:BrokerCloseInput|None=None):
    if not _local_broker_access(request):raise HTTPException(403,'LIVE平倉僅供本機確認')
    return JSONResponse(content=live_broker_orders.create_close(live_trade_stream.snapshot(),position_id,
        **(body.model_dump() if body else {})),headers={'Cache-Control':'no-store'})


@app.post('/api/live/positions/{position_id}/protection-draft')
def broker_live_protection_draft(request:Request,position_id:str,body:ProtectionInput):
    if not _local_broker_access(request):raise HTTPException(403,'LIVE保護修改僅供本機確認')
    return JSONResponse(content=live_broker_orders.create_protection(live_trade_stream.snapshot(),position_id,
        body.model_dump(exclude_unset=True)),headers={'Cache-Control':'no-store'})


@app.post('/api/live/pending/{order_id}/cancel-draft')
def broker_live_pending_cancel_draft(request:Request,order_id:str):
    if not _local_broker_access(request):raise HTTPException(403,'LIVE掛單取消僅供本機確認')
    return JSONResponse(content=live_broker_orders.create_pending_cancel(live_trade_stream.snapshot(),order_id),
        headers={'Cache-Control':'no-store'})


@app.post('/api/broker/drafts/{draft_id}/confirm')
def broker_demo_confirm(request: Request, draft_id: str, body: BrokerConfirmInput):
    if not _local_broker_access(request):
        return JSONResponse(status_code=403, content={'detail': 'DEMO 委託僅供本機確認'})
    result=broker_orders.confirm(draft_id, body.revision, body.idempotency_key)
    try:
        draft=broker_orders.drafts.get(draft_id) or {};key=draft.get('account_key')
        if key:trade_plans.attach_receipt(key,draft_id,result)
    except (OSError,sqlite3.Error,ValueError,DomainError):pass
    return result


@app.get('/api/broker/drafts/{draft_id}/status')
def broker_demo_order_status(request: Request, draft_id: str):
    if not _local_broker_access(request):
        return JSONResponse(status_code=403, content={'detail': 'DEMO 委託僅供本機查看'})
    result=broker_orders.status(draft_id)
    try:
        key=(demo_market_stream.snapshot().get('account') or {}).get('account_key')
        if key:trade_plans.attach_receipt(key,draft_id,result)
    except (OSError,sqlite3.Error,ValueError,DomainError):pass
    return JSONResponse(content=result, headers={'Cache-Control': 'no-store'})


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
    return _answer_market_chat(demo_market_stream.query_snapshot(),body)


@app.post('/api/live/assistant/chat')
def live_account_chat(request:Request,body:LiveChatInput):
    if not _local_broker_access(request):
        raise HTTPException(403,'LIVE盤面對話僅供本機使用')
    return _answer_market_chat(_live_read_snapshot(query=True),body)


def _answer_market_chat(snapshot,body):
    macro=select_context(macro_calendar.snapshot(refresh=True),body.message) if body.include_macro else None
    now=_analysis_capture_time(snapshot);retrieval=None;query={}
    mode=body.advice_mode
    analysis_side=body.side
    if body.include_cases or mode:
        if build_live_context(snapshot,now=now)['status']=='CURRENT':
            if mode=='COMPARE':
                signal=signal_for_query(profile_from_live_dual_snapshot(snapshot))
                analysis_side=signal['side'] or body.side
            retrieval,query=_live_retrieval(snapshot,analysis_side)
        else:retrieval=context_unavailable('BROKER_QUOTE_UNAVAILABLE')
        retrieval=dict(retrieval,query_side=analysis_side)
    draft=body.draft.model_dump() if body.draft else None
    advice=_frozen_trade_advice(snapshot,query,body.side if mode=='SIDE' else None,draft,now) if mode else None
    bundle=prepare_analysis(snapshot,analysis_side,retrieval,query,profiles=getattr(engine.cases,'candidate_profiles',{}),now=now,operation_sources=_analysis_operation_sources(retrieval),draft=draft,input_revision=body.input_revision,forward_store=case_forward_store,execution_store=case_execution_store,advice=advice)
    if macro is not None:bundle=augment_bundle(bundle,macro)
    saved=analysis_snapshots.put(bundle)
    reply=respond_context(saved['context'],body.message,enabled=body.llm_enabled,previous_questions=body.previous_questions,conversation_id=body.conversation_id,conversation=[row.model_dump() for row in body.conversation],**_model_options(body))
    return JSONResponse(content=_save_analysis_reply(reply,saved),
        headers={'Cache-Control':'no-store'})


@app.get('/api/assistant/macro-calendar')
def macro_events(request:Request,days:int=Query(default=60,ge=1,le=60)):
    if not _local_broker_access(request):return JSONResponse(status_code=403,content={'detail':'事件查詢僅供本機使用'})
    return JSONResponse(content=select_context(macro_calendar.snapshot(refresh=True,days=days),'接下來重大事件'),headers={'Cache-Control':'no-store'})


@app.post('/api/assistant/gold-chat')
def gold_chat(request:Request,body:GoldChatInput):
    if not _local_broker_access(request):return JSONResponse(status_code=403,content={'detail':'黃金知識與事件對話僅供本機使用'})
    kind=question_kind(body.message)
    if kind is None:raise HTTPException(400,'此入口用於黃金知識與事件討論；明確委託請沿草稿確認流程。')
    snapshot=macro_calendar.snapshot(refresh=True) if kind!='knowledge' else None
    reply=gold_answer(body.message,kind,snapshot,enabled=body.llm_enabled,conversation_id=body.conversation_id,conversation=[r.model_dump() for r in body.conversation],**_model_options(body))
    return JSONResponse(content=_save_analysis_reply(reply),headers={'Cache-Control':'no-store'})


def _analysis_now():
    return datetime.now(timezone.utc).timestamp()


def _analysis_clock_wait(seconds):
    timing.sleep(seconds)


# The DEMO tick clock can lead this host by about 2 seconds. Wait for the
# already received tick to become current; build_live_context stays strict.
MAX_ANALYSIS_SOURCE_LEAD_SECONDS = 3.0
ANALYSIS_CLOCK_SETTLE_SECONDS = 0.005


def _analysis_capture_time(snapshot):
    """Wait briefly for an already received tick; never advance the clock or bars.

    Only read-only conversation uses this. The original quote checks still run
    afterwards. Cross-boundary and large leads fail normally, without waiting.
    """
    now=_analysis_now()
    try:
        quote=snapshot['quote']
        if snapshot.get('connection_status')!='CONNECTED' or quote.get('status')!='CURRENT':
            return now
        source=datetime.fromisoformat(quote['source_time_utc'].replace('Z','+00:00'))
        if source.tzinfo is None:return now
        source_time=source.timestamp()
        lead=source_time-now
        if QUOTE_CLOCK_TOLERANCE_MS/1000 < lead <= MAX_ANALYSIS_SOURCE_LEAD_SECONDS and int(source_time)//300==int(now)//300:
            _analysis_clock_wait(lead+ANALYSIS_CLOCK_SETTLE_SECONDS)
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
    reply=respond_context(bundle['context'],body.message,enabled=body.llm_enabled,
        previous_questions=body.previous_questions,frozen=True,conversation_id=body.conversation_id,conversation=[row.model_dump() for row in body.conversation],**_model_options(body))
    return JSONResponse(content=_save_analysis_reply(reply,bundle),headers={'Cache-Control':'no-store'})


@app.post('/api/trading/plans/{plan_id}/discuss')
def trading_plan_discuss(request:Request,plan_id:str,body:PlanDiscussInput):
    _snapshot,key=_trade_account(request)
    if not key:raise HTTPException(409,'帳戶識別尚未就緒。')
    plan=trade_plans.get(key,plan_id);bundle=plan.get('snapshot_bundle') or {}
    if not bundle.get('context'):raise HTTPException(409,'這筆舊計畫沒有可解讀的固定盤面。')
    memory=[dict(thread_id=plan['id'],question=mask_context_text(plan.get('note','')),answer=mask_context_text('本人復盤：'+plan.get('review_note','')+'；心得：'+plan.get('lesson','')))]
    reply=respond_context(bundle['context'],body.message,enabled=body.llm_enabled,frozen=True,conversation_id=plan['id'],conversation=memory,**_model_options(body))
    return JSONResponse(content=_save_analysis_reply(reply,bundle),headers={'Cache-Control':'no-store'})

@app.get('/api/assistant/analyses/{analysis_ref}')
def archived_analysis(request:Request,analysis_ref:str):
    if not _local_broker_access(request):return JSONResponse(status_code=403,content={'detail':'歷史分析僅供本機查看'})
    return JSONResponse(content=analysis_history.reply(analysis_ref),headers={'Cache-Control':'no-store'})

@app.delete('/api/assistant/analyses/{analysis_ref}')
def delete_archived_analysis(request:Request,analysis_ref:str):
    if not _local_broker_access(request):return JSONResponse(status_code=403,content={'detail':'歷史分析僅供本機管理'})
    analysis_history.delete(analysis_ref)
    return {'status':'deleted'}


@app.get('/api/assistant/snapshots/{snapshot_id}/charts')
def analysis_charts(request:Request,snapshot_id:str):
    if not _local_broker_access(request):return JSONResponse(status_code=403,content={'detail':'分析圖表僅供本機查看'})
    return JSONResponse(content=_read_analysis_snapshot(snapshot_id)['charts'],headers={'Cache-Control':'no-store'})


@app.get('/api/assistant/snapshots/{snapshot_id}/case-preview')
def case_preview(request:Request,snapshot_id:str,case_ref:str|None=Query(default=None,min_length=1,max_length=64)):
    if not _local_broker_access(request):return JSONResponse(status_code=403,content={'detail':'案例圖像僅供本機'})
    bundle=_read_analysis_snapshot(snapshot_id)
    return JSONResponse(content=dict(case_vision_preview(selected_charts(bundle,case_ref)),snapshot_id=snapshot_id,case_ref=case_ref),headers={'Cache-Control':'no-store'})


@app.post('/api/assistant/snapshots/{snapshot_id}/case-review')
def case_review(request:Request,snapshot_id:str,body:CaseReviewInput):
    if not _local_broker_access(request):return JSONResponse(status_code=403,content={'detail':'案例解讀僅供本機'})
    return JSONResponse(content=review_cases(_read_analysis_snapshot(snapshot_id),enabled=body.enabled,vision=body.vision,case_ref=body.case_ref,**_model_options(body)),headers={'Cache-Control':'no-store'})


@app.get('/api/assistant/snapshots/{snapshot_id}/operations')
def analysis_operations(request:Request,snapshot_id:str,case_ref:str=Query(min_length=1,max_length=64)):
    if not _local_broker_access(request):return JSONResponse(status_code=403,content={'detail':'歷史操作明細僅供本機查看'})
    bundle=_read_analysis_snapshot(snapshot_id)
    row=bundle.get('operations',{}).get(case_ref)
    if row is None:return JSONResponse(status_code=404,content={'detail':'此快照未保留該案例操作明細；請重新提問，不會改讀新資料。'})
    return JSONResponse(content=dict(row,snapshot_id=snapshot_id,case_ref=case_ref,
        as_of_utc=bundle['context']['as_of_utc'],clock_status='UNKNOWN',source='trader_history'),headers={'Cache-Control':'no-store'})


@app.get('/api/assistant/snapshots/{snapshot_id}/outcomes')
def analysis_outcomes(request:Request,snapshot_id:str,case_ref:str=Query(min_length=1,max_length=64),minutes:int=Query(default=60)):
    if not _local_broker_access(request):return JSONResponse(status_code=403,content={'detail':'歷史後續情境僅供本機查看'})
    if minutes not in (5,30,60):raise DomainError('觀察期僅支援5、30或60分鐘',422)
    bundle=_read_analysis_snapshot(snapshot_id)
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


@app.get('/api/live/cases/{case_id}')
def broker_live_case(request: Request, case_id: str):
    if not _local_broker_access(request):
        raise HTTPException(403, 'LIVE 案例僅供本機查看')
    # The reference library is shared historical evidence; the LIVE query and
    # account stream remain separate from DEMO.
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
