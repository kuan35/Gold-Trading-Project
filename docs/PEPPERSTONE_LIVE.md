# Pepperstone cTrader LIVE 工作區

新版本機網站（8766）頂端「交易環境」可切換 DEMO 模擬與 LIVE 真實資金。兩邊行情、持倉、草稿、送單紀錄及瀏覽器聊天分開；歷史交易員案例是共同參考庫，檢索時使用目前所選環境的已收 K 棒。LIVE 畫面顯示帳戶末四碼與券商回報的帳戶槓桿。使用者截圖中的 LIVE 餘額為 0、帳戶槓桿為 1:30；這不代表 XAUUSD 一定按 1:30 收取保證金，仍需依該帳戶的商品規格與券商預估結果。

## 本機設定

1. 先由帳戶持有人在 Pepperstone／cTrader 完成官方授權。把 `product/.env.ctrader.live.example` 複製為本機的 `.env.ctrader.live`；只在本機填 cTrader Open API 憑證、`trading` scope 的 access token，以及明確的 LIVE Open API 帳戶 ID。瀏覽器不輸入 token，設定檔不可提交 GitHub。
2. `CTRADER_LIVE_TRADING_ENABLED=NO` 是預設。維持此值仍可用獨立唯讀 LIVE 連線查行情、帳戶與案例。
3. 若帳戶持有人日後要自行啟用真實資金委託，先設定正數 `GOLD_LIVE_MAX_ORDER_STOP_USD`（單筆停損情境損失上限）及 `GOLD_LIVE_MAX_GROSS_LOTS`（黃金持倉加掛單總手數上限），再明確設 `CTRADER_LIVE_TRADING_ENABLED=YES` 並重啟後端。設定空白、權限不足、非 USD、淨值不足、報價或保證金未就緒都不能送新單。
4. 每筆新 LIVE 單必填停損，先檢查草稿，核對帳戶末四碼、預估保證金、情境損失與累計手數，再由本人按「確認送出 LIVE 委託」。已接受不等於成交，回報不明時先到 cTrader 核對，勿重送。

## 已提供與目前限制

- 已提供 LIVE 報價、已收／形成中 K 棒、歷史案例查詢、Agent 分析、帳戶持倉與券商紀錄、唯讀試算、市價／限價新單草稿、市價平倉、保護價修改及掛單取消，後三項也需人工核對。自動測試使用合成帳戶，沒有執行真實資金委託。
- LIVE 限價平倉未開放。cTrader 原生 ClosePositionReq 無指定限價欄位；目前 DEMO 的反向限價方法不能直接用於真實資金。
- LIVE 交易計畫及條件提醒尚未接入獨立儲存／監測；不要把 DEMO 工具的紀錄當成 LIVE 依據。LIVE 草稿中的「交易理由」暫不保存為交易計畫。
- 停損損失與保證金是事前估算，跳空、滑價、費用及強平可能讓實際結果不同。歷史案例的結果只是事後描述，不能當成未來勝率。

## 入金

入金在 Pepperstone 官方安全客戶區選該 LIVE 帳戶後，依當頁顯示的方式、最低額、費用與地區規則操作。Gold Desk 不收款或執行入金。此帳戶截圖餘額為 0，因此目前不能建立新 LIVE 委託；足額與否要看 LIVE 商品規格、券商預估保證金與使用者設定的風險上限，不能只看某個通用最低入金數字。
