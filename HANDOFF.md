# Gold Desk 本機產品交接

## 2026-10-31 — Windows／macOS 分發與Codex接頭

安裝先讀README.md、AI_SETUP.md、docs/LOCAL_INSTALL.md；介面沿用frontend，
後端沿用backend，不需要重建或先架雲端站。TEAM_HANDOFF.md的舊架站紀錄僅供背景。

- 新增Codex官方CLI文字接頭，逐請求選擇Codex／Claude Code／程式解讀／API；
  Codex模型與思考程度來自本人metadata。沒有自動付費推論或借用開發聊天。
- Windows setup.ps1/start-local.ps1與macOS setup.sh/start-local.sh共用
  scripts/local_app.py；保留.env、單worker、127.0.0.1:8765、診斷不印憑證。
- scripts/data_bundle.py只匯出授權runtime資料；manifest、SHA、完整runtime載入、
  路徑／大小／鎖／還原驗證。私人包另行由資料擁有者分享，不公開上GitHub。
- 每人自己的cTrader DEMO與官方CLI登入；個人OAuth、refresh、量能來源重建詳見
  安裝指南。不得為了跨帳戶可用而移除tick source檢查。LIVE維持唯讀。
- 公開程式MIT，資料與第三方另依DATA_POLICY.md及THIRD_PARTY_NOTICES.md。
  用scripts/package_local.py準備精確白名單，勿git add作者研究工作區或private。

驗證：獨立Windows安裝包執行python -m scripts.local_app setup（含pip、npm ci、
build）與重跑成功，doctor為synthetic_demo／program／券商未設定；首頁與JS HTTP200。
完整後端pytest621 passed，frontend npm test143 passed，npm run build及build:pages成功。
原作者工作區完整620 passed、1 skipped；私人包379檔還原，11,902案例／10,887參考
盤面與進出場／後續／量能索引通過。未使用原始對帳單作安裝必需檔。

一次獨立review發現部分但SHA正確的包也可覆寫案例，已回歸測試重現並修正為
匯入前驗完整runtime；收據寫入失敗亦還原。清潔安裝還發現缺demo-data.json，
已補精確白名單與回歸測試。既有Starlette/httpx棄用與大bundle提示保留。

macOS：shell語法已檢查並提供Windows/macOS CI矩陣，未做實體Mac執行。
Codex：metadata確認可用，原生假模型隔離測試完成，未做真實付費推論。
cTrader：本輪未替組員做OAuth／下載／送單。瀏覽器點選與視覺驗收未執行。
下一步：本人選擇GitHub整合方式後推送，檢查Mac CI，再由各組員本機登入驗收。
