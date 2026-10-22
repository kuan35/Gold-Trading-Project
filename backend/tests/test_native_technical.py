"""Native bars must carry their own history, never fabricated five-minute bars."""
from decimal import Decimal

import pytest

from backend import technical


def bars(count=120, seconds=300):
    result = []
    for i in range(count):
        close = Decimal(2000) + Decimal(i) / 10 + Decimal((i % 9) - 4) / 2
        result.append(dict(time=i * seconds, open=str(close - Decimal('.1')),
                           high=str(close + 1), low=str(close - 1), close=str(close),
                           volume=str(100 + i % 11)))
    return result


def native_analysis(candles, seconds, clock):
    assert callable(getattr(technical, 'analyze_native', None)), 'native indicator entry point is missing'
    return technical.analyze_native(candles, seconds, clock)


@pytest.mark.parametrize('seconds', [300, 900, 3600])
def test_native_matches_existing_aggregated_indicator_formulas(seconds):
    source = bars(1440)
    clock = len(source) * 300
    native = []
    for offset in range(0, len(source), seconds // 300):
        group = source[offset:offset + seconds // 300]
        native.append(dict(time=group[0]['time'], open=group[0]['open'], close=group[-1]['close'],
                           high=str(max(Decimal(b['high']) for b in group)),
                           low=str(min(Decimal(b['low']) for b in group)),
                           volume=str(sum((Decimal(b['volume']) for b in group), Decimal(0)))))
    expected = technical.analyze(source, seconds, clock)
    actual = native_analysis(native, seconds, clock)
    assert {key: actual[key] for key in expected} == expected


def test_hourly_history_produces_rsi_atr_and_ma60_independent_of_short_5m_window():
    result = native_analysis(bars(120, 3600), 3600, 120 * 3600)
    assert result['count'] == 120
    assert Decimal(result['rsi14']) > 0
    assert Decimal(result['atr14']) > 0
    # Indices 60..119 average 89.5; their nine-step offsets sum to zero.
    assert result['ma60'] == '2008.95'
    assert result['ma20'] == result['boll_middle']
    assert result['reading']['bias'] != 'insufficient'
    # The same span represented by only 120 five-minute bars cannot supply MA60.
    assert technical.analyze(bars(120), 3600, 120 * 300)['reading']['bias'] == 'insufficient'


def test_forming_and_future_native_bars_cannot_change_closed_indicators():
    source = bars(122)
    actual = native_analysis(source, 300, 120 * 300 + 100)
    expected = native_analysis(source[:120], 300, 120 * 300 + 100)
    assert actual['count'] == 120
    assert actual['last_closed_at'] == 120 * 300
    for key in ('rsi14', 'atr14', 'ma60', 'source_volume_ratio', 'levels', 'reading'):
        assert actual[key] == expected[key]
    assert actual['data_quality']['excluded_unclosed_count'] == 2


@pytest.mark.parametrize('field,value', [('open', None), ('close', 'NaN'), ('high', 'Infinity'),
                                         ('low', '0'), ('high', '1'), ('close', 'bad')])
def test_malformed_ohlc_is_excluded_and_explained_without_zero_prices(field, value):
    source = bars(21)
    source[-1][field] = value
    result = native_analysis(source, 300, 21 * 300)
    assert result['count'] == 20
    assert result['last_closed_at'] == 20 * 300
    assert result['data_quality']['rejected_price_count'] == 1
    assert result['data_quality']['reasons']
    assert result['source_volume_ratio'] is None


@pytest.mark.parametrize('value', [None, 'NaN', '-1', 'bad'])
def test_unknown_source_volume_does_not_become_zero_or_remove_valid_prices(value):
    source = bars(25)
    source[-2]['volume'] = value
    result = native_analysis(source, 300, 25 * 300)
    assert result['count'] == 25
    assert result['source_volume_ratio'] is None
    assert result['data_quality']['unknown_volume_count'] == 1
    assert '不足' in result['reading']['indicators']['volume']


def test_missing_volume_outside_comparison_window_does_not_prevent_known_ratio():
    source = bars(25)
    del source[0]['volume']
    result = native_analysis(source, 300, 25 * 300)
    assert result['source_volume_ratio'] is not None
    assert result['data_quality']['unknown_volume_count'] == 1


@pytest.mark.parametrize('change', ['duplicate', 'out_of_order', 'non_integer', 'unaligned'])
def test_invalid_native_time_sequence_is_rejected_instead_of_silently_repaired(change):
    source = bars(25)
    if change == 'duplicate':
        source[-1]['time'] = source[-2]['time']
    elif change == 'out_of_order':
        source[-2], source[-1] = source[-1], source[-2]
    elif change == 'non_integer':
        source[-1]['time'] = '7200'
    else:
        source[-1]['time'] += 1
    result = native_analysis(source, 300, 30 * 300)
    assert result['count'] == 0
    assert result['rsi14'] is None
    assert result['ma60'] is None
    assert result['data_quality']['status'] == 'invalid'
    assert result['data_quality']['reasons']


def test_missing_native_interval_is_reported_without_filling_or_inventing_volume():
    source = bars(25)
    del source[8]
    result = native_analysis(source, 300, 25 * 300)
    assert result['count'] == 24
    assert result['data_quality']['gap_count'] == 1
    assert result['data_quality']['missing_interval_count'] == 1
    assert result['data_quality']['status'] == 'partial'
    assert result['last_closed_at'] == 25 * 300


def test_empty_native_input_is_insufficient_without_fabricated_values():
    result = native_analysis([], 3600, 120 * 3600)
    assert result['count'] == 0
    assert result['close'] is None
    assert result['rsi14'] is None
    assert result['source_volume_ratio'] is None
    assert result['data_quality']['status'] == 'insufficient'
