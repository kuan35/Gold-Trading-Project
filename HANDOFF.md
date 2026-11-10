## 2026-11-10 — Windows CI 診斷與 UTF-8 輸出

- 前次 `190308d` 的 GitHub Windows 工作在「Backend without credentials」步驟失敗，但 macOS、Pages 與產品檢查成功；公開註解只有 exit 1，未取得工作日誌，因此原因未證實。公開 checkout 的全新 Python venv 跑 1005 項全通過；乾淨 git archive 重跑亦 1005 項通過，`doctor` 回 exit 0。為縮小故障範圍，`.github/workflows/local-ci.yml` 將 pytest 與 doctor 拆成獨立步驟，並固定 Python UTF-8 輸出。下一次遠端執行需觀察結果。修改檔案：該 workflow、`HANDOFF.md`、`PUBLICATION_MANIFEST.json`；本次未改交易邏輯。branch `main`；記錄時 commit N/A。

## 2026-11-10 — LIVE 隔離版本與新版 8766 介面發布

- 新版前端加入 DEMO／LIVE 切換、獨立聊天與草稿、LIVE 看盤／案例／Agent／帳戶／委託；後端加入獨立 LIVE 連線、風險上限、必填停損、人工確認及持倉保護／掛單取消。LIVE 限價平倉停用，計畫／提醒待獨立實作。LIVE 預設唯讀，真實資金委託未在開發或測試中送出。`docs/PEPPERSTONE_LIVE.md` 說明設定、入金入口及限制。
- 本機唯讀檢查發現缺 Open API 帳戶 ID，已修連線退出時保留設定錯誤並於新版頂部顯示；實際 API 回 `ACCOUNT_ID_REQUIRED`，`order_connection=false`。使用者須自行填入正確的 LIVE Open API 帳戶 ID，不以券商畫面登入號代替。
- 修改檔案為本 checkout `backend/`、`scripts/`、`frontend/src/`、`frontend/tests/`、`frontend/e2e/` 對應功能與測試，及 `README.md`、`AGENTS.md`、`API_CONTRACT.md`、`docs/`、`.env.ctrader.live.example`、`PUBLICATION_MANIFEST.json`。產品端同名後端／腳本／文件已同步。指令：後端完整 1002 passed／1 skipped；狀態修正相關 11 passed；前端 235 passed、build／build:pages 成功；委託環境 e2e 31 passed，LIVE 環境 e2e 2 passed；diff、白名單、憑證檢查通過。243 份受保護原件 SHA-256 不變。阻礙：LIVE 本機帳戶 ID 未填，無法驗收真實帳戶同步；不送實單。下一步：GitHub main 發布後由帳戶持有人完成本機設定與唯讀驗收。branch `main`；記錄時 commit N/A。

## 2026-11-10 — 多例草稿500、跳動試算與同快照Agent核對

- 實際讀server-error.log定位`broker_demo_draft → respond_context(enabled=False) → render_sections`：第三至五例可信否定模板被模型機率守衛拒絕，導致非JSON500。獨立案例Agent修正`product/backend/live_assistant.py`為可信fact renderer及summary_contract，主Agent整合百分號與指定否定句、簡化草稿提示。肯定的本次勝率／自行數字仍拒絕。新增`tests/test_assistant_summary_contract.py`（11項）及market_case_brief fixture，真實五展示／六全池分母涵蓋原500。
- 新版發布frontend：`api.ts`集中解析HTTP／非JSON；`TicketPreview.tsx`改非重疊刷新，背景保留數據及details，不依每tick abort；`AccountScenario.tsx`背景pending不折疊，`experience/integration.css`穩定槽位。新增`agentSummary.ts`共用首個模型摘要；`ConversationWorkspace.tsx`將同draft Agent pending/ready/error/stale同步`ConversationOrderReview.tsx`，不再獨立套程式WAIT；切換聊天取消後同步終止核對pending，過期刷新不偷偷引用舊Agent。`LiveAssistant.tsx`補欄位、`experience/AgentAnswer.tsx`明示缺歷史關聯。原版product/frontend未改。
- Agent首段要求當時盤面、全池結果及正確有效分母、案例形態、支持／反證。COMPLETE僅為結構與引用，不保證語義。模型省略歷史時明示INCOMPLETE_HISTORY，程式歷史資料標來源；已驗證模型原句才可提升，不能以程式文字冒稱模型結論。舊聊天不重寫，新檢查才適用。
- 先見新增前端回歸4敗；完整案例API測試重現500後改200；另先重現切換聊天核對永遠pending、否定句誤擋及缺百分號，再修正。指令：產品venv `pytest -q` 九個相關模組（test_assistant_summary_contract/live_assistant/market_case_brief/case_analysis_api/case_scenarios/case_operations/case_statistics/case_context/conversation_api）121 passed；發布frontend `npm test`234 passed，`npm run build`成功。`npm run test:ui -- e2e/draft-assistance.spec.ts`含2.4秒慢預覽、HTML500、同摘要、取消分析及過期等；另`e2e/nonblocking-chat.spec.ts`5 passed。最終委託23項全數通過，合計28項瀏覽器測試通過。測試確認／取消全是攔截合成API。
- 真實Claude Code3次純合成呼叫：第一回未完整歷史關聯，第二回invalid_response，第三回首段COMPLETE但附加否定句被舊守衛誤擋；修正指定否定句及百分比單位後，重放同份實際回覆為ok／COMPLETE，不再呼叫模型。不是品質／收益驗證，模型仍可能格式或引用失敗，此時明示，不用另一程式WAIT頂替。外傳僅虛構摘要及占位符，無真實行情或交易。
- IAB實際連8766、讀實際報價帳戶，填0.01手／4080／4050／4150測試草稿、只按檢查，成功顯示風險及核對，未送券商訂單／平倉／取消掛單。截圖與模型診斷留private/coherent_review_20261110。開發中HMR留下舊dependency警告，正式reload後使用新effect。依CIM核對路徑重啟8765（最後PID31448），8766 Vite已載入新版；保留既有成本假設及個人env。
- 新增`docs/coherent_order_review_20261110.md`、更新API_CONTRACT及market_case_agent_evidence文件；6個後端／測試／文件與發布包逐位元相同。243份原始資料及根附件SHA-256前後一致。未複製private至公開。root codex/candidate-market-retrieval；發布main基線e33acf8，commit N/A，未推送GitHub。後續若發布需更新精確白名單manifest；下一步使用者以新草稿／新提問驗收不同真實盤面的模型敘事，不能宣稱所有bug或模型失敗已消失。

