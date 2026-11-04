"""Private, immutable trading plans survive chats and application restarts."""
from copy import deepcopy
import json

import pytest

from backend.engine import DomainError


def store_type():
    # An assertion gives the initial RED a useful missing-feature failure.
    try:
        from backend import trade_plans
    except ImportError:
        pytest.fail('durable trade plan storage module is missing')
    assert hasattr(trade_plans, 'TradePlanStore'), 'durable trade plan storage is missing'
    return trade_plans.TradePlanStore


def capture(store, account='A', draft_id='draft-1', **kwargs):
    draft = dict(id=draft_id, revision=3, side='BUY', lot='0.10', price='2500.300',
                 sl='2490.00', tp='2520.00', status='REVIEW', source='ctrader_demo_xauusd',
                 environment='demo', account_key=account, account_signature='PRIVATE-SIGNATURE',
                 volume_cents=1000, token='PRIVATE-TOKEN', unexpected='not-public')
    analysis = dict(analysis_ref='analysis-1', snapshot_id='snapshot-1',
                    sections=[{'text': '原本盤面答案'}], evidence={'status': 'NO_MATCH'},
                    case_comparison={'items': []}, outcome_analysis={'status': 'NO_CASES'})
    return store.capture(account, draft, analysis, note='原始進場理由', **kwargs)


def test_constructor_is_lazy_and_reopening_preserves_original_evidence(tmp_path):
    cls = store_type()
    path = tmp_path/'private'/'plans.sqlite3'
    store = cls(path)
    assert not path.exists()
    plan = capture(store, snapshot_bundle={'snapshot_id': 'snapshot-1', 'bars': [{'close': '2500.300'}]})
    reopened = cls(path).get('A', plan['id'])
    assert reopened == plan
    assert reopened['analysis']['evidence']['status'] == 'NO_MATCH'
    assert reopened['snapshot_bundle']['bars'][0]['close'] == '2500.300'
    assert reopened['draft']['price'] == '2500.300'


def test_same_account_and_draft_is_idempotent_and_keeps_first_capture(tmp_path):
    store = store_type()(tmp_path/'plans.sqlite3')
    first = capture(store)
    second = store.capture('A', {'id': 'draft-1', 'price': '9999'}, {'snapshot_id': 'new'}, note='new')
    assert second == first
    assert store.list('A')['total'] == 1
    assert capture(store, account='B')['id'] != first['id']


def test_payloads_and_return_values_are_independent_deep_copies(tmp_path):
    store = store_type()(tmp_path/'plans.sqlite3')
    draft = {'id': 'one', 'side': 'SELL', 'risk': {'scenarios': ['old']}}
    analysis = {'sections': [{'text': 'original'}]}
    risk = {'amount': '500.000', 'warnings': ['old']}
    bundle = {'snapshot_id': 'fixed', 'bars': [{'close': '123.450'}]}
    original = deepcopy((draft, analysis, risk, bundle))
    plan = store.capture('A', draft, analysis, risk=risk, snapshot_bundle=bundle)
    assert (draft, analysis, risk, bundle) == original
    analysis['sections'][0]['text'] = 'changed'
    risk['warnings'].append('changed')
    bundle['bars'][0]['close'] = '0'
    plan['analysis']['sections'].clear()
    reread = store.get('A', plan['id'])
    assert reread['analysis']['sections'][0]['text'] == 'original'
    assert reread['risk'] == original[2]
    assert reread['snapshot_bundle'] == original[3]


def test_account_isolation_and_sql_parameters(tmp_path):
    store = store_type()(tmp_path/'plans.sqlite3')
    account = "A' OR 1=1 --"
    plan = capture(store, account=account)
    assert store.list('B')['items'] == []
    for operation in (lambda: store.get('B', plan['id']),
                      lambda: store.update_review('B', plan['id'], 1, note='intrusion')):
        with pytest.raises(DomainError) as exc:
            operation()
        assert exc.value.status == 404
    assert store.attach_receipt('B', 'draft-1', {'status': 'FILLED'}) is None
    assert store.get(account, plan['id'])['receipt'] is None


def test_review_uses_revision_and_never_replaces_original_reason(tmp_path):
    store = store_type()(tmp_path/'plans.sqlite3')
    plan = capture(store)
    updated = store.update_review('A', plan['id'], plan['revision'], note='事後復盤',
                                  adherence='NO', lesson='下次減少部位')
    assert updated['revision'] == plan['revision'] + 1
    assert updated['note'] == '原始進場理由'
    assert updated['review_note'] == '事後復盤'
    assert updated['adherence'] == 'NO'
    assert updated['lesson'] == '下次減少部位'
    with pytest.raises(DomainError) as exc:
        store.update_review('A', plan['id'], plan['revision'], note='stale')
    assert exc.value.status == 409
    assert store.get('A', plan['id']) == updated


def test_storage_and_ui_payload_exclude_credentials_and_internal_draft_fields(tmp_path):
    path = tmp_path/'plans.sqlite3'
    store = store_type()(path)
    plan = capture(store, snapshot_bundle={'account': {'account_key': 'A', 'token': 'BUNDLE-TOKEN'},
                                         'access_token': 'ACCESS', 'bars': []})
    serialized = json.dumps(plan)
    assert 'account_key' not in serialized and 'account_signature' not in serialized
    for forbidden in ('token', 'volume_cents', 'unexpected', 'PRIVATE-SIGNATURE', 'PRIVATE-TOKEN', 'BUNDLE-TOKEN'):
        assert forbidden not in serialized
        assert forbidden.encode() not in path.read_bytes()


