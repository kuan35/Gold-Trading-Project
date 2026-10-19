# Frontend API contract v1

## Optional public Groq explanation proxy (2026-10-13)

This Cloudflare Worker is separate from the local `/api` contract. When configured, Pages may POST `/explain` with `{message,facts,token}` after explicit visitor opt-in and Turnstile verification. It returns `{message,provider:"groq_explanation"}`. `facts` contain the synthetic replay snapshot and aggregate counts from the public real-case retrieval; they exclude per-case rows and credentials. The Worker validates the Turnstile token with Siteverify, checks hostname/action, and keeps `GROQ_API_KEY` / `TURNSTILE_SECRET_KEY` in Worker secrets. The response is display-only: it cannot create or confirm drafts, change similarity results, or execute orders. If absent or unavailable, `/chat` remains the local deterministic browser implementation. See `groq-proxy/README.md`.

All amounts/prices/lots are decimal strings. OHLC plotting is numeric. REST base /api. Errors JSON {detail: string}. Modes replay and broker_demo. Synthetic demo is clearly named, private imported data source is labelled.

- GET /api/state → {mode,version,clock,data_source,broker_connected:false,llm_enabled:false,quote:{bid,ask,time},account:{balance,equity},positions:[{id,side,lot,entry,sl,tp,pnl,opened_at}],pending_orders:[{id,side,lot,limit_price,sl,tp,created_at,action,status:'PENDING'}],orders:[{id,side,lot,price,status,time,action,pnl}],market:{change_pct,range_pct,high,low,ma20,ma60},data_quality:[string]}
- GET /api/bars?interval=5m|15m|1h&focus=optional_order_id → {bars,markers,source,interval,focus,analysis}. Unknown focus returns 404. GET does not advance time or alter positions.
  - bars: complete closed OHLCV only. Default latest250; focused view includes selected entry/exit plus100 bars before (enough for MA60) and40 after if already known, possibly more than250 for long holds.
  - new markers: {id,position_id,action,time,executed_at,price:decimal_string,time_precision:'snapshot'|'bar',position:'belowBar'|'aboveBar',color,shape,text}. price is execution price; time anchors to last available CLOSED candle at the event (boundary uses just-closed candle). executed_at is original replay timestamp. Higher frame forming candles are never fabricated. time_precision=bar for OHLC stop/target triggers, not precise execution seconds. Legacy case markers without price may retain aboveBar/belowBar.
  - focus: null or {selected_id,order_ids,orders,pairing:'linked'|'open'|'unavailable',note}. New fills and exits carry position_id. Old exits missing this key are not guessed. Other orders inside the visible window can still appear, selected prices have reference lines.
  - analysis: current replay snapshot, even when focusing OLD trades: {interval,count,last_closed_at,rsi14,macd_line,macd_signal,macd_histogram,atr14,boll_lower,boll_middle,boll_upper,source_volume_ratio,levels,definitions}. Financial values are decimal strings, missing values null. Wilder14 RSI/ATR; SMA-seeded EMA12/26/9 MACD; population-SD Bollinger20×2. Source volume ratio is latest source volume / prior20 average, not global volume.
  - levels: candidate supports/resistances from120 closed bars, strict local pivots with2 closed bars on each side; same-kind pivots merged within max(ATR14/4,0.20), nearest2 per side of last close. Each {price,pivot_count,confirmed_at}. This is not a trader-drawn line, validated reversal probability or historical decision-time signal.
