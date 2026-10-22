"""Conservative local interpretation; returned patches never authorize an order.

Only a bounded set of explicit Chinese/English field phrases is supported. Values
stay decimal strings; broker precision, lot rules and price relationships remain
the existing review endpoint's responsibility. Unsupported/ambiguous text is never
partially applied. Previous analysis direction is discussion context, not a default
order side. The supplied draft is read only.
"""
from decimal import Decimal, InvalidOperation
import re
import unicodedata


_NUMBER = r'(?<![\d.])[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?![\d.])'
_SIDE = {
    'BUY': r'做多|看多|偏多|多單|買進|買入|買單|買在|(?<![A-Za-z])buy(?![A-Za-z])',
    'SELL': r'做空|看空|偏空|空單|賣出|賣單|賣在|(?<![A-Za-z])sell(?![A-Za-z])',
}
_LABELS = {
    'lot': r'手數|lot(?:s)?', 'limit_price': r'限價|進場價|委託價',
    'sl': r'停損|止損|(?<![a-z])sl(?![a-z])',
    'tp': r'停利|止盈|(?<![a-z])tp(?![a-z])',
}
_LINK = r'\s*(?:(?:改成|改為|修改為|調整為|設為|設定為|設定|設在|設|改|為|是|到|:|=)\s*)?'
_CLEAR = r'清空|清除|移除|刪除|取消|不設(?:定)?|不要'


def _positive_string(value: str) -> str | None:
    try:
        number = Decimal(value)
        return value.lstrip('+') if number.is_finite() and number > 0 else None
    except InvalidOperation:
        return None


def _extract_fields(text: str) -> tuple[dict, bool]:
    """Return only explicit values and an ambiguity flag; never infer units."""
    fields: dict = {}
    ambiguous = False
    for side, pattern in _SIDE.items():
        if re.search(pattern, text):
            if 'side' in fields:
                ambiguous = True
            fields['side'] = side
    types = [value for value, pattern in (
        ('MARKET', r'市價|\bmarket\b'), ('LIMIT', r'限價|\blimit\b')
    ) if re.search(pattern, text)]
    if len(types) > 1:
        ambiguous = True
    elif types:
        fields['order_type'] = types[0]

    for field, label in _LABELS.items():
        values = re.findall(r'(?:' + label + ')' + _LINK + '(' + _NUMBER + ')', text)
        if field == 'lot':
            values += re.findall('(' + _NUMBER + r')\s*(?:手|\blots?\b)', text)
        if field == 'limit_price':
            # A stated entry price is preserved but doesn't itself imply LIMIT.
            values += re.findall(r'(?:買在|賣在|做多|做空)\s*(' + _NUMBER + r')(?!\s*(?:手|lots?\b))', text)
        distinct = list(dict.fromkeys(values))
        clear = field in ('sl', 'tp') and bool(re.search(
            r'(?:' + _CLEAR + r')\s*(?:' + label + r')|(?:' + label + r')\s*(?:' + _CLEAR + ')', text))
        # One clear instruction can apply to a joined SL/TP pair.
        if field in ('sl', 'tp') and re.search(r'(?:' + _CLEAR + r')\s*(?:停損|止損|sl)\s*(?:和|及|與|、|/|跟)\s*(?:停利|止盈|tp)', text):
            clear = True
        if len(distinct) > 1 or (clear and distinct):
            ambiguous = True
        elif clear:
            fields[field] = None
        elif distinct:
            value = _positive_string(distinct[0])
            if value is None:
                ambiguous = True
            else:
                fields[field] = value

    # Alternatives, ranges, percentages or relative amounts require explicit input.
    if re.search(r'\d\s*(?:或(?:者)?|還是|到|至|~|～|—)\s*[\d.]|\d\s*(?:點|pips?\b|美元|美金|%|百分)', text):
        ambiguous = True
    # Explicitly clearing optional stops is allowed; other negation cannot be
    # interpreted as the opposite direction or ignored while patching a field.
    stop_label = r'(?:停損|止損|停利|止盈|sl|tp)'
    if re.search(stop_label + r'\s*(?:不要|不設(?:定)?)\s*(?:清空|清除|取消|移除|刪除|改|設|\d)', text):
        ambiguous = True
    without_clears = re.sub(r'(?:' + _CLEAR + r')\s*' + stop_label, '', text)
    without_clears = re.sub(stop_label + r'\s*(?:' + _CLEAR + ')', '', without_clears)
    if fields and re.search(r'不|別|勿|否定|\bnot\b|\bdon.t\b', without_clears):
        ambiguous = True
    if re.search(r'(?:nan|inf(?:inity)?)\b', text):
        ambiguous = True
    if re.search(r'\d,\d|\d[\d.]*\.\d*\.', text):
        ambiguous = True
    # Don't ignore an incomplete explicit field edit and apply another field.
    for field, label in _LABELS.items():
        if re.search(r'(?:' + label + r')\s*(?:改成|改為|設為|設定為)', text) and field not in fields:
            ambiguous = True
        if re.search(r'(?:' + label + ')' + _LINK + r'[-+\d.]', text) and field not in fields:
            ambiguous = True
    if 'limit_price' in fields and 'order_type' not in fields and re.search(r'買在|賣在|進場價|委託價', text):
        ambiguous = True
    return fields, ambiguous


