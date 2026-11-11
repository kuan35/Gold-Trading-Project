# Windows / macOS 本機安裝

需要Git、Python3.11（建議此已測版本；最低3.11）及Node.js24 LTS。完整功能
是本機FastAPI＋一般Vite build；GitHub Pages是不同的靜態展示。

```sh
git clone https://github.com/kuan35/Gold-Trading-Project.git
cd Gold-Trading-Project
git rev-parse HEAD
```

新版已整合到預設main，直接clone或按Code／Download ZIP即可取得這版。
完整本機盤面比對可用本人 Pepperstone 帳戶的唯讀歷史行情自建；AI 與 DEMO
由本人設定。不同帳戶歷史覆蓋與配對可能不同。原版另留分支供回復。

Windows PowerShell：

```powershell
.\setup.ps1
.\.venv\Scripts\python.exe -m scripts.local_app doctor
.\start-local.ps1
```

macOS Terminal（Apple Silicon與Intel同一流程）：

```sh
sh setup.sh
.venv/bin/python -m scripts.local_app doctor
sh start-local.sh
```

若PowerShell限制本機腳本，先閱讀腳本，再依校內政策解除該下載檔的封鎖；
不要求永久放寬整台電腦的執行政策。若py預設不是3.11以上，可直接用合適的
python執行 `-m scripts.local_app setup`。macOS系統自帶Python可能太舊。

setup可重跑，不覆蓋.env.local／.env.ctrader；start讀.env.local，僅綁loopback。
doctor不輸出secret，`--check-ai`才向官方本機CLI查登入／模型metadata，仍不推論。
預設程式解讀；送出問題才會使用介面選定的AI與本人額度。缺券商設定仍可回放。
目前Windows可本機實測；macOS有相同Python核心與shell入口／CI矩陣，是否已在
macOS實機通過以release驗收紀錄為準，不把腳本存在當作已實機驗證。

## AI

各自安裝官方工具並完成官方登入：Codex用 `codex login`，Claude Code用
`claude auth login`。不是只登入網頁就保證CLI已登入。若PATH找不到，可在
.env.local填GOLD_CODEX_EXECUTABLE／GOLD_CLAUDE_EXECUTABLE的官方絕對路徑。
介面選供應商、模型與思考程度；Codex清單來自本人帳戶，不承諾所有人同模型。
未登入／額度不足／逾時顯示原因並保留程式摘要，不偷偷改用另一個付費供應商。

Codex接頭以乾淨暫存工作目錄、忽略使用者自訂、ephemeral及read-only執行，並
關閉shell／MCP／plugins／hooks／影像／瀏覽／多agent等工具；僅接收去識別文字。
當前CLI仍可宣告無I/O的request_user_input，若模型真的呼叫工具，結果會被拒絕，
不當作有效盤面分析。原生假模型工具清單測試與實際付費推論是不同驗收。

## 完整案例資料

整理後的 11,902 筆交易員逐筆案例已隨 GitHub `main` 提供，檔案在
`frontend/public/data/trader-cases.json`，GitHub Pages 的合成查詢可用它查看真實歷史操作。
公開包另有 10,887 筆案例的候選進出場 UTC 對照，但不含第三方 K 線或量能。
`setup.ps1`／`setup.sh` 只安裝依賴；沒有個人歷史行情時，`doctor` 明示
`synthetic_demo` 及 `personal_history.UNAVAILABLE`。依下節可自行取得行情並重建。
候選時點是 `PROJECT_REFERENCE`；交易員原始券商時鐘仍是 `UNKNOWN`。

向資料擁有者取得授權的最新私人包，勿上傳公開repo或AI聊天。先停止網站。

```sh
# Windows請把python換成 .\.venv\Scripts\python.exe；macOS為 .venv/bin/python
python -m scripts.data_bundle import /path/to/GoldDesk_PRIVATE_RUNTIME.zip
python -m scripts.data_bundle verify
```

不同版本既有資料不自動覆蓋；`--replace`是明確替換所列資料檔，請先備份。
包內只含runtime所需案例／參考棒／最小對齊證據／tick資料，不含原始來源檔名、
帳戶憑證或委託紀錄。資料擁有者可用data_bundle export產生本機受控包。

