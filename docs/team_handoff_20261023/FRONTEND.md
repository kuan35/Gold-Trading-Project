# 前端同學／Codex任務

先讀 [共同入口](README.md) 與API契約。目標是將目前React工作台接到同學部署的真後端，保留聊天與委託共用草稿流程。

## 負責範圍

product/frontend。先盤點App、ConversationWorkspace／Reply／Charts／Resize、SharedTicket、ConversationOrderReview、CaseComparison／Operations、demoMarket、useLiveCandles、BrokerAccountPanel。不要整頁另寫第二份草稿與確認流程。

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

「我是前端負責人。請依共同入口與本文件，延續product/frontend接同學後端。先核對API、認證及真後端build模式，修復整合缺口，保留現有共享草稿、固定快照、案例與人工確認流程。未約定的後端需求列契約差異，不另做瀏覽器假成交來補介面。」