- POST /api/replay/step {bars:1|6|12} → state; POST /api/replay/reset {} → state; POST /api/mode {mode:'replay'|'broker_demo'} → state. Switching mode to unconfigured demo clearly disables submitting; no synthetic broker response.
- POST /api/drafts {side:'BUY'|'SELL',lot:'0.10',sl:null|string,tp:null|string,order_type:'MARKET'|'LIMIT',limit_price:null|string} → {id,revision,side,lot,sl,tp,price,order_type,limit_price,action:'FIRST'|'ADD'|'OPPOSITE',status:'REVIEW',risk:{before_lot,after_lot,average_entry,stop_loss_usd:null|string,reward_risk:null|string,scenarios:[{move,loss}],warnings:[string]},retrieval:{total,wins,losses,flat,unknown,win_rate:null|string,cases:[Case],limitations:[string]},explanation:string}. MARKET 預設且限價須空；BUY LIMIT 低於當前 ask，SELL LIMIT 高於當前 bid，0.01 單位。
- POST /api/drafts/{id}/confirm {revision:number,idempotency_key:string} → {status:'FILLED'|'PENDING',order_id:string,state}; 限價確認後僅列待成交，409 stale/repeated other-version，503 unconnected broker。POST /api/drafts/{id}/cancel {} → {status:'CANCELLED'}。
- POST /api/pending/{id}/cancel {} → {status:'CANCELLED',order_id,state}；已觸價或不存在回 409。回放下一根已收 5m K 棒以固定 0.30 價差的 ask low（BUY）或 bid high（SELL）判定限價觸及，以指定限價模擬成交；不重建棒內先後、排隊、價差變動、跳空改善價、滑價或同棒停損停利。重設清空待成交單。
- POST /api/positions/{id}/close {confirmed:true,idempotency_key:string} → {status,order_id,state}. UI confirmation required; close must still work when entry cases absent.
- POST /api/chat {message:string,lot?:string,side?:string} → {message:string,draft:Draft|null,provider:'local_rules'|'configured_llm'}. Never auto-confirm.
- GET /api/cases?side=BUY&action=FIRST&lot=0.1 → retrieval (same fields as draft).
- GET /api/cases/{id} → Case + {bars:[],markers:[]} when true verified OHLC exists, otherwise clear empty-chart reason; no invented chart.
- GET /api/audit → {source_files,total_gold_records,period,groups:[{code,label,count,description}],limitations:[string],refreshed_at,source:'synthetic_demo'|'private_audit'}.

Case = {id,label,side,action,lot,entry,exit,opened_at,closed_at,profit,distance,match_reasons:[string],differences:[string],group,source_kind:'synthetic_demo'|'trader_history',time_alignment:'confirmed'|'unknown',behavior,sequence:[{index,side,lot,entry,exit,profit,role}]}. Historical outcomes are available only before query clock. UI must show source and limitations; never call win_rate a forecast.


## Operation similarity extension (2026-10-12)

`POST /api/drafts`, `POST /api/chat` accept optional `typical_lot: null|string`;
`GET /api/cases` accepts optional `typical_lot` query string. Empty/null means absolute-lot comparison;
a supplied non-positive/non-finite value returns 400. It is the user's declared usual order lot,
not account equity or a broker lot conversion. Chat and form share the same retrieval.

Retrieval additionally returns:
- `profit_cases`, `loss_cases`: closest six of each outcome, selected AFTER full matching/group deduplication.
- `cases`: up to three profit and three loss cases, shortages filled by nearest remaining candidates.
- `comparison`: `{method,basis:'relative_lot'|'absolute_lot',max_distance:0.65,excluded_missing_profile,market_features_enabled:false,parameters_validated:false}`.
- `sufficiency`: `{status:'usable'|'limited'|'insufficient',label,reasons:string[],matched_groups,is_success_probability:false}`.
- Each ranked Case has `comparison_basis`, `missing_features`, `components:[{feature,label,query:null|string,case:null|string,weight,distance,missing}]`.

The full matched pool statistics do not change when displaying profits/losses. Distance is not
a forecast probability. FIRST relative-lot matching requires a past-only profile for the historical case;
missing-profile cases are excluded from that mode, never silently compared with another distance basis.
Historical profiles use the previous 20 completed local 5m order batches per source, with at least
10 batches across 3 dates. Source is not a verified account; ordering and completeness remain provisional.
ADD dimensions: lot scale .35, same-side count .20, new/prior lot .25, signed distance-to-average .20.
Missing ADD dimensions retain their weight with distance 1. Hard guards: lot/exposure scale <=2x,
signed-price gap <=0.5 percentage points, opposite favorable/adverse signs beyond +/-0.02% rejected.
FIRST distance uses only the lot scale. Maximum weighted distance .65; unvalidated engineering defaults.
No P/L, holding duration, close price, future sequence or market shape enters distance.

