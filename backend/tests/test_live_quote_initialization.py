import pytest
from backend.live_assistant import build_live_context


@pytest.mark.parametrize('source_time', [None, 0, {}, 'invalid'])
def test_initial_quote_without_a_valid_timestamp_is_unavailable(source_time):
    context = build_live_context({'connection_status': 'CONNECTED', 'quote': {
        'source_time_utc': source_time, 'status': 'CURRENT', 'bid': None, 'ask': None,
    }}, now=1800000000)
    assert context['status'] == 'UNAVAILABLE'
    assert context['facts'] == []
