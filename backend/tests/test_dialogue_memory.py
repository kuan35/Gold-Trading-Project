from backend.dialogue_memory import dialogue_history,mask_context_text


def test_memory_is_bounded_same_thread_and_masks_old_financial_numbers():
    rows=[dict(thread_id='one',question='5分鐘做多，4050進場0.1手',answer='MA20上方，當時價格4061.5，報酬2.3%。') for _ in range(8)]
    result=dialogue_history(rows,'one')
    assert len(result)==6
    assert '4050' not in str(result) and '4061.5' not in str(result) and '2.3' not in str(result)
    assert '5分鐘' in result[0]['user'] and 'MA20' in result[0]['assistant']
    assert '當時數值' in str(result) and '非當前行情' in result[0]['basis']
    assert dialogue_history(rows,'another')==[] and dialogue_history(rows,None)==[]


def test_credentials_and_untrusted_extra_fields_are_not_part_of_memory():
    value=dialogue_history([dict(thread_id='one',question='gsk_abcdefghijklmnopqrstuvwxyz',answer='討論停損',confirm=True,api_key='SECRET')],'one')
    assert 'gsk_' not in str(value) and 'SECRET' not in str(value) and 'confirm' not in str(value)
    assert mask_context_text('RSI14與1小時，價位4500')=='RSI14與1小時，價位[當時數值]'


def test_memory_also_scrubs_email_and_named_credentials_for_both_roles():
    rows=[dict(thread_id='one',question='email alice@example.com token: abcdefghijklmnop',answer='account: private-account')]
    value=str(dialogue_history(rows,'one'))
    assert 'alice@example.com' not in value and 'abcdefghijklmnop' not in value and 'private-account' not in value


def test_current_facts_and_quoted_discussion_are_separate_in_mock_provider(monkeypatch):
    from backend import live_assistant as live
    from backend.tests.test_live_assistant import snapshot,NOW
    captured=[]
    def provider(*args,**kwargs):
        captured.append(kwargs);return dict(status='unavailable',model=None)
    monkeypatch.setattr(live,'explain_context',provider)
    context=live.build_live_context(snapshot(),now=NOW)
    rows=[dict(thread_id='one',question='做多4500，停損4490',answer='當時價格4502，討論風險')]
    live.respond_context(context,'剛剛的想法有什麼相反訊號？',enabled=True,conversation=rows,conversation_id='one')
    assert len(captured)==1
    payload=captured[0]['catalog']
    assert '4500' not in str(payload['previous_dialogue']) and '4490' not in str(payload['previous_dialogue'])
    assert payload['facts'] and '不是此次facts' in captured[0]['system_prompt']
    live.respond_context(context,'延續討論',enabled=True,conversation=rows,conversation_id='two')
    assert 'previous_dialogue' not in captured[-1]['catalog']
