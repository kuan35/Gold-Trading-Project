"""Recover original reported Gain for exact already-imported CSV observations.

Adds a private evidence file, never changes cases or assumes margin capital.
"""
import csv,hashlib,json
from decimal import Decimal,InvalidOperation
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def main():
    private=ROOT/'product/private';casepath=private/'cases.json'
    auditpath=ROOT/'artifacts/behavior_audit_20261001_final/gold_behavior_records.csv'
    cases={c['id']:c for c in json.loads(casepath.read_text(encoding='utf-8'))['cases']}
    result={};mismatch=0
    with auditpath.open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            ident='T-'+hashlib.sha256(row['record_id'].encode()).hexdigest()[:12]
            if ident not in cases or row['source_format']!='CSV':continue
            c=cases[ident]
            if any(Decimal(row[key])!=Decimal(c[other]) for key,other in [('open_price','entry'),('close_price','exit'),('lot','lot')]) or row['side']!=c['side']:
                mismatch+=1;continue
            try:
                raw=json.loads(row['raw_values']);gain=raw.get('Gain')
                value=Decimal(str(gain).strip().replace('%','').replace(',',''))
                if not value.is_finite():continue
            except (ValueError,InvalidOperation,AttributeError):continue
            if ident in result:raise ValueError('DUPLICATE_CASE_LINK')
            result[ident]=dict(reported_gain_raw=gain,reported_gain_pct=format(value,'f'),
                basis='MYFXBOOK_REPORTED_GAIN_OPENING_BALANCE',margin_roi_pct=None,
                source=row['source'],source_row=row['source_row'],audit_record_id=row['record_id'])
    folder=private/'margin_reaudit_20261030';folder.mkdir(exist_ok=True)
    payload=dict(source_definition='https://www.myfxbook.com/help/knowledge-base/gain/',
      inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (casepath,auditpath)},cases=result)
    (folder/'reported_gain_by_case_PRIVATE.json').write_text(json.dumps(payload,ensure_ascii=False,sort_keys=True,indent=2),encoding='utf-8')
    summary=dict(product_candidates=len(cases),csv_candidates=sum(c.get('source_format')=='CSV' for c in cases.values()),
      exactly_linked_reported_gain=len(result),link_mismatches=mismatch,missing_reported_gain=len(cases)-len(result),
      actual_initial_margin_records=0,production_changed=False,
      note='Gain為原報表帳戶餘額基準報酬，非單筆保證金ROI；原值保留，不由四捨五入百分比倒推本金。')
    (ROOT/'product/docs/reported_gain_coverage_20261030.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
