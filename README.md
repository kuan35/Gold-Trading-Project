# Gold Desk · 黃金交易工作台

可在Windows或macOS本機執行的React＋FastAPI交易討論／歷史案例參考工具。
保留聊天主入口、即時tick、按需K線、案例前後對照、DEMO草稿與持倉紀錄。

## 快速開始

先安裝Python3.11與Node.js24 LTS，再clone本repo。
公開repo根目錄就是產品根目錄，不需要再cd product。

| 系統 | 安裝 | 啟動 |
|---|---|---|
| Windows PowerShell | `.\setup.ps1` | `.\start-local.ps1` |
| macOS Terminal | `sh setup.sh` | `sh start-local.sh` |

開啟 http://127.0.0.1:8765/ 。沒有AI或券商設定也能先看明示合成回放。
安裝可重跑，不覆蓋已填設定。完整指令、診斷、資料匯入、DEMO授權與更新方式：
[本機安裝指南](docs/LOCAL_INSTALL.md)。

## 交給自己的Codex／Claude Code安裝

把本repo網址與這句話交給**本機**coding agent：

> 請先讀AI_SETUP.md、AGENTS.md與docs/LOCAL_INSTALL.md，沿用現有前後端，
> 依我的作業系統安裝、診斷並啟動；不要重寫介面、公開憑證、消耗模型額度或交易。

詳見 [可直接貼用的完整任務](AI_SETUP.md)。雲端coding agent不能直接替另一台電腦登入。

## 三種設定分開

- AI：可選Codex／Claude Code及個人可用模型／思考程度；本人完成官方CLI登入。
- 案例：完整私人資料包另向資料擁有者取得，匯入並驗證後才能重現完整真實案例功能。
- 行情／DEMO：使用自己的cTrader帳戶與本機憑證。不同帳戶tick來源可能需要另建索引。

介面相同不代表不同帳戶的即時報價、模型文字及案例來源完全相同。
歷史結果不是預測。券商委託要由本人核對草稿並確認；LIVE保持唯讀。

## 驗證與授權

用專案venv執行 `python -m pytest -q backend/tests`；frontend執行`npm test`與
`npm run build`。Windows本機驗收與macOS CI／實機驗收分開記錄，請看[驗收紀錄](docs/LOCAL_RELEASE_CHECK.md)。
程式碼 [MIT](LICENSE)；[資料使用範圍](DATA_POLICY.md)、
[第三方授權](THIRD_PARTY_NOTICES.md)另列。CLI與訂閱不隨本程式分發。
