"""Private evidence figures for the frozen A/B experiment; no product UI changes."""
from __future__ import annotations
import argparse
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np

PRODUCT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PRODUCT))
from research.context_similarity_ab import OUTPUT, LIMITS, METHOD, write_review_template
from research.render_similarity_comparison import configure
from research.render_live_dual_samples import candle,path

EVENTS=dict(IN_RANGE='區間內',ABOVE='收在上緣外',BELOW='收在下緣外',
            LOWER_RECLAIM='跌出後收回',UPPER_RECLAIM='突破後收回',BOTH_RECLAIM='雙向收出後回區間',
            BOUNDARY_UNKNOWN='邊界附近，未定')
LABELS=dict(A='A 上一版',B_paths='B 僅全路徑',B_tail='B 加末段',B_vol='B 再加波動',
            B_strict='B 嚴',B_medium='B 中',B_loose='B 寬')
COLORS={'Q':'#243f70','A':'#c58328','B_medium':'#8064a2'}


def tw(stamp):return datetime.fromtimestamp(stamp,ZoneInfo('Asia/Taipei')).strftime('%Y-%m-%d %H:%M')


def save(fig,out,name):
    fig.savefig(out/(name+'.png'),dpi=300)
    fig.savefig(out/(name+'.pdf'))
    plt.close(fig)


def draw_levels(ax,bars,features):
    base=float(bars[0]['close'])
    for k,color in [('reference_high','#926db0'),('reference_low','#92733a')]:
        value=(float(features[k])/base-1)*100
        ax.hlines(value,len(bars)-26-.5,len(bars)-.5,color=color,ls='--',lw=.9)
    ax.axvspan(len(bars)-6-.5,len(bars)-.5,color='#c8d4de',alpha=.23)


def page(r,profiles,pdf,out):
    q=profiles['queries'][r['query_id']];rows=[('Q',q,None,r['query_features'])]
    from research.context_similarity_ab import market_features
    for method in ('A','B_medium'):
        ranked=r['methods'][method]['rows']
        p=profiles['cases'][ranked[0]['case_id']] if ranked else None
        rows.append((method,p,ranked[0] if ranked else None,market_features(p) if p else None))
    fig,axes=plt.subplots(3,2,figsize=(15,12),sharey='col')
    fig.subplots_adjust(left=.075,right=.98,top=.865,bottom=.18,wspace=.17,hspace=.76)
    for row,(method,p,m,f) in enumerate(rows):
        if p is None:
            for ax in axes[row]:
                ax.text(.5,.52,'B 中檔：無通過案例\n空格照實保留，未用其他案例補上',ha='center',va='center',
                        transform=ax.transAxes,fontsize=14,color='#6f5663')
                ax.set_xticks([]);ax.grid(False)
            continue
        for col,iv in enumerate(('5m','1h')):
            bars=p['pre_entry_bars'][iv]
            candle(axes[row,col],bars,levels=False)
            if col==0:draw_levels(axes[row,col],bars,f)
            label='查詢盤面' if method=='Q' else LABELS[method]+' 第一名'
            axes[row,col].set_title(label+('｜5分60根' if iv=='5m' else '｜1h20根'),loc='left',fontsize=12,fontweight='bold')
        text=f"{EVENTS[f['event']]}｜末段 {f['tail_direction']}"
        if m:text+=f"｜5分 {m['d5']:.3f}、1h {m['d1h']:.3f}、末段 {m['dtail']:.3f} 百分點｜波動 {m['vol_ratio']:.2f}倍"
        axes[row,0].text(0,-.24,text,transform=axes[row,0].transAxes,fontsize=9,color='#42576a')
        if m:axes[row,1].text(0,-.24,f"案例 {m['case_id']}｜參考 {tw(p['as_of'])}",transform=axes[row,1].transAxes,fontsize=9,color='#42576a')
    fig.suptitle(f"{r['query_id']}｜{tw(r['as_of'])} 台灣｜{r['side']}：同一盤面比較 A／B",fontsize=19,y=.97,fontweight='bold')
    fig.text(.075,.916,'每欄共用縱軸，各圖首收盤歸零。5分陰影：最近6根；虛線：這6根之前的固定20棒高低。',fontsize=11,color='#42576a')
    fig.text(.075,.052,'A依原版排名；B中檔為未校準試驗條件，可少於五筆或為空。U／D／N＝末段上／下／中性。\n歷史為PROJECT_REFERENCE，原時鐘UNKNOWN。此為既有券商歷史盤面回看，沒有新即時抓取或人工準確率。',fontsize=10,color='#536b7c',linespacing=1.6)
    pdf.savefig(fig)
    fig.savefig(out/(r['query_id']+'_AB_K線.png'),dpi=300)
    plt.close(fig)


