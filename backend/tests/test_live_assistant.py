from datetime import datetime,timezone
from copy import deepcopy
import json
import pytest
from backend import live_assistant as live

NOW=1800003600

def test_clock_lead_is_explained_without_relaxing_quote_or_order_checks():
    s=snapshot();s['quote']['source_time_utc']=datetime.fromtimestamp(NOW+.165,timezone.utc).isoformat()
    answer=live.respond_live(s,'分析盤面',now=NOW)
    assert answer['llm_status']=='market_unavailable'
    assert '時鐘' in answer['message']
    assert '沒有5秒內' not in answer['message']


def snapshot():
    def bars(span):
        return [dict(time=NOW-(120-i)*span,open=4000+i,high=4002+i,low=3999+i,close=4001+i,volume=100+i) for i in range(120)]
    return dict(connection_status='CONNECTED',quote=dict(status='CURRENT',bid='4120.12',ask='4120.32',
        source_time_utc=datetime.fromtimestamp(NOW,timezone.utc).isoformat(),age_seconds=0),
        bars={key:bars(span) for key,span in [('5m',300),('15m',900),('1h',3600)]},
        account={'account_id':'SECRETACCOUNT','balance':'999999'},forming={'secret':'not_for_analysis'},access_token='SECRETKEY')


def test_live_context_has_native_three_frames_and_no_private_account_or_forming_data():
    context=live.build_live_context(snapshot(),now=NOW)
    assert context['status']=='CURRENT'
    assert [f['interval'] for f in context['frames']]==['5m','15m','1h']
    assert all(f['count']==120 and f['ma60'] is not None for f in context['frames'])
    assert 'SECRET' not in json.dumps(context)
    assert 'account' not in context and 'forming' not in context
    assert context['as_of_utc']==datetime.fromtimestamp(NOW,timezone.utc).isoformat()


def test_stale_future_and_disconnected_data_never_gets_a_live_model_answer(monkeypatch):
    monkeypatch.setattr(live,'explain_context',lambda *a,**k:pytest.fail('must not call model'))
    for adjust in ({'connection_status':'DISCONNECTED'},{'quote':dict(snapshot()['quote'],age_seconds=20)},
                   {'quote':dict(snapshot()['quote'],source_time_utc=datetime.fromtimestamp(NOW+1,timezone.utc).isoformat())}):
        s=snapshot();s.update(adjust)
        answer=live.respond_live(s,'現在盤面如何',enabled=True,now=NOW)
        assert answer['llm_status']=='market_unavailable' and answer['draft'] is None
        assert answer['market_status']!='CURRENT'


@pytest.mark.parametrize('lead_seconds',[.02,.1])
def test_subsecond_broker_clock_jitter_does_not_hide_an_otherwise_current_quote(lead_seconds):
    s=snapshot();s['quote']['source_time_utc']=datetime.fromtimestamp(NOW+lead_seconds,timezone.utc).isoformat()
    context=live.build_live_context(s,now=NOW)
    assert context['status']=='CURRENT' and context['quote_clock_tolerance_ms']==100
    assert 0<context['quote_clock_skew_ms']<=100


def test_quote_beyond_clock_jitter_tolerance_remains_unavailable():
    s=snapshot();s['quote']['source_time_utc']=datetime.fromtimestamp(NOW+.101,timezone.utc).isoformat()
    assert live.build_live_context(s,now=NOW)['status']=='UNAVAILABLE'


def test_tolerated_quote_clock_jitter_cannot_advance_into_next_closed_bar_boundary():
    boundary=int(NOW)//300*300
    s=snapshot();s['quote']['source_time_utc']=datetime.fromtimestamp(boundary+.02,timezone.utc).isoformat()
    assert live.build_live_context(s,now=boundary-.02)['status']=='UNAVAILABLE'


def test_opt_in_is_required_and_program_fallback_still_explains_frames(monkeypatch):
    monkeypatch.setattr(live,'explain_context',lambda *a,**k:pytest.fail('opt-in missing'))
    answer=live.respond_live(snapshot(),'說明一小時趨勢',enabled=False,now=NOW)
    assert answer['provider']=='local_market_rules' and answer['llm_status']=='not_requested'
    assert '一小時' in answer['message'] and answer['draft'] is None
    assert answer['sections'] and answer['source']=='ctrader_demo_xauusd'


