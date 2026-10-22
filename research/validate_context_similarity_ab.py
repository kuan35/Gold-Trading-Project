"""Independent Decimal checks of primary A/B matches and deterministic reruns."""
from decimal import Decimal, localcontext
from hashlib import sha256
import json
from pathlib import Path
import csv

PRODUCT=Path(__file__).resolve().parents[1]
OUT=PRODUCT/'private/context_similarity_ab_20261021'


def independent_distance(left,right):
    with localcontext() as ctx:
        ctx.prec=40
        a=[(Decimal(b['close'])/Decimal(left[0]['close'])-1)*100 for b in left]
        b=[(Decimal(c['close'])/Decimal(right[0]['close'])-1)*100 for c in right]
        return float((sum((x-y)**2 for x,y in zip(a,b))/len(a)).sqrt())


def main():
    manifest=json.loads((OUT/'manifest_PRIVATE.json').read_text(encoding='utf-8'))
    for p,h in manifest['inputs'].items():assert sha256((PRODUCT/p).read_bytes()).hexdigest()==h,p
    names=['queries_PRIVATE.json','summary.json','plot_profiles_PRIVATE.json','comparison.csv','manifest_PRIVATE.json','notes.txt','validation.json']
    for name in names:assert (OUT/name).read_bytes()==(OUT/'repro'/name).read_bytes(),name
    records=json.loads((OUT/'queries_PRIVATE.json').read_text(encoding='utf-8'))
    with (OUT/'comparison.csv').open(encoding='utf-8-sig',newline='') as stream:
        exported=list(csv.DictReader(stream))
    assert len(exported)==len(records)*7
    lookup={r['query_id']:r for r in records}
    for row in exported:
        matches=lookup[row['query_id']]['methods'][row['method']]['rows']
        assert row['case_id']==(matches[0]['case_id'] if matches else ''),'CSV_CASE_ID_MISSING'
    profiles=json.loads((OUT/'plot_profiles_PRIVATE.json').read_text(encoding='utf-8'))
    checked=0;errors=[]
    for r in records:
        q=profiles['queries'][r['query_id']]
        for m in ('A','B_medium'):
            if not r['methods'][m]['rows']:continue
            pair=r['methods'][m]['rows'][0];p=profiles['cases'][pair['case_id']]
            for label,size,key in [('5m',60,'d5'),('1h',20,'d1h'),('5m',7,'dtail')]:
                a=q['pre_entry_bars'][label][-size:];b=p['pre_entry_bars'][label][-size:]
                distance=independent_distance(a,b);error=abs(distance-pair[key]);errors.append(error)
                assert error<1e-10,(r['query_id'],m,key,error)
                assert all(c['time']+(300 if label=='5m' else 3600)<=q['as_of'] for c in a)
                assert all(c['time']+(300 if label=='5m' else 3600)<=p['as_of'] for c in b)
            vq=Decimal(q['indicators']['5m_atr_pct']);vp=Decimal(p['indicators']['5m_atr_pct'])
            assert abs(float(max(vq/vp,vp/vq))-pair['vol_ratio'])<1e-10
            checked+=1
    from pypdf import PdfReader
    pdf=PdfReader(OUT/'十日_AB六格K線對照.pdf')
    assert len(pdf.pages)==10
    for number,page in enumerate(pdf.pages,1):assert f'D{number:02}' in page.extract_text()
    before=PRODUCT/'private/context_ab_originals_before_20261021.txt'
    after=PRODUCT/'private/context_ab_originals_after_20261021.txt'
    assert before.read_bytes()==after.read_bytes()
    result=dict(status='PASS',repro_files_identical=names,csv_rows_checked=len(exported),primary_pairs_independently_checked=checked,
                decimal_precision=40,max_distance_error=max(errors),pdf_pages_checked=10,
                original_files_count=len(before.read_text(encoding='utf-8').splitlines()),
                original_set_sha256=sha256(before.read_bytes()).hexdigest().upper())
    (OUT/'independent_validation.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