Evidence: fewer than 5 matched groups is insufficient; 5-29 or missing information is limited.
Unverified clocks, absolute-only comparison, incomplete fields or unverified independent sources cap
the result at limited. At present all private sources remain unverified, so usable is not emitted.
Case detail still returns no unverified historical candles. Private profiles live in
`private/case_size_profiles.json`; stale case-file hashes disable profiles and disclose the reason,
while absolute comparison and the rest of the app remain available. No private source identifiers
or profile metadata are returned in Case responses.


### 2026-10-12 LLM explanation contract

- `POST /drafts` and `POST /chat` use the same anonymized, closed-bar market and retrieval summary when external LLM use is enabled. No-match is valid and never forces a looser match.
- Drafts add optional `llm: {status, model, provider?}`; chat adds `llm_status` and `model`. `configured_llm` is returned only after a complete, nonempty response. Disabled, expired-key, timeout and provider failures preserve deterministic summaries and pending drafts.
- `state.llm_enabled` means configured, not verified connectivity or valid credit. The model receives no original identifiers, files, account numbers or access tokens. Examples use request-local H1/H2 labels.
- Explanations include mode/time, completed 5m/15m/1h bar statistics, operation-based matches/differences, matured outcomes and known gaps. Live TradingView contents are not available to this API. Volume, confirmed trendlines and validated support/resistance remain unavailable.
- Network waits occur after the snapshot is captured, without holding the global engine lock. Confirming still checks the original draft revision; explanations cannot execute orders. No LLM output determines retrieval distance, financial arithmetic or rule triggers.

### Grounded explanation card (2026-10-12)

Draft and chat responses add optional `explanation_card`:
`{version:1,as_of_utc,origin:'model_selection'|'program',status,model,sections:[{id,title,facts:[{id,text,source,evidence}]}]}`.
Four sections: `market`, `history`, `risk`, `limits`. `evidence` contains anonymized program-produced values only.
Chat also returns `intro` (draft/instruction notice). Existing `message` and `explanation` remain text equivalents for older clients.

The production chat/draft path asks the model ONLY for a JSON selection of fact IDs. All displayed sentences and numbers are generated from the decision snapshot, not model prose.
Unknown, duplicate, missing, or cross-section IDs reject the entire selection (`invalid_selection`) and use deterministic defaults. Required context, evidence caveats, risk facts and profit/loss examples when present cannot be hidden by model selection.
`ok` / `configured_llm` now means validated model selection, not free-form financial reasoning. Disabled/failure responses return the same card with program origin and honest status.
The low-level legacy free-text helper is retained for compatibility tests; product routes do not use that mode. Model selection is not a truth verifier or a validated recommendation engine.
The scenario values are total floating P/L of all positions including the hypothetical order, NOT incremental loss from now. The existing replay assumes 100 oz/lot and a 0.30 quote spread; scenarios do not execute stops or include slippage, fees or overnight financing. No broker specifications are inferred.
Cards are immutable snapshots. Existing revision checks and user confirmation still control execution.


### Descriptive market reading / arrow markers (2026-10-12)

Bar analysis adds optional `reading: {bias,label,reasons,indicators:{rsi,macd,atr,bollinger,volume},method}`.
`bias` is bullish, bearish, bullish_pullback, bearish_rebound, mixed or insufficient.
The server describes close/MA20/MA60 structure; RSI45–55 is an explicit neutral buffer and MACD zero/signal positions are explained separately. No fitted accuracy, probability or forecast is implied. ATR and source volume never determine direction. Missing MA60 warmup returns insufficient.
Market explanation catalog adds `{interval}.reading`; 5m reading is mandatory so model ID selection cannot hide the direction's numerical basis. Current-frame UI uses the same program-owned text. Other frames require that frame's complete candles.
All execution markers use BUY arrowUp/belowBar and SELL arrowDown/aboveBar, including close orders. `price` remains the exact executed-price string for labels and focused price lines; the arrow's Y location is deliberately outside the candle, not the executed price. Order record linkage, timestamps and conservative closed-candle anchoring are unchanged.


