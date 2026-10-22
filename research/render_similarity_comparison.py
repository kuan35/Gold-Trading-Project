"""Chinese PNG/PDF comparison figures from frozen matched-query outputs."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from statistics import mean
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle
import numpy as np

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PRODUCT))
from research.path_similarity_experiment import OUTPUT, BASE, METHODS, LABELS
from backend.compact_market import STRUCTURES

COLORS = ['#84909e','#168b8b','#c58328','#4785ba','#243f70','#926db0']


def configure():
    font=Path('C:/Windows/Fonts/msjh.ttc')
    if font.exists():
        font_manager.fontManager.addfont(str(font))
        plt.rcParams['font.family']=font_manager.FontProperties(fname=str(font)).get_name()
    plt.rcParams.update({'font.size':11,'axes.unicode_minus':False,'axes.spines.top':False,
                         'axes.spines.right':False,'pdf.fonttype':42,'figure.facecolor':'white'})


def save(figure, name, pdf):
    figure.savefig(OUTPUT/(name+'.png'),dpi=300,bbox_inches='tight')
    figure.savefig(OUTPUT/(name+'.pdf'),bbox_inches='tight')
    pdf.savefig(figure,bbox_inches='tight');plt.close(figure)


def overview(summary, pdf):
    stats=summary['methods']
    figure,axes=plt.subplots(2,2,figsize=(15,10))
    figure.subplots_adjust(left=.18,right=.97,bottom=.16,top=.86,wspace=.53,hspace=.4)
    fields=[('path_5m_rmse_pct','五分鐘走勢差 ↓','RMSE，百分點；越低越接近',1),
            ('path_1h_rmse_pct','一小時走勢差 ↓','RMSE，百分點；越低越接近',1),
            ('structure_agreement','前高低狀態相同 ↑','配對比例；這是排序條件，並非準確率',100),
            ('volatility_ratio','波動倍率差 ↓','兩者 ATR% 較大值／較小值；1＝相同',1)]
    names=[LABELS[m] for m in METHODS]
    for ax,(key,title,xlabel,multiplier) in zip(axes.flat,fields):
        values=[stats[m][key]*multiplier for m in METHODS]
        ax.barh(range(len(METHODS)),values,color=COLORS,height=.64)
        ax.set_yticks(range(len(METHODS)),names,fontsize=10)
        ax.invert_yaxis();ax.set_title(title,loc='left',fontweight='bold',fontsize=13,pad=11)
        ax.set_xlabel(xlabel,fontsize=9,labelpad=9)
        ax.set_xlim(0,max(values)*1.23)
        ax.grid(axis='x',alpha=.18);ax.set_axisbelow(True)
        for i,value in enumerate(values):
            label=f'{value:.1f}%' if multiplier==100 else f'{value:.3f}'
            ax.text(value+max(values)*.025,i,label,va='center',fontsize=10)
        if key=='volatility_ratio':ax.axvline(1,color='#596778',ls=':',lw=1)
    figure.suptitle('歷史案例檢索：六種方法的相同查詢對照',x=.05,ha='left',fontsize=20,fontweight='bold',y=.97)
    figure.text(.05,.915,'2021–2025 固定 41 個月份查詢｜每次前五筆，每法 205 個配對｜同方向、成熟、不同群、窗口不重疊',fontsize=11,color='#415363')
    figure.text(.05,.065,'怎麼讀：完整雙週期補回三段文字遺失的細節；加入高低狀態會犧牲部分路徑距離。\n注意：這些指標與排序輸入重疊，顯示的是數值取捨；尚非人工相似度準確率，也不是交易策略獲利回測。',fontsize=11,color='#415363',linespacing=1.7)
    save(figure,'方法比較總覽',pdf)


def tradeoff(summary,pdf):
    stats=summary['methods'];fig,ax=plt.subplots(figsize=(11,7.5))
    fig.subplots_adjust(left=.12,right=.9,top=.83,bottom=.2)
    offsets=[(15,12),(12,-10),(-45,18),(15,-15),(20,20),(20,-40)]
    for i,m in enumerate(METHODS):
        x,y=stats[m]['path_5m_rmse_pct'],stats[m]['path_1h_rmse_pct']
        ax.scatter(x,y,color=COLORS[i],s=105,zorder=3,marker=['o','s','D','^','P','X'][i])
        ax.annotate(LABELS[m],(x,y),xytext=offsets[i],textcoords='offset points',fontsize=10,
                    arrowprops={'arrowstyle':'-','color':COLORS[i]},color=COLORS[i])
    ax.set_xlim(.085,.285);ax.set_ylim(.245,.715)
    ax.set_xlabel('五分鐘路徑差（百分點）↓');ax.set_ylabel('一小時路徑差（百分點）↓')
    ax.grid(alpha=.2)
    fig.suptitle('兩個週期要一起看：越靠左下，兩邊的逐棒差距越小',fontsize=17,y=.96)
    fig.text(.12,.88,'同一批 41 個查詢、前五平均；不同方法的數值取捨，沒有合併成一個百分比',fontsize=10)
    fig.text(.12,.075,'高低狀態優先法：一小時差距明顯小於原混合法，五分鐘差距接近。\n小幅錯時（DTW）在這批資料的整體改變很小，先保留為實驗選項。',fontsize=11,linespacing=1.7)
    save(fig,'雙週期取捨圖',pdf)


def candle(ax,bars,*,structure):
    base=float(bars[0]['close'])
    value=lambda x:(float(x)/base-1)*100
    for i,b in enumerate(bars):
        op,hi,lo,cl=[value(b[k]) for k in ('open','high','low','close')]
        color='#168b8b' if cl>=op else '#c58328'
        ax.vlines(i,lo,hi,color=color,lw=.8)
        ax.add_patch(Rectangle((i-.29,min(op,cl)),.58,max(abs(cl-op),.001),color=color,lw=.3))
    if structure:
        hi=max(value(b['high']) for b in bars[-21:-1]);lo=min(value(b['low']) for b in bars[-21:-1])
        ax.hlines(hi,len(bars)-21.5,len(bars)-.5,color='#926db0',lw=1,ls='--')
        ax.hlines(lo,len(bars)-21.5,len(bars)-.5,color='#8c7135',lw=1,ls='--')
    ax.axhline(0,color='#9eabb6',lw=.6);ax.grid(axis='y',alpha=.15)
    ax.set_xlim(-1,len(bars));ax.set_xticks([0,len(bars)//2,len(bars)-1],
                 [f'-{len(bars)-1}棒',f'-{len(bars)-1-len(bars)//2}棒','最後已收棒'])
    ax.set_ylabel('相對首根收盤 (%)',fontsize=9);ax.tick_params(labelsize=9)


def examples(records,profiles,descriptions,pdf):
    chosen=[]
    for year in (2024,2025):
        r=next(r for r in records if r['year']==year)
        methods=['existing_hybrid','full','dual_structure','dual_dtw_structure']
        items=[('查詢盤面',r['case_id'],None)]+[(LABELS[m]+'：第一名',r['methods'][m][0]['case_id'],r['methods'][m][0]) for m in methods]
        fig,axes=plt.subplots(len(items),2,figsize=(15,16),sharey='col')
        fig.subplots_adjust(left=.08,right=.98,top=.88,bottom=.09,wspace=.16,hspace=.85)
        for row,(label,cid,metric) in enumerate(items):
            d=descriptions[cid]
            for col,iv in enumerate(('5m','1h')):
                candle(axes[row,col],profiles[cid]['pre_entry_bars'][iv],structure=col==0)
                pattern=d['pattern_5m'] if col==0 else d['pattern_1h']
                title=f"{label}｜{'五分鐘 60 根' if col==0 else '一小時 20 根'}\n三段 {pattern}｜{STRUCTURES[d['structure']] if col==0 else '保留完整20根，逐棒比較'}"
                if metric:
                    key='path_5m_rmse_pct' if col==0 else 'path_1h_rmse_pct'
                    title+=f"\n路徑差 {metric[key]:.3f} 百分點；ATR%倍率 {metric['volatility_ratio']:.2f}"
                axes[row,col].set_title(title,loc='left',fontsize=10,pad=10)
        fig.suptitle(f'同一查詢，不同方法找到了什麼？固定 {year} 年第一個月查詢',fontsize=18,y=.98)
        fig.text(.08,.935,f"查詢 {r['month']}／{r['side']}｜各法第一名｜同欄共用尺度，首根收盤歸零；不以改善最多的查詢挑圖",fontsize=11)
        fig.text(.08,.025,'每列左為五分鐘、右為一小時。紫／棕虛線是末棒之前20棒高／低，沒有用後續棒確認。\nS＝三段內淨變動小，並不等於中間沒有震盪。此處為參考盤面檢索，不含後續損益。',fontsize=11,linespacing=1.6)
        save(fig,f'K線對照_{year}',pdf)
        chosen.append(dict(year=year,query_id=r['case_id'],month=r['month'],
                           candidates={m:r['methods'][m][0]['case_id'] for m in methods}))
    return chosen


def report(summary,records,timings):
    stats=summary['methods'];base=stats['full'];old=stats['existing_hybrid'];dual=stats['dual_structure'];dtw=stats['dual_dtw_structure']
    lines=['# 盤面相似檢索改進：實驗與圖表','',
           '建議先採「完整五分鐘＋一小時路徑，前高低狀態優先」，固定文字保留為解釋。此建議來自數值取捨，尚待獨立圖像判讀；本輪不修改網站預設。',
           '', '## 相同41個月份的結果','',
           '全部方法均為2021–2025既有固定41查詢，每次前五、每法205配對。不是把全庫當作當時已知；只取當下已成熟、同方向、不同群與窗口不重疊的完整盤面。這些年份並非未使用過的獨立測試集。','',
           '| 方法 | 五分路徑差↓ | 一小時路徑差↓ | 高低狀態一致 | ATR%倍率差↓ |',
           '|---|---:|---:|---:|---:|']
    for m in METHODS:
        s=stats[m]
        lines.append(f"| {LABELS[m]} | {s['path_5m_rmse_pct']:.3f} | {s['path_1h_rmse_pct']:.3f} | {s['structure_agreement']:.1%} | {s['volatility_ratio']:.2f} |")
    lines += ['', '路徑差單位＝百分點；ATR%倍率差取兩者較大／較小，1為相同。高低狀態是最後5分棒相對先前20棒的狀態，不代表完整支撐壓力線偵測。',
              '', '## 主要發現與代價','',
              f"- 相對四欄文字基線，雙週期＋高低狀態的五分路徑差降低 {(1-dual['path_5m_rmse_pct']/base['path_5m_rmse_pct']):.1%}、一小時降低 {(1-dual['path_1h_rmse_pct']/base['path_1h_rmse_pct']):.1%}。這是既定距離下降，不是準確率提高同樣百分比。",
              f"- 相對網站原12指標混合法，一小時差降低 {(1-dual['path_1h_rmse_pct']/old['path_1h_rmse_pct']):.1%}；五分 {old['path_5m_rmse_pct']:.6f}→{dual['path_5m_rmse_pct']:.6f}，接近但略增。不能稱所有軸均勝出。",
              f"- 代價：ATR%倍率由文字基線 {base['volatility_ratio']:.2f} 增至 {dual['volatility_ratio']:.2f}；一小時三段字碼吻合也由 {base['hourly_pattern_agreement']:.1%} 降到 {dual['hourly_pattern_agreement']:.1%}。完整路徑距離小，仍可能跨過±1ATR分類界線，因此應將形狀、幅度／波動與文字標籤分開看。",
              '- 高低狀態100%是排序優先條件在此池內足夠所致，不是獨立驗證的100%準確率；稀有狀態或資料較少時仍可能不足五筆。',
              f"- DTW相對不錯時版本：五分 {dual['path_5m_rmse_pct']:.3f}→{dtw['path_5m_rmse_pct']:.3f}、一小時 {dual['path_1h_rmse_pct']:.3f}→{dtw['path_1h_rmse_pct']:.3f}。小幅變形未帶來明顯整體改善，暫不增加預設方法複雜度。"]
    lines += ['', '## 逐查詢與分年，不只看總平均','',
              '| 新方法相對四欄文字基線 | 5分變近／41 | 1小時變近／41 | 兩軸都變近／41 |','|---|---:|---:|---:|']
    for m in METHODS[3:]:
        near5=nearh=both=0
        for r in records:
            a=r['methods'][m];b=r['methods']['full']
            five=mean(p['path_5m_rmse_pct'] for p in a)<mean(p['path_5m_rmse_pct'] for p in b)
            hour=mean(p['path_1h_rmse_pct'] for p in a)<mean(p['path_1h_rmse_pct'] for p in b)
            near5+=five;nearh+=hour;both+=five and hour
        lines.append(f'| {LABELS[m]} | {near5} | {nearh} | {both} |')
    lines += ['', '| 年份 | 查詢 | 四欄文字 5分／1h | 雙週期＋高低 5分／1h |','|---|---:|---:|---:|']
    for year,values in summary['by_year'].items():
        a,b=values['full'],values['dual_structure']
        lines.append(f"| {year} | {a['queries']} | {a['path_5m_rmse_pct']:.3f}／{a['path_1h_rmse_pct']:.3f} | {b['path_5m_rmse_pct']:.3f}／{b['path_1h_rmse_pct']:.3f} |")
    overlap=mean(len({p['case_id'] for p in r['methods']['dual_structure']}&{p['case_id'] for p in r['methods']['dual_dtw_structure']})/5 for r in records)
    lines += ['', f'DTW與固定對位前五重疊平均 {overlap:.1%}。DTW允許索引5分±3／1h±1棒，末點仍固定；不是對帳單時區修正。',
              '', '## 圖表與可重跑檔案','',
              '- `方法比較總覽.png/pdf`：同查詢的路徑、高低、波動四圖。',
              '- `雙週期取捨圖.png/pdf`：越靠左下表示兩個原始對位距離都小。',
              '- `K線對照_2024.png/pdf`、`K線對照_2025.png/pdf`：固定各年第一個月查詢及四種方法第一名；共用縱軸，不挑最佳案例。',
              '- `圖表比較報告.pdf`：以上四張合成一份PDF；`comparison.csv`供Excel；`queries_PRIVATE.jsonl`保存每次前五。',
              '- PNG 300DPI，使用者可依圖檢查。這些是展示效果的圖，不是已完成的人工作答。',
              f"- 全部 {summary['checked_pairs']} 配對檢查時序、群與去重規則通過；結果SHA-256 `{summary['result_digest']}`。",
              '- 本輪未呼叫券商或LLM API，未使用手數、盈虧或出場後資訊排名。歷史盤面PROJECT_REFERENCE、原券商時鐘UNKNOWN。',
              '', '## 下一輪值得測的內容','',
              '先用同一批雙週期圖判斷「方向與高低狀態對，但振幅差一倍是否可比」。若不可比，下一輪單獨加入波動倍率或折返程度，不同時加很多指標；參數須事先固定。先保留DTW為備選。',
              '原始依據與風險見 `product/docs/retrieval_similarity_research_20261020.md`；規格見 `path_similarity_experiment_plan_20261020.md`。',
              '', '```powershell','python -B -X utf8 product/research/path_similarity_experiment.py',
              'python -B -X utf8 product/research/render_similarity_comparison.py','```']
    (OUTPUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    # Generic report is safe locally; data and images remain private by default.
    (PRODUCT/'docs/path_similarity_experiment_results_20261020.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def main():
    configure()
    manifest=json.loads((OUTPUT/'manifest_PRIVATE.json').read_text(encoding='utf-8'))
    for relative,expected in manifest['inputs'].items():
        if sha256((PRODUCT/relative).read_bytes()).hexdigest()!=expected:
            raise RuntimeError('input changed: '+relative)
    summary=json.loads((OUTPUT/'summary.json').read_text(encoding='utf-8'))
    if summary['result_digest']!=sha256((OUTPUT/'queries_PRIVATE.jsonl').read_bytes()).hexdigest():
        raise RuntimeError('query results changed')
    records=list(map(json.loads,(OUTPUT/'queries_PRIVATE.jsonl').read_text(encoding='utf-8').splitlines()))
    profiles=json.loads((PRODUCT/'private/case_candidate_market_profiles.json').read_text(encoding='utf-8'))['profiles']
    descriptions={d['case_id']:d for d in map(json.loads,(BASE/'descriptions_PRIVATE.jsonl').read_text(encoding='utf-8').splitlines())}
    timings=json.loads((OUTPUT/'timings.json').read_text(encoding='utf-8'))
    with PdfPages(OUTPUT/'圖表比較報告.pdf') as pdf:
        overview(summary,pdf);tradeoff(summary,pdf)
        selected=examples(records,profiles,descriptions,pdf)
    report(summary,records,timings)
    (OUTPUT/'figure_manifest_PRIVATE.json').write_text(json.dumps(dict(renderer_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        result_digest=summary['result_digest'],example_selection=selected),ensure_ascii=False,sort_keys=True,indent=2),encoding='utf-8')
    print('Rendered 4 PNG/PDF figures and combined PDF; fixed examples='+str(len(selected)))


if __name__=='__main__': main()