def overview(records,profiles,out):
    fig,axes=plt.subplots(10,2,figsize=(14,22))
    fig.subplots_adjust(left=.075,right=.98,top=.925,bottom=.055,hspace=1.05,wspace=.21)
    for i,r in enumerate(records):
        q=profiles['queries'][r['query_id']]
        for col,iv in enumerate(('5m','1h')):
            ax=axes[i,col];ax.plot(path(q['pre_entry_bars'][iv]),color=COLORS['Q'],label='查詢',lw=1.4)
            for method in ('A','B_medium'):
                rows=r['methods'][method]['rows']
                if rows:
                    p=profiles['cases'][rows[0]['case_id']]
                    ax.plot(path(p['pre_entry_bars'][iv]),color=COLORS[method],label=LABELS[method],lw=1.2,
                            ls='--' if method=='B_medium' else '-')
            if not r['methods']['B_medium']['rows']:ax.text(.98,.08,'B中：無通過',ha='right',transform=ax.transAxes,fontsize=8,color='#8064a2')
            ax.set_title(f"{r['query_id']} {tw(r['as_of'])[:10]} {r['side']}｜{'5分' if col==0 else '1h'}",loc='left',fontsize=10)
            ax.axhline(0,color='#aab4bd',lw=.5);ax.grid(alpha=.15);ax.tick_params(labelsize=8)
            if i==0 and col==0:ax.legend(fontsize=8,ncol=3)
    fig.suptitle('相同10個不同日期：查詢、A第一名與B中檔第一名',fontsize=18,y=.98,fontweight='bold')
    fig.text(.075,.947,'藍：查詢　金：A　紫虛線：B｜相對首棒百分比，無個別拉伸振幅；B空白不補案例',fontsize=11)
    fig.text(.075,.017,'所有日期與第一名照實呈現。中檔門檻尚未校準；線圖／條件符合不等於人工相似準確率。',fontsize=10,color='#536b7c')
    save(fig,out,'十日_AB走勢總覽')


