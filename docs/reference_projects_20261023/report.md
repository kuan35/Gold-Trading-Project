# 交易工作台參考專案：可重用部分與人機互動改版建議

查核日期：2026-10-23。本輪依使用者提供的專案清單，查閱實際原碼、套件依賴、授權與官方文件，不擴張成全面找新框架。下載副本只放本機private研究區；未安裝或執行第三方程式、未呼叫模型或券商、未修改網站功能或推送GitHub。Pairlens公開站只觀察初始語言設定，未完成開通；下述功能為原碼核查，非操作流暢度／成交／安全完整性驗收。

## 決策摘要

**優先採NOMO的聊天內容結構、Pairlens的共用助手狀態，再用現有Lightweight Charts把分析與圖連起來。OpenCharts取局部圖表操作，Ez只先參考回放流程。保留Gold Desk自己的cTrader／FastAPI／案例檢索與委託日誌。**

你們已用React／TypeScript／Vite，lockfile的Lightweight Charts為5.2.1；目前的不滿主要該從資訊架構、互動連續性與狀態回饋解，不必先換成Next.js、再造券商層或增加多代理。

老師先前指定首頁以聊天＋精簡委託＋tick為主，K線按需展開。貼文的「K線永遠主視覺」是另一種產品選擇，並非通用規則；本報告沿用既有首頁需求，讓專用看盤／回放頁承擔圖表密度。

## 每個專案的用途與採納方式

