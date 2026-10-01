"""Import audited, sanitized data locally; never commit the private directory."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from collections import Counter,defaultdict
from datetime import datetime,timedelta,timezone
from decimal import Decimal,InvalidOperation
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BEHAVIORS={'NO_OBSERVED_POSITION':'可見初始單','ADD_ADVERSE':'價格不利時加單','ADD_FAVORABLE':'價格有利時加單',
           'ADD_FLAT':'同價加單','TIME_TIE':'順序不明','OPPOSITE':'反向持倉','MIXED':'混合持倉','INVALID':'無法判讀'}


def read_rows(path:Path) -> list[dict]:
    with path.open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))


def date(value:str) -> datetime:
    return datetime.fromisoformat(value)


def upper_time(value:str) -> int:
    dt=date(value)
    if dt.tzinfo is not None:
        return int((dt+timedelta(minutes=1)).timestamp())
    # Latest UTC for any offset in [-14,+14]. Minute precision is an interval.
    return int((dt.replace(tzinfo=timezone.utc)+timedelta(hours=14,minutes=1)).timestamp())


def load_cases(path:Path,group_sequences:dict|None=None) -> list[dict]:
    rows=read_rows(path)
    groups:dict[str,list[dict]]=defaultdict(list)
    for row in rows:
        if row.get('observed_overlap_group') and row.get('open_time') and row.get('close_time'):
            groups[row['observed_overlap_group']].append(row)
    cases=[]
    cached:dict[str,tuple[int,list[dict]]]={}
    for row in rows:
        behavior=row.get('behavior','INVALID')
        if behavior not in ('NO_OBSERVED_POSITION','ADD_ADVERSE','ADD_FAVORABLE','ADD_FLAT'):
            continue
        if int(row.get('identical_signature_candidate_count') or '1')!=1:
            continue
        if row.get('cross_source_duplicate_candidate','').lower() in ('true','1'):
            continue
        if row.get('side') not in ('BUY','SELL') or not row.get('profit'):
            continue
        try:
            qty=Decimal(row['lot']); entry=Decimal(row['open_price']); profit=Decimal(row['profit'])
            if not all(x.is_finite() for x in (qty,entry,profit)) or qty<=0 or entry<=0:
                continue
            group=row.get('observed_overlap_group') or row['record_id']
            members=groups.get(group,[row])
            if group not in cached:
                available=max(upper_time(r['close_time']) for r in members)
                sequence=[]
                for i,r in enumerate(sorted(members,key=lambda r:(r['open_time'],r['record_id'])),1):
                    if not r.get('lot') or not r.get('open_price'):
                        continue
                    sequence.append(dict(index=i,side=r['side'],lot=r['lot'],entry=r['open_price'],exit=r.get('close_price'),
                                         profit=r.get('profit'),role=BEHAVIORS.get(r['behavior'],r['behavior']),
                                         ordering_uncertain=r['behavior']=='TIME_TIE'))
                cached[group]=(available,sequence)
            available,sequence=cached[group]
            public_group='G-'+hashlib.sha256(group.encode()).hexdigest()[:12]
            if group_sequences is not None:
                group_sequences[public_group]=sequence[:100]
            ident='T-'+hashlib.sha256(row['record_id'].encode()).hexdigest()[:12]
            cases.append(dict(id=ident,label=BEHAVIORS[behavior],side=row['side'],action='FIRST' if behavior=='NO_OBSERVED_POSITION' else 'ADD',
                              lot=str(qty),entry=row['open_price'],exit=row.get('close_price'),opened_at=row['open_time'],closed_at=row['close_time'],
                              available_at=available,profit=str(profit),currency=row.get('currency') or 'UNKNOWN',
                              group=public_group,source_kind='trader_history',time_alignment='unknown',
                              behavior=behavior,prior_count=int(row.get('observed_prior_count') or 0),prior_lot=row.get('observed_prior_lot') or '0',
                              signed_distance=row.get('signed_distance_to_avg_pct') or None,market=None,sequence=sequence[:24] if group_sequences is None else [],
                              sequence_total=len(sequence),source_format=row.get('source_format'),
                              scope_status='逐來源可見資料，不等於完整帳戶',market_alignment_reason='來源時區未核實，未提供盤面特徵'))
        except (KeyError,ValueError,InvalidOperation):
            # Audited rows remain in original derived CSV. This case index only accepts valid mature candidates.
            continue
    return cases


def import_bars(path:Path,start:str,days:int) -> dict:
    lower=datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    upper=lower+timedelta(days=days)
    bars=[]
    with path.open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            stamp=datetime.fromisoformat(row['timestamp'])
            if lower<=stamp<upper:
                bars.append(dict(time=int(stamp.timestamp()),**{key:row[key] for key in ('open','high','low','close','volume')}))
    if len(bars)<360:
        raise ValueError('指定行情窗口不足360根5分K，請改選有交易日的期間')
    return dict(source='Dukascopy BID歷史行情・非即時報價・來源量欄位非全球成交量',bars=bars)


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-dir',type=Path,required=True)
    parser.add_argument('--bars',type=Path,required=True)
    parser.add_argument('--market-start',default='2025-10-01')
    parser.add_argument('--days',type=int,default=10)
    args=parser.parse_args()
    records=args.audit_dir/'gold_behavior_records.csv'
    rows=read_rows(records)
    group_sequences={}
    cases=load_cases(records,group_sequences)
    counts=Counter(r.get('behavior','INVALID') for r in rows)
    sources=read_rows(args.audit_dir/'source_inventory.csv')
    times=[r['open_time'] for r in rows if r.get('open_time')]
    audit=dict(source_files=len(sources),total_gold_records=len(rows),period=f'{min(times)[:10]} 至 {max(times)[:10]}' if times else '無資料',
               refreshed_at='2026-10-01',source='private_audit',
               groups=[dict(code=code,label=label,count=counts[code],description='描述可見操作條件，不是已確認策略') for code,label in BEHAVIORS.items()],
               limitations=['來源觀察列不是去重後獨立交易數；跨格式可能重複',
                            'CSV時間只到分鐘；未平倉快照不算已實現績效',
                            '帳戶／時區與資料完整性未全核實，首筆僅指無可見既有持倉',
                            '此頁含全部可見列；案例檢索另排除順序不明和重複候選'])
    private=ROOT/'private';private.mkdir(exist_ok=True)
    (private/'cases.json').write_text(json.dumps({'cases':cases,'group_sequences':group_sequences},ensure_ascii=False),encoding='utf-8')
    (private/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    (private/'bars.json').write_text(json.dumps(import_bars(args.bars,args.market_start,args.days),ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'eligible_cases':len(cases),'audit_rows':len(rows),'private_output':'product/private','raw_input_modified':False},ensure_ascii=False))


if __name__=='__main__':
    main()