## 2026-11-10 — 已送掛單取消、過期續單、實際持倉ROI與案例敘事整合

- 依使用者更正，「取消」指已送出待成交單。`backend/position_management.py`、`broker_orders.py`、`order_binding.py`與`scripts/position_command_payloads.py`／`stream_ctrader_demo.py`擴充OPEN/CLOSE的LIMIT/STOP/STOP_LIMIT取消，不要求進場前已有position。確認比較同帳戶原單指紋（含stop_price），只有匹配原帳戶/order的ORDER_CANCELLED才取消成功；UNKNOWN不重送。重啟後可用CURRENT同帳戶及原單身分明確歷史終態恢復，原單FILLED/EXPIRED/REJECTED只表示取消失敗，不能冒充取消成功；不靠清單消失判定。防止已取消但尚未同步的第二份草稿重送。新版`BrokerPendingCancel.tsx`及`DeskAccountTray.tsx`／`BrokerAccountPanel.tsx`補核對／取消按鈕，右側待成交卡片避免橫捲。
- 新版`ConversationOrderReview.tsx`／`ConversationWorkspace.tsx`：原30秒後端有效性保留，過期或明確未送出之stale/服務重啟失效可按「更新報價並繼續」，保留欄位重新建立固定快照與風險、對照後人工確認；刷新失敗保留舊核對可重試，不重跑付費AI。不解除UNKNOWN或已送出鎖。與原清除未送草稿功能分開。
- 另一Agent建立`account_scenarios.py`與`ctrader_account_payloads.py`補財務欄位；主Agent整合`app.py`與新版`AccountScenario.tsx`、TicketPreview、types/demoMarket/brokerActivity及帳戶畫面。使用者最後明確指定持倉主要用ROI：優先券商usedMargin（position.moneyDigits解碼）與未實現淨損益，缺值才用明示槓桿估算，已知零／無效分母不估算；價格報酬藏詳情。券商成交紀錄用原單實際進出價顯示價格報酬，歷史保證金不捏造。下單前及核對新增固定持倉／價差之淨值歸零情境，不等於強平價；完整USD曝險與新鮮淨值不足拒算。不填SLTP也可看情境。未計潛在平倉佣金，不稱最終實現報酬。
- 案例證據由獨立Agent處理：`market_case_brief.py`固定事前雙週期三段描述接入`case_analysis.py`；`case_scenarios.py`明列draft.terms方向/單型/SLTP；`case_operations.py`前五例原單敘事；`live_assistant.py`不再因停損問題移除案例形態，要求同快照當前盤面、歷史型態、全池統計及原單結果共同判讀，窄守衛拒絕將BUY草稿直接說成偏空草稿。三段描述在檢索後建立，不更動檢索／盈虧排名，不是離線全庫LLM人工標註。尚未新增真實模型品質／交易績效實證。
- 文件：API_CONTRACT與`docs/pending_cancel_and_refresh_20261110.md`、`account_scenarios_20261110.md`、`market_case_agent_evidence_20261110.md`。23個後端/測試/文件與發布包逐位元一致。唯讀審查Agent發現UNKNOWN重啟無法恢復、stopPrice漏核對、遺失草稿409無續單，均補回歸修正。
- 驗證先紅後綠：取消OPEN/競態/回報、過期無入口、實際ROI未主顯等回歸先失敗再修改。產品venv相關17模組`pytest`298 passed（含TestClient合成API）；新版`npm test`228 passed，`npm run build`成功；`npm run test:ui -- e2e/draft-assistance.spec.ts e2e/pending-cancel.spec.ts e2e/position-protection.spec.ts e2e/nonblocking-chat.spec.ts`31 passed，合成ROI畫面已目視。讀取來源的官方API/stopout文件已記在docs，原有Starlette／bundle提示保留。243受保護原件SHA-256全不變。無付費模型推論或真實送單／取消／保護修改。
- 已核對路徑重啟8765（父PID33016），新版8766首頁200，最後唯讀檢查券商與欄位狀態；保留既有成本環境假設、個人設定優先，未改憑證。原聊天不重寫，新Agent提示需新提問／重新檢查。root `codex/candidate-market-retrieval`；發布`main`基線e33acf8；commit N/A，未推送（本輪未要求）。若後續發布先刷新白名單/manifest，不帶private。未完整改舊版product/frontend，現版主體仍發布checkout的8766。