def test_grounded_narrative_uses_only_referenced_fact_placeholders_and_has_followups(monkeypatch):
    def provider(*a,**k):
        assert 'SECRET' not in json.dumps(k,ensure_ascii=False)
        return dict(status='ok',model='test',text=json.dumps({'sections':[
            {'title':'目前盤面','text':'目前可賣出價為 {{bid}}，買進價為 {{ask}}。','fact_ids':['quote']},
            {'title':'五分鐘背景','text':'{{f5_structure}}；{{f5_bias}}。','fact_ids':['f5.trend']}]}))
    monkeypatch.setattr(live,'explain_context',provider)
    answer=live.respond_live(snapshot(),'目前如何',enabled=True,now=NOW)
    assert answer['llm_status']=='ok' and answer['provider']=='groq_market_analysis'
    assert '4120.12' in answer['message'] and '{{' not in answer['message']
    assert answer['followups'] and answer['evidence']


@pytest.mark.parametrize('section',[
    {'title':'盤面','text':'下一根必漲，建議買進。','fact_ids':['quote']},
    {'title':'盤面','text':'價格 {{unknown}}。','fact_ids':['quote']},
    {'title':'盤面','text':'價格 {{f5_close}}。','fact_ids':['quote']},
    {'title':'盤面','text':'價格5000，獲利機率90%。','fact_ids':['quote']},
    {'title':'盤面','text':'行情上漲。','fact_ids':['invented']},
])
def test_unsupported_claims_and_invented_references_fall_back(section,monkeypatch):
    monkeypatch.setattr(live,'explain_context',lambda *a,**k:dict(status='ok',model='test',text=json.dumps({'sections':[section]})))
    answer=live.respond_live(snapshot(),'分析',enabled=True,now=NOW)
    assert answer['llm_status']=='invalid_grounding' and answer['provider']=='local_market_rules'
    assert '5000' not in answer['message'] and answer['draft'] is None


def test_live_chat_does_not_interpret_order_or_close_as_authorization(monkeypatch):
    monkeypatch.setattr(live,'explain_context',lambda *a,**k:pytest.fail('no order path'))
    answer=live.respond_live(snapshot(),'幫我買進0.1手並直接確認平倉',enabled=True,now=NOW)
    assert answer['draft'] is None and answer['llm_status']=='read_only'
    assert '確認' in answer['message']


def test_support_question_fallback_and_subsecond_quote_are_usable():
    s=snapshot();s['quote']['source_time_utc']=datetime.fromtimestamp(NOW+.5,timezone.utc).isoformat()
    r=live.respond_live(s,'支撐壓力在哪',enabled=False,now=NOW+.8)
    assert r['market_status']=='CURRENT' and '轉折參考' in r['message']


def test_invalid_price_bar_does_not_crash_summary_or_fill_missing_values():
    s=snapshot();s['bars']['5m'][-1]['open']='NaN'
    r=live.respond_live(s,'分析',enabled=False,now=NOW)
    assert '五分鐘完整已收棒不足' in r['message']


def test_fresh_quote_cannot_make_day_old_indicators_current():
    s=snapshot()
    for rows in s['bars'].values():
        for row in rows:row['time']-=86400
    context=live.build_live_context(s,now=NOW)
    assert context['status']=='CURRENT'
    assert not any(f['id'].endswith(('.trend','.momentum','.levels','.range')) for f in context['facts'])
    assert '過期' in str(context['facts'])


@pytest.mark.parametrize('sections',[[None],[5],['text'],[{'title':'行情','text':'目前收盤20，附近壓力60。','fact_ids':['quote']}],
    [{'title':'行情','text':'目前價格為四千五百。','fact_ids':['quote']}],
    [{'title':'下一根必漲','text':'報價{{bid}}。','fact_ids':['quote']}],
    [{'title':'動能','text':'RSI為七十左右，已經超買。','fact_ids':['f5.momentum']}],
    [{'title':'價位','text':'附近支撐在四五〇〇附近。','fact_ids':['f5.momentum']}],
    [{'title':'價格5000','text':'價格{{bid}}。','fact_ids':['quote']}]])
def test_malformed_sections_and_disguised_prices_fall_back(sections,monkeypatch):
    monkeypatch.setattr(live,'explain_context',lambda *a,**k:dict(status='ok',model='test',text=json.dumps({'sections':sections})))
    assert live.respond_live(snapshot(),'分析',enabled=True,now=NOW)['llm_status']=='invalid_grounding'


def test_indicator_period_names_are_allowed_but_not_unverified_market_numbers():
    context=live.build_live_context(snapshot(),now=NOW)
    text='5分鐘與1小時的MA20、MA60、RSI14及MACD12/26/9是不同窗口；{{bid}}是Bid。萬一價格回落，仍需觀察，不把百分比當預測。'
    assert live.render_sections([dict(title='5分與1小時',text=text,fact_ids=['quote'])],context['facts'])


