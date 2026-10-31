"""Supplementary EURUSD clock evidence for exports containing no gold.

Read-only statements; private outputs only. Never confirms account timezone.
"""
import argparse,csv,io,json,time,urllib.request,urllib.parse,zipfile
from collections import Counter
from datetime import datetime
from decimal import Decimal as D
from pathlib import Path
import expand_time_alignment as m


def run(root: Path, output: Path) -> None:
    output.mkdir(parents=True,exist_ok=True);cache=output/'eurusd_archives';cache.mkdir(exist_ok=True)
    records=list(csv.DictReader((root/'artifacts/behavior_audit_20261001_final/all_records.csv').open(encoding='utf-8-sig')))
    gold_sources={r['source'] for r in records if r['gold'].lower()=='true'}
    rows=[r for r in records if r['source'] not in gold_sources and r['symbol']=='EURUSD' and r['record_type']=='TRADE']
    manifest=[]
    for year in sorted({int(r['open_time'][:4]) for r in rows}):
        path=cache/f'EURUSD_M1_{year}.zip'
        page=f'https://www.histdata.com/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/eurusd/{year}'
        if not path.exists():
            with urllib.request.urlopen(page,timeout=30) as response:html=response.read().decode()
            form=m.DownloadForm();form.feed(html)
            if form.fields.get('fxpair')!='EURUSD':raise ValueError('Wrong public download form')
            request=urllib.request.Request('https://www.histdata.com/get.php',data=urllib.parse.urlencode(form.fields).encode(),headers={'Referer':page})
            with urllib.request.urlopen(request,timeout=90) as response:body=response.read()
            with zipfile.ZipFile(io.BytesIO(body)) as z:
                if z.testzip():raise ValueError('Invalid archive')
            with path.open('xb') as stream:stream.write(body)
        manifest.append(dict(period=year,page=page,bytes=path.stat().st_size,sha256=m.sha(path)))
        print(json.dumps(dict(stage='eurusd_download',year=year,bytes=path.stat().st_size)),flush=True)
        time.sleep(.5)
    (output/'download_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    bars={}
    scale=D(5000) # base tolerance .5 == 0.0001 USD/EUR (one pip), not $0.50.
    for dt,b in m.histdata_rows(cache,'EMPIRICAL_EU_SHIFT'):
        key=int(dt.timestamp())//300*300;lo=b['low']*scale;hi=b['high']*scale
        if key in bars:bars[key]=(min(bars[key][0],lo),max(bars[key][1],hi))
        else:bars[key]=(lo,hi)
    normalized=[dict(r,gold='True',open_price=str(D(r['open_price'])*scale)) for r in rows]
    events=m.calibration_events(normalized);profiles=[]
    for source,entries in sorted(events.items()):
        summary,_,_=m.base.evaluate(entries,bars)
        if m.limited_candidate(summary):summary['status']='LIMITED_PRICE_CANDIDATE'
        profiles.append(dict(source_key='S-'+m.hashlib.sha256(source.encode()).hexdigest()[:12],source_private=source,
            **summary,models=summary['equivalent_models'],instrument='EURUSD',tolerance='0.0001',
            market_clock_model='EMPIRICAL_EU_SHIFT',market_clock_status='NOT_INDEPENDENTLY_VERIFIED_FOR_EURUSD'))
    m.base.write_csv(output/'profiles_PRIVATE.csv',profiles)
    summary=dict(trade_rows=len(rows),sources=len(events),statuses=dict(Counter(p['status'] for p in profiles)),
        strong_source_rows=sum(1 for r in rows if any(p['source_private']==r['source'] and p['status']=='STRONG_PRICE_CANDIDATE' for p in profiles)),
        confirmed_timezone_rows=0,production_enabled_rows=0,eurusd_market_clock_status='REQUIRES_INDEPENDENT_EVENT_ANCHOR',
        note='EURUSD only; no-gold export clock candidates. Do not treat as gold market similarity.')
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.root.resolve(),a.output.resolve())
