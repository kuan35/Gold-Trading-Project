"""Same-thread quoted discussion only; old financial numbers never become current facts."""
import re

PERIOD=re.compile(r'(?i)(?:MA|EMA|RSI|ATR)\s*\d+|MACD\s*12[/／]26[/／]9|(?<!\d)(?:5|15|1)\s*(?:分鐘|分K|分|小時)|\b(?:5m|15m|1h)\b')


def mask_context_text(value):
    if not isinstance(value,str):return ''
    from .assistant import scrub
    value=scrub(value)
    text=re.sub(r'(?:gsk_|sk-|github_pat_|ghp_)[A-Za-z0-9_-]{12,}','[憑證已隱藏]',value[:1800])
    text=re.sub(r'(?i)Bearer\s+\S+','[憑證已隱藏]',text)
    parts=[];end=0
    def numbers(s):return re.sub(r'[-+]?\d[\d,]*(?:\.\d+)?%?','[當時數值]',s)
    for match in PERIOD.finditer(text):
        parts.extend([numbers(text[end:match.start()]),match.group()]);end=match.end()
    return ''.join(parts)+numbers(text[end:])


def dialogue_history(rows,thread_id):
    if not isinstance(thread_id,str) or not thread_id or not isinstance(rows,list):return []
    return [dict(user=mask_context_text(row.get('question')),assistant=mask_context_text(row.get('answer')),
        basis='先前討論，非當前行情或委託授權') for row in rows[-6:] if isinstance(row,dict) and row.get('thread_id')==thread_id
        and isinstance(row.get('question'),str) and isinstance(row.get('answer'),str)]
