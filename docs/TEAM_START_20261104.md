# 同學安裝這個版本

這是金色深色工作台的新UI，包含交易對話、可還原的聊天／案例／K線、即時行情、指標、
DEMO草稿與人工確認、持倉／平倉／紀錄、官方總經事件，以及Claude Code／Codex／API切換。
SL/TP即時顯示USD、價格報酬率與預估保證金ROI；按檢查後可由所選助手解讀原快照。

## 下載

使用分支 `codex/peer-ui-integration-20261103`，不要下載main的舊版。
[直接下載完整程式ZIP](https://github.com/kuan35/Gold-Trading-Project/archive/refs/heads/codex/peer-ui-integration-20261103.zip)
或：

```sh
git clone --branch codex/peer-ui-integration-20261103 https://github.com/kuan35/Gold-Trading-Project.git
cd Gold-Trading-Project
```

安裝Python3.11+、Node.js24 LTS。在含backend、frontend、setup.ps1的資料夾：

| 系統 | 安裝 | 啟動 |
|---|---|---|
| Windows PowerShell | `.\setup.ps1` | `.\start-local.ps1` |
| macOS Terminal | `sh setup.sh` | `sh start-local.sh` |

網址為 http://127.0.0.1:8765/ 。先以程式解讀／合成回放驗收，再設定本人AI與cTrader DEMO。
8766是作者與原版並存時的開發預覽，一般同學不需要兩個埠。

## 要還原到什麼程度

下載可還原相同介面和功能程式。完整案例與行情runtime包需由資料擁有者另行受控提供，
依 [安裝指南](LOCAL_INSTALL.md) 的data_bundle import／verify匯入。
只有公開程式與示範資料時，不會自動取得作者完整本機案例、聊天、AI登入或券商帳戶。

每人自行登入Claude Code或Codex，使用自己的cTrader DEMO憑證。
換券商／帳戶的tick來源可能不同，需按安裝指南重建本人原生量索引，否則會明示資料不可比較。
即時報價、模型回答、實際持倉與案例結果不保證和作者相同。不要複製作者的.env或認證檔。
Windows已實測；macOS有安裝入口及路徑測試，尚未做Mac實機驗收。

本輪從449檔精確白名單包建立全新Windows虛擬環境，實際完成setup（Python依賴、npm ci、
一般build），首頁與state API回應200；另於測試副本匯入runtime並驗證11,902筆案例、
10,887份盤面特徵、進出場／後續結果與原生tick索引可用。沒有複製作者憑證或登入。

## 報酬率

- USD損益＝方向調整價差×合約盎司，槓桿不另外乘一次。
- 價格報酬率＝方向調整價差÷擬進場價。
- 預估保證金ROI＝USD損益÷預估保證金。
- 市價優先券商預估（USD）。尚未回覆／不適用時按進場價×盎司÷槓桿試算，限價也使用這個假設。
- `.env.local` 的 `GOLD_PREVIEW_LEVERAGE=200` 是可修改的個人試算假設，修改後重啟。
  黃金的商品／分級槓桿仍可能與帳戶上限不同；UI會標「券商預估」或「1:200試算」。
- 都是下單前、未扣交易成本的情境估計。歷史案例沒有原單保證金，不套用目前帳戶槓桿回算歷史ROI。

## 可直接貼給本機Codex／Claude Code

```text
請協助在我的電腦安裝Gold Desk。
Repo: https://github.com/kuan35/Gold-Trading-Project
分支: codex/peer-ui-integration-20261103

先讀README.md、AGENTS.md、AI_SETUP.md、docs/TEAM_START_20261104.md及docs/LOCAL_INSTALL.md。
沿用完整前後端，不重新生成介面；clone指定分支並記錄commit。
檢查Python與Node，依Windows/macOS執行setup與start-local。
先用程式解讀驗收首頁、三分頁、聊天A→B→A→重整及案例K線還原。
未匯入完整runtime包時，回報只有示範資料，不冒稱完整案例就緒。
若我提供授權案例包，停止服務後用data_bundle匯入並verify；保留原private及.env。
AI官方登入及cTrader憑證由我自行填寫，不讀或複製其他人的認證。
按我的帳戶設定.env.local中GOLD_PREVIEW_LEVERAGE；這只是ROI備援假設。
一般網址是127.0.0.1:8765；已有原版時先讀PEER_UI_PREVIEW，不停止未知服務。
不自動消耗模型額度、不送單／平倉、不公開私人資料。
最後回報網址、commit、資料包／AI／券商各自狀態及尚未驗收項目。
```

更新時停止服務、git pull同一分支、重跑setup／start-local，保留個人.env、private及瀏覽器資料。
原版保留在 `codex/local-distribution-20261031`，這輪不合併main。
