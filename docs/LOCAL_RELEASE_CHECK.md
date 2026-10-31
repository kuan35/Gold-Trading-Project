# Windows／macOS 本機分發驗收（2026-10-31）

本輪以現有React／FastAPI為基礎，公開包是產品根目錄，沒有多一層product。
完整私人資料與公開程式分開，未將新私人資料或登入憑證上傳。

已驗證：

- Windows Python3.11全新目錄：獨立venv、pip依賴、npm ci、一般build成功；重跑安裝保留設定。
- 無私人資料／AI／券商憑證也能啟動，首頁及JS資產HTTP200，程式解讀可用。
- 原工作區完整後端620 passed、1 skipped；前端143 passed，一般與Pages建置成功。
- 不含私人案例／憑證的獨立安裝包：後端621 passed，前端143 passed，一般與Pages建置均成功。
- 私人包379檔，獨立匯入並驗SHA；11,902案例、10,887參考盤面，進出場／後續／原生tick索引可載入。
- 官方Codex僅查help、登入與模型metadata，8個本人可用模型；未進行真實模型推論。
- 原生CLI以本機假模型檢查工具清單：僅request_user_input，無shell／檔案／網路／MCP工具；若回應含工具呼叫會拒絕。
- 一次獨立程式審查發現「部分資料包可能破壞完整資料」，已先重現再補匯入前runtime驗證；失敗還原測試通過。
- 原243份對帳單／根目錄文件圖檔SHA前後一致。

尚未驗證：

- macOS實機執行。已提供共用Python核心、POSIX入口及Windows／macOS CI矩陣；Windows上的shell語法檢查不等於Mac實測。
- 每位組員的官方AI登入、付費推論、cTrader OAuth及本人DEMO帳戶；需由本人在自己電腦完成。
- 瀏覽器實際點選／視覺驗收。本輪只有HTTP、SSR與自動測試，未宣稱已點選所有操作。

CI需公開程式推送後才會執行；請以實際workflow結果確認Mac是否通過。
既有大bundle提示與Starlette/httpx棄用提示仍在，不影響本輪已通過的建置／測試。
公開首頁Pages仍是靜態展示，不能從網頁呼叫另一台電腦的本機CLI或私人券商後端。
