# 同學資料交接

日期：2026-10-01。

- [公開程式、網站、合成示範與 Word](https://github.com/kuan35/Gold-Trading-Project)
- [私人原始資料與處理結果](https://github.com/kuan35/Gold-Trading-Project-Data)：需要 repository 擁有者加入權限；沒有權限時會顯示 404，並非檔案不存在。

私人包含 271 份資料檔，約 157 MiB：原始交易檔 221、最新稽核 19、前次 baseline inventory 1、行情／早期特徵與說明 23、產品 runtime JSON 3、參考文件 4。另有交接 README、manifest 與檔案校驗程式。不含金鑰、憑證、環境設定、登入資訊或電腦日誌。

## 同學接手順序

1. 閱讀公開程式 `README.md`、`PRODUCT.md`、`API_CONTRACT.md`、`docs/project-report.md` 與 `docs/live-chart-and-llm.md`。
2. 有私人存取權後下載資料 repository，執行 `python verify_files.py` 核對 271 份資料。
3. 按私人 README 將 `runtime/private/` 的 3 份 JSON 複製到程式 repository 的 `private/`，可直接啟動真實案例本機版本。只用公開 repository 也可以啟動合成示範。
4. 需要重新分群時，使用 `raw/statements/`、舊 baseline inventory 與公開程式 `research/` 工具；輸出到新的 private 資料夾。重新匯入使用 `market/xauusd_5m_bars.csv`。

私人資料必須保持 private，不能放到公開 repository 或 Pages 前端。公開網站回放依舊使用合成資料，TradingView 嵌入僅供即時看盤，尚未接券商 API 或外部 LLM。

交接前已用複製後的原始資料重新執行分群，9 項主要計數／來源檢查全部與既有稽核相同。PDF 文字抽取本次未重現既有 30 筆數值列，因此保留既有 PDF 原件與稽核結果供檢視；PDF 買賣方向仍未知，兩次均未納入交易分群。重新執行不保證所有輸出檔案逐位元相同，原始／交付資料完整性另由 manifest 核對。

## Word

目前產品專題 Word 是 `docs/黃金交易輔助平台專題報告_v1.docx`（標楷體、至少 12pt）。它不是先前的「規則精煉」舊版企劃書。較晚新增的 TradingView 即時看盤與訂閱路線在 `docs/live-chart-and-llm.md`；Word 尚未合併這些晚於初版報告的更新。

## 資料版本限制

最新刷新資料與早期 v3 特徵集是不同來源版本，不可混用 record ID 或把不同表列數相加。全量來源觀察列、候選操作群與獨立決策分開看；時區／完整性與同分鐘順序仍有未知。早期 BUY/SELL 標籤以已下單為條件，不是會不會下單標籤。沒有同學的 XGBoost 程式與實驗結果，因尚未收到，交接包不能宣稱包含它們。
