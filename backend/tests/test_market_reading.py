from decimal import Decimal as D
import json
import pytest
from backend import technical, evidence
from backend.tests.test_technical_analysis import sequence
from backend.tests.test_assistant_context import synthetic_engine
from backend import assistant


def snapshot(**overrides):
    values=dict(close=D('102'),ma20=D('101'),ma60=D('100'),rsi14=D('60'),
                macd_line=D('1'),macd_histogram=D('.2'),atr14=D('2'),
                boll_middle=D('101'),boll_lower=D('98'),boll_upper=D('104'),source_volume_ratio=D('.8'))
    values.update(overrides)
    return technical.interpret(values)


@pytest.mark.parametrize('close,ma20,ma60,bias',[
    ('102','101','100','bullish'),('98','99','100','bearish'),
    ('99.5','99','100','bearish_rebound'),('100.5','101','100','bullish_pullback'),
    ('101','99','100','mixed'),('100','100','100','mixed')])
def test_structure_separates_trend_from_rebound(close,ma20,ma60,bias):
    reading=snapshot(close=D(close),ma20=D(ma20),ma60=D(ma60))
    assert reading['bias']==bias
    assert all(value in reading['reasons'][0] for value in (f'{D(close):.2f}',f'{D(ma20):.2f}',f'{D(ma60):.2f}'))


def test_negative_macd_positive_hist_is_not_claimed_new_bull_cross():
    text=snapshot(macd_line=D('-3'),macd_histogram=D('2'))['indicators']['macd']
    assert '12期快均線低於26期慢均線' in text
    assert '高於訊號線' in text and '反彈' in text
    assert '剛' not in text and '金叉' not in text


def test_volatility_and_source_volume_do_not_vote_for_direction():
    base=snapshot()
    changed=snapshot(atr14=D('200'),source_volume_ratio=D('12'))
    assert changed['bias']==base['bias']
    assert '不分多空' in changed['indicators']['atr']
    assert '不能單獨判斷方向' in changed['indicators']['volume']
    assert '低於前20根平均' in base['indicators']['volume']


def test_missing_warmup_not_flat_or_bullish_and_future_is_ignored():
    bars=sequence(list(range(100,180)))
    short=technical.analyze(bars,300,5*300)['reading']
    assert short['bias']=='insufficient'
    assert '不足' in short['indicators']['rsi']
    assert technical.analyze(bars,300,60*300)==technical.analyze(bars[:60],300,60*300)
    assert technical.analyze(bars,300,80*300)['reading']['bias']=='bullish'


def test_card_cannot_hide_direction_and_explanations(monkeypatch):
    engine=synthetic_engine(monkeypatch)
    ctx=assistant.build_context(engine)
    catalog=evidence.build_catalog(ctx)
    chosen={key:[section['facts'][0]['id']] for key,section in catalog['sections'].items()}
    card=evidence.render_card(catalog,json.dumps(chosen),'ok','test')
    fact=next(f for f in card['sections'][0]['facts'] if f['id']=='market.5m.reading')
    assert ctx['market']['frames'][0]['reading']['label'] in fact['text']
    assert 'MA20' in fact['text'] and '訊號線' in fact['text']