def test_relevance_keeps_both_requested_frames_and_multiple_requested_axes(monkeypatch):
    answer=live.respond_live(snapshot(),'五分鐘和一小時的RSI與波動',now=NOW)
    assert {i for s in answer['sections'] for i in s['fact_ids']} >= {'f5.trend','f1.trend','f5.momentum','f1.momentum','f5.range','f1.range'}
    def provider(*a,**k):
        ids={f['id'] for f in k['catalog']['facts']}
        assert 'f15.momentum' in ids and not any(i.startswith('f1.') or i.startswith('f5.') for i in ids)
        assert 'SECRET' not in json.dumps(k)
        return dict(status='ok',model='test',text=json.dumps({'sections':[{'title':'動能','text':'{{f15_rsi_state}}。','fact_ids':['f15.momentum']}]}))
    monkeypatch.setattr(live,'explain_context',provider)
    assert live.respond_live(snapshot(),'十五分鐘RSI',enabled=True,now=NOW)['llm_status']=='ok'


def test_model_cannot_cite_a_frame_not_in_its_selected_context(monkeypatch):
    monkeypatch.setattr(live,'explain_context',lambda *a,**k:dict(status='ok',model='test',text=json.dumps({'sections':[{'title':'五分鐘','text':'{{f5_bias}}。','fact_ids':['f5.trend']}]})))
    assert live.respond_live(snapshot(),'十五分鐘RSI',enabled=True,now=NOW)['llm_status']=='invalid_grounding'


def test_writer_sees_computed_relationships_but_numbers_are_filled_locally(monkeypatch):
    def provider(*a,**k):
        encoded=json.dumps(k['catalog'],ensure_ascii=False)
        assert '4120.12' not in encoded and 'SECRET' not in encoded
        trend=next(f for f in k['catalog']['facts'] if f['id']=='f5.trend')
        assert '高於' in trend['basis']['f5_structure'] and 'f5_structure' in trend['tokens']
        assert 'values' not in trend
        return dict(status='ok',model='test',text=json.dumps({'sections':[dict(title='五分鐘結構',text='{{f5_structure}}；{{f5_bias}}。這表示價格在兩條均線之上。',fact_ids=['f5.trend'])]}))
    monkeypatch.setattr(live,'explain_context',provider)
    answer=live.respond_live(snapshot(),'五分鐘盤面',enabled=True,now=NOW)
    assert answer['llm_status']=='ok' and '4120.00' in answer['message']


def test_one_bad_model_paragraph_is_replaced_without_discarding_other_grounded_prose(monkeypatch):
    monkeypatch.setattr(live,'explain_context',lambda *a,**k:dict(status='ok',model='test',text=json.dumps({'sections':[
        dict(title='目前報價',text='最新Bid {{bid}}，Ask {{ask}}。',fact_ids=['quote']),
        dict(title='推測波幅',text='波幅較大，價格5000。',fact_ids=['f5.range'])]})))
    answer=live.respond_live(snapshot(),'五分鐘波動',enabled=True,now=NOW)
    assert answer['provider']=='groq_market_analysis' and answer['llm_status']=='partial_grounding'
    assert [s['source'] for s in answer['sections']]==['model','program']
    assert '5000' not in answer['message'] and 'ATR14' in answer['message']
    assert '部分模型段落' in answer['message']


def test_live_quote_below_averages_is_separate_from_last_closed_bullish_structure():
    s=snapshot();s['quote'].update(bid='4000.12',ask='4000.32')
    context=live.build_live_context(s,now=NOW)
    trend=next(f for f in context['facts'] if f['id']=='f5.trend')['values']
    assert trend['f5_bias']=='短線偏多'
    assert '低於 MA20' in trend['f5_live_structure'] and '低於 MA60' in trend['f5_live_structure']
    assert '高於 MA20' in trend['f5_structure']
    narrative=live.writer_facts([next(f for f in context['facts'] if f['id']=='f5.trend')])[0]
    assert '低於 MA20' in narrative['basis']['f5_live_structure'] and '4000.12' not in str(narrative)


def test_followup_inherits_recent_explicit_period_and_general_analysis_can_reset_it(monkeypatch):
    def provider(*a,**k):
        ids={f['id'] for f in k['catalog']['facts']}
        assert 'f15.levels' in ids and not any(i.startswith('f5.') or i.startswith('f1.') for i in ids)
        return dict(status='ok',model='test',text=json.dumps({'sections':[dict(title='轉折參考',text='下方{{f15_support}}，上方{{f15_resistance}}。',fact_ids=['f15.levels'])]}))
    monkeypatch.setattr(live,'explain_context',provider)
    assert live.respond_live(snapshot(),'那支撐壓力呢？',enabled=True,now=NOW,previous_questions=['十五分鐘RSI如何'])['llm_status']=='ok'
    assert live.selection_question('分析目前黃金盤面',['十五分鐘RSI如何'])=='分析目前黃金盤面'
