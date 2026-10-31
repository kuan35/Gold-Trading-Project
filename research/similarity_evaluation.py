"""Local-only blinded relevance study; production rules and rankings are read-only."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import sys

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))
SEED = 'GoldDesk-eval-20261023-v1'
OUTPUT = PRODUCT/'private/similarity_evaluation_20261023'
FIELDS = ['pair_id','reviewer','five_path_1_to_5','hour_background_1_to_5',
          'event_same_different_unclear','volatility_same_different_unclear','overall','reason']


def digest(value):
    return sha256((SEED+str(value)).encode()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+'\n', encoding='utf8')


def day(stamp):
    return datetime.fromtimestamp(stamp, timezone.utc).date().isoformat()


def select_queries(candidates, excluded_dates, count=30):
    """Monthly round-robin, hash order, direction preference; never sees outcomes."""
    buckets = defaultdict(list)
    for row in candidates:
        if day(row['as_of']) not in excluded_dates:
            buckets[day(row['as_of'])[:7]].append(row)
    for rows in buckets.values(): rows.sort(key=lambda r:digest(r['case_id']))
    selected = []; groups = set(); dates = set()
    while len(selected) < count:
        progress = False
        for month in sorted(buckets):
            preferred = 'BUY' if len(selected)%2 == 0 else 'SELL'
            rows = sorted(buckets[month], key=lambda r:(r['side'] != preferred,digest(r['case_id'])))
            for row in rows:
                if (row['group'] in groups or day(row['as_of']) in dates or
                    any(row['window_start'] < old['window_end'] and old['window_start'] < row['window_end'] for old in selected)):
                    continue
                selected.append(row); groups.add(row['group']); dates.add(day(row['as_of']))
                buckets[month].remove(row); progress = True
                break
            if len(selected) == count: break
        if not progress: raise ValueError('INSUFFICIENT_DISTINCT_QUERY_WINDOWS')
    return sorted(selected, key=lambda r:(r['as_of'],r['case_id']))


def blind_packet(pair_id, query, candidate, side):
    def normalized(profile):
        result = {}
        for interval, n in [('5m',60),('1h',20)]:
            bars = profile['pre_entry_bars'][interval][-n:]
            base = float(bars[0]['close'])
            result[interval] = [{k:(float(b[k])/base-1)*100 for k in ('open','high','low','close')} for b in bars]
        return result
    return dict(pair_id=pair_id,side=side,query=normalized(query),candidate=normalized(candidate))


def write_review_csv(path, pair_ids, reviewer):
    try: stream=path.open('x',encoding='utf-8-sig',newline='')
    except FileExistsError: return False
    with stream:
        writer=csv.DictWriter(stream,fieldnames=FIELDS); writer.writeheader()
        writer.writerows(dict(pair_id=p,reviewer=reviewer) for p in pair_ids)
    return True


def summarize_reviews(keys, ratings):
    by_id={k['pair_id']:k for k in keys}; methods=defaultdict(Counter)
    reviewers=('reviewer_1','reviewer_2')
    scores={(pid,reviewer):'' for pid in by_id for reviewer in reviewers};seen=set()
    for row in ratings:
        pid=row.get('pair_id'); reviewer=row.get('reviewer','').strip(); label=row.get('overall','').strip()
        if pid not in by_id: raise ValueError('UNKNOWN_PAIR_ID')
        if reviewer not in reviewers: raise ValueError('UNKNOWN_REVIEWER')
        if (pid,reviewer) in seen: raise ValueError('DUPLICATE_RATING')
        if label not in ('','yes','no','insufficient'): raise ValueError('INVALID_LABEL')
        scores[pid,reviewer]=label;seen.add((pid,reviewer))
    for (pid,reviewer),label in scores.items():
        for method in by_id[pid]['methods']:
            methods[method]['assigned']+=1
            methods[method]['rated' if label else 'unfilled']+=1
            if label: methods[method][label]+=1
    report={}
    for method in sorted({m for key in keys for m in key['methods']}):
        c=methods[method]; decisive=c['yes']+c['no']
        report[method]={k:c[k] for k in ('assigned','rated','unfilled','yes','no','insufficient')}
        report[method]['yes_rate_decidable']=c['yes']/decisive if decisive else None
    paired=[]
    if len(reviewers)==2:
        a,b=sorted(reviewers)
        paired=[(scores.get((pid,a)),scores.get((pid,b))) for pid in by_id
                if scores.get((pid,a)) and scores.get((pid,b))]
    observed=sum(a==b for a,b in paired)/len(paired) if paired else None
    kappa=None
    if paired:
        left,right=Counter(a for a,b in paired),Counter(b for a,b in paired)
        chance=sum(left[c]*right[c] for c in ('yes','no','insufficient'))/len(paired)**2
        if chance<1: kappa=(observed-chance)/(1-chance)
    return dict(methods=report,agreement=dict(paired=len(paired),observed=observed,kappa=kappa),
                interpretation='人評相關性；不是獲利預測準確率；insufficient和未填分開。')


def render_pairs(packets, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.patches import Rectangle
    from research.render_similarity_comparison import configure
    configure(); (out/'charts').mkdir(exist_ok=True)
    with PdfPages(out/'匿名K線對照.pdf') as pdf:
        for packet in packets:
            fig,axes=plt.subplots(2,2,figsize=(12,8),sharey='col')
            fig.subplots_adjust(left=.08,right=.98,top=.88,bottom=.13,hspace=.30,wspace=.15)
            for row,kind in enumerate(('query','candidate')):
                for col,iv in enumerate(('5m','1h')):
                    ax=axes[row,col]; bars=packet[kind][iv]
                    if iv=='5m':
                        ax.axvspan(len(bars)-6.5,len(bars)-.5,color='#dde8ed',alpha=.5)
                        reference=bars[-26:-6]
                        for bound in (max(b['high'] for b in reference),min(b['low'] for b in reference)):
                            ax.hlines(bound,len(bars)-26.5,len(bars)-.5,color='#7c8791',ls='--',lw=.8)
                    for i,b in enumerate(bars):
                        color='#168b8b' if b['close']>=b['open'] else '#c58328'
                        ax.vlines(i,b['low'],b['high'],color=color,lw=.8)
                        ax.add_patch(Rectangle((i-.3,min(b['open'],b['close'])),.6,max(.0001,abs(b['close']-b['open'])),facecolor=color,edgecolor=color,lw=.3))
                    ax.axhline(0,color='#bac3cc',lw=.6); ax.grid(axis='y',alpha=.15)
                    ax.set_xlim(-1,len(bars)); ax.tick_params(labelsize=8)
                    ax.set_xticks([0,len(bars)-1],['窗口起點','最後已收棒'])
                    ax.set_ylabel('相對首棒收盤（%）',fontsize=9)
                    ax.set_title(('查詢盤面' if row==0 else '供比較的歷史盤面')+'｜'+('五分鐘60棒' if iv=='5m' else '一小時20棒'),loc='left',fontsize=12)
            fig.suptitle(packet['pair_id']+'｜相同'+('買進' if packet['side']=='BUY' else '賣出')+'方向',fontsize=17)
            fig.text(.08,.035,'同欄共用縱軸，各自首棒收盤歸零；灰底為最後六棒，虛線為之前二十棒的高低。\n只比較進場前盤面。請在獨立評分表填寫，不要先查看解盲檔。',fontsize=10,color='#526273')
            fig.savefig(out/'charts'/f"{packet['pair_id']}.png",dpi=135); pdf.savefig(fig); plt.close(fig)
    cards=''.join(f'<section id="{p["pair_id"]}"><h2>{p["pair_id"]}</h2><img loading="lazy" src="charts/{p["pair_id"]}.png" alt="{p["pair_id"]} 匿名五分鐘與一小時K線對照"></section>' for p in packets)
    links=' '.join(f'<a href="#{p["pair_id"]}">{p["pair_id"]}</a>' for p in packets)
    (out/'review.html').write_text('''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Gold Desk 匿名案例評估</title><style>body{font:17px/1.65 system-ui,sans-serif;color:#223445;background:#f3f5f7;margin:0}header,main{max-width:1150px;margin:auto;padding:24px}nav{display:flex;gap:10px;flex-wrap:wrap}a{color:#24606d}section{background:white;margin:24px 0;padding:12px;border:1px solid #d8dfe5;border-radius:8px;scroll-margin-top:12px}img{display:block;width:100%;height:auto}p{max-width:950px}</style><header><h1>匿名盤面對照評估</h1><p>請各自填 reviewer_1.csv 或 reviewer_2.csv。先看5分鐘走勢、一小時背景、是否越界後收回、波動差異，再填整體yes／no／insufficient及理由。yes是「適合拿來比較」，不是預測之後會賺。日期、方法、排名與盈虧已遮蔽；請勿先開解盲檔或討論答案。</p><nav>'''+links+'</nav></header><main>'+cards+'</main></html>',encoding='utf8')


def build(out=OUTPUT, render=True):
    from backend.candidate_sidecar import load_candidate_sidecar
    from backend.context_retrieval import ContextIndex,THRESHOLDS
    from backend.dual_path_retrieval import DualPathIndex
    from backend.compact_market import describe_compact
    out=out.resolve()
    if not out.is_relative_to((PRODUCT/'private').resolve()): raise ValueError('PRIVATE_OUTPUT_REQUIRED')
    out.mkdir(parents=True,exist_ok=True)
    casefile=PRODUCT/'private/cases.json'; sidefile=PRODUCT/'private/case_candidate_market_profiles.json'
    cases=json.loads(casefile.read_text(encoding='utf8'))['cases']
    profiles,status=load_candidate_sidecar(casefile,sidefile,PRODUCT/'private')
    if status!='READY': raise ValueError('SIDECAR_'+status)
    index=ContextIndex(cases,profiles); baseline=DualPathIndex(cases,profiles)
    frozen=PRODUCT/'private/context_similarity_ab_20261021/queries_PRIVATE.json'
    excluded={day(r['as_of']) for r in json.loads(frozen.read_text(encoding='utf8'))}
    candidates=[]
    for c in index.cases:
        d=index.descriptions[c['id']]
        if datetime.fromtimestamp(d['as_of'],timezone.utc).year not in (2024,2025): continue
        candidates.append(dict(case_id=c['id'],group=c['group'],side=c['side'],**{k:d[k] for k in ('as_of','window_start','window_end')}))
    selected=select_queries(candidates,excluded,30)
    selection=dict(seed=SEED,thresholds=THRESHOLDS,excluded_dates=sorted(excluded),queries=selected,
                   inputs={str(p.relative_to(PRODUCT)):sha256(p.read_bytes()).hexdigest() for p in (casefile,sidefile,frozen)})
    frozen_path=out/'selection_PRIVATE.json'
    if frozen_path.exists() and json.loads(frozen_path.read_text(encoding='utf8'))!=selection: raise ValueError('FROZEN_SELECTION_CHANGED')
    dump(frozen_path,selection)
    records=[]; keys=[]; packets=[]; query_profiles={}
    for n,q in enumerate(selected):
        qp=profiles[q['case_id']]; qid='Q'+digest(q['case_id'])[:7].upper()
        current=index.retrieve(qp,q['side'],exclude_group=q['group'])
        old=baseline.retrieve(qp,q['side'],exclude_group=q['group'])
        pool,_=index.eligible(qp,q['side'],q['group'])
        controls=sorted(pool,key=lambda c:digest(qid+c['id']))
        method_ids={'current':current['cases'][0]['id'] if current['cases'] else None,
                    'baseline':old['cases'][0]['id'] if old['cases'] else None,
                    'control':controls[0]['id'] if controls else None}
        split='development' if n<20 else 'reserved_review'
        records.append(dict(query_id=qid,query_case_id=q['case_id'],side=q['side'],split=split,
                            as_of=q['as_of'],current=current,baseline=old,method_ids=method_ids))
        query_profiles[qid]=qp
        for cid in sorted(set(method_ids.values())-{None}):
            c=index.lookup[cid]; d=index.descriptions[cid]
            assert c['available_at']<=q['as_of'] and c['side']==q['side'] and c['group']!=q['group']
            assert d['window_end']<=q['window_start']
            pid='P'+digest(qid+cid)[:9].upper()
            keys.append(dict(pair_id=pid,query_id=qid,case_id=cid,split=split,
                             methods=[m for m,v in method_ids.items() if v==cid]))
            packet=blind_packet(pid,qp,profiles[cid],q['side']);packet['query_id']=qid;packets.append(packet)
        print(f'Frozen query {n+1}/30: {current["rule_status"]}',flush=True)
    packets.sort(key=lambda p:digest(p['pair_id']));keys.sort(key=lambda p:p['pair_id'])
    dump(out/'results_PRIVATE.json',records);dump(out/'query_profiles_PRIVATE.json',query_profiles)
    dump(out/'blinding_key_PRIVATE.json',keys);dump(out/'blind_pairs.json',packets)
    for reviewer in ('1','2'): write_review_csv(out/f'reviewer_{reviewer}.csv',[p['pair_id'] for p in packets],'reviewer_'+reviewer)
    if render: render_pairs(packets,out)
    summary=dict(queries=30,development_queries=20,reserved_review_queries=10,distinct_dates=len({day(q['as_of']) for q in selected}),
                 sides=dict(Counter(q['side'] for q in selected)),years=dict(Counter(day(q['as_of'])[:4] for q in selected)),
                 rule_statuses=dict(Counter(r['current']['rule_status'] for r in records)),
                 unique_blind_pairs=len(keys),current_top1_queries=sum(bool(r['method_ids']['current']) for r in records),
                 method='context_contract_v1',human_accuracy=None,selection_independent_of_retrieval=True,
                 note='同一歷史資料庫上的補充回顧人評，不是未來市場泛化或獲利回測。')
    dump(out/'cohort_summary.json',summary);summarize(out)
    print(json.dumps(summary,ensure_ascii=False),flush=True)


def summarize(out):
    keys=json.loads((out/'blinding_key_PRIVATE.json').read_text(encoding='utf8'))
    ratings=[]
    for p in sorted(out.glob('reviewer_*.csv')):
        with p.open(encoding='utf-8-sig',newline='') as stream: ratings.extend(csv.DictReader(stream))
    result=summarize_reviews(keys,ratings)
    result['missing_review_files']=[f'reviewer_{n}.csv' for n in ('1','2') if not (out/f'reviewer_{n}.csv').exists()]
    result['by_split']={}
    for split in ('development','reserved_review'):
        subset=[k for k in keys if k.get('split')==split];ids={k['pair_id'] for k in subset}
        result['by_split'][split]=summarize_reviews(subset,[r for r in ratings if r['pair_id'] in ids])
    common={k['query_id'] for k in keys if 'current' in k['methods']}
    subset=[k for k in keys if k['query_id'] in common];ids={k['pair_id'] for k in subset}
    result['common_output_queries']=len(common)
    result['common_output_subset']=summarize_reviews(subset,[r for r in ratings if r['pair_id'] in ids])
    dump(out/'review_summary.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=OUTPUT)
    parser.add_argument('--summarize',action='store_true');parser.add_argument('--no-render',action='store_true')
    args=parser.parse_args()
    if args.summarize: print(json.dumps(summarize(args.output),ensure_ascii=False))
    else: build(args.output,render=not args.no_render)
