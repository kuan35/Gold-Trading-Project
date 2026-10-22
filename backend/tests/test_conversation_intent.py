"""Safety behavior of the deterministic, local conversation interpreter."""
from copy import deepcopy

import pytest

from backend.conversation_intent import interpret_message


BUY_DRAFT = {
    'side': 'BUY', 'lot': '0.1', 'order_type': 'LIMIT',
    'limit_price': '4090', 'sl': '4080', 'tp': '4110',
}


def test_directional_opinion_only_selects_analysis():
    result = interpret_message('我覺得可以做多')
    assert result['intent'] == 'DISCUSS'
    assert result['analysis_side'] == 'BUY'
    assert result['patch'] == {}
    assert result['missing_fields'] == []


def test_hypothetical_sell_preserves_buy_draft_and_offers_explicit_proposal():
    draft = deepcopy(BUY_DRAFT)
    result = interpret_message('如果改做空呢？', draft=draft)
    assert result['intent'] == 'DISCUSS'
    assert result['analysis_side'] == 'SELL'
    assert result['patch'] == {}
    assert result['proposal'] == {'side': 'SELL'}
    assert draft == BUY_DRAFT


def test_explicit_prepare_extracts_decimal_strings_without_float_rounding():
    result = interpret_message('幫我準備0.10手限價做多4090.25，停損4080，停利4110.50')
    assert result['intent'] == 'PREPARE'
    assert result['patch'] == {
        'side': 'BUY', 'lot': '0.10', 'order_type': 'LIMIT',
        'limit_price': '4090.25', 'sl': '4080', 'tp': '4110.50',
    }
    assert result['missing_fields'] == []


def test_explicit_market_edit_does_not_copy_unspecified_fields_into_patch():
    result = interpret_message('把這張改成市價，手數改成0.25', draft=BUY_DRAFT)
    assert result['intent'] == 'EDIT'
    assert result['patch'] == {'order_type': 'MARKET', 'lot': '0.25'}
    assert result['missing_fields'] == []


@pytest.mark.parametrize('message,patch', [
    ('停利改成4120.05', {'tp': '4120.05'}),
    ('停損4082，停利4115', {'sl': '4082', 'tp': '4115'}),
    ('清空停損和停利', {'sl': None, 'tp': None}),
    ('取消SL，移除TP', {'sl': None, 'tp': None}),
    ('0.20手', {'lot': '0.20'}),
    ('改做空', {'side': 'SELL'}),
])
def test_explicit_draft_edits(message, patch):
    result = interpret_message(message, draft=BUY_DRAFT)
    assert result['intent'] == 'EDIT'
    assert result['patch'] == patch


@pytest.mark.parametrize('message', [
    '幫我準備買在4090', '停損20點', '停利改成30美元',
    '改做多或做空', '不要做空', '不是做多，是做空',
    '幫我準備0.1或0.2手做多市價', '手數改成-0.1',
    '限價改成NaN', '停損改成0',
    '不要準備0.1手市價', '先不修改停損4080',
    '手數改0.2，但不要市價', '停損4080還是4090',
    '停損改成4,080', '準備0.1手市價做多，SL4080.5.5',
    '停損不要清空', 'SL不要改成4080',
])
def test_ambiguity_negation_conflict_or_invalid_amount_cannot_patch(message):
    result = interpret_message(message, draft=BUY_DRAFT)
    assert result['intent'] == 'CLARIFY'
    assert result['patch'] == {}
    assert result['message']


def test_missing_required_fields_never_default_from_previous_analysis():
    result = interpret_message('幫我準備一張委託', analysis_side='BUY')
    assert result['intent'] == 'PREPARE'
    assert result['patch'] == {}
    assert result['missing_fields'] == ['side', 'lot', 'order_type']


def test_limit_requires_price_but_not_optional_stops():
    result = interpret_message('準備0.1手限價做空')
    assert result['patch'] == {'side': 'SELL', 'lot': '0.1', 'order_type': 'LIMIT'}
    assert result['missing_fields'] == ['limit_price']


def test_analysis_side_continues_only_for_discussion():
    assert interpret_message('那風險呢？', analysis_side='SELL')['analysis_side'] == 'SELL'
    result = interpret_message('準備0.1手市價', analysis_side='SELL')
    assert result['analysis_side'] is None
    assert result['missing_fields'] == ['side']
    assert 'side' not in result['patch']


@pytest.mark.parametrize('message', ['幫我平倉', '取消券商委託', '幫我撤單',
                                    '幫我取消這張委託', '直接實盤買進0.1手'])
def test_unsupported_actions_never_generate_a_patch(message):
    result = interpret_message(message, draft=BUY_DRAFT)
    assert result['intent'] == 'UNSUPPORTED'
    assert result['patch'] == {}


def test_explaining_closing_is_discussion_and_has_no_trade_patch():
    result = interpret_message('如何平倉？', draft=BUY_DRAFT)
    assert result['intent'] == 'DISCUSS'
    assert result['patch'] == {}


def test_empty_message_requests_clarification_without_side_default():
    result = interpret_message('  ')
    assert result['intent'] == 'CLARIFY'
    assert result['analysis_side'] is None
    assert result['patch'] == {}


@pytest.mark.parametrize('message', ['停損改成4080會怎樣？', '停利改成4120好嗎？'])
def test_edit_scenario_question_is_discussion_without_modifying_draft(message):
    result = interpret_message(message, draft=BUY_DRAFT)
    assert result['intent'] == 'DISCUSS'
    assert result['patch'] == {}
@pytest.mark.parametrize('message', ['若改做空呢？','要是把停損改成4080呢？','我想知道停損改成4080的風險','幫我分析如果改做空的風險'])
def test_hypothetical_or_risk_inquiry_never_mutates_draft(message):
    result=interpret_message(message,{'side':'BUY','sl':'4100','lot':'.1','order_type':'MARKET'},'BUY')
    assert result['intent']=='DISCUSS'
    assert result['patch']=={}

def test_lot_after_direction_is_not_misread_as_a_second_entry_price():
    result=interpret_message('想用限價4200做多0.1手，停損4190',{})
    assert result['intent']=='EDIT'
    assert result['patch']=={'side':'BUY','order_type':'LIMIT','lot':'0.1','limit_price':'4200','sl':'4190'}
    result=interpret_message('準備做多0.1手市價',{})
    assert result['patch']=={'side':'BUY','order_type':'MARKET','lot':'0.1'}
