"""Candle pairs for fixed, nonoverlapping broker historical days."""
import json
from hashlib import sha256
from pathlib import Path
import sys
from collections import Counter

PRODUCT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PRODUCT))
from research.distinct_day_samples import OUTPUT,tw
from research.render_live_dual_samples import candle,path
from research.render_similarity_comparison import configure
from backend.compact_market import STRUCTURES
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


def page(r,pdf):
    first=r['result']['cases'][0];d=r['query_description'];other=r['matched_description']
    fig,axes=plt.subplots(2,2,figsize=(15,10),sharey='col')
    fig.subplots_adjust(left=.08,right=.98,top=.79,bottom=.17,wspace=.16,hspace=.4)
    for row,(label,p) in enumerate([('指定日期券商盤面',r['profile']),('檢索第一名歷史案例',r['matched_profile'])]):
        for col,iv in enumerate(('5m','1h')):
            candle(axes[row,col],p['pre_entry_bars'][iv],levels=col==0)
            axes[row,col].set_title(label+('｜五分鐘60根' if col==0 else '｜一小時20根'),loc='left',fontsize=13,fontweight='bold')
    fig.suptitle(f"{r['sample']}｜{tw(r['as_of'])} 台灣時間｜測試方向 {r['side']}",fontsize=19,y=.97,fontweight='bold')
    fig.text(.08,.90,f"查詢：{STRUCTURES[d['structure']]}　→　歷史：{STRUCTURES[other['structure']]}　｜　{'狀態相同' if first['structure_match'] else '狀態不同'}",fontsize=12,color='#173247')
    fig.text(.08,.855,f"五分路徑差 {first['path_distance_pct']:.3f} 百分點　｜　一小時差 {first['hour_path_distance_pct']:.3f} 百分點　｜　ATR%倍率差 {first['volatility_ratio']:.2f} 倍",fontsize=12,color='#415363')
    fig.text(.08,.105,f"歷史 {first['id']}｜參考時點 {tw(other['as_of'])}（來源時間模型，原時鐘未核實）",fontsize=10,color='#536b7c')
    fig.text(.08,.045,'十個查詢取自不同週，5分與1h完整窗口互不重疊。原生券商歷史K線回看，不是當時逐次即時擷取。\n同欄共用縱軸，各自首根收盤歸零。虛線為末棒前20棒高低；前五為相對最近參考，未校準相似門檻。',fontsize=10,color='#536b7c',linespacing=1.6)
    fig.savefig(OUTPUT/f"{r['sample']}_不同日對照.png",dpi=300)
    fig.savefig(OUTPUT/f"{r['sample']}_不同日對照.pdf");pdf.savefig(fig);plt.close(fig)


def overview(payload):
    fig,axes=plt.subplots(10,2,figsize=(13.5,21))
    fig.subplots_adjust(left=.075,right=.98,top=.925,bottom=.065,hspace=1.1,wspace=.2)
    for row,r in enumerate(payload['records']):
        c=r['result']['cases'][0]
        for col,iv in enumerate(('5m','1h')):
            ax=axes[row,col]
            ax.plot(path(r['profile']['pre_entry_bars'][iv]),color='#243f70',lw=1.4,label='指定日盤面')
            ax.plot(path(r['matched_profile']['pre_entry_bars'][iv]),color='#c58328',lw=1.3,label='歷史第一名')
            metric=c['path_distance_pct'] if iv=='5m' else c['hour_path_distance_pct']
            ax.set_title(f"{r['sample']} {tw(r['as_of'])[:10]} {r['side']}｜{'5分' if col==0 else '1h'} 差 {metric:.3f} 百分點",loc='left',fontsize=10)
            ax.axhline(0,color='#9baab7',lw=.6);ax.grid(alpha=.14);ax.tick_params(labelsize=8)
            if row==0 and col==0:ax.legend(fontsize=8,ncol=2,loc='best')
    fig.suptitle('10個不同日期盤面 × 同一新方法的歷史第一名',fontsize=20,y=.98,fontweight='bold')
    fig.text(.075,.945,'藍：指定日期　金：歷史第一名｜左5分60根、右1h20根｜每週二23:00，窗口完全分開',fontsize=11,color='#536b7c')
    fig.text(.075,.018,'日期2026/08/11–10/20；9/8因1h缺棒排除，向前補8/11，未依檢索好壞挑日期。BUY／SELL各5次為固定輸入。\n資料為新取得的券商歷史K線，未改檢索規則；不同日期仍不代表統計獨立或準確率。',fontsize=11,color='#536b7c',linespacing=1.7)
    fig.savefig(OUTPUT/'不同日期_十組走勢總覽.png',dpi=300);fig.savefig(OUTPUT/'不同日期_十組走勢總覽.pdf');plt.close(fig)


