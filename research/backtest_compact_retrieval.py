"""Point-in-time replay of a frozen, compact market-description retrieval rule.

Run with the analysis Python (numpy/matplotlib), not the web service process.
All per-case outputs remain in product/private. No order or external LLM calls.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import sqrt
from pathlib import Path
from statistics import mean
import sys

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from backend.candidate_sidecar import load_candidate_sidecar
from backend.compact_market import (METHOD, describe_compact, distinct_rows, eligible_pool,
                                    format_compact, pair_measure, rank_pool, volatility_bounds,
                                    volatility_band)
from backend.hybrid_retrieval import rank_hybrid_candidates

METHODS = ('five', 'hour', 'full', 'path_only', 'recent', 'random')
LABELS = dict(five='五分型態＋波動', hour='加一小時三段', full='加前高低結構（主方法）',
              path_only='純五分收盤路徑', recent='最近成熟案例', random='固定種子隨機',
              existing_hybrid='原12指標混合方法（月樣本）')


def dump(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True,
                               separators=(',', ':')), encoding='utf-8')


def path_pct(profile, interval):
    bars = profile['pre_entry_bars'][interval]
    base = float(bars[0]['close'])
    return [(float(b['close']) / base - 1) * 100 for b in bars]


def select_queries(cases, descriptions):
    representatives = {}
    for c in sorted(cases, key=lambda c: (descriptions.get(c['id'], {}).get('as_of', 10**20), c['id'])):
        d = descriptions.get(c['id'])
        if d and d['tier'] == 'full':
            representatives.setdefault(c['group'], c)
    queries = sorted(representatives.values(), key=lambda c: (descriptions[c['id']]['as_of'], c['id']))
    seen = set()
    result = []
    for case in queries:
        d = descriptions[case['id']]
        window = (case['side'], d['end_5m'], d['end_1h'])
        primary = window not in seen
        seen.add(window)
        year = datetime.fromtimestamp(d['as_of'], timezone.utc).year
        result.append(dict(case_id=case['id'], group=case['group'], side=case['side'],
                           as_of=d['as_of'], year=year,
                           month=datetime.fromtimestamp(d['as_of'], timezone.utc).strftime('%Y-%m'),
                           primary=primary, period='evaluation_2024_2025' if year in (2024, 2025)
                           else 'recent_2026' if year >= 2026 else 'earlier_through_2023'))
    return result


def annotate(rows, descriptions, query, bounds, paths):
    result = []
    for row in rows:
        case_id = row['case_id']
        d = descriptions[case_id]
        full = pair_measure(query, d, bounds, 'full')
        result.append(dict(case_id=case_id, group=row['group'], agreement=full['agreement_count'],
                           fields=full['field_matches'], max_difference_atr=full['max_difference_atr'],
                           volatility_ratio=full['volatility_ratio'],
                           path_5m_rmse_pct=sqrt(mean((a-b)**2 for a,b in zip(paths['query']['5m'],paths[case_id]['5m']))),
                           path_1h_rmse_pct=sqrt(mean((a-b)**2 for a,b in zip(paths['query']['1h'],paths[case_id]['1h'])))))
    return result


def aggregate(records, method, *, primary=True):
    chosen = [r for r in records if (r['primary'] or not primary) and method in r['methods']]
    available = [r for r in chosen if r['methods'][method]]
    pairs = [p for r in available for p in r['methods'][method]]
    return dict(queries=len(chosen), with_results=len(available),
                with_five=sum(len(r['methods'][method]) == 5 for r in chosen),
                any_same_template=sum(any(p['agreement'] == 4 for p in r['methods'][method]) for r in available),
                top_one_same_template=sum(r['methods'][method][0]['agreement'] == 4 for r in available),
                top_one_agreement_distribution=dict(sorted(Counter(str(r['methods'][method][0]['agreement']) for r in available).items())),
                top_five_agreement_distribution=dict(sorted(Counter(str(p['agreement']) for p in pairs).items())),
                pair_count=len(pairs), mean_agreement=mean(p['agreement'] for p in pairs) if pairs else None,
                path_5m_rmse_pct=mean(p['path_5m_rmse_pct'] for p in pairs) if pairs else None,
                path_1h_rmse_pct=mean(p['path_1h_rmse_pct'] for p in pairs) if pairs else None,
                structure_agreement=mean(p['fields']['structure'] for p in pairs) if pairs else None,
                hourly_pattern_agreement=mean(p['fields']['hour'] for p in pairs) if pairs else None,
                volatility_ratio=mean(p['volatility_ratio'] for p in pairs) if pairs else None)


def masked_chart(profile, interval):
    bars = profile['pre_entry_bars'][interval]
    base = float(bars[0]['close'])
    return [[(float(b[k])/base - 1)*100 for k in ('open','high','low','close')] for b in bars]


def render_viewer(output, records, cases, profiles, descriptions):
    """Fixed first available primary query per quarter/side, not curated winners."""
    selected = {}
    for r in records:
        if r['year'] not in (2024, 2025) or not r['primary'] or not r['methods']['full']:
            continue
        key = (r['year'], (int(r['month'][-2:])-1)//3, r['side'])
        selected.setdefault(key, r)
    items = []
    for token, r in enumerate(selected.values(), 1):
        q = descriptions[r['case_id']]
        bounds = r['volatility_bounds']
        def item(case_id):
            d = descriptions[case_id]
            return dict(text=format_compact(d, volatility_band(d['atr_pct_5m'],bounds)),
                        five=masked_chart(profiles[case_id],'5m'),
                        hour=masked_chart(profiles[case_id],'1h'))
        items.append(dict(token=f'Q{token:02}', query=item(r['case_id']),
                          methods={LABELS[m]:[dict(**item(p['case_id']),agreement=p['agreement'],
                                                  difference=p['max_difference_atr'])
                                              for p in r['methods'][m][:2]]
                                   for m in ('five','hour','full','path_only')}))
    payload = json.dumps(items, ensure_ascii=False, separators=(',',':')).replace('<','\\u003c')
    template = """<!doctype html><meta charset="utf-8"><title>Gold Desk 雙週期檢索回放</title>
