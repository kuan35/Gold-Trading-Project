# Gold Trading Project

## 2026-10-18：本機參考盤面檢索

本機逐案稽核 11,902 筆產品案例，其中 10,921 筆可建立進場前盤面特徵；10,887 筆另具進出場參考棒與一致時序，納入專題參考盤面檢索（完整三週期 6,542、僅五分鐘 4,345）。目前先篩 BUY／SELL 與成熟時間，再依 60 根已收五分鐘 K 線收盤路徑及技術指標分軸排序；前 15 個不同操作群內，固定三段走勢型態相同者提前，各層展示前五。手數、首筆／加倉與盈虧不參與排序。提問或建立草稿時取本機回放時點的已收盤面；外部即時報價尚未接入。參考盤面由來源時間模型定位，券商原始時鐘獨立核實仍為 0；盲評與足夠相似門檻也尚未完成。公開 Pages 只依方向列出合成案例，沒有私人交易或歷史盤面。詳細方法見 [固定盤面描述與混合檢索](docs/market_state_text_retrieval_20261019.md)。

線上展示：https://kuan35.github.io/Gold-Trading-Project/

GitHub Pages 回放演練可在瀏覽器獨立操作，使用合成行情與案例；每位訪客工作階段獨立，重新整理會清空模擬持倉。首筆、加倉、平倉、案例與本地中文助手均可使用；另有 TradingView 外部即時看盤頁。它沒有 Python 後端、私人交易員資料或券商連線；Groq 說明代理部署後可由訪客主動啟用，未設定時維持本地助手。本機版本則保留 FastAPI 與私人資料匯入。

Pages 部署由 `.github/workflows/pages.yml` 在 main 的前端更新後自動執行，先跑前端測試再建置。

公開 Groq 代理的 Worker 程式與部署設定見 [groq-proxy](groq-proxy/README.md)。金鑰只存 Cloudflare Worker secret，Pages 不含金鑰；目前是否已連線，以網站「對話助手」狀態為準。本機參考盤面已可用於專題案例檢索；券商原始時鐘仍待獨立核實。

黃金交易案例與下單前風險輔助平台。React + TypeScript + Vite 前端、TradingView Lightweight Charts、FastAPI 後端。

首筆進場或加倉前，先看相似歷史操作、持倉變化與價格情境損失，再由人確認。這是本機歷史回放產品原型；券商 DEMO 與外部 LLM 尚未完成實際連線驗收。

## 已完成

- 5 分、15 分、1 小時 K 線、MA20/MA60、來源量欄位、進出場標記；明暗與手機版。桌面版採中央圖表、右側可調寬委託區及底部交易表，保留資料來源和未連線狀態。
- BUY/SELL 市價與限價草稿、首筆、加倉、選填停損停利、確認／取消、逐筆平倉。限價單確認後先列待成交，回放 K 棒觸價才模擬成交，可在待成交表取消。
- Decimal 損益、加單前後手數／同向均價、指定價格情境損失；未設停損不填造風險報酬比。
- 候選檢索顯示完整三週期與五分鐘限定層，以及歷史結果分布；盈虧不參與排序。公開合成示範可分開查看獲利與虧損案例。
- 個人提醒條件可在右側頁籤編輯，檢查訂單時呈現規則結果；證據不足會標明未知。
- 中文助手建立待確認草稿；未啟用 LLM 時為明示的本地規則解析。
- HTML／Excel／CSV 資料稽核、固定可見行為分類、來源 SHA-256 查核與私人案例匯入。

## 啟動