def diagnostic(summary,records,out):
    methods=['A','B_paths','B_tail','B_vol','B_strict','B_medium','B_loose']
    fig,axes=plt.subplots(1,2,figsize=(14,6))
    fig.subplots_adjust(left=.065,right=.98,top=.78,bottom=.26,wspace=.23)
    for ax,(cohort,label) in zip(axes,[('broker_10_days','10個不同週券商盤面'),('monthly_2021_2025','41個歷史月份查詢')]):
        data=summary['cohorts'][cohort]['methods'];n=data['A']['queries']
        vals=[data[m]['queries_with_output'] for m in methods]
        bars=ax.bar(range(len(methods)),vals,color=['#c58328','#b3c1d1','#9eacc4','#899bc0','#c5b4d3','#8064a2','#a593bb'])
        for b,v in zip(bars,vals):ax.text(b.get_x()+b.get_width()/2,v+.3,str(v),ha='center',fontsize=10)
        ax.set_xticks(range(len(methods)),[LABELS[m] for m in methods],rotation=35,ha='right',fontsize=10)
        ax.set_ylim(0,n*1.14);ax.set_title(label,loc='left',fontweight='bold');ax.set_ylabel('至少返回一例的查詢數')
        ax.axhline(n,color='#8796a4',ls=':',lw=1);ax.grid(axis='y',alpha=.13);ax.set_axisbelow(True)
    fig.suptitle('方法與容忍設定的覆蓋取捨',fontsize=19,y=.95,fontweight='bold')
    fig.text(.065,.85,'B前三項為中檔逐步加條件；嚴／中／寬為完整B的敏感度。返回較少不代表較準。',fontsize=11)
    fig.text(.065,.045,'全部51個查詢固定先選；不是新盲測。嚴中寬參數執行前固定，未用結果重調。',fontsize=10,color='#536b7c')
    save(fig,out,'Figure_1_覆蓋與條件消融')
    fig,axes=plt.subplots(2,2,figsize=(12,10))
    fig.subplots_adjust(left=.085,right=.98,top=.86,bottom=.10,wspace=.28,hspace=.38)
    for ax,key,title in zip(axes.flat,['d5','d1h','dtail','vol_ratio'],['5分完整路徑差（百分點）','1h完整路徑差（百分點）','最近6根路徑差（百分點）','ATR%波動倍率（1為相同）']):
        values=[]
        for cohort,color,label in [('monthly_2021_2025','#a8b3c0','歷史月份'),('broker_10_days','#243f70','券商不同週')]:
            pairs=[(r['methods']['A']['rows'][0][key],r['methods']['B_medium']['rows'][0][key])
                   for r in records if r['cohort']==cohort and r['methods']['B_medium']['rows']]
            if pairs:
                x,y=zip(*pairs);ax.scatter(x,y,c=color,s=28,label=label,alpha=.9);values+=list(x)+list(y)
        hi=max(values)*1.1;lo=1 if key=='vol_ratio' else 0
        ax.plot([lo,hi],[lo,hi],ls=':',color='#536b7c',lw=1);ax.set_xlim(lo,hi);ax.set_ylim(lo,hi)
        ax.set_title(title,loc='left',fontsize=11,fontweight='bold');ax.set_xlabel('A第一名');ax.set_ylabel('B中檔第一名');ax.grid(alpha=.15)
    axes[0,0].legend(fontsize=9)
    fig.suptitle('只比A／B都有輸出的相同查詢：點在對角線下方代表B差距較小',fontsize=15,y=.96,fontweight='bold')
    common_count=sum(bool(r['methods']['B_medium']['rows']) for r in records)
    fig.text(.085,.035,f'比較{common_count}個共同查詢，拒絕的{len(records)-common_count}個未混入平均；數值軸是檢索條件，不是獨立人工準確率。',fontsize=10,color='#536b7c')
    save(fig,out,'Figure_2_共同查詢差距')


