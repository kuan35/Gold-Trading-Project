from datetime import datetime,timezone
from copy import deepcopy
import json
import pytest
from backend import live_assistant as live

NOW=1800003600

def test_frozen_draft_writer_assesses_this_order_instead_of_a_generic_direction_plan(monkeypatch):
    context=live.build_live_context(snapshot(),now=NOW)
    def provider(*a,**kw):
        prompt=kw['system_prompt']
        assert '這筆委託評估' in prompt
        assert '已填的方向、單型、手數' in prompt
        assert '不代替程式判定委託是否合法' in prompt
        return dict(status='ok',text=json.dumps({'sections':[
            dict(title='這筆委託評估',text='先核對這筆委託的風險。',fact_ids=['f5.trend'])]}))
    monkeypatch.setattr(live,'explain_context',provider)
    reply=live.respond_context(context,'檢查這筆委託',enabled=True,frozen=True)
    assert reply['analysis_mode']=='draft_snapshot'
    assert reply['llm_status']=='ok'
    assert reply['sections'][0]['title']=='這筆委託評估'

def test_presented_moving_average_names_are_plain_language_after_local_substitution():
    facts=[dict(id='f5.trend',text='{{f5_structure}}',values={'f5_structure':'高於 MA20、低於 MA60'})]
    result=live.render_sections([dict(title='均線位置',text='{{f5_structure}}。',fact_ids=['f5.trend'])],facts)
    assert result[0]['text']=='高於 最近100分鐘均價、低於 最近5小時均價。'
    assert facts[0]['values']['f5_structure']=='高於 MA20、低於 MA60'


def test_plain_quotes_and_averages_keep_their_actual_timeframes():
    facts=[dict(id='f1.trend',text='',values={'f1_structure':'Bid 4000；MA20 3990；MA60 3980'}),
           dict(id='f5.trend',text='',values={'f5_structure':'MA20 4010'})]
    result=live.render_sections([dict(title='均價',text='{{f1_structure}}。五分鐘{{f5_structure}}。Ask。',
                                    fact_ids=['f1.trend','f5.trend'])],facts)[0]['text']
    assert '目前可賣出價 4000' in result and '目前可買進價' in result
    assert '最近20小時均價 3990' in result and '最近60小時均價 3980' in result
    assert '最近100分鐘均價 4010' in result
    assert 'Bid' not in result and 'MA20' not in result


def test_five_minute_direction_reason_is_not_relabelled_with_an_hourly_section():
    context=live.build_live_context(snapshot(),now=NOW)
    facts=live.trade_advice_facts(dict(action='WAIT',headline='等待',reason='原因',
        direction=dict(side='BUY',basis='5m',reason='五分鐘末根高於 MA20。')))+context['facts']
    text=live.render_sections([dict(title='方向',text='{{advice_direction_reason_state}}',fact_ids=['advice.direction','f1.trend'])],facts)[0]['text']
    assert '最近100分鐘均價' in text and '最近20小時' not in text


def test_fixed_average_names_do_not_allow_fabricated_market_numbers():
    facts=live.build_live_context(snapshot(),now=NOW)['facts']
    rendered=live.render_model_sections([dict(title='綜合建議',text='現價高於最近100分鐘均價。',fact_ids=['f5.trend'])],facts)
    assert rendered[0][0]['source']=='model'
    with pytest.raises(ValueError):
        live.render_sections([dict(title='盤面',text='支撐為4000。',fact_ids=['f5.levels'])],facts)


def test_plan_keeps_risk_budget_constraints_and_direction_specific_protection():
    facts=live.trade_advice_facts(dict(action='ADJUST',headline='先調整',reason_code='RISK_BUDGET',reason='超出預算',
        protection=dict(status='AVAILABLE',entry='4000',stop='4010',target='3980',stop_basis='壓力上方',target_basis='前低',reward_risk_ratio='2',conditional=True)))
    plan=next(f for f in facts if f['id']=='advice.plan')
    assert '超出使用者預算' in plan['values']['plan_constraint_state']
    assert next(f for f in facts if f['id']=='advice.protection')['values']['advice_protection_side_state']=='做空'