## 2026-11-10 — 成交後停損停利入口、取消準備中委託與專用助手評估

- 新版 `frontend/src/DeskAccountTray.tsx`／`experience/AgentDrawer.tsx`：右側帳戶改為逐部位卡片，直接顯示幣別損益、停損停利、平倉及修改入口；原完整表也加修改入口。`BrokerPositionActions.tsx`沿用現有PROTECT API及人工確認，預填原設定，KEEP省略／CLEAR傳null，保留高階停損限制與帳戶同步鎖；關閉視窗不丟棄UNKNOWN輪詢。無新增LIVE寫入權限。
- `ConversationWorkspace.tsx`／`ConversationOrderReview.tsx`／`TicketCheckAction.tsx`：兩份共用表單新增取消準備中委託，未檢查時本機清空，已檢查REVIEW先取消成功才清空；失敗保留草稿，正在送出／回報未明不能藉此解除鎖定。清除方向／單型／手數／限價／SLTP／交易理由，保留風險預算與聊天；遞增版本並中止舊草稿助手。選填方向只改草稿，不自動另發一般分析。一般聊天比較方向不改草稿；檢查委託評估已填欄位。
- `frontend/src/draftAgent.ts`與`product/backend/live_assistant.py`新增固定草稿專用「這筆委託評估」提示，要求依同份快照的手數、價位、風險及全部歷史匹配池評估本筆，不能改金額、合法性、確認或送單。新增`product/docs/order_controls_20261110.md`、更新API_CONTRACT，後端／測試／文件4檔逐位元同步發布checkout。舊聊天不重寫。
- 驗證先見新增單元／模型契約與瀏覽器回歸在舊碼失敗後再修改。指令：產品venv `pytest -q backend/tests/test_live_assistant.py backend/tests/test_position_management.py backend/tests/test_position_command_payloads.py backend/tests/test_broker_orders.py backend/tests/test_case_analysis_api.py backend/tests/test_scenario_api.py`（發布包執行）76 passed；前端`npm test`224 passed；`npm run build`成功；`npm run test:ui -- e2e/draft-assistance.spec.ts e2e/position-protection.spec.ts e2e/nonblocking-chat.spec.ts`23 passed，補強送出鎖4 passed及可見持倉同步3 passed。包含取消前後／失敗保留、共用欄位、停止晚到助手、單欄SL保持TP、人工確認、UNKNOWN輪詢、唯讀禁改與聊天背景回覆。修正一項舊文案斷言後全通過。合成畫面已檢視，QA留private；未使用外部模型或真實券商異動。既有大bundle與Starlette提示保留。
- 243份交易員資料及根目錄受保護原件SHA-256前後一致。已核對8765程序路徑並重啟，backend父PID12152；新版8766首頁HTTP200，原版8765保留。沿用既有暫用成本、個人設定優先，未改憑證。
- root `codex/candidate-market-retrieval`，發布`main`基線e33acf8；commit N/A／未推送（本輪未要求）。後續若發布須更新精確白名單與manifest，不帶private。提示詞與合成測試不代表實際模型敘事或交易績效已驗證；使用者須重新整理新版頁面與重新檢查草稿以套用新提示。

## 2026-11-10 — 背景回答與全池平均結果

- ConversationWorkspace唯讀回答不鎖導覽，請求依聊天隔離；可切頁／並行聊天／停止回覆，背景結果只回原聊天。切聊天後的遲到解析不改現在草稿，刪除後不復活。實際交易處理鎖定保留。
- 新增backend/case_statistics.py與CasePerformance，對全部通過並去重的代表單算歷史獲利比例、平均價格報酬／每盎司價差及分幣別平均損益，不只前五例。history.aggregate同快照提供Agent；未知不補零、不混幣別。各例圖表及操作明細加入原單進出時間，與行情參考UTC分開。修正跨週期均價文字換算。
- 契約與說明見API_CONTRACT及docs/matched_pool_results_20261110.md。相關後端124項通過，最後歷史勝率引用守衛及live助手53項通過；前端224項、背景／委託瀏覽器16項、全池統計及逐案時間focused瀏覽器1項通過，build及diff檢查成功。無真實模型／券商送單；即時停用LLM驗收取得5組案例／全池統計5組／5例原單時間。
- 主工作區243份保護原件雜湊不變，13個後端／測試／文件已同步。8766已載入；需新提問或更新盤面，舊聊天不重寫。main基線e33acf8，commit N/A、未推送；發布前更新白名單與manifest，勿複製private。

## 2026-11-10 — 1組案例即可納入建議

