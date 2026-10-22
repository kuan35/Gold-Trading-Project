"""LOCAL ONLY: frozen real broker queries -> unchanged product context rules.

No broker, network, LLM or order calls. Run from any working directory:
python -B -X utf8 product/research/assistant_case_acceptance.py
Use the existing Python environment that has research/requirements.txt installed.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import csv
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

PRODUCT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PRODUCT))
from backend.candidate_sidecar import load_candidate_sidecar
from backend.context_retrieval import ContextIndex, METHOD, THRESHOLDS
from backend.context_rules import market_features
from backend.case_context import build_case_context

FROZEN=PRODUCT/'private/context_similarity_ab_20261021'
OUTPUT=PRODUCT/'private/assistant_case_acceptance_20261022'


def tw(stamp):
    return datetime.fromtimestamp(stamp,ZoneInfo('Asia/Taipei')).strftime('%Y-%m-%d %H:%M')


def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n',encoding='utf8')


def select_real_queries(records):
    """Preserve the whole pre-existing ten-week cohort; never choose by outcome."""
    selected=sorted((r for r in records if r['cohort']=='broker_10_days'),key=lambda r:r['query_id'])
    if len(selected)!=10 or [r['query_id'] for r in selected]!=[f'D{i:02}' for i in range(1,11)]:
        raise ValueError('TEN_FROZEN_BROKER_QUERIES_REQUIRED')
    if len({tw(r['as_of'])[:10] for r in selected})!=10:
        raise ValueError('TEN_DISTINCT_REAL_DATES_REQUIRED')
    return selected


def controlled_probe_queries(query):
    """Artificial variants are separate probes, never counted as real dates."""
    missing=deepcopy(query);missing['pre_entry_bars']['1h']=[]
    uncertain=deepcopy(query)
    boundary=market_features(query)['reference_high']
    last=uncertain['pre_entry_bars']['5m'][-1]
    last['close']=boundary
    last['high']=str(max(Decimal(last['high']),Decimal(boundary)))
    last['low']=str(min(Decimal(last['low']),Decimal(boundary)))
    return dict(missing_hour=missing,uncertain_event=uncertain)


def validate_frozen(result,record):
    expected=record['methods']['B_medium']
    assert [c['id'] for c in result['cases']]==[c['case_id'] for c in expected['rows']],record['query_id']
    assert result['total']==expected['passed_unique']
    assert result['comparison']['rejections']==expected['rejections']
    for actual,old in zip(result['cases'],expected['rows']):
        for new_key,old_key in [('path_distance_pct','d5'),('hour_path_distance_pct','d1h'),
                                ('tail_path_distance_pct','dtail'),('volatility_ratio','vol_ratio')]:
            assert abs(actual[new_key]-old[old_key])<1e-10


def verify_pairs(index,query,result,side):
    # The same accepted descriptions used by eligibility provide conservative windows.
    from backend.compact_market import describe_compact
    qdesc=describe_compact(query,side)
    groups=set();windows=set()
    for item in result['cases']:
        case=index.lookup[item['id']];desc=index.descriptions[item['id']]
        assert case['side']==side and case['available_at']<=query['as_of']
        assert desc['window_end']<=qdesc['window_start']
        assert case['group'] not in groups
        window=(desc['end_5m'],desc['end_1h'])
        assert window not in windows
        assert item['context_check']['passed'] and item['context_check']['score_max']<=1+1e-12
        assert item['reference_alignment']=='PROJECT_REFERENCE' and item['clock_status']=='UNKNOWN'
        groups.add(case['group']);windows.add(window)
    return len(groups)


def checked_context(result,query,side,snapshot_id):
    context=build_case_context(result,{**query,'side':side},snapshot_id=snapshot_id)
    assert context['status']==result['rule_status']
    assert context['side']==side and context['query_as_of_utc']==query['as_of']
    assert [c['case_id'] for c in context['cases']]==[c['id'] for c in result['cases']]
    assert context['counts']['displayed']==len(result['cases'])
    model_facts=json.dumps(context['facts'],ensure_ascii=False)
    for case in result['cases']:
        assert case['id'] not in model_facts
    assert len([f for f in context['facts'] if f['id'].startswith('history.case')])<=2
    # The actual external-model input is only facts; local case_id is for chart linking.
    assert all(set(f)=={'id','text','values'} for f in context['facts'])
    for case in context['cases']:
        assert len(case['metrics'])==4 and all(m['passed'] for m in case['metrics'])
    return context


def render_page(record,query,result,profiles,out):
    import matplotlib.pyplot as plt
    from research.render_live_dual_samples import candle
    from research.render_context_similarity_ab import draw_levels
    first=result['cases'][0] if result['cases'] else None
    other=profiles[first['id']] if first else None
    fig,axes=plt.subplots(2,2,figsize=(15,10),sharey='col')
    fig.subplots_adjust(left=.08,right=.98,top=.80,bottom=.19,wspace=.15,hspace=.44)
    for row,(label,p) in enumerate([('真實券商歷史查詢',query),('通過規則第一名',other)]):
        for col,iv in enumerate(('5m','1h')):
            ax=axes[row,col]
            if p is None:
                ax.text(.5,.5,'沒有通過案例\n保留空格，不補近鄰',transform=ax.transAxes,
                        ha='center',va='center',fontsize=16,color='#78515c')
                ax.set_xticks([]);ax.grid(False)
                continue
            candle(ax,p['pre_entry_bars'][iv],levels=False)
            if iv=='5m':draw_levels(ax,p['pre_entry_bars'][iv],market_features(p))
            ax.set_title(label+('｜5分60根' if iv=='5m' else '｜1h20根'),loc='left',fontsize=13)
    fig.suptitle(f"{record['query_id']}｜{tw(record['as_of'])} 台灣｜{record['side']}",fontsize=20,y=.97)
    comp=result['comparison']
    fig.text(.08,.90,f"{result['rule_status']}｜事件：{comp['query_event_label']}｜末段：{comp['query_tail_direction']}",fontsize=12)
    fig.text(.08,.85,f"可比較 {comp['eligible_rows']} 列｜通過去重 {result['total']} 群｜展示 {len(result['cases'])} 筆；下方僅畫第一名",fontsize=11)
    if first:
        text=(f"案例 {first['id']}｜參考 {tw(other['as_of'])}\n"
              f"5分差 {first['path_distance_pct']:.4f}／0.25；1h差 {first['hour_path_distance_pct']:.4f}／0.50；"
              f"末段差 {first['tail_path_distance_pct']:.4f}／0.10 百分點；波動 {first['volatility_ratio']:.3f}／2倍")
    else:
        # Long rejection diagnostics live in the HTML and JSON; keep the figure legible.
        text='本次全部未通過，未用其他方法或改動門檻補案例。詳細拒絕原因見同名 HTML 驗收表。'
    fig.text(.08,.105,text,fontsize=10,color='#42576a',linespacing=1.8)
    fig.text(.08,.035,'同欄共用縱軸，各自首收盤歸零；陰影＝末6棒，虛線＝事件前20棒固定高低。\n既有原生券商歷史棒回看；案例 PROJECT_REFERENCE／原始時鐘 UNKNOWN；通過試驗條件不是人工準確率或未來勝率。',fontsize=10,color='#536b7c',linespacing=1.7)
    name=f"{record['query_id']}_{tw(record['as_of'])[:10]}.png"
    fig.savefig(out/name,dpi=170);plt.close(fig)
    return name


def render_html(rows,probes,out,source):
    head='''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>十日真實盤面與情境案例驗收</title><style>body{font:16px/1.7 "Microsoft JhengHei",sans-serif;background:#f4f6f7;color:#243747;margin:0 auto;padding:32px;max-width:1280px}h1{font-size:28px}h2{font-size:21px}p{max-width:1000px}article{background:white;border:1px solid #d8e0e5;padding:24px;margin:24px 0}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:9px;text-align:left;border-bottom:1px solid #ddd}img{width:100%;height:auto}code{background:#eef2f4;padding:3px}a{color:#1a587c}.note{color:#5b6470}.pass{color:#14645a}.empty{color:#8b3e4e}details{margin-top:16px}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>十個不同日期：真實券商歷史盤面 → 既有情境案例</h1>'''
    content=[head,'<p>完整保留既有 D01–D10 固定週取樣，未依本輪結果挑日期、方向或案例。7 次通過、3 次全部未通過；允許零筆，沒有補案例。這是凍結資料重跑與展示驗收，不是新的盲測或人工相似準確率。</p>',
             '<p>查詢來源：cTrader DEMO XAUUSD 原生歷史已收 K 線（UTC 來源時間）；取得於 '+escape(source['fetched_at_utc'])+'。屬歷史盤面回看，不冒充當日即時抓取。歷史案例依來源時間模型定位，<code>PROJECT_REFERENCE</code>／原始時鐘 <code>UNKNOWN</code>。</p>',
             '<p>規則固定 <code>context_contract_v1</code>：同方向、成熟且不重疊，5分60根＋1h20根；事件相同、末段方向不相反；5分／1h／末段差≤0.25／0.50／0.10百分點，波動倍率≤2。按最大標準化差、合計、ID 排序，每群／參考時點最多一筆，最多五筆。手數及盈虧不排名。</p>',
             '<p>本機驗收沒有呼叫外部 LLM、券商或委託工具。解釋資料由同版共用的去識別化 case_context 建立；這裡檢查解釋輸入及程式敘述，不把離線模板當作實際模型回答。</p>',
             '<p class="note">完整 CSV、結果 JSON 與雜湊收據保存在本機 product/private/assistant_case_acceptance_20261022 資料夾；此網頁只提供圖表閱讀。</p>',
             '<table><thead><tr><th>查詢</th><th>台灣時間</th><th>方向</th><th>結果</th><th>可比較列</th><th>通過去重群／展示</th></tr></thead><tbody>']
    for row in rows:
        r=row['result'];c=r['comparison']
        content.append(f'<tr><td><a href="#{row["query_id"]}">{row["query_id"]}</a></td><td>{row["date_tw"]}</td><td>{row["side"]}</td><td>{r["rule_status"]}</td><td>{c["eligible_rows"]}</td><td>{r["total"]}／{len(r["cases"])}</td></tr>')
    content.append('</tbody></table>')
    for row in rows:
        r=row['result'];c=r['comparison'];style='pass' if r['cases'] else 'empty'
        content.append(f'<article id="{row["query_id"]}"><h2>{row["query_id"]} · {row["date_tw"]} · {row["side"]} · <span class="{style}">{r["rule_status"]}</span></h2>')
        content.append('<p>'+escape(c['query_market_text'])+'</p><p>'+escape(c['reason'])+'</p>')
        context=row['case_context']
        content.append('<p>解釋層判定：<strong>'+escape(context['label'])+'</strong>。'+escape(context['reason'])+'</p>')
        content.append(f'<a href="{row["plot"]}"><img src="{row["plot"]}" loading="lazy" alt="{row["query_id"]}五分鐘與一小時查詢和第一名案例K線對照"></a>')
        if r['cases']:
            content.append('<table><tr><th>名次／案例</th><th>5分差</th><th>1h差</th><th>末段差</th><th>波動倍率</th></tr>')
            for n,case in enumerate(r['cases'],1):
                content.append(f'<tr><td>{n} · {escape(case["id"])}</td><td>{case["path_distance_pct"]:.5f}</td><td>{case["hour_path_distance_pct"]:.5f}</td><td>{case["tail_path_distance_pct"]:.5f}</td><td>{case["volatility_ratio"]:.4f}</td></tr>')
            content.append('</table>')
        content.append('<details><summary>拒絕原因次數（同一列可違反多條，不能相加當案例數）</summary><ul>')
        content.extend('<li>'+escape(c['rejection_labels'][key])+f'：{count}</li>' for key,count in c['rejections'].items())
        content.append('</ul></details>')
        if 'case_context' in row:
            content.append('<details><summary>去識別化解釋輸入（離線檢查，未送模型）</summary><pre>'+escape(json.dumps(row['case_context'],ensure_ascii=False,indent=2))+'</pre></details>')
        content.append('</article>')
    content.append('<article><h2>另外的受控探針：不計入十個真實日期</h2><p>下列是從 D01 複製後明確改動資料或改用空歷史池的程式測試，不是新的券商日期或當天實際缺資料證據。</p><table><tr><th>探針</th><th>改動</th><th>程式結果</th></tr>')
    for p in probes:
        content.append('<tr><td>'+escape(p['probe'])+'</td><td>'+escape(p['modification'])+'</td><td>'+p['result']['rule_status']+'</td></tr>')
    content.append('</table></article><p class="note">本頁只存在本機 private；未更新公開 Pages、未新增公開欄位。結果可重跑，圖形符合仍可能與人的主觀判斷不同；沒有人工標註就不報準確率。</p></html>')
    (out/'index.html').write_text('\n'.join(content),encoding='utf8')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    args=parser.parse_args(argv);out=args.output.resolve()
    if not out.is_relative_to((PRODUCT/'private').resolve()):raise ValueError('PRIVATE_OUTPUT_REQUIRED')
    out.mkdir(parents=True,exist_ok=True)
    files=[PRODUCT/'private/cases.json',PRODUCT/'private/case_candidate_market_profiles.json',
           FROZEN/'queries_PRIVATE.json',FROZEN/'plot_profiles_PRIVATE.json',
           PRODUCT/'private/distinct_day_dual_path_20261021/samples_PRIVATE.json',
           PRODUCT/'backend/context_rules.py',PRODUCT/'backend/context_retrieval.py',Path(__file__)]
    files.extend([PRODUCT/'backend/case_context.py',PRODUCT/'research/test_assistant_case_acceptance.py',
                  PRODUCT/'research/render_live_dual_samples.py',PRODUCT/'research/render_context_similarity_ab.py'])
    before={p.relative_to(PRODUCT).as_posix():sha256(p.read_bytes()).hexdigest() for p in files}
    frozen=json.loads(files[2].read_text(encoding='utf8'))
    plot_profiles=json.loads(files[3].read_text(encoding='utf8'))['queries']
    source=json.loads(files[4].read_text(encoding='utf8'))
    cases=json.loads(files[0].read_text(encoding='utf8'))['cases']
    profiles,status=load_candidate_sidecar(files[0],files[1],PRODUCT/'private')
    if status!='READY':raise RuntimeError(status)
    index=ContextIndex(cases,profiles)
    from research.render_similarity_comparison import configure
    configure()
    rows=[];checked=0;windows={'5m':[],'1h':[]}
    for record in select_real_queries(frozen):
        query=plot_profiles[record['query_id']]
        assert query['source']=='ctrader_demo_xauusd' and query['query_clock_status']=='UTC_SOURCE_TIMESTAMP'
        assert query['as_of']==record['as_of']
        for iv,size in [('5m',300),('1h',3600)]:
            bars=query['pre_entry_bars'][iv]
            assert len(bars)==(60 if iv=='5m' else 20)
            interval=(bars[0]['time'],bars[-1]['time']+size)
            assert all(interval[1]<=prior[0] or prior[1]<=interval[0] for prior in windows[iv])
            windows[iv].append(interval)
        result=index.retrieve(query,record['side'])
        validate_frozen(result,record)
        checked+=verify_pairs(index,query,result,record['side'])
        row=dict(query_id=record['query_id'],date_tw=tw(record['as_of']),as_of=record['as_of'],
                 side=record['side'],query_source=query['source'],capture_kind=source['capture_kind'],
                 query_clock_status=query['query_clock_status'],result=result)
        row['plot']=render_page(record,query,result,profiles,out)
        row['case_context']=checked_context(result,query,record['side'],f'frozen-{record["query_id"]}')
        rows.append(row)
        print(f"{row['query_id']} {row['date_tw']} {result['rule_status']} shown={len(result['cases'])}",flush=True)
    base=plot_profiles['D01'];variants=controlled_probe_queries(base)
    probes=[]
    for name,query,engine,expected,change in [
        ('missing_hour',variants['missing_hour'],index,'INSUFFICIENT_DATA','清空複本的一小時棒'),
        ('empty_history_pool',base,ContextIndex([],{}),'NO_COMPARABLE_CASES','原查詢不改，改用空歷史索引'),
        ('uncertain_event',variants['uncertain_event'],index,'UNCERTAIN_EVENT','複本最後五分鐘收盤改到事件前區間上緣，維持OHLC一致')]:
        result=engine.retrieve(query,'BUY');assert result['rule_status']==expected
        assert not result['cases']
        probes.append(dict(probe=name,controlled=True,modification=change,result=result,
                           case_context=checked_context(result,query,'BUY',f'controlled-{name}')))
    assert Counter(r['result']['rule_status'] for r in rows)=={'PASSED':7,'NO_RULE_MATCH':3}
    dump(out/'results_PRIVATE.json',dict(method=METHOD,thresholds=THRESHOLDS,real_date_queries=rows,controlled_probes=probes))
    fields=['query_id','date_tw','side','query_source','rule_status','eligible_rows','passed_unique','shown','first_case_id','d5','d1h','dtail','vol_ratio']
    with (out/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for row in rows:
            r=row['result'];first=r['cases'][0] if r['cases'] else {}
            writer.writerow(dict(query_id=row['query_id'],date_tw=row['date_tw'],side=row['side'],query_source=row['query_source'],
                rule_status=r['rule_status'],eligible_rows=r['comparison']['eligible_rows'],passed_unique=r['total'],shown=len(r['cases']),
                first_case_id=first.get('id'),d5=first.get('path_distance_pct'),d1h=first.get('hour_path_distance_pct'),
                dtail=first.get('tail_path_distance_pct'),vol_ratio=first.get('volatility_ratio')))
    render_html(rows,probes,out,source)
    after={p.relative_to(PRODUCT).as_posix():sha256(p.read_bytes()).hexdigest() for p in files}
    assert before==after,'INPUT_CHANGED_DURING_ACCEPTANCE'
    receipt=dict(status='PASS',method=METHOD,thresholds=THRESHOLDS,real_distinct_dates=10,queries_with_output=7,
                 actual_no_rule_match=3,controlled_probes=len(probes),displayed_pairs_checked=checked,
                 frozen_top5_counts_rejections_distances_equal=True,nonoverlapping_query_windows=True,
                 query_source='ctrader_demo_xauusd',capture_kind=source['capture_kind'],fetched_at_utc=source['fetched_at_utc'],
                 external_llm_calls=0,broker_calls=0,order_calls=0,similarity_accuracy=None,inputs_unchanged=True,inputs=before)
    receipt.update(case_context_adapter_checks=13,deidentified_fact_inputs_checked=True,
                   human_similarity_accuracy_measured=False,live_model_response_validated=False)
    dump(out/'manifest_PRIVATE.json',receipt)
    print(json.dumps({k:v for k,v in receipt.items() if k!='inputs'},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
