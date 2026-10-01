# 私人交易資料稽核工具

此資料夾只含程式與合成測試，不附原始資料。保留 Decimal、原始字串、存提款、非黃金商品與解析問題。分類描述可見部位關係，不推論心理或完整策略。

從產品根目錄執行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r research/requirements.txt
.\.venv\Scripts\python.exe -m pytest -q research
.\.venv\Scripts\python.exe research/scripts/profile_trade_behaviors.py --input C:/path/statements --output private/baseline
.\.venv\Scripts\python.exe research/scripts/refresh_trade_case_data.py --input C:/path/statements --baseline private/baseline/source_inventory.csv --output private/audit
```

輸出資料夾須新建或為空，不覆寫既有稽核。首次 baseline 由 HTML/Excel 舊解析建立；刷新器另讀 CSV 與可辨識 PDF 數值。來源格式有限，不保證支援任意券商。PDF 方向不可讀維持 UNKNOWN；CSV 分鐘精度不補秒，時區未知，跨檔重複只標候選。

完整來源清單、原始列、來源帳戶與雜湊留在 private；不要上傳。刷新後 group ID 可能改變，匯入產品需要用新稽核的 case ID／版本。雖有 sanitized_case_records.csv，它仍含個人逐筆資訊，也不應公開。