- `backend/trade_advice.py` MIN_SAMPLES改為1，0組／未成熟後續仍排除，其餘成本、事件、原單反證、風險與人工確認保留。新版AgentAnswer在建議後標實際相似案例數；若多空試算池不同則分開標示，缺值不補0，不以已顯示前五筆或eligible列數代替。QA、契約及兩份說明已更新。
- pytest相關74項、前端223項、合成瀏覽器數量呈現1項通過，build及diff檢查成功。無外部模型呼叫／真實送單，主工作區243份原件雜湊不變。8766已載入，舊聊天保留當時判定，新提問或更新盤面使用新門檻。
- main基線e33acf8，commit N/A，未推送；尚未做新門檻績效驗證。發布前更新白名單及manifest。

## 2026-11-09 — 交易計畫與歷史操作首屏摘要

- `backend/live_assistant.py` 改簡短盤面語意及交易計畫提示，不把原始WAIT／組數判定當成Agent指令；程式action、證據、MIN_SAMPLES及下單檢核未改。風險預算、成本、歷史反證仍提供，保護價註明適用方向。`case_operations.py` 增摘要日期與有來源的報表損益／幣別，精確數字在本機填回。
- `frontend/src/experience/AgentAnswer.tsx` 首屏可讀主計畫與歷史操作解說，Agent漏寫完整原單資料時補同證據的資料列。均線依週期改約多久均價，Bid／Ask改可賣出／買進價，ROI改保證金報酬率，10組門檻解釋留詳細QA。文件見 `docs/clear_agent_plan_20261109.md`，契約更新。
- 驗證94項相關後端、221項前端、11項委託瀏覽器合成測試通過，build成功、diff檢查通過。無真實模型／券商送單；原件243份雜湊不變。8766已載入、Claude ready。實際模型文字待重新提問試用，舊聊天不重寫。main基線e33acf8，commit N/A、未推送，發布前重建精確白名單與manifest。

## 2026-11-09 — 原單操作解讀與連續委託

- 後端 `case_operations.py`／`case_analysis.py`／`live_assistant.py` 增加成熟首兩例原單日期、方向、進出價與未扣成本價格報酬的本機填值事實；模型只取占位符／定性狀態，不送原始帳戶及精確值。不更改檢索排序，原對帳單時區未知與圖表參考時間分開。回答稱均線，當前進出參考不能搬用歷史絕對價。
- 新版 `ConversationOrderReview` 與 `conversationState` 在已接受、部分成交或已成交且帳戶CURRENT同步後，可按「準備下一筆委託」清除當次核對，保留原掛單／持倉；UNKNOWN不解鎖。下一筆使用新草稿並再人工確認。具體操作見 `docs/agent_history_and_next_order_20261109.md`，契約已更新。
- 回歸：相關後端68項、前端218項、委託合成瀏覽器10項通過，本機build成功，diff檢查通過。未執行真實送單或LLM推論。40個固定日期80次查詢61次有案例、19次無；不是相似準確率或收益評估，private逐次結果未複製。主工作區243份原件雜湊一致。
- main，基線e33acf8，commit N/A、未推送；8766與8765後端已載入。原聊天文字不重寫，需新提問試用。後續發布先更新白名單與manifest，不把private或個人憑證放進repo。

## 2026-11-07 — Agent 綜合建議與老師回饋整合發布

- 新增 `backend/trade_advice.py`、`trade_protection_advice.py`、`trade_advice_replay.py` 與前端 `TradeAdviceCard.tsx`、`tradeAdvice.ts`。同盤面成本後多空比較、原單價格報酬、草稿風險及結構停損停利隨分析快照保存。案例檢索沿用五分／一小時路徑、事件、末段、波動與來源相容 tick 條件。
- Agent 收到交易員原則、當前支壓與已檢索案例，首屏給一段綜合建議。檢查委託等待 Agent 完成後顯示模型分析，失敗提示原因。展開可讀案例差異、三十分鐘後續及完整試算。原始金融數字透過本機引用標記填回。
- 本機更新盤面處理券商來源領先本機 0.1–0.75 秒的短差，等待本機時間追上再檢查。來源跨五分鐘邊界或更大偏差仍顯示未就緒。模型連線由本人設定，成本範本須填六欄。
- 交接入口 README、TEAM_HANDOFF 與 API_CONTRACT 已更新。功能符合明確建議、歷史情境與下單前人機互動的展示要求。人機協作成效仍需固定樣本與比較組實測。
- 發布前重跑後端與兩項檢索研究回歸 878 passed／1 skipped，前端 217 passed、合成瀏覽器 24 passed，一般與 Pages 建置成功。補齊歷史看盤測試的合成回放狀態，驗收可獨立於作者服務執行。487 檔白名單包已核對，實際付費模型文字及人機協作效益仍待試用評估。此次發布 branch main，原基線 a402c9b，遠端提交收據另記作者工作區 HANDOFF。

## 2026-11-04 — 完整歷史看盤與日期跳轉

