"""Build private past-only size profiles, clock checklist, and 30 audit queries."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import random
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.cases import CaseStore
from backend.similarity import build_size_profiles, D, METHOD


def read(path: Path) -> list[dict]:
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))


def write(path: Path, rows: list[dict]) -> None:
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def query_clock(c: dict) -> int:
    dt=datetime.fromisoformat(c['opened_at'])
    if dt.tzinfo is None:
        dt=dt.replace(tzinfo=timezone.utc)-timedelta(hours=14,minutes=1)
    return int(dt.timestamp())


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    out=args.output.resolve()
    if not out.is_relative_to((ROOT/'private').resolve()):raise ValueError('逐筆資料只能寫入 product/private')
    public=ROOT/'docs'/out.name
    if out.exists() or public.exists():raise FileExistsError('輸出路徑必須尚未存在')
    audit=ROOT.parent/'artifacts/behavior_audit_20261001_final/gold_behavior_records.csv'
    cases_path=ROOT/'private/cases.json'
    original_hash=hashlib.sha256(cases_path.read_bytes()).hexdigest()
    payload=json.loads(cases_path.read_text(encoding='utf-8'))
    rows=read(audit)
    # Input family already gold; invalid/snapshot rows do not enter entry baselines.
    valid=[r for r in rows if r['record_type']=='TRADE' and r['side'] in ('BUY','SELL')
           and r.get('cross_source_duplicate_candidate','').lower() not in ('true','1')
           and int(r.get('identical_signature_candidate_count') or 1)==1]
    raw_profiles=build_size_profiles(valid)
    keyed={'T-'+hashlib.sha256(k.encode()).hexdigest()[:12]:v for k,v in raw_profiles.items()}
    profiles={c['id']:keyed.get(c['id'],dict(status='INSUFFICIENT_HISTORY',typical_lot=None,count=0,days=0)) for c in payload['cases']}
    data=dict(method=METHOD,profiles=profiles,input_cases_sha256=original_hash,
              limitations=['逐來源可見歷史，不等於完整帳戶','來源時區尚未核實，來源內時間排序為暫定',
                           '前20個已結束5分鐘批次，至少10批及3個日期才有基準'])
    out.mkdir(parents=True);public.mkdir(parents=True)
    (out/'case_size_profiles_PRIVATE.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    # Runtime sidecar is reproducible; never replace cases.json or original files.
    (ROOT/'private/case_size_profiles.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    metadata={}
    for r in rows:
        ident='T-'+hashlib.sha256(r['record_id'].encode()).hexdigest()[:12]
        metadata[ident]=r
    associated=Counter(metadata[c['id']]['source'] for c in payload['cases'])
    registry=read(ROOT/'private/d_time_alignment_expanded_20261012/minute-candidates/source_registry_PRIVATE.csv')
    checklist=[]
    for r in registry:
        checklist.append(dict(source_key=r['source_key'],source_private=r['source_private'],scope=r['scope'],format=r['format'],
                              candidate_status=r['status'],best_model=r['best_model'],equivalent_models=r['equivalent_models'],
                              product_candidates=associated.get(r['source_private'],0),
                              broker_platform_to_confirm='',display_timezone_to_confirm='',effective_dates_to_confirm='',
                              historical_dst_policy_to_confirm='',evidence_file_or_url='',reviewed_by='',
                              timezone_status='UNKNOWN',market_similarity_enabled=False))
    checklist.sort(key=lambda r:(r['candidate_status']!='STRONG_PRICE_CANDIDATE',-r['product_candidates'],r['source_key']))
    write(out/'source_time_confirmation_PRIVATE.csv',checklist)
    s=CaseStore()
    seed=random.Random(20261012)
    selected=[]
    # Time bins within four strata; use no outcomes when selecting.
    for action,side,n in [('FIRST','BUY',8),('FIRST','SELL',7),('ADD','BUY',8),('ADD','SELL',7)]:
        pool=sorted([c for c in s.items if c['action']==action and c['side']==side],key=lambda c:(c['opened_at'],c['id']))
        if len(pool)<n:raise ValueError('不足30筆分層查詢')
        for i in range(n):selected.append(seed.choice(pool[i*len(pool)//n:(i+1)*len(pool)//n]))
    queries=[];results=[];blind=[]
    for i,c in enumerate(selected,1):
        clock=query_clock(c);profile=profiles[c['id']]
        typical=D(profile['typical_lot']) if profile['status']=='READY' else None
        kwargs=dict(prior_count=c.get('prior_count',0),prior_lot=D(c.get('prior_lot') or 0),
                    signed_distance=D(c['signed_distance']) if c.get('signed_distance') else None,typical_lot=typical)
        r=s.retrieve(c['side'],c['action'],D(c['lot']),clock,**kwargs)
        q=dict(query_id=f'Q{i:02}',case_id_private=c['id'],clock_utc=datetime.fromtimestamp(clock,timezone.utc).isoformat(),
               side=c['side'],action=c['action'],lot=c['lot'],typical_lot=str(typical) if typical is not None else None,
               prior_count=kwargs['prior_count'],prior_lot=str(kwargs['prior_lot']),signed_distance=c.get('signed_distance'))
        queries.append(q)
        matched=s.rank(c['side'],c['action'],D(c['lot']),clock,**kwargs)
        assert all(x['group']!=c['group'] and x['available_at']<=clock for x in matched)
        before=[(x['id'],x['distance']) for x in matched]
        for x in s.items:
            if x.get('profit') is not None:x['profit']=str(-D(x['profit']))
        after=s.rank(c['side'],c['action'],D(c['lot']),clock,**kwargs)
        assert before==[(x['id'],x['distance']) for x in after]
        for x in s.items:
            if x.get('profit') is not None:x['profit']=str(-D(x['profit']))
        results.append(dict(query_id=q['query_id'],side=c['side'],action=c['action'],year=c['opened_at'][:4],
                            basis=r['comparison']['basis'],matched_groups=r['total'],status=r['sufficiency']['status'],
                            excluded_missing_profile=r['comparison']['excluded_missing_profile'],
                            matched_with_missing=sum(bool(x['missing_features']) for x in matched),
                            profit_groups=r['wins'],loss_groups=r['losses'],outcome_invariance_pass=True))
        blind.append(dict(query=q,candidates=[{k:v for k,v in x.items() if k not in ('profit','exit','closed_at','sequence','available_at')} for x in matched[:6]],
                          reviewer_scores=dict(relevance_0_to_2='',explanation_correct_0_to_2='',missing_disclosed_0_to_2='',comments='')))
    write(out/'queries_PRIVATE.csv',queries)
    (out/'blind_review_PRIVATE.json').write_text(json.dumps(blind,ensure_ascii=False,indent=2),encoding='utf-8')
    write(public/'query_summary.csv',results)
    stats=Counter(r['status'] for r in results)
    ready=Counter(c['action'] for c in s.items if profiles[c['id']]['status']=='READY')
    summary=dict(method=METHOD,product_candidates=len(s.items),ready_profiles=sum(ready.values()),ready_by_action=ready,
                 queries=30,status_counts={k:stats[k] for k in ('usable','limited','insufficient')},
                 source_confirmation_rows=len(checklist),raw_timezone_confirmed=False,parameters_validated=False,
                 outcome_invariance_pass=True,cases_json_unchanged=hashlib.sha256(cases_path.read_bytes()).hexdigest()==original_hash)
    assert summary['cases_json_unchanged']
    (public/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# D：相似案例實作與30筆查詢試算','',f'產品候選 {len(s.items)}；相對手數基準可用 {sum(ready.values())}（首筆 {ready["FIRST"]}／加倉 {ready["ADD"]}）。不是獨立交易數。',
           '',f'30筆按首筆／加倉、BUY／SELL及時間分層抽取：可參考 {stats["usable"]}、有限參考 {stats["limited"]}、資料不足 {stats["insufficient"]}。',
           '這是程式試算，尚未取得人工盲評，不能宣稱檢索準確率。門檻與權重未依盈虧調整，也尚未完成相關性驗證。','',
           '## 比較方式','',
           '- 先篩方向、首筆／同向加倉及保守成熟時間；每候選群最多一筆。',
           '- 有使用者提供的平常手數，則只與歷史基準足夠的案例比較倍數；其他案例不混入同一距離。未提供則用絕對手數並明示限制。',
           '- 歷史基準按來源取前20個已結束5分鐘下單批次；至少10批及3個日期。每批最早時間的手數中位數一票，避免拆單大量投票。同批及未來都不使用。來源不等於帳戶，時區／完整性仍有限制。',
           '- 首筆距離＝abs(log2(案例手數尺度／查詢手數尺度))。加倉權重：手數0.35、既有單數0.20、加單／既有手數0.25、距均價0.20。',
           '- 手數尺度及加單比例不可相差超過2倍；有利／不利超過±0.02%時不能互配；均價距離差不可超過0.5個百分點。加權距離最多0.65。這些是可解釋工程界線，不是已驗證最適參數。',
           '- 缺少加倉條件，該項距離記1並揭露，不刪權重讓缺漏案例變得更相似。',
           '- 先形成完整池，才各取最近3筆獲利與虧損，缺額用最近案例補齊；另提供各類最近6筆。統計不隨展示篩選改變。',
           '- 少於5群＝資料不足；5–29群或缺基準／未核實時區／缺欄位＝有限參考。狀態不是成功機率；目前沒有市場相似度。','',
           '## 來源時間確認','',
           f'私人確認清單 {len(checklist)} 列，優先較強候選與案例數較多者。請填原平台／券商、匯出顯示時區、適用日期、歷史夏令時間設定及證據位置。不是交易員逐筆標註。',
           '價格吻合只支持候選；原設定文件／當年平台截圖或券商歷史說明才可補獨立證據。所有market_similarity仍false。','',
           '## 盲評方式','',
           '- 私人queries檔凍結30筆；候選文件隱藏盈虧／平倉結果，評分欄0–2：條件接近程度、說明正確性、缺漏揭露。',
           '- 比較不同檢索方法時，沿用相同查詢，將候選隨機代碼／順序交給不知道方法名稱的人；不得用獲利高低評相關性。',
           '- 目前只交付本方法的待評資料，尚未完成多方法隨機盲測；來源／帳戶身份未核實。','']
    (public/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
