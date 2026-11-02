# Gold Desk 本機產品交接

## 2026-11-02 — MACD／訊號線即時跳動修正

- 使用者開啟MACD與MACDsignal後圖表跳動。原ChartWorkspaceTools的effect依賴bars，每個tick cleanup移除全部指標與空副圖、再新增並setHeight(90)。不是價格正常跳動，亦不是前次CSS高度回饋。
- 新frontend/src/chartStudies.ts統一指標series生命週期，選擇設定變動才改配置；同一形成棒只update尾點，新棒append，暖機／歷史修正／視窗更換才setData。MACD雙線共用一個副圖；初始主副圖3:1，tick不重設面板比例或fit／scroll。ChartWorkspaceTools只在runtime切換時清理，其他圖表沿用同一修正。
- 新tests/chart-studies.test.ts先以舊移除／重建行為跑出4失敗，再5項全通過：80次tick維持series及使用者尺寸、三類副圖、歷史修正、暖機缺值、fallback量、選擇切換與清理。全前端173 passed；npm run build及build:pages成功（原chunk警告）。後端未修改，不重跑後端全套。
- Chrome實際原生行情驗收：雙MACD原主／副圖110.8／245.6px，更新版初始266.8／89.6px；手動改為238.8／117.6px，接收tick638→791仍保留尺寸。另開RSI／ATR、取消／重開訊號線、切15m與1h確認副圖配置；保持使用者原MACD雙線選擇。一次獨立read-only review無可執行問題。
- 無模型呼叫、無交易操作、無檢索規則／量能門檻變更。作者驗收截圖、測試log、243原件SHA與公開白名單收據留private/indicator_tick_fix_20261102，不公開案例／憑證／聊天。根branch codex/candidate-market-retrieval／commit N/A；公開沿codex/local-distribution-20261031、PR #1，發布SHA另記根HANDOFF。

## 2026-11-02 — 完整分析與圖表還原、總經快捷提問

- 切聊天原先只還原純文字，圖表快照又只在記憶體。新增analysis_history磁碟保存唯讀回覆及原快照，schema3聊天索引保存analysis_ref及圖表選擇；保留schema1／2文字相容。A→B→A、重整、服務真正重啟後皆讀原分析，不以新行情替代。
- analysisHistory／ArchivedConversationReply及工作台快取保留完整案例卡、分析圖、週期及案例／後續範圍。舊版沒有保存原快照者仍只能看文字。刪除先成功保存瀏覽器紀錄才清理後端引用；quota失敗不破壞原資料。共享快照不隨單一回覆刪除。
- GET／DELETE /api/assistant/analyses/{analysis_ref}僅本機；回覆不含可執行草稿或憑證。舊草稿仍走原TTL與人工確認，不因還原分析取得送單權限。
- 常用聊天新增「最近有哪些總經事件會影響黃金？」沿用calendar入口，按下才查詢，沒有常駐消息輪詢。
- 後端650 passed、1 skipped；前端168 passed；一般及Pages build成功（既有chunk警告）。一次獨立review的quota刪除順序問題已RED→GREEN修正。
- 真實Chrome驗收A開1h圖→B→A→重整→重啟後重整，原時間與圖表內容保留、圖表高度440px；當次即時無符合案例，有案例卡片以回歸fixture驗證。全程未呼叫付費模型或送交易；原Claude供應商設定已還原。
- 原243檔SHA與公開白名單收據留作者private/chat_analysis_fix_20261102。完整受控runtime包379檔驗證可載11902列案例／10887盤面；不含聊天、analysis_history或金鑰。組員沿README指定分支安裝、本人AI與DEMO設定，案例包另外私下分享。
- 根branch codex/candidate-market-retrieval／commit N/A；公開沿既有PR #1分支，實際發布SHA記於根HANDOFF。下一步組員依LOCAL_INSTALL安裝並驗收聊天切換，macOS實機仍待確認。

## 2026-11-02 — 圖表高度循環／統一平倉入口／開盤量能實測