<style>body{font:15px system-ui;margin:24px;background:#f4f6f8;color:#18212c}header{position:sticky;top:0;background:#f4f6f8;padding:12px 0;z-index:2}select{font:inherit;padding:8px;margin:4px}article{background:white;border:1px solid #ccd3da;border-radius:6px;margin:12px 0;padding:16px}.charts{display:grid;grid-template-columns:1fr 1fr;gap:12px}svg{width:100%;background:#fff}p{line-height:1.6}.muted{color:#596776;font-size:13px}h2{font-size:17px}@media(max-width:800px){.charts{grid-template-columns:1fr}}</style>
<header><h1>固定格式盤面檢索：歷史時點回放</h1><label>查詢<select id="query"></select></label><label>方法<select id="method"></select></label><p class="muted">固定選取2024–2025每季每方向第一個可用查詢。已遮日期、來源身分與損益；此頁用來看效果，不是已完成的人工盲評。每列左5分60棒、右1小時20棒；價格均以第一根收盤價歸零。</p></header><main id="main"></main>
<script>const data=__DATA__;const q=document.querySelector('#query'),m=document.querySelector('#method');data.forEach((x,i)=>q.add(new Option(x.token,i)));Object.keys(data[0]?.methods||{}).forEach(x=>m.add(new Option(x,x)));m.value='加前高低結構（主方法）';
function chart(b,title){let lo=Math.min(...b.map(x=>x[2])),hi=Math.max(...b.map(x=>x[1]));let pad=Math.max((hi-lo)*.08,.01);lo-=pad;hi+=pad;const y=v=>220-(v-lo)/(hi-lo)*190;let s='<svg viewBox="0 0 700 250"><text x="8" y="17" font-size="13">'+title+'</text>';[lo,(lo+hi)/2,hi].forEach(v=>s+='<line x1="50" x2="690" y1="'+y(v)+'" y2="'+y(v)+'" stroke="#e5e9ee"/><text x="0" y="'+(y(v)+4)+'" font-size="10">'+v.toFixed(2)+'%</text>');b.forEach((x,i)=>{const px=56+i*630/b.length,c=x[3]>=x[0]?'#177e89':'#d17a22';s+='<line x1="'+px+'" x2="'+px+'" y1="'+y(x[1])+'" y2="'+y(x[2])+'" stroke="'+c+'"/><rect x="'+(px-2.5)+'" y="'+Math.min(y(x[0]),y(x[3]))+'" width="5" height="'+Math.max(1,Math.abs(y(x[0])-y(x[3])))+'" fill="'+c+'"/>'});return s+'</svg>'}
function row(x,title){return '<article><h2>'+title+'</h2><p>'+x.text+'</p><div class="charts">'+chart(x.five,'5分鐘')+chart(x.hour,'1小時')+'</div></article>'}function draw(){const x=data[+q.value];if(!x)return;document.querySelector('#main').innerHTML=row(x.query,'查詢盤面')+x.methods[m.value].map((a,i)=>row(a,'第'+(i+1)+'筆：四欄吻合 '+a.agreement+'/4；最大數值差 '+a.difference.toFixed(2)+' ATR')).join('')}q.onchange=m.onchange=draw;draw();</script>"""
    (output/'review_PRIVATE.html').write_text(template.replace('__DATA__',payload),encoding='utf-8')
    return len(items)


def render_overview(output, summary):
    import matplotlib.pyplot as plt
    methods = ['five','hour','full','path_only','recent','random']
    labels = ['5m + vol','+ hourly','+ structure','5m path','Recent','Random']
    stats = summary['evaluation_2024_2025']
    fig,axes=plt.subplots(1,3,figsize=(14,4),layout='constrained')
    for ax,key,title in zip(axes,('mean_agreement','path_5m_rmse_pct','path_1h_rmse_pct'),
                           ('Four-field agreement (0-4; higher)','5m path RMSE, percentage points (lower)',
                            '1h path RMSE, percentage points (lower)')):
        vals=[stats[m][key] or 0 for m in methods]
        ax.bar(range(len(methods)),vals,color=['#7f9db0','#527a96','#177e89','#d17a22','#88909a','#adb6be'])
        ax.set_xticks(range(len(methods)),labels,rotation=30,ha='right',fontsize=8)
        ax.set_title(title,fontsize=10)
        ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    fig.suptitle('2024-2025 temporal replay: diagnostics, not relevance accuracy',fontsize=12)
    fig.savefig(output/'overview.png',dpi=300);fig.savefig(output/'overview.pdf');plt.close(fig)


def make_report(output, summary):
    rows=['# 固定格式盤面檢索 v1：離線回放結果','',
          f"已產生 {summary['library']['ready_descriptions']} 筆固定描述；完整 {summary['library']['full']}、五分鐘限定 {summary['library']['five_only']}。",
          f"完整資料每群最早一筆共 {summary['query_groups']} 個查詢群，去除相同方向／已收盤面時點後主統計 {summary['primary_queries']} 個查詢窗。2024–2025 主要時間分段統計如下。",
          '', '| 方法 | 有結果／查詢 | 至少一筆同四欄描述 | 前五平均吻合欄數 | 五分路徑RMS差（百分點） | 一小時路徑RMS差（百分點） |',
          '|---|---:|---:|---:|---:|---:|']
    for method in METHODS:
        s=summary['evaluation_2024_2025'][method]
        def f(key): return '—' if s[key] is None else f'{s[key]:.3f}'
        rows.append(f"| {LABELS[method]} | {s['with_results']}/{s['queries']} | {s['any_same_template']} | {f('mean_agreement')} | {f('path_5m_rmse_pct')} | {f('path_1h_rmse_pct')} |")
    stats=summary['evaluation_2024_2025'];five=stats['five'];hour=stats['hour'];full=stats['full']
    if full['queries'] and full['with_results']:
        rows += ['', '## 這次實測的取捨', '',
                 f"- 主方法在 {full['queries']} 個查詢窗中，有 {full['any_same_template']} 個至少找到一筆四欄全相同描述（{full['any_same_template']/full['queries']:.1%}）；其餘只能稱最近參考，不能把所有列出的前五都當足夠相似。",
                 f"- 加一小時三段後，一小時路徑差由 {five['path_1h_rmse_pct']:.3f} 降為 {hour['path_1h_rmse_pct']:.3f} 百分點；五分鐘差則由 {five['path_5m_rmse_pct']:.3f} 變為 {hour['path_5m_rmse_pct']:.3f}。多週期背景更接近，但五分鐘細節有所取捨。",
                 f"- 再加前高低結構後，前五結構吻合由 {hour['structure_agreement']:.1%} 增為 {full['structure_agreement']:.1%}；一小時路徑差由 {hour['path_1h_rmse_pct']:.3f} 變為 {full['path_1h_rmse_pct']:.3f}。規則符合程度提高不代表每個 K 線距離都改善。",
                 f"- 主方法第一名四欄吻合數分布：`{json.dumps(full['top_one_agreement_distribution'],ensure_ascii=False)}`。",
                 '- 以上描述同一批原行情上的診斷；沒有獨立人工相關性分數，不能宣稱新法準確率高於原法。']
    rows += ['', '## 原混合方法：相同固定月份子樣本', '',
             '| 方法 | 查詢窗 | 平均四欄吻合 | 五分路徑RMS差 | 一小時路徑RMS差 |', '|---|---:|---:|---:|---:|']
    for method in ('full','path_only','existing_hybrid'):
        s=summary['matched_monthly_sample'][method]
        vals=['—' if s[k] is None else f'{s[k]:.3f}' for k in ('mean_agreement','path_5m_rmse_pct','path_1h_rmse_pct')]
        rows.append(f"| {LABELS[method]} | {s['queries']} | {' | '.join(vals)} |")
    rows += ['', '## 參數敏感性', '',
             '保持其他規則不變，把各段 U/D 中性界線由 1 ATR 改為 0.8／1.2 ATR，只在固定月樣本觀察前五重疊。不是從中選最好看的參數。',
             '```json',json.dumps(summary['sensitivity'],ensure_ascii=False,indent=2),'```',
             '', '## 如何解讀', '',
             '- 四欄吻合是這套規則本身的符合程度，不能當獨立準確率；同描述仍可能有不同的段內震盪、轉折位置。',
             '- K 線 RMS 是原行情數值差，越小代表該定義下更近；它和排名輸入有重疊，也不是人工相關性真值。',
             '- 回放依查詢時點重新建立池與波動分位，案例須成熟、不同群、進場前盤面不重疊。所有方法同池。',
             '- 沒有定義交易策略出場、成本與風控，因此此處沒有策略收益／獲利預測準確率。損益與手數沒有進入任何排序。',
             '- 2024–2025 是時間分段檢查，這些年份已有其他研究，不稱完全未看過的獨立留出集。',
             '- 歷史行情是 PROJECT_REFERENCE，原券商時鐘 UNKNOWN。正式網站仍維持原混合方法。',
             '', f"結果資料摘要 SHA-256：`{summary['result_digest']}`。逐查詢資料、描述及輸入／程式 SHA-256 在同資料夾。",
             '', '查看 `review_PRIVATE.html` 可切換方法，並對照同一查詢及前兩筆案例的五分鐘／一小時 K 棒。']
    (output/'report.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')


def main(argv=None):
    import numpy as np
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=PRODUCT/'private/compact_retrieval_backtest_20261020')
    parser.add_argument('--limit',type=int)
    parser.add_argument('--skip-hybrid',action='store_true')
    args=parser.parse_args(argv)
    output=args.output.resolve()
    if not output.is_relative_to((PRODUCT/'private').resolve()):
        raise ValueError('per-case outputs must remain under product/private')
    output.mkdir(parents=True,exist_ok=True)
    case_path=PRODUCT/'private/cases.json'
    sidecar=PRODUCT/'private/case_candidate_market_profiles.json'
    profiles,status=load_candidate_sidecar(case_path,sidecar,PRODUCT/'private')
    if status!='READY':raise RuntimeError('sidecar integrity check: '+status)
    cases=json.loads(case_path.read_text(encoding='utf-8'))['cases']
    descriptions={};issues=[]
    for case in cases:
        if case['id'] not in profiles:continue
        try:descriptions[case['id']]=describe_compact(profiles[case['id']],case['side'])
        except (KeyError,TypeError,ValueError) as error:issues.append(dict(case_id=case['id'],reason=str(error)))
    print(f'descriptions={len(descriptions)} issues={len(issues)}',flush=True)
    with (output/'descriptions_PRIVATE.jsonl').open('w',encoding='utf-8',newline='\n') as stream:
        for ident in sorted(descriptions):stream.write(json.dumps(dict(case_id=ident,**descriptions[ident]),ensure_ascii=False,sort_keys=True)+'\n')
    dump(output/'description_issues_PRIVATE.json',issues)
    full_cases=[c for c in cases if c['id'] in descriptions and descriptions[c['id']]['tier']=='full']
    queries=select_queries(cases,descriptions)
    if args.limit:queries=queries[:args.limit]
    full_ids=[c['id'] for c in full_cases];positions={ident:i for i,ident in enumerate(full_ids)}
    paths={ident:{iv:path_pct(profiles[ident],iv) for iv in ('5m','1h')} for ident in full_ids}
    path_matrix=np.asarray([paths[ident]['5m'] for ident in full_ids])
    records=[];monthly_seen=set();monthly_records=[]
    for number,query_info in enumerate(queries,1):
        qid=query_info['case_id'];query=descriptions[qid]
        pool,counts=eligible_pool(full_cases,descriptions,query,exclude_group=query_info['group'])
        bounds=volatility_bounds(pool,descriptions)
        record=dict(**query_info,counts=counts,volatility_bounds=bounds,methods={m:[] for m in METHODS})
        if bounds:
            paths['query']=paths[qid]
            for variant in ('five','hour','full'):
                record['methods'][variant]=annotate(rank_pool(pool,descriptions,query,bounds,variant=variant),descriptions,query,bounds,paths)
            indices=np.asarray([positions[c['id']] for c in pool],dtype=int)
            distances=np.sqrt(np.mean((path_matrix[indices]-np.asarray(paths[qid]['5m']))**2,axis=1))
            ordered=sorted(zip(pool,distances),key=lambda p:(float(p[1]),p[0]['id']))
            base_rows=[dict(case_id=c['id'],group=c['group']) for c,_ in ordered]
            recent=sorted(pool,key=lambda c:(-descriptions[c['id']]['as_of'],c['id']))
            random_groups={}
            for c in sorted(pool,key=lambda c:(descriptions[c['id']]['as_of'],c['id'])):
                random_groups.setdefault(c['group'],c)
            random=sorted(random_groups.values(),key=lambda c:sha256(f'compact-v1|{qid}|{c["group"]}'.encode()).digest())
            for name,rows in [('path_only',base_rows),('recent',[dict(case_id=c['id'],group=c['group']) for c in recent]),
                              ('random',[dict(case_id=c['id'],group=c['group']) for c in random])]:
                record['methods'][name]=annotate(distinct_rows(rows,descriptions),descriptions,query,bounds,paths)
            if (query_info['primary'] and 2021<=query_info['year']<=2025
                    and query_info['month'] not in monthly_seen):
                monthly_seen.add(query_info['month'])
                if not args.skip_hybrid:
                    old=rank_hybrid_candidates(pool,profiles,profiles[qid],query['side'],query['as_of'])
                    old_rows=distinct_rows(old['full'],descriptions)
                    record['methods']['existing_hybrid']=annotate(old_rows,descriptions,query,bounds,paths)
                monthly_records.append(record)
        records.append(record)
        if number%100==0 or number==len(queries):print(f'replay={number}/{len(queries)}',flush=True)
    with (output/'queries_PRIVATE.jsonl').open('w',encoding='utf-8',newline='\n') as stream:
        for record in records:stream.write(json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n')
    print('running frozen sensitivity checks',flush=True)
    sensitivity={}
    for neutral in (.8,1.2):
        altered={ident:dict(d,pattern_5m=''.join('U' if v>neutral else 'D' if v< -neutral else 'S' for v in d['phase_5m_atr']),
                             pattern_1h=''.join('U' if v>neutral else 'D' if v< -neutral else 'S' for v in d['phase_1h_atr']) if d['phase_1h_atr'] else None)
                 for ident,d in descriptions.items()}
        overlaps=[]
        for r in monthly_records:
            q=altered[r['case_id']]
            pool,_=eligible_pool(full_cases,altered,q,exclude_group=r['group'])
            rows=rank_pool(pool,altered,q,r['volatility_bounds'])
            before={p['case_id'] for p in r['methods']['full']}
            overlaps.append(len(before&{p['case_id'] for p in rows})/len(before))
        sensitivity[str(neutral)]=dict(queries=len(overlaps),mean_top_five_overlap=mean(overlaps) if overlaps else None,
                                       changed_full_pattern_rows=sum((d['pattern_5m'],d['pattern_1h'])!=(altered[i]['pattern_5m'],altered[i]['pattern_1h']) for i,d in descriptions.items() if d['tier']=='full'))
    summary=dict(method=METHOD,library=dict(cases=len(cases),ready_descriptions=len(descriptions),
                                           full=sum(d['tier']=='full' for d in descriptions.values()),
                                           five_only=sum(d['tier']=='5m_only' for d in descriptions.values()),
                                           unavailable_cases=len(cases)-len(descriptions),issues=len(issues)),
                 query_groups=len(records),primary_queries=sum(r['primary'] for r in records),
                 all_years={m:aggregate(records,m) for m in METHODS},
                 evaluation_2024_2025={m:aggregate([r for r in records if r['year'] in (2024,2025)],m) for m in METHODS},
                 by_year={str(y):{m:aggregate([r for r in records if r['year']==y],m) for m in METHODS} for y in sorted({r['year'] for r in records})},
                 matched_monthly_sample={m:aggregate(monthly_records,m) for m in ('full','path_only','existing_hybrid')},
                 sensitivity=sensitivity,independent_human_relevance_labels=0,
                 similarity_accuracy=None,strategy_return=None,clock_status='UNKNOWN',alignment_scope='PROJECT_REFERENCE')
    summary['result_digest']=sha256((output/'queries_PRIVATE.jsonl').read_bytes()).hexdigest()
    summary['viewer_query_count']=render_viewer(output,records,cases,profiles,descriptions)
    dump(output/'summary.json',summary)
    files=[case_path,sidecar,Path(__file__),PRODUCT/'backend/compact_market.py',PRODUCT/'backend/hybrid_retrieval.py',
           PRODUCT/'docs/compact_market_retrieval_v1_20261020.md']
    dump(output/'manifest_PRIVATE.json',dict(inputs={str(p.relative_to(PRODUCT)):sha256(p.read_bytes()).hexdigest() for p in files},
                                            config=dict(neutral_atr=1,support_lookback=20,top_k=5,purge_overlap=True,
                                                        five_anchors=[0,19,39,59],hour_anchors=[0,6,12,19],
                                                        volatility_quantiles=[.25,.75],equal_category_fields=['five','hour','structure','volatility'],
                                                        ranking_tie_break=['max_atr_difference','mean_atr_difference','volatility_ratio','case_id']),
                                            query_limit=args.limit,hybrid_skipped=args.skip_hybrid,result_digest=summary['result_digest']))
    make_report(output,summary);render_overview(output,summary)
    print(json.dumps(dict(output=str(output),query_groups=len(records),primary_queries=summary['primary_queries'],digest=summary['result_digest'],evaluation=summary['evaluation_2024_2025']),ensure_ascii=False),flush=True)
    return summary


if __name__=='__main__':main()
