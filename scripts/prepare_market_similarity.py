"""Build hash-bound private market profiles from explicitly reviewed timestamps."""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter
import csv
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.market_similarity import build_profiles, snapshot, METHOD
from backend.cases import CaseStore


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def private(path: Path) -> Path:
    path=path.resolve()
    if not path.is_relative_to((ROOT/'private').resolve()):raise ValueError('逐筆資料與輸出限product/private')
    return path


def load_bars(path: Path) -> list[dict]:
    if path.suffix.lower()=='.json':
        rows=json.loads(path.read_text(encoding='utf-8'))['bars']
    else:
        with path.open(encoding='utf-8-sig',newline='') as f:
            rows=list(csv.DictReader(f))
        for r in rows:
            stamp=datetime.fromisoformat(r['timestamp'])
            if stamp.tzinfo is None:raise ValueError('行情必須帶UTC偏移，不能猜測時區')
            r['time']=int(stamp.timestamp())
    rows=sorted(rows,key=lambda b:b['time'])
    if len({r['time'] for r in rows})!=len(rows):raise ValueError('行情時間重複，請先稽核')
    return rows


def evaluate_queries(path: Path, bars: list[dict]) -> dict:
    """Frozen real queries. No human relevance labels or measured accuracy implied."""
    with path.open(encoding='utf-8-sig',newline='') as f: queries=list(csv.DictReader(f))
    s=CaseStore();times=[b['time'] for b in bars];results=[];status=Counter();modes=Counter();invariance=0
    for q in queries:
        clock=int(datetime.fromisoformat(q['clock_utc']).timestamp())
        args=dict(prior_count=int(q['prior_count']),prior_lot=Decimal(q['prior_lot'] or '0'),
                  signed_distance=Decimal(q['signed_distance']) if q['signed_distance'] else None,
                  typical_lot=Decimal(q['typical_lot']) if q['typical_lot'] else None,
                  query_market=snapshot(bars[max(0,bisect_right(times,clock)-1441):bisect_right(times,clock)],clock))
        # Exclude query's own candidate group even if an input maturity bound errs.
        own=next((c for c in s.items if c['id']==q['case_id_private']),None)
        original=s.items
        s.items=[c for c in original if not own or c['group']!=own['group']]
        r=s.retrieve(q['side'],q['action'],Decimal(q['lot']),clock,**args)
        ranked_rows=s.rank(q['side'],q['action'],Decimal(q['lot']),clock,**args)
        before=[(c['id'],c['distance']) for c in ranked_rows]
        saved=[c.get('profit') for c in s.items]
        for c in s.items:c['profit']='999999'
        after=[(c['id'],c['distance']) for c in s.rank(q['side'],q['action'],Decimal(q['lot']),clock,**args)]
        for c,p in zip(s.items,saved):c['profit']=p
        s.items=original
        invariance+=before==after;status[r['sufficiency']['status']]+=1;modes[r['comparison']['mode']]+=1
        results.append(dict(query_id=q['query_id'],mode=r['comparison']['mode'],matched_groups=r['total'],
                            sufficiency=r['sufficiency'],comparison=r['comparison'],
                            blind_candidates=[dict(case_id_private=c['id'],operation=c.get('operation_comparison'),
                              market=c.get('market_comparison'),conditions=c.get('components'))
                              for c in ranked_rows[:5]]))
    return dict(summary=dict(queries=len(queries),sufficiency=dict(status),modes=dict(modes),
                             outcome_invariance_passed=invariance,relevance_accuracy='NOT_MEASURED'),results=results)


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--alignment',type=Path,required=True)
    parser.add_argument('--bars',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'private/case_market_profiles.json')
    parser.add_argument('--queries',type=Path)
    args=parser.parse_args()
    alignment,bars_path,output=private(args.alignment),private(args.bars),private(args.output)
    if output.exists():raise FileExistsError('輸出已存在，請先檢閱舊版或使用新路徑')
    cases_path=ROOT/'private/cases.json'
    original=digest(cases_path)
    dependencies={'bars':bars_path,'alignment':alignment}
    before_inputs={key:dict(path=str(p.relative_to(ROOT/'private')),sha256=digest(p)) for key,p in dependencies.items()}
    ledger=json.loads(alignment.read_text(encoding='utf-8-sig'))
    rows=ledger['cases'];bars=load_bars(bars_path)
    # Evidence references are local, checked and hash-bound through the ledger;
    # the provider's clock itself must also be reviewed, not assumed from a URL.
    checked=[]
    for row in rows:
        if row.get('timezone_status')=='CONFIRMED':
            ref=row.get('evidence_ref')
            if not ref or not private(ROOT/'private'/ref).is_file():raise ValueError('確認時間需附可讀取的私人證據檔')
            evidence=private(ROOT/'private'/ref)
            key='evidence_'+str(len(dependencies)-2)
            dependencies[key]=evidence
            before_inputs[key]=dict(path=str(evidence.relative_to(ROOT/'private')),sha256=digest(evidence))
        checked.append(row)
    result=build_profiles(json.loads(cases_path.read_text(encoding='utf-8'))['cases'],checked,bars)
    result.update(input_cases_sha256=original,inputs=before_inputs)
    if digest(cases_path)!=original:raise RuntimeError('建置中案例索引變更，請重跑')
    if any(digest(path)!=before_inputs[key]['sha256'] for key,path in dependencies.items()):
        raise RuntimeError('建置中行情或證據變更，請重跑')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    summary=dict(method=METHOD,**result['counts'])
    if args.queries:
        evaluation=evaluate_queries(private(args.queries),bars)
        output.with_name(output.stem+'_queries_PRIVATE.json').write_text(json.dumps(evaluation,ensure_ascii=False),encoding='utf-8')
        summary['evaluation']=evaluation['summary']
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