- 使用者選擇獨立歷史看盤，不新增日期重設交易。歷史回放頁預設新看盤子頁，原交易演練可切換。日期／時分、台灣UTC+8／UTC與圖表時間軸一致，5m／15m／1h，金色定位點、前後分頁與手勢邊緣載入，圖表最多2400棒並固定高度；保留原指標／畫線／PNG／全螢幕。
- 私人SQLite按來源／週期／時間索引，API每次上限1200棒、背景原子建庫，5m完整連續才彙整15m/H1。缺口／範圍外／未完成高週期明示、不補棒或缺量為0。不同資料來源不拼同一根。查詢不改engine游標、版本、持倉、草稿或案例／模型。
- 作者本機參考CSV讀取433,119根M5（2020起），另透過本人既有DEMO歷史請求新增32週43,573根M5（近期待載部分，與參考來源重疊）。初次36次及最後一週增量5次SDK請求，0送單／模型。存獨立private/history_native，不碰原案例量能索引。可用資料最新至2026-11-04當次已保存棒，後續按HISTORY_BROWSER說明自行補取。
- 新增backend/history_library.py、3項測試模組、scripts/update_history_library.py；既有下載器只加選填output_folder維持預設行為。app新增3個loopback history API；前端HistoryBrowser、日期／合併模型、Chart日期格式／定位／有限分頁、App／DeskRouteFrame模式隔離，CSS與e2e。文件API_CONTRACT、HISTORY_BROWSER、README、TEAM_START、白名單更新。
- TDD與最終審查修正：讀取跨索引代次競態、更新metadata取消日期請求而卡住、舊圖錯標新週期、分頁邊界漏缺口、原進出場／案例跳轉誤進看盤模式；新增來源變動回滾／非法來源保留／未知量不補0等測試。fresh-context審查五項重要發現已修正並複查無剩餘重要問題。
- 指令／驗證：pytest -q backend/tests research/test_context_similarity_ab.py research/test_assistant_case_acceptance.py、npm test、npm run test:ui、normal與Pages build；最終log在private/history_browser_20261104。真實Edge1660／390，2020~2026七日期各600棒成功（72~103ms本次單機觀察），錯誤0、無橫溢出，手機圖高480px，engine時鐘／版本不變。沒有實際送單或付費推論。
- root backend／tests／scripts／docs選擇性同步且備份；8765原版frontend/src與dist保留，8766預覽新版。新行情／SQLite／QA不公開，現有runtime匯出白名單不擴大，同學程式相同、行情另用授權包／本人DEMO更新。
- 最終850項後端與相關研究／1skip、214前端、22合成瀏覽器通過；normal／Pages build成功。待SHA／公開包及main推送。branch main；commit N/A。

## 2026-11-04 — 交易員工作流程五項整合

- 接續使用者接受的五項方案，main新增：回答優先／無匹配細節收合；Decimal風險卡與預算反算；固定原始依據的交易計畫／復盤；即時圖草稿進場SL/TP拖曳；私人價位／已收五分棒／官方事件提醒。原版分支及8765前端保留，8766預覽新版。
- 計畫隨DEMO草稿檢查保存，確認仍是原人工流程；後續回報關聯不把接受當成交、部分平倉不猜單筆淨ROI。計畫／提醒SQLite在private，不發布。模型回顧僅使用者明確點選，提醒不自動推論或交易。LIVE沒有增權。
- 後端模組與API測試、前端211項及合成瀏覽器17項驗證；normal／Pages build成功。實際DEMO唯讀驗收風險反算及工具頁，桌機1660／手機390無pageerror／橫溢出。無實際下單或模型呼叫。
- 修正空lot不能反算、復盤同key重複、拖曳隨tick取消、開站回放初始化中指令無反應等問題。券商來源時鐘實測約快0.1秒；唯讀試算／提醒共用0.25秒容差，過期5秒界線與送單檢查不變。
- 完整後端與兩項既有檢索／助手研究驗證使用CI相同指令；全部research另有舊numpy／trader_sim缺依賴，不當成本輪產品測試通過。fresh-context審查嘗試因agent額度失敗，改主代理逐項檢視＋測試，未宣稱該審查完成。
- docs/TRADER_WORKFLOW.md、API_CONTRACT、同學安裝入口及精確白名單更新。原始資料／根文件243、原版UI293 SHA在最終發布前比對；私人驗收與備份留根product/private/trader_workflow_20261104。branch main；commit N/A（待本輪驗證後提交）。

## 2026-11-04 — 新版整合為GitHub預設main

- GitHub首輪Pages及Windows/macOS本機安裝CI已成功；舊Verify product handoff的backend失敗。其安裝步驟漏列requirements-ctrader.txt，與新增官方SDK協定測試及已成功local-ci不一致；本輪補齊安裝與pip快取鍵。另14項對應研究測試本機全過。公開包白名單納入verify.yml（450檔），待新GitHub回合核對。
- 使用者指定以目前新版為主，讓同學直接下載。git remote show origin核對預設main原為5bf88de，origin/main為新版祖先、沒有分歧；本機main以--ff-only整合至62cd931，保留codex/local-distribution-20261031（4253e8a）及codex/peer-ui-integration-20261103（62cd931），不刪分支、不重寫歷史。
- README、AI_SETUP、TEAM_HANDOFF、docs/{TEAM_START_20261104,PEER_UI_PREVIEW,LOCAL_INSTALL}改為main下載／clone與現況；移除「main尚未合併」的現行指引，補舊分支同學安全切main更新方式。PUBLICATION_MANIFEST以449檔公開白名單重新計算雜湊；私人runtime包、憑證與聊天不新增公開。
- main整合後完整backend/tests：686 passed／1 skipped；前端192 passed。程式內容與前輪已驗證新版一致，本輪其餘只調整下載與交接文件。上輪normal／Pages build、13項合成瀏覽器、Windows乾淨安裝及唯讀ROI驗證仍適用；未再呼叫模型或交易。
- main push會依現有工作流程觸發Pages及Windows/macOS CI。Pages是靜態展示，下載本機包才提供完整後端；本人AI、DEMO與受控案例runtime仍各自設定。原8765與新8766並存預覽不替換，原資料243與原版UI293檔SHA需在推送後核對。
- branch main；commit N/A（本筆隨整合發布紀錄提交；推送與遠端核對收據另存root private/main_release_20261104）。下一步同學直接由repo首頁Code／Download ZIP或一般git clone取得main新版。

