"""Offline threshold sensitivity. No model calls, profit metrics or product changes."""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from math import log
from pathlib import Path
from statistics import mean, median
import sys

PRODUCT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PRODUCT))
DEFAULT=PRODUCT/'private/threshold_comparison_20261027'
FIELDS=('d5','d1h','dtail','vol_ratio')
BASE=dict(d5=.25,d1h=.50,dtail=.10,vol_ratio=2.)


def configurations():
    result={
        'strict':dict(label='原嚴檔',kind='joint',limits=dict(d5=.15,d1h=.30,dtail=.06,vol_ratio=1.5)),
        'medium':dict(label='原中檔：基線',kind='baseline',limits=dict(BASE)),
        'loose':dict(label='原寬檔',kind='joint',limits=dict(d5=.40,d1h=.80,dtail=.16,vol_ratio=3.)),
    }
    for name,label,key,value in [
        ('five20','五分更嚴0.20','d5',.20),('five30','五分更寬0.30','d5',.30),
        ('hour40','小時更嚴0.40','d1h',.40),('hour60','小時更寬0.60','d1h',.60),
        ('tail08','末段更嚴0.08','dtail',.08),('tail12','末段更寬0.12','dtail',.12),
        ('vol15','波動更嚴1.5倍','vol_ratio',1.5),('vol30','波動更寬3倍','vol_ratio',3.),
    ]:
        limits=dict(BASE);limits[key]=value
        result[name]=dict(label=label,kind='single',limits=limits)
    for name,label,factor in [('minus10','基線收緊10% ',.9),('plus10','基線放寬10% ',1.1)]:
        result[name]=dict(label=label.strip(),kind='local',limits={
            **{k:round(BASE[k]*factor,8) for k in FIELDS[:3]},'vol_ratio':1+(BASE['vol_ratio']-1)*factor})
    return result


def fixed_score(row):
    return max(*(row[k]/BASE[k] for k in FIELDS[:3]),log(row['vol_ratio'])/log(BASE['vol_ratio']))


def compare_outputs(base,other):
    if not base or not other:
        return dict(top1_same_case=None,top1_same_group=None,top5_group_jaccard=None)
    a={r['group'] for r in base};b={r['group'] for r in other}
    return dict(top1_same_case=base[0]['case_id']==other[0]['case_id'],
                top1_same_group=base[0]['group']==other[0]['group'],top5_group_jaccard=len(a&b)/len(a|b))


def metric_medians(rows):
    if not rows:return None
    return {**{k:median(r[k] for r in rows) for k in FIELDS},
            'fixed_medium_max':median(fixed_score(r) for r in rows)}


def summarize(records,configs):
    output={}
    for split in ('all','development','reserved_review'):
        subset=[r for r in records if split=='all' or r['split']==split];group={}
        for method in configs:
            pairs=[(r['methods']['medium'],r['methods'][method]) for r in subset]
            common=[(a,b) for a,b in pairs if a['rows'] and b['rows']]
            comparisons=[compare_outputs(a['rows'],b['rows']) for a,b in common]
            hits=sum(bool(b['rows']) for a,b in pairs);n=len(pairs)
            group[method]=dict(queries=n,with_output=hits,coverage=hits/n if n else None,
                with_five=sum(len(b['rows'])>=5 for a,b in pairs),
                passed_unique_median=median(b['passed_unique'] for a,b in pairs) if n else None,
                statuses={status:sum(b['status']==status for a,b in pairs) for status in sorted({b['status'] for a,b in pairs})},
                common_queries=len(common),only_variant=sum(not a['rows'] and bool(b['rows']) for a,b in pairs),
                only_medium=sum(bool(a['rows']) and not b['rows'] for a,b in pairs),
                both_empty=sum(not a['rows'] and not b['rows'] for a,b in pairs),
                top1_case_agreement=mean(c['top1_same_case'] for c in comparisons) if common else None,
                top1_group_agreement=mean(c['top1_same_group'] for c in comparisons) if common else None,
                top5_group_jaccard=mean(c['top5_group_jaccard'] for c in comparisons) if common else None,
                common_variant=metric_medians([b['rows'][0] for a,b in common]),
                common_medium=metric_medians([a['rows'][0] for a,b in common]))
        output[split]=group
    return output


