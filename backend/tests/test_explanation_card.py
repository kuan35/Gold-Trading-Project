"""Grounded card regressions using synthetic fixtures; never calls a provider."""
import json
import pytest
from copy import deepcopy
from backend import assistant, evidence
from backend.tests.test_assistant_context import synthetic_engine


def context(monkeypatch, empty=False):
    engine = synthetic_engine(monkeypatch)
    if empty:
        engine.cases.items = []
    draft = engine.create_draft('BUY', '0.10', None, None)
    return engine, assistant.build_context(engine, draft=draft)


def selection(catalog):
    return {key: value['defaults'] for key, value in catalog['sections'].items()}


def all_text(card):
    return '\n'.join(f['text'] for s in card['sections'] for f in s['facts'])


def test_card_no_match_still_has_market_risk_and_sources(monkeypatch):
    _, ctx = context(monkeypatch, empty=True)
    catalog = evidence.build_catalog(ctx)
    card = evidence.render_card(catalog, None, 'disabled', 'test')
    assert [s['id'] for s in card['sections']] == ['market', 'history', 'risk', 'limits']
    text = all_text(card)
    assert '沒有符合' in text and '歷史回放' in text
    assert '低於' in text and '情境' in text and '0.10' in text
    assert all(f['source'] and f['evidence'] for s in card['sections'] for f in s['facts'])
    assert card['as_of_utc'] == ctx['market']['as_of_utc']


def test_model_can_select_order_but_cannot_write_facts(monkeypatch):
    _, ctx = context(monkeypatch)
    catalog = evidence.build_catalog(ctx)
    chosen = selection(catalog)
    chosen['market'] = ['market.1h', 'market.5m']
    card = evidence.render_card(catalog, json.dumps(chosen), 'ok', 'test')
    assert card['status'] == 'ok'
    assert card['sections'][0]['facts'][0]['id'] == 'market.1h'
    assert '市場必漲' not in all_text(card)
    assert '資料不足' in all_text(card) or '僅供' in all_text(card)


def test_injection_unknown_cross_section_duplicate_or_missing_sections_fall_back(monkeypatch):
    _, ctx = context(monkeypatch)
    catalog = evidence.build_catalog(ctx)
    good = selection(catalog)
    bad = []
    for value in ('市場必漲', 'risk.exposure', good['market'][0]):
        candidate = deepcopy(good)
        candidate['market'] = [good['market'][0], value]
        bad.append(candidate)
    bad += [{'market': []}, dict(good, advice='買進'), dict(good, market=[])]
    fallback = evidence.render_card(catalog, None, 'disabled', 'test')
    for candidate in bad:
        card = evidence.render_card(catalog, json.dumps(candidate), 'ok', 'test')
        assert card['status'] == 'invalid_selection'
        assert card['sections'] == fallback['sections']


def test_model_cannot_hide_pool_caveats_or_both_outcome_examples(monkeypatch):
    _, ctx = context(monkeypatch)
    catalog = evidence.build_catalog(ctx)
    chosen = selection(catalog)
    chosen['history'] = ['history.status']
    chosen['limits'] = [chosen['limits'][0]]
    card = evidence.render_card(catalog, json.dumps(chosen), 'ok', 'test')
    text = all_text(card)
    assert '不是本筆勝率' in text and '候選群' in text
    assert '獲利' in text and '虧損' in text
    assert '尚未核實' in text and '合成' in text


def test_price_scenarios_are_total_pnl_not_incremental_loss(monkeypatch):
    _, ctx = context(monkeypatch)
    ctx['draft']['risk']['scenarios'] = [dict(move='-5.00', loss='-12.34')]
    catalog = evidence.build_catalog(ctx)
    card = evidence.render_card(catalog, None, 'disabled', 'test')
    assert '浮動獲利 12.34 USD' in all_text(card)
    assert '總部位' in all_text(card) and '額外損失' not in all_text(card)


def test_plain_prose_invalid_json_and_truncation_do_not_claim_llm_success(monkeypatch):
    _, ctx = context(monkeypatch)
    catalog = evidence.build_catalog(ctx)
    for content, status in [('盤面高於均線', 'ok'), ('{', 'ok'), (json.dumps(selection(catalog)), 'truncated')]:
        card = evidence.render_card(catalog, content, status, 'test')
        assert card['status'] != 'ok' and card['origin'] == 'program'


def test_chat_and_form_use_catalog_without_mutating_order_state(monkeypatch):
    engine, _ = context(monkeypatch)
    calls = []
    def explain(ctx, question, *, catalog=None):
        assert catalog is not None
        calls.append(catalog)
        return dict(status='ok', text=json.dumps(selection(catalog)), model='test')
    monkeypatch.setattr(assistant, 'explain_context', explain)
    reply = assistant.respond(engine, '分析風險', 'BUY', '0.10')
    draft = assistant.explain_draft(engine, engine.create_draft('BUY', '0.10', None, None))
    assert reply['explanation_card']['status'] == draft['explanation_card']['status'] == 'ok'
    assert len(calls) == 2 and not engine.orders and not engine.positions
    assert '尚未建立' in reply['message']


def test_future_candles_do_not_change_catalog(monkeypatch):
    engine, ctx = context(monkeypatch)
    before = evidence.build_catalog(ctx)
    engine.bars[engine.cursor]['close'] = '99999'
    assert evidence.build_catalog(assistant.build_context(engine, draft=engine.drafts[next(iter(engine.drafts))])) == before


def test_draft_snapshot_cannot_mix_new_market_with_old_risk(monkeypatch):
    engine, _ = context(monkeypatch)
    draft = engine.drafts[next(iter(engine.drafts))]
    engine.step(1)
    with pytest.raises(assistant.DomainError, match='行情已更新'):
        assistant.explain_draft(engine, draft)


def test_unknown_currency_and_bid_ask_are_explained_without_guessing(monkeypatch):
    _, ctx = context(monkeypatch)
    ctx['historical_reference']['cases'][0]['currency'] = 'NOT_STATED_IN_CSV'
    catalog = evidence.build_catalog(ctx)
    card = evidence.render_card(catalog, None, 'disabled', 'test')
    assert 'NOT_STATED_IN_CSV' not in all_text(card)
    assert '幣別未確認' in all_text(card)
    assert '可賣出價（Bid）' in all_text(card) and '可買進價（Ask）' in all_text(card)
