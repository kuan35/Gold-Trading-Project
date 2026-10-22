# 架站實作順序與驗收

2026-10-23。這是交接規格，尚未部署完整雲端後端；現有程式以本機受限原型為基線。

## 服務選擇

優先評估單一常駐 Docker Web Service，同站供應 React 與 FastAPI。保留一個 cTrader 連線 owner、單實例／單 worker；目前記憶體工作階段、快照和 SQLite 鎖還不能直接多副本。Render 支援 Docker、健康檢查、Secrets 與持久磁碟；持久磁碟限付費服務，費用與使用額度由團隊確認。參考 [Web Services](https://render.com/docs/web-services)、[Docker](https://render.com/docs/docker)、[磁碟](https://render.com/docs/disks)。

前端另用 Vercel 亦可，但不能直接把現有請求啟動子程序與本機磁碟當雲端常駐架構。先完成後端，再決定同源反向代理或具體跨站認證，包含 EventSource／SSE。此建議基於現有程式的長連線與耐久狀態需求，不宣稱 Vercel 所有模式都不能用。

## 第一關：從乾淨 clone 重現

在產品根目錄依 README 安裝 Python、Node 依賴；測試另安裝 research/requirements.txt（含 numpy；離線研究額外需求見 requirements-evaluation.txt），cTrader 用 requirements-ctrader.txt。Windows 本機命令：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r research/requirements.txt
.\.venv\Scripts\python.exe -B -m pytest -q backend/tests research/test_context_similarity_ab.py research/test_assistant_case_acceptance.py
cd frontend
npm ci
npm test
npm run build
cd ..
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8765
```

無私有資料／憑證時應能開示範站，且顯示合成來源／未連線；這一關只證明程式可以啟動。Linux 改用 `.venv/bin/python`，不要執行 Windows DPAPI 啟動腳本。

## 第二關：受控資料與設定

- `CaseStore` 目前從產品根 `private/cases.json` 載入真實案例。
- `private/case_candidate_market_profiles.json` 必須與 cases 的雜湊一致，且其 inputs 所列引用全部在 private 根內存在、雜湊相符；alignment 的標記也須通過 `backend/candidate_sidecar.py::load_candidate_sidecar`。完整資料包由擁有者受控提供。公開 `frontend/public/data/trader-market-index.json` 是舊 Pages 索引，不能直接更名代替。
- `case_size_profiles.json`、`case_market_profiles.json` 是舊方法可選側檔；新方法以現行 loader 與 context 檢索為準。準備資料時記錄 READY／MISSING／STALE／INVALID 與實際載入數，不偽造校驗。
- Groq 參考 `.env.example`，cTrader 參考 `ctrader.env.example`，兩者都是空白設定樣板。填好的檔案只放伺服器的受控儲存或 Secrets，不能 commit。現有 stream 對 `.env.ctrader` 有存在檢查；後端同學需改為安全的雲端設定載入，或使用平台私密檔掛載，不把金鑰塞入前端。
- 帳戶 token 的 scope、到期、刷新、DEMO 環境都要驗；未取得權限維持拒絕送單。

先確認授權名單與帳戶歸屬，再載入真實帳戶。私人資料包與 Secrets 不經 public repo 傳送。

## 第三關：公開前的後端工作

把現有 loopback 守衛換成明確的本機／雲端策略；雲端每個帳戶、持倉、草稿、快照、日誌與串流端點都要做後端授權。現有回放與快照未完整使用者隔離，不能只增加登入頁就宣稱完成。公開行情與個人帳戶功能分別控制權限。

先單實例，把委託日誌、UNKNOWN 狀態與必要資料放持久磁碟或資料庫。建立備份、重啟與部署中斷測試；請求逾時只查原防重送 key，不自動新送一筆。容器接 SIGTERM 能關閉串流並保留結果；加不含帳戶／密鑰的 liveness 與 readiness。市場休市或未設定帳戶不應無限重啟整個網站。

後端同學交付 Dockerfile、受控 .dockerignore、啟動命令、健康檢查與平台設定。容器鏡像只含白名單程式；private、.env、提交日誌與測試收據不進 image。這些部署檔本次沒有以未實作認證的設定冒稱可直接公開。

## 第四關：共同驗收才算上線

1. 未登入訪客無法查看個人帳戶資料或建立／確認／平倉指定 DEMO 委託；指定使用者也不能存取別人的資源。
2. 讀到正確的行情來源、快照時間、已收棒與形成棒，斷線／過期照實呈現。
3. 載入真實案例索引且沿用 context_contract_v1；零符合與缺資料分開，原始時鐘 UNKNOWN 保留。量能只用於盤面解讀。
4. 聊天與側欄共用一份草稿，過期版本與重複 key 被正確處理，UNKNOWN 跨重新登入／重啟仍不能重送。
5. 持倉、未成交、成交紀錄、損益依券商回報展示，不把 ACCEPTED 當 FILLED。
6. 上述先用假串流／暫存帳戶資料自動測試；真正 DEMO 的最終送單／平倉由擁有者操作，留下可核對回報。
7. 給出前端網址、API 來源、commit、備份位置、回復步驟、限制與平台費用。未完成就列阻礙，不把 GitHub Pages 成功當作完整服務完成。

## 持續更新

設定 GitHub PR 測試與部署預覽；正式站跟經驗收分支自動部署。獨立保存 Secrets 與持久資料，每次上線先備份與列出資料變更。帶磁碟的 Render 服務在部署時有停機限制，展示前留維護時間；參考 [Deploys](https://render.com/docs/deploys)。一般介面修改不需要搬資料或重建帳戶。