| 專案 | 真正值得用的部分 | 採納方式 | 與Gold Desk的主要差異 |
|---|---|---|---|
| [NOMO](https://github.com/Ut8v/NOMO) | 聊天內文字／圖／委託區塊、可收合工具進度、確認卡、聊天紀錄、停止與捲動細節 | 最高優先；MIT元件可評估局部改寫與保留通知 | Robinhood／美股、Express／Anthropic；不是現成cTrader即時行情與多人後端 |
| [Pairlens](https://github.com/Pairlens/trading-terminal) | 跨頁共用助手、畫面上下文、會話狀態分離、提案後顯示操作結果 | 高優先參考模式；複製程式需按FSL處理 | 大型Bun／TanStack／Tauri monorepo、自家圖表；含免逐筆確認選項，不直接搬 |
| [Lightweight Charts](https://tradingview.github.io/lightweight-charts/tutorials) | 價位線、marker、區間、click／crosshair、增量更新與量柱 | 最適合直接延伸；本來已使用 | 只是圖表庫，不附行情、相似判別或券商成交 |
| [OpenCharts](https://github.com/dylanpersonguy/OpenCharts) | 可拆面板、行情adapter、圖上拖TP／SL與預覽、回放控制列 | 局部程式可作重用候選；MIT與第三方NOTICE須保留 | LWC4與我們5不同；demo行情與DOM模擬；one-click和直接改倉位需改回草稿 |
| [Ez_backtest](https://github.com/awaqawaqawaq/Ez_backtest) | 日期／播放／速度、點交易紀錄定位進出場圖、同棒渲染平滑 | 先借互動概念；查核版本未見明確root授權 | Binance量與cTrader不同；前端撮合及P/L不能替代黃金後端 |
| [TradingAgents](https://github.com/TauricResearch/TradingAgents) | 支持／反對／觀察條件的內容架構、結構化研究輸出 | 取回答組織方式；不先引入整個LangGraph | 研究／辯論／報告流程，不是現成交易聊天前端 |
| [cTrader OpenApiPy](https://github.com/spotware/OpenApiPy) | 驗證、訂閱、心跳、回呼與重連界線 | 延伸現有券商橋接，不是換UI | 需產品自己恢復驗證／訂閱／補棒；SDK不自動解決多人授權 |
| QuantDesk | 附件沒有原始網址，無法確認是哪一個 | 暫不列直接採用清單 | 網路同名有AGPL工作區、MIT投組工具與beta網站，不能混為一談 |

以上判斷的固定commit、元件、函式與原碼行號見後半部附錄。每案「可重用」是候選，不代表已完成整合或所有依賴授權都逐一清查。

## 對目前網站的具體診斷

這些判斷來自本機現行程式，與第三方專案評價分開。

1. **現在比較像逐次查詢，完整對話狀態較薄。** ConversationWorkspace的turns是元件useState；發給live-chat的是最近4個使用者問句與這次資料，不是持久化完整會話／決策歷程。它能提供上下文線索，但還不等於重新登入後可接著討論、引用某張案例卡的完整互動。應保存conversation、訊息區塊、所引用snapshot與草稿版本；舊數值仍是歷史快照，不能混作最新盤面。
2. **修改欄位常被當成重新分析。** PREPARE／EDIT會轉成通用盤面分析問題，check又把草稿分析回覆加進對話；同一方向也可能反覆出相近長答。較好的體驗是「已將手數0.10改成0.20，停損情境同步更新」，只在盤面過期、方向改變或使用者要求時重分析。
3. **操作和解說仍分兩處。** 目前聊天可顯示提案套用，常駐票券有確認；應讓聊天內卡片與側欄指向同一草稿，點欄位就編輯，修改處短暫標示變化，不重建第二個下單狀態。
4. **圖有了，證據連動可更細。** 目前已有同快照圖表、支撐壓力、標記與focus；還能把每個結論的「看證據」直接定位到特定週期、區間或價位，顯示對應案例差異，而不是只開一整組圖再讓使用者自己找。
5. **工作進度需要反映真實階段。** 顯示「讀取已收盤面／比較歷史案例／檢查委託」，取代只有泛用loading或一次吐大量結果；完成後收合。中止要保留已完成與未完成的區分，不把中止生成解讀成撤單。

定位：frontend/src/ConversationWorkspace.tsx（turns、safeQuestion、previous_questions、check）、backend/conversation_intent.py（目前為保守規則解析）、backend/live_assistant.py（facts與近期問句）、frontend/src/AnalysisChart.tsx、ConversationCharts.tsx。相似核心與後端確認流程不因此重寫。

## 我建議的互動骨架

首頁維持三個清楚角色：可收合的對話紀錄入口、主聊天區、常駐精簡委託。最上方共用tick與連線狀態。圖表與案例詳細證據在同一工作台按需開啟，輸入與草稿始終保留；持倉／歷史紀錄有固定入口，不在每則分析反覆鋪滿。

一則助手回覆依用途呈現不同區塊，而不是所有問題都跑同一份長報告：

- 一兩句直接回應；必要時列支持與相反訊號。
- 查到案例時只先顯示一張比較卡：相同處、差異、代表歷史結果與資料時點；按需看其他案例及圖。
- 缺欄位時只追問一個必要問題，或提供可點選欄位。
- 使用者要求準備交易才放委託卡；欄位與側欄同步。分析多空不等於已準備某方向下單。
- 確認前用既有後端重新核對，回覆真實委託生命週期，保持UNKNOWN／ACCEPTED／FILLED差別。

可用下列三個情境先驗收人機互動，而不是先搬完整終端：

| 使用者的話／動作 | 預期互動 | 延伸參考 |
|---|---|---|
| 我想做多，有什麼反對訊號？ | 先回答支持／相反各一點＋一張案例卡；不替人補手數或直接下單 | NOMO內容區塊、TradingAgents支持／反方 |
| 改成限價4020、0.10手、停損4010 | 原草稿顯示修改差異、同步側欄；缺欄位就追問，不重吐整份盤面 | NOMO委託卡、Pairlens共用狀態；價格是互動示例，不是現況建議 |
| 點「案例為何相似」 | 同頁打開同快照5m／1h對照，聚焦所引用事件；回到聊天時原草稿仍在 | Pairlens畫面上下文、OpenCharts操作、現有LWC |

再補一個反例：「如果改做空呢？」先比較做空論點與案例，保留做多草稿；明確按套用才改。這沿用使用者之前選定的規則。

## 貼文中不宜照單全收的內容

- 示意圖的「信心72%」「相似度91%」「勝率66.7%」並不是我們校準出的數值。不要用漂亮百分比代替可核對條件；歷史盈虧需說清楚案例池分母與來源，不推成這次勝率，SL未知不能硬算R。
- Pairlens有常駐授權後自動執行，所以不能將它概括成每筆都必須本人點確認；我們保留逐筆明確確認。
- NOMO原生get_quote說明是前一交易日資料，ChartBlock不是tick訂閱；OpenCharts預設feed是歷史價折返，DOM深度是計算出的模擬量。可借畫面，不冒充cTrader行情。
- Pairlens的FSL並非一律禁止畢專：原條款明列非商業教育／研究，但再散布與用途仍有條件。NOMO與OpenCharts的MIT也不等於可刪除依賴的NOTICE／署名。
- Ez查核版本缺明確root授權，先借操作概念；不直接複製其程式／素材到公開repo。
- cTrader的algo-samples是cTrader內的機器人／指標／外掛範例，不是網頁Open API的整套前後端。

## 採納次序與交給同學的邊界

第一輪：NOMO式結構化聊天區塊與真實進度 → 編輯委託只更新差異 → 同一草稿與確認狀態同步。前端先接現有API，不同時更換模型／券商。

第二輪：Pairlens式共用會話與明確畫面上下文 → 透過同學後端保存與隔離 → 點證據定位既有圖表。保存歷史卡片不賦予舊單重新執行權。

第三輪：看盤頁的圖上價格預覽、拖SL／TP只修改草稿 → 回放頁的日期／播放／紀錄定位。保留cTrader原數值與權威回報；動畫中間值只用來畫圖。

第一輪先用上表三個情境完成可點的工作流程，再討論視覺風格；這樣可以評估到底少了幾次跳頁、重複輸入與重複文字。這輪沒有實作新架構，沒有宣稱任何專案能提高檢索準確率或交易績效。

---
# 原碼查核附錄

以下保留各案固定版本、檔案與連結，供前後端同學的Codex逐項查證。附錄描述的已有能力均指閱讀到的實作；完整執行驗收與公開部署仍是後續工作。

# Pairlens：共用助手與交易提案原碼核查

日期2026-10-23，固定commit `5e93f5ae911019d75a6c415216a28f33d857e104`。唯讀下載選定原始檔，未安裝／執行。公開網站只觀察到語言設定初始流程，未完成設定、登入或交易；下列功能判斷來自原碼，不宣稱流暢度或實際成交已驗收。

## 最值得參考

1. **同一助手跨頁存在。** `AssistantDock`置於路由內容之外，收合只隱藏、不卸載對話；圖表／其他頁面能用同一入口帶入問題。這解決的是使用者看案例、回看盤面、改草稿時不必重述背景。[dock](https://github.com/Pairlens/trading-terminal/blob/5e93f5ae911019d75a6c415216a28f33d857e104/apps/terminal/src/components/assistant-dock/assistant-dock.tsx#L4-L24)、[共用store與askAssistant](https://github.com/Pairlens/trading-terminal/blob/5e93f5ae911019d75a6c415216a28f33d857e104/apps/terminal/src/stores/assistant-store.ts#L10-L28)。Gold Desk適合採這個狀態所有權；首頁仍可有大聊天區，不必照搬浮動小球。
2. **畫面上下文是明確資料，不是模型猜畫面。** registry把掛載的surface之summary／detail收集成screen context，最多8個surface、每份detail截長；`get_screen`、`highlight_ui`有封閉動作入口。[screen-context](https://github.com/Pairlens/trading-terminal/blob/5e93f5ae911019d75a6c415216a28f33d857e104/apps/terminal/src/lib/assistant-core/screen-context.ts#L11-L54)、[terminal-tools](https://github.com/Pairlens/trading-terminal/blob/5e93f5ae911019d75a6c415216a28f33d857e104/apps/terminal/src/lib/assistant-core/terminal-tools.ts#L154-L223)。Gold Desk可只送目前週期、選取案例別名、快照ID、選取證據及草稿版本，數值仍由後端ledger提供；開圖／定位證據用小型白名單工具。
3. **會話與視窗狀態分開。** 一個store管視窗與作業狀態，另一個保存會話索引與每串訊息，localStorage延遲讀各串並處理上限；這是可借的拆分方式，不代表已替我們完成多人後端保存。[會話保存](https://github.com/Pairlens/trading-terminal/blob/5e93f5ae911019d75a6c415216a28f33d857e104/apps/terminal/src/stores/assistant-conversations-store.ts#L28-L40)、[讀取](https://github.com/Pairlens/trading-terminal/blob/5e93f5ae911019d75a6c415216a28f33d857e104/apps/terminal/src/stores/assistant-conversations-store.ts#L79-L112)。Gold Desk需按登入使用者保存，舊訊息中的委託卡只能查原後端狀態，不重新變成可執行的確認卡。
4. **交易提案與執行分離。** `buildTradingTools`的place/cancel先回提案，卡片再呼叫下層provider；可借提案、討論、確認三層，不把模型輸出當成交。[trading-tools](https://github.com/Pairlens/trading-terminal/blob/5e93f5ae911019d75a6c415216a28f33d857e104/apps/terminal/src/lib/copilot/trading-tools.ts#L12-L21)。

## 貼文需要修正的地方

- **並非永遠逐筆點確認。** 原碼有standing consent；若預先授權、提案新鮮且未執行，卡片effect可自動執行，還有paper/live的不同scope。[auto-confirm](https://github.com/Pairlens/trading-terminal/blob/5e93f5ae911019d75a6c415216a28f33d857e104/apps/terminal/src/components/copilot/copilot-order-card.tsx#L154-L171)、[consent-store](https://github.com/Pairlens/trading-terminal/blob/5e93f5ae911019d75a6c415216a28f33d857e104/apps/terminal/src/stores/trade-consent-store.ts#L6-L27)。Gold Desk現階段不採免確認／自動授權，也不擴大真實資金範圍。
- **有下層風險檢查，不等於與我們的後端權限等價。** provider檢查vault、ordersLocked和position size，但某些估值缺失採fail-open；它是local-first的架構，不能拿React內的guard直接替代我們公開後端的逐使用者授權、Decimal、UNKNOWN耐久日誌。[provider](https://github.com/Pairlens/trading-terminal/blob/5e93f5ae911019d75a6c415216a28f33d857e104/apps/terminal/src/lib/market-data-provider.tsx#L1687-L1730)。
- **不是可原樣接管的雲端後端。** README明示sign-in／跨裝置同步／news／hosted AI proxy所在App Server未納此repo；開發預設可連作者hosted API，不代表我們clone就擁有同一後端。[README](https://github.com/Pairlens/trading-terminal/blob/5e93f5ae911019d75a6c415216a28f33d857e104/README.md)。
- **整包移植成本高。** React19／TypeScript與我們相近，但使用Bun monorepo、TanStack Start、Zustand、AI SDK、Tauri、內部workspace packages及自家WebGL圖表，並非換幾個元件即可。Gold Desk先保留Vite／FastAPI／cTrader與Lightweight Charts。[terminal依賴](https://github.com/Pairlens/trading-terminal/blob/5e93f5ae911019d75a6c415216a28f33d857e104/apps/terminal/package.json)。

## 授權

根LICENSE是FSL-1.1-Apache-2.0。條文明列非商業教育／研究為permitted purpose，並對衍生再散布要求保留條款與版權；商業競爭用途有範圍限制，各版本兩年後取得Apache2的額外授權。因此不是「畢專一律不能用」，也不是「跟MIT一樣無條件搬」。目前建議先參考互動模式自行實作；若複製程式，按所取檔案與固定版本保留授權並確認團隊的發布用途。獨立圖表repo所稱MIT不覆蓋terminal程式。[LICENSE](https://github.com/Pairlens/trading-terminal/blob/5e93f5ae911019d75a6c415216a28f33d857e104/LICENSE.md#L27-L70)。

## 最小可採切片

共用會話狀態 → 元件式訊息與提案 → 目前畫面上下文 → 點證據定位圖表。浮動玻璃視窗、小球、動畫、多市場／外掛／自動策略不是這輪優先；網站主入口仍依使用者選定聊天＋精簡委託＋tick，K線按需要展開。


---

# NOMO：Gold Desk 對話式交易介面參考審查

研究日期：2026-10-23。範圍：公開 README、作者提供截圖與實際原始碼；唯讀下載，沒有安裝、執行、登入券商或送單。固定版本：`9479e6b27d8bac0b3742bb7042193df61b41ae38`。下列「已有」指程式碼可見，非本次已完成執行驗收。

## 結論

**適合拿來參考 Gold Desk 的對話工作台，不適合整包替換或直接公開架站。** 最有價值的是：一則對話能依序放文字、圖、確認卡；工具作業過程可見、完成後收合；聊天紀錄可恢復；同一確認卡呈現支持理由、反例與券商警告。這些能減少我們把盤面、案例、風險、算法說明一次鋪滿頁面的問題。

它不是現成的 cTrader 黃金即時平台，也沒有我們的歷史盤面相似檢索。它的行情工具內建 Polygon 美國股票歷史聚合棒／前一交易日資料；圖表元件沒有 tick 串流更新；後端是單使用者、沒有帳號權限的 localhost Express。應保留我們的 React/TS、FastAPI、cTrader、Decimal、已收棒快照與檢索規則，移植互動契約和部分前端元件。

## 實際可採納的部分

| 項目 | 程式實際做到什麼 | Gold Desk 建議怎麼用 |
|---|---|---|
| 對話內結構化區塊 | `MessageBlock` 是 text/chart/order 聯集；伺服器送不同 SSE 事件，前端直接畫元件，不從 Markdown 猜圖表或下單 | 擴成 text/market-summary/case-comparison/chart/draft。聊天短答＋一張案例卡，需要才展開圖或證據。圖表應保留「當時快照」，另設明確即時模式 |
| 工具進度 | 執行中顯示工具名稱與 running/done/error；完成後自動收合 | 改成「取得已收盤面 → 比對歷史案例 → 檢查草稿」三個實際進度。不要為了視覺效果新增多代理；中止應顯示已中止，不能沿用原版將 running 改成 done 的邏輯 |
| 確認卡 | 確認／拒絕、有效時間、拒絕理由，以及 thesis/bearCase/brokerWarnings 三欄 | 用「支持這個想法／相反訊號／相似案例差異與損益／待確認委託」。金額與手數從我們的草稿版本取得；拒絕只影響草稿，非替使用者取消已送券商委託 |
| 聊天紀錄 | 可收側欄、新對話、刪對話、重新載入恢復最新紀錄，生成完成後延遲400ms保存 | 接同學後端的 conversation/message API，記錄分析快照 ID、案例 ID、草稿版本。伺服器隔離每位使用者；畫面歷史不是成交真相 |
| 滾動與中止 | 固定 viewport 高度；使用者往上讀時不被串流強拉到底；有 Stop、中文輸入法 composition 保護 | 可直接借用這些細節，但整合我們已做的聊天高度調整；中止 LLM 不等於撤銷草稿，更不等於券商刪單 |
| 只讀工具／下單工具分級 | 提供模型的 schema 與執行時都檢查 tool tier，execution 只建立待確認提案 | 沿用概念，但保留我們的最小工具集與白名單，不把券商完整工具開給模型。Groq tool calling 需要 provider adapter，不能照貼 Anthropic SDK |

證據：

- [聊天區塊型別與上下文處理](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/frontend/src/components/Chat.tsx#L31-L89)、[事件轉成卡片](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/frontend/src/components/Chat.tsx#L242-L295)、[渲染三種區塊](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/frontend/src/components/Chat.tsx#L433-L484)。
- [工具進度收合與中止後狀態](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/frontend/src/components/ActivityPanel.tsx#L58-L80)。
- [確認卡的理由、反例、券商審查](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/frontend/src/components/OrderCard.tsx#L101-L174)。
- [聊天恢復、保存與閱讀時不強拉到底](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/frontend/src/components/Chat.tsx#L120-L178)、[中文輸入法和Stop](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/frontend/src/components/ChatInput.tsx#L11-L38)。
- [工具分級與輸出分流](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/server/src/tools/registry.ts#L11-L62)、[執行時再次檢查](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/server/src/services/chat.ts#L57-L101)。

## 確認門：不是只有 README 說有

1. 模型呼叫 `proposeOrder/proposeCancel` 只寫 pending_orders，回給模型「尚未送出」。
2. 保存參數和五分鐘到期時間。確認時只用 ID，不讓用戶端另帶一組價格手數取代已審閱內容。
3. SQLite 以條件 UPDATE 將 awaiting_confirmation 原子轉成 confirmed；狀態與到期檢查使相同提案無法重複確認。
4. 只有確認服務呼叫券商執行函式；訂單內容來自保存列，送單使用待確認單 UUID 作 ref_id。
5. 拒絕與過期不進入執行路徑。研究代理產生的提案必須先完成券商 review 才建卡，review 失敗不產生提案。

證據：[提案](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/server/src/services/executionGate.ts#L148-L190)、[原子狀態轉移與到期](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/server/src/db/pendingOrders.ts#L112-L145)、[確認後才呼叫券商](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/server/src/services/executionGate.ts#L294-L325)、[保存參數與 ref_id](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/server/src/services/robinhoodMcp.ts#L329-L364)、[研究提案先審查](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/server/src/agents/proposal.ts#L20-L45)。

這些是值得取用的模式，但我們已經有草稿→明確確認、防重送及失聯未知結果保護，沒有必要倒退成整包改用它。原碼把任何執行例外標成 failed，正常 ack 直接標 executed；這不等於已核實成交，遇上傳輸斷線但券商可能收到時，Gold Desk 應維持既有 UNKNOWN／對帳流程，並區分已送、受理、成交和拒絕。[狀態處理證據](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/server/src/services/executionGate.ts#L305-L324)。

**「必須人工確認」的實際邊界：** 所查生產程式只有 executionGate 呼叫 `executeConfirmedOrder`；模型的同名 place/cancel 工具其實包的是提案，所以一般模型工具路徑不能直接送單。但 `POST /api/orders/:id/confirm` 本身沒有身份、角色或人類來源驗證；任何能接觸此單人 HTTP API 的客戶端拿到 ID 都能呼叫，因此不能把它描述成「技術上證明必有本人點擊」。它有資料庫狀態比對，但沒有草稿 version／If-Match 欄位，也沒有券商結果 UNKNOWN 後自動對帳的生命週期。送單的 `ref_id` 是程式有帶，不等於本次已核實上游券商實際去重效果；取消分支只帶 order_id，未帶同樣的 ref_id。來源：[工具只建提案](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/server/src/tools/executionTools.ts#L10-L57)、[沒有身份檢查的 confirm route](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/server/src/routes/orders.ts#L52-L65)、[狀態欄位而非版本欄位](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/shared/src/orders.ts#L11-L49)、[取消與送單分支](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/server/src/services/robinhoodMcp.ts#L415-L454)。

## 不能照搬或不能宣稱的部分

- **即時行情不是現成提供。** `get_quote` 的工具描述明說 end-of-day、not live，來源是 previous close；圖表載入 REST 聚合資料後 `setData`，沒有 `update` 或報價訂閱。改用我們 cTrader 5m/15m/1h native bars、forming bars 和 tick 推送。不能把 README 的 market data 寫成已驗證即時能力。[行情工具](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/server/src/tools/marketData.ts#L153-L170)、[REST資料來源](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/server/src/services/polygon.ts#L94-L157)、[圖表初始化](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/frontend/src/components/ChartBlock.tsx#L57-L129)。
- **不能直接公開部署。** 主程式明示單人無認證，HOST 不是 loopback 就退出；HTTP routes 沒有使用者或角色驗證。完整移植要補登入、角色、帳戶隔離、確認權限、節流與審計，不能單純改 `0.0.0.0`。[設定限制](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/server/src/config.ts#L9-L17)、[routes](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/server/src/app.ts#L13-L31)。
- **密鑰儲存不符合我們現行契約。** 原碼把 provider secret 直接插入本機 SQLite，所看路徑沒有加密步驟；我們應維持環境／雲端 Secret，不移植它的憑證頁儲存方法。[實際寫入](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/server/src/db/credentials.ts#L5-L29)。
- **不是相似盤面檢索工具。** `search_history` 是聊天文字 FTS，不是歷史K線；而查詢正規化會移除非 `a-z0-9` 字元，直接照抄會令純中文搜尋變空。[搜尋程式](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/server/src/db/search.ts#L44-L69)。我們的 context_contract_v1 檢索應獨立保留，結果透過一個只讀工具接回聊天。
- **股票單型不能照抄成黃金 CFD。** 它處理 share quantity 或 dollar notional、stock ticker、stop price；不能把 stop-market 的觸發價當成持倉停損。cTrader lots/units、SELL平空、positionId、SL/TP、合約規格與最小量必須用我們後端。[輸入解析](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/server/src/services/executionGate.ts#L57-L133)。
- **LLM 自由回答仍需我們的數值依據保護。** 它的 chat loop 直接把模型 text delta 傳到前端；圖和指標的來源是程式，並不代表每句自然語言都經過數值核實。我們應保留 facts token／ledger、資料新鮮度與已收棒原則。[文字串流](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/server/src/services/chat.ts#L177-L248)。
- **多代理研究不是必要第一步。** 此處主要是美股基本面、財報、SEC與新聞；對單一 XAUUSD 專題直接搬來會增加耗時、依賴與說明負擔。可以借「支持／反對」的呈現，但不必先建 technical/fundamentals/skeptic 多套代理。研究流程最終仍把自由 thesis 與 bearCase 放到卡片，沒有替我們驗證歷史相似度的標準答案。
- **歷史回測功能不等於我們的歷史交易盤面回放。** 它的策略工具是股票規則回測；不提供我們需要的逐案券商時鐘、參考棒、成熟時間或歷史案例群驗證。不可把共用的 backtest 一詞當功能已替代。

## 最小移植順序

1. 先只改呈現：聊天短答、案例比較卡、按需圖、委託卡；首頁維持「聊天＋精簡委託＋tick」，不改成圖表優先。
2. 加入真實的查詢進度、停止、錯誤重試與不強制捲底。先用我們既有 API，避免第一輪同時換模型與券商。
3. 同學後端準備好後接聊天保存、使用者／角色與分析快照。歷史訊息中的已確認卡必須重新讀後端訂單狀態，不能依本機保存的卡片當真。
4. 最後才考慮 Groq tool routing，僅開 `get_market_snapshot`、`retrieve_cases`、`render_chart`、`update_draft`；確認與送單不列為模型工具。

## 依賴與授權

技術相容度：前端 React18、TS5.7、Vite6、Lightweight Charts5.2、react-markdown；後端 Node20+/Express4、Anthropic SDK、MCP SDK、better-sqlite3。React元件可改寫對接，但套件版本與我們既有 chart API 先比對，不宜整份 lockfile 合併。[frontend/package.json](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/frontend/package.json)、[server/package.json](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/server/package.json)。

專案 LICENSE 是 MIT，複製實質程式碼或大量元件應保留 `Copyright (c) 2026 NOMO contributors` 和完整授權文字，可在 THIRD_PARTY_NOTICES 記錄來源與固定版本。MIT不等於取得券商、資料商或其商標的使用權；Lightweight Charts等依賴另外遵守各自條款，不應自行刪原本 attribution。[LICENSE](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/LICENSE#L1-L21)。這是依 repository 文字整理，不是法律意見。

`package-lock.json` 實際鎖定：Lightweight Charts **5.2.0 / Apache-2.0**；React **18.3.1 / MIT**；react-markdown **10.1.0 / MIT**；Anthropic SDK **0.112.5 / MIT**；MCP SDK **1.29.0 / MIT**；better-sqlite3 **11.10.0 / MIT**。這不是整份依賴的完整授權稽核。Lightweight Charts 5.2.0 的官方 LICENSE 要保留授權及相關 NOTICE，改過其檔案應註明改動；官方 README另要求在使用者可見頁面放 TradingView attribution notice 與連結。若只移植 NOMO 元件而仍使用我們原有 chart package，應核對我們實際安裝版本的條款，不能因 NOMO 主專案是 MIT 就把圖表依賴也當 MIT。[lockfile](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/package-lock.json#L3378-L3385)、[圖表 LICENSE](https://github.com/tradingview/lightweight-charts/blob/v5.2.0/LICENSE#L79-L109)、[圖表 NOTICE](https://github.com/tradingview/lightweight-charts/blob/v5.2.0/NOTICE)、[官方 attribution 說明](https://github.com/tradingview/lightweight-charts/blob/v5.2.0/README.md#license)。

已有 mock 測試涵蓋確認前不送、二次確認衝突、拒絕、過期、券商 review 失敗等，可作為我們整合測試的情境清單；**本次沒有執行其測試，也未驗證真實 Robinhood 送單或作者效能／費用主張**。[測試來源](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/server/tests/services/executionGate.test.ts#L61-L299)。

作者介面截圖僅作布局參考，非本次執行畫面：[overview.png](https://github.com/Ut8v/NOMO/blob/9479e6b27d8bac0b3742bb7042193df61b41ae38/docs/screenshots/overview.png)。


---

# 圖表與回放專案來源核查（2026-10-23）

此文件是來源研究，不是執行／整合驗收。已唯讀 clone 原始碼、讀元件與資料流；未 npm install、執行陌生程式、呼叫券商、LLM、實際下單或改 Gold Desk 產品。以下連結固定在本次 SHA，不只依 README 推論。

## 結論

**OpenCharts 比較適合借用「券商工作台的局部元件與圖上操作」；Ez_backtest 比較適合參考「選日期、回放、點交易紀錄回到圖」的互動。兩者都不是 Gold Desk 對話首頁的直接替代品。** 首頁應維持聊天＋共用草稿＋tick，圖表按需展開，把專業圖表工具集中在看盤／回放頁。整站搬過來會再次變成圖表主導、資訊過多的終端。

優先順序：① 訂單草稿與圖上進出／停損停利的同步預覽，② 點案例開圖並保留原聊天與分析快照，③ 簡潔回放控制列與交易時間定位，④ 需要時才開繪圖工具。深度梯與加密貨幣資金流不是目前應搬入的內容。

## 1. OpenCharts

- 原始碼：https://github.com/dylanpersonguy/OpenCharts
- 本次 SHA：`d3fc63cc002e6e651801be6e952e7514e58fa5fe`。
- 套件版本 0.3.0，React peer >=18.2、實際 dev React19，Vite6、TypeScript5.7；圖表依賴 **Lightweight Charts4.2**，Gold Desk 現在是5，因此圖表 API／primitive 類型需遷移，不能直接假設相容。[package.json](https://github.com/dylanpersonguy/OpenCharts/blob/d3fc63cc002e6e651801be6e952e7514e58fa5fe/package.json#L71-L115)

### 已看到的可用實作

| 能力 | 原始碼核查 | 對 Gold Desk 的用法 |
|---|---|---|
| 可拆工作台面板 | `Chart`、`OrderTicket`、`Watchlist`、`Positions`、`Orders` 分開匯出，透過 TerminalProvider 共用上下文。[panels.tsx](https://github.com/dylanpersonguy/OpenCharts/blob/d3fc63cc002e6e651801be6e952e7514e58fa5fe/src/terminal/panels.tsx#L10-L130) | 參考「共用狀態、按需要放置面板」，不要用完整 Terminal 取代聊天首頁。 |
| 清楚的行情／交易邊界 | `MarketDataSource` 提供歷史 getCandles、quote、subscribe、connection state；`trading` 可省略成唯讀圖表，另有 storage driver。[types.ts](https://github.com/dylanpersonguy/OpenCharts/blob/d3fc63cc002e6e651801be6e952e7514e58fa5fe/src/adapter/types.ts#L27-L90)、[trading/storage](https://github.com/dylanpersonguy/OpenCharts/blob/d3fc63cc002e6e651801be6e952e7514e58fa5fe/src/adapter/types.ts#L141-L184) | 值得採 adapter 概念接我們的 FastAPI SSE／cTrader，但金額和手數要維持 Gold Desk Decimal 字串契約；它的 number schema 不能直接當財務後端。 |
| 市價／限價／停損委託、TP/SL、確認視窗 | OrderPanel 有價格／數量檢查、單型欄位和 `onConfirmOrder` callback。[OrderPanel](https://github.com/dylanpersonguy/OpenCharts/blob/d3fc63cc002e6e651801be6e952e7514e58fa5fe/src/pages/trading/OrderPanel.tsx#L63-L179) | 借用輸入階層與預覽；應接我們同一份待確認草稿，不另生一份 UI 自己的下單 state。 |
| 圖上拖 TP/SL | `useSlTpDrag` 找8px內的價格線，拖動時暫停圖表平移、預覽價格與損益，mouseup 才叫 callback。[useSlTpDrag](https://github.com/dylanpersonguy/OpenCharts/blob/d3fc63cc002e6e651801be6e952e7514e58fa5fe/src/pages/trading/useSlTpDrag.ts#L74-L205) | 是最值得轉用的互動。Gold Desk 應改成「拖動只修改草稿 → 顯示差額 → 人工確認」，不能照它直接改持倉。 |
| 可調底部持倉區 | TradingPage 分離 chart 與 bottomPanel，拖曳高度約100–600px。[resize](https://github.com/dylanpersonguy/OpenCharts/blob/d3fc63cc002e6e651801be6e952e7514e58fa5fe/src/pages/TradingPage.tsx#L104-L144) | 看盤頁可參考。Gold Desk 聊天已有尺寸把手，無需另裝整套狀態。 |
| 回放日期、播放／暫停／倍速、可拖進度 | ReplayHUD＋ReplayScrubber；後者 pointer capture、時間軸 seek 並疊加交易點。[HUD](https://github.com/dylanpersonguy/OpenCharts/blob/d3fc63cc002e6e651801be6e952e7514e58fa5fe/src/pages/trading/ReplayHUD.tsx#L20-L56)、[Scrubber](https://github.com/dylanpersonguy/OpenCharts/blob/d3fc63cc002e6e651801be6e952e7514e58fa5fe/src/pages/trading/ReplayScrubber.tsx#L14-L105) | 合適移植到歷史案例回放頁；需沿用查詢截止與已收棒規則，不將未來交易結果帶入進場檢索。 |

### 必須澄清的展示內容

1. **預設 demo 不是真實即時行情。** `feed.ts` 每600ms取內建歷史1m收盤，從尾端往前走、碰端點折返，報價加上人工 spread、timestamp 用 Date.now()。它很像即時終端，但不能拿這段接到我們「即時」模式。[feed.ts](https://github.com/dylanpersonguy/OpenCharts/blob/d3fc63cc002e6e651801be6e952e7514e58fa5fe/src/services/demo/feed.ts#L6-L95) demo 商品是 BTC/ETH/SOL/BNB/XRP/ADA，不是已做好黃金券商接入。[instruments](https://github.com/dylanpersonguy/OpenCharts/blob/d3fc63cc002e6e651801be6e952e7514e58fa5fe/src/services/demo/instruments.ts#L29-L36)
2. **Depth of Market 是模擬深度。** `depthAt` 對價格做 hash，產生固定偽亂數量；函式只收到 tick bid/ask，沒有真正逐檔委託簿。即使接上真實頂層報價，這面板仍不會自動變真實深度。[DOMPanel](https://github.com/dylanpersonguy/OpenCharts/blob/d3fc63cc002e6e651801be6e952e7514e58fa5fe/src/pages/trading/DOMPanel.tsx#L4-L77)
3. **交易確認不是我們的安全契約。** 市價 oneClick 會跳過確認；沒給 onConfirmOrder 時也直接送。TP/SL拖動 callback 對應 `modifyPositionLevels`，直接 `api.modifyPosition`。需要更換這兩處，保留 draft version、人工確認、防重送與 UNKNOWN 耐久日誌。[OrderPanel](https://github.com/dylanpersonguy/OpenCharts/blob/d3fc63cc002e6e651801be6e952e7514e58fa5fe/src/pages/trading/OrderPanel.tsx#L153-L178)、[modify](https://github.com/dylanpersonguy/OpenCharts/blob/d3fc63cc002e6e651801be6e952e7514e58fa5fe/src/terminal/context.tsx#L245-L265)
4. paper engine 確實有 pending limit/stop lifecycle，但 market 使用 mid、沒有 Gold Desk 的券商伺服器確認／使用者隔離；不是完整 cTrader DEMO execution。優先留我們 backend，不替換。[engine開頭](https://github.com/dylanpersonguy/OpenCharts/blob/d3fc63cc002e6e651801be6e952e7514e58fa5fe/src/services/demo/engine.ts#L1-L22)

### 授權與直接使用可行性

root [LICENSE](https://github.com/dylanpersonguy/OpenCharts/blob/d3fc63cc002e6e651801be6e952e7514e58fa5fe/LICENSE) 是 MIT，可作重用候選；若複製實質程式碼要保留 copyright/license。另 [NOTICE](https://github.com/dylanpersonguy/OpenCharts/blob/d3fc63cc002e6e651801be6e952e7514e58fa5fe/NOTICE) 明列圖表及部分 plugins 源自 TradingView Lightweight Charts（Apache2），需保留 NOTICE、相關標示與使用者可見 TradingView連結。不是整個repo標MIT就能刪第三方標示。

**建議小量移植，非整套安裝。** 完整 library 雖有 exports／provider，會引入 React Query、Zustand、Radix、Tailwind等額外依賴；也會同時有LWC4與現有LWC5，形成重複bundle／CSS與API整合成本。最小切片是把拖線邏輯移植到現有圖表（先確認授權／v5），其餘用本專案元件重做。README亦說套件尚未發布，不能預設 npm install 便能取到這個版本。[README](https://github.com/dylanpersonguy/OpenCharts/blob/d3fc63cc002e6e651801be6e952e7514e58fa5fe/README.md)

## 2. Ez_backtest

- 原始碼：https://github.com/awaqawaqawaq/Ez_backtest
- 本次 SHA：`0d0e6a4d2a5c20380171abf4646e3d126fa48479`。
- React19.2、LWC5.1、Vite7、TS5.9，圖表主版本比較接近 Gold Desk；但同時依賴其他kline套件、Tailwind4、Zustand、React Query、dnd-kit，不建議整包搬入。[package](https://github.com/awaqawaqawaq/Ez_backtest/blob/0d0e6a4d2a5c20380171abf4646e3d126fa48479/package.json#L15-L43)
- **本次 `git ls-files '*LICENSE*' '*NOTICE*' '*COPYING*'` 無結果，package沒有license欄位，root/README也未給明確重用授權。** 公開可看不等於已取得複製改作授權。現階段作互動／架構參考；要複製程式碼或素材，先向作者取得明確授權。相依套件授權也需另查，未在此宣稱全部清查完畢。

### 真正有實作的部分與適用方式

| 能力 | 原始碼 | 建議 |
|---|---|---|
| 回放／即時／日期跳轉分工 | Header 回放控制、useSimulation接provider的start/pause/resume/stop，chartDataProvider在cursor切資料。[Header](https://github.com/awaqawaqawaq/Ez_backtest/blob/0d0e6a4d2a5c20380171abf4646e3d126fa48479/src/components/TradingChart/Header.tsx#L577-L619)、[provider](https://github.com/awaqawaqawaq/Ez_backtest/blob/0d0e6a4d2a5c20380171abf4646e3d126fa48479/src/components/TradingChart/controllers/chartDataProvider.ts#L255-L303)、[visible slice](https://github.com/awaqawaqawaq/Ez_backtest/blob/0d0e6a4d2a5c20380171abf4646e3d126fa48479/src/components/TradingChart/controllers/chartDataProvider.ts#L424-L450) | 回放頁可仿其短控制列，不將大量設定塞入首頁。資料切片有hide future設計，但未整套驗證所有指標／其他元件無資訊穿越。 |
| 輸入日期後圖表定位 | `useHeaderTimeJump` 解析輸入為GMT+8、請求資料後等資料涵蓋目標再跳可視範圍。[hook](https://github.com/awaqawaqawaq/Ez_backtest/blob/0d0e6a4d2a5c20380171abf4646e3d126fa48479/src/components/TradingChart/hooks/useHeaderTimeJump.ts#L13-L111) | 借互動流程，Gold Desk需明示顯示時區並沿用來源UTC，不複製固定減8h處理券商時間。 |
| 市價／限價、圖上TP/SL、手動平倉 | TradeToolbarPrimitive有pending limit、trade lifecycle，圖上選價；dataUpdated會檢查棒high/low。[primitive](https://github.com/awaqawaqawaq/Ez_backtest/blob/0d0e6a4d2a5c20380171abf4646e3d126fa48479/src/components/TradingChart/plugins/trade-toolbar/primitive.ts#L279-L347) | 借圖上預覽／調整手勢；不替換我們後端。它的撮合是前端模擬，不是券商成交。 |
| 紀錄與圖連動 | useTradeJournalSync把開／平事件寫journal、生成marker，點交易可跳進出場區域；journal面板有JSON匯出匯入。[sync](https://github.com/awaqawaqawaq/Ez_backtest/blob/0d0e6a4d2a5c20380171abf4646e3d126fa48479/src/components/TradingChart/hooks/useTradeJournalSync.ts#L34-L126)、[匯出](https://github.com/awaqawaqawaq/Ez_backtest/blob/0d0e6a4d2a5c20380171abf4646e3d126fa48479/src/components/TradingChart/trade-journal/TradeJournalPanel.tsx#L722-L774) | **最適合Gold Desk案例功能**：案例卡按「看當時盤面」打開同頁雙週期、標原進出點、可切回討論。資料與snapshot仍由我們API供應。 |
| 即時棒平滑 | RealtimeKlineAnimator在同根棒更新時 rAF插值open/high/low/close及量欄位；新棒直接同步，補高低值合法關係。[animator](https://github.com/awaqawaqawaq/Ez_backtest/blob/0d0e6a4d2a5c20380171abf4646e3d126fa48479/src/components/TradingChart/controllers/realtimeKlineAnimator.ts#L34-L119)、[插值](https://github.com/awaqawaqawaq/Ez_backtest/blob/0d0e6a4d2a5c20380171abf4646e3d126fa48479/src/components/TradingChart/controllers/realtimeKlineAnimator.ts#L151-L174) | 參考渲染平滑，但分析／送單仍用原始權威數值；動畫中間值不是新真實tick，不能拿去觸發案例檢索或成交。 |

### 不能照搬的假設

- 真實市場資料接的是 **Binance USDT perpetual**：REST fapi klines，WS kline／aggTrade，不是cTrader黃金；資金流／taker量含義也不等於XAUUSD的tick volume。[REST](https://github.com/awaqawaqawaq/Ez_backtest/blob/0d0e6a4d2a5c20380171abf4646e3d126fa48479/src/components/TradingChart/data/queries/klineQuery.ts#L5-L61)、[WS](https://github.com/awaqawaqawaq/Ez_backtest/blob/0d0e6a4d2a5c20380171abf4646e3d126fa48479/src/components/TradingChart/live/binanceRealtimeGateway.ts#L162-L183)
- 模擬判斷同一棒同時碰TP/SL時，程式先檢查TP、`else if`才SL，無法得知該棒內真正先後。這不能拿來宣稱可靠回測績效；Gold Desk後端要保持自己的保守撮合規則。[觸發順序](https://github.com/awaqawaqawaq/Ez_backtest/blob/0d0e6a4d2a5c20380171abf4646e3d126fa48479/src/components/TradingChart/plugins/trade-toolbar/primitive.ts#L321-L345)
- journal P/L = price delta ×qty，是通用前端模型，不含XAU合約乘數、券商費用或匯率，不能直接當我們的USD損益。[calcPnl](https://github.com/awaqawaqawaq/Ez_backtest/blob/0d0e6a4d2a5c20380171abf4646e3d126fa48479/src/components/TradingChart/trade-journal/store.ts#L87-L108)
- 尚未執行其測試、建置或操作demo，因此只能說「來源已有這段實作」，不能說其流暢度／部署／回放正確性已實測通過。

## 建議的整合邊界

第一階段先畫 Gold Desk 自己的三個互動：聊天出案例卡 → 同頁展開當時盤面；點訂單價位 → 圖上預覽；拖TP/SL → 只回寫同一草稿、確認才送。這能改善目前「文字很多、分頁與資訊分散、不跟手」，而不是再加更多面板。

第二階段才做專用圖表／回放工作區：上方一列日期／播放／速度／時間，中央圖，側邊案例摘要，底部交易紀錄可收合。OpenCharts提供可合法重用的局部實作候選，Ez提供案例回看流程概念；兩者都保留原FastAPI、cTrader、檢索與提交日誌，不改成瀏覽器paper引擎。

本次本機clone只存 `product/private/reference_projects_20261023/repos/`，未加入公開白名單或產品依賴。沒有更動原始交易資料或根目錄媒體。


---

# Supporting projects：交易分析、圖表與 cTrader 接入查核

查核日期：2026-10-23。範圍是使用者附件中的 TradingAgents、Lightweight Charts、cTrader 範例及未附網址的 QuantDesk。這份是設計研究；沒有安裝／執行第三方套件、呼叫券商、送單、改產品或推送。

## 建議先讀的結論

1. **Lightweight Charts 直接沿用現有套件與元件**，補強「點分析文字→定位圖上證據→回到草稿」互動。Gold Desk 已是 React／TypeScript，lockfile 實際版本已是 5.2.1；不需要為了外觀換整套圖表。
2. **TradingAgents 借用分析的內容結構**：支持此想法、反對訊號、資料依據、尚待確認條件。不要把完整多代理辯論管線搬進即時聊天，會增加等待、字量與維護，也沒有證據顯示能改善我們的案例相似判別。
3. **OpenApiPy 作為既有券商接入層的參考**，不是新網站 UI 模板。現行產品本來就在用它；重點是前端可理解的連線／驗證／訂閱狀態，以及斷線後安全恢復。
4. **QuantDesk 身分未確認**。網路上有多個完全不同的同名產品；沒有使用者原始連結，不能斷言某個候選就是附件指的專案。

## 證據層級與版本

| 專案 | 本輪取得範圍 | 固定版本／授權 | 可以證實什麼 |
|---|---|---|---|
| TauricResearch/TradingAgents | README、淺層 clone、關鍵 Python／HTML 程式 | commit `e8f5503e9b86d5c2710b0c76b1f686703968c9df`；`__version__ = 0.7.0`；Apache-2.0 | 實際分析圖、結構化提案、終端進度與靜態報告機制 |
| spotware/OpenApiPy | README、官方文件、淺層 clone、連線／範例程式 | commit `e944996e6fe9436b8b4a1b668da4ac41a826bb85`；MIT；repo pyproject version 0.0.0 不能當 PyPI 發布版號 | SDK 請求對應、回呼、心跳、驗證與訂閱範例 |
| tradingview/lightweight-charts | 官方 API／tutorial、master 原始檔，及本機目前使用狀況 | 官方 master package 5.2.1；Apache-2.0＋NOTICE／連結署名要求；本機 lockfile 也是 5.2.1 | API 支援能力；未把官方示例當我們網站已完成的新功能 |
| QuantDesk 多個候選 | 官網／GitHub README、部分 package／檔案目錄 | 各案不同，見後文 | 僅能辨識候選與功能定位，未本機執行或完整程式稽核 |

本輪 clone 只存 `product/private/reference_projects_20261023/repos/TradingAgents/` 與 `.../OpenApiPy/`，沒把第三方程式放入正式依賴。以下行號為固定 commit 的程式行號；不是 runtime 驗收。第三方 README 的功能自述不代表效果已獨立證實。

## 1. TradingAgents：取內容設計，保留我們自己的執行層

官方 repo：[TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)。

### 實際程式是什麼

- [`graph/setup.py` L109–185](https://github.com/TauricResearch/TradingAgents/blob/e8f5503e9b86d5c2710b0c76b1f686703968c9df/tradingagents/graph/setup.py#L109-L185) 建立 LangGraph：選擇的分析師→多空研究→研究主管→交易提案→風險討論→投資組合主管。它是研究／決策報告流程，不是可直接替換 Gold Desk 的聊天工作台。
- [`agents/researchers/bull_researcher.py` L9–63](https://github.com/TauricResearch/TradingAgents/blob/e8f5503e9b86d5c2710b0c76b1f686703968c9df/tradingagents/agents/researchers/bull_researcher.py#L9-L63) 與 [`bear_researcher.py` L9–65](https://github.com/TauricResearch/TradingAgents/blob/e8f5503e9b86d5c2710b0c76b1f686703968c9df/tradingagents/agents/researchers/bear_researcher.py#L9-L65)：不同立場讀同批報告並回應對手。借鏡點是**同一資料下呈現相反證據**；不是兩個模型互相認同就算證實。
- [`agents/schemas.py` L95–213](https://github.com/TauricResearch/TradingAgents/blob/e8f5503e9b86d5c2710b0c76b1f686703968c9df/tradingagents/agents/schemas.py#L95-L213) 有 Pydantic 的研究計畫／交易提案，欄位包括 action、reasoning、選填 entry_price、stop_loss、position_sizing，再轉為固定格式文字。這適合借成卡片資料契約，但我們的價格、手數仍要用 Decimal 字串並由後端驗證。
- [`cli/display.py` L26–92、160–173](https://github.com/TauricResearch/TradingAgents/blob/e8f5503e9b86d5c2710b0c76b1f686703968c9df/cli/display.py#L26-L92) 用有限長度訊息 buffer、agent 狀態、報告區，Rich 終端排版；不是 React chat UI。
- [`report_html.py` L248–295](https://github.com/TauricResearch/TradingAgents/blob/e8f5503e9b86d5c2710b0c76b1f686703968c9df/tradingagents/report_html.py#L248-L295) 產生含目錄／分析日期／評等／區塊的靜態 HTML 報告；頁面 CSP 禁止 script。不能把這個 HTML 報告當成已有即時委託與人機互動系統。

### Gold Desk 可採納

**分析卡片以三區為主**：支持你的想法／相反訊號／下一個觀察條件。每個句子掛自己的證據 ID，按一下可以開同一快照的圖，預設不把多空完整辯論逐字輸出。

**工作狀態用使用者任務命名**：讀取盤面、比較案例、整理回覆；不要把「Bull Researcher→Risk Agent」全塞上畫面。它的進度觀念有用，但角色數量不等於使用者需要看到的步驟。

**交易提案是待確認物件**：先短文字討論，再顯示做多／做空、單型、手數、入場、SL／TP 的可編輯卡片。與常駐委託區共用同份草稿；修改後重新檢查，人工確認才成交。此為我們的整合建議，不是 TradingAgents 已替我們提供的券商防重送機制。

### 不建議直接導入

不採「完整多代理鏈就是產品核心」：它會增加模型呼叫及序列階段，與使用者希望即時、簡潔、互動順手的目標有衝突。其股票／基本面 prompt 亦需重新適配 XAUUSD，不能原樣套用。沒有執行本輪框架，因此不報實測延遲／正確率。

授權可檢查 [固定版 LICENSE](https://github.com/TauricResearch/TradingAgents/blob/e8f5503e9b86d5c2710b0c76b1f686703968c9df/LICENSE)。若複製程式應保留授權與適用通知；這輪只研究。

## 2. Lightweight Charts：最適合直接延伸的既有基礎

官方 [repo](https://github.com/tradingview/lightweight-charts)、[API](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/ISeriesApi)、[plugin guide](https://tradingview.github.io/lightweight-charts/docs/plugins/intro)。

### 可以直接用哪些能力

| 互動 | 官方 API／例子 | Gold Desk 用途 |
|---|---|---|
| tick 更新末根 K 棒、量柱 | [`ISeriesApi.update`](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/ISeriesApi#update) | 保留縮放，更新同時點末棒；不是每次重建整張圖 |
| 入場、SL、TP、支撐壓力線 | [`createPriceLine`](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/ISeriesApi#createpriceline) | 點「上方壓力」時只強調該條線與對應說明 |
| 進出場或突破標記 | [Series markers tutorial](https://tradingview.github.io/lightweight-charts/tutorials/how_to/series-markers) | 讓案例與當前圖能看出比較的是哪個已收時點 |
| 價量分區 | [Price and volume tutorial](https://tradingview.github.io/lightweight-charts/tutorials/how_to/price-and-volume) | tick 量柱與價格分開尺度，避免量把 K 線壓扁 |
| 點圖／十字線帶回聊天 | [`IChartApiBase`](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/IChartApiBase) 的 click／crosshair 事件 | 使用者點某棒後問「這裡為何沒突破」，附該棒時間，而非模型猜圖 |
| 區間框、可互動工具提示 | [Series primitive／pane primitive](https://tradingview.github.io/lightweight-charts/docs/plugins/intro) | 固定區間、事件範圍、目前選中的證據；需要自行實作資料與互動 |

現有程式 `frontend/src/AnalysisChart.tsx` L11–23 已畫 MA、價位線、marker、SVG 區間及 focus；`LiveCandleChart.tsx` L16–46 已有量柱、update、動畫。真正缺口偏向**把聊天中的某個結論連到具體圖層，圖與草稿協作，控制顯示密度**，不是換圖表套件。

可做成「聊天預設無大圖；按證據／看圖後在同一工作台打開」，同時保留草稿與輸入。比較歷史案例時使用兩欄同尺度的當前／歷史 5m＋1h，避免一次四張大圖擠壓聊天。這是建議互動，不宣稱已實作。

**圖表不提供資料或成交能力**：官方 API 是繪圖介面。cTrader 的歷史棒、tick、帳戶／委託仍由既有後端提供；Lightweight Charts 不會自動附送交易所市場資料、TradingView 全部指標、完整券商交易終端。

授權：[README License 段](https://github.com/tradingview/lightweight-charts#license) 與 [NOTICE](https://github.com/tradingview/lightweight-charts/blob/master/NOTICE) 要求署名及 TradingView 連結。保留現有 attributionLogo 並檢查 NOTICE 的展示；這輪沒有以研究結果宣稱法律合規已全面審完。

## 3. cTrader：正確參考專案是 OpenApiPy，Algo Samples 是另一用途

### OpenApiPy 實際內容

- [官方 README](https://github.com/spotware/OpenApiPy)：Twisted 非同步 Python SDK，包含 Protobuf 訊息。
- [`ctrader_open_api/client.py` L9–18、29–69](https://github.com/spotware/OpenApiPy/blob/e944996e6fe9436b8b4a1b668da4ac41a826bb85/ctrader_open_api/client.py#L9-L69)：Twisted ClientService、連接／斷開／收訊回呼，clientMsgId 對應 Deferred，response timeout；斷線時清 pending map。SDK 管傳輸，不替產品判斷 UNKNOWN 委託是否可重送。
- [`tcpProtocol.py` L29–74](https://github.com/spotware/OpenApiPy/blob/e944996e6fe9436b8b4a1b668da4ac41a826bb85/ctrader_open_api/tcpProtocol.py#L29-L74)：發送佇列、每秒發送數控制、空閒心跳、解碼收訊。這是穩定串流基礎，不是前端動畫本身。
- [`samples/ConsoleSample/main.py` L46–74、130–135、175–208](https://github.com/spotware/OpenApiPy/blob/e944996e6fe9436b8b4a1b668da4ac41a826bb85/samples/ConsoleSample/main.py#L46-L74)：應用驗證、帳戶驗證、spot 訂閱、歷史棒與 tick 請求；L210–245 另有下單／平倉範例。範例的浮點價格與簡單 CLI 不能直接取代產品的 Decimal、草稿版本、人工確認、防重送與耐久 journal。

[SDK Client 文件](https://spotware.github.io/OpenApiPy/client/) 說明傳輸重連抽象；**連線重新接通不等於應用已重新驗證、訂閱與補齊缺棒**。此結論是讀 Client 與 ConsoleSample 的程式責任分工所得。應用應維護 wanted subscriptions／generation、斷線時標記舊價、驗證成功後恢復，再補缺棒；交易結果不明不得自動重送。

[官方連線文件](https://help.ctrader.com/open-api/connection/) 區分 SSL TCP 與 WebSocket；保留後端常駐 owner，由網頁訂閱我們後端的 SSE／WebSocket，不讓每個瀏覽分頁持有券商憑證。

### 適合借到畫面的狀態

`連線中 → 帳戶驗證中 → 載入 K 棒 → 已連線`；斷線後保留畫面並標「報價已停止／最後更新時間」，重新驗證後再恢復互動。報價可看、盤面分析可用、允許 DEMO 送單，是三種不同狀態，不要只用一顆綠點混在一起。

### 與 ctrader-algo-samples 的差別

[spotware/ctrader-algo-samples](https://github.com/spotware/ctrader-algo-samples) 根目錄是 Robots／Indicators／Plugins，README 定義是 cTrader Algo API 的 cBot／指標範例。它適合參考**在 cTrader 內跑的指標／cBot**，不是 React／FastAPI 網站的 Open API 連線 SDK，也不是完整聊天機器人模板。repo 標示 MIT；這輪只看索引／README，沒有逐個機器人稽核。

tick 量定義仍依 [ProtoOATrendbar](https://help.ctrader.com/open-api/model-messages/#protooatrendbar)：volume 是 bar volume in ticks；不能把其他交易委託 volume 欄位的單位套過來。量能分析已具備，不因這次參考改案例排名。

## 4. QuantDesk：先釐清對象，避免研究錯專案

附件只有名稱，至少找到以下不同對象：

| 候選 | 一手來源可確認的定位 | 對本專題的相關性／限制 |
|---|---|---|
| [0xbet-ai/QuantDesk](https://github.com/0xbet-ai/QuantDesk) | README 是 AI 策略研究→回測→風險驗證→paper trading；ui/package.json 有 React／Vite／Radix／Lightweight Charts | 最接近「AI 工作區」語境，但偏策略研發。可參考實驗／證據分頁，不能當它就是使用者指定。AGPL-3.0；ui package 標 AGPL-3.0-or-later，移植前需按 LICENSE 核對 |
| [pcsadz4/quantdesk](https://github.com/pcsadz4/quantdesk) | Python API／CLI／FastAPI 投組風險、VaR 與回測工具，MIT | 沒有因此證實有 AI 聊天 UI；與本輪互動改版關聯低 |
| [quantdesk.live](https://www.quantdesk.live/) | 官網描述自動化交易 desk、錢包／風險權限、聊天 copilot；封閉 beta | 只讀公開自述，未登入、未操作／驗證，不能把自主下單模式帶進我們的人為確認流程 |

0xbet 的可核對資料：[README](https://github.com/0xbet-ai/QuantDesk/blob/main/README.md)、[ui/package.json](https://github.com/0xbet-ai/QuantDesk/blob/main/ui/package.json)、[ui/src 目錄](https://github.com/0xbet-ai/QuantDesk/tree/main/ui/src)。這輪沒有 clone 或完整跑它，因此不提供其聊天元件行號或聲稱 runtime 流程已驗收。其他同名站與此 repo 不能合併成一個產品。

## 整合優先序（建議，尚未實作）

| 優先 | 可以做的改動 | 直接沿用什麼 | 驗收方式 |
|---|---|---|---|
| 1 | 分析回覆收斂成支持／相反／下一條件＋一張案例卡 | 現有 fact／snapshot／case API，借 TradingAgents 結構 | 同問句下數值逐項可追、無案例不硬塞、多空都能討論 |
| 2 | 每項結論「看證據」連動圖層 | 現有 AnalysisChart focus＋Lightweight Charts | 按支撐只強調對應價格；快照固定不被新 tick 偷換 |
| 3 | 聊天內可編輯交易卡，常駐區同步 | 現有 SharedTicket／草稿版本／確認 API | 修改後舊確認失效、問「如果改做空」不擅改草稿 |
| 4 | 連線、資料、DEMO 授權分開狀態 | OpenApiPy 回呼＋現有 broker state | 斷線報價不裝成即時；恢復訂閱不重送 UNKNOWN 委託 |
| 5 | 同快照的案例比較抽屜／收合圖區 | 現有 case/snapshot 功能、圖表 API | 不離開聊天、可回原草稿、保持 K 線與結果時點一致 |

這些對 HCI 的改善比加入更多代理角色更直接；要先用兩三個完整操作情境驗收，再決定是否導入額外聊天元件框架。沒有新增模型準確率、相似度成效或已完成 UI 的主張。


---
