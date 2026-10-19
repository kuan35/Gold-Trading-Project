# Gold Desk Groq 說明代理

GitHub Pages 以瀏覽器程式處理合成回放、公開真實案例檢索、草稿、確認與模擬成交；此 Worker **只回傳文字說明**。它沒有訂單 API 或券商權限。訪客須主動開啟 Groq，完成 Turnstile 驗證後，瀏覽器才傳送問題、合成盤面摘要及公開真實案例的彙總計數，不傳逐筆列。未設定／失敗時仍使用本地規則助手，畫面標示 Groq 未連線。

部署需要專案擁有者的 Cloudflare 帳戶及 Groq API key；目前原始碼不含任何金鑰。準備好後：

1. 在 Cloudflare Turnstile 建立站點，允許 `kuan35.github.io`，保留公開的 site key 與私密 secret key。
2. 在此目錄執行 `npx wrangler login`、`npx wrangler secret put GROQ_API_KEY`、`npx wrangler secret put TURNSTILE_SECRET_KEY`、`npx wrangler deploy`。金鑰只在 Wrangler 互動提示輸入，不能寫進倉庫或前端建置變數。
3. 在 GitHub 倉庫的 Actions variables 設 `GROQ_PROXY_URL` 為部署後的 Worker HTTPS 根網址，`TURNSTILE_SITE_KEY` 為公開 site key。重新執行 Pages workflow。這兩個是公開設定，不是金鑰。
4. 在 Pages 開啟「對話助手」，主動啟用 Groq、完成驗證並送出非敏感示範問題；確認回應標示 `Groq 說明`，確認草稿仍須使用者手動審查，且不會因模型回答成交。失敗時應顯示本地助手。

Worker 只接受 `https://kuan35.github.io` 的 POST；Turnstile token 由 Worker 向 Siteverify 驗證 hostname 與 action，單次使用。Cloudflare Workers rate limiting binding 對同 IP 最多每分鐘 3 次；缺綁定時代理拒絕服務。每次 Groq 請求最多 768 completion tokens；若 Groq 回報截斷或說明超過服務端長度上限，就回退本地結果，不展示半句回答。服務端遮罩常見金鑰／email／長數字，且不記錄請求。Origin 檢查本身不能作為驗證，公開服務仍應在 Cloudflare 設每日預算／監控。Turnstile 與頻率限制不能保證不產生費用。部署需 Wrangler 4.36.0 以上。

測試：`node --test worker.test.mjs`。2026-10-13 已在 Cloudflare Dashboard 建立代理與金鑰 Secret，並以公開 Pages 的合成問題確認可連線；後續更新 Worker 程式須重新部署。
