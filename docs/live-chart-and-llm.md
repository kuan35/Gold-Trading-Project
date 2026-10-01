# 即時圖表與 LLM 連線選擇

日期：2026-10-01。

## 已實作的即時看盤

TradingView Advanced Chart Widget 免費提供嵌入，保留品牌與來源連結。網站的「即時看盤」載入 OANDA:XAUUSD，預設 5 分 K 與 UTC，可用圖表工具切換週期、畫線與加指標。開市／來源正常時自動更新，時效與休市狀態依外部圖表判讀，網站不聲稱自行驗證每筆報價延遲。

即時看盤與回放演練分開：前者沒有下單／對話執行表單，也沒有回放成交價與帳戶表格；切回回放保留本次模擬持倉。外部圖表不會推進回放或提供價格給風險引擎。僅開啟即時頁時載入第三方圖表，切換／主題變更清理旧容器；載入失敗提供重試與 TradingView 原站連結。

圖表是看盤元件，不是券商 API。Widget 沒有可取出行情與指標值的資料 API，後續整合成交與風險仍需選定行情來源。未設定／使用任何券商或 LLM 金鑰。

## API、Pi 與訂閱額度

Pi 是 agent 框架與客戶端，不是模型或免費額度供應商。其官方 README 提供 ChatGPT Plus/Pro (Codex) 的訂閱登入、API key，以及 SDK/RPC 整合；技術支援登入不等於網站可共用個人帳戶的訂閱給所有訪客。

- 自己本機測試：可考慮 Pi＋本人授權的訂閱登入；共用相同訂閱限額，需處理登入、token 更新與並發，尚未在本專題驗收。
- 多人公開網站：建議先以後端呼叫 API，方便控制每位使用者的資料、用量與回應格式；金鑰不可放 GitHub Pages。
- 每位使用者帶自己的訂閱：OpenAI 官方 Sign in with ChatGPT 已提供符合資格的開源應用使用訂閱路線，但須完成應用註冊、個別使用者 OAuth 授權與資格核對，且有預覽 API 限制。這是可評估擴充，不必依赖 Pi；不能把現有 API key 呼叫改名成訂閱呼叫。

目前只有 LLM 解釋介面及本機規則解析，没有完成 Pi、訂閱登入或外部 LLM 連線。程式負責計算、檢索與確認；LLM 只接收必要摘要，不能自行送單。模型選擇須通過繁體中文草稿解析與證據忠實性測試。

## 官方來源

- [TradingView 免費 Widget](https://www.tradingview.com/widget/)
- [TradingView Widget 資料限制](https://www.tradingview.com/widget-docs/faq/data/)
- [Pi 官方專案](https://github.com/earendil-works/pi/tree/main/packages/coding-agent)
- [OpenAI Sign in with ChatGPT](https://developers.openai.com/siwc/quickstart)
- [訂閱路線預覽限制](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)
