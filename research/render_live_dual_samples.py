"""Render the ten fixed recent broker queries against their actual top result."""
from __future__ import annotations

from collections import Counter
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
from matplotlib.patches import Rectangle

PRODUCT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PRODUCT))
from research.render_similarity_comparison import configure
from research.sample_live_dual_paths import OUTPUT
from backend.compact_market import STRUCTURES


def taiwan(stamp):return datetime.fromtimestamp(stamp,ZoneInfo('Asia/Taipei')).strftime('%m/%d %H:%M')


def path(bars):
    first=float(bars[0]['close'])
    return [(float(b['close'])/first-1)*100 for b in bars]


def candle(ax,bars,*,levels=False):
    base=float(bars[0]['close']);pct=lambda value:(float(value)/base-1)*100
    for i,b in enumerate(bars):
        op,hi,lo,cl=[pct(b[k]) for k in ('open','high','low','close')]
        color='#168b8b' if cl>=op else '#c58328'
        ax.vlines(i,lo,hi,color=color,lw=.8)
        ax.add_patch(Rectangle((i-.3,min(op,cl)),.6,max(.001,abs(cl-op)),facecolor=color,edgecolor=color,lw=.3))
    if levels:
        hi=max(pct(b['high']) for b in bars[-21:-1]);lo=min(pct(b['low']) for b in bars[-21:-1])
        ax.hlines(hi,len(bars)-21.5,len(bars)-.5,color='#926db0',ls='--',lw=1,label='前20棒高')
        ax.hlines(lo,len(bars)-21.5,len(bars)-.5,color='#92733a',ls='--',lw=1,label='前20棒低')
        ax.legend(loc='lower left',fontsize=8,framealpha=.8)
    ax.axhline(0,color='#9baab7',lw=.6);ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
    ax.set_xlim(-1,len(bars));ax.set_ylabel('相對首根收盤 (%)',fontsize=10)
    ax.set_xticks([0,len(bars)//2,len(bars)-1],[f'-{len(bars)-1}棒',f'-{len(bars)-1-len(bars)//2}棒','最後已收棒'])
    ax.tick_params(labelsize=9)


def sample_page(record,pdf):
    q=record['profile'];h=record['matched_profile'];first=record['result']['cases'][0]
    d=record['query_description'];other=record['matched_description'];name=record['sample']
    fig,axes=plt.subplots(2,2,figsize=(15,10),sharey='col')
    fig.subplots_adjust(left=.08,right=.98,top=.79,bottom=.17,wspace=.16,hspace=.4)
    for row,(label,p,desc) in enumerate([('券商近期盤面',q,d),('第一名歷史案例',h,other)]):
        for col,iv in enumerate(('5m','1h')):
            candle(axes[row,col],p['pre_entry_bars'][iv],levels=col==0)
            axes[row,col].set_title(label+('｜五分鐘60根' if col==0 else '｜一小時20根'),loc='left',fontsize=13,fontweight='bold')
    fig.suptitle(f"{name}｜{taiwan(record['as_of'])} 台灣時間｜測試方向 {record['side']}",fontsize=20,y=.97,fontweight='bold')
    fig.text(.08,.9,f"查詢：{STRUCTURES[d['structure']]}　→　歷史：{STRUCTURES[other['structure']]}　｜　{'狀態相同' if first['structure_match'] else '狀態不同，補充參考'}",fontsize=12,color='#173247')
    fig.text(.08,.855,f"五分路徑差 {first['path_distance_pct']:.3f} 百分點　｜　一小時差 {first['hour_path_distance_pct']:.3f} 百分點　｜　ATR%倍率差 {first['volatility_ratio']:.2f} 倍（1＝相同）",fontsize=12,color='#415363')
    fig.text(.08,.105,f"歷史案例 {first['id']}｜參考時點 {datetime.fromtimestamp(other['as_of'],ZoneInfo('Asia/Taipei')).strftime('%Y-%m-%d %H:%M')}（來源時間模型，原時鐘未核實）",fontsize=10,color='#536b7c')
    fig.text(.08,.045,'每欄共用縱軸，兩邊各自首根收盤歸零；虛線為末棒之前20棒高／低。\n以10/21 00:33取得的券商行情回看最近10個收盤時點，不是當時逐次即時擷取；前五排名未校準足夠相似門檻。',fontsize=10,color='#536b7c',linespacing=1.6)
    fig.savefig(OUTPUT/f'{name}_盤面與第一名.png',dpi=300)
    fig.savefig(OUTPUT/f'{name}_盤面與第一名.pdf')
    pdf.savefig(fig);plt.close(fig)


def contact(payload):
    records=payload['records'];fig,axes=plt.subplots(10,2,figsize=(13.5,21))
    fig.subplots_adjust(left=.075,right=.98,top=.925,bottom=.065,hspace=1.1,wspace=.2)
    for row,r in enumerate(records):
        c=r['result']['cases'][0]
        for col,iv in enumerate(('5m','1h')):
            ax=axes[row,col]
            a=path(r['profile']['pre_entry_bars'][iv]);b=path(r['matched_profile']['pre_entry_bars'][iv])
            ax.plot(a,color='#243f70',lw=1.4,label='查詢盤面')
            ax.plot(b,color='#c58328',lw=1.3,label='歷史第一名')
            ax.axhline(0,color='#b9c3cc',lw=.5);ax.grid(alpha=.14)
            metric=c['path_distance_pct'] if iv=='5m' else c['hour_path_distance_pct']
            ax.set_title(f"{r['sample']} {taiwan(r['as_of'])} {r['side']}｜{'5分' if col==0 else '1h'} 差 {metric:.3f} 百分點",loc='left',fontsize=10)
            ax.tick_params(labelsize=8)
            if row==0 and col==0:ax.legend(fontsize=8,ncol=2,loc='lower left')
    fig.suptitle('最近10個券商盤面 × 新方法找到的第一名歷史案例',fontsize=20,y=.98,fontweight='bold')
    fig.text(.075,.945,'藍線：查詢　金線：第一名｜左5分60根、右1小時20根｜各自首根歸零；同一格共用尺度',fontsize=11,color='#536b7c')
    fig.text(.075,.018,'擷取：台灣時間10/21 00:33；回看10/20 23:45–10/21 00:30。BUY／SELL固定交錯，不是方向預測。\n十個盤面彼此重疊，僅跨兩個一小時背景；結果供目視檢查，不是十個獨立情境或準確率測試。',fontsize=11,color='#536b7c',linespacing=1.7)
    fig.savefig(OUTPUT/'十組路徑總覽.png',dpi=300);fig.savefig(OUTPUT/'十組路徑總覽.pdf');plt.close(fig)


def report(payload,summary):
    rows=['# 新方法：最近10個券商已收盤面與第一名歷史案例','',
          f"方法 `{payload['method']}`；實際擷取UTC時間 `{payload['captured_at_utc']}`（台灣10/21 00:33）。來源 cTrader DEMO，當時連線與報價CURRENT，5分／1h各119根。",
          '使用者選擇從最新取得行情回看最近10個五分鐘收盤時點。Q01–Q10按時間排序，BUY／SELL固定交錯各5，不是系統預測。每個時點嚴格截掉當時未收棒與後續棒；較早時點不聲稱當時即時擷取。',
          '', '| 查詢（台灣） | 方向 | 歷史第一名 | 狀態同？ | 5分差↓ | 1h差↓ | ATR%倍率↓ |',
          '|---|---|---|---|---:|---:|---:|']
    for r in payload['records']:
        c=r['result']['cases'][0]
        rows.append(f"| {r['sample']} {taiwan(r['as_of'])} | {r['side']} | {c['id']} | {'是' if c['structure_match'] else '否'} | {c['path_distance_pct']:.3f} | {c['hour_path_distance_pct']:.3f} | {c['volatility_ratio']:.2f} |")
    states=Counter(r['query_description']['structure'] for r in payload['records'])
    counts=Counter(r['result']['cases'][0]['id'] for r in payload['records'])
    repeated={cid:n for cid,n in counts.items() if n>1}
    rows+=['', '路徑差單位為百分點；ATR%倍率是較大／較小，1為相同。每個Q各有四格K線及當前／歷史的狀態。',
           '', '## 如何看結果','',
           f"- 十次第一名共有 {summary['distinct_top_one_cases']} 筆不同案例，重複 `{repeated}`。重複是原排名結果，未為多樣性更換案例。",
           f"- 查詢高低狀態分布 `{dict(states)}`；第一名狀態同 {summary['same_structure_top_one']}/10，因為狀態優先，不能叫100%準確率。",
           f"- 五分／1h第一名平均差 {summary['mean_five_path_distance']:.3f}／{summary['mean_hour_path_distance']:.3f} 百分點，平均波動倍率 {summary['mean_volatility_ratio']:.2f}；倍率大表示即使路徑接近，局部波動仍不同。",
           f"- 10個查詢只跨 {summary['distinct_hourly_query_windows']} 個已收一小時背景，五分窗口也高度重疊；不是10個獨立行情情境。",
           '- 先看同欄共用尺度的K線，確認轉折、回檔與振幅是否符合你的「可比較」。排名只用收盤路徑與末棒高低狀態，中途影線形狀沒有完整排名。',
           '', '## 檔案','',
           '- `十組盤面與歷史第一名.pdf`：10頁，每頁四格K線。',
           '- `十組路徑總覽.png/pdf`：10組線圖快速比較。',
           '- `Q01_盤面與第一名.png/pdf` 至Q10：各組圖檔。',
           '- `samples_PRIVATE.json`：每時點的已收盤面、前五及第一名歷史盤面；`comparison.csv`供Excel；`broker_snapshot_PRIVATE.json`為已去帳戶與憑證快照。',
           '- `manifest_PRIVATE.json`與`validation.json`：來源／輸入／程式雜湊及時序／離線算法核對。',
           '', '## 驗證與使用界線','',
           '- 50個前五配對時序、成熟、同方向、群／時點去重檢查通過；10次前五與原離線NumPy算法逐次一致，距離誤差小於1e-10。',
           '- 使用同一後端新模組進行抽樣與本機即時檢索；原方法可選，公開Pages與回放不切換。一般對話助手仍不是此即時管線。',
           '- 未呼叫LLM、未建立或確認券商委託、未公開本資料包。歷史時鐘UNKNOWN／PROJECT_REFERENCE，尚無足夠相似門檻或相關性準確率。',
           f"- 結果SHA-256 `{summary['result_digest']}`。"]
    (OUTPUT/'report.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')


def main():
    configure()
    manifest=json.loads((OUTPUT/'manifest_PRIVATE.json').read_text(encoding='utf-8'))
    for relative,expected in manifest['inputs'].items():
        if sha256((PRODUCT/relative).read_bytes()).hexdigest()!=expected:raise RuntimeError('changed input: '+relative)
    if sha256((OUTPUT/'samples_PRIVATE.json').read_bytes()).hexdigest()!=manifest['result_digest']:
        raise RuntimeError('changed samples')
    payload=json.loads((OUTPUT/'samples_PRIVATE.json').read_text(encoding='utf-8'))
    summary=json.loads((OUTPUT/'summary.json').read_text(encoding='utf-8'))
    with PdfPages(OUTPUT/'十組盤面與歷史第一名.pdf') as pdf:
        for record in payload['records']:sample_page(record,pdf)
    contact(payload);report(payload,summary)
    dump=dict(renderer_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),result_digest=manifest['result_digest'],pages=10)
    (OUTPUT/'figure_manifest_PRIVATE.json').write_text(json.dumps(dump,sort_keys=True,indent=2),encoding='utf-8')
    print('Rendered ten 4-panel candle pages and 10-pair path contact sheet')


if __name__=='__main__':main()
