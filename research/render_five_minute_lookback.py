"""Figures for short-detail versus long-context five-minute retrieval."""
from __future__ import annotations
import csv
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle
import numpy as np

PRODUCT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PRODUCT))
from research.five_minute_lookback import OUTPUT,METHODS,LABELS
from research.render_similarity_comparison import configure

COLORS=['#c58328','#4785ba','#926db0','#168b8b','#243f70']
SHORT=['5分60根＋高低','5分120根＋高低','5分240根＋高低','5分三個長度分窗＋高低','5分60＋1h20對照＋高低']


def save(fig,name,pdf):
    fig.savefig(OUTPUT/(name+'.png'),dpi=300,bbox_inches='tight')
    fig.savefig(OUTPUT/(name+'.pdf'),bbox_inches='tight')
    pdf.savefig(fig,bbox_inches='tight');plt.close(fig)


def overview(summary,pdf):
    stats=summary['methods'];fig,axes=plt.subplots(2,2,figsize=(15,10))
    fig.subplots_adjust(left=.19,right=.97,top=.86,bottom=.16,wspace=.54,hspace=.4)
    fields=[('path_5m_rmse_pct','最近60根：進場附近細節','RMSE百分點 ↓'),
            ('path_120_rmse_pct','最近120根：中段走勢','RMSE百分點 ↓'),
            ('path_240_rmse_pct','最近240根：長段背景','RMSE百分點 ↓'),
            ('volatility_ratio','波動幅度差','ATR%較大／較小；1＝相同 ↓')]
    for ax,(key,title,unit) in zip(axes.flat,fields):
        values=[stats[m][key] for m in METHODS]
        ax.barh(range(5),values,color=COLORS,height=.62)
        ax.set_yticks(range(5),SHORT,fontsize=10);ax.invert_yaxis()
        ax.set_title(title,loc='left',fontsize=13,pad=10,fontweight='bold')
        ax.set_xlabel(unit,fontsize=10);ax.set_xlim(0,max(values)*1.2)
        for i,v in enumerate(values):ax.text(v+max(values)*.025,i,f'{v:.3f}',va='center',fontsize=10)
        ax.grid(axis='x',alpha=.18);ax.set_axisbelow(True)
        if key=='volatility_ratio':ax.axvline(1,color='#647382',ls=':',lw=1)
    fig.suptitle('只用五分鐘K線：看更多根，會找得更像嗎？',x=.045,ha='left',fontsize=20,fontweight='bold',y=.97)
    fig.text(.045,.915,'同一批41個月份查詢、每法205配對｜各法同池、同方向／成熟／去重規則，皆將前高低狀態相同者提前',fontsize=11,color='#415363')
    fig.text(.045,.065,'看更多根能補背景，但整段距離可能掩蓋最近的細節；三個長度分開比可減輕這個問題。\n60／120／240根約5／10／20個交易小時；休市會拉長實際時間。這是數值診斷，並非人工相似度準確率。',fontsize=11,color='#415363',linespacing=1.7)
    save(fig,'五分K長度比較',pdf)


def tradeoff(summary,pdf):
    stats=summary['methods'];fig,ax=plt.subplots(figsize=(11,7.5))
    fig.subplots_adjust(left=.12,right=.94,top=.83,bottom=.19)
    offsets=[(15,10),(15,12),(-140,-30),(20,-5),(-115,15)]
    for i,m in enumerate(METHODS):
        x,y=stats[m]['path_5m_rmse_pct'],stats[m]['path_240_rmse_pct']
        ax.scatter(x,y,s=100,color=COLORS[i],marker=['o','s','D','^','P'][i],zorder=3)
        ax.annotate(SHORT[i],(x,y),textcoords='offset points',xytext=offsets[i],color=COLORS[i],fontsize=10,
                    arrowprops={'arrowstyle':'-','color':COLORS[i]})
    ax.set_xlim(.095,.31);ax.set_ylim(.24,.72);ax.grid(alpha=.2)
    ax.set_xlabel('最近60根路徑差（百分點）↓');ax.set_ylabel('最近240根路徑差（百分點）↓')
    fig.suptitle('短線細節與長段背景：兩邊都要看',fontsize=18,y=.96)
    fig.text(.12,.88,'越靠左下，短段與長段的逐棒差距越小；不把兩者合成一個「準確率」',fontsize=11)
    fig.text(.12,.06,'只比240根讓背景更像，最近60根卻可能變遠；分窗比較保留兩種尺度。\n同一種5分資料可以看長短背景，但更多根並不自動代表更準。',fontsize=11,linespacing=1.7)
    save(fig,'短線與背景取捨',pdf)


