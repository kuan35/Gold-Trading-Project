from datetime import datetime, timezone
from types import SimpleNamespace as NS
import pytest
from backend.ticket_preview import ticket_preview
from backend.tests.test_ticket_preview import snapshot, draft, NOW


def test_leverage_200_keeps_dollar_profit_and_price_return_unchanged():
    r = ticket_preview(snapshot(), draft(), now=NOW, leverage='200')
    assert r['margin']['amount_usd'] == '1000.00'
    assert r['margin']['source'] == 'LEVERAGE_ESTIMATE'
    assert r['margin']['leverage'] == '200'
    assert r['sl']['margin_roi_pct'] == '-50.0000'
    assert r['tp']['margin_roi_pct'] == '100.0000'
    assert r['sl']['pnl_usd'] == '-500.00'
    assert r['sl']['price_return_pct'] == '-0.2500'
    q=draft();q.update(side='SELL',sl='4020',tp='3990')
    assert ticket_preview(snapshot(),q,now=NOW)['tp']['margin_roi_pct']=='50.0000'


def broker_margin(**kw):
    return dict(status='AVAILABLE',currency='USD',buy='2000',sell='2500',
                updated_at_utc=datetime.fromtimestamp(NOW,timezone.utc).isoformat(),**kw)


def test_market_prefers_fresh_broker_side_margin_but_limit_uses_entry_assumption():
    q=draft();q['order_type']='MARKET'
    r=ticket_preview(snapshot(),q,now=NOW,expected_margin=broker_margin())
    assert r['margin']['source']=='BROKER_EXPECTED' and r['margin']['amount_usd']=='2000.00'
    assert r['tp']['margin_roi_pct']=='49.5000'
    q.update(side='SELL',sl='4020',tp='3990')
    assert ticket_preview(snapshot(),q,now=NOW,expected_margin=broker_margin())['tp']['margin_roi_pct']=='20.0000'
    r=ticket_preview(snapshot(),draft(),now=NOW,expected_margin=broker_margin())
    assert r['margin']['source']=='LEVERAGE_ESTIMATE' and r['tp']['margin_roi_pct']=='100.0000'


@pytest.mark.parametrize('change',[{'buy':'0'},{'buy':'NaN'},{'currency':'EUR'},
    {'updated_at_utc':datetime.fromtimestamp(NOW-6,timezone.utc).isoformat()},
    {'updated_at_utc':datetime.fromtimestamp(NOW+1,timezone.utc).isoformat()}, {'status':'UNAVAILABLE'}])
def test_bad_broker_margin_cannot_create_fake_actual_roi(change):
    m=broker_margin();m.update(change);q=draft();q['order_type']='MARKET'
    r=ticket_preview(snapshot(),q,now=NOW,expected_margin=m)
    assert r['margin']['source']=='LEVERAGE_ESTIMATE'


@pytest.mark.parametrize('leverage',['0','NaN','Infinity','oops','10001'])
def test_bad_leverage_keeps_usd_but_no_roi(leverage):
    r=ticket_preview(snapshot(),draft(),now=NOW,leverage=leverage)
    assert r['tp']['pnl_usd']=='1000.00'
    assert r['margin']['source']=='UNAVAILABLE' and r['tp']['margin_roi_pct'] is None


def test_money_precision_and_response_identity():
    from scripts.expected_margin import decode_margin
    response=NS(ctidTraderAccountId=12,moneyDigits=8,HasField=lambda _:True,
                margin=[NS(volume=5000,buyMargin=123456789012,sellMargin=99999999999)])
    assert decode_margin(response,12,5000,'USD')['buy']=='1234.56789012'
    with pytest.raises(ValueError):decode_margin(response,13,5000,'USD')
    with pytest.raises(ValueError):decode_margin(response,12,4000,'USD')
    response.moneyDigits=99
    with pytest.raises(ValueError):decode_margin(response,12,5000,'USD')


def test_readonly_cache_deduplicates_expires_and_rejects_wrong_context_or_late_reply():
    from backend.margin_cache import MarginCache
    cache=MarginCache()
    value,cmd=cache.get('account-a:exposure-1',5000,now=0)
    assert value is None and cmd['kind']=='expected_margin'
    assert 'client_order_id' not in cmd
    assert cache.get('account-a:exposure-1',5000,now=1)==(None,None)
    assert cache.accept(dict(request_id=cmd['request_id'],status='AVAILABLE',buy='1000'),now=1)
    assert cache.get('account-a:exposure-1',5000,now=4)[0]['buy']=='1000'
    assert cache.get('account-a:exposure-1',5000,now=6)[0] is None
    _,other=cache.get('account-b:exposure-1',5000,now=7)
    assert other and not cache.accept(dict(request_id=cmd['request_id'],buy='42'),now=7)
    _,new=cache.get('account-b:exposure-2',5000,now=8)
    assert new and not cache.accept(dict(request_id=other['request_id'],buy='42'),now=8)
    assert not cache.accept(dict(request_id=new['request_id'],buy='42'),now=19)