def test_trade_plan_writer_gets_brief_market_meaning_without_a_sample_count_veto(monkeypatch):
    context=live.build_live_context(snapshot(),now=NOW)
    context['trade_advice']=dict(action='WAIT',headline='建議先等待',reason_code='INSUFFICIENT_PAIRS',
        reason='有5組完整配對，方向建議需至少10組。',signal='跌破後收回',signal_code='RECLAIM_LOW',
        direction={'side':'BUY','reason':'五分鐘末根高於 MA20。'})
    def provider(*a,**kw):
        payload=kw['catalog'];facts={f['id']:f for f in payload['facts']}
        assert 'advice.decision' not in facts
        assert 'action' not in payload['program_trade_advice']
        assert 'f5_live_reading_state' in facts['f5.trend']['basis']
        assert 'f5_structure' not in facts['f5.trend']['text']
        assert '5組' not in str(payload) and '10組' not in str(payload)
        assert '不是進場許可' in kw['system_prompt']
        assert '歷史操作參照' in kw['system_prompt']
        return dict(status='ok',provider='claude_code',text=json.dumps({'sections':[
            dict(title='綜合建議',text='優先找回踩後做多的機會，若支撐失效就取消這個計畫。',fact_ids=['f5.levels'])]}))
    monkeypatch.setattr(live,'explain_context',provider)
    reply=live.respond_context(context,'現在該做多還是做空？',enabled=True)
    assert reply['llm_status']=='ok' and reply['trade_advice']['action']=='WAIT'
    assert any(f['id']=='advice.decision' for f in reply['evidence'])

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
    assert '開啟Groq' not in answer['message']
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
        assert '高於短線均價' in trend['basis']['f5_live_reading_state'] and 'f5_structure' in trend['tokens']
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


def test_claude_explains_protection_with_bound_values_despite_an_invalid_section(monkeypatch):
    context=live.build_live_context(snapshot(),now=NOW)
    context['trade_advice']=dict(action='WAIT',signal_code='ABOVE',reason_code='INSUFFICIENT_PAIRS',
        headline='建議先等待',reason='有 5 組完整配對。',signal='向上突破',
        protection=dict(status='AVAILABLE',conditional=True,entry='4101.23',stop='4091.23',
            target='4121.23',reward_risk_ratio='2.00',stop_basis='區間上緣下方',target_basis='區間高度延伸'))
    def provider(*args,**kwargs):
        payload=kwargs['catalog']
        assert '4091.23' not in json.dumps(payload) and '5 組完整配對' not in str(payload)
        fact=next(f for f in payload['facts'] if f['id']=='advice.protection')
        assert '區間上緣下方' in fact['basis']['advice_stop_basis_state']
        return dict(status='ok',provider='claude_code',text=json.dumps({'sections':[
            dict(title='停損依據',text='停損參考 {{advice_stop}}，若結構失效就重新評估。',fact_ids=['advice.protection']),
            dict(title='無依據',text='價格會到 9999。',fact_ids=['made.up']),
        ]}))
    monkeypatch.setattr(live,'explain_context',provider)
    answer=live.respond_context(context,'為什麼設這個停損？',enabled=True,provider='claude_code')
    assert answer['provider']=='claude_market_analysis' and answer['llm_status']=='partial_grounding'
    assert '4091.23' in answer['message'] and '9999' not in answer['message']


