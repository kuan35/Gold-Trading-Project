# Gold Desk 架站交接：交給同學與 Codex

更新：2026-10-23。目標：兩位同學在現有產品上完成正式展示站。使用者負責的相似案例檢索主線已有本機實作；本次把最新程式與測試交接，雲端站部署由同學接手。

本次交接已納入最新深灰金色聊天工作台與其他分頁改版：對話紀錄、可調大小聊天、支持／相反訊號卡、同一份委託草稿、底部帳戶紀錄，以及即時／回放／案例的統一樣式。細部模組位置與操作限制已補在兩份角色文件。一般 build 與 Pages 的能力仍不同；Pages 不會因推送自動連上私人 DEMO。

發布包本次重跑：後端與指定研究回歸 **462 passed、1 skipped**，前端 **101 passed**；一般 build 與 build:pages 均成功。既有 chunk 大小及 FastAPI/httpx 棄用提示保留。測試使用假串流／暫存資料，沒有實際券商送單或外部模型呼叫。完整命令見 [DEPLOYMENT.md](docs/team_handoff_20261023/DEPLOYMENT.md)；新環境仍須重新驗證。

## 先取得同一份程式

GitHub：https://github.com/kuan35/Gold-Trading-Project

```bash
git clone https://github.com/kuan35/Gold-Trading-Project.git
cd Gold-Trading-Project
git rev-parse HEAD
```

兩人記下相同提交版本，再各開 `codex/frontend-deploy`、`codex/backend-deploy` 分支，用 Pull Request 合併。公開倉庫根目錄就是產品根目錄；原開發工作區才有外層 `product/`。以下連結均以產品根目錄為準。不要把同學電腦上的路徑照搬到設定裡。

先讀 [共同入口](docs/team_handoff_20261023/README.md)、[API契約](API_CONTRACT.md)，再依角色讀 [前端任務](docs/team_handoff_20261023/FRONTEND.md)／[後端任務](docs/team_handoff_20261023/BACKEND.md)。

## 可直接貼給前端同學的 Codex

> 我是 Gold Desk 前端負責人。請先讀根目錄 AGENTS.md、HANDOFF.md、TEAM_HANDOFF.md，以及 docs/team_handoff_20261023/FRONTEND.md 和 API_CONTRACT.md。產品根目錄就是此 repo 根目錄。請在 codex/frontend-deploy 分支延續現有 frontend/，與後端同學共同完成架站。先重跑 npm test、npm run build 與 npm run build:pages。部署完整服務用一般 build；pages 模式是靜態示範，沒有券商後端。接好登入、API、SSE、斷線與權限狀態，保留聊天主入口、可調聊天大小、共用草稿、tick、按需圖表、案例與人工確認。API 變動先和後端確認並同步契約。交付 PR、預覽網址、測試紀錄及需要後端提供的設定；未完成的項目要明列。請勿將金鑰放入 VITE_，或用假成交補真後端功能。真 DEMO 的最終送單／平倉由帳戶擁有者執行。

## 可直接貼給後端同學的 Codex

> 我是 Gold Desk 後端負責人。請先讀根目錄 AGENTS.md、HANDOFF.md、TEAM_HANDOFF.md，以及 docs/team_handoff_20261023/BACKEND.md、API_CONTRACT.md、docs/team_handoff_20261023/DEPLOYMENT.md。產品根目錄就是此 repo 根目錄。請在 codex/backend-deploy 分支把現有 FastAPI 與 cTrader DEMO 常駐橋接部署成受保護的展示服務。先建立可重跑基線，再完成登入／指定同學送單授權、使用者與帳戶資源隔離、Secrets、資料庫／持久磁碟、單實例單 worker、Linux 啟動與健康檢查；保留本機模式與所有草稿版本／人工確認／冪等／UNKNOWN 耐久保護。相似核心 context_contract_v1 沿用，不重寫排名。私人案例索引需向資料擁有者取得受控資料包並通過現有完整性校驗，不把缺資料或合成庫當真實庫成功。保留程式計算數值、Groq 只解釋摘要的界線。先使用假串流測試，真 DEMO 最終確認由擁有者執行。交付 PR、部署網址、環境設定範例、資料需求清單、測試結果、回復版本與備份步驟。

## 目前有什麼，還缺什麼

| 項目 | 交接狀態 |
|---|---|
| 聊天工作台、共用草稿、tick、圖表、持倉與損益 | 本機已實作；公開站依模式展示不同能力 |
| 相似檢索 | 本機預設 context_contract_v1；[方法與範圍](docs/retrieval_completion_status_20261023.md) |
| 即時量能 | 券商已收棒 tick 量／前20棒均量；[定義](docs/live_volume_analysis_20261023.md)；不加入案例排名 |
| 固定快照與 LLM 解讀 | 本機已實作，使用者啟用才呼叫；模型沒有送單權限 |
| 正式多人雲端站 | 待同學完成認證、隔離、資料持久化與部署驗收 |
| 人工盲評準確率 | 尚未完成獨立評分；不可將測試通過寫成相似準確率 |

公開 repo 不含 private/、原始對帳單、帳戶、.env、憑證、提交日誌或私人行情。已公開的逐筆案例與舊檢索索引維持既有授權；clone 後缺本機側檔時，FastAPI 會以明示的合成庫啟動。**成功開網頁不等於真實案例索引或券商連線已就緒。**

資料擁有者已另備本機 `GoldDesk_PRIVATE_CASE_DATA_20261023.zip`（約66 MiB），供指定同學透過受控管道取得；包內保留 `private/` 相對路徑、完整性manifest與解壓說明，不含API金鑰或委託日誌。它沒有上傳GitHub，也不要放入前端public/；取得後必須跑現有側檔校驗才算恢復真實索引。

## 怎麼架站，之後好不好改

建議先用一個常駐 Docker 服務，同站提供 React build 與 FastAPI；同源 `/api` 能減少前後端跨站設定。Render 是可選平台，需持久磁碟的服務有費用；先由同學確認方案，不自動購買。若前端同學偏好 Vercel，可放前端，後端仍採常駐服務並共同完成代理與認證。詳細順序、資料需求與設定見 [DEPLOYMENT.md](docs/team_handoff_20261023/DEPLOYMENT.md)。

架好之後可以持續改，不必重架：分支修改 → PR／自動測試 → 預覽站確認 → 合併主分支 → 自動部署。介面與文案修改通常只需重新部署前端；API 同步修改契約與兩端；資料庫結構改動先備份、寫 migration，再部署。Secrets 放平台設定，資料與提交日誌放持久儲存，不跟程式版本一起清空。重要展示前保留穩定版本，先用測試站驗證；回復程式版本不能取代資料庫回復方案。

現在的 GitHub Pages 仍可作靜態展示；推送程式或 Pages 部署成功不表示新雲端後端已上線。
