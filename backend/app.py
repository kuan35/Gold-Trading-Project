from __future__ import annotations
import json
from decimal import Decimal
from typing import Literal
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from .engine import Engine, DomainError, amount
from .market import ROOT
from .cases import LABELS
from .assistant import respond, llm_enabled, explain_draft
from .personal_rules import validate_rules, evaluate_rules
from .technical import analyze as technical_analysis

app=FastAPI(title='Gold Trading Project',version='0.1.0')
engine=Engine()


class Body(BaseModel):
    model_config=ConfigDict(extra='forbid')


class DraftInput(Body):
    side:Literal['BUY','SELL']
    lot:str=Field(max_length=30)
    sl:str|None=None
    tp:str|None=None
    typical_lot:str|None=Field(default=None,max_length=30)
    personal_rules:list[dict]=Field(default_factory=list,max_length=50)


class ConfirmInput(Body):
    revision:int
    idempotency_key:str=Field(min_length=1,max_length=128)
    personal_rules:list[dict]=Field(default_factory=list,max_length=50)


class CloseInput(Body):
    confirmed:bool
    idempotency_key:str=Field(min_length=1,max_length=128)


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
        value=engine.create_draft(body.side,body.lot,body.sl,body.tp,body.typical_lot)
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


@app.post('/api/positions/{position_id}/close')
def close(position_id:str,body:CloseInput):
    if not body.confirmed:
        raise DomainError('需要使用者確認平倉')
    return engine.close(position_id,body.idempotency_key)


@app.post('/api/chat')
def chat(body:ChatInput):
    rules=checked_rules(body.personal_rules)
    return respond(engine,body.message,body.side,body.lot,body.typical_lot,rules)


@app.get('/api/cases')
def cases(side:Literal['BUY','SELL']='BUY',action:Literal['FIRST','ADD','OPPOSITE']='FIRST',lot:str='0.1',typical_lot:str|None=None):
    with engine.lock:
        return engine.retrieve(side,action,amount(lot,'手數'),amount(typical_lot,'平常手數') if typical_lot else None)


@app.get('/api/cases/{case_id}')
def case(case_id:str):
    value=engine.cases.get(case_id)
    if not value or value['available_at']>engine.clock:
        raise DomainError('案例不存在或在回放當時尚不可用',404)
    return dict(value,bars=[],markers=[],match_reasons=[],differences=['案例圖表時區未核實，盤面相似度未啟用'],distance=None,
                chart_reason='交易紀錄與行情時區尚未逐來源核實，暫不畫歷史進出場位置' if value['source_kind']=='trader_history' else '此為合成流程案例，沒有真實歷史K線')


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
