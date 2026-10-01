# Gold Trading Project

## Purpose
黃金交易下單前案例檢索與風險輔助平台，供有交易經驗者在首筆或加倉前核對歷史經驗與部位變化。五人八週，先完成完整可展示流程。

## Users and scene
使用者在一般室內桌面環境長時間查看行情，用鍵盤與滑鼠準備訂單。採可切換明暗的緊湊交易工作台，首版以低眩光深色、清晰數字和有限色彩呈現，並保持日間可讀性。

## Platform
web

## Register
product

## Scope
React TypeScript Vite、Lightweight Charts；Python FastAPI。行情、部位、訂單、案例、解釋五個模組。初版採本機歷史回放和券商demo連接界面；未配置demo憑證不連線、不稱券商成交。LLM未配置時明示規則解析模式，不假裝AI。

## Constraints
財務值在後端使用Decimal並用字串傳輸。案例排序只用事前條件；結果只作已成熟歷史案例的解釋。未知時區、缺漏或順序不明須顯示。原始資料、本機匯入案例與key不得上傳GitHub。初版不訓練ML、不交易真實資金。

## Style
像券商的交易操作平台，不做行銷首頁、大卡片、聊天泡泡主頁、漸層或emoji。緊湊工具列、K線、數字表格、右側下單單、必要確認視窗。明示回放資料與時間，不寫即時行情假標籤。