- CaseComparison的grid＋100%圖表canvas會自撐高，實際Chrome量測四圖達22,464.5px。
  chartWorkspace.css限制比較圖360～440px、plot可縮且canvas絕對定位，指標不再推min-height。
  ChartWorkspaceTools只在有畫線時合併重畫；DrawingHistory修復刪光後復原與重做狀態。
- BrokerClosePanel單一「平倉」入口，先選MARKET／LIMIT才檢查草稿、人工確認；
  ReplayPositionActions／App本機持倉表也合併入口。後端與防重送權限未變。
- 前端162 passed及兩種build成功；後端量能／部位管理55 passed。開盤三週期串流
  形成中K棒與tick計數均更新；同原部位兩種close-draft建立及取消成功，無確認／成交。
- 20:55台灣查詢：BUY價格190列→tick178列，SELL17→16；20個不同歷史日16次有結果
  加量後仍16次，配對1416→1166、第一名改變2次。不是相似準確率或獨立交易數。
  量能2倍規則未改。詳細本機報告docs/chart_tick_validation_20261102.md（不在發布白名單）。
- 原頁面卡住後，電腦操作工具因無法確認網址而停止，未繞過；修正後瀏覽器互動驗收待補，
  可關閉卡住分頁再開本機站。完整收據及243原件SHA在作者private/chart_tick_fix_20261102。

## 2026-11-01 — 消息面改為交易對話按需回答

- 依使用者要求移除首頁MacroCalendarBar及其背景輪詢、倒數timer與樣式。
  事件／多空關聯仍在交易對話回覆中；問CPI、FOMC、消息等才取得及說明。
- ConversationWorkspace與LiveAssistant不再無條件include_macro:true；
  requestsMacroContext只在使用者這次提問包含消息主題時附加背景。
  普通知識、案例排序、委託草稿與人工確認不變；沒有新增主動通知。
- macro-events回歸測試涵蓋首次工作台無事件列、一般盤面／下單不請求消息、
  問消息才要求背景，以及既有多空情境／來源／歷史文字保存。
  前端156 passed，npm run build及build:pages成功；後端未改，不重跑完整後端。
  詳見docs/gold_macro_assistant_20261101.md；發布結果見研究工作區HANDOFF。

## 2026-11-01 — 黃金知識與官方消息面，逐事件說明多空關聯

- 新增macro_calendar／macro_knowledge／macro_assistant／macro_grounding；固定讀Fed
  FOMC、政策及發言RSS、BLS與BEA發布ICS，15分鐘快取。每個事件及公告都有影響機制、
  可能偏多／偏空的條件、未知及來源，不從標題宣稱當次鷹鴿或預測必漲跌。
- 知識／消息可獨立於券商報價回答；今天／本週／下週按台灣日期、主題先篩再截取。
  即時對話可把事件加入同一固定快照；不改案例檢索、原草稿／確認或LIVE唯讀限制。
  UI新增「黃金事件／看多空關聯」及回覆卡，歷史聊天保存當次來源與狀態。
- API：GET /api/assistant/macro-calendar；POST /api/assistant/gold-chat；live-chat新增
  include_macro（預設false，相容舊客戶端）。API_CONTRACT與docs/gold_macro_assistant_20261101.md
  說明欄位及限制。新增beautifulsoup4依賴，組員需重跑setup更新requirements。
- BLS官方US-Eastern別名已轉America/New_York；BEA排除州縣年度數據；FOMC只提供日期時
  不編精確倒數。尚無實際值／前值／市場共識，不計驚喜、不聲稱已判斷當次事件方向。
- 測試：後端644 passed、1 skipped；前端154 passed；一般與Pages build成功。
  一次獨立review後修正日期／主題先篩、今日消息意圖、無依據結果斷言；均有RED→GREEN。
  詞句檢查只是有限防護，不是語義真實性證明。5個官方來源HTTP讀取成功，本機首頁／JS與
  4個program查詢驗收成功；本輪未用模型額度、未送券商指令、未做瀏覽器點選驗收。
- 公開包只含程式與說明，不含官方快取、私人收據或新增私人資料；原3份公開JSON不變。
  原始資料／根目錄媒體243檔SHA另於本機檢查。PR仍未合併，Pages不等於本機功能。

