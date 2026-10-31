"""Offline clock calibration and private, non-production UTC candidate sidecars.

HistData fixed EST is UTC-5 year round (official FAQ). Its M1 bars are BID;
volume is unavailable, not zero activity. Never mutate statement timestamps.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

UTC=timezone.utc
D=Decimal
audit_path=Path(__file__).with_name('audit_market_time_alignment.py')
if not audit_path.exists():
    audit_path=Path(__file__).parents[1]/'time_alignment_20261012/audit_market_time_alignment.py'
spec=importlib.util.spec_from_file_location('expanded_clock_base',audit_path)
base=importlib.util.module_from_spec(spec);sys.modules[spec.name]=base
spec.loader.exec_module(base)


def parse_histdata_line(line: str) -> tuple[datetime, dict[str, Decimal | None]]:
    cells=line.strip().split(';')
    if len(cells)!=6:raise ValueError('Invalid HistData row')
    text=cells[0]
    local=datetime.fromisoformat(f'{text[:4]}-{text[4:6]}-{text[6:8]}T{text[9:11]}:{text[11:13]}:{text[13:15]}')
    stamp=(local+timedelta(hours=5)).replace(tzinfo=UTC)
    values={k:D(v) for k,v in zip(('open','high','low','close'),cells[1:5])}
    if not all(v.is_finite() and v>0 for v in values.values()):raise ValueError('Invalid price')
    if not (values['low']<=min(values['open'],values['close'])<=max(values['open'],values['close'])<=values['high']):
        raise ValueError('Invalid OHLC bounds')
    if stamp.second:raise ValueError('Not minute-aligned')
    return stamp,dict(**values,volume=None)


class DownloadForm(HTMLParser):
    def __init__(self) -> None:
        super().__init__();self.active=False;self.fields:dict[str,str]={}

    def handle_starttag(self, tag: str, attrs: list[tuple[str,str | None]]) -> None:
        a=dict(attrs)
        if tag=='form':self.active=a.get('id')=='file_down'
        if tag=='input' and self.active and a.get('name') and a.get('value'):
            self.fields[a['name']]=a['value']

    def handle_endtag(self, tag: str) -> None:
        if tag=='form':self.active=False


def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def snapshot(root: Path) -> dict[str,str]:
    files=[p for p in (root/'交易員資料').rglob('*') if p.is_file()]
    files += [p for p in root.iterdir() if p.suffix.lower() in ('.pdf','.png','.docx','.m4a')]
    files += [root/'artifacts/behavior_audit_20261001_final/all_records.csv',
              root/'artifacts/behavior_audit_20261001_final/gold_behavior_records.csv',
              root/'artifacts/market_data/xauusd_5m_bars.csv',root/'product/private/cases.json']
    return {str(p.relative_to(root)):sha(p) for p in sorted(set(files))}


def download(root: Path, output: Path) -> None:
    output.mkdir(parents=True,exist_ok=True)
    integrity=output/'integrity_before_PRIVATE.json'
    if not integrity.exists():integrity.write_text(json.dumps(snapshot(root),ensure_ascii=False,indent=2),encoding='utf-8')
    cache=output/'histdata_archives';cache.mkdir(exist_ok=True)
    # All observed years; yearly files reduce requests, current year is monthly.
    periods=[(year,None) for year in range(2018,2026)]+[(2026,m) for m in (1,2,3)]
    manifest=[]
    for year,month in periods:
        label=str(year)+(f'{month:02d}' if month else '')
        path=cache/f'XAUUSD_M1_{label}.zip'
        page=f'https://www.histdata.com/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/xauusd/{year}'+(f'/{month}' if month else '')
        error=None
        if not path.exists():
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(page,timeout=30) as response:html=response.read().decode('utf-8')
                    form=DownloadForm();form.feed(html)
                    if form.fields.get('fxpair')!='XAUUSD' or form.fields.get('timeframe')!='M1':
                        raise ValueError('Expected free XAUUSD M1 download form missing')
                    request=urllib.request.Request('https://www.histdata.com/get.php',
                        data=urllib.parse.urlencode(form.fields).encode(),headers={'Referer':page})
                    with urllib.request.urlopen(request,timeout=90) as response:body=response.read()
                    with zipfile.ZipFile(io.BytesIO(body)) as archive:
                        if archive.testzip() is not None:raise ValueError('Corrupt ZIP')
                        if not any(n.lower().endswith('.csv') for n in archive.namelist()):raise ValueError('No CSV')
                    with path.open('xb') as stream:stream.write(body)
                    error=None;break
                except Exception as exc:
                    error=f'{type(exc).__name__}: {str(exc)[:180]}'
                    if isinstance(exc,urllib.error.HTTPError) and exc.code in (401,403,429):break
                    time.sleep(2*(attempt+1))
        row=dict(period=label,page=page,status='DOWNLOADED' if path.exists() else 'FAILED',
                 bytes=path.stat().st_size if path.exists() else 0,sha256=sha(path) if path.exists() else None,error=error)
        manifest.append(row)
        (output/'download_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        print(json.dumps({k:row[k] for k in ('period','status','bytes','error')}),flush=True)
        if row['status']=='FAILED' and error and ('429' in error or '403' in error):break
        time.sleep(.5)


def calibration_events(rows: list[dict]) -> dict[str,list]:
    sources:dict[str,dict[datetime,Any]]=defaultdict(dict)
    # A repeated export is still evaluated locally, but is NEVER an independent account.
    # Within each source all same-five-minute batches have one vote, including copies.
    for row in sorted(rows,key=lambda r:(r.get('open_time',''),r.get('open_price',''),r.get('record_id',''))):
        if row.get('record_type')!='TRADE' or row.get('gold','').lower() not in ('true','1'):
            continue
        try:
            dt=datetime.fromisoformat(row['open_time']);price=D(row['open_price'])
            if dt.tzinfo is not None or base.boundary_day(dt) or not price.is_finite() or price<=0:continue
            bucket=dt.replace(minute=dt.minute//5*5,second=0,microsecond=0)
            sources[row['source']].setdefault(bucket,base.Event(dt,price))
        except (ValueError,KeyError,ArithmeticError):continue
    return {s:list(v.values()) for s,v in sources.items()}


def timestamp_options(local: str, models: list[str]) -> list[int]:
    if not local:return []
    try:dt=datetime.fromisoformat(local)
    except ValueError:return []
    if dt.tzinfo is not None:return [int(dt.timestamp())]
    if base.boundary_day(dt) and any(m in ('US_2_3','EU_2_3') for m in models):return []
    return sorted({base.utc_stamp(base.Event(dt,D(1)),m) for m in models})


def iso(stamp: int) -> str:
    return datetime.fromtimestamp(stamp,UTC).isoformat()


def price_gap(price: str, stamp: int, bars: dict, interval: int) -> str:
    bar=bars.get(stamp//interval*interval)
    if not bar:return ''
    try:p=D(price)
    except ArithmeticError:return ''
    return str(max(bar[0]-p,p-bar[1],D(0)))


def align_row(row: dict, source: dict, bars5: dict, bars1: dict) -> dict:
    strong=source.get('status')=='STRONG_PRICE_CANDIDATE'
    limited=source.get('status')=='LIMITED_PRICE_CANDIDATE'
    models=source.get('models',[]) if strong or limited else []
    opens=timestamp_options(row.get('open_time',''),models) if models else []
    closes=timestamp_options(row.get('close_time',''),models) if models else []
    issues=[]
    for value in (row.get('open_time',''),row.get('close_time','')):
        if value and models:
            try:
                dt=datetime.fromisoformat(value)
                if base.boundary_day(dt) and any(m in ('US_2_3','EU_2_3') for m in models):
                    issues.append('DST_BOUNDARY_REQUIRES_EXACT_RULE')
            except ValueError:issues.append('INVALID_TIME')
    if row.get('open_time') and row.get('close_time'):
        try:
            if datetime.fromisoformat(row['close_time'])<datetime.fromisoformat(row['open_time']):
                issues.append('INVALID_LOCAL_CHRONOLOGY')
        except ValueError:issues.append('INVALID_TIME')
    gold=row.get('gold','').lower() in ('true','1')
    if not gold:issues.append('SYMBOL_NOT_PRICE_CHECKED')
    if not strong:issues.append(source.get('status','NO_GOLD_CALIBRATION'))
    if len(opens)>1 or len(closes)>1:issues.append('EQUIVALENT_MODELS_DISAGREE_AT_THIS_TIMESTAMP')
    opening=opens[0] if len(opens)==1 else None
    closing=closes[0] if len(closes)==1 else None
    gap5=price_gap(row.get('open_price',''),opening,bars5,300) if gold and opening is not None else ''
    gap1=price_gap(row.get('open_price',''),opening,bars1,60) if gold and opening is not None else ''
    exitgap1=price_gap(row.get('close_price',''),closing,bars1,60) if gold and closing is not None and row.get('close_price') else ''
    if gold and opening is not None and not gap5:issues.append('NO_ENTRY_5M_QUOTE')
    if gold and opening is not None and gap1 and D(gap1)>D('.5'):issues.append('ENTRY_1M_PRICE_MISMATCH')
    if gold and closing is not None and exitgap1 and D(exitgap1)>D('.5'):issues.append('EXIT_1M_PRICE_MISMATCH')
    return dict(record_id=row.get('record_id',''),source_key='S-'+hashlib.sha256(row.get('source','').encode()).hexdigest()[:12],
        record_type=row.get('record_type',''),symbol=row.get('symbol',''),
        open_time_original=row.get('open_time',''),close_time_original=row.get('close_time',''),
        open_time_raw=row.get('open_time_raw',''),close_time_raw=row.get('close_time_raw',''),
        timestamp_precision=row.get('timestamp_precision','UNKNOWN'),
        timezone_status='UNKNOWN',evidence_status=source.get('status','NO_GOLD_CALIBRATION'),
        candidate_models=models,open_utc_candidate=iso(opening) if strong and opening is not None else '',
        close_utc_candidate=iso(closing) if strong and closing is not None else '',
        open_utc_review_candidate=iso(opening) if limited and opening is not None else '',
        close_utc_review_candidate=iso(closing) if limited and closing is not None else '',
        open_utc_options_count=len(opens),close_utc_options_count=len(closes),
        last_closed_5m_candidate=iso(opening//300*300-300) if strong and opening is not None else '',
        entry_gap_5m_usd=gap5,entry_gap_1m_usd=gap1,exit_gap_1m_usd=exitgap1,
        production_enabled=False,issues=sorted(set(issues)))


@lru_cache(maxsize=4096)
def empirical_market_daily_shift(year: int, month: int, day: int) -> int:
    return base.offset_minutes('EU_2_3',datetime(year,month,day))-120


def correct_histdata_timestamp(dt: datetime, model: str) -> datetime:
    """An explicit empirical correction, NOT a change to the provider's claim.

    Raw archive clock disagrees with fixed-EST FAQ during EU summer time.
    Existing independent UTC quotes and dated BLS release anchors support -1h.
    DST transition buffers remain unsuitable for production clock inference.
    """
    if model=='EST_CLAIM_ONLY':return dt
    if model!='EMPIRICAL_EU_SHIFT':raise ValueError('Unknown market clock model')
    minutes=empirical_market_daily_shift(dt.year,dt.month,dt.day)
    return dt-timedelta(minutes=minutes)


def histdata_rows(cache: Path, market_clock: str='EST_CLAIM_ONLY'):
    for path in sorted(cache.glob('*.zip')):
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                if name.lower().endswith('.csv'):
                    with archive.open(name) as binary:
                        for line in io.TextIOWrapper(binary,encoding='utf-8-sig'):
                            dt,bar=parse_histdata_line(line)
                            yield correct_histdata_timestamp(dt,market_clock),bar


def build_5m(cache: Path, output: Path, market_clock: str='EST_CLAIM_ONLY') -> tuple[dict,dict]:
    aggregates={};minutes=0;duplicate_minutes=0;seen=set()
    for dt,bar in histdata_rows(cache,market_clock):
        stamp=int(dt.timestamp());minutes+=1
        if stamp in seen:duplicate_minutes+=1;continue
        seen.add(stamp);bucket=stamp//300*300
        if bucket not in aggregates:
            aggregates[bucket]=[bar['open'],bar['high'],bar['low'],bar['close'],stamp,stamp,1]
        else:
            a=aggregates[bucket];a[1]=max(a[1],bar['high']);a[2]=min(a[2],bar['low']);a[6]+=1
            if stamp<a[4]:a[0]=bar['open'];a[4]=stamp
            if stamp>a[5]:a[3]=bar['close'];a[5]=stamp
    target=output/'histdata_xauusd_5m_UTC.csv'
    rows=[dict(timestamp=iso(t),open=str(a[0]),high=str(a[1]),low=str(a[2]),close=str(a[3]),
               observed_minutes=a[6],volume='',source='HistData',quote_side='BID',volume_status='UNAVAILABLE')
          for t,a in sorted(aggregates.items())]
    base.write_csv(target,rows)
    return {t:(a[2],a[1]) for t,a in aggregates.items()},dict(
        minute_rows=minutes,unique_minutes=len(seen),duplicate_minutes=duplicate_minutes,
        bars_5m=len(aggregates),partial_5m_bars=sum(a[6]<5 for a in aggregates.values()),
        start=iso(min(aggregates)),end=iso(max(aggregates)),quote_side='BID',
        upstream_timezone_claim='EST_FIXED_UTC_MINUS_5',market_clock_model=market_clock,
        market_clock_status='INFERRED_FROM_OVERLAP_AND_EVENT_ANCHORS' if market_clock!='EST_CLAIM_ONLY' else 'PROVIDER_CLAIM_UNVERIFIED',
        volume_status='UNAVAILABLE')


def read_selected_minutes(cache: Path, wanted: set[int],market_clock: str='EST_CLAIM_ONLY') -> dict:
    result={}
    for dt,bar in histdata_rows(cache,market_clock):
        stamp=int(dt.timestamp())
        if stamp in wanted:result[stamp]=(bar['low'],bar['high'])
    return result


def quarter(local: datetime) -> str:
    return f'{local.year}-Q{(local.month-1)//3+1}'


def limited_candidate(summary: dict) -> bool:
    # Descriptive review hints only. This never relaxes the strong/production gate.
    return (summary['status']=='INSUFFICIENT_COMPARABLE_EVENTS' and
            summary['train_events']>=5 and summary['validation_events']>=3 and
            summary['train_days']>=2 and summary['validation_days']>=2 and
            summary['train_hit_rate']>=.8 and summary['validation_hit_rate']>=.8 and
            summary['train_margin']>=.10 and summary['validation_margin']>=.10)


def run(root: Path, output: Path, result: Path,market_clock: str='EST_CLAIM_ONLY',calibration_interval: int=300) -> dict:
    if result.exists():raise FileExistsError('Choose a new result directory')
    expected=json.loads((output/'integrity_before_PRIVATE.json').read_text(encoding='utf-8'))
    if any(sha(root/p)!=h for p,h in expected.items()):raise RuntimeError('Original inputs changed')
    result.mkdir(parents=True)
    records=root/'artifacts/behavior_audit_20261001_final/all_records.csv'
    with records.open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
    bars,market_info=build_5m(output/'histdata_archives',result,market_clock)
    dukas,_=base.read_bars(root/'artifacts/market_data/xauusd_5m_bars.csv')
    common=sorted(set(bars)&set(dukas))
    gaps=[max(bars[t][0]-dukas[t][1],dukas[t][0]-bars[t][1],D(0)) for t in common]
    market_info['dukascopy_overlap']=dict(bars=len(common),range_overlap_rate=sum(x==0 for x in gaps)/len(gaps) if gaps else None,
         median_disjoint_gap=str(base.median(gaps)) if gaps else None,
         gap_le_05_rate=sum(x<=D('.5') for x in gaps)/len(gaps) if gaps else None)
    print(json.dumps(dict(stage='market_loaded',market=market_info)),flush=True)
    events=calibration_events(rows)
    minute_precached=None
    if calibration_interval==60:
        wanted_all=set()
        for row in rows:
            if row.get('gold','').lower() not in ('true','1'):continue
            for field in ('open_time','close_time'):
                if not row.get(field):continue
                try:event=base.Event(datetime.fromisoformat(row[field]),D(1))
                except ValueError:continue
                for model in base.models():wanted_all.add(base.utc_stamp(event,model)//60*60)
        print(json.dumps(dict(stage='minute_index',requested_minutes=len(wanted_all))),flush=True)
        minute_precached=read_selected_minutes(output/'histdata_archives',wanted_all,market_clock)
    calibration_bars=minute_precached if minute_precached is not None else bars
    profiles={};registries=[];month_rows=[];hypotheses=[];segmented={}
    source_info={r['source']:r for r in rows}
    for i,(source,entries) in enumerate(sorted(events.items())):
        key='S-'+hashlib.sha256(source.encode()).hexdigest()[:12]
        summary,scores,months=base.evaluate(entries,calibration_bars,calibration_interval)
        if limited_candidate(summary):summary['status']='LIMITED_PRICE_CANDIDATE'
        profiles[source]=dict(status=summary['status'],models=summary['equivalent_models'],**{'summary':summary})
        registries.append(dict(source_key=key,source_private=source,scope='WHOLE_SOURCE',format=source_info[source]['source_format'],**summary))
        month_rows.extend(dict(source_key=key,**m) for m in months)
        hypotheses.extend(dict(source_key=key,scope='WHOLE_SOURCE',**s) for s in scores)
        # Fixed calendar quarters, only for sources whose full period fails strict screening.
        # No arbitrary cut points optimized against price; all segment tests stay candidates.
        groups=defaultdict(list)
        for event in entries:groups[quarter(event.local)].append(event)
        if summary['status']!='STRONG_PRICE_CANDIDATE' and len(groups)>1:
            for period,group in sorted(groups.items()):
                sub,ss,_=base.evaluate(group,calibration_bars,calibration_interval)
                registries.append(dict(source_key=key,source_private=source,scope=period,format=source_info[source]['source_format'],**sub))
                hypotheses.extend(dict(source_key=key,scope=period,**s) for s in ss)
                if sub['status']=='STRONG_PRICE_CANDIDATE':
                    segmented[(source,period)]=dict(status=sub['status'],models=sub['equivalent_models'],summary=sub)
        if i%20==0:print(json.dumps(dict(stage='sources',completed=i+1,total=len(events))),flush=True)
    wanted=set()
    for row in rows:
        profile=profiles.get(row['source'],{})
        if row.get('open_time') and profile.get('status')!='STRONG_PRICE_CANDIDATE':
            profile=segmented.get((row['source'],quarter(datetime.fromisoformat(row['open_time']))),profile)
        if profile.get('status') in ('STRONG_PRICE_CANDIDATE','LIMITED_PRICE_CANDIDATE'):
            for field in ('open_time','close_time'):
                wanted.update(t//60*60 for t in timestamp_options(row.get(field,''),profile['models']))
    minutes=minute_precached if minute_precached is not None else read_selected_minutes(output/'histdata_archives',wanted,market_clock)
    # M1 checks are a frozen-model diagnostic. They do not retrospectively select a new clock.
    source_checks=[]
    for source,profile in sorted(profiles.items()):
        if profile['status']!='STRONG_PRICE_CANDIDATE':continue
        best=profile['models'][0]
        eligible=[e for e in events[source] if any(base.utc_stamp(e,m)//calibration_interval*calibration_interval in calibration_bars for m in base.models())]
        days=sorted({e.local.date() for e in eligible});split=max(1,min(len(days)-1,int(len(days)*.6)))
        train_days=set(days[:split]);validation_days=set(days[split:]);validation=[e for e in eligible if e.local.date() in validation_days]
        entry=base.metrics([None if (b:=minutes.get(base.utc_stamp(e,best)//60*60)) is None else max(b[0]-e.price,e.price-b[1],D(0)) for e in validation])
        # Closing quotes on validation ENTRY days only, one vote per local close five minutes.
        exit_events={}
        for row in rows:
            if row['source']!=source or row.get('gold','').lower() not in ('true','1') or row.get('record_type')!='TRADE':continue
            try:
                opened=datetime.fromisoformat(row['open_time']);closed=datetime.fromisoformat(row['close_time'])
                price=D(row['close_price'])
                if opened.date() not in validation_days or base.boundary_day(closed) or price<=0:continue
                options=timestamp_options(row['close_time'],profile['models'])
                if len(options)==1:exit_events.setdefault(options[0]//300,base.Event(closed,price))
            except (ValueError,KeyError,ArithmeticError):continue
        exits=base.metrics([None if (b:=minutes.get(base.utc_stamp(e,best)//60*60)) is None else max(b[0]-e.price,e.price-b[1],D(0)) for e in exit_events.values()])
        source_checks.append(dict(source_key='S-'+hashlib.sha256(source.encode()).hexdigest()[:12],
            validation_entry_1m=entry,validation_exit_1m=exits,
            entry_check_reuses_validation=calibration_interval==60,
            diagnostic_only=True,confirmed_timezone=False))
    aligned=[];counts=Counter();years=defaultdict(Counter);case_ids={c['id'] for c in json.loads((root/'product/private/cases.json').read_text(encoding='utf-8'))['cases']};case_counts=Counter()
    for row in rows:
        profile=profiles.get(row['source'],dict(status='NO_GOLD_CALIBRATION',models=[]))
        scope='WHOLE_SOURCE'
        if row.get('open_time') and profile['status']!='STRONG_PRICE_CANDIDATE':
            scope=quarter(datetime.fromisoformat(row['open_time']))
            profile=segmented.get((row['source'],scope),profile)
        item=align_row(row,profile,bars,minutes);item['model_scope']=scope
        item['market_clock_model']=market_clock
        item['market_clock_status']=market_info['market_clock_status']
        if scope!='WHOLE_SOURCE' and profile.get('status')=='STRONG_PRICE_CANDIDATE' and row.get('close_time'):
            if quarter(datetime.fromisoformat(row['close_time']))!=scope:
                item['close_utc_candidate']='';item['close_utc_options_count']=0;item['exit_gap_1m_usd']=''
                item['issues']=sorted(set(item['issues']+['CLOSE_OUTSIDE_SUPPORTED_SEGMENT']))
        aligned.append(item)
        gold=row.get('gold','').lower() in ('true','1') and row['record_type']=='TRADE'
        key=('gold_' if gold else 'other_')+('candidate_utc' if item['open_utc_candidate'] else 'review_candidate_utc' if item['open_utc_review_candidate'] else 'unresolved')
        counts[key]+=1;years[row.get('open_time','')[:4]][key]+=1
        if gold and item['open_utc_candidate']:
            if item['entry_gap_1m_usd'] and D(item['entry_gap_1m_usd'])<=D('.5'):
                counts['gold_candidate_entry_1m_match']+=1
                if item['exit_gap_1m_usd'] and D(item['exit_gap_1m_usd'])<=D('.5'):
                    counts['gold_candidate_both_1m_match']+=1
        if gold and item['open_utc_review_candidate'] and item['entry_gap_1m_usd'] and D(item['entry_gap_1m_usd'])<=D('.5'):
            counts['gold_review_entry_1m_match']+=1
            if item['exit_gap_1m_usd'] and D(item['exit_gap_1m_usd'])<=D('.5'):counts['gold_review_both_1m_match']+=1
        cid='T-'+hashlib.sha256(row['record_id'].encode()).hexdigest()[:12]
        if cid in case_ids:
            case_counts['total']+=1
            case_counts['candidate_utc' if item['open_utc_candidate'] else 'review_candidate_utc' if item['open_utc_review_candidate'] else 'unresolved']+=1
            if item['open_utc_candidate'] and item['entry_gap_1m_usd'] and D(item['entry_gap_1m_usd'])<=D('.5'):
                case_counts['candidate_entry_1m_match']+=1
    available_gold=sum(any(base.execution_bar(base.Event(datetime.fromisoformat(r['open_time']),D(r['open_price'])),m) in bars for m in base.models())
                       for r in rows if r.get('gold','').lower() in ('true','1') and r['record_type']=='TRADE')
    summary=dict(record_rows=len(rows),trade_rows=sum(r['record_type']=='TRADE' for r in rows),
        gold_trade_rows=sum(r.get('gold','').lower() in ('true','1') and r['record_type']=='TRADE' for r in rows),
        calibration_interval_seconds=calibration_interval,
        source_count=len(source_info),gold_calibration_sources=len(events),
        full_source_statuses=dict(Counter(p['status'] for p in profiles.values())),
        strong_calendar_segments=len(segmented),retained_local_events=sum(map(len,events.values())),
        market=market_info,gold_rows_with_any_clock_quote=available_gold,
        row_statuses=dict(counts),by_year={y:dict(c) for y,c in sorted(years.items())},product_candidates=dict(case_counts),
        confirmed_timezone_rows=0,production_enabled_rows=0,
        tolerance_usd_per_oz='0.5',sidecar_is_private=True,
        independence_note='Sources and repeated exports are not independent accounts; evidence deduplicated within source 5m.',
        minute_diagnostics_sources=len(source_checks))
    base.write_csv(result/'all_records_UTC_candidates_PRIVATE.csv',aligned)
    base.write_csv(result/'source_registry_PRIVATE.csv',registries)
    base.write_csv(result/'source_1m_checks_PRIVATE.csv',source_checks)
    base.write_csv(result/'hypotheses_PRIVATE.csv',hypotheses)
    base.write_csv(result/'months_PRIVATE.csv',month_rows)
    (result/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    changed=[p for p,h in expected.items() if sha(root/p)!=h]
    if changed:raise RuntimeError('Immutable inputs changed')
    provenance=dict(inputs=expected,raw_and_input_files_checked=len(expected),changed=changed,
        script_sha256=sha(Path(__file__)),archives={p.name:sha(p) for p in sorted((output/'histdata_archives').glob('*.zip'))},
        source_metadata_has_explicit_timezone=False,market_timezone_reference='https://www.histdata.com/f-a-q/',
        public_feed_failures=['Dukascopy JSON HTTP 429 Bot blocked','Dukascopy bi5 HTTP 429'])
    (result/'provenance_PRIVATE.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding='utf-8')
    return summary


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['download','analyze'])
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--result',type=Path)
    parser.add_argument('--market-clock',choices=['EST_CLAIM_ONLY','EMPIRICAL_EU_SHIFT'],default='EST_CLAIM_ONLY')
    parser.add_argument('--calibration-interval',type=int,choices=[60,300],default=300)
    args=parser.parse_args()
    if args.action=='download':download(args.root.resolve(),args.output.resolve())
    else:
        if args.result is None:parser.error('--result required for analyze')
        print(json.dumps(run(args.root.resolve(),args.output.resolve(),args.result.resolve(),args.market_clock,args.calibration_interval),ensure_ascii=False))

if __name__=='__main__':main()
