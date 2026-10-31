"""Package aggregate findings and all-row private alignment sidecars."""
import csv,hashlib,io,json,zipfile
from collections import Counter,defaultdict
from datetime import datetime,timedelta,timezone
from decimal import Decimal as D
from pathlib import Path
import expand_time_alignment as m

ROOT=Path(r'C:\Users\USER\Desktop\專題\新版本專題交易員模擬')
P=ROOT/'product/private/d_time_alignment_expanded_20261012'
ANALYSIS=P/'minute-candidates'
DELIVERY=P/'delivery'
PUBLIC=ROOT/'product/docs/d_time_alignment_expanded_20261012'


def release_anchors() -> list[dict]:
    anchors=[('XAUUSD',d) for d in ['20180712','20190711','20200714','20210713','20220713','20230712','20240711','20250715','20240111','20240312']]
    anchors += [('EURUSD',d) for d in ['20140722','20160715','20190711']]
    findings=[]
    for pair,day in anchors:
        cache=P/'histdata_archives' if pair=='XAUUSD' else P/'non-gold/eurusd_archives'
        target=cache/f'{pair}_M1_{day[:4]}.zip'
        matches={}
        with zipfile.ZipFile(target) as archive:
            for name in archive.namelist():
                if name.endswith('.csv'):
                    for line in io.TextIOWrapper(archive.open(name),encoding='utf-8-sig'):
                        if line[:8]==day:
                            dt,bar=m.parse_histdata_line(line)
                            matches[dt]=bar['high']-bar['low']
        local=datetime.strptime(day,'%Y%m%d').replace(hour=8,minute=30)
        us_summer=m.base.offset_minutes('US_2_3',local)==180
        utc=(local+timedelta(hours=4 if us_summer else 5)).replace(tzinfo=timezone.utc)
        correction=m.empirical_market_daily_shift(utc.year,utc.month,utc.day)
        raw_claimed=utc+timedelta(minutes=correction)
        findings.append(dict(instrument=pair,date=local.date().isoformat(),official_release_local='08:30 America/New_York',
            official_release_utc=utc.isoformat(),provider_claim_implied_utc=raw_claimed.isoformat(),
            empirical_correction_minutes=-correction,
            range_at_expected_utc_without_correction=str(matches.get(utc,'')),
            range_at_expected_utc_after_correction=str(matches.get(raw_claimed,'')),
            official_source=f'https://www.bls.gov/news.release/archives/cpi_{day[4:]}{day[:4]}.htm',
            status='DESCRIPTIVE_CLOCK_ANCHOR_NOT_CAUSAL_PROOF'))
    return findings


