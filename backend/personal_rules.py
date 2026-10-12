"""Validated, reminder-only rules; financial comparisons never use the LLM."""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
import re
from typing import Any

KINDS = {'order_lot':'本筆手數','after_lot':'新單後總手數','same_side_count':'既有同向持倉筆數',
         'missing_sl':'未設定停損','stop_loss_usd':'本筆停損情境損失','market_bias':'5分盤面'}
BIASES = {'bullish':'短線偏多','bearish':'短線偏空','bullish_pullback':'多方結構中的回檔',
          'bearish_rebound':'空方結構中的反彈','mixed':'多空結構尚不一致'}

def validate_rules(raw: Any) -> list[dict]:
    if not isinstance(raw,list) or len(raw)>50:
        raise ValueError('個人規則須為清單，最多50條')
    rules=[]; seen=set()
    for item in raw:
        if not isinstance(item,dict) or set(item)!={'id','kind','value','op','enabled','side'}:
            raise ValueError('個人規則欄位不完整或含不支援欄位')
        r=dict(item)
        if not isinstance(r['id'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',r['id']) or r['id'] in seen:
            raise ValueError('規則識別碼無效或重複')
        seen.add(r['id'])
        if not isinstance(r['kind'],str) or r['kind'] not in KINDS or type(r['enabled']) is not bool or r['side'] not in ('ANY','BUY','SELL'):
            raise ValueError('不支援的規則類型或方向')
        if r['kind']=='missing_sl':
            if r['value'] is not None or r['op']!='is':raise ValueError('未設定停損條件不能附數字')
        elif r['kind']=='market_bias':
            if not isinstance(r['value'],str) or r['value'] not in BIASES or r['op']!='is':raise ValueError('不支援的盤面分類')
        else:
            if r['op'] not in ('gt','gte') or not isinstance(r['value'],str) or len(r['value'])>30:
                raise ValueError('請使用大於或大於等於及有效數字')
            try:v=Decimal(r['value'])
            except (InvalidOperation,ValueError):raise ValueError('規則門檻不是有效數字')
            if not v.is_finite() or v<=0 or v>Decimal('1000000000'):
                raise ValueError('規則門檻須大於零且不超過十億')
            if r['kind']=='same_side_count' and v!=v.to_integral_value():raise ValueError('筆數須為整數')
        rules.append(r)
    return rules

def rule_text(r: dict) -> str:
    prefix={'ANY':'','BUY':'買進時，','SELL':'賣出時，'}[r['side']]
    if r['kind']=='missing_sl':return prefix+'未設定停損時提醒'
    if r['kind']=='market_bias':return prefix+'5分盤面為「'+BIASES[r['value']]+'」時提醒'
    unit='筆' if r['kind']=='same_side_count' else 'USD' if r['kind']=='stop_loss_usd' else '手'
    return prefix+KINDS[r['kind']]+('大於等於' if r['op']=='gte' else '大於')+r['value']+' '+unit+'時提醒'

def evaluate_rules(raw: list[dict], state: dict, draft: dict | None = None, reading: dict | None = None) -> dict:
    results=[]
    for r in validate_rules(raw):
        if not r['enabled']:continue
        status='unknown';actual=None;reason='尚未建立待確認訂單，無法判斷此條件'
        if draft and r['side']!='ANY' and r['side']!=draft['side']:
            status='clear';reason='此規則限定另一個買賣方向'
        elif r['side']!='ANY' and not draft:
            reason='此規則限定下單方向，尚未建立待確認訂單'
        elif r['kind']=='market_bias':
            if reading and reading.get('bias') in BIASES:
                actual=reading.get('label',BIASES[reading['bias']]);status='triggered' if reading['bias']==r['value'] else 'clear'
                reason='依回放當時最近已收5分K棒的程式判讀；分類須完全相同'
            else:reason='尚無足夠的已收5分K棒判讀盤面'
        elif draft:
            kind=r['kind']
            if kind=='missing_sl':
                actual='未設定' if not draft.get('sl') else str(draft['sl']);status='triggered' if not draft.get('sl') else 'clear';reason='檢查本筆待確認訂單的停損設定'
            else:
                if kind=='order_lot':actual=draft['lot']
                elif kind=='same_side_count':actual=str(sum(p['side']==draft['side'] for p in state['positions']))
                else:actual=draft['risk'].get(kind)
                if actual is not None:
                    a=Decimal(actual);b=Decimal(r['value'])
                    status='triggered' if (a>=b if r['op']=='gte' else a>b) else 'clear'
                    reason=f'實際 {actual}，條件 '+('≥ ' if r['op']=='gte' else '> ')+r['value']
                    if kind=='stop_loss_usd':reason+=' USD；未含滑價、佣金及跳空影響，不保證損失上限'
                else:reason='未設定停損，無法試算本筆停損情境損失'
        results.append(dict(id=r['id'],text=rule_text(r),status=status,actual=actual,reason=reason))
    return dict(source='program',reminder_only=True,results=results)

def is_rule_message(message: str) -> bool:
    """Conservative guard: a setting, hypothetical or negative is never an order."""
    return bool(re.search(r'規則|提醒|警告|通知|以後|每次|超過|上限|暫停|啟用|停用|刪除|如果|假如|假設|若|不要|別買|別賣|不買|不賣|取消|不用|改第|第\s*\d+\s*條',message))
