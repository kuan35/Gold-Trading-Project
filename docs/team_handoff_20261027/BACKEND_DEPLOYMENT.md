# Gold Desk 後端架站交接（2026-10-27）

## 交接目標

以此倉庫的現有 React 介面為產品基準，將本機 FastAPI、歷史案例檢索、即時行情、Groq 解讀與 cTrader DEMO 帳戶接成可供指定成員使用的網站。**第一階段先讓現有畫面與互動在正式網址上完整運作；通過驗收後，再由後端同學自行新增需要的管理或輔助介面。** 原有前端不是待重畫的示意稿。跨前後端修改先更新 `API_CONTRACT.md`，並與前端負責人核對。

此 repo 根目錄就是產品根目錄；原開發工作區的 `product/` 前綴在 clone 後省略。GitHub Pages 的 `build:pages` 仍是合成行情瀏覽器示範，不是已上線的 cTrader 後端。推送原碼不會把本機憑證、私人案例側檔或券商連線搬到 Render。

## 第一階段介面契約：請照現有畫面接後端

| 使用者看見的區域 | 現有前端入口 | 後端必須提供的能力 |
|---|---|---|
| 頁首 XAUUSD tick、DEMO 連線與帳戶狀態 | `frontend/src/ConversationWorkspace.tsx`、`frontend/src/api.ts` | 已授權帳戶的 quote／market／activity／chart-stream；斷線和過期狀態明示 |
| 中央交易對話、固定高度紀錄、可調尺寸 | `ConversationWorkspace.tsx`、`ConversationReply.tsx` | `POST /api/assistant/interpret`、`/live-chat`；只用同一分析快照，聊天提案與草稿同步規則保留 |
| 支持與相反訊號、相似案例 | `ConversationReply.tsx`、`CaseOutcomePanel.tsx` | 已收 K 棒的盤面事實、`context_contract_v1` 檢索；零案例與缺資料有不同原因 |
| 「進場前盤面對照」 | `CaseComparisonCharts.tsx`、`OutcomeSummary.tsx` | 同一 snapshot 的 `/charts` 與 `/outcomes`；同案例、同 5／30／60 分鐘，查詢端不得看到未來棒 |
| 右側共用委託、檢查與人工確認 | `ConversationWorkspace.tsx` | DEMO 草稿、版本重驗、後端授權、防重送 key、實際券商回報；模型無送單權 |
| 底部持倉、待成交、下單紀錄與平倉 | `ConversationWorkspace.tsx` | 帳戶隔離的持倉／委託／歷史、即時浮損益與平倉草稿；ACCEPTED 不當 FILLED |
| 即時看盤與歷史回放分頁 | `frontend/src/` 現有分頁與圖表元件 | 即時已收棒／形成棒分開；回放維持合成來源標示 |

先在目前的深灰金色工作台上驗證每個按鈕、狀態與手機尺寸。需要新的帳戶管理頁、部署診斷頁等時，第二階段再新增；保留現有聊天主入口、行情頁首、按需展開圖表及共用草稿。

## 這次更新的案例與歷史後續

- 本機預設檢索仍是 `context_contract_v1`。同方向、已成熟、不重疊且進場前完整 5m×60／1h×20；事件階段與末段方向先檢查，再檢查五分鐘路徑 0.25、一小時路徑 0.50、最近半小時 0.12 **百分點**及波動最多 2 倍。通過後按最大標準化差、合計與 ID 排序；每群／參考時點最多一筆，最多顯示五筆且允許零筆。0.12 同時是准入門檻與排名分母。手數、加倉標籤、事後盈虧不參與排名。讀 `backend/context_rules.py`、`backend/context_retrieval.py` 與 `docs/context_rules_product_20261021.md`。
- 固定分析快照讓案例與圖表保持同一查詢時間。`backend/forward_outcomes.py` 的私人 v2 側檔提供已完整發生的後續 5／30／60 分鐘（1／6／12 根五分K）；`backend/case_scenarios.py` 才將歷史百分比走勢套到本筆草稿試算。後續、MAE／MFE 只在挑選案例後展示，不回流到檢索。查詢圖只含進場前已收棒；歷史案例圖可接後續，沒有完整資料就顯示原因。
- 原始券商時鐘尚未獨立核實，參考盤面維持 `PROJECT_REFERENCE`／`UNKNOWN`。門檻有看圖與敏感度實驗，但尚無完成的人類盲評；通過不等於相似準確率或未來獲利機率。
- `frontend/public/data/` 現有三個檔案屬先前明確授權的公開範圍，請保持原樣。`private/` 及新 v2 後續側檔不在公開 Git 白名單，需由資料擁有者經受控管道交付。10/23 私人包建立時間早於 v2，接手時要檢查／補齊 `case_forward_outcomes.json`，並驗證 cases、profiles、來源 bars 的 SHA；不能用舊側檔冒充有 5 分鐘後續。
- 資料擁有者本機另備 `GoldDesk_PRIVATE_CASE_DATA_20261027_v2.zip`，包含原受控案例依賴與新後續側檔，包內有 SHA-256 manifest。此包**沒有上傳 GitHub**；先由擁有者核准傳遞方式，再放到部署環境的受控儲存。倉庫中的程式仍可在缺私人包時以合成示範啟動。

