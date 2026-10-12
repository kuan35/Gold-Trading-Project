# 來源時間補證：跨格式候選橋接與分來源日曆

查核日期：2026-10-13。這輪只新增私人稽核工具及匿名報告；沒有修改原件、正式時間 ledger、案例、行情或盤面側檔。

## 主要進展

已把 **166 個黃金來源整理成 185 列來源／年份候選日曆**，並補出原本欠缺的跨格式線索：**55 個沒有券商欄位的來源**，能與具有券商欄位的 HTML 找到多日、同經濟數值、同進出分鐘的候選橋接，涵蓋 **5,549 個產品候選**。這些是可追查的來源對應候選，尚不是同帳戶或時區確認。

最重要的新發現是：原先單一 UTC+0 CSV 例外，現在可以連到 **broker 欄位標為 intertrader 的 HTML**。不是只憑檔名猜券商；兩份現有匯出有 **84 種不同的商品／方向／手數／進出價組合，分布 9 個日期，進出分鐘差均為 0**。此結果讓例外有了具體追查對象。

本輪正式新增確認仍為 **0**；11,902 個產品候選的正式盤面匹配仍未啟用。這輪完成的是候選來源映射、分年日曆、例外查核與補證優先順序。

## 1. 跨格式橋接補出了什麼

原件可辨識券商欄位的 67 個來源，只對應 197 個產品候選；其餘 99 個 CSV／XLSX 來源對應 11,705 個產品候選。不能把前者的券商政策直接套到後者。

本輪在既有解析表建立經濟指紋，使用商品、方向、Decimal 手數、進場價、平倉價。再要求兩份匯出的進場與平倉分鐘差相同且在正負 14 小時內；秒精度只向下截到分鐘以配合 CSV。至少 3 種不同指紋、2 個日期，才列為多日候選。此為離線來源稽核，平倉價沒有用作下單前特徵或相似度。

結果為 62 對候選來源連結，其中 61 對達上述多日條件。55 個原無券商欄位的來源得到唯一券商候選，沒有同來源連到不同券商的衝突。

| 原無券商欄位來源所連到的 HTML 券商 | 候選來源數 | 對應產品候選數 |
|---|---:|---:|
| RoboForex | 33 | 3,959 |
| XM | 10 | 706 |
| INFINOX Capital | 7 | 293 |
| Hantec Markets | 2 | 481 |
| Hantec Global Ltd | 1 | 0 |
| intertrader | 1 | 110 |
| Lirunex | 1 | 0 |
| 合計 | 55 | 5,549 |

**橋接仍是候選。** 經濟數值相同可能來自複製交易、跨帳戶或重複匯出；沒有交易編號或原生帳戶映射，不能確認同帳戶，也不能將這些連結當成獨立交易樣本。現有資料仍沒有「同交易編號加經濟數值」的確切身份橋接。來源清單、原檔 SHA 與逐對證據只留在私人目錄。

## 2. UTC+0 例外的具體結果

該 CSV 共 236 列已解析觀察，其中 208 列為黃金市場交易；208 列較強 UTC+0 價格候選涵蓋 29 個進場日期，對應 110 個產品候選。CSV 表頭符合 Myfxbook 匯出；Tags、Comment、Magic Number 沒有可辨識券商／平台名稱。不能因為這些欄位沒有標示就推定平台。

它與 intertrader HTML 的 84 種經濟指紋／9 日期橋接，同時支持兩份匯出使用相同分鐘時鐘。但 HTML 中找不到 CSV 的 236 個 ticket 字串，也沒有 ticket／order ID 標籤，因此仍未確認帳戶身份。

用既有 M1 快取再查同一來源，取一個來源內每個 5 分進場批次一票，排除 DST 邊界前後一天；四種解釋共用 **137 個批次**：

| 時鐘假設 | 價格吻合／137 | 缺行情分鐘 |
|---|---:|---:|
| UTC+0 | 129（94.16%） | 2 |
| 歐洲日期冬+2／夏+3 | 12（8.76%） | 2 |
| 美國日期冬+2／夏+3 | 12（8.76%） | 2 |
| 台灣 UTC+8 | 3（2.19%） | 18 |

