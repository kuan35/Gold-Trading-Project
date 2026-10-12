# Gold Desk 交易工作台技能選型與介面審查

查核日期：2026-10-13。此文件記錄來源選型、既有 UI 問題與已實作的工作台；券商仍未連線。

## 採用的技能

| 技能 | 來源及狀態 | 本次用途 |
|---|---|---|
| Impeccable 3.9.1 | 現有已安裝外掛，已讀 product register 並執行 context/detect | 交易工具的密度、狀態、層級、響應式與視覺驗收 |
| frontend-design | 已透過 skill-installer 從 [Anthropic 官方 skills](https://github.com/anthropics/skills/tree/main/skills/frontend-design) 安裝；已讀本機 SKILL.md | 以黃金交易準備流程決定風格，避免套用行銷網站與裝飾性卡片 |
| web-design-guidelines | 已透過 skill-installer 從 [Vercel 官方 agent-skills](https://github.com/vercel-labs/agent-skills/tree/main/skills/web-design-guidelines) 安裝；已讀技能及最新 [檢查規則](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md) | 表單標籤、鍵盤操作、焦點、數字對齊、溢出與非同步狀態審查 |

安裝位置為使用者的 Codex skills。沒有執行第三方套件安裝腳本或新增前端相依套件。新技能下輪起可由技能目錄自動載入；本輪讀取文件進行審查。

使用者列出的其他選項：UI UX Pro Max 可作資料庫參考，但本案已有明確產品情境與設計系統，暫不需要另一套生成器；GSAP 與 Stitch 偏動畫或設計稿轉換，非本輪交易終端需求；test skill、5HK、Neo design skill、文字牆排版技能缺精確倉庫連結，不能只憑影片名稱確認來源或數量，未安裝。黑白點陣字體也不適合長時間閱讀金額。未將影片宣稱的 84/23/57 項數量當作已驗證的採用依據。

## 參考站與交易介面慣例

已在瀏覽器實際讀取 [Gold Desk Workspace](https://nekomata864.github.io/Gold-Desk-Workspace/)，包括標準工作台、版型選單、尺寸調整入口、委託區與底部交易頁籤。參考其圖表主區、下單/對話/提醒切換及可調尺寸思路；不複製提案版型比較工具、Agent 標籤、裝飾卡片，也不取用其合成資料充當真實資料。

[MetaTrader 5 官方操作文件](https://www.metatrader5.com/en/terminal/help/trading/performing_deals) 的一般委託欄位為商品、類型、手數、SL、TP，並展示 Bid/Ask、持倉與歷史紀錄。Gold Desk 以這些熟悉的資訊順序為參考，保留本產品必要的草稿與風險確認。介面相似不代表已連券商，也不新增未實作的限價單、保證金或一鍵成交。

## 審查發現與建議

- `src/styles.css:52`：對話區固定 height 760px/min-height 600px，桌面交易工作區容易整頁拉長；建議改成可視高度內的面板捲動。
- `src/styles.css:43`、`src/styles.css:50`：detect 找到兩處側邊 3px 色條；視覺層級改由標題、分隔線與狀態文字表達。
- `src/App.tsx:109`：選填平常手數、標記說明與來源字串佔據主要操作空間；建議使用可展開說明，保留語義與缺資料資訊。
- `src/App.tsx:95`：主內容缺少 skip link；新增鍵盤可跳至行情與委託區的入口。
- `src/App.tsx`：表單應補 name/autocomplete/inputMode，檢查長來源文字、長回應與錯誤顯示；控制元件不可只靠顏色區分買賣。

行號是本次改版前的讀取位置，之後如實作需重新驗收。

## 已實作與驗證

使用者在聊天中確認採用後，已實作中央 K 線、右側可調寬委託區、下方持倉／成交／案例／資料頁籤。桌面同時看得到圖表與交易表；窄螢幕上下排列。右側可切換委託單、交易說明及提醒條件。採用低眩光深灰、等寬數字與有限狀態色，保留來源、回放時間、未連線標示、使用者確認及防重送流程；沒有更動相似度算法或下單權限。

鍵盤可跳至行情、用方向鍵調整右側寬度；寬度儲存在本機並可還原。1100×650 視窗曾發現對話送出鍵被裁切，已改為可捲動對話區並讓送出控制維持可見。前端 23 項測試與 Pages 建置通過；正式 Pages 模式的合成展示另以瀏覽器操作驗證。歷史交易盤面對齊仍為候選，頁面不宣稱已核實。
