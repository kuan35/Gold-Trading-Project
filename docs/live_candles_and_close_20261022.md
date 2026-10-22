# 即時形成中 K 棒與模擬平倉

2026-10-21 開始，2026-10-22 完成驗收。本輪更新本機版，不部署公開私人帳戶後端。

## 使用方式

- 即時看盤的「5 分／15 分／1 小時」均顯示最後一根形成中 Bid 棒，實體、收盤價與高低影線跟隨收到的 Bid 更新；圖表上方顯示形成中時間、開高低收及接收 tick 數。
- 即時頁 K 線下方「持倉與損益」每列新增「平倉」。點擊只建立 30 秒草稿，核對部位／全部剩餘手數／Bid 或 Ask 參考價後，由使用者按「確認平倉 DEMO 部位」才會送給券商。取消草稿不會平倉。
- 本機回放對話頁的持倉摘要亦有「平倉」，沿用本機確認視窗。回放平倉與券商平倉各自標示，不互相代替。
- 下單紀錄明列「進場／加倉」或「平倉」、原方向及部位編號，避免把平倉原多單看成再買進。

## K 棒與量的資料範圍

現有單一 cTrader SDK 連線接收 Bid spot events，依來源 UTC 時戳分進 300／900／3600 秒桶。價格用 Decimal 解碼，僅繪圖輸出轉為數字；相同來源時間與價格的重複事件、亂序、未來及超過 5 秒的過期 tick 不累積。沒有 tick 就不模擬價格或補量。間隔超過 5 秒會標記觀測可能不完整。

形成中量是本機已接收的有效 Bid 更新筆數，包含同一根棒連線後的累積，不是全球黃金成交量，也不保證等同券商原生 tick volume。剛連線的第一根開高低與量可能不完整，畫面使用「觀測開／高／低」及不完整提示。若行情回應有該根原生 OHLC，可補開盤與高低，但保留最新觀測收盤及本機 tick 計數，不把未知的歷史量補成完整量。

棒結束後，在券商原生收棒到達前暫留本機觀測值，畫面明列「最近 N 根已結束棒仍為本機觀測值」，由原生棒到達後覆蓋。這些暫存棒和形成中棒都只用於繪圖，絕不加入案例檢索的 `query_snapshot()['bars']` 或原 `/broker/bars` 已收棒接口。

官方 spot trendbar 訂閱提供最後已收棒，因此不能單靠該欄當成每個 tick 的形成中棒；依[官方行情文件](https://help.ctrader.com/open-api/symbol-data/)維持券商收棒，再以有效 Bid spot 更新展示尾棒。

## 動畫及效能

新增 loopback-only `GET /api/broker/chart-stream?interval=5m|15m|1h`，SSE 每 250ms 最多推送一次最新完整展示快照（可合併同期間多個 ticks），沒有新值只送 keepalive，不增加券商訂閱連線。前端離頁／切換週期／隱藏分頁時關閉 SSE；行情未就緒可顯示原 TradingView 參考圖。

新 LiveCandleChart 僅在週期／主題改變時建立圖表，普通 tick 用 `series.update` 更新尾棒及量柱，不每次重建、fitContent 或強制捲回最新，保留使用者縮放位置。僅收盤位置以 160ms 緩動到真實最新值，高低價與量不製造額外變動；prefers-reduced-motion 直接更新。原生歷史修訂才換整組數據並保留視窗。做法依 [Lightweight Charts 增量更新 API](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/ISeriesApi)。

## 平倉完整性

使用真正 `ProtoOAClosePositionReq(positionId,volume)`，不是反向新開一單。草稿綁定已確認 DEMO 帳戶、原部位及全部剩餘 volume，確認前重新核對最新有效報價、權限、帳戶簽章、商品規格、部位及手數、30 秒期限與 revision。

確認時 SQLite 先耐久寫入 UNKNOWN 及防重送識別，再送出指令。同帳戶／部位有 UNKNOWN、ACCEPTED 或 PARTIALLY_FILLED 平倉時，重新整理或建立其他草稿也不能重送。FILLED 須等帳戶快照時間晚於成交觀察時間，才核對剩餘部位。明確 JSON 4xx 驗證拒絕可重新檢查；網路中斷、5xx 或格式不明仍視未知，提示到 cTrader 核對。

平倉回報只由原請求 correlation 或已知券商 orderId 關聯。外部手動／SL／TP 的其他 closing order 不能只因 positionId 相同就冒充本工作台平倉成交。結果與紀錄明列 intent=CLOSE。

## 驗證邊界

三週期實際唯讀串流及形成中收盤／tick 計數已核對。測試替身涵蓋部位改變、重啟、重複確認、跨草稿鎖、期限、不同帳戶、拒絕／未知回報及原生／暫存棒隔離。本輪不實際送出券商進場或平倉；有部位時只測建立／取消草稿，使用者持倉保留。

私人結果、測試日誌及截圖留在 `product/private/`，原始交易對帳單與憑證不變更、不上傳。

最終驗證：後端 `pytest -q backend/tests research/test_context_similarity_ab.py` **278 passed／1 skipped**（既有缺NumPy交叉排序），前端 `npm test` **54 passed**，production／Pages兩種build成功（既有bundle大於500kB提醒）。回放快捷平倉斷言追加後相關前端16項通過。原件241份SHA256前後一致。

本機唯讀驗收收據 `private/live_close_runtime_20261022.json`：三週期各3個快照的收盤及量持續更新；5分tick計數228→229→230。當前DEMO部位的平倉草稿REVIEW→CANCELLED，`position_preserved=true`，未呼叫確認、送單數0。10/21已目視三週期；10/22既有分頁因停在內部連線錯誤頁，受瀏覽器網址政策阻擋，已請使用者重新整理；最終新視窗操作尚待該刷新，未繞過安全限制。
