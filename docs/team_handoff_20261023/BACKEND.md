# 後端同學／Codex任務

先讀 [共同入口](README.md) 與其API契約。目標是把目前本機服務變成有權限隔離、可持續運作的雲端後端；相似規則沿用既有核心。

## 負責範圍

product/backend、product/scripts的券商橋接、Python依賴與部署設定。前端只提出必要契約差異，請前端負責人修改。相似核心為backend/context_rules.py、context_retrieval.py、compact_market.py；Cases／側檔載入為cases.py及candidate_sidecar.py。先讀實作再拆模組，避免重新實作另一套排序。

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
