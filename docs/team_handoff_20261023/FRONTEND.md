# 前端同學／Codex任務

先讀 [共同入口](README.md) 與API契約。目標是將目前React工作台接到同學部署的真後端，保留聊天與委託共用草稿流程。

## 這次接手的最新介面

已包含參考圖的深灰金色三欄聊天工作台，以及即時看盤、回放、案例詳情、提醒與帳戶分頁的統一樣式。沿用 React／TypeScript／Vite／Lightweight Charts，沒有新增 UI 框架。實作與驗收見 [聊天工作台](../product_conversation_desk_20261023.md)、[其他分頁](../secondary_pages_20261023.md)。請延續這一版，先接通服務，避免另寫一套草稿。

以下路徑從公開 repo 根目錄起算（原開發工作區才有外層 `product/`）：

| 入口 | 接手時要保留的行為 |
|---|---|
| `frontend/src/DeskRouteFrame.tsx`、`DeskChrome.tsx` | 共用外框、導覽與行情頁首；保持 children 位置，切頁不能重掛載聊天而清空草稿 |
| `ConversationWorkspace.tsx`、`ConversationReply.tsx` | 固定上下界、可調大小聊天；短答、支持／相反訊號、案例卡；詳細資料收合 |
| `deskConversations.ts` | 瀏覽器唯讀文字歷史，上限12段／每段20輪；不儲存或還原可執行草稿、提案、確認 key；尚非後端多人會話 |
| `SharedTicket.tsx`、`ConversationOrderReview.tsx` | 聊天與側欄共用草稿；改數值簡短回饋，方向變動重查，最終仍須人工確認 |
| `DeskAccountTray.tsx`、`BrokerAccountPanel.tsx` | 真 DEMO 持倉、待成交、紀錄；未連線不當零筆，過期損益不當最新值；可見頁才掛載帳戶區，避免重複 ID |
| `LivePageGuide.tsx`、`productDesk.css`、`secondaryPages.css`、`chartTheme.ts` | 其他分頁、圖表色票與手機版；舊 CSS 優先度曾造成工具列遮蔽與 K 線高度不足，改版須重驗 |

完整新聊天工作台位於一般 build，使用 FastAPI；`build:pages` 仍為另一個靜態展示入口。Pages 有新配色與其他分頁樣式，不會因此取得本機 cTrader、帳戶、歷史文字儲存或新聊天工作台的全部能力。切勿只看 Pages 就認為程式缺少本機功能。

## 負責範圍

`frontend/`。先盤點App、ConversationWorkspace／Reply／Charts／Resize、SharedTicket、ConversationOrderReview、CaseComparison／Operations、demoMarket、useLiveCandles、BrokerAccountPanel。不要整頁另寫第二份草稿與確認流程。

## 執行順序

1. 取得後端共同commit與測試URL，核對API_CONTRACT。部署真後端的前端使用一般build；build:pages是獨立瀏覽器示範引擎，不能拿它驗證券商後端。
2. 使用同源/api或由後端確認的base URL與認證方式；api.ts以外，直接fetch、EventSource與圖表串流也要逐一接上。不能只改api.ts就聲稱全站已切換。
3. 接登入／角色與會話逾期狀態。報價可共用，持倉／草稿／成交紀錄須由後端權限提供；UI顯示鎖不能取代後端授權。
4. 保留聊天主入口、頁首tick、共享欄位、假設比較不改草稿、說方向即檢索、固定快照與人工確認。歷史結果及幣別未知照實；排序分數不是獲利機率。
5. 保留聊天區內捲動、寬高調整、Q&A與詳細依據收合、手機單欄；首頁不預設K線，按需同頁展開並保留對話與輸入。
6. 核對交易與資料狀態：連線中／未連線／過期、讀取失敗、五種檢索狀態、取消、拒絕、已接受、部分成交、UNKNOWN與已成交。送單後不確定就查原key結果，不自動再送。

## 可交付證據

執行package.json中的test與build；若保留公開示範再跑build:pages。用實際瀏覽器驗多輪對話／舊訊息捲動／大小調整／快照圖表／手機排版／重新登入；核對新訊息與報價不覆蓋尚未提交欄位。用假後端或測試資料驗確認；真DEMO的最終確認由擁有者操作。提供部署URL、實際使用API來源、console與錯誤狀態驗收、PR及契約差異。

## 可直接貼給Codex

「我是前端負責人。請先讀 AGENTS.md、HANDOFF.md、TEAM_HANDOFF.md、docs/team_handoff_20261023/FRONTEND.md 及 API_CONTRACT.md，延續 frontend/ 接同學後端。先跑 npm test、npm run build 與 npm run build:pages，核對認證及一般 build 的 API／SSE 接線。保留目前深灰金色工作台、跨頁共用草稿、固定快照、唯讀文字紀錄、案例與人工確認。手機版驗聊天捲動與大小調整、圖表高度、表格不撐寬頁面；報價與回覆不得覆蓋尚未提交的欄位。未約定的後端需求列契約差異，不另做假成交補介面。交付 PR、測試紀錄、預覽網址及仍缺的後端設定；真 DEMO 最終確認由帳戶擁有者操作。」
