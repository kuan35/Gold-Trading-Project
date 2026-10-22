# Gold Desk：前後端 Codex 共同交接入口

2026-10-23。此文件以目前相似案例檢索主線為準，舊D分工不構成新增需求。交接狀態：本機功能可展示；獨立盲評、多人隔離與雲端部署由下一階段接手。這份文件不是已完成部署的聲明。

最新交接推送入口：[TEAM_HANDOFF.md](../../TEAM_HANDOFF.md)，含兩位Codex可直接貼上的任務。架站次序見[DEPLOYMENT.md](DEPLOYMENT.md)。公開repo根目錄即產品根目錄；文件中的product/是原工作區外層，在clone後請省略。

## 交給誰

- 後端同學的Codex：讀 [BACKEND.md](BACKEND.md)。
- 前端同學的Codex：讀 [FRONTEND.md](FRONTEND.md)。
- 量能與後續範圍：讀 [VOLUME.md](VOLUME.md)。最新即時解讀已實作，未加入排名。

兩位先閱讀專案AGENTS.md、HANDOFF.md最新紀錄及 [API_CONTRACT.md](../../API_CONTRACT.md)。同一repo分支協作，各自管理frontend與backend；API契約由後端提版本、前端對照確認。跨模組變更先列檔案及理由，保持相似規則核心可重跑。

## 現在交付的是什麼

1. React／TS／Vite聊天工作台、可調聊天大小、共用草稿、即時tick與按需展開圖表。
2. FastAPI與cTrader DEMO常駐連線橋接；已收5m／15m／1h指標、tick形成棒、持倉／損益／紀錄與確認式進平倉。
3. 相似檢索固定context_contract_v1：同BUY／SELL、成熟、不重疊、完整5m60／1h20；雙路徑＋末段＋事件＋波動通過才保留；最大標準化差／合計／ID排序，每群與參考時點去重，預設最多五筆，允許零筆。手數、首筆／加倉與盈虧不排名。詳 [現行規格](../context_rules_product_20261021.md)。
4. 固定快照的案例、指標、四圖與可見群操作；Groq明確啟用後只解釋去識別摘要，沒有確認／送單工具。

兩方共用的資料來源標示與五種狀態沿用API契約。沒有私人案例時可能載入合成示範；這不是成功載入真實檢索庫。公開Pages仍是另一個舊展示版本，不能拿Pages build當雲端後端。

## GitHub與資料交接

目前以公開Gold-Trading-Project的白名單程式包交接；本機tmp/publish-gold-20261001是發布工作副本，與原研究工作區不是同一個Git根。同學clone遠端同一commit即可取得產品程式，實際推送版本以git log為準。團隊日後可另建私有整合repo；私人資料仍受控交付。

程式、依賴鎖檔、測試、契約、無秘密env範例及交接文件進程式repo。依AGENTS規則，原始報表、金鑰、.env、帳戶資料、SQLite提交日誌、私人行情／側檔與QA仍走擁有者指定的受控資料交接，不加到公開包。既有公開真實案例例外不擴張至其他私人檔案。

本機真實檢索至少需要private/cases.json、case_candidate_market_profiles.json，並須備妥側檔loader檢查的引用輸入；由load_candidate_sidecar的現行校驗列出完整需求，不能只複製兩檔就宣稱可重現。請擁有者另提供經同意的資料包或產生步驟，金鑰由每位使用者在自己的後端設定。

## 部署方向與次序

先部署一個Render常駐Docker Web Service，同站提供React build與FastAPI；券商連線程序保留單一owner，提交日誌使用持久儲存。前後端仍分工開發，沒有要求改成同一人負責。若前端另放Vercel，則以同源/api代理或經驗證的跨站認證接後端，前端不可用pages模式冒充真後端。

部署工作順序：本機共同commit重跑 → 認證／授權與使用者隔離 → Secrets及資料磁碟 → 真實後端與前端串接 → 受限DEMO驗收 → 正式展示。現行loopback限制須由已驗證的使用者權限接替；不是刪掉判斷直接公開。現有回放是單工作階段記憶體原型，公開多人使用前需隔離；SQLite與連線狀態未抽離前採單實例／單worker。

## 共同完成標準

- 同一commit可安裝、建置、啟動，能辨認真實案例庫／示範庫、連線與未連線。
- 已收棒與形成棒分開；固定快照的案例及圖表不隨下一個tick偷偷改變。
- 有符合、全部未過、無合格池、事件未定、資料不足五種狀態都能展示。
- 新／舊欄位競態、草稿取消、人工確認、防重送key、UNKNOWN跨草稿／重啟保護保持。
- 多人權限隔離、服務重啟後提交紀錄與UNKNOWN保留；公開訪客不能操作指定DEMO帳戶。
- 未經人評不報準確率；PROJECT_REFERENCE／原始時鐘UNKNOWN按目前邊界說明。

驗收分兩層：CI使用假串流與暫存資料驗證送單流程；連真DEMO時確認送單／平倉由帳戶擁有者親自執行。交接後的Codex不能自動用真帳戶跑成交測試。

## 可直接貼給兩位Codex

「請先讀專案AGENTS.md、HANDOFF.md及product/docs/team_handoff_20261023/README.md，再依你的FRONTEND.md或BACKEND.md接手。先檢查現有實作並重跑相關測試，列出部署缺口後在分配模組內完成整合；保留context_contract_v1與既有API及確認／防重送流程。交付可重跑的PR、測試紀錄、設定範例與部署驗收，不將私人資料或金鑰加進Git。」