def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n',encoding='utf8')


def private_output(path):
    path=path.resolve()
    if not path.is_relative_to((PRODUCT/'private').resolve()):raise ValueError('PRIVATE_OUTPUT_REQUIRED')
    path.mkdir(parents=True,exist_ok=True)
    return path


def build(out):
    from backend.candidate_sidecar import load_candidate_sidecar
    from backend.context_retrieval import ContextIndex
    from backend.context_rules import market_features,pair_metrics,evaluate_rows
    from research.similarity_evaluation import blind_packet
    out=private_output(out);old=PRODUCT/'private/similarity_evaluation_20261023'
    selection_path=old/'selection_PRIVATE.json'
    selection=json.loads(selection_path.read_text(encoding='utf8'))
    for relative,expected in selection['inputs'].items():
        if sha256((PRODUCT/relative).read_bytes()).hexdigest()!=expected:raise ValueError('FROZEN_INPUT_CHANGED')
    expected=json.loads((old/'results_PRIVATE.json').read_text(encoding='utf8'))
    expected_by_id={r['query_case_id']:r for r in expected}
    selected=selection['queries']
    if len(selected)!=30 or len(expected_by_id)!=30:raise ValueError('FROZEN_QUERY_COUNT_CHANGED')
    casefile=PRODUCT/'private/cases.json';sidefile=PRODUCT/'private/case_candidate_market_profiles.json'
    cases=json.loads(casefile.read_text(encoding='utf8'))['cases']
    profiles,status=load_candidate_sidecar(casefile,sidefile,PRODUCT/'private')
    if status!='READY':raise ValueError('SIDECAR_'+status)
    configs=configurations();inputs={str(p.relative_to(PRODUCT)):sha256(p.read_bytes()).hexdigest()
        for p in (casefile,sidefile,selection_path,old/'results_PRIVATE.json',PRODUCT/'backend/context_rules.py',PRODUCT/'backend/context_retrieval.py')}
    manifest=dict(schema='threshold_comparison_v1',inputs=inputs,configs=configs,queries=30,
        fixed_event_buffer=.1,fixed_tail_neutral=.5,human_accuracy=None,default_changed=False,
        note='Prior frozen30 historical dates, split20/10 already previously inspected; no unseen-test claim.')
    manifest_path=out/'manifest_PRIVATE.json'
    if manifest_path.exists() and json.loads(manifest_path.read_text(encoding='utf8'))!=manifest:
        raise ValueError('FROZEN_EXPERIMENT_CHANGED')
    dump(manifest_path,manifest)
    index=ContextIndex(cases,profiles);records=[];chart_packets=[];parity=0;checked=0
    for number,q in enumerate(selected,1):
        old_record=expected_by_id[q['case_id']];qp=profiles[q['case_id']];qf=market_features(qp)
        if qp['as_of']!=q['as_of'] or index.lookup[q['case_id']]['group']!=q['group']:raise ValueError('QUERY_IDENTITY_CHANGED')
        split='development' if number<=20 else 'reserved_review'
        if old_record['split']!=split:raise ValueError('FROZEN_SPLIT_CHANGED')
        pool,counts=index.eligible(qp,q['side'],q['group'])
        metrics=[dict(case_id=c['id'],group=c['group'],**pair_metrics(qf,index.features[c['id']])) for c in pool]
        methods={};sets={}
        for name,config in configs.items():
            evaluation=evaluate_rows(metrics,index.descriptions,config['limits'])
            sets[name]=evaluation.pop('_passed_ids');evaluation.pop('nearest_rejected')
            evaluation['status']=('UNCERTAIN_EVENT' if qf['event']=='BOUNDARY_UNKNOWN' else
                                  'NO_COMPARABLE_CASES' if not pool else 'PASSED' if evaluation['rows'] else 'NO_RULE_MATCH')
            for r in evaluation['rows']:
                case=index.lookup[r['case_id']];desc=index.descriptions[r['case_id']]
                assert case['side']==q['side'] and case['available_at']<=q['as_of']
                assert case['group']!=q['group'] and desc['window_end']<=q['window_start']
                assert not r['reasons'] and r['score_max']<=1+1e-12
                checked+=1
            methods[name]=evaluation
        assert sets['strict']<=sets['medium']<=sets['loose']
        new=methods['medium'];prior=old_record['current']
        assert [r['case_id'] for r in new['rows']]==[r['id'] for r in prior['cases']]
        assert new['status']==prior['rule_status'] and new['passed_unique']==prior['comparison']['passed_unique']
        parity+=1
        record=dict(query_id=old_record['query_id'],split=split,as_of=q['as_of'],side=q['side'],
                    eligible_rows=len(pool),query_event=qf['event'],methods=methods)
        records.append(record)
        ids=[methods[n]['rows'][0]['case_id'] if methods[n]['rows'] else None for n in ('strict','medium','loose')]
        if len(set(ids))>1 and len(chart_packets)<6:
            first=next(cid for cid in ids if cid is not None)
            query=blind_packet('unused',qp,profiles[first],q['side'])['query']
            candidates={name:(blind_packet('unused',qp,profiles[methods[name]['rows'][0]['case_id']],q['side'])['candidate']
                        if methods[name]['rows'] else None) for name in ('strict','medium','loose')}
            chart_packets.append(dict(query_id=record['query_id'],side=q['side'],split=split,query=query,candidates=candidates,
                first_metrics={name:(methods[name]['rows'][0] if methods[name]['rows'] else None) for name in candidates}))
        print(f'Fixed query {number}/30 completed ({split})',flush=True)
    summary=summarize(records,configs)
    dump(out/'results_PRIVATE.json',records);dump(out/'summary.json',summary);dump(out/'chart_packets_PRIVATE.json',chart_packets)
    dump(out/'validation.json',dict(queries=30,configurations=len(configs),medium_parity_queries=parity,
        temporal_checked_displayed_pairs=checked,nested_sets=True,diagnostic_pages=len(chart_packets),human_accuracy=None))
    with (out/'summary.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        fields=['split','method','label','queries','with_output','coverage','common_queries','only_variant','only_medium',
                'top1_case_agreement','top1_group_agreement','top5_group_jaccard',*FIELDS,'fixed_medium_max']
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for split,group in summary.items():
            for name,s in group.items():
                writer.writerow(dict(split=split,method=name,label=configs[name]['label'],
                    **{k:s[k] for k in fields[3:12]},**(s['common_variant'] or {})))
    (out/'notes.txt').write_text('Frozen13 settings on original30 dates. All quality metrics are internal diagnostics, not human accuracy.\n'
        'Common-output cohorts have separate denominators. Diagnostic plots are first6 chronological differing outputs, not blind review.\n'
        'No default changes, no profit-based choice, no provider calls.\n',encoding='utf8')
    print(json.dumps(summary['all'],ensure_ascii=False),flush=True)
    return summary


