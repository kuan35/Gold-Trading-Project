# 直接貼給本機Codex或Claude Code

你是在使用者本機協助安裝Gold Desk的coding agent。先讀本repo的README、
AGENTS.md、DATA_POLICY.md、docs/LOCAL_INSTALL.md。沿用現有React/FastAPI，
不要重新生成介面、換框架或另建雲端站。

1. 確認目前目錄是產品根目錄（有backend、frontend、requirements.txt）。公開
   clone沒有外層product；原研究工作區才需要先cd product。
2. 記錄git commit。檢查Python3.11+與Node.js24 LTS；不要修改全域執行政策。
3. Windows執行setup.ps1；macOS執行sh setup.sh。它建立專案venv、npm ci及
   一般build，不是build:pages。不要覆蓋既有.env或private資料。
4. 執行專案venv的 `python -m scripts.local_app doctor`，回報狀態，不印設定值。
5. 未取得私人包時維持明示合成回放。若本人取得授權包，先停止網站，再依
   data_bundle import/verify流程導入；不得從別人電腦或公開網路擅取私人資料。
6. 使用者自行在官方CLI登入Codex或Claude Code。不要讀取／複製auth.json、
   OAuth token或接管開發聊天。介面可切供應商；不自動執行付費合成測試。
7. cTrader先保持未設定；依本人意願啟用DEMO，詳讀安裝文件。需要登入或貼
   secret時請本人在終端操作，不把憑證貼聊天。不得複製作者.env.ctrader。
8. 依OS啟動start-local，確認http://127.0.0.1:8765/回應。不要開0.0.0.0、
   多worker或在未知埠衝突時停止其他程序。
9. 只做必要修復及相關測試。交付URL、commit、資料／AI／券商各自是否就緒。
   不以成功開首頁冒充完整案例／模型推論／券商委託已驗收。

安裝或驗收不可以自動送單、平倉、修改保護、消耗模型額度、公開資料或push。
若只提供雲端coding agent，它可以準備程式與CI；仍需使用者在自己的電腦
執行安裝／登入／啟動，不能聲稱已在該電腦開好網站。