## 2026-11-04 — 預估保證金ROI與新版同學分發

- 使用者提供DEMO槓桿1:200並要求修改報酬率、推送新版供同學建置。沿codex/peer-ui-integration-20261103；原版codex/local-distribution-20261031及main不合併。計畫：docs/superpowers/plans/2026-11-04-margin-roi-distribution.md。
- ticket_preview與TicketPreview：原USD損益、價格報酬率保留；各SL/TP增加margin_roi_pct，按未四捨五入損益／預估保證金計算，不重複乘槓桿。顯示保證金金額及券商預估／1:200試算來源，詳細成本與假設可展開。限價按指定進場價、每人.env.local可設GOLD_PREVIEW_LEVERAGE；非法設定仍保留USD但不補ROI為0。歷史原單未有保證金，維持價格報酬率。
- demo_market_stream／margin_cache／stream_ctrader_demo／expected_margin：市價經現有SDK子程序獨立唯讀ExpectedMargin查詢。Decimal解碼moneyDigits，核對帳戶與volume、USD幣別；快取綁定商品／帳戶／曝光，請求起5秒有效、最多1待回覆、每秒至多1請求，過期／重連／變更拒用。非阻塞、錯誤不停止行情；未就緒、非USD與限價回退槓桿估算。LIVE不增權限，沒有草稿／確認／交易通道副作用。
- API_CONTRACT、README、AI_SETUP、TEAM_HANDOFF、PEER_UI_PREVIEW與docs/TEAM_START_20261104更新；可貼給同學agent的分支clone／Windows與macOS安裝prompt。公開白名單449檔；新建乾淨程式包，npm離線安裝／一般build通過，另以完整setup建全新venv／安裝Python依賴／npm ci／build成功，TestClient首頁與state API皆200。Mac只有入口／路徑測試，未實機驗收。
- 私人runtime由既有受控匯出器建立379檔、86,660,808 bytes ZIP，測試副本匯入及validate_runtime通過：11,902 cases／10,887 profiles、execution AVAILABLE／outcomes READY／native_ticks READY。未匯出.env、CLI登入、帳戶或聊天快取；ZIP僅留根product/private/margin_roi_distribution_20261104，不加入GitHub。不同帳戶量來源仍須按安裝指南重建。
- TDD紅→綠；前端192通過、相關後端／DEMO草稿平倉／API／分發93通過、合成瀏覽器13通過、normal與Pages build成功（既有大chunk提示）。一次fresh-context唯讀審查無重要問題。Windows TestClient及SDK protobuf驗證使用require_escalated避開本機socket sandbox限制。
- 真實隔離Edge唯讀桌機1660及手機390：SL/TP -500／+1000USD、價格-0.25／+0.50%、預估保證金ROI -50／+100%，無pageerror／橫溢出。實際券商ExpectedMargin成功返回，限價fallback來源清楚。真實模型呼叫0、送單0。收據／截圖／原root備份在上述private資料夾。
- 共用後端app／串流／新模組／local_app及測試同步root product；原8765服務當時未啟動，已由官方本機啟動器啟動，新8766Vite背景啟動。原243份資料原件SHA與293個原版前端檔SHA一致。下一步：使用者重新整理8766；同學下載指定分支，自己的AI／DEMO與受控runtime另設。
- branch: codex/peer-ui-integration-20261103；commit: N/A（本紀錄隨本次提交發布，精確版本請查git log -1）。

## 2026-11-04 — 不同日期無匹配實測、委託Agent與SL/TP即時試算