def candles(ax,bars,*,long):
    base=float(bars[0]['close']);pct=lambda v:(float(v)/base-1)*100
    if long:
        ax.axvspan(119.5,239.5,color='#4785ba',alpha=.045)
        ax.axvspan(179.5,239.5,color='#c58328',alpha=.065)
        ax.axvline(119.5,color='#4785ba',ls='--',lw=.8)
        ax.axvline(179.5,color='#c58328',ls='--',lw=.8)
    for i,b in enumerate(bars):
        op,hi,lo,cl=[pct(b[k]) for k in ('open','high','low','close')]
        color='#168b8b' if cl>=op else '#c58328'
        ax.vlines(i,lo,hi,color=color,lw=.55 if long else .8)
        ax.add_patch(Rectangle((i-.3,min(op,cl)),.6,max(abs(cl-op),.001),color=color,lw=.2))
    ax.axhline(0,color='#a6b2bd',lw=.5);ax.grid(axis='y',alpha=.15)
    ax.set_xlim(-1,len(bars));ax.set_ylabel('相對首根收盤 (%)',fontsize=8)
    ax.set_xticks([0,119,179,239] if long else [0,29,59],
                  ['-239棒','最近120起點','最近60起點','最後已收棒'] if long else ['-59棒','-30棒','最後已收棒'])
    ax.tick_params(labelsize=8)


def example_charts(examples,pdf):
    for x in examples:
        r=x['record'];raw=x['bars']
        items=[('查詢盤面',r['case_id'],None)]+[(SHORT[i]+'：第一名',r['methods'][m][0]['case_id'],r['methods'][m][0]) for i,m in enumerate(METHODS)]
        fig,axes=plt.subplots(6,2,figsize=(16,18),sharey='col',gridspec_kw={'width_ratios':[1.5,1]})
        fig.subplots_adjust(left=.07,right=.98,top=.9,bottom=.08,hspace=.75,wspace=.18)
        for row,(label,cid,p) in enumerate(items):
            bars=raw[cid]
            for col,window in enumerate((bars,bars[-60:])):
                candles(axes[row,col],window,long=col==0)
                title=label+('｜240根背景' if col==0 else '｜最近60根細節')
                if p:title+=f"\n路徑差 {p['path_240_rmse_pct' if col==0 else 'path_5m_rmse_pct']:.3f} 百分點"
                axes[row,col].set_title(title,loc='left',fontsize=10,pad=9)
        fig.suptitle(f"固定{r['year']}年第一個成功查詢：同一張5分圖看長短範圍",fontsize=18,y=.98)
        fig.text(.07,.945,f"{r['month']}／{r['side']}｜每法第一名，不按改善最多挑圖｜同欄共用尺度；每個窗各自首棒歸零",fontsize=11)
        fig.text(.07,.025,'左圖皆為240根5分K；藍／金虛線標最近120／60根起點。右圖將最近60根獨立放大比較。\n所有方法皆使用相同前高低狀態優先條件；圖中不顯示交易結果。控制組才把1h路徑放進排名。',fontsize=11,linespacing=1.6)
        save(fig,f'五分K案例_{r["year"]}',pdf)


