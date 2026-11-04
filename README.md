# Gold Desk · 黃金交易工作台

本輪新版與可貼給同學agent的安裝任務：[2026-11-04同學安裝入口](docs/TEAM_START_20261104.md)。

可在Windows或macOS本機執行的React＋FastAPI交易討論／歷史案例參考工具。
保留聊天主入口、即時tick、按需K線、案例前後對照、DEMO草稿與持倉紀錄。
本機另提供黃金知識與官方總經事件，每項事件說明條件式多空關聯；
詳見[官方事件工具](docs/gold_macro_assistant_20261101.md)。
聊天可回看完整分析、案例與原K線，切換／重整／本機服務重啟後可還原；
詳見[聊天保存](docs/conversation_history_20261031.md)。首頁常用問題亦可查近期總經事件。

本分支已採完整同學UI外殼，右側預設下單、案例留聊天，模型選項位於助手設定。
原版仍保留於 `codex/local-distribution-20261031`；[雙版本預覽與交接](docs/PEER_UI_PREVIEW.md)。

## 快速開始

先安裝Python3.11與Node.js24 LTS，再clone本repo。
公開repo根目錄就是產品根目錄，不需要再cd product。

本輪版本位於 `codex/peer-ui-integration-20261103` 分支；尚未合併main時請用：

不使用Git也可[下載這個分支的完整程式ZIP](https://github.com/kuan35/Gold-Trading-Project/archive/refs/heads/codex/peer-ui-integration-20261103.zip)，
解壓縮後進入同時含backend、frontend與setup.ps1的資料夾，依下表安裝／啟動。
此包包含相同介面與功能程式；完整案例包另由資料擁有者私下提供，AI與券商設定各自填寫。

```sh
git clone --branch codex/peer-ui-integration-20261103 https://github.com/kuan35/Gold-Trading-Project.git
cd Gold-Trading-Project
```

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