def write_report(records,summary,out):
    lines=['# A／B相似判斷實測結果','',
           'A＝上一版雙路徑＋末棒前高低狀態優先；B＝目前事件階段＋末段＋雙路徑＋波動容忍。',
           '同池51查詢，既有資料離線重跑；未替換網站，沒有呼叫API／LLM或新人工標註。B參數未校準。','',
           '## 覆蓋與敏感度','',
           '| 方法 | 券商10日：有輸出／10 | 券商10日：五筆齊全 | 歷史月份：有輸出／41 | 歷史月份：五筆齊全 |',
           '|---|---:|---:|---:|---:|']
    for m in ['A','B_paths','B_tail','B_vol','B_strict','B_medium','B_loose']:
        a=summary['cohorts']['broker_10_days']['methods'][m];b=summary['cohorts']['monthly_2021_2025']['methods'][m]
        lines.append(f"| {LABELS[m]} | {a['queries_with_output']} | {a['full_five_queries']} | {b['queries_with_output']} | {b['full_five_queries']} |")
    lines+=['','B嚴檔在10個券商日期全拒絕，不能稱優秀或100%精確；中檔回7日，寬檔回9日。這證明界線強烈影響可用性，尚不能指定為正式值。',
            '', '## 公平比較：A與B中都有輸出的相同查詢','',
            '| 批次／方法 | 同查詢數 | 5分完整差↓ | 1h完整差↓ | 末段差↓ | 波動倍率↓ | 事件階段同 | 末段相反 |',
            '|---|---:|---:|---:|---:|---:|---:|---:|']
    for cohort,label in [('broker_10_days','券商不同週'),('monthly_2021_2025','歷史月份')]:
        for m in ('A','B_medium'):
            d=summary['cohorts'][cohort]['common_subset'][m]
            lines.append(f"| {label}／{LABELS[m]} | {d['queries']} | {d['mean_top1_d5']:.4f} | {d['mean_top1_d1h']:.4f} | {d['mean_top1_dtail']:.4f} | {d['mean_top1_vol_ratio']:.3f} | {d['event_match_top1']} | {d['opposed_tail_top1']} |")
    lines+=['','B在共同查詢的末段與波動差較小，事件階段一致且無U/D對立；這些正是它的規則，不能拿來當獨立準確率。它的完整5分與1h路徑反而平均較遠，沒有全面勝出。',
            '', '## 10個券商日期逐案','',
            '| 編號／台灣日期 | 查詢階段 | A第一名：階段／末段 | B中檔：筆數／第一名 | B寬檔筆數 |',
            '|---|---|---|---|---:|']
    for r in records:
        if r['cohort']!='broker_10_days':continue
        a=r['methods']['A']['rows'][0];b=r['methods']['B_medium']['rows']
        btext=f"{len(b)}／{b[0]['case_id']}" if b else '0／無通過'
        lines.append(f"| {r['query_id']} {tw(r['as_of'])[:10]} | {EVENTS[r['query_features']['event']]} | {EVENTS[a['case_event']]}／{a['case_tail']} | {btext} | {len(r['methods']['B_loose']['rows'])} |")
    lines+=['','## 結果怎麼解讀','',
            '- A適合始終提供「相對最近的參考」，整段走勢往往更貼，但可能此刻階段／末段相反。',
            '- B更符合「同階段才可稱相似」的產品語意，也能合理回空；目前明示門檻只是試驗，嚴檔過度拒絕。',
            '- 建議採B的判斷方向作下一版驗證，先保留A作參考／對照；不直接宣稱B更準或用本輪圖事後把門檻調到全回。',
            '- 先看D02／D04／D06的空結果，以及D01／D05／D10被更換第一名的圖；全部十日都保留，沒有只挑漂亮圖。',
            '- 可用pair_review.csv記錄人工的可比／不可比／不足與理由，方法與盈虧可遮蔽；目前評分空白，沒有填造正確率。',
            '', '## 檔案','',
            '- `十日_AB六格K線對照.pdf`：每頁查詢／A／B中，兩週期共六格；B空結果不補。',
            '- `十日_AB走勢總覽.png/pdf`：十日路徑疊圖。',
            '- `Figure_1_覆蓋與條件消融.png/pdf`、`Figure_2_共同查詢差距.png/pdf`。',
            '- `comparison.csv`：51查詢×7設定第一名與輸出數；`queries_PRIVATE.json`保留前五／拒絕原因。',
            '- `manifest_PRIVATE.json`與`validation.json`：規則、輸入hash、A舊前五一致及時間／去重檢查。',
            '', '## 限制','',
            '兩批都是既有實驗資料，不是新留出盲測。完整歷史參考池不代表所有行情。第一名平均差與規則符合不是相似準確率，也不是獲利能力。歷史PROJECT_REFERENCE及原始時鐘UNKNOWN保留；未新增下載、委託、訓練或公開發布。',
            '',f"結果SHA256：`{summary['result_digest']}`。"]
    (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=OUTPUT)
    out=parser.parse_args().output.resolve()
    if not out.is_relative_to((PRODUCT/'private').resolve()):raise ValueError('PRIVATE_OUTPUT_REQUIRED')
    configure()
    records=json.loads((out/'queries_PRIVATE.json').read_text(encoding='utf-8'))
    profiles=json.loads((out/'plot_profiles_PRIVATE.json').read_text(encoding='utf-8'))
    summary=json.loads((out/'summary.json').read_text(encoding='utf-8'))
    assert sha256((out/'queries_PRIVATE.json').read_bytes()).hexdigest()==summary['result_digest']
    manifest=json.loads((out/'manifest_PRIVATE.json').read_text(encoding='utf-8'))
    for p,h in manifest['inputs'].items():assert sha256((PRODUCT/p).read_bytes()).hexdigest()==h,p
    days=[r for r in records if r['cohort']=='broker_10_days']
    with PdfPages(out/'十日_AB六格K線對照.pdf') as pdf:
        for r in days:page(r,profiles,pdf,out)
    overview(days,profiles,out);diagnostic(summary,records,out);write_report(records,summary,out)
    write_review_template(records,out/'pair_review.csv')
    dump=dict(renderer_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
              shared_candle_renderer_sha256=sha256((PRODUCT/'research/render_live_dual_samples.py').read_bytes()).hexdigest(),
              result_digest=summary['result_digest'],candle_pages=10,dpi=300)
    (out/'figure_manifest_PRIVATE.json').write_text(json.dumps(dump,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print('Rendered: 10 six-panel pages, all-day overview, coverage and common-query diagnostics.',flush=True)


if __name__=='__main__':main()