需要 Python 3.11+、Node.js 20.19+ 或 22.12+、npm。以下在此 README 所在的產品資料夾執行；原研究工作區則先 `cd product`。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
npm ci
npm run build
cd ..
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8765
```

瀏覽 http://127.0.0.1:8765。無 private 資料時，自動載入標示清楚的合成行情與合成案例；不是原交易員績效。已安裝依賴並完成建置後，也可用 `powershell -File start.ps1` 在背景啟動本機伺服器。

開發前端可另開終端執行 `cd frontend`、`npm run dev`，使用 http://127.0.0.1:5173。Vite 將 API 轉送 8765，後端仍需啟動。

## 展示操作

1. 查看回放時間與來源，選 BUY／SELL，輸入 0.10 手。
2. 點「首筆進場 · 檢查訂單」，查看部位、價格情境與歷史案例；確認前不會成交。
3. 點「確認本機模擬成交」，再建立同向加倉，觀察整體情境損失變化。
4. 推進一根 K 棒，在圖上查看首筆與加單標記；從持倉列確認平倉。
5. 在對話助手輸入「買進黃金0.05手」，查看同一套草稿流程。
6. 切到未設定的券商模擬模式，確認系統不會把本機成交說成券商成交。

## 本機私人資料

同學交接的完整真實資料另放在私人 [Gold-Trading-Project-Data](https://github.com/kuan35/Gold-Trading-Project-Data)。需要權限後才能讀取，下載、校驗、還原及重跑流程見 [資料交接說明](docs/data-handoff.md)。

原始交易檔、帳號、來源檔名、逐筆資料、行情下載檔與私人案例不在公開版本。資料提供者須確認匯入與使用權利。

資料稽核工具在 `research/`，見該資料夾 README。完成稽核後：

```powershell
.\.venv\Scripts\python.exe scripts/import_private_data.py --audit-dir private/audit --bars C:/path/xauusd_5m_bars.csv
```

行情 CSV 須含 `timestamp,open,high,low,close,volume`，是明確 UTC 的已知 5 分鐘來源；預設擷取 2025-10-01 起 10 天，可用 `--start`、`--days` 調整。匯入後重新啟動後端。

本機有完整私人側檔時，使用依來源時間模型定位的參考盤面進行混合檢索，案例詳情只繪製進場前已收 K 線；券商原始時鐘尚未獨立核實。公開 Pages 沒有私人側檔，仍只依方向展示合成案例。可見初始單不代表帳戶確定空手；來源缺漏與重複候選仍限制結果。

## 模擬規格與邊界

單一記憶體工作階段，重設或重啟會清空模擬持倉。每手 100 盎司、USD、本機初始餘額 10,000、固定 0.30 價差；未模擬佣金、隔夜費、保證金或強制平倉。未設定停損時，價格情境不是損失上限。同棒觸及停損與停利採停損優先。不是券商逐筆成交重建。

本機有私人交易員資料時，案例檢索只篩方向與成熟時間，每候選操作群最多一筆；同層依 K 線收盤路徑和指標雙軸排序，再於前 15 群以三段型態重排。側檔失效或查詢盤面不足時顯示原因，不退回舊版手數權重。未知時區案例以全群最晚平倉加 14 小時及 1 分鐘作保守成熟界線。這不是已確認時區或已證明帳戶完整。未匯入私人資料的公開示範則只列出同方向的合成案例。

歷史獲利比例僅描述匹配池，不是目前下單的預測機率。合成案例、回放模擬與交易員紀錄分別標示。可選外部 LLM 只負責解釋，沒有確認成交的權限。

## 即時看盤

「即時看盤」使用免費 TradingView 嵌入圖表顯示 OANDA:XAUUSD，可切換週期、畫線與加入指標；報價時間與市場狀態依圖表判讀。與回放演練分開，尚未接入模擬下單、持倉損益、案例檢索或 LLM。只在開啟此頁時載入第三方資源，無須金鑰。詳見 [即時圖表與 LLM 選擇](docs/live-chart-and-llm.md)。

## 可選外部 LLM

預設不讀取金鑰、不呼叫外部服務。`.env.example` 是設定範例，不會自動載入；需要使用者自行設定 shell 的 `GOLD_ENABLE_LLM=true`、`GOLD_LLM_API_KEY`、`GOLD_LLM_MODEL`，再啟動後端。啟用後會傳送必要市場／部位／草稿風險摘要與遮罩後指令；未傳完整對帳單與來源識別。文字遮罩不是完整個資防護，指令勿包含帳號或私密內容。實際外部回應與摘要審核尚待有金鑰時驗收。

## 驗證與文件

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm run build
```

2026-10-17 公開副本前端 27 項、後端 142 項測試通過，Pages 建置完成；本機瀏覽器檢查候選案例分層、進場前 K 線與頁面捲動。歷史時間仍未核實，價格相容率不等於時間正確率。見 [匿名候選盤面報告](docs/price_only_probe_20261013/candidate_market_validation.md) 與 [匿名時間補證報告](docs/time-evidence-20261013/report.md)。

- `docs/黃金交易輔助平台專題報告_v1.docx`：標楷體、至少 12pt，包含摘要、邏輯、八週安排及六階段後續擴充。
- `docs/project-report.md`：可修改文字版。
- `docs/data-audit-summary.md`：本次匿名彙總資料結果。
- `API_CONTRACT.md`：前後端契約。
- `docs/demo-script.md`：可交給同學操作的展示腳本。

後續完成參考盤面檢索盲評，並補券商／匯出時鐘與獨立行情證據；券商 DEMO 帳戶授權與成交回報另行驗收。之後延伸 MAE、持倉警示、個人資料匯入、多使用者隔離與部署。真實資金交易不在此版範圍。

圖表使用 TradingView Lightweight Charts（https://tradingview.github.io/lightweight-charts/）；圖表保留套件提供的 TradingView 標識。第三方套件權利依其授權，原始交易資料不隨程式公開。