def _missing(fields: dict) -> list[str]:
    missing = [key for key in ('side', 'lot', 'order_type') if fields.get(key) in (None, '')]
    if fields.get('order_type') == 'LIMIT' and fields.get('limit_price') in (None, ''):
        missing.append('limit_price')
    return missing


def interpret_message(message: str, draft: dict | None = None,
                      analysis_side: str | None = None) -> dict:
    """Classify text and propose an explicit patch without mutating input state.

    ``proposal`` contains explicit candidate fields for a deliberate apply action;
    it is not permission to mutate a draft. ``patch`` is nonempty only for an
    unambiguous PREPARE/EDIT. Missing required fields do not trigger defaults, and
    SL/TP are never required. Unsupported grammar falls back to discussion or a
    single clarification; this is not a general natural-language trading parser.
    """
    text = unicodedata.normalize('NFKC', message).strip().lower()
    previous_side = analysis_side if analysis_side in ('BUY', 'SELL') else None

    def result(intent: str, *, side=None, patch=None, proposal=None,
               explanation='', missing=None) -> dict:
        return dict(intent=intent, analysis_side=side, patch=patch or {},
                    proposal=proposal or {}, message=explanation,
                    missing_fields=missing or [])

    if not text:
        return result('CLARIFY', explanation='請說明要分析的盤面或要準備的委託。')
    educational = bool(re.search(r'如何|怎麼|是什麼|意思|教我|流程', text))
    unsupported = bool(re.search(r'平倉|撤單|(?:取消|撤銷)(?:既有|券商|這張|這筆|全部)?(?:委託|訂單)|實盤|真實資金', text))
    if unsupported and not educational:
        return result('UNSUPPORTED', explanation='對話不執行平倉、撤單或真實資金交易；請使用既有操作入口。')
    fields, ambiguous = _extract_fields(text)
    if ambiguous:
        return result('CLARIFY', explanation='請明確指定單一方向、手數、單型與絕對價格；這次尚未修改委託。')
    side = fields.get('side')
    hypothetical = bool(re.search(r'如果|假如|假設|倘若|萬一|若|要是|想知道|想問|請問|會怎樣|好嗎|可以嗎|\bif\b|what if', text))
    opinion = bool(re.search(r'覺得|認為|看法|可以嗎|適合嗎|是否|怎麼|如何|會不會|分析|討論', text))
    prepare = bool(re.search(r'準備|建立|新增|開一張|下單|幫我(?:買進|買入|賣出)|\bprepare\b|\bcreate\b', text))
    edit = bool(re.search(r'改成|改為|改做|修改|調整|設為|設定|清空|清除|移除|刪除|取消(?:sl|tp|停損|停利)', text))
    numeric_edit = any(key in fields for key in ('lot', 'limit_price', 'sl', 'tp'))
    if hypothetical or educational or (opinion and not prepare and not edit):
        return result('DISCUSS', side=side or previous_side, proposal=fields,
                      explanation='依此方向分析；準備中的委託保留原值。')
    if prepare or edit or (draft is not None and numeric_edit):
        intent = 'EDIT' if draft is not None and not prepare else 'PREPARE'
        if not fields and edit:
            return result('CLARIFY', explanation='請指定要修改的欄位與數值。')
        effective = dict(draft or {})
        effective.update(fields)
        return result(intent, side=side, patch=fields, proposal=fields,
                      explanation='已辨識明確欄位，仍須檢查委託並由你確認。',
                      missing=_missing(effective))
    return result('DISCUSS', side=side or previous_side, proposal=fields,
                  explanation='依此方向討論盤面；如要建立委託，請明確要求準備委託。')