- 使用者要求不同盤面測無案例頻率、程式先核對再由所選Agent解讀原草稿，另加SL/TP即時金額與百分率。沿現有8766獨立分支實作，8765原版介面保留。plan：docs/superpowers/plans/2026-11-04-retrieval-draft-review.md。
- 固定舊30日期＋10不同週券商日期，BUY/SELL各測，共40日期80查詢，直接用現行ContextIndex（d5 .25／h1 .50／tail .12／vol2＋原生tick2倍）。60歷史查詢45有15無、20券商查詢16有4無，合計61有／19無（23.75%無匹配），43次至少5群。資料／門檻不改、未以盈虧選查詢。各個原因重疊，不可加總當不同案例。
- 舊10日快照缺tick，初測正確為資料不足；以唯讀DEMO另取同10時點20批原生M5/H1（810根，0送單），僅存private/retrieval_native_20261104，重建查詢後資料來源與既有量能索引一致。tick刪除部分群／改變排名，但此80查詢沒有從有變零。即時program-only抽樣BUY合格5210、SELL1332，兩邊five_path全未過，最後0；此刻不是tick造成零結果。
- 私人重跑腳本／原始結果／每關交集／SHA／逐日期CSV／report.md／coverage.png+pdf在根product/private/retrieval_draft_review_20261104；沒有公開新的行情或案例欄位。不把覆蓋率當人工相似準確率或勝率；40日期是既有固定樣本、同日多空非獨立樣本。
- 前端新增draftAgent.ts：核對成功立即呈現原程式結果及人工確認，再以選定provider/model/effort呼叫既有draft-chat。只取原immutable snapshot，不重新查行情／案例，不延長30秒期限，不改草稿／風險／確認權限。改欄位、重查、換串、取消會停止顯示舊解讀，核對draft/snapshot/asof/revision；失敗保留程式，program或未就緒不呼叫。pending只在當下畫面，不存成永久等待訊息。
- backend/ticket_preview.py＋POST /api/broker/ticket-preview：純Decimal、只讀快取行情／商品規格、no-store／loopback；無草稿或模型副作用。BUY Ask／SELL Bid，限價用指定價；每個SL/TP回名目USD與方向調整價差÷進場價的價格報酬率，錯邊／缺值／過期明示。margin_roi_pct=null，未扣成本，不宣稱保證金ROI。前端TicketPreview共用於兩處SharedTicket，120ms debounce、取消／stale保護，隨tick更新。
- 一次fresh read-only final review找到P2：程式回覆換成模型會換analysis_ref，已開圖表的引用被archive丟棄。已以rebindDraftChart在同驗證快照改綁引用，unit與瀏覽器「先開圖→模型完成→重整」通過。另實際手機截圖發現原透明浮層透字，合成RED→GREEN，改固定浮層背景為opaque var(--bg)。
- 驗證：前端191/191、相關後端／API／發布政策138/138；完整合成瀏覽器13項、normal與Pages建置結果見本輪收據。新增金額方向、價格報酬率、未填／錯邊／過期、無帳戶外露、原模型設定、晚回覆、備援、保存圖表測試。Windows TestClient使用require_escalated避開socketpair；macOS未實機驗收。
- 實際Edge唯讀API以假設限價3500／.5手／SL3490／TP3520驗證-500.00USD/-0.2857%、+1000.00USD/+0.5714%，390px無橫溢出及pageerror；全部broker金融寫入阻擋，模型強制program。本輪真實LLM呼叫0、真實／DEMO送單0；未消耗前次3次以外額度。
- app.py／新試算模組／測試及API_CONTRACT已同步root product，原共用後端由官方本機啟動器重啟；frontend只更新發布checkout，原版src/dist不覆蓋。API合約與新版說明更新、e2e納入發布白名單。243原件SHA前後檢查與分支提交／push收據另記。
- branch codex/peer-ui-integration-20261103；commit N/A（待本輪驗證提交）。下一步使用者重新整理8766，填SL/TP先看試算，再按檢查看原草稿Agent解讀；送單仍由本人確認。

## 2026-11-03 — 新版互動、效能與問答切題修正

- 使用者回報8766卡頓、拖曳無效、四入口與問句不符、回答數值牆；同意最多3次純合成Claude問答。修改僅在codex/peer-ui-integration-20261103，原版前端293檔與243原件SHA一致。共享後端5模組與新測試同步回product/backend，已由原啟動器重啟8765；原版介面保持。
- frontend/src/ConversationWorkspace、ConversationResize、experience/{Experience,AgentAnswer,agent.css}：移除pointermove全頁光效與DOM ripple；靜態金色外觀，memo舊回覆，rAF拖曳＋延後保存。原flex shrink吞掉高度，現實際log210–1000px，整頁可容納超高。固定120事件量測樣式寫入480→0、recalc121→1；同拖140px由0變化→140px。四入口分成知識／中立訊號／先選案例方向／只聚焦委託，無靜默預填；新聊天重設滾動。
- ConversationReply、MacroEvents與macroEventModel：短標題＋16px正文、展開保留全文，程序修補不擠掉模型正文；無草稿時不硬塞風險空狀態。事件先列時程再按需展開多空關聯，覆蓋／完整數字留詳細區。知識問答不顯示無行情的成交量面板。
- backend/{claude_code,conversation_intent,live_assistant,macro_assistant,macro_knowledge}.py：確認官方CLI回傳單一JSON fence被誤拒，僅正規化完整單一外框，仍維持JSON／數字／引用檢查；新增白話聚焦提示。純質性偏多偏空訊號是DISCUSS，含數量／改單仍走原保守解析。新手專用知識；最近事件改近7天至未來7天；總經「受到支撐」不誤判成技術價位，具體支撐線及RSI仍須依據。
- 實際唯讀Edge：新手、總經、盤面HTTP200，官方5來源CURRENT／6事件；1660與390無橫溢出或pageerror，RSI+MACD下body940/chat565/drawer858連3樣本一致。用program模式且攔截其他POST，無交易。3次Claude呼叫已用完：前2 invalid_response，第2stdout證明單一json fence；修正後第3取得2段模型＋1段保守修補，修正用詞誤判後離線重播3段通過。第2離線重播3模型＋1修補保留。沒有第4次；沒有送真實盤面／日期／交易／帳戶。不能把三次說成都成功或聲稱真人評分。
- 驗證：前端187/187；Playwright8/8（resize/保存/還原、四入口/精確問句、總經、完整段落、手機、UNKNOWN平倉鎖、A→B→A原圖）；相關後端／API／發布政策133/133。Windows sandbox的TestClient卡socketpair，15秒堆疊確認後以require_escalated重跑133全過，非產品API故障。全後端曾在sandbox停止，未宣稱全套通過。normal與Pages build通過，既有大型chunk警告；macOS未實機驗收。新增tests/test_assistant_focus.py、frontend/tests/agent-answer-focus.test.ts及e2e/interaction-quality.spec.ts，發布白名單納入e2e。
- 詳細before/after量測、3次合成payload與結果、截圖及SHA收據僅保留根product/private/peer_ui_ux_fix_20261103；公開docs/PEER_UI_PREVIEW.md更新。branch codex/peer-ui-integration-20261103，commit N/A（尚未提交）；不合併main、不改原分支、不公開private或env。下一步使用者重新整理8766試用；原8765可對照。

