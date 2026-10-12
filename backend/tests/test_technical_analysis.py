from decimal import Decimal
from backend import technical


def sequence(values):
    return [dict(time=i*300,open=str(v),high=str(v+1),low=str(v-1),close=str(v),volume=100) for i,v in enumerate(values)]


def test_wilder_rsi_ema_macd_atr_and_population_bands():
    bars=sequence(list(range(100,180)))
    result=technical.analyze(bars,300,80*300)
    assert result['rsi14']=='100.00'
    assert Decimal(result['atr14'])==2
    assert Decimal(result['macd_line'])==7
    assert Decimal(result['macd_signal'])==7
    assert Decimal(result['macd_histogram'])==0
    assert Decimal(result['boll_middle'])==Decimal('169.50')
    expected=Decimal('169.5')+2*(Decimal(399)/12).sqrt()
    assert abs(Decimal(result['boll_upper'])-expected)<Decimal('.01')


def test_flat_market_is_neutral_and_short_history_is_unknown():
    flat=technical.analyze(sequence([100]*80),300,80*300)
    assert flat['rsi14']=='50.00'
    short=technical.analyze(sequence([100]*5),300,1500)
    assert short['rsi14'] is None and short['macd_line'] is None
    assert short['levels']['status']=='candidate'


def test_future_candles_do_not_change_analysis_and_pivots_need_two_right_bars():
    bars=sequence([100,101,110,102,101])
    early=technical.analyze(bars,300,900)
    assert not early['levels']['resistance']
    confirmed=technical.analyze(bars,300,1500)
    assert confirmed['levels']['resistance'][0]['price']=='111.00'
    assert confirmed['levels']['resistance'][0]['confirmed_at']==1500
    future=dict(sequence([99999])[0],time=1500)
    assert technical.analyze(bars+[future],300,900)==early


def test_incomplete_higher_timeframe_is_not_included():
    bars=sequence(list(range(100,180)))
    result=technical.analyze(bars,900,80*300)
    assert result['last_closed_at']<=80*300
    assert result['count']==26


def test_rsi_matches_known_mixed_gain_loss_seed():
    values=[Decimal(v) for v in ['44.34','44.09','44.15','43.61','44.33','44.83','45.10','45.42','45.84','46.08','45.89','46.03','45.61','46.28','46.28']]
    assert technical.analyze(sequence(values),300,15*300)['rsi14']=='70.46'
