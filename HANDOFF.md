# Gold Desk 交接紀錄

## 2026-10-23：同步最新產品程式與架站交接

入口：[TEAM_HANDOFF.md](TEAM_HANDOFF.md)，包含可直接貼給前端／後端同學Codex的任務。[架站工作](docs/team_handoff_20261023/DEPLOYMENT.md)仍待實作及驗收，這次推送不是完整雲端後端已部署的聲明。

同步React聊天工作台與可調聊天大小、共用草稿、固定快照、案例對照、cTrader形成棒／已收棒、持倉／損益／紀錄／確認式平倉、Groq盤面解讀與tick量分析，以及context_contract_v1核心和相關測試。Pages繼續使用獨立合成回放及舊公開索引；一般build才接FastAPI。既有公開data三檔未改。

未包含private/、憑證、原始對帳單、私人行情／索引、委託日誌及QA。乾淨clone可以示範啟動，不等於真實案例側檔與券商已設定；資料需求見DEPLOYMENT.md。原工作區保留完整本機收據與原件SHA驗證。

乾淨發布包重跑：Python後端與兩份研究回歸458 passed、1 skipped；前端npm ci後86 passed；一般build及build:pages成功。修正一項圖集路由測試對本機private圖集的依賴，改為暫存合成fixture，仍驗證白名單／存取限制／缺檔，不上傳私人圖集。既有前端chunk大小提示與FastAPI httpx警告保留。沒有真帳戶送單或外部模型呼叫。新增verify.yml讓同學PR自動驗證兩端，Pages workflow保留。

公開檔案掃描無禁入路徑／憑證模式，既有三個公開資料檔雜湊保持相同。真實案例最小受控資料包已在擁有者本機另行準備，沒有進GitHub；同學須私下取得，再執行loader完整性檢查。推送提交請以GitHub Actions和git log核對。

下一步：兩位先clone相同commit、各開分支，後端先做授權／隔離／耐久部署，前端配合API與SSE認證，再共同驗收測試站。獨立盲評尚未完成，切勿將程式通過當人工相似準確率。
