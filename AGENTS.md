# Gold Desk 公開產品程式交接

先讀 TEAM_HANDOFF.md、HANDOFF.md，再讀 API_CONTRACT.md。接手後端架站時優先讀 docs/team_handoff_20261027/BACKEND_DEPLOYMENT.md；舊角色分工補充在 docs/team_handoff_20261023/。此 repo 根目錄是產品根目錄；舊文件的 product/ 指原研究工作區外層，clone 後省略。

小步修改與驗證；前端管 frontend/，後端管 backend/、scripts/ 與部署。跨模組/API 變更先同步契約，交付 PR、測試命令和結果。分支使用 codex/ 前綴。

相似案例主線是 context_contract_v1：同方向、成熟、不重疊、完整已收5m60／1h20，固定事件與末段方向條件，雙路徑／末段／波動各自通過才保留；最大標準化差、合計、ID穩定排序，群／參考時點去重，最多五筆且允許零筆。手數、首筆／加倉、事後盈虧不排名。沿用 context_rules.py 與 context_retrieval.py，改規則須先與負責人確認。PROJECT_REFERENCE 與原始時鐘 UNKNOWN 保留；歷史結果分布不是成功機率，未完成獨立盲評不報準確率。

現行本機中檔門檻為五分鐘0.25、一小時0.50、最近半小時0.12百分點及波動2倍；末段門檻同時用於准入和排名。後續5／30／60分鐘只在選出案例後展示，使用v2私人側檔，不參與檢索。新的前後盤面圖以現有React介面為準；先接齊後端，再增設額外介面。

金額／價格／手數後端用 Decimal、API 十進位字串。缺資料用 null 與原因。量能是來源 tick 量，用於即時解讀，尚未加入檢索排名。

下單維持草稿 → 人工確認 → 後端重驗版本／權限／防重送 key → 查真實回報。UNKNOWN 跨草稿與重啟保護必須保存。LLM 只解釋或產生待確認草稿，使用者啟用才呼叫，沒有確認／送單權限。測試用假串流；真 DEMO 最終確認與平倉由帳戶擁有者執行。真實資金交易不在範圍。

private/、原始對帳單、帳戶、填好的.env、憑證、SQLite日誌及QA不進Git。既有frontend/public/data三檔是明確授權公開的逐筆案例／舊索引／合成查詢，不擴充私人資料公開範圍。公開後端前完成認證、逐資源授權、使用者／帳戶隔離與耐久儲存；保留本機限制，不能刪除loopback判斷就稱可上線。

npm test、npm run build 在 frontend/；Python測試依 DEPLOYMENT.md。修改後在HANDOFF.md記錄檔案、指令、結果、阻礙與下一步。不改原始資料來讓測試通過。