## 個人提醒規則（2026-10-12）

POST `/api/drafts`、`/api/chat`、`/api/drafts/{id}/confirm` 可帶 `personal_rules`，預設空清單。規則保存於前端此origin的localStorage `gold-personal-rules-v1`，不在後端共用帳戶保存，沒有跨裝置同步或登入隔離的宣稱。

每條固定欄位：`{id,kind,value,op,enabled,side}`，最多50條、id唯一。kind為 `order_lot/after_lot/same_side_count/missing_sl/stop_loss_usd/market_bias`。前三種與stop_loss_usd的value為正有限十進位字串，op為gt/gte，筆數必須整數。missing_sl為value=null/op=is。market_bias為value=bullish/bearish/bullish_pullback/bearish_rebound/mixed、op=is。side為ANY/BUY/SELL；其他欄位拒絕。

草稿與一般聊天回應新增 `personal_rules:{source:"program",reminder_only:true,results:[{id,text,status,actual,reason}]}`。status為triggered/clear/unknown，停用規則不參與。沒有草稿時，訂單條件unknown；market_bias限定方向也需草稿。after_lot為所有多空部位手數絕對值總和加新單，same_side_count為下單前同方向筆數，不含新單。

提醒不阻止使用者確認成交，但確認時規則清單須與草稿快照相同，不同回409要求重建草稿。行情／帳戶變更仍依既有revision檢查。重送已成功確認維持冪等。規則設定、假設或否定語句先隔離，不可走訂單解析。

口語設定採本地明確語句解析，不呼叫LLM猜規則；支援「單筆超過0.1手提醒我」「沒設定停損就提醒我」「把第1條改成0.2手」「暫停第1條」「列出我的規則」。複合條件、含糊單位及不支援週期要求使用管理表單。新增／修改／暫停／啟用／刪除均先預覽並由使用者確認。無法保存報錯，既有壞儲存不覆蓋。

頁面開啟且使用回放時，5m任何方向分類會隨已收棒更新；持續觸發不重複新增對話。不是背景24小時監控。Pages使用合成資料與decimal.js檢查；缺乏技術判讀會回unknown，不借用iframe即時行情。


## Operation / market evidence axes (2026-10-12)

### 本機參考盤面模式（2026-10-18，覆蓋下述舊檢索說明）

`trader_history` 使用經 SHA-256 綁定的私人 `case_candidate_market_profiles.json` 及其進出場標記台帳。專題可用門檻：來源時間模型有唯一進場時刻，進出場皆定位到參考五分鐘棒且時序一致，進場前有足夠已收 K 線形成特徵。原有 10,921 筆特徵中 10,887 筆符合（完整三週期 6,542、五分鐘限定 4,345）。這是「參考盤面可用」的操作定義，不等同券商原始時鐘獨立核實。`GET /api/cases`、草稿與聊天共用回放決策時刻及已收完 K 線；`action`、`lot`、`typical_lot` 仍為既有 API／下單驗證欄位，但案例檢索只按 `side` 篩選，手數與盈虧不參與排序。來源側檔失效或查詢盤面不足時，`candidate_market_unavailable_reason` 說明原因，回傳空案例，不退回操作權重。

