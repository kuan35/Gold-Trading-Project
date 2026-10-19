"""Repeatable, pre-entry market descriptions for explanation and offline retrieval trials.

This module serializes an already point-in-time profile. It does not assign
similarity scores, make a recommendation, or include post-entry outcomes.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


def _decimal(value: object) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError('market profile has a missing numeric field') from error
    if not number.is_finite():
        raise ValueError('market profile has a non-finite numeric field')
    return number


def _number(value: object, digits: int = 2) -> str:
    number = _decimal(value)
    return f'{number:.{digits}f}'


def describe_market_state(profile: dict) -> dict:
    """Return one fixed-schema description using only bars closed by ``as_of``."""
    if profile.get('status') != 'candidate_only' or profile.get('tier') not in ('full', '5m_only'):
        raise ValueError('market profile is unavailable')
    clock = profile.get('as_of')
    if type(clock) is not int:
        raise ValueError('market profile has no decision timestamp')
    frames = profile.get('pre_entry_bars') or {}
    closed = profile.get('latest_closed') or {}
    expected = ('5m', '15m', '1h') if profile['tier'] == 'full' else ('5m',)
    if set(frames) != set(expected) or set(closed) != set(expected):
        raise ValueError('market profile has incomplete frame coverage')
    if any(type(closed[frame]) is not int or closed[frame] > clock for frame in expected):
        raise ValueError('market profile contains a future bar')
    five = frames['5m']
    if len(five) != 60:
        raise ValueError('market profile needs 60 closed five-minute bars')
    try:
        first = Decimal(str(five[0]['close']))
        last = Decimal(str(five[-1]['close']))
    except (KeyError, IndexError, InvalidOperation, TypeError, ValueError) as error:
        raise ValueError('market profile has invalid closes') from error
    if not first.is_finite() or not last.is_finite():
        raise ValueError('market profile has invalid closes')
    if first <= 0 or last <= 0:
        raise ValueError('market profile has invalid closes')
    path_change = (last / first - 1) * 100
    indicators = profile.get('indicators') or {}
    fields = [
        ('5m_path_change_pct', path_change),
        ('5m_atr_pct', indicators.get('5m_atr_pct')),
        ('5m_ma_gap_atr', indicators.get('5m_ma_gap')),
        ('5m_ma_slope_atr', indicators.get('5m_slope')),
        ('5m_rsi14', indicators.get('5m_rsi14')),
        ('5m_macd_hist_atr', indicators.get('5m_macd_hist')),
        ('5m_range_position', _decimal(indicators.get('range_position')) * 100),
    ]
    if profile['tier'] == 'full':
        fields += [
            ('15m_atr_pct', indicators.get('15m_atr_pct')),
            ('15m_ma_gap_atr', indicators.get('15m_ma_gap')),
            ('15m_rsi14', indicators.get('15m_rsi14')),
            ('15m_macd_hist_atr', indicators.get('15m_macd_hist')),
            ('1h_atr_pct', indicators.get('1h_atr_pct')),
            ('1h_ma_gap_atr', indicators.get('1h_ma_gap')),
        ]
    values = {name: _number(value) for name, value in fields}
    clauses = [
        f'進場前已收60根5分鐘K線；首尾收盤變動 {values["5m_path_change_pct"]}%；'
        f'ATR/價格 {values["5m_atr_pct"]}%；收盤距MA20 {values["5m_ma_gap_atr"]} ATR；'
        f'MA20斜率 {values["5m_ma_slope_atr"]} ATR/棒；RSI14 {values["5m_rsi14"]}；'
        f'MACD柱 {values["5m_macd_hist_atr"]} ATR；60棒區間位置 {values["5m_range_position"]}%。'
    ]
    if profile['tier'] == 'full':
        clauses.append(
            f'15分鐘：ATR/價格 {values["15m_atr_pct"]}%，收盤距MA20 '
            f'{values["15m_ma_gap_atr"]} ATR，RSI14 {values["15m_rsi14"]}，'
            f'MACD柱 {values["15m_macd_hist_atr"]} ATR。'
            f'1小時：ATR/價格 {values["1h_atr_pct"]}%，'
            f'收盤距MA20 {values["1h_ma_gap_atr"]} ATR。'
        )
    else:
        clauses.append('15分鐘與1小時：資料不足，未參與比較。')
    return {
        'schema_version': 'pre_entry_market_v1',
        'as_of': clock,
        'tier': profile['tier'],
        'timezone_status': profile.get('timezone_status', 'UNKNOWN'),
        'values': values,
        'text': ' '.join(clauses),
    }