def report(summary,records):
    stats=summary['methods'];a=stats['five60'];b=stats['five240'];nested=stats['five_nested'];control=stats['dual_structure']
    lines=['# 只用五分鐘K線與增加觀察根數：結果','',
           '可以從同一批五分鐘資料看長短背景；不需要把15分K當作獨立新增資訊。但只把60根改為240根，會犧牲最近的細節，應分開看不同長度。這輪方法仍為離線試驗，網站未切換。','',
           '## 主對照：相同41查詢／相同池','',
           '各方法均將末棒對先前20棒高低狀態相同者優先；取同方向、已成熟、不同群、最長參考窗不重疊的完整240根與1h資料交集，去群／時點後取五。各法205配對。這次控制組在相同池重算，未直接混用舊均值。','',
           '| 方法 | 最近60根差↓ | 最近120根差↓ | 最近240根差↓ | 1h差（診斷）↓ | ATR%倍率↓ |',
           '|---|---:|---:|---:|---:|---:|']
    for m in METHODS:
        s=stats[m]
        lines.append(f"| {LABELS[m]} | {s['path_5m_rmse_pct']:.3f} | {s['path_120_rmse_pct']:.3f} | {s['path_240_rmse_pct']:.3f} | {s['path_1h_rmse_pct']:.3f} | {s['volatility_ratio']:.2f} |")
    lines+=['','路徑差單位為百分點；在同一個觀察長度內跨方法比較，不把60根和240根數字大小直接當優劣。1h只在控制組排名，其他四法僅使用5分資料。ATR%倍率取較大／較小，1為相同。',
            '', '## 看到了什麼','',
            f"- 只從60改240：長段差 {a['path_240_rmse_pct']:.3f}→{b['path_240_rmse_pct']:.3f}，但最近60根差 {a['path_5m_rmse_pct']:.3f}→{b['path_5m_rmse_pct']:.3f}，增至 {b['path_5m_rmse_pct']/a['path_5m_rmse_pct']:.2f}倍。更多背景沒有自動帶來更好的進場附近形狀。",
            f"- 三窗分開比較：最近60根 {nested['path_5m_rmse_pct']:.3f}、240根 {nested['path_240_rmse_pct']:.3f}。相對只比240根，短段差減少 {1-nested['path_5m_rmse_pct']/b['path_5m_rmse_pct']:.1%}，但長段差增加 {nested['path_240_rmse_pct']/b['path_240_rmse_pct']-1:.1%}；是折衷，並非全勝。",
            f"- 與原雙週期控制比較：三窗5分的長段240根較近（{nested['path_240_rmse_pct']:.3f} 對 {control['path_240_rmse_pct']:.3f}），但最近60根較遠（{nested['path_5m_rmse_pct']:.3f} 對 {control['path_5m_rmse_pct']:.3f}）、1h也較遠（{nested['path_1h_rmse_pct']:.3f} 對 {control['path_1h_rmse_pct']:.3f}）。不能宣稱5分單一來源已全面勝過雙週期。",
            '- 建議若要簡化為只讀5分資料，採「同一張圖分長短窗」方向；暫不直接改成整段240根單一距離。60／120／240是這次固定先導設定，不是已選出的最佳根數。',
            '- 三窗視為同等重要、結構優先也是方法假設。重疊窗口並非三份獨立證據；此版本不新增技術指標、不訓練模型，也沒有以獲利反推參數。',
            '', '## 全部現有可用盤面的覆蓋','',
            '| 原層級 | 60根可用 | 120根可用 | 240根可用 |','|---|---:|---:|---:|']
    for tier,label,total in [('full','完整層',6542),('5m_only','原5分限定層',4345)]:
        c=summary['coverage'][tier]
        lines.append(f"| {label}／{total} | {c['60'].get('READY',0)} | {c['120'].get('READY',0)} | {c['240'].get('READY',0)} |")
    lines+=['',f"共 {summary['all_extended_profiles']} 筆能取完整240根。其餘長窗口有未解釋缺口，沒有補棒或把缺口猜為休市。全部10,887筆的最近60根OHLC皆逐值匹配原盤面；不含原先無可用盤面的1,015筆。",
            '', '## 15分K和5分K的關係','',
            '同源同邊界且完整時，3根5分彙成15分：open取第1根、high取3根最大、low取3根最小、close取第3根。不是把3個close畫成一根就能得到完整OHLC。聚合會省略中間走法；它沒有新增成交資料，但讓趨勢更濃縮。',
            '60根5分看約5小時、60根15分看約15小時，不能只因為同樣60根就當作相同背景範圍。240根5分約20個交易小時，但與20根整點1h仍會有邊界／當前未收小時差異；跨休市實際時間會更長。',
            '', '## 檔案與驗證','',
            '- `五分K長度比較.png/pdf`、`短線與背景取捨.png/pdf`：共用量尺的數值比較。',
            '- `五分K案例_2024.png/pdf`、`五分K案例_2025.png/pdf`：固定各年第一個成功查詢，240根背景與最近60根細節。',
            '- `五分K實驗圖表.pdf`：上述四張；`comparison.csv`可用Excel開；逐查詢、逐案覆蓋及manifest只留本機。',
            f"- {summary['query_denominator']}查詢全部可比較，{summary['checked_pairs']}配對時序、群與參考時點去重檢查通過。結果SHA-256 `{summary['result_digest']}`。",
            '- 所有指標都是與排序輸入相關的數值診斷，沒有新的獨立人工標註；不能當作相似度準確率或策略回測收益。歷史盤面PROJECT_REFERENCE，原時鐘UNKNOWN。',
            '', '```powershell','python -B -X utf8 product/research/five_minute_lookback.py',
            'python -B -X utf8 product/research/render_five_minute_lookback.py','```']
    text='\n'.join(lines)+'\n'
    (OUTPUT/'report.md').write_text(text,encoding='utf-8')
    (PRODUCT/'docs/five_minute_lookback_results_20261020.md').write_text(text,encoding='utf-8')
    keys=['queries','pair_count','path_5m_rmse_pct','path_120_rmse_pct','path_240_rmse_pct','path_1h_rmse_pct','volatility_ratio','structure_agreement']
    with (OUTPUT/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['method','label']+keys);writer.writeheader()
        for m in METHODS:writer.writerow(dict(method=m,label=LABELS[m],**{k:stats[m][k] for k in keys}))