## 個人cTrader DEMO

1. 向支援cTrader的券商建立本人DEMO，確認商品XAUUSD。
2. 於https://openapi.ctrader.com/apps 申請自己的Open API app，待核准。
3. 執行 `python -m scripts.setup_ctrader_local credentials`，本人填ID與隱藏secret。
4. 在app新增redirect `http://127.0.0.1:8766/callback`。
5. 執行 `python -m scripts.setup_ctrader_local authorize`，先唯讀授權並選DEMO；
   若本人需要DEMO委託，改用 `authorize --trade`。不允許選LIVE。
6. token到期用 `python -m scripts.setup_ctrader_local refresh`；未有refresh token
   時重新授權。此流程不讀模型、不發交易請求。官方若不回傳state會安全中止，
   不放寬state檢查；亦可自行在.env.ctrader填本人Playground token，沿既有唯讀
   `python -m scripts.check_ctrader_demo`診斷。兩種流程都未替每位組員實際授權。

純本機方案建議各自app是為避免分發共同client_secret，不是cTrader強制每名用戶
都當開發者；共用app需另外妥善保護secret，不在這個版本建置共用雲端代理。
不要共用作者帳戶，避免同學彼此修改同一組持倉。DEMO寫入仍須本人確認草稿。

### 同學用自己的帳戶建立完整案例盤面與 tick 量

先依上一節由本人完成 cTrader Open API 授權。DEMO 設定檔中的
`CTRADER_ACCOUNT_ID` 必須是正確的 Open API 帳戶 ID。以下命令只讀取行情，
不會送單或使用 LLM 額度。請在網站停止時建索引；`probe` 只抓三個時段的
5 分鐘與 1 小時樣本，`download` 抓所有可請求的週片段，已抓片段可續傳。

```sh
python -m scripts.history_bootstrap plan
python -m scripts.history_bootstrap probe
python -m scripts.history_bootstrap download --max-chunks 10
python -m scripts.history_bootstrap download
python -m scripts.history_bootstrap build
python -m scripts.history_bootstrap verify
python -m scripts.history_bootstrap activate
```

Windows 把 `python` 換成 `.\.venv\Scripts\python.exe`；
macOS 換成 `.venv/bin/python`。若本人已完成授權並願意一次跑完下載至啟用，
可用 `python -m scripts.history_bootstrap all`。只有 LIVE 帳戶時，每項命令都加
`--environment live --read-only`；LIVE 歷史連線仍只允許讀取資料。

`doctor` 會回報 READY／PARTIAL／UNAVAILABLE。PARTIAL 表示有可用案例，但
某些年份、時段或量能缺失；網站只用同一帳戶的原生 K 線與 tick 量，保留
`context_contract_v1` 相同門檻及排序，不混入作者 HistData。歷史量是券商
tick 次數，不是全市場成交量。由於券商資料保留、交易時鐘候選與缺棒不同，
同學和作者看到的配對不保證逐筆相同。建置期間應保留 `private/`，不要用
`git clean -fdx` 清除下載片段。

## 更新、測試與移除

GitHub程式包能還原相同介面與保存功能；不是複製作者帳戶、聊天或即時報價。
新聊天的完整分析另存在本機private/analysis_history，更新時請保留這個資料夾及
同瀏覽器的網站資料，避免只備份程式卻遺失分析。舊版只存文字者無法補回未保存圖表。
完整案例包、本人AI登入及cTrader設定完成後才有相應功能；不同帳戶需依前節重建tick來源，
不能承諾每位同學看到同一市場報價、模型選單或相同案例結果。

停止網站後git pull，重跑setup再start；保留自己的.env和private。大改前記錄
commit並備份個人資料；不要用git clean -fdx刪除本機資料。

```sh
python -m pytest -q backend/tests
cd frontend
npm test
npm run build
```

移除只需先停止本程式，再自行移除這個專案資料夾。AI CLI與帳戶登入由本人
自行管理，不隨Gold Desk移除或登出。離線原始資料及訂閱權限不隨MIT授權轉移。
