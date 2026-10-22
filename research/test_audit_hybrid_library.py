from research.audit_hybrid_library import audit_library


def test_audit_rejects_future_bars_and_unmatured_cases_without_disclosing_ids():
    cases = [
        {'id': 'private-a', 'group': 'g1', 'side': 'BUY', 'available_at': 2000},
        {'id': 'private-b', 'group': 'g2', 'side': 'SELL', 'available_at': 900},
    ]
    profiles = {
        'private-a': {'as_of': 1000, 'tier': '5m_only', 'pre_entry_bars': {
            '5m': [{'time': 600, 'close': '100'}] * 60}},
        'private-b': {'as_of': 1000, 'tier': '5m_only', 'pre_entry_bars': {
            '5m': [{'time': 900, 'close': '100'}] * 60}},
    }
    result = audit_library(cases, profiles)
    assert result['cases_total'] == 2
    assert result['profiles_ready'] == 2
    assert result['mature_after_entry'] == 1
    assert result['not_mature_after_entry'] == 1
    assert result['future_or_unclosed_five_minute_profiles'] == 1
    assert 'private-a' not in str(result)
    assert 'private-b' not in str(result)