容差沿用 BID 分鐘高低範圍 ±0.5 USD/oz，缺行情計入分母且視為未吻合。137 是批次，不是獨立交易數；94.16% 是價格相容率，不能當成時間正確率。此批資料是已看過的回溯診斷，且沿用未正式確認的 EMPIRICAL_EU_SHIFT 行情時鐘。

目前較具體的分類是 **「可能與 intertrader 來源相連、價格支持 UTC+0 的 Myfxbook CSV」**。仍須區分券商本身採 UTC、匯出曾轉 UTC，以及行情時鐘或候選比對仍有誤等解釋。觀察期未跨歐洲夏季，不能據此確認全年固定 UTC，也不能排除 London 冬季 GMT／夏季 BST。

本輪查找 Intertrader 官方時間政策時，官網首頁回傳 redirect loop，FAQ 與平台頁未成功取得。搜尋到第三方 GMT 說法，但沒有採為正式證據；不依此新增確認。

## 3. 候選日曆與 DST 實測

逐來源／年份保留原檔 SHA、格式、原券商欄位、候選券商、原件期間、既有價格模型、EU／US 兩套切換日，以及不同步週 M1 結果。沒有只有夏季資料就將固定+3當成全年政策，也沒有將冬季固定+2強制歸為 EU 或 US。