def main() -> None:
    if DELIVERY.exists() or PUBLIC.exists():raise FileExistsError('Delivery already exists')
    summary=json.loads((ANALYSIS/'summary.json').read_text(encoding='utf-8'))
    raw=list(csv.DictReader((ROOT/'artifacts/behavior_audit_20261001_final/all_records.csv').open(encoding='utf-8-sig')))
    originals={r['record_id']:r for r in raw}
    rows=list(csv.DictReader((ANALYSIS/'all_records_UTC_candidates_PRIVATE.csv').open(encoding='utf-8-sig')))
    assert len(originals)==len(rows)==31511
    fx=list(csv.DictReader((P/'non-gold/profiles_PRIVATE.csv').open(encoding='utf-8-sig')))
    fxmap={p['source_private']:p for p in fx}
    fxadded=Counter()
    for row in rows:
        r=originals[row['record_id']]
        row['calibration_instrument']='XAUUSD'
        row['calibration_interval_seconds']='60'
        if r['source'] in fxmap:
            p=fxmap[r['source']]
            profile=dict(status=p['status'],models=json.loads(p['models']))
            item=m.align_row(r,profile,{}, {})
            row.update({k:json.dumps(v,ensure_ascii=False) if isinstance(v,list) else str(v) if isinstance(v,bool) else v for k,v in item.items()})
            row['calibration_instrument']='EURUSD';row['calibration_interval_seconds']='300'
            row['market_clock_model']='EMPIRICAL_EU_SHIFT'
            row['market_clock_status']='INFERRED_FROM_THREE_BLS_RELEASE_ANCHORS'
            row['model_scope']='WHOLE_SOURCE'
            if row['open_utc_candidate']:fxadded['strong_candidate_rows']+=1
            elif row['open_utc_review_candidate']:fxadded['review_candidate_rows']+=1
        assert row['open_time_original']==r['open_time'] and row['close_time_original']==r['close_time']
        assert row['timezone_status']=='UNKNOWN' and row['production_enabled'] in ('False',False)
    DELIVERY.mkdir()
    m.base.write_csv(DELIVERY/'all_records_time_alignment_PRIVATE.csv',rows)
    candidate_case_ids={c['id'] for c in json.loads((ROOT/'product/private/cases.json').read_text(encoding='utf-8'))['cases']}
    case_index=[]
    for r in rows:
        cid='T-'+hashlib.sha256(r['record_id'].encode()).hexdigest()[:12]
        if cid in candidate_case_ids:
            case_index.append(dict(case_id=cid,source_key=r['source_key'],
                open_utc_candidate=r['open_utc_candidate'],close_utc_candidate=r['close_utc_candidate'],
                open_utc_review_candidate=r['open_utc_review_candidate'],close_utc_review_candidate=r['close_utc_review_candidate'],
                evidence_status=r['evidence_status'],timezone_status='UNKNOWN',
                entry_gap_1m_usd=r['entry_gap_1m_usd'],exit_gap_1m_usd=r['exit_gap_1m_usd'],
                last_closed_5m_candidate=r['last_closed_5m_candidate'],
                can_use_for_market_similarity=False,issues=json.loads(r['issues'])))
    assert len(case_index)==len(candidate_case_ids)==11902
    (DELIVERY/'case_time_alignment_PRIVATE.json').write_text(json.dumps(dict(cases=case_index),ensure_ascii=False,indent=2),encoding='utf-8')
    counts=Counter();years=defaultdict(Counter);trade_counts=Counter()
    for row in rows:
        state='strong_candidate' if row['open_utc_candidate'] else 'review_candidate' if row['open_utc_review_candidate'] else 'unresolved'
        counts[state]+=1;years[row['open_time_original'][:4]][state]+=1
        if row['record_type']=='TRADE':trade_counts[state]+=1
    summary['all_record_alignment_states']=dict(counts)
    summary['all_trade_alignment_states']=dict(trade_counts)
    summary['supplementary_eurusd']=dict(json.loads((P/'non-gold/summary.json').read_text()),**dict(fxadded))
    summary['supplementary_eurusd']['eurusd_market_clock_status']='INFERRED_FROM_THREE_BLS_RELEASE_ANCHORS'
    anchors=release_anchors()
    (DELIVERY/'market_clock_anchors.json').write_text(json.dumps(anchors,ensure_ascii=False,indent=2),encoding='utf-8')
    integrity=json.loads((P/'integrity_before_PRIVATE.json').read_text(encoding='utf-8'))
    assert not [f for f,h in integrity.items() if m.sha(ROOT/f)!=h]
    # Public reports may contain aggregates and public market observations, never source IDs.
    public_text=json.dumps(summary,ensure_ascii=False)
    private_names={r['source'] for r in raw}
    assert not any(s in public_text for s in private_names)
    PUBLIC.mkdir(parents=True)
    (PUBLIC/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    m.base.write_csv(PUBLIC/'market_clock_anchors.csv',anchors)
    g=summary['row_statuses'];cases=summary['product_candidates'];ms=summary['market']
    text=f'''# 全部交易紀錄時間對照：實測結果與使用方式

本輪已逐列處理全部 {len(rows):,} 列紀錄，其中 {summary['trade_rows']:,} 列已平倉交易、{summary['gold_trade_rows']:,} 列黃金交易。這些是來源觀察列，包含重複匯出，不等於獨立交易數。

## 可以先看懂的結論

| 黃金交易狀態 | 觀察列數 | 意義 |
|---|---:|---|
| 較強的UTC候選 | {g.get('gold_candidate_utc',0):,} | 來源通過時間切分與價格檢查，且等價模型在該筆時間一致；仍未取得帳戶時區設定證明 |
| 供複核的UTC候選 | {g.get('gold_review_candidate_utc',0):,} | 樣本較少，時間與價格支持該候選，單獨存放、不當成已核實資料 |
| 仍無法判定 | {g.get('gold_unresolved',0):,} | 天數／事件不足、替代時差仍有競爭、DST邊界或價格不吻合等 |

較強候選中，逐筆進場價吻合1分K者 {g.get('gold_candidate_entry_1m_match',0):,} 列，進場及平倉價均吻合者 {g.get('gold_candidate_both_1m_match',0):,} 列；容許差為0.5美元／盎司，不是已核實的券商價差，也不是正確率。

產品的11,902個候選案例：較強時間候選 {cases.get('candidate_utc',0):,}、供複核 {cases.get('review_candidate_utc',0):,}、未判定 {cases.get('unresolved',0):,}。全部仍標 UNKNOWN，市場相似度與案例K線尚未自動開啟。

## 行情缺口已補到哪裡

下載11份XAUUSD歷史壓縮檔，2018—2025整年與2026年1—3月，共 {ms['minute_rows']:,} 列1分報價、{ms['unique_minutes']:,} 個不同分鐘。420列相同分鐘相同價格的重複資料只算一次。範圍涵蓋所有黃金入場日期；任一時間假設有報價，不代表該筆時間已確定。

另下載EURUSD的2014、2016、2019年度檔，補查12個沒有黃金的來源。它們共1612列EURUSD交易，使用1 pip容許差作5分K來源對時；其他商品未逐筆核價。EURUSD補充的較強／供複核候選分別為 {fxadded.get('strong_candidate_rows',0)}／{fxadded.get('review_candidate_rows',0)} 列來源紀錄，與黃金數字分開。

## 發現並處理的行情時鐘問題

HistData官方FAQ稱資料為固定EST、不調夏令時間；但本批下載檔按該說明轉換後，夏季與既有UTC行情呈一小時偏差。不能直接相信CSV欄位寫UTC。

本輪保留未修正診斷，用明示的 EMPIRICAL_EU_SHIFT 假設：在歐洲夏季期間，將按FAQ換算的時間再減1小時。修正後與原Dukascopy行情有351,001根重疊5分K，其高低價格區間全部重疊。兩份檔案的報價高度一致，不能當成兩份獨立價格證據。

另列13個美國BLS官方公布時點，涵蓋黃金2018—2025各年夏季、2024冬季及美歐DST不同步期間，以及EURUSD三個年度；價格波動位置支持這項修正。這是實證推定，不是供應商對個別檔案的正式時區保證。切換邊界不採用簡化規則作正式用途。

來源：[HistData FAQ](https://www.histdata.com/f-a-q/)、[BLS 2024-07-11](https://www.bls.gov/news.release/archives/cpi_07112024.htm)、[BLS 2024-03-12](https://www.bls.gov/news.release/archives/cpi_03122024.htm)。完整時點與連結見同目錄 market_clock_anchors.csv。沒有使用公布數值當作交易前特徵。

## 對時方法與限制

- 每個匯出來源分開比較UTC−12至+14、每15分鐘，以及美／歐GMT+2/+3，共107種時間模型。來源不等於帳戶。
- 同來源同5分鐘只留一個進場事件投票；重複來源分別診斷，但不當成獨立證據。與上輪排除全部跨來源重複的取樣不同，不能直接拿來源數比較改善幅度。
- 用較早60%交易日選模型、較晚40%驗證；不使用盈虧。正式本輪使用1分K重選全部模型；進場1分驗證與選模的驗證集相同，不重複當成第二份獨立證據。平倉價格只作離線交叉檢查。
- 較強候選沿用至少30事件、訓練15／驗證10、各5日、前後吻合率≥80%、領先其他模型≥10百分點。供複核候選另要求訓練5／驗證3、各2日及相同吻合／領先門檻。這些是工程篩檢，不是統計信心水準。
- 整段不穩定的來源，另以事先固定的自然年季度檢查；季度結論不外推其他季度，跨期平倉時間會留空。多重篩選仍只能稱候選。
- 不強迫挑選等價DST模型；每筆開／平倉分別換算，各模型不同時留空。保留原始字串、分鐘／秒精度及未判定原因。
- 不補造成交量：HistData沒有可用量；部分5分K不足5分鐘，只供離線價格診斷，不能視為完整可交易棒。
- 執行K棒與平倉價用於離線對時；實際下單前只能取較早已收盤K棒。所有 production_enabled 均為false。

## 檔案給同學怎麼用

私人逐筆成果在 product/private/d_time_alignment_expanded_20261012/delivery/，不得放公開GitHub：

- all_records_time_alignment_PRIVATE.csv：全部31,511列，一列對應一筆來源紀錄，附原時間、UTC候選、證據層級、模型與原因。
- case_time_alignment_PRIVATE.json：11,902個產品案例ID與同一組時間證據，方便之後接案例圖；can_use_for_market_similarity目前全false。
- market_clock_anchors.json：公開行情時點的可重現檢查依據。

精確來源／假設／月份／價格驗證在 minute-candidates/；不要讀 run1/（供應商FAQ直轉、夏季偏差未修正）、corrected-run/（中止的慢速程序）或 final-candidates/（5分精度中間結果）。

## 還需要什麼，才能正式核實

不需要交易員逐筆標註。需要取得各批匯出的時間設定：Myfxbook是否改過顯示時區、Excel來自MT4／MT5或cTrader，以及相應帳戶與日期的伺服器時間證據。少量原始下單紀錄能同時看到交易時間與可信UTC時鐘，也能作獨立查證。

樣本太少／候選不唯一的來源，維持未判定；不能因同一家券商或檔名相似，就套用另一來源的結果。下一步核實設定後才開放盤面檢索與案例K線。時間設定證明與價格匹配是兩件事。

## 重現

在專案根目錄執行：

```powershell
python -B product/research/scripts/expand_time_alignment.py download --root . --output product/private/d_time_alignment_expanded_20261012
python -B product/research/scripts/expand_time_alignment.py analyze --root . --output product/private/d_time_alignment_expanded_20261012 --result product/private/d_time_alignment_expanded_20261012/repeat-check --market-clock EMPIRICAL_EU_SHIFT --calibration-interval 60
python -B product/research/scripts/non_gold_clocks.py --root . --output product/private/d_time_alignment_expanded_20261012/non-gold
.\\product\\.venv\\Scripts\\python.exe -B -m pytest -q -c product/research/pytest.ini product/research -p no:cacheprovider
```

私人交付打包程式為 product/research/scripts/finalize_time_alignment.py；已有交付時拒絕覆寫。原件與四份核心輸入SHA共243檔前後一致，research 43項測試通過。沒有改寫原始時間、產品案例索引或既有行情，沒有連券商／LLM或推送GitHub。
'''
    assert not any(s in text for s in private_names)
    (PUBLIC/'report.md').write_text(text,encoding='utf-8')
    (P/'README.md').write_text('正式交付：delivery/；正式1分分析：minute-candidates/。run1為未修正行情時鐘的診斷；corrected-run中止；final-candidates為5分中間結果。所有結果均為候選，未正式核實。\n',encoding='utf-8')
    verification=dict(checked_immutable_files=len(integrity),changed_files=0,research_tests_passed=43,
        all_rows_preserved=len(rows),case_ids_preserved=len(case_index),public_source_identifiers=0,
        confirmed_rows=0,production_enabled_rows=0,
        scripts={p.name:m.sha(p) for p in (ROOT/'product/research/scripts').glob('*time_alignment*.py')})
    (DELIVERY/'verification_PRIVATE.json').write_text(json.dumps(verification,indent=2),encoding='utf-8')
    handoff=ROOT/'HANDOFF.md';old=handoff.read_text(encoding='utf-8-sig')
    record=f'''## 2026-10-12 — 全部交易時間對照、補行情與1分K核驗（Codex）

- 使用者授權盡量對齊全部交易；已檢查31511來源觀察列（28415已平倉交易／25656黃金），全列保留原時間，另輸出私人UTC候選與未判定原因。不是去重獨立交易數。
- 新增expand_time_alignment.py、non_gold_clocks.py、finalize_time_alignment.py及15項測試；既有audit_market_time_alignment.py新增1m精度參數，預設5m行為不變。公開彙總product/docs/d_time_alignment_expanded_20261012/report.md與summary.json；逐列及11902案例映射在同名private目錄delivery/。
- Dukascopy JSON／bi5均HTTP429，改走HistData免費表單；下載11份XAUUSD檔（2018–2025及2026Q1），2874217分鐘觀察／2873797唯一分鐘。另3份EURUSD（2014／2016／2019）處理無黃金的12來源。2018月檔無有效ZIP，年度檔成功。
- 發現HistData本批檔按官方FAQ固定EST轉UTC後夏季晚1h；保留未修正run1診斷，以明示EMPIRICAL_EU_SHIFT修正假設核驗，351001根與既有行情重疊且價格區間全重疊；13個BLS官方時點交叉檢查。市場時鐘仍標實證推定，不把報價相同視為獨立價格來源。corrected-run是中止慢程序，final-candidates是5m中間版，正式分析minute-candidates。
- 正式黃金較強UTC候選{g.get('gold_candidate_utc',0)}列、低樣本複核{g.get('gold_review_candidate_utc',0)}、未判定{g.get('gold_unresolved',0)}；較強候選進場／雙邊1m吻合{g.get('gold_candidate_entry_1m_match',0)}／{g.get('gold_candidate_both_1m_match',0)}（0.5USD/oz容許差）。產品候選較強{cases.get('candidate_utc',0)}／複核{cases.get('review_candidate_utc',0)}／未判定{cases.get('unresolved',0)}。全來源UNKNOWN，production／market_similarity皆false；未改cases.py、前端、原始案例索引。
- 固定交易日60/40分割、不用盈虧，同來源5m一票，107模型在1m行情重新比較；跨來源重複只作各來源時鐘診斷，不當獨立帳戶證據。自然季度分段不外推，等價模型不強選，開平倉各自換算。下一步取各批匯出顯示時區／平台／帳戶歷史設定證據，不需要逐筆人工標註。
- 驗證：research43 passed，243原件／輸入SHA不變，31511列與11902案例ID完整，公開來源識別0；私人成果未推公開GitHub。Git master；commit N/A。桌面為正式工作區，fca5僅暫存。

'''
    assert '全部交易時間對照、補行情與1分K核驗' not in old
    handoff.write_text('# HANDOFF.md\n\n'+record+old.removeprefix('# HANDOFF.md').lstrip('\r\n'),encoding='utf-8')
    print(json.dumps(dict(gold=g,cases=cases,all_trades=dict(trade_counts),verification=verification),ensure_ascii=False))

if __name__=='__main__':main()