## 架站順序與完成標準

1. **凍結基線。** clone、記下 `git rev-parse HEAD`。依 `README.md` 安裝依賴，跑 `python -B -m pytest -q backend/tests research/test_context_similarity_ab.py research/test_assistant_case_acceptance.py`；前端跑 `npm ci && npm test && npm run build && npm run build:pages`。記錄實際數量、失敗與環境差異。先用假串流與合成資料開起現有畫面。
2. **做雲端部署包。** 建議單一常駐 Docker Web Service，同源提供 React 一般 build 與 FastAPI `/api`。維持一個 cTrader 連線 owner、單實例單 worker，加入健康檢查與正常關閉。部署設定、CI 與 secret 注入寫入可重跑的檔案／平台設定說明；不要把 Windows `start-groq.ps1` 當 Linux 啟動命令。
3. **補權限與耐久。** 現有 loopback 守衛是本機保護，不能只移除。雲端先驗證登入者，再逐帳戶、草稿、快照、操作紀錄及串流做後端授權。限定只有擁有者與指定同學可送 DEMO 單；訪客若能看公開行情，也不能讀個人帳戶。委託日誌、UNKNOWN 回報與必要資料放持久儲存，重啟後仍阻止重送。Secrets 只放 Render 環境／私密檔，不進前端 `VITE_*`、Git 或容器鏡像。
4. **接受控資料。** 由資料擁有者另外提供私人包；在受控儲存中載入，執行現有 hash-bound loader，記錄 READY／MISSING／STALE／INVALID 和載入筆數。重建或接收 v2 後續側檔後，抽查 5／30／60 分鐘及 point-in-time 截止。未拿到包時網站仍可用合成示範，但要清楚標示，不能稱為真實案例檢索已上線。
5. **按現有介面驗收。** 固定同一快照問做多／做空、查零／多個案例、切案例與後續期間、打開前後圖；確認 tick 更新不竄改舊分析。填市價／限價草稿、停損停利，確認過期版本和重複 key 被拒；帳戶、持倉、待成交與歷史顯示一致。先用假券商測全流程；真 DEMO 最終送單與平倉由帳戶擁有者親自操作。
6. **交付與擴充。** 交付 PR、站點網址、API 基址、健康檢查、測試輸出、資料與 Secrets 需求清單、備份／還原步驟及尚未完成項目。上述現有介面驗收完成後，才另開 PR 新增額外介面；新頁仍使用相同帳戶權限與 API 契約。

## GitHub 共編與 Render 更新

倉庫擁有者保留 GitHub 寫入權限。每人用 `codex/` 分支改動、開 PR、讓測試與前後端同學檢查後合併；Render 連到指定部署分支並設定自動部署，之後合併到該分支即可重建站點。若選「CI 通過才部署」，要先讓該提交的檢查正常執行。GitHub 共編權限**不等於** Render 控制台、Secrets、日誌或手動回滾權限；需要這些操作時，由服務擁有者另給適當 Render 團隊權限。PR 預覽是否啟用依平台方案決定，不作必要依賴。參考 [Render 部署](https://render.com/docs/deploys)、[Git 連線](https://render.com/docs/git-provider)及 [GitHub 受保護分支](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)。

## 可直接貼給後端同學 Codex

> 我接手 Gold Desk 後端架站。先讀 `AGENTS.md`、`HANDOFF.md`、`TEAM_HANDOFF.md`、`API_CONTRACT.md` 和 `docs/team_handoff_20261027/BACKEND_DEPLOYMENT.md`。以現有 `frontend/src/ConversationWorkspace.tsx` 及其圖表、委託、帳戶元件為第一階段介面基準，先讓所有現有畫面與按鈕在受保護的正式服務工作；API 變動同步契約和前端。沿用 `context_contract_v1` 的 0.25／0.50／0.12／2 門檻及固定快照，補齊私人 v2 後續資料的 5／30／60 分鐘，但不要把私人資料或金鑰推上 GitHub。完成登入、逐資源授權、單連線 owner、持久委託日誌、Docker 部署與假串流測試；真 DEMO 最終交易請帳戶擁有者操作。交付 PR、正式網址、測試結果與未完成清單。現有介面驗收後再另開 PR 加額外介面。

更細的舊架站背景可參考 `docs/team_handoff_20261023/DEPLOYMENT.md`；若與本文件的 0.12 門檻或 v2 後續不同，以本文件與目前程式／API 契約為準。