## 2026-11-03 — 同學完整UI外殼整合，新分支獨立預覽

- 使用者確認完整設計後，從4253e8a建立codex/peer-ui-integration-20261103。三頁共用同學AgentRail/Topbar、金球、背景、卡片、分頁抽屜與通知；右側預設下單，案例與原K線在聊天，助手名稱開供應商／模型／effort面板，不採登入閘門。原本product/src與dist不改，原版8765仍提供原版資源，新版Vite8766代理相同後端；聊天／草稿依origin分開，券商DEMO帳戶共用。
- 沿用現ConversationWorkspace狀態、schema3保存／命名刪除、analysis_ref快照、圖表工具、檢索、委託版本與唯一人工確認。捲動聊天有上下界、可調整大小；手機可由指令面板開新對話／紀錄。帳戶側欄首次開啟後保留掛載，切頁／收合不清掉UNKNOWN回報。保留原生tick量、已收／形成中與過期提示。
- 不採舊聊天截斷、假進度、文字證據改寫、勝率上色、滑動送單。原後端未修改；Vite預覽代理僅允許列明的loopback Origin，轉送既有後端允許Origin，外部來源寫入拒絕。LIVE仍唯讀，原有限價平倉未核實狀態照實呈現。
- 驗證：前端186/186、normal+Pages build通過（大型chunk提示）；發布白名單2/2；全合成Playwright4/4，涵蓋手機入口、過期圖、UNKNOWN平倉回報保留、聊天切換／重整後案例與原圖。一次獨立review三項P2均經瀏覽器RED→GREEN修正。測試中的平倉確認由合成route完全攔截，沒有真實或DEMO送單。實際程式解讀／唯讀行情的隔離Edge驗收涵蓋三頁、分頁、欄位保留、1660／390寬度、無pageerror；RSI+MACD下圖高480與scroll753連三次穩定。
- 更新安裝／agent交接與docs/PEER_UI_PREVIEW.md；npm run dev:peer鎖8766，npm run test:ui執行合成瀏覽器測試。新UI依賴Motion/cmdk/Sonner；Playwright只屬開發測試，Vite修補到6.4.5，npm安裝稽核0漏洞。未執行付費推論，macOS未實機驗收，不冒稱模型或實際券商送單已驗收。
- 只在本分支發布程式與文件，不合併main、不變更原分支，不加入原件、private、設定或截圖。新版單獨安裝一般start-local仍8765；8766是與原版同機並存的開發預覽。

# Gold Desk 本機產品交接

## 2026-11-03 — 聊天內委託補上檢查及人工確認入口

- 使用者在聊天內填好欄位卻找不到下一步。原cw-inline只渲染SharedTicket，檢查與ConversationOrderReview只在右側；且未選單型時僅右側小字提示。
- 新TicketCheckAction共用明確「檢查 DEMO 委託」、缺填與連線提示，錯誤留在觸發入口。SharedTicket提示尚未選擇市價或限價，維持未預選單型。ConversationWorkspace兩處都呼叫同一check流程，核對成功後只在觸發位置渲染一份原ConversationOrderReview；聊天內可以接著核對風險並人工確認，不需輸入聊天文字或移到右側。沿用版本、防重送及UNKNOWN鎖。
- 新inline-ticket-submit測試先2 RED，再178項前端全通過；一般build及Pages build成功（原chunk警告）。測試另覆蓋連線／檢查中／鎖定狀態、缺填、錯誤回饋及不自動送單。後端未修改，未重跑後端全套。一次獨立read-only review無可執行問題。
- 實際Chrome：聊天及右側欄位同步，缺單型時按檢查在聊天內提示；選擇市價後建立核對草稿、全頁僅1確認區且位於聊天內，顯示風險與人工確認按鈕。僅建立並取消核對草稿，未按確認、未成交；驗收切程式解讀，無付費模型呼叫。測試單型清除、使用者原欄位與Claude設定還原。截圖／log／243原件SHA留private/inline_ticket_fix_20261103。
- 根branch codex/candidate-market-retrieval／commit N/A；公開沿codex/local-distribution-20261031／PR #1同步修正，發布SHA另記根HANDOFF。下一步使用者選好市價或限價後於聊天內按檢查，再自行核對確認。

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
