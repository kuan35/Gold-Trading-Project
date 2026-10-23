# 後端同學／Codex任務

先讀 [共同入口](README.md) 與其API契約。目標是把目前本機服務變成有權限隔離、可持續運作的雲端後端；相似規則沿用既有核心。

## 這次程式差異與未完成項目

最新介面已可呈現盤面、案例與帳戶結果。本輪後端只修正 `backend/live_assistant.py` 的啟動缺值：行情時間戳不是字串時回既有 `UNAVAILABLE`，避免 null 導致500；四種缺值回歸在 `backend/tests/test_live_quote_initialization.py`。沒有變更 API、相似排序、時間品質門檻或券商送單權限。

本機流程已有實作；**雲端登入、逐資源授權、多使用者隔離、部署與耐久儲存驗收尚未完成**。前端文字歷史目前在瀏覽器；如果要跨裝置會話，需先約定後端契約，不要把舊文字紀錄還原成可確認的委託。後端初期先保持單實例／單 worker，完成下列工作再開放指定同學送單。

## 負責範圍

`backend/`、`scripts/` 的券商橋接、Python依賴與部署設定（公開 repo 根目錄即產品根，沒有外層 product/）。前端只提出必要契約差異，請前端負責人修改。相似核心為backend/context_rules.py、context_retrieval.py、compact_market.py；Cases／側檔載入為cases.py及candidate_sidecar.py。先讀實作再拆模組，避免重新實作另一套排序。

## 執行順序

1. 用既有測試與假串流建立可重跑基線；確認私人案例／索引是否齊全，無資料時明確表示未載入。API的金額／價格／手數繼續用十進位字串。
2. 將loopback限制包成明確的雲端存取策略：登入、指定同學DEMO送單角色、帳戶歸屬與每筆資源存取檢查。保留本機模式。前端送來帳號字串本身不代表授權。
3. 回放engine、聊天快照、草稿、冪等提交紀錄按使用者／帳戶隔離。先單實例／單worker，驗證子程序只開一條受控券商連線；擴容前再將狀態與提交鎖移至共享儲存。
4. 本機Windows DPAPI／env檔檢查改成雲端環境設定介面；Secrets設定由擁有者輸入。檢查token到期／刷新、安全記錄、關機與重連。資料與SQLite日誌放持久磁碟或資料庫，不能因deploy清空UNKNOWN。
5. 提供Linux Docker啟動、health/readiness、資料需求manifest與無秘密設定範例。確認子程序依賴、UTC時鐘、出站連線與查詢限流；先驗唯讀報價／已收棒／案例API，再由擁有者確認DEMO測試。
6. 與前端驗API、SSE的認證與斷線恢復；新增或變更契約同時更新API_CONTRACT及範例。不要只在Vercel Functions請求中臨時開券商程序就當作常駐成功。

## 主要入口

- backend/app.py：live-chat、interpret、broker/drafts、confirm／cancel／status、持倉平倉草稿、market／bars／chart-stream、snapshots圖表／operations。
- demo_market_stream.py與scripts/stream_ctrader_demo.py：常駐資料及委託回報。
- broker_orders.py：SQLite耐久UNKNOWN／同key結果／跨草稿保護。
- case_analysis.py、analysis_snapshots.py、case_context.py、case_operations.py：固定快照與外部模型資料界線。

## 可交付證據

沿README執行後端相關測試，保留命令／exit code與結果。加入跨使用者越權、錯帳戶、斷線／過期／重啟、同key與新草稿重送、併發確認測試。提供部署URL、設定清單、資料與日誌保存位置及回復步驟。實際DEMO交易需擁有者執行；測試假串流不可標成券商成交。

## 可直接貼給 Codex

「我是後端負責人。請先讀 AGENTS.md、HANDOFF.md、TEAM_HANDOFF.md、docs/team_handoff_20261023/BACKEND.md、docs/team_handoff_20261023/DEPLOYMENT.md 與 API_CONTRACT.md。延續 backend/、scripts/，先重跑現有後端及兩份指定研究回歸，再與前端確認一般 build 的 API／SSE 認證。目標是受保護的常駐展示站：完成登入、指定同學送單授權、逐使用者／帳戶資源隔離、Secrets、私有案例資料校驗、持久提交日誌、單 owner 券商連線、Linux 啟動／健康檢查及備份回復。沿用 context_contract_v1，不另改相似排序；保留草稿版本、人工確認、防重送與 UNKNOWN 耐久保護。沒有私人索引或行情時如實顯示未就緒。用假串流驗證，真 DEMO 的最終送單和平倉由擁有者執行。交付 PR、部署網址、設定範例、測試紀錄與未完成清單，不把金鑰、帳戶或 private/ 放 Git。」