## 2026-11-01 — 歷史聊天完整保存與安裝分支

- 修正ConversationWorkspace／deskConversations：不再只存前兩段、1800字、20則及12串。
  conversationArchive轉成唯讀完整文字，含全部段落、案例／差異、量比、情境與錯誤。
  仍不保存委託ID／確認key或可重送動作；圖表不是離線備份。
- schema v2沿用原localStorage key、自動讀v1、記住activeId，重整回原串。
  不自動刪舊串；超過容量明示未保存並保留先前磁碟資料，桌機／窄螢幕均有警告。
  問題尚未完成即先保存；舊版已截掉並關閉頁面的文字不能復原。
- ArchivedConversationReply讓長歷史文字可展開。過往紀錄不套用到當前委託；
  原有近6則LLM去識別上下文上限不變。詳見docs/conversation_history_20261031.md。
- README／AI_SETUP／LOCAL_INSTALL明確指定codex/local-distribution-20261031；
  尚未合併main前，直接clone預設main不含本輪更新。
- 新增先RED的conversation-archive測試，更新舊截斷預期；最後npm test150 passed，
  npm run build與build:pages均成功。未改後端API，未呼叫模型或券商。
  原安裝版Windows／macOS GitHub CI已全部成功；本輪更新後由PR重跑。
  下一步組員依PR分支安裝、用本人資料／登入驗收；聊天只存在同瀏覽器同origin。

## 2026-10-31 — Windows／macOS 分發與Codex接頭

安裝先讀README.md、AI_SETUP.md、docs/LOCAL_INSTALL.md；介面沿用frontend，
後端沿用backend，不需要重建或先架雲端站。TEAM_HANDOFF.md的舊架站紀錄僅供背景。

- 新增Codex官方CLI文字接頭，逐請求選擇Codex／Claude Code／程式解讀／API；
  Codex模型與思考程度來自本人metadata。沒有自動付費推論或借用開發聊天。
- Windows setup.ps1/start-local.ps1與macOS setup.sh/start-local.sh共用
  scripts/local_app.py；保留.env、單worker、127.0.0.1:8765、診斷不印憑證。
- scripts/data_bundle.py只匯出授權runtime資料；manifest、SHA、完整runtime載入、
  路徑／大小／鎖／還原驗證。私人包另行由資料擁有者分享，不公開上GitHub。
- 每人自己的cTrader DEMO與官方CLI登入；個人OAuth、refresh、量能來源重建詳見
  安裝指南。不得為了跨帳戶可用而移除tick source檢查。LIVE維持唯讀。
- 公開程式MIT，資料與第三方另依DATA_POLICY.md及THIRD_PARTY_NOTICES.md。
  用scripts/package_local.py準備精確白名單，勿git add作者研究工作區或private。

驗證：獨立Windows安裝包執行python -m scripts.local_app setup（含pip、npm ci、
build）與重跑成功，doctor為synthetic_demo／program／券商未設定；首頁與JS HTTP200。
完整後端pytest621 passed，frontend npm test143 passed，npm run build及build:pages成功。
原作者工作區完整620 passed、1 skipped；私人包379檔還原，11,902案例／10,887參考
盤面與進出場／後續／量能索引通過。未使用原始對帳單作安裝必需檔。

一次獨立review發現部分但SHA正確的包也可覆寫案例，已回歸測試重現並修正為
匯入前驗完整runtime；收據寫入失敗亦還原。清潔安裝還發現缺demo-data.json，
已補精確白名單與回歸測試。既有Starlette/httpx棄用與大bundle提示保留。

macOS：shell語法已檢查並提供Windows/macOS CI矩陣，未做實體Mac執行。
Codex：metadata確認可用，原生假模型隔離測試完成，未做真實付費推論。
cTrader：本輪未替組員做OAuth／下載／送單。瀏覽器點選與視覺驗收未執行。
下一步：本人選擇GitHub整合方式後推送，檢查Mac CI，再由各組員本機登入驗收。