def render(out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.patches import Rectangle
    from research.render_similarity_comparison import configure
    configure();out=private_output(out)
    summary=json.loads((out/'summary.json').read_text(encoding='utf8'))
    configs=json.loads((out/'manifest_PRIVATE.json').read_text(encoding='utf8'))['configs']
    names=list(configurations());labels=[configs[n]['label'] for n in names]
    allstats=summary['all'];positions=list(range(len(names)))
    footer='固定30個歷史日期；內部數值診斷不是人評準確率。20／10組先前已有基線結果，不是全新獨立測試。'
    fig,axes=plt.subplots(1,2,figsize=(16,9));fig.subplots_adjust(left=.16,right=.96,top=.87,bottom=.15,wspace=.43)
    for split,offset,color in [('development',-.18,'#286c82'),('reserved_review',.18,'#ce9336')]:
        values=[summary[split][n]['coverage']*100 for n in names]
        axes[0].barh([p+offset for p in positions],values,height=.34,color=color,label='原前20日期' if split=='development' else '原後10日期')
    axes[0].set_yticks(positions,labels);axes[0].set_xlim(0,118);axes[0].invert_yaxis()
    axes[0].set_title('找到至少一例的比例',loc='left',fontweight='bold');axes[0].set_xlabel('查詢覆蓋（%）；越高不等於越準');axes[0].legend(fontsize=10)
    values=[allstats[n]['with_output'] for n in names]
    axes[1].barh(positions,values,color=['#ce9336' if n=='medium' else '#438795' for n in names],height=.62)
    axes[1].set_yticks(positions,labels);axes[1].invert_yaxis();axes[1].set_xlim(0,33);axes[1].set_title('全30日期的有輸出次數',loc='left',fontweight='bold')
    for p,v in enumerate(values):axes[1].text(v+.3,p,f'{v}/30',va='center',fontsize=10)
    for ax in axes:ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
    fig.suptitle('門檻比較一：放寬後多找到多少案例？',fontsize=20,fontweight='bold',y=.96)
    fig.text(.04,.045,footer,fontsize=11);fig.savefig(out/'01_門檻覆蓋比較.png',dpi=300)
    fig.savefig(out/'01_門檻覆蓋比較.pdf');plt.close(fig)

    fig,axes=plt.subplots(1,2,figsize=(16,9));fig.subplots_adjust(left=.16,right=.96,top=.85,bottom=.16,wspace=.43)
    agreement=[allstats[n]['top1_group_agreement'] for n in names]
    for p,n in enumerate(names):
        a=agreement[p]
        if a is not None:axes[0].barh(p,a*100,color='#438795',height=.60)
        axes[0].text((a*100 if a is not None else 0)+1,p,f'{a:.0%} (n={allstats[n]["common_queries"]})' if a is not None else '無共同輸出',va='center',fontsize=9)
    flips=[allstats[n]['only_variant']+allstats[n]['only_medium'] for n in names]
    axes[1].barh(positions,flips,color='#ce9336',height=.60)
    for p,n in enumerate(names):axes[1].text(flips[p]+.12,p,f'+{allstats[n]["only_variant"]} / -{allstats[n]["only_medium"]}',va='center',fontsize=10)
    for ax in axes:ax.set_yticks(positions,labels);ax.invert_yaxis();ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
    axes[0].set_xlim(0,137);axes[0].set_xticks([0,20,40,60,80,100]);axes[0].set_title('與中檔同一第一名操作群',loc='left',fontweight='bold');axes[0].set_xlabel('只算兩者共同有輸出的查詢；空結果不算一致')
    axes[1].set_xlim(0,max(flips)+4);axes[1].set_title('有無結果翻轉次數（分母30）',loc='left',fontweight='bold');axes[1].set_xlabel('+ 新增有結果；- 中檔有、該方案沒有')
    fig.suptitle('門檻比較二：改門檻，案例會不會換？',fontsize=20,fontweight='bold',y=.96)
    fig.text(.04,.045,'±10%兩列是局部擾動；其餘是較大步長。群一致不代表人工正確，較嚴的零結果也不是成功拒絕證明。',fontsize=11)
    fig.savefig(out/'02_結果穩定性.png',dpi=300);fig.savefig(out/'02_結果穩定性.pdf');plt.close(fig)

    fig,axes=plt.subplots(2,2,figsize=(16,13));fig.subplots_adjust(left=.18,right=.96,top=.89,bottom=.12,hspace=.37,wspace=.65)
    for ax,key,title in zip(axes.flat,FIELDS,['五分鐘路徑差（百分點）','一小時路徑差（百分點）','最近半小時路徑差（百分點）','相對波動倍率（1為相同）']):
        for p,n in enumerate(names):
            s=allstats[n]
            if not s['common_variant']:continue
            a=s['common_medium'][key];b=s['common_variant'][key]
            ax.plot([a,b],[p,p],color='#c6cdd3',lw=2)
            ax.scatter(a,p,color='#9babb5',s=28);ax.scatter(b,p,color='#168b8b',s=32)
        ax.set_yticks(positions,[f'{labels[i]} (n={allstats[n]["common_queries"]})' for i,n in enumerate(names)],fontsize=9)
        ax.invert_yaxis();ax.set_title(title,loc='left',fontweight='bold',fontsize=12);ax.grid(axis='x',alpha=.15)
    axes[0,0].scatter([],[],color='#9babb5',label='中檔');axes[0,0].scatter([],[],color='#168b8b',label='比較方案');axes[0,0].legend(fontsize=9)
    fig.suptitle('門檻比較三：同一批可比較查詢的第一名差距',fontsize=19,fontweight='bold',y=.96)
    fig.text(.04,.035,'每列只比較該方案與中檔共同有輸出的相同查詢，中位數；各列n可能不同，不宜直接跨列排冠軍。\n這些數值也參與檢索，反映取捨而非外部準確率；未以賺賠挑門檻。',fontsize=11,linespacing=1.7)
    fig.savefig(out/'03_共同查詢數值取捨.png',dpi=300);fig.savefig(out/'03_共同查詢數值取捨.pdf');plt.close(fig)

    packets=json.loads((out/'chart_packets_PRIVATE.json').read_text(encoding='utf8'));(out/'charts').mkdir(exist_ok=True)
    with PdfPages(out/'六日_嚴中寬K線對照.pdf') as pdf:
        for p in packets:
            fig,axes=plt.subplots(4,2,figsize=(14,12),sharey='col')
            fig.subplots_adjust(left=.08,right=.98,bottom=.11,top=.91,hspace=.42,wspace=.14)
            for r,name in enumerate(('query','strict','medium','loose')):
                data=p['query'] if name=='query' else p['candidates'][name]
                for col,iv in enumerate(('5m','1h')):
                    ax=axes[r,col];name_label='查詢盤面' if name=='query' else configs[name]['label']
                    ax.set_title(name_label+'｜'+('五分鐘60棒' if iv=='5m' else '一小時20棒'),loc='left',fontsize=11)
                    if data is None:
                        ax.text(.5,.5,'本設定沒有符合案例',transform=ax.transAxes,ha='center',va='center',color='#a15d2b');ax.grid(axis='y',alpha=.12);continue
                    bars=data[iv]
                    if iv=='5m':
                        ax.axvspan(53.5,59.5,color='#e7edf0',alpha=.65)
                        ref=bars[-26:-6]
                        for value in (max(b['high'] for b in ref),min(b['low'] for b in ref)):
                            ax.hlines(value,33.5,59.5,ls='--',color='#8695a0',lw=.7)
                    for x,b in enumerate(bars):
                        color='#168b8b' if b['close']>=b['open'] else '#c17b35'
                        ax.vlines(x,b['low'],b['high'],color=color,lw=.7)
                        ax.add_patch(Rectangle((x-.3,min(b['open'],b['close'])),.6,max(.0001,abs(b['close']-b['open'])),facecolor=color,edgecolor=color,lw=.3))
                    ax.set_xlim(-1,len(bars));ax.set_xticks([0,len(bars)-1],['起點','最後已收棒']);ax.set_ylabel('相對首收（%）',fontsize=9);ax.grid(axis='y',alpha=.12)
            fig.suptitle(p['query_id']+'｜'+p['side']+'｜嚴、中、寬實際第一名對照',fontsize=17,fontweight='bold')
            fig.text(.07,.025,'按時間取最前六個輸出不同的查詢；這是差異診斷，不是隨機盲評。每欄共用縱軸，各路徑首收歸零。\n灰底為最後半小時；虛線為事件前參考高低。無結果保持空白，沒有用未過關案例補滿。',fontsize=10,linespacing=1.6)
            fig.savefig(out/'charts'/f'{p["query_id"]}.png',dpi=135);pdf.savefig(fig);plt.close(fig)
    cards=''.join(f'<section><h2>{p["query_id"]}</h2><img src="charts/{p["query_id"]}.png" loading="lazy" alt="嚴中寬K線診斷"></section>' for p in packets)
    figures=''.join(f'<section><img src="{name}.png" alt="{name}"></section>' for name in ('01_門檻覆蓋比較','02_結果穩定性','03_共同查詢數值取捨'))
    (out/'index.html').write_text('<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>門檻比較</title><style>body{font:18px/1.65 system-ui;color:#183344;background:#eef2f4;max-width:1280px;margin:auto;padding:24px}section{margin:24px 0;background:white;padding:16px}img{width:100%;height:auto}</style><h1>門檻比較：數值取捨與K線對照</h1><p>固定30個不同日期、13組設定；沒有人工準確率，不以覆蓋率或歷史賺賠宣告最佳門檻。正式網站未改。</p>'+figures+cards+'</html>',encoding='utf8')
    print('Rendered three overview PNGs and '+str(len(packets))+' diagnostic pages.',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=DEFAULT);parser.add_argument('--render-only',action='store_true')
    args=parser.parse_args()
    if args.render_only:render(args.output)
    else:build(args.output)