def main():
    configure()
    manifest=json.loads((OUTPUT/'manifest_PRIVATE.json').read_text(encoding='utf-8'))
    for relative,expected in manifest['inputs'].items():
        assert sha256((PRODUCT.parent/relative).read_bytes()).hexdigest()==expected,relative
    summary=json.loads((OUTPUT/'summary.json').read_text(encoding='utf-8'))
    assert sha256((OUTPUT/'queries_PRIVATE.jsonl').read_bytes()).hexdigest()==summary['result_digest']
    records=list(map(json.loads,(OUTPUT/'queries_PRIVATE.jsonl').read_text(encoding='utf-8').splitlines()))
    examples=json.loads((OUTPUT/'examples_PRIVATE.json').read_text(encoding='utf-8'))
    with PdfPages(OUTPUT/'五分K實驗圖表.pdf') as pdf:
        overview(summary,pdf);tradeoff(summary,pdf);example_charts(examples,pdf)
    report(summary,records)
    (OUTPUT/'figure_manifest_PRIVATE.json').write_text(json.dumps(dict(renderer_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        result_digest=summary['result_digest'],examples=[x['record']['case_id'] for x in examples]),sort_keys=True,indent=2),encoding='utf-8')
    print('Rendered four PNG/PDF figures and combined PDF')


if __name__=='__main__':main()
