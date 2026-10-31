import pytest
from backend.live_assistant import render_model_sections

FACTS=[dict(id='f5.trend',text='趨勢為{{f5_bias}}。',values={'f5_bias':'上行'})]


def test_replay_of_synthetic_answer_cannot_add_unprovided_ma_structure():
    raw=[dict(title='合成測試說明',text='五分鐘價格與均線結構呈現上行。',fact_ids=['f5.trend'])]
    with pytest.raises(ValueError,match='no grounded narrative'):render_model_sections(raw,FACTS)


def test_unreferenced_indicator_section_is_replaced_without_calling_model():
    raw=[dict(title='趨勢',text='程式判讀{{f5_bias}}。',fact_ids=['f5.trend']),
         dict(title='動能',text='RSI動能偏多。',fact_ids=['f5.trend'])]
    sections,repaired=render_model_sections(raw,FACTS)
    assert repaired and [s['source'] for s in sections]==['model','program']
    assert 'RSI' not in sections[1]['text']


def test_actual_referenced_indicator_remains_usable():
    facts=[dict(id='f5.momentum',text='RSI判讀{{f5_rsi_state}}。',values={'f5_rsi_state':'中性'})]
    sections,repaired=render_model_sections([dict(title='RSI',text='RSI判讀{{f5_rsi_state}}，只能反映已收棒動能。',fact_ids=['f5.momentum'])],facts)
    assert not repaired and sections[0]['source']=='model'
