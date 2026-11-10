"""Filled fact values must not leave doubled punctuation or repeated direction words."""
from backend.live_assistant import render_program_sections, render_sections, tidy_text


FACTS = [
    dict(id='advice.opening', text='綜合建議開場：{{advice_opening_state}}。',
         values=dict(advice_opening_state='偏多，優先找做多機會')),
    dict(id='advice.direction', text='目前方向{{advice_direction_state}}。方向依據{{advice_direction_reason_state}}。',
         values=dict(advice_direction_state='偏多',
                     advice_direction_reason_state='五分鐘末根已收 K 高於 最近100分鐘均價，短線方向以這個週期判讀。')),
]


def test_model_sections_drop_repeated_direction_and_doubled_punctuation():
    raw = [dict(title='綜合建議', fact_ids=['advice.opening', 'advice.direction'],
                text='{{advice_opening_state}}，{{advice_direction_state}}；方向依據是{{advice_direction_reason_state}}。'
                     '可嘗試的條件是：等待確認後再進場。，目前沒有明確參考價位。')]
    text = render_sections(raw, FACTS)[0]['text']
    assert text == ('偏多，優先找做多機會；方向依據是五分鐘末根已收 K 高於最近100分鐘均價，短線方向以這個週期判讀。'
                    '可嘗試的條件是：等待確認後再進場。目前沒有明確參考價位。')


def test_program_sections_use_the_same_tidy_rules():
    text = render_program_sections([dict(title='方向', fact_ids=['advice.direction'])], FACTS)[0]['text']
    assert '。。' not in text and '高於最近100分鐘均價' in text


def test_tidy_keeps_latin_spacing_newlines_and_distinct_clauses():
    assert tidy_text('已收 K 高於 均價。\n下一段，偏空；偏多。') == '已收 K 高於均價。\n下一段，偏空；偏多。'
    assert tidy_text('偏空，優先找做空機會，偏空。') == '偏空，優先找做空機會。'
    assert tidy_text('條件一，，條件二；；結束。。') == '條件一，條件二；結束。'