`comparison.mode='candidate_market'`（相容欄位名稱）、`alignment_scope='PROJECT_REFERENCE'`、`clock_status='UNKNOWN'`、`independent_clock_verified=false`、`similarity_sufficiency='UNCALIBRATED'` 表示本機參考盤面近鄰。`production_enabled=false` 仍保留為原時鐘／券商成交的嚴格旗標，不否定專題檢索可用。`total`／`cases`／`full_cases` 是完整三週期層；`five_minute_only_total`／`five_minute_only_cases` 是獨立的五分鐘限定層。`comparison.method='path_indicator_pattern_v1'` 表示 60 根已收五分鐘 K 線的首棒百分比收盤路徑與技術指標分軸排名，按兩軸較差者排序；每層前 15 個不同操作群內，三段固定走勢型態完全相同者提前，最後各展示前五。五分鐘限定層只用五分鐘指標，不與完整層比較分數。`comparison.query_pattern_code`、`query_market_text` 與 `rerank_window` 說明查詢盤面；案例的 `path_rank`、`path_distance_pct`、`indicator_rank`、`pattern_code`、`pattern_match`、`market_state_text` 說明逐案結果。`shape_rank` 保留舊欄位相容，此方法下值等於 `path_rank`。相對排名不是準確率，型態取自同一批 K 線，沒有獨立訊號或足夠相似門檻。查詢時若沒有合格案例回 `NO_MATCH`；有案例回 `UNCALIBRATED`，不表示足夠相似。`GET /api/cases/{id}` 僅在成熟且側檔有效時展示 60 根進場前已收盤參考行情，不畫進出場點；對時依據在詳情中揭露。LLM 僅接收去識別化的方向、層級、盤面固定描述、兩軸排名、型態與限制。

2026-10-19 起，公開 Pages 的回放行情／模擬成交仍為合成資料，但案例檢索改用使用者明確核准公開的真實逐筆案例。靜態檔為 `data/trader-cases.json`（11,902 筆原樣案例資料）、`data/trader-market-index.json`（10,887 筆進場前路徑、指標、三段型態及固定文字）和 `data/synthetic-query-profiles.json`（361 個合成回放查詢盤面）。Pages 在瀏覽器內依本節 `path_indicator_pattern_v1` 流程排序，`comparison.basis='synthetic_query_real_history'`，來源時鐘 `UNKNOWN`、`similarity_sufficiency='UNCALIBRATED'`。靜態檔案可公開下載，不包含金鑰、帳戶號碼或原始對帳單。以下舊版操作／盤面權重契約只供原型與向下相容，不適用目前檢索。

Retrieval `comparison` adds `mode:operation_only|market_and_operation`, `operation_candidates`, `verified_market_candidates`, `excluded_unverified_market`, `query_market_ready`, `market_matches`, and a program-generated `reason`. Counts of market-eligible rows are distinct from deduplicated operation candidate groups. `market_features_enabled` indicates this query's actual filtering mode, including a zero-match strict result; it is not a global coverage claim.

Ranked cases add `operation_distance`, `operation_comparison:{distance,label,strength:weak|limited,reason}`, and `market_comparison:{status:matched|unavailable,label,reason,distance,coverage,components}`. Market components have the same decimal-string query/case values and dimensionless distance/weight fields as operation components. Private profiles, evidence paths and hashes are not returned.

Operation-only mode preserves the original matcher and labels market comparison unavailable. If a ready query and eligible historical market profiles exist, only independently passing operation (<=0.65) and market (<=0.40) candidates are ranked by 0.4*operation + 0.6*market. Missing optional market fields retain cost1; known feature weights must cover >=0.8, and all three timeframe price/MA gaps must exist. No fallback to weaker examples when strict mode returns zero. A lack of verified historical profiles or incomplete current data is explicitly disclosed as operation-only.

`parameters_validated` remains false in production; sufficiency always discloses this and cannot upgrade solely because many candidates exist. Source/independence limitations are conditional on actual metadata, not hard-coded permanent claims. No probability is inferred from distances, coverage or historical outcomes. Profit/loss grouping occurs only after matching.

Chat facts include actual comparison scope and use the same snapshots as form drafts. New snapshots use closed candles only; no embeddings, LLM ranking, broker order connection or automatic order execution is introduced. Pages 提供真實歷史案例近鄰，但查詢行情屬合成回放；Groq 僅接收彙總，不傳逐筆案例。`GET /api/broker/quote` 僅在本機 FastAPI 可用，回傳 `{source:'ctrader_demo_xauusd',environment:'demo',status,bid,ask,source_time_utc,age_seconds,order_connection:false}`，由 DEMO XAUUSD 唯讀 spot 訂閱取得單次快照並快取十秒；未設定或失敗時價格為 `null`。此路由不進入回放、檢索或送單流程，Pages 沒有該路由。