def test_draft_agent_gets_trader_playbook_levels_and_same_snapshot_case_evidence(monkeypatch):
    context = live.build_live_context(snapshot(), now=NOW)
    context['trade_advice'] = dict(
        action='WAIT', signal_code='RECLAIM_LOW', reason_code='INSUFFICIENT_PAIRS',
        headline='建議先等待', reason='配對不足。', signal='跌破後收回',
        simulations={'count': 3, **{side: dict(positive=2, median_pct='0.11', stress_median_pct='0.08')
                                    for side in ('BUY', 'SELL')}},
        original={'BUY': dict(count=3, median_pct='0.6712')},
    )
    context['facts'].extend([
        dict(id='history.case1', text='案例甲末段反彈。', values={}),
        dict(id='history.outcome', text='其他觀察區間。', values={}),
    ])
    context['outcome_analysis'] = {'cases': [
        {'ref': '案例甲', 'horizons': {'30': dict(status='AVAILABLE', minutes=30,
                                               change_pct='0.1234', mae_pct='0.0567')}}
    ]}

    def provider(*args, **kwargs):
        catalog = kwargs['catalog']
        facts = {fact['id']: fact for fact in catalog['facts']}
        assert 'trader_playbook' in catalog and '斜率線' in str(catalog['trader_playbook'])
        assert {'f1.trend', 'f5.trend', 'f5.levels', 'history.case1',
                'advice.case_outcome', 'advice.comparison'} <= facts.keys()
        assert 'advice_buy_positive' in facts['advice.comparison']['tokens']
        assert 'advice.original.buy' in facts
        assert all(value not in str(catalog) for value in ('0.1234', '0.0567', '0.6712'))
        return dict(status='ok', provider='claude_code', text=json.dumps({'sections': [
            dict(title='綜合建議', text='等回踩再考慮做多。案例甲途中最大逆向為{{advice_case_mae}}%。',
                 fact_ids=['f5.levels', 'advice.case_outcome']),
            dict(title='未證實', text='價格已突破斜率線。', fact_ids=['f5.levels']),
        ]}))

    monkeypatch.setattr(live, 'explain_context', provider)
    reply = live.respond_context(context, '停損停利怎麼看？', enabled=True, frozen=True, provider='claude_code')
    assert reply['provider'] == 'claude_market_analysis'
    assert '0.0567%' in reply['sections'][0]['text']
    assert '價格已突破斜率線' not in reply['message']


def test_live_quote_below_averages_is_separate_from_last_closed_bullish_structure():
    s=snapshot();s['quote'].update(bid='4000.12',ask='4000.32')
    context=live.build_live_context(s,now=NOW)
    trend=next(f for f in context['facts'] if f['id']=='f5.trend')['values']
    assert trend['f5_bias']=='短線偏多'
    assert '低於 MA20' in trend['f5_live_structure'] and '低於 MA60' in trend['f5_live_structure']
    assert '高於 MA20' in trend['f5_structure']
    narrative=live.writer_facts([next(f for f in context['facts'] if f['id']=='f5.trend')])[0]
    assert '低於短線均價' in narrative['basis']['f5_live_reading_state'] and '4000.12' not in str(narrative)
    assert 'f5_live_structure' not in narrative['basis']


@pytest.mark.parametrize('action,reason,side,expected', [
    ('BUY', 'CONFIRMED', 'BUY', '建議做多'),
    ('SELL', 'CONFIRMED', 'SELL', '建議做空'),
    ('WAIT', 'INSUFFICIENT_PAIRS', 'BUY', '偏多，優先找做多機會'),
    ('WAIT', 'COST_UNAVAILABLE', 'SELL', '偏空，優先找做空機會'),
    ('WAIT', 'STRESS_COST', 'BUY', None),
    ('ADJUST', 'RISK_BUDGET', 'BUY', None),
])
def test_trade_summary_has_a_direct_opening_without_overriding_entry_checks(action, reason, side, expected):
    facts = live.trade_advice_facts(dict(
        action=action, reason_code=reason, headline='原判斷', reason='原原因',
        direction=dict(side=side, reason='已收棒訊號'),
    ))
    opening = next((f['values']['advice_opening_state'] for f in facts if f['id']=='advice.opening'), None)
    assert opening == expected


def test_followup_inherits_recent_explicit_period_and_general_analysis_can_reset_it(monkeypatch):
    def provider(*a,**k):
        ids={f['id'] for f in k['catalog']['facts']}
        assert 'f15.levels' in ids and not any(i.startswith('f5.') or i.startswith('f1.') for i in ids)
        return dict(status='ok',model='test',text=json.dumps({'sections':[dict(title='轉折參考',text='下方{{f15_support}}，上方{{f15_resistance}}。',fact_ids=['f15.levels'])]}))
    monkeypatch.setattr(live,'explain_context',provider)
    assert live.respond_live(snapshot(),'那支撐壓力呢？',enabled=True,now=NOW,previous_questions=['十五分鐘RSI如何'])['llm_status']=='ok'
    assert live.selection_question('分析目前黃金盤面',['十五分鐘RSI如何'])=='分析目前黃金盤面'
