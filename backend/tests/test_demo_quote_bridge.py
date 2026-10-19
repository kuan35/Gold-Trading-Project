from backend.demo_quote_bridge import sanitize_quote_result


def test_quote_bridge_returns_only_read_only_market_fields():
    result = sanitize_quote_result({
        'quote_status': 'CURRENT', 'environment': 'demo', 'token_scope': 'TRADE',
        'demo_account_count': 1, 'gold_symbols': ['XAUUSD'], 'orders_sent': 0,
        'quote': {'bid': '4169.78', 'ask': '4169.95',
                  'source_time_utc': '2026-10-19T12:10:11+00:00',
                  'age_seconds': 0.7, 'freshness': 'CURRENT'},
    })
    assert result == {'source': 'ctrader_demo_xauusd', 'environment': 'demo',
                      'status': 'CURRENT', 'bid': '4169.78', 'ask': '4169.95',
                      'source_time_utc': '2026-10-19T12:10:11+00:00',
                      'age_seconds': 0.7, 'order_connection': False}
    assert 'token_scope' not in result
    assert 'demo_account_count' not in result


def test_quote_bridge_does_not_pass_through_broken_or_unavailable_quote():
    result = sanitize_quote_result({'quote_status': 'TIMEOUT',
                                    'quote': {'bid': '1', 'ask': '2'}})
    assert result['bid'] is None
    assert result['ask'] is None
    assert result['status'] == 'TIMEOUT'
