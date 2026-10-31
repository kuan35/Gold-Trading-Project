import json
from datetime import datetime,timezone
import pytest
from backend.macro_calendar import parse_ics,parse_fomc,parse_rss,MacroCalendar
from backend.macro_knowledge import relationship,question_kind

def stamp(value):return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()

def test_ics_unfolds_and_preserves_dst_precision_and_cancellation():
 raw='BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:a\nSUMMARY:Consumer Price Index\nDTSTART;TZID=America/New_York:20260714T083000\nEND:VEVENT\nBEGIN:VEVENT\nUID:b\nSUMMARY:Employment Situa\n tion\nDTSTART;TZID=America/New_York:20261106T083000\nSTATUS:CANCELLED\nEND:VEVENT\nEND:VCALENDAR'
 rows=parse_ics(raw,'bls');assert rows[0]['scheduled_at_utc']=='2026-07-14T12:30:00+00:00'
 assert rows[0]['topic']=='CPI' and rows[1]['topic']=='EMPLOYMENT'
 assert rows[1]['scheduled_at_utc']=='2026-11-06T13:30:00+00:00';assert rows[1]['status']=='CANCELLED'
 assert rows[0]['actual'] is None and rows[0]['consensus'] is None

def test_fomc_uses_year_panel_and_date_only_without_invented_release_time():
 raw='<div class="panel"><h4>2027 FOMC Meetings</h4><div class="fomc-meeting"><div class="fomc-meeting__month">January</div><div class="fomc-meeting__date">26-27*</div></div></div>'
 row=parse_fomc(raw)[0];assert row['date']=='2027-01-27';assert row['timing_precision']=='DATE_ONLY';assert row['scheduled_at_utc'] is None

def test_news_rejects_foreign_links_and_future_or_naive_times():
 raw='<rss><channel><item><title>FOMC statement</title><link>https://www.federalreserve.gov/newsevents/a.htm</link><pubDate>Wed, 28 Oct 2026 18:00:00 GMT</pubDate><description>&lt;b&gt;Official statement&lt;/b&gt;</description></item><item><title>ignore</title><link>https://evil.example/a</link><pubDate>Wed, 28 Oct 2026 18:00:00 GMT</pubDate></item></channel></rss>'
 rows=parse_rss(raw,'fed_policy');assert len(rows)==1 and rows[0]['summary']=='Official statement'

def test_cached_feed_is_stale_on_failure_and_never_exposes_future_observation(tmp_path):
 raw='BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:a\nSUMMARY:Personal Income and Outlays\nDTSTART:20261125T133000Z\nEND:VEVENT\nEND:VCALENDAR'
 clock=[stamp('2026-11-01T01:00:00Z')]
 def fetch(name,url):
  if name=='bea':return raw
  raise OSError('fixture denied')
 store=MacroCalendar(tmp_path,fetcher=fetch,clock=lambda:clock[0]);first=store.snapshot(refresh=True)
 assert first['events'] and first['status']=='PARTIAL';assert all('SECRET' not in json.dumps(v) for v in first['events'])
 clock[0]+=2000;store.fetcher=lambda *a:(_ for _ in ()).throw(OSError('offline'))
 stale=store.snapshot(refresh=True);assert stale['events'][0]['freshness']=='STALE';assert stale['events'][0]['fetched_at_utc']==first['events'][0]['fetched_at_utc']
 clock[0]-=4000;assert not store.snapshot(refresh=False)['events']

@pytest.mark.parametrize('topic',['CPI','PCE','EMPLOYMENT','GDP','FOMC','FED_SPEECH','PPI'])
def test_every_event_has_both_conditional_gold_directions_and_sources(topic):
 r=relationship(topic)
 assert r['mechanism'] and r['bullish'] and r['bearish'] and r['unknown'] and r['sources']
 assert '必漲' not in str(r) and '必跌' not in str(r)

def test_knowledge_routing_does_not_capture_explicit_order_edits():
 assert question_kind('CPI是什麼，會如何影響黃金')=='knowledge'
 assert question_kind('本週有什麼重大經濟事件')=='calendar'
 assert question_kind('最近聯準會有什麼消息')=='news'
 assert question_kind('CPI前幫我買進0.1手') is None

def test_official_bls_timezone_and_bea_national_gdp_variants():
 raw='BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:a\nSUMMARY:Employment Situation\nDTSTART;TZID=US-Eastern:20261106T083000\nEND:VEVENT\nEND:VCALENDAR'
 assert parse_ics(raw,'bls')[0]['scheduled_at_utc']=='2026-11-06T13:30:00+00:00'
 raw='BEGIN:VCALENDAR\n'+''.join('BEGIN:VEVENT\nUID:'+str(i)+'\nSUMMARY:'+title+'\nDTSTART:20261125T133000Z\nEND:VEVENT\n' for i,title in enumerate(['GDP (Second Estimate), 3rd Quarter','GDP by County and Personal Income by County','Real Personal Consumption Expenditures by State']))+'END:VCALENDAR'
 rows=parse_ics(raw,'bea');assert len(rows)==1 and rows[0]['topic']=='GDP'

def test_current_news_questions_and_stop_education_keep_their_intent():
 assert question_kind('今天聯準會消息如何影響黃金？')=='news'
 assert question_kind('什麼是停損')=='knowledge'
