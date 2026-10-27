# 相似案例與助手評估：本輪交付

2026-10-23。依 [凍結協定](similarity_evaluation_20261023.md) 完成離線工具、資料與盲評材料；人評尚未填寫。取得使用者具體外傳授權後已實際呼叫Groq，遇429依協定停止。這份文件不宣稱相似準確率。

## 已實際完成

| 項目 | 實際結果 |
|---|---|
| 查詢 | 30個不同UTC日期，2024年17個、2025年13個；BUY17、SELL13 |
| 抽樣 | 月份輪流、固定雜湊、方向偏好交錯；排除先前51查詢日期；完整雙週期、不同群及查詢窗口不重疊；不讀損益或檢索結果抽樣 |
| 分組 | 本輪時間前20個開發組、後10個保留評分組；尚未依本輪人評調參 |
| 現行規則 | context_contract_v1，中檔容忍不改；22次有符合、8次全部未通過 |
| 比較材料 | 現行第一名22筆、舊雙路徑第一名30筆、固定同池對照30筆；同查詢同案例合併後79組匿名配對 |
| 圖表 | 79張四格PNG、79頁PDF與HTML閱讀頁；5m60／1h20、同欄共尺度、首收歸零、參考高低與末六棒 |
| 人評 | 兩份79列CSV，固定分母158個配對評分機會；實際已填0，不報yes比例或人評準確率 |
| 助手 | 6組相同去識別事實、6題，程式摘要與兩種提示詞；上限12次，實際3次，2次成功、1次rate_limited後停止，其餘9次未執行 |
| 穩定性 | 重跑後selection、results、匿名資料、解盲鍵與兩份評分表SHA全部一致；評分表不覆寫 |
| 測試 | 新工具16 passed；連既有檢索／助手回歸共106 passed、1 skipped；保留既有FastAPI/httpx提示 |
| 原件 | 交易員資料與根目錄原件241份SHA全部不變 |

22／30是「通過自定條件的查詢數」，不是相似準確率。固定對照也可能真的相似，不預先把它當負樣本。79配對不等於79個獨立市場情境，同一查詢可有多個對照、同一歷史案例也可能重複出現。

## 先給評分者

本機資料夾 `private/similarity_evaluation_20261023/`：

- `匿名盲評材料.zip`（約7.43 MiB）：只含匿名HTML、79張PNG、79頁PDF、兩份空白CSV及評分說明；不含解盲鍵或原始結果。
- `開始評分.md`：欄位、1–5分與yes／no／insufficient定義及獨立評分步驟。
- `review.html`／`匿名K線對照.pdf`：看圖。
- `reviewer_1.csv`／`reviewer_2.csv`：兩位各填自己的表；請保存UTF-8，不討論後再回填。

評完後執行摘要，會分開報：各方法完整分母／已評／不足／未填、有效yes比例、共同查詢子集、開發／保留組及兩人一致性。若某人缺交或刪列，分母也不會縮小。這裡量測檢索相關性，不是獲利預測。

## 助手仍待哪一步

`assistant_samples_PRIVATE.json` 已準備六題；`assistant_review.html` 含六份程式摘要、兩份成功模型回答，以及一次限流的程式降級。其餘九份模型版本明示未取得回答，不可填作模型成功。`assistant_summary.json` 與 `assistant_human_summary.json` 所有人評結果維持空值。

第一次命令被自動審核拒絕，理由是對這批私人案例衍生內容的具體外傳授權及去識別化確認不足。沒有繞過；完成payload檢查後，使用者明確回覆「同意這批內容送至Groq，最多12次」，才重新執行。全程沒有列印或保存金鑰。

`outgoing_payload_preview.json` 是準備外傳的12份內容；`payload_audit.json` 是執行前檢查，當時外部呼叫0；最終執行數見 `assistant_run_receipt.json`。catalog只含模板、token名稱及定性狀態，無原始K棒、精確價位、日期、原始案例ID、帳戶或損益。數值仍由程式在本機填回。獨立審查另補了整段淨上行／淨下行定性依據，避免模型只看占位符卻不知道方向。實際先後交錯，第三次API返回rate_limited便停止，沒有重試。

成功兩次來自同一題：現行提示詞需部分程式補正，範例提示詞該次完整通過引用／數值格式檢查。這只能證明端到端接通與守衛有作用，樣本不足以判定哪種提示詞較好。另有待人評核對的說法：模型將「段落淨變動小」延伸成走勢平緩，或用「後半段」描述僅最後半小時；格式檢查無法證明這類語意正確，不能以完整通過格式當成全答對。

耗時分開記錄成功回覆與所有嘗試，避免快速429被誤算為回答較快。原提示詞成功約1.85秒；範例提示詞成功約1.79秒，只有各一份，不能當效能比較。後續可在額度恢復後另開新評估輸出保留本輪，不覆寫或自動續送。

正式比較同一份資料及守衛：原盤面提示詞＋共同離線說明，對照再加兩個固定範例。所有段落仍驗數值引用；保留原文、自動補正與最終顯示分開。人工對最終文字評忠實、切題與易懂，不把補正後好評當原模型能力，也不把格式通過率當語意正確率。

## 重跑命令

在產品根目錄執行。索引與輸入依現有loader完整性校驗；新增資料後請使用新的private輸出資料夾，勿覆蓋既有凍結樣本或評分。

```powershell
# 產品venv：離線檢索、摘要與測試（不呼叫模型）
.\.venv\Scripts\python.exe -B -X utf8 research/similarity_evaluation.py --no-render
.\.venv\Scripts\python.exe -B -X utf8 research/similarity_evaluation.py --summarize
.\.venv\Scripts\python.exe -B -X utf8 research/assistant_evaluation.py
.\.venv\Scripts\python.exe -B -X utf8 research/assistant_evaluation.py --summarize
.\.venv\Scripts\python.exe -B -X utf8 -m pytest -q research/test_similarity_evaluation.py research/test_assistant_evaluation.py
```

完整建圖需既有 `research/requirements-evaluation.txt` 的matplotlib／numpy。此機產品venv未安裝matplotlib，本輪用已安裝matplotlib3.10.9的系統Python讀取固定blind_pairs.json建圖，沒有安裝新套件或改網站依賴；有完整評估依賴的Python可直接跑 `research/similarity_evaluation.py`。

模型評估保護已完成：未啟用不呼叫、API失敗停止、原文／補正分開、實測結果檔存在就拒絕覆寫。`--summarize` 只彙總現有人工表，不發外部請求；模型呼叫不能因重新做摘要而重跑。

## 怎樣向老師解釋用途

「我們先從進場前盤面找出可比較的歷史操作，再讓使用者看到相似點、差異與當時結果。目標是增加決策資訊的可查證性，協助討論與風險檢查；是否提高獲利尚未驗證。我們分開評案例適不適合比較、助手是否忠於資料及使用者是否看得懂，而不把歷史獲利比例當這次成功機率。」

這一輪不改正式排序、不微調模型、不新增送單能力，也未同步公開發布包。評分者的資料請私下分享；完成的人評及匿名統計可再整理為報告成果，是否公開另檢查白名單。
