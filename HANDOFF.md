# Gold Desk 交接紀錄

## 2026-10-27 — 後端架站交接與本機新版原碼同步（Codex）

- 以原研究工作區 `product/` 精確白名單同步產品原碼：`backend/` 的後續情境／5分鐘側檔／0.12中檔規則、`frontend/src/` 聊天工作台與同案例前後K線、相關測試、`scripts/build_case_outcomes.py`、`API_CONTRACT.md`及直接相關文件。新增 `docs/team_handoff_20261027/BACKEND_DEPLOYMENT.md`，明定先照現有React介面接齊後端、驗收後再加額外介面，並寫明GitHub共編與Render部署分支。公開 `frontend/public/data/` 三檔未擴大或更改。
- 此提交只交付程式與文件；GitHub Pages仍是合成瀏覽器示範。私人案例、行情與新 `case_forward_outcomes.json` v2、帳戶憑證、金鑰、SQLite與QA不入Git；資料擁有者本機另備受控 `GoldDesk_PRIVATE_CASE_DATA_20261027_v2.zip`，交接前驗證包內SHA。來源時鐘仍UNKNOWN，PROJECT_REFERENCE與人評未完成的界線不變。
- 在公開checkout執行 `python -B -X utf8 -m pytest -q backend/tests research/test_context_similarity_ab.py research/test_assistant_case_acceptance.py`：509 passed、1 skipped、既有Starlette提示；`frontend/npm test`：110 passed；`npm run build`及`npm run build:pages`成功（既有chunk大小提示）。首次受限環境阻斷本機測試通訊，已停止該程序並在允許本機通訊的環境完整重跑通過。`git diff --cached --check`通過，61個暫存檔經白名單與憑證樣式掃描；根工作區243份原始報表及根PDF／PNG／DOCX／m4a SHA-256零變更。
- branch `main`／commit N/A（本條記錄寫於提交前）。阻礙：完整雲端後端、使用者授權與持久資料尚由後端同學實作；公開Pages成功不代表DEMO連線。下一步：同學依新交接文件開 `codex/` 分支，交付受保護的常駐服務、PR與實際驗收網址。

## 2026-10-23：最新工作台與前後端分工交接

本次以 c9a3396 為基準，同步最新深灰金色聊天工作台及即時／回放／案例等分頁；31個精確白名單路徑，另更新本交接紀錄。新增 DeskChrome／DeskRouteFrame、帳戶 tray、唯讀文字紀錄、趨勢支持／反向訊號、圖表共用色票與分頁樣式，保留共用草稿、固定快照、確認／版本／防重送與 UNKNOWN。後端僅修正啟動時 quote 時間戳缺值回 UNAVAILABLE，沒有改相似規則或 API。

[TEAM_HANDOFF.md](TEAM_HANDOFF.md) 是共同入口；[前端](docs/team_handoff_20261023/FRONTEND.md)、[後端](docs/team_handoff_20261023/BACKEND.md) 各有模組位置、已完成／待辦、驗收與可貼給 Codex 的任務。兩位 clone 相同 commit，再各開 codex/frontend-deploy、codex/backend-deploy 分支。架站順序與受控資料需求見 [DEPLOYMENT.md](docs/team_handoff_20261023/DEPLOYMENT.md)。

發布包 fresh 驗證：`python -B -X utf8 -m pytest -q backend/tests research/test_context_similarity_ab.py research/test_assistant_case_acceptance.py` 得462 passed、1 skipped；`npm test` 得101 passed；`npm run build` 及 `npm run build:pages` 成功。保留原 chunk 大小與 FastAPI/httpx 提示。前兩輪已完成本機桌面與手機互動驗收，本次重跑公開包測試／建置；沒有真 DEMO 下單、平倉或外部模型呼叫。

既有公開三份data JSON未改；私人案例包、金鑰、帳戶設定、提交日誌、原始資料與QA未加入。掃描命中的兩項key字串已逐一核對為遮蔽功能的固定合成測試值；其餘無憑證模式命中。文件連結與diff空白另檢查，收據留原工作區private目錄。

一般 build＋FastAPI 包含完整新聊天工作台；Pages 仍為靜態展示入口，保留原瀏覽器聊天與合成回放。推送會觸發 verify 及 Pages workflow，是否成功以此 commit 的 Actions 為準；完整受保護雲端後端仍待同學部署，登入／資源隔離／持久資料／單owner串流是下一步。相似檢索獨立盲評未完成，不報準確率。branch main；提交以本條紀錄所在 git commit 為準。

## 2026-10-23：同步最新產品程式與架站交接

入口：[TEAM_HANDOFF.md](TEAM_HANDOFF.md)，包含可直接貼給前端／後端同學Codex的任務。[架站工作](docs/team_handoff_20261023/DEPLOYMENT.md)仍待實作及驗收，這次推送不是完整雲端後端已部署的聲明。

同步React聊天工作台與可調聊天大小、共用草稿、固定快照、案例對照、cTrader形成棒／已收棒、持倉／損益／紀錄／確認式平倉、Groq盤面解讀與tick量分析，以及context_contract_v1核心和相關測試。Pages繼續使用獨立合成回放及舊公開索引；一般build才接FastAPI。既有公開data三檔未改。

未包含private/、憑證、原始對帳單、私人行情／索引、委託日誌及QA。乾淨clone可以示範啟動，不等於真實案例側檔與券商已設定；資料需求見DEPLOYMENT.md。原工作區保留完整本機收據與原件SHA驗證。

乾淨發布包重跑：Python後端與兩份研究回歸458 passed、1 skipped；前端npm ci後86 passed；一般build及build:pages成功。修正一項圖集路由測試對本機private圖集的依賴，改為暫存合成fixture，仍驗證白名單／存取限制／缺檔，不上傳私人圖集。既有前端chunk大小提示與FastAPI httpx警告保留。沒有真帳戶送單或外部模型呼叫。新增verify.yml讓同學PR自動驗證兩端，Pages workflow保留。

公開檔案掃描無禁入路徑／憑證模式，既有三個公開資料檔雜湊保持相同。真實案例最小受控資料包已在擁有者本機另行準備，沒有進GitHub；同學須私下取得，再執行loader完整性檢查。推送提交請以GitHub Actions和git log核對。

下一步：兩位先clone相同commit、各開分支，後端先做授權／隔離／耐久部署，前端配合API與SSE認證，再共同驗收測試站。獨立盲評尚未完成，切勿將程式通過當人工相似準確率。