def report(payload,summary):
    rows=['# 十個不同日期：雙週期路徑＋前高低狀態實測','',
        f"方法 `{payload['method']}` 不變；cTrader DEMO XAUUSD原生歷史棒，取得時間UTC `{payload['fetched_at_utc']}`。不使用合成K線，不冒充當時即時擷取。",
        '從最近10週每週二台灣23:00開始。9/8的1h背景有現有每週時段表無法解釋的3小時缺棒，保留原因並往前加8/11，11個固定候選日先以資料完整性決定10天，再排名；不是看檢索表現挑圖。此為目視試驗，不是新留出準確率。','',
        '| 編號 | 查詢日期（台灣23:00） | 方向 | 第一名歷史參考日 | 狀態同 | 5分差↓ | 1h差↓ | 波動倍率 |',
        '|---|---|---|---|---|---:|---:|---:|']
    for r in payload['records']:
        c=r['result']['cases'][0]
        rows.append(f"| {r['sample']} | {tw(r['as_of'])[:10]} | {r['side']} | {tw(r['matched_description']['as_of'])} | {c['structure_match']} | {c['path_distance_pct']:.3f} | {c['hour_path_distance_pct']:.3f} | {c['volatility_ratio']:.2f} |")
    rows+=['',f"10個日期的5分與1h窗口均互不重疊，兩種週期各10個不同收盤路徑。第一名共{summary['distinct_top_one_cases']}筆不同案例；同狀態{summary['same_structure_top_one']}/10（排序優先條件，不是準確率）。",
        f"平均5分／1h路徑RMSE {summary['mean_five_path_distance']:.3f}／{summary['mean_hour_path_distance']:.3f}百分點，平均ATR%倍率{summary['mean_volatility_ratio']:.2f}。波動倍率1代表相同，但未用於排名。",
        f"查詢結構狀態：{dict(Counter(STRUCTURES[r['query_description']['structure']] for r in payload['records']))}。",
        '', '## 檢查與重跑','',
        '- 50個前五配對方向／成熟時間／完整窗口／群與參考時點去重均通過；10次前五與凍結的離線NumPy算法逐次一致，距離誤差<1e-10。',
        '- 十頁PDF每頁四格K線，同欄共用尺度；總覽為逐根收盤路徑疊圖。所有第一名照實保留，不手動替換。',
        '- 點位時鐘UNKNOWN／PROJECT_REFERENCE保留；未建立或確認委託、未呼叫LLM或更新公開站。',
        '- `comparison.csv`記錄各天案例ID、參考時點與距離；JSON保留前五與查詢／第一名OHLC。`manifest_PRIVATE.json`保留輸入雜湊，`validation.json`保留50配對條件。',
        f"- 結果SHA256 `{summary['result_digest']}`。",'', '## 排除日期','']
    rows.extend(f"- {tw(r['as_of'])}：{r['reason']}。" for r in payload['excluded_query_days'])
    (OUTPUT/'report.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')


def main():
    configure()
    manifest=json.loads((OUTPUT/'manifest_PRIVATE.json').read_text(encoding='utf-8'))
    assert all(sha256((PRODUCT/n).read_bytes()).hexdigest()==h for n,h in manifest['inputs'].items())
    assert sha256((OUTPUT/'samples_PRIVATE.json').read_bytes()).hexdigest()==manifest['result_digest']
    payload=json.loads((OUTPUT/'samples_PRIVATE.json').read_text(encoding='utf-8'));summary=json.loads((OUTPUT/'summary.json').read_text(encoding='utf-8'))
    with PdfPages(OUTPUT/'不同日期_十組K線對照.pdf') as pdf:
        for r in payload['records']:page(r,pdf)
    overview(payload);report(payload,summary)
    (OUTPUT/'figure_manifest_PRIVATE.json').write_text(json.dumps(dict(renderer_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),shared_candle_renderer_sha256=sha256((PRODUCT/'research/render_live_dual_samples.py').read_bytes()).hexdigest(),pages=10,result_digest=manifest['result_digest']),indent=2),encoding='utf-8')
    print('rendered ten different-day candle pages and overlay overview')


if __name__=='__main__':main()
