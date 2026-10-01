"""Explicit local parser. Optional LLM is explanation-only and opt-in."""
from __future__ import annotations
import json
import os
import re
import httpx
from .engine import Engine


def llm_enabled() -> bool:
    return os.getenv('GOLD_ENABLE_LLM','false').lower()=='true' and bool(os.getenv('GOLD_LLM_API_KEY'))


def scrub(text: str) -> str:
    text=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[已遮罩email]',text)
    text=re.sub(r'(帳號|account|API.?key|token)\s*[:：=]?\s*\S+',r'\1 [已遮罩]',text,flags=re.I)
    return re.sub(r'\b\d{8,}\b','[已遮罩識別數字]',text)


def respond(engine:Engine,message:str,side:str|None=None,lot:str|None=None) -> dict:
    message=message.strip()
    if not message:
        return dict(message='請輸入問題或訂單內容，例如「買進黃金0.1手」。',draft=None,provider='local_rules')
    draft=None
    requested_side = 'SELL' if re.search(r'賣|做空|\bSELL\b',message,re.I) else 'BUY' if re.search(r'買|做多|\bBUY\b',message,re.I) else side if '改' in message else None
    match=re.search(r'(\d+(?:\.\d+)?)\s*(?:手|lots?\b)',message,re.I)
    if requested_side and match and not re.search(r'不要|別|不買|不賣|取消|不用',message):
        stop=re.search(r'停損\s*([0-9]+(?:\.[0-9]+)?)',message)
        target=re.search(r'停利\s*([0-9]+(?:\.[0-9]+)?)',message)
        draft=engine.create_draft(requested_side,match.group(1),stop.group(1) if stop else None,target.group(1) if target else None)
        answer='已準備'+('買進' if requested_side=='BUY' else '賣出')+draft['lot']+'手草稿，尚未送出。請開啟訂單檢查，核對案例及風險後確認。'
    elif re.search(r'買|賣|下單|改成|BUY|SELL',message,re.I):
        answer='請明確指定方向與手數，例如「買進黃金0.1手」。我只能準備草稿，不能代替你確認送單。'
    else:
        state=engine.state(); m=state['market']
        answer=f'目前回放行情最近60根5分K的價格變化為 {m["change_pct"]}%，區間 {m["low"]} 至 {m["high"]}。均線20為 {m["ma20"]}，均線60為 {m["ma60"]}。這些是盤面描述，不是買賣指令。加倉會增加價格繼續不利時的損失；可以準備草稿查看具體試算。'
    if not llm_enabled():
        return dict(message=answer,draft=draft,provider='local_rules')
    # No row identifiers, source names, account identifiers, credentials or full statements.
    context=dict(market=engine.state()['market'],position_summary=[dict(side=p['side'],lot=p['lot'],entry=p['entry']) for p in engine.positions])
    if draft:
        context['draft']=dict(side=draft['side'],lot=draft['lot'],risk=draft['risk'],historical_counts={k:draft['retrieval'][k] for k in ('total','wins','losses','flat','unknown')})
    try:
        response=httpx.post('https://api.openai.com/v1/chat/completions',headers={'Authorization':'Bearer '+os.environ['GOLD_LLM_API_KEY']},
                            json={'model':os.getenv('GOLD_LLM_MODEL','gpt-4.1-mini'),'messages':[
                                {'role':'system','content':'用繁體中文簡短解釋提供的盤面數值與風險。只能引用已提供數字。不可建議買賣、預測勝率或聲稱已送单。不要推斷交易員心理或虧損原因。回答不具工具操作權限。'},
                                {'role':'user','content':scrub(message)+'\n必要數值摘要：'+json.dumps(context,ensure_ascii=False)}], 'max_completion_tokens':400},timeout=15)
        response.raise_for_status()
        explanation=response.json()['choices'][0]['message']['content']
        return dict(message=answer+'\n\n'+explanation,draft=draft,provider='configured_llm')
    except (httpx.HTTPError,KeyError,IndexError,TypeError,ValueError):
        return dict(message=answer+'\n外部文字解釋目前無法取得；以下保留程式計算結果。',draft=draft,provider='local_rules')