美國規則採 3 月第二個週日／11 月第一個週日；歐洲規則採 3 月最後一個週日／10 月最後一個週日。這些是候選日曆，沒有補造每個券商的實際換時瞬間；邊界及前後一天都排除診斷。[NIST DST 規則](https://www.nist.gov/pml/time-and-frequency-division/popular-links/daylight-saving-time-dst)、[歐盟執委會 summertime 說明](https://transport.ec.europa.eu/transport-themes/summertime_en)。

| 年份 | 美國進／出夏令日 | 歐洲進／出夏令日 |
|---|---|---|
| 2024 | 03-10／11-03 | 03-31／10-27 |
| 2025 | 03-09／11-02 | 03-30／10-26 |
| 2026 | 03-08／11-01 | 03-29／10-25 |

所有來源共需 2,193 個指定 M1 時點，取得 2,120 個；缺的 73 個不補 0。43 個來源有美歐不同步週進場。以預先寫入工具的保守描述性篩選條件：至少 10 個批次、5 個日期、較佳模型價格吻合至少 90%，且優勢至少 50 個百分點，185 列來源／年份中有 **7 列可區分（EU 2、US 5），178 列保留未解**。這 7 個來源合計對應 1,415 個產品候選；不表示這 1,415 個候選都已通過時間驗證。

對樣本少、只有共同冬夏期間或同分來源，不強行選日曆。跨來源可能相依，因此 7 列也不能當成 7 票獨立證明。

## 4. 這輪補讀的官方資料

以下均於 2026-10-13 查讀，只使用公開券商、平台及政策名稱搜尋，沒有傳送私人帳號、檔名、交易編號、價格或逐筆時間。

| 官方來源 | 這輪可確認的內容 | 適用限制 |
|---|---|---|
| [Myfxbook API](https://www.myfxbook.com/api) | Important notes 說 transaction timestamps 使用 broker local timezone | 現行 API 定義；不是每份歷史 CSV／HTML 的無轉換保證 |
| [Myfxbook 匯出教學](https://www.myfxbook.com/help/knowledge-base/exporting-trading-history/) | 完整取得正文：由帳戶頁圖表上方設定圖示選擇匯出 | 正文沒有定義匯出時區；不能據此補上 offset |
| [RoboForex 2025-03-04 公告](https://roboforex.com/about/company/news/show/8055-schedule-trade-changes-10032025/) | 2025-03-10 至 03-28，MT4／MT5 黃金以 server time 00:05–22:55 交易 | 有日期的交易時段；沒有直接給個別帳戶 offset |
| [FTMO 2025-03-06 公告](https://ftmo.com/en/blog/trading-updates/trading-update-6-mar-2025/) | 03-09 平台由 GMT+2 轉+3，03-30 歐洲才切換；cTrader／DXtrade 顯示可依使用者設定 | 證明該年平台規則與顯示差異；沒有證明本機 XLSX 來自 FTMO |
| [FTMO 2026-03-05 公告](https://ftmo.com/en/blog/trading-updates/trading-update-5-mar-2026/) | 03-08 平台轉+3，歐洲 03-29 切換；每日損失仍按 Prague 時鐘重置 | 平台時鐘、介面顯示和風控重置不能混用 |
| [INFINOX Market Hours](https://infinox.com/global/en/market-hours) | 現行說冬+2／夏+3並對齊 NY close | 未找到各歷史年度／server 的完整換時公告；不能只因 EET 字樣直接選 EU 日期 |
| [MetaTrader 5 History](https://www.metatrader5.com/en/terminal/help/trading/performing_deals) | 原生 History／position time 依 broker trading server timezone | 一般欄位定義，不提供 broker offset 或二次匯出映射 |

另外將 38 份 XLSX 的全部 XML 與 relationships 掃描 FTMO、MetaTrader、cTrader、DXtrade 等來源 token，**命中 0 份**。價格支持 US 日曆的 XLSX 也不能因此指認 FTMO。檔名、文件建立時間及資料夾名稱都不作平台或交易時區證據。

## 5. 可信 UTC 行情補查的實際結果

新增有上限的 raw Dukascopy hourly tick probe，預定 4 個公開日曆日期（冬季、春季不同步週、夏季、秋季不同步週）各 2 小時，最多 8 次，成功請求間隔 1.5 秒；任何錯誤即停止，不換 IP／端點或輪替身分。

普通沙箱第一次請求遇 DNS getaddrinfo failed；使用正常權限流程於沙箱外重跑同一公開端點，第一次請求遇 TLS handshake timeout。**本輪取得 0 個 raw 檔、0 根 bar，沒有收到可用 HTTP 回應。** 前輪曾發生 HTTP 429，但不能把本輪的 DNS／TLS 錯誤寫成仍在 429，也不能宣稱新 UTC 錨點已驗證。原有行情時鐘確認狀態維持不變。

## 6. 交付、重現與驗證

以下重跑指令僅供持有完整本機工作區及私人資料的團隊成員使用；公開倉庫只提供這份匿名報告和彙總 JSON。私人工具及逐來源證據位於本機 `product/private/time_completion_20261013/`，包含候選券商對應、185 列日曆、逐對經濟橋接、UTC 例外詳情、XLSX metadata 掃描、tick 失敗 manifest、完整性及重跑紀錄。

在專案根目錄執行：

```powershell
product/.venv/Scripts/python.exe -B product/private/time_completion_20261013/complete_evidence.py
product/.venv/Scripts/python.exe -B product/private/time_completion_20261013/provenance_probe.py
product/.venv/Scripts/python.exe -B product/private/time_completion_20261013/verify_results.py
product/.venv/Scripts/python.exe -B product/private/time_completion_20261013/integrity_check.py
```

tick probe 需可連至公開 datafeed 的網路環境才另外執行，不是離線重現必要步驟。它只有取得有效資料才進行比較。

驗證覆蓋：來源與產品候選計數、M1 共同分母及缺值、日曆週日及月份規則、原檔 SHA 綁定、候選身份維持未確認、匿名摘要不含私人來源 ID／檔名／交易欄位、5 支新 Python 工具語法，以及 239 原件集合／SHA 與 3 個正式產品輸入 SHA 前後相同。沒有改產品程式，本模組未重跑前後端測試。

離線工具重跑後，6 份核心候選 JSON 逐位元相同；17 個稽核輸入 SHA 亦通過核對。匿名交付另附 summary、integrity、verification、provenance_probe_summary 與 repeat_check JSON，不含私人來源清單或雜湊。

後續應先沿這 55 個跨格式候選向少數來源補原生身份橋接；UTC 例外優先核對 intertrader 的 server／匯出規則，而非要求交易員逐筆補標註。產品候選最多的前 10 個來源涵蓋 4,409 個候選、前 20 個涵蓋 6,564 個；這是補證工作量排序，與前輪「較強價格候選前十來源」的 2,926 不同分母。只有原生映射、歷史適用政策與可信 UTC 行情一起補齊，才更新正式 ledger 並重建盤面側檔。
