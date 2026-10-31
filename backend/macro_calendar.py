"""Fixed-source, bounded public calendars and official announcements. No forecasts."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from pathlib import Path
from threading import RLock
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
import calendar,json,re,time,math,xml.etree.ElementTree as ET
import httpx
from bs4 import BeautifulSoup
from .macro_knowledge import detect_topic,relationship

SOURCES={
 'bls':('https://www.bls.gov/schedule/news_release/bls.ics','ics'),
 'bea':('https://www.bea.gov/news/schedule/ics/online-calendar-subscription.ics','ics'),
 'fed':('https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm','fomc'),
 'fed_policy':('https://www.federalreserve.gov/feeds/press_monetary.xml','rss'),
 'fed_speech':('https://www.federalreserve.gov/feeds/speeches.xml','rss'),
}
UTC=timezone.utc;TTL=900;MAX_BYTES=2_000_000
def iso(stamp):return datetime.fromtimestamp(stamp,UTC).isoformat()
def clean(text):return re.sub(r'\s+',' ',BeautifulSoup(str(text),'html.parser').get_text(' ',strip=True)).strip()[:900]
def allowed_url(url,host):
 try:p=urlsplit(url);return p.scheme=='https' and p.hostname==host and not p.username and not p.password and p.port in (None,443)
 except ValueError:return False

def event(source,ident,title,when,day,precision):
 topic=detect_topic(title)
 return dict(id=source+'-'+sha256(ident.encode()).hexdigest()[:20],title=clean(title),topic=topic,source=source,source_url=SOURCES[source][0],
  scheduled_at_utc=when,date=day,timing_precision=precision,source_timezone='America/New_York',status='SCHEDULED',actual=None,consensus=None,previous=None,
  result_status='NOT_FETCHED',gold_relation=relationship(topic))

def parse_ics(raw,source):
 # splitlines handles the BEA feed's CRCRLF, then unfold RFC5545 continuations.
 lines=[]
 for line in raw.splitlines():
  if not line:continue
  if line.startswith((' ','\t')) and lines:lines[-1]+=line[1:]
  else:lines.append(line)
 rows=[];fields=None
 for line in lines:
  if line=='BEGIN:VEVENT':fields={};continue
  if line=='END:VEVENT':
   try:
    title=fields['SUMMARY'][1].replace('\\,',',').replace('\\n',' ').replace('\\;', ';')
    pattern=r'^(?:Personal Income and Outlays|Gross Domestic Product|GDP\s*\()' if source=='bea' else r'Consumer Price|Employment Situation|Producer Price|Job Openings'
    if not re.search(pattern,title,re.I):fields=None;continue
    key,value=fields['DTSTART'];naive=datetime.strptime(value[:8],'%Y%m%d')
    if len(value)==8:when=None;precision='DATE_ONLY'
    else:
     tzmatch=re.search(r'TZID=([^;:]+)',key)
     tzname=tzmatch[1] if tzmatch else 'America/New_York'
     if tzname=='US-Eastern':tzname='America/New_York'
     tz=UTC if value.endswith('Z') else ZoneInfo(tzname)
     dt=datetime.strptime(value.rstrip('Z'),'%Y%m%dT%H%M%S').replace(tzinfo=tz)
     when=dt.astimezone(UTC).isoformat();precision='EXACT'
    row=event(source,fields.get('UID',('',title+value))[1],title,when,naive.date().isoformat(),precision)
    row['status']='CANCELLED' if fields.get('STATUS',('',''))[1]=='CANCELLED' else 'SCHEDULED';row['version']=fields.get('SEQUENCE',('','0'))[1][:30]
    rows.append(row)
   except (KeyError,TypeError,ValueError,IndexError):pass
   fields=None;continue
  if fields is not None and ':' in line:
   key,value=line.split(':',1);fields[key.split(';')[0]]=(key,value)
 return rows

def parse_fomc(raw):
 soup=BeautifulSoup(raw,'html.parser');rows=[]
 for meeting in soup.select('.fomc-meeting'):
  heading=meeting.find_previous(re.compile('^h[234]$'))
  year=re.search(r'\b(20\d{2})\b',heading.get_text() if heading else '')
  month=meeting.select_one('.fomc-meeting__month');date=meeting.select_one('.fomc-meeting__date')
  if not year or not month or not date:continue
  try:
   month_text=month.get_text(' ',strip=True).split('/')[-1].strip();month_num=list(calendar.month_name).index(month_text)
   day=int(re.findall(r'\d+',date.get_text())[-1]);stamp=datetime(int(year[1]),month_num,day)
   rows.append(event('fed',stamp.date().isoformat(),'FOMC會議（末日）',None,stamp.date().isoformat(),'DATE_ONLY'))
  except (ValueError,IndexError):continue
 return rows

def parse_rss(raw,source):
 root=ET.fromstring(raw);rows=[]
 for item in root.findall('./channel/item')[:50]:
  url=(item.findtext('link') or '').strip()
  if not allowed_url(url,'www.federalreserve.gov'):continue
  try:
   stamp=parsedate_to_datetime(item.findtext('pubDate') or '')
   if stamp.tzinfo is None:continue
   rows.append(dict(id=sha256(url.encode()).hexdigest()[:20],title=clean(item.findtext('title') or ''),summary=clean(item.findtext('description') or ''),source=source,source_url=url,published_at_utc=stamp.astimezone(UTC).isoformat(),gold_relation=relationship('FED_SPEECH' if source=='fed_speech' else 'FOMC')))
  except (ValueError,TypeError,OverflowError):continue
 return rows

def fetch_public(name,url):
 if name not in SOURCES or url!=SOURCES[name][0]:raise ValueError('source not allowed')
 with httpx.Client(timeout=httpx.Timeout(6,connect=3),follow_redirects=False,headers={'User-Agent':'GoldDesk/1.0 official-calendar-reader'}) as client:
  with client.stream('GET',url) as response:
   response.raise_for_status();data=bytearray()
   for chunk in response.iter_bytes():
    data.extend(chunk)
    if len(data)>MAX_BYTES:raise ValueError('source too large')
   return data.decode('utf-8-sig')

class MacroCalendar:
 def __init__(self,root,*,fetcher=fetch_public,clock=time.time):
  self.root=Path(root);self.path=self.root/'macro-calendar.json';self.fetcher=fetcher;self.clock=clock;self.lock=RLock();self.cache={};self.attempted=0
  try:
   value=json.loads(self.path.read_text(encoding='utf8'))
   if isinstance(value,dict):self.cache={k:v for k,v in value.items() if k in SOURCES and isinstance(v,dict) and isinstance(v.get('raw'),str) and len(v['raw'])<=MAX_BYTES and type(v.get('fetched')) in (int,float) and math.isfinite(v['fetched'])}
  except (OSError,ValueError):pass

 def snapshot(self,*,refresh=False,days=60):
  with self.lock:
   now=self.clock();errors={}
   due=[k for k in SOURCES if k not in self.cache or now-self.cache[k]['fetched']>=TTL]
   if refresh and due and (not self.attempted or now-self.attempted>=60):
    self.attempted=now
    def load(key):
     try:return key,self.fetcher(key,SOURCES[key][0]),None
     except Exception as e:return key,None,'HTTP_'+str(e.response.status_code) if isinstance(e,httpx.HTTPStatusError) else 'SOURCE_UNAVAILABLE'
    with ThreadPoolExecutor(max_workers=5) as executor:
     for key,raw,error in executor.map(load,due):
      if error:errors[key]=error
      else:self.cache[key]=dict(raw=raw,fetched=self.clock())
    try:
     self.root.mkdir(parents=True,exist_ok=True);temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(self.cache),encoding='utf8');temp.replace(self.path)
    except OSError:pass
   now=self.clock();events=[];news=[];sources=[]
   for key,(url,kind) in SOURCES.items():
    value=self.cache.get(key);status='UNAVAILABLE';fetched=None
    if value and value['fetched']<=now:
     fetched=value['fetched'];status='CURRENT' if now-fetched<TTL and key not in errors else 'STALE'
     try:
      rows=parse_ics(value['raw'],key) if kind=='ics' else parse_fomc(value['raw']) if kind=='fomc' else parse_rss(value['raw'],key)
      if not rows:status='INVALID'
      for row in rows:
       row.update(fetched_at_utc=iso(fetched),freshness=status)
       if kind=='rss':
        stamp=datetime.fromisoformat(row['published_at_utc']).timestamp()
        if now-14*86400<=stamp<=now:news.append(row)
       else:
        stamp=datetime.fromisoformat(row['scheduled_at_utc']).timestamp() if row['scheduled_at_utc'] else None
        date=datetime.fromisoformat(row['date']).date();today=datetime.fromtimestamp(now,ZoneInfo('America/New_York')).date()
        if (stamp is not None and now-7*86400<=stamp<=now+days*86400) or (stamp is None and today-timedelta(days=7)<=date<=today+timedelta(days=days)):
         if row['status']!='CANCELLED':row['status']='SCHEDULED' if (stamp>now if stamp else date>=today) else 'TIME_PASSED_RESULT_UNKNOWN'
         events.append(row)
     except (ValueError,TypeError,ET.ParseError):status='INVALID'
    sources.append(dict(id=key,url=url,status=status,fetched_at_utc=iso(fetched) if fetched is not None else None,reason=errors.get(key)))
   unique={e['id']:e for e in events};events=sorted(unique.values(),key=lambda e:(e['date'],e['scheduled_at_utc'] or '99',e['id']))[:120]
   news=sorted({n['id']:n for n in news}.values(),key=lambda n:n['published_at_utc'],reverse=True)[:6]
   current=sum(s['status']=='CURRENT' for s in sources);available=bool(events or news)
   status='AVAILABLE' if current==len(SOURCES) else 'PARTIAL' if available and current else 'STALE' if available else 'UNAVAILABLE'
   payload=dict(status=status,as_of_utc=iso(now),horizon_days=days,coverage='Fed官方公告與Fed/BLS/BEA發布排程；未涵蓋全部地緣或市場新聞',sources=sources,events=events,news=news,consensus_status='NOT_PROVIDED',actual_values_status='NOT_FETCHED')
   payload['snapshot_id']=sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest();return deepcopy(payload)
