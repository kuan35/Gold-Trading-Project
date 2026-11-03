# 新版完整 UI 與原版並存

此分支 `codex/peer-ui-integration-20261103` 採同學完整介面外殼，接入現版功能。
原版仍在 `codex/local-distribution-20261031`，不合併 main、不變更公開 Pages 主站。

## 介面與功能

- 交易對話、即時看盤、歷史回放共用金色深／淺主題、圖示導航、報價頁首與狀態通知。
- 右側預設「下單」，另有即時圖、帳戶、紀錄；案例與前後 K 線在聊天展開。
- 點助手名稱調整 Claude Code／Codex／API／程式解讀、模型與思考程度。
- 聊天先顯示摘要、支持／相反訊號及第一組案例，完整數據按需展開。
- 完整聊天保存、命名／刪除、分析／圖表還原、全部圖表工具沿用現版。
- 手機用右上搜尋／指令按鈕切頁、開新對話及聊天紀錄。
- 委託仍須檢查並人工確認，收合側欄不會清除待核對／UNKNOWN 狀態。
- 即時圖標示新鮮度與形成中 K 棒；tick 量不是集中市場成交量。

## 同學從 GitHub 安裝

```sh
git clone --branch codex/peer-ui-integration-20261103 https://github.com/kuan35/Gold-Trading-Project.git
cd Gold-Trading-Project
```

依 README 安裝 Python3.11、Node24，再執行 Windows `setup.ps1`／`start-local.ps1`，
或 macOS `sh setup.sh`／`sh start-local.sh`。一般安裝網址仍是8765，新版會由本地FastAPI提供。
這個分支已含完整程式，勿讓 agent 另行生成一套介面。
完整案例包、個人CLI登入、券商DEMO憑證各自設定；不要複製別人的 `.env` 或認證檔。

## 同一台電腦同時比較兩版

先照原流程啟動原版本機網站 `http://127.0.0.1:8765/`。
在**新版分支**產品根目錄開另一個終端：

```sh
cd frontend
npm ci
npm run dev:peer
```

新版網址 `http://127.0.0.1:8766/`，僅前端使用8766，API代理到8765。
請保留原版服務。若8766被占用會直接停止，不會偷偷換網址或停止其他程序。
預覽僅接受列明的loopback來源；不需要更動原後端的Origin限制。

兩個網址的聊天、草稿與偏好分開。**券商DEMO帳戶、行情、持倉與券商紀錄共用**，
因此不是兩個交易帳戶；不要為比較畫面重複確認委託。
原版原碼／dist不需要替換；停止新版 Vite 或打開8765即回原版。

## 可直接交給本機 agent

> 請讀README、AGENTS.md、AI_SETUP.md與docs/PEER_UI_PREVIEW.md，clone或切到
> codex/peer-ui-integration-20261103，不要切回main或重新生成UI。
> 沿用現有React/FastAPI，以我的作業系統安裝並診斷；保留.env與private資料。
> 單獨安裝用start-local啟動8765；若本機已有原版8765，請僅在新版frontend執行
> npm run dev:peer，使用8766代理既有後端，不能再啟動第二個券商後端。
> 先選程式解讀驗收聊天／案例／K線／分頁，不消耗付費模型額度、不送單。
> 憑證與官方CLI登入由我親自完成；不要讀取作者或其他人的登入認證檔。

## 驗證

```sh
cd frontend
npm test
npm run build
npm run build:pages
npm run test:ui
```

瀏覽器測試使用全合成帳戶與回報，攔截券商變更，不會操作真實／DEMO帳戶。
Windows使用本機Edge的獨立臨時profile；macOS/Linux測試者先執行
`npx playwright install chromium`，不使用個人登入profile。
若已有8766預覽會沿用，否則測試自行啟動前端；仍需既有本機後端提供一般唯讀服務。
CI若不執行UI測試，不影響一般安裝。macOS實機與模型推論不以Windows測試冒稱已驗收。

## 本輪限制

外觀直接採來源元件／樣式，指定的下單分頁、模型設定及資料語意是有意差異，
不宣稱所有像素完全一致。原有券商限價平倉的未核實／自動撤單狀態仍照實呈現。
LIVE保持唯讀。歷史相似與結果僅為參考，不改演算法或提高證據等級。