def test_list_is_paginated_stable_summary_without_large_saved_payloads(tmp_path):
    store = store_type()(tmp_path/'plans.sqlite3')
    for i in range(3):
        capture(store, draft_id=str(i), snapshot_bundle={'bars': [1, 2, 3]})
    first, second = store.list('A', limit=1), store.list('A', limit=1, offset=1)
    assert first['total'] == 3 and first['limit'] == 1 and first['offset'] == 0
    assert first['items'][0]['id'] != second['items'][0]['id']
    assert store.list('A', limit=1)['items'] == first['items']
    row = first['items'][0]
    assert row['lot'] == '0.10' and row['price'] == '2500.300'
    assert not {'analysis', 'snapshot_bundle', 'draft', 'risk'} & row.keys()


def test_receipt_progress_never_regresses_or_turns_unknown_into_fill(tmp_path):
    store = store_type()(tmp_path/'plans.sqlite3')
    plan = capture(store)
    unknown = store.attach_receipt('A', plan['draft_id'], {'status': 'UNKNOWN', 'position_id': 'p'})
    assert unknown['receipt']['status'] == 'UNKNOWN'
    accepted = store.attach_receipt('A', plan['draft_id'], {'status': 'ACCEPTED', 'order_id': 'o'})
    assert accepted['receipt']['status'] == 'ACCEPTED'
    late = store.attach_receipt('A', plan['draft_id'], {'status': 'UNKNOWN', 'order_id': 'wrong'})
    assert late['receipt'] == accepted['receipt']
    filled = store.attach_receipt('A', plan['draft_id'], {'status': 'FILLED', 'execution_price': '2500.3100'})
    assert filled['receipt']['execution_price'] == '2500.3100'
    assert filled['receipt']['position_id'] == 'p'
    assert store.attach_receipt('A', plan['draft_id'], {'status': 'ACCEPTED'})['receipt'] == filled['receipt']
    assert store.list('A')['items'][0]['receipt']['status'] == 'FILLED'


@pytest.mark.parametrize('operation', [
    lambda s: s.capture('', {'id': 'x'}, {}),
    lambda s: s.capture('A', {}, {}),
    lambda s: s.capture('A', {'id': 'x'}, []),
    lambda s: s.list('A', limit=0),
    lambda s: s.list('A', offset=-1),
    lambda s: s.update_review('A', 'x', True),
    lambda s: s.update_review('A', 'x', 1, adherence='GUESS'),
])
def test_invalid_requests_have_domain_validation_error(tmp_path, operation):
    store = store_type()(tmp_path/'plans.sqlite3')
    with pytest.raises(DomainError) as exc:
        operation(store)
    assert exc.value.status == 422


def test_enrich_links_only_observed_close_fills_and_never_invents_plan_roi(tmp_path):
    from backend.trade_plans import enrich
    store = store_type()(tmp_path/'plans.sqlite3')
    plan = capture(store)
    plan = store.attach_receipt('A', plan['draft_id'], {'status': 'FILLED', 'position_id': 'p'})
    closes = [
        {'id': 'close-part', 'position_id': 'p', 'role': 'CLOSE', 'status': 'PARTIALLY_FILLED',
         'lot': '0.01', 'realized_gross_pnl': '1.2000', 'commission': None},
        {'id': 'open', 'position_id': 'p', 'role': 'OPEN', 'status': 'FILLED'},
        {'id': 'unconfirmed', 'position_id': 'p', 'role': 'CLOSE', 'status': 'UNKNOWN'},
        {'id': 'different', 'position_id': 'q', 'role': 'CLOSE', 'status': 'FILLED'},
    ]
    activity = {'history': {'broker_deals': {'status': 'CURRENT', 'items': closes, 'has_more': True}},
                'account': {'positions': []}}
    enriched = enrich(plan, activity)
    result = enriched['broker_outcome']
    assert [row['id'] for row in result['closing_deals']] == ['close-part']
    assert result['closing_deals'][0]['realized_gross_pnl'] == '1.2000'
    assert result['fully_closed'] is None and result['net_pnl'] is None and result['roi_pct'] is None
    assert result['status'] == 'CLOSE_DEALS_OBSERVED'
    assert 'broker_outcome' not in plan
    assert store.get('A', plan['id']) == plan
    # The endpoint DTO form is supported, too; stale/absent positions prove nothing.
    stale = enrich(plan, {'broker_deals': {'status': 'STALE', 'items': closes}})['broker_outcome']
    assert stale['status'] == 'UNKNOWN' and stale['closing_deals'] == []
    empty = enrich(plan, {'broker_deals': {'status': 'CURRENT', 'items': []}})['broker_outcome']
    assert empty['status'] == 'UNKNOWN' and empty['fully_closed'] is None


def test_independent_store_instances_enforce_review_revision(tmp_path):
    cls = store_type()
    path = tmp_path/'plans.sqlite3'
    first, second = cls(path), cls(path)
    plan = capture(first)
    second.update_review('A', plan['id'], 1, note='other browser')
    with pytest.raises(DomainError) as exc:
        first.update_review('A', plan['id'], 1, note='old browser')
    assert exc.value.status == 409
