# Frontend API contract v1

## 2026-10-31 本機供應商逐請求選擇

GET `/api/assistant/status?provider=codex|claude_code|program|openai_compatible` 查所選
供應商的本機能力，不推論。Codex回傳本人帳戶的`models`（id、label、efforts、
default_effort）、`model_options`、reason；不回傳帳戶身分或token。
本機分析／案例解釋／對話請求可帶`provider`；Codex另用`codex_model`、`codex_effort`，
由後端驗證能力清單，不把Claude的sonnet等別名送給Codex。舊model／effort仍供Claude使用。
所有LLM請求仍需既有request opt-in／去識別摘要／數字驗證；供應商切換不修改伺服器環境。
`program`不呼叫模型；未就緒不偷偷切換付費供應商。公開Pages不具本機CLI能力。

## 2026-10-31 本機預設tick活躍度條件

正式CaseStore的context_contract_v1追加tick gate，comparison.ruleset=`context_tick_activity_v2`。comparison.tick_volume有enabled、limit（十進位字串2）、query_status／query_reason／query_relative及retained_rows；原vol_ratio仍指價格波動。完整四軸通過列先按相對tick量差距≤2倍篩選，再去重及取五例，原排序分數不加權。context_passed_rows為量篩前列數，passed_rows為篩後列數，total及結果分布為最終完整去重池。

每例tick_comparison={passed,reason,multiplier,query_relative,case_relative,limit}的比值皆十進位字串，不含來源指紋。case_comparison新增tick_volume、每例tick_activity與第五個metrics.key=tick_ratio。query／歷史來源或連續21棒不足時不靜默退回舊結果，明示不可比較原因。來源hash只留worker IPC及內部query_snapshot，不出公開snapshot、API或LLM。新快照hash納入ruleset。研究直接ContextIndex無store保留不含量能基準；公開Pages未改。

## 2026-10-30 已知持倉參考走勢摘要（本機）

`charts.cases[].holding_observation` 是隨原分析快照凍結的程式結果，不重排案例，不改原單價格報酬或固定5／30／60分鐘情境。欄位：`status:'AVAILABLE'|'PARTIAL'|'INSUFFICIENT'|'UNAVAILABLE'`、reason、basis=`REFERENCE_COMPLETE_BARS_WITHIN_HOLDING`、scope=`OBSERVED_REFERENCE_BARS_ONLY`、source／clock_status／alignment／side、anchor_time／anchor_price／last_bar_end、bars_used／expected_closed_slots／missing_closed_slots、reference_return_pct、observed_mae_pct／observed_mfe_pct、observed_mae_per_oz／observed_mfe_per_oz。價格／百分比為Decimal字串，未知null；計數／UTC秒為數值。

僅完整持倉來源可用（execution AVAILABLE／FULL_HOLDING／WHOLE_REFERENCE_HOLDING）才計算。固定錨點為 `ceil(reference_open/300)*300` 的完整五分鐘棒開盤價，必須實際存在，不移到較晚棒；只選 `bar.time>=anchor_time` 且 `bar.time+300<=reference_close` 的已知完整棒，原資料每棒也須不晚於查詢截止。非整棒進出場的邊界棒不參與，沒有完整棒回INSUFFICIENT，不補0。這個錨點不是原券商成交價，不計實際單筆MAE／損益或保證金ROI。

AVAILABLE僅表示該可觀察完整棒窗口沒有五分鐘日曆槽缺口，並非原單全程／原券商時間已核實。PARTIAL表示窗口有休市或來源缺口，數字只代表已知棒的觀察極值，不能宣稱未知缺口的全程最大值；觀察段收尾是最後一根已知完整棒收盤。BUY／SELL方向調整由程式Decimal計算，順向／逆向幅度皆非負，收尾可正可負。scope與UNKNOWN／PROJECT_REFERENCE始終保留。

既有`case-review`只把原快照最多五例的持倉觀察加入匿名facts模板；精確數值僅放本機values，外部writer拿到定性basis及占位符，不含原始K棒、實際時間／價位／ID。持倉數字引用的每個空白行分隔段落都須含對應 `{{cN_observation_basis_state}}`，否則整次改程式說明並回invalid_grounding，不重試供應者。圖像依舊只有進場前，不用它聲稱驗證持倉後續；LLM不得自行計算或編造順序。引用檢查不等於全面自然語言真實性驗證。指定case_ref時，圖像配置／完整性預檢失敗仍回三段程式摘要及可選`notice`，前端保留該原因。

## 2026-10-30 完整持倉參考行情（本機）

既有 `charts.cases[].execution` 新增 `mode:'FULL_HOLDING'`，`bars` 為進場所在棒至出場所在棒之間來源可用、完整觀測五分鐘的K棒，`close_bars:[]`。中間可能有休市或資料缺口，不插值、不補零；缺首尾任一參考棒仍回 `UNAVAILABLE`，不以最近棒代替。原進出價報酬、markers 與 `PROJECT_REFERENCE／UNKNOWN` 不變；進出場及每根棒結束都不晚於查詢截止。

可選 `coverage:{scope:'WHOLE_REFERENCE_HOLDING'|'ENDPOINT_WINDOWS',calendar_slots:number,available_bars:number,gap_slots:number}`。`calendar_slots` 是首尾含端點的五分鐘日曆槽數，`available_bars` 是本次返回的去重來源棒數，差值 `gap_slots` 含休市／來源缺漏，首尾模式時也含刻意未展開範圍，不能解讀成開市漏資料率。scope表示請求／展示範圍，不宣稱連續觀測。完整範圍最多17,280日曆槽（60日顯示效能界線，非檢索門檻）；超限保留 `SEPARATE_CLOSE` 首尾模式及ENDPOINT_WINDOWS。

本機離線 `python -m scripts.build_execution_history` 另建 `private/case_execution_bars_v2.json`，不覆蓋v1或原始CSV。runtime初始化時優先v2，核對cases／profiles／bars／alignment四來源SHA及窗口；v2不存在才用v1，存在但失配時不靜默降級。來源變動仍拒絕，舊分析快照保留原資料，不回填新棒；服務重啟後舊快照409需重查。沒有新外部API路由；後續與原單結果不參與排名，也不自動加入LLM圖像／文字payload。

## 2026-10-30 模型／思考程度與預設自動解讀

本機UI依使用者新指示不再顯示啟用checkbox；送出問題／要求分析時傳`llm_enabled:true`（案例分析`enabled:true`）。既有API旗標省略仍為false，舊回放自動摘要與DEMO確認不變。不是每tick呼叫。

`LiveChatInput`、`DraftChatInput`、`CaseReviewInput`新增可選`model:'sonnet'|'opus'|'haiku'`與`effort:'low'|'medium'|'high'|'xhigh'|'max'`。非法字串422，非Claude服務收到這些覆寫亦422。省略時用服務預設；每請求局部傳遞，不寫process env。status另提供`model_options,effort_options,default_effort`。前端未確認provider時不傳Claude欄位。

模型回覆保留`model`（請求的模型別名）及`requested_effort`，是原請求設定，不宣稱管理政策下的effective effort已獨立核實。舊回覆／原快照不因目前選單改變；聊天紀錄以文字保留。CLI timeout預設120、允許1–150秒；聊天fetch上限180秒。新詳細說明見`docs/model_controls_20261030.md`。

## 2026-10-30 官方 Claude Code 本機文字 provider

`GOLD_LLM_PROVIDER=openai_compatible|claude_code`；未設定保留原HTTP服務，非法值拒絕啟用。`GET /api/assistant/status` 保留原本機／no-store規則並新增 `provider,provider_label,reason,supports_vision`。Claude 的 configured 代表官方CLI已安裝且唯讀登入探測成功；enabled還需GOLD_ENABLE_LLM=true，不保證額度／模型回覆。探測不發起模型推論，最多快取10秒，不回帳號、token或原始CLI輸出。舊HTTP模式configured仍只是有key，不保證授權。

Claude reason包含`ready,authentication_required,cli_not_installed,cli_probe_failed`。前端保留request opt-in，未啟用不呼叫模型；`claude_market_analysis`／`claude_case_review` 為Claude成功解讀的新provider，原Groq值保留。共同引用／占位符核對與partial_grounding不變，程式降級仍為HTTP200。新增安全錯誤status：`cli_not_installed,cli_unavailable,busy,unsupported_image`，以及原authentication_failed／rate_limited／timeout／invalid_response等。

第一版Claude只接受文字。`image_url`回unsupported_image且不推論；前端依supports_vision=false停用送圖，仍可本機預覽。訂閱模式走使用者官方CLI登入、不需要GOLD_LLM_API_KEY，不自提OAuth token；空工作目錄／safe-mode／無工具MCP／無session持久化。模型從既有後端接收受限摘要，無券商工具或委託權限。啟動切換、環境與實際驗收範圍見 `docs/claude_local_adapter_20261030.md`；公開Pages Groq Worker不變。

## 2026-10-27 後續5分鐘與統一圖表（本機更新）

中檔thresholds現為.25/.50/.12/2；末段准入與score正規化分母同步，舊凍結研究不覆寫。`outcome_analysis.cases[].horizons/scenarios`及快照outcomes現在都含`5`,`30`,`60`，5分鐘為首根完整五分棒（1根）。離線側檔method升為`case_forward_outcomes_v2`，舊v1不冒充提供5分鐘，需重建。

charts端點仍只含進場前query／cases；前端另讀同一快照outcomes，以同ref、同期間接歷史後續。後續K線不寫回query或檢索特徵。切換只顯示目前request key的資料；回傳快照／案例／期間不符即拒絕。圖表可顯示歷史未來，但查詢盤面未來保持空白。


## 2026-10-27 歷史後續情境與本筆草稿風險（本機）

`POST /api/assistant/live-chat` 可加 `draft:{side?,order_type?,lot,limit_price,sl,tp}` 與 `input_revision:int|null`；欄位沿ConversationDraftInput、extra forbid。`POST /api/broker/drafts` 可加input_revision，建立委託後以同一報價與欄位保留分析。下單確認／版本／防重送權限不變。分析快照fingerprint加草稿六欄與input_revision／合約大小，防止相同行情的不同草稿共用舊風險。

MarketReply新增 `outcome_analysis:{status,draft_risk,input_revision,matched_cases,displayed_cases,basis:'DISPLAYED_CASES_ONLY',cases:[{ref,horizons:{'5':HistoricalSummary,'30':...,'60':...},scenarios:{'5':Scenario,'30':...,'60':...}}]}`。matched_cases仍為完整檢索池去重數，後續僅呈現最多五個展示案例，沒有全池後續分布宣稱。後續本身不參與檢索；中檔末段容忍的後續微調見本檔最上方，公開Pages未同步。

HistoricalSummary含status/reason/minutes/anchor_time/end_time/source/basis/side/change_pct/mae_pct/mfe_pct/clock_status/alignment，無bars。錨點為`ceil(case_as_of/300)*300`首根完整五分棒開盤，不是原成交價；固定1、6或12根連續棒、observed_minutes=5且OHLC合法才可用。change_pct依BUY／SELL方向調整，mae_pct／mfe_pct非負；所有百分比、價格、金額以有限十進位字串傳輸，未知null、不補0。source為HistData BID；PROJECT_REFERENCE／UNKNOWN維持。每個觀察期end_time都須不晚於查詢截止；尚未完整發生回NOT_YET_KNOWN，不回傳該期bars與指標。

`draft_risk`含status（AVAILABLE／INCOMPLETE／INVALID／UNAVAILABLE）、reason、side、lot、order_type、entry_price、quantity_oz、contract_units_per_lot、stop_price、target_price、stop_loss_usd、reward_risk、conditional_on_fill、scope:'THIS_DRAFT_ONLY'、currency:'USD'、assumption。券商合約規格缺失不假設100oz；市價採同快照Ask(BUY)/Bid(SELL)，限價採指定價並明示假設已成交。停損距離名目損失不保證成交損失，未含成本／既有持倉／保證金。

Scenario含status（AVAILABLE／UNAVAILABLE／SIDE_MISMATCH）、reason、end_pnl_usd、mae_loss_usd、mfe_profit_usd、stop_nominal_loss_usd、touch_state/touch_label、first_touch_minutes、gap_at_first_touch、executed_pnl_usd:null、conditional_on_fill、path_basis:'RETURN_PCT_REBASED'、mae_basis:'FULL_PATH_WITHOUT_EXIT'。以完整歷史百分比路徑平移到本筆擬進場價、乘券商盎司單位；最大逆向損失是在未套退出的完整路徑，不是已觸發停損後損益。SL／TP觸價只依OHLC判定STOP_FIRST／TARGET_FIRST／BOTH_SAME_BAR／NEITHER／NO_LEVELS；同棒先後未知、跳空不假定可於SL成交。討論方向與草稿不同不投射；沒有匹配案例仍保留盤面及draft_risk。

`GET /api/assistant/snapshots/{snapshot_id}/outcomes?case_ref=案例甲&minutes=5|30|60`：與其他快照路由相同loopback client／Host／Origin限制、成功no-store。只讀原快照選中ref；未知ref404、minutes其他值422、失效／重啟409，不刷新行情或案例。回 `{snapshot_id,case_ref,query_as_of_utc,history,scenario}`；history額外含anchor_price與已收bars（OHLC轉float僅繪圖）。不得回傳case ID、帳號、檔名或私密路徑。圖表手動展開、5/30/60切換與案例選擇均固定原分析。

私人`case_forward_outcomes.json`由`scripts/build_case_outcomes.py`離線建立；來源沿candidate sidecar的同一CSV，cases／profiles／bars三個SHA綁定，runtime檔案異動重驗。缺檔／失配／不完整保留MISSING／STALE／GAPPED_WINDOW／INCOMPLETE_MINUTES等原因。本輪全10887 profiles建置，非獨立交易數。

LLM新增`history.outcome`與`draft.risk`事實模板、token及定性basis；精確價格／手數／損益保留本機代入。模型不得計算、選例、改草稿／確認委託或把事後觀察當預測。數字或引用不通過驗證時回程式摘要，不重試供應者。多週期程式fallback逐段驗證，模型敘事段數上限不變。

## 2026-10-23 即時量能（本機）

原生技術盤面各週期新增`volume_activity:{status,last,mean20,ratio,baseline_count,relation}`；數量／平均／倍率皆十進位字串或null，relation為ABOVE／BELOW／EQUAL或null。status為AVAILABLE／INSUFFICIENT_HISTORY／GAPPED_BASELINE／UNKNOWN_VOLUME／ZERO_BASELINE。最後21根已收棒需連續；ratio=末根tick量／此前20根均量，形成棒排除。真實0保持0，均量0不除。

即時助手evidence新增`f5.volume`／`f15.volume`／`f1.volume`，values為各前綴的`_volume_count`、`_volume_mean`、`_volume_ratio`、`_volume_window`、`_volume_state`、`_volume_note_state`。缺值在解讀ledger中以「未提供／無法計算」呈現，數值API仍null。模型只用token與程式關係，後端凍結後代入原值。range事實保留價格／ATR，量問題另選volume。前端量能區標明券商tick量與均量定義。未增加送單權限或檢索特徵；公開Pages未部署此更新。

## 2026-10-22 聊天案例操作明細與未知回報補強（本機）

`GET /api/assistant/snapshots/{snapshot_id}/operations?case_ref=案例甲`：本機client／Host／Origin限制、成功no-store。case_ref限原快照選出的別名（1..64字）；未知別名404、快照過期或不存在409，不回退讀新資料。回傳 `{snapshot_id,case_ref,as_of_utc,clock_status:UNKNOWN,source:trader_history,status:AVAILABLE|UNAVAILABLE,representative,rows,provided_rows,displayed_rows,reported_total,truncated,coverage,limitations}`。

`representative`為該案例代表單筆 `{side,action,lot,entry,exit,profit,currency,...}`。`rows`最多100筆，每筆 `{index,side,lot,entry,exit,profit,currency,result,role,ordering_uncertain}`；金額皆有限十進位字串或null。每列幣別只讀本列，不繼承代表單筆的USD；unknown不補0，不提供群和。coverage為VISIBLE_ONLY（僅來源可見，不保證完整帳戶）、PARTIAL（缺漏／截斷）、COUNT_CONFLICT（記載筆數與序列衝突）。原始帳號／來源檔／case ID不在此輸出。

操作資料於live-chat／DEMO草稿原分析建立時，從選出案例的來源可見序列製成白名單並凍結；存在SnapshotStore的獨立operations欄位，不加入context.facts或外部模型資料。讀取明細不再讀行情／案例／檢索，不改案例排序與時間界線。

`POST /api/broker/drafts`及新進場confirm新增耐久日誌檢查：同帳戶有UNKNOWN／未辨識回報時回409，禁止用另一份草稿／重開頁面／重啟程序繞過；confirm在SQLite寫入交易中再次檢查。相同草稿及相同防重送key仍只查原結果。兩個明確不同帳戶不互相阻擋；舊紀錄無法證明帳戶時保守阻擋不明回報。已接受、部分成交與已辨識終態不是UNKNOWN，不能因此把已接受限價稱為成交。畸形回報（含status的null／陣列／物件）保存為UNKNOWN並供核對，不自動重送。

## 2026-10-22 聊天共用委託與固定圖層（本機）

`POST /api/assistant/interpret`：loopback client／Host／Origin限制及no-store；body `{message:string(1..1500),draft?:{side?:BUY|SELL|null,order_type?:MARKET|LIMIT|null,lot?:string,limit_price?:string,sl?:string,tp?:string},analysis_side?:BUY|SELL|null,input_revision?:int>=0}`；draft各字串最多30字，禁止額外欄位。純程式解析，不讀報價／模型／券商，不建立後端草稿。回傳 `{intent:DISCUSS|PREPARE|EDIT|CLARIFY|UNSUPPORTED,analysis_side,patch,proposal,message,missing_fields,input_revision}`。patch僅明確欄位、SLTP null表清空；proposal需使用者另按套用；前端必須比對input_revision，假設／澄清不可改欄位。沒有方向不能因API舊預設BUY而查案例，首頁以include_cases=false分析。

`POST /api/broker/drafts`增加 `analysis_reply`（與analysis_snapshot_id／asof一致的程式解讀、FROZEN）。仍只讀一次市場快照；不因產生解釋再次查市場／案例，不呼叫外部模型，不改確認權限或期限。

`GET /api/assistant/snapshots/{id}/charts`增加 `analysis:{as_of_utc,frames:{5m,15m,1h:{bars,layers,quality}}}`。bars最多90已收棒數值座標；layers為程式 `{id,kind:line|region|marker,label,price?,time?,start_time?,end_time?,high?,low?}`，價格字串、UTC秒；不是模型圖上建議。quality保留原生缺棒／不足／過期資訊。原query／cases雙週期60／20窗口保持。缺快照409，不用新行情代替。

`case_comparison.cases[]`增加僅本機展示的 `representative:{result:WIN|LOSS|FLAT|UNKNOWN,profit:string|null,currency:string|null,currency_stated:boolean,side,action,lot:string|null}`；是代表單筆，不是群和。`case_comparison.distribution:{total,wins,losses,flat,unknown,basis}`使用完整通過去重池；矛盾或缺值為null。新增原值不進模型facts；既有去識別化模型資料契約不變。


## 2026-10-22 即時盤面對話（僅本機）

`GET /api/assistant/status`：沿用 loopback client／Host／Origin 檢查、`Cache-Control:no-store`。回傳 `configured:boolean,enabled:boolean,model:string,provider,provider_label,reason,supports_vision,source:'ctrader_demo_xauusd',read_only:true`；不回金鑰，不發起模型推論。HTTP的configured只表示後端已設定key；Claude則作官方CLI唯讀登入探測，均不保證可用額度。

`POST /api/assistant/live-chat`：同一本機限制、no-store。body `{message:string(1..1500),llm_enabled?:boolean=false,previous_questions?:string[0..4](每項<=600),side?:'BUY'|'SELL'='BUY',include_cases?:boolean=true}`，禁止額外欄位。每次只取得一次券商串流快照；include_cases=true且有效即時報價時，從同份已收棒檢索情境案例。false不執行案例檢索。stale不呼叫外部模型。

回傳 `{message,provider,llm_status,model,source,market_status,as_of_utc,quote_time_utc,sections:[{title,text,fact_ids,source?:'model'|'program'}],evidence:[{id,text,values}],followups:string[],draft:null,snapshot_id,query_as_of_utc,analysis_mode:'live'|'draft_snapshot',case_comparison:null|object}`。provider為`groq_market_analysis`、`claude_market_analysis`或`local_market_rules`；llm_status包括`ok,partial_grounding,not_requested,market_unavailable,read_only,invalid_grounding`及既有模型錯誤狀態（disabled、timeout、expired_key、authentication_failed、rate_limited等）。部分段落被替換時必須標記partial_grounding，不能稱全部是模型產生。程式降級仍是HTTP200，輸入錯誤422、本機存取拒絕403。

`case_comparison`：`{status,label,reason,method,side,snapshot_id,query_as_of_utc,query_state:{event,tail_direction},counts:{eligible:int|null,passed:int|null,displayed:int},cases:[{ref,case_id,metrics:[{key,label,actual:decimal_string|null,tolerance:decimal_string|null,unit,passed:bool|null}],event,tail_direction,similarities:string[],differences:string[]}],rejections:[{key,label,count}]}`。五個status為PASSED／NO_RULE_MATCH／NO_COMPARABLE_CASES／UNCERTAIN_EVENT／INSUFFICIENT_DATA。cases最多五組，case_id只供本機連結，不送Groq；外部facts只含前兩組別名與程式比較事實，不含逐筆成果／識別欄位。actual為距離或倍率，非機率。未通過次數按列、可重複；counts不可混用。

`POST /api/broker/drafts`加回傳`analysis_snapshot_id,analysis_as_of_utc`，原確認版本／idempotency／30秒期限不變。`POST /api/assistant/draft-chat` body `{draft_id:string(1..64),message:string(1..1500),llm_enabled?:boolean=false,previous_questions?:string[0..4]}`，禁止額外欄位；只讀該草稿原分析，不重新讀行情／檢索。回傳同上但analysis_mode=draft_snapshot、market_status=FROZEN、draft=null。FROZEN指歷史快照，不表示原報價一定有效；原資料不足仍回market_unavailable且說明當時缺資料。沒有確認送單權限。

`GET /api/assistant/snapshots/{snapshot_id}/charts`：回`{snapshot_id,query_as_of_utc,source,query:{'5m':OHLC[],'1h':OHLC[]},cases:[{ref,as_of_utc,clock_status:'UNKNOWN',alignment:'PROJECT_REFERENCE','5m':OHLC[],'1h':OHLC[]}]}`。只含決策前60／20根，價格float僅供繪圖；未知量不補零。原始案例ID不在此圖表回應。快照最多32份、TTL20分鐘，過期／被釋放／服務重啟409，不換新盤面。上述新路由均loopback client／Host／Origin＋no-store。

`GET /api/assistant/acceptance/{filename}`：同一本機限制；只提供固定index.html與D01–D10 PNG十日圖集，其他名稱404。不提供任意private檔案、CSV／JSON／雜湊清單。此為離線凍結回看，非本輪十次即時行情。詳細見`docs/case_assistant_integration_20261022.md`。

`evidence.text`是帶占位符的程式事實，`values`是精確十進位字串或明確缺值文字。Groq只接收選定事實模板、token名稱及程式算好的關係／動能判讀，不接收原始帳戶、憑證或逐筆案例；回覆經已提供事實ID、占位符及部分宣稱檢查後，程式才填回原值。evidence並非所有語意都驗證的保證。原生5m／15m／1h完整指標只用已收棒，報價須五秒內；唯讀解讀容許來源時鐘領先本機最多100毫秒，但不得跨入下一個五分鐘已收棒邊界。券商執行檢查不變。舊棒／無行情明示原因，不用回放代替現在。詳細流程見`docs/live_market_assistant_20261022.md`及本輪case_assistant_integration文件。

## 2026-10-22 形成中繪圖串流與 DEMO 平倉

`GET /api/broker/chart-stream?interval=5m|15m|1h`：loopback Host／Origin、no-store、text/event-stream；最多每250ms一個`data:`完整展示快照，未變更送註解keepalive。沿用bars回應並加`closed_only:false,forming_status:CURRENT|WAITING,price_basis:BID,volume_basis:observed_bid_updates,forming:null|{bar,pending_bars,updated_at_ms,partial,price_basis,volume_basis}`。形成中bar為UTC開始秒OHLC及本機接收量，只供繪圖；pending_bars亦是待原生棒覆蓋的觀測值。原`/broker/bars`與檢索query_snapshot仍closed-only，沒有形成中資料。

`POST /api/broker/positions/{position_id}/close-draft`：建立全量平倉草稿，僅DEMO且須有效帳戶／交易權限／5秒內報價。回應`intent:CLOSE,action:CLOSE,position_id,side`（原部位方向）、`lot`（全部剩餘）、`price`（BUY取Bid／SELL取Ask）、revision／expires_at_utc／explanation。使用既有`/broker/drafts/{id}/confirm|cancel|status`；confirm帶revision與idempotency_key，先持久記錄再送ClosePositionReq。status新增`intent,position_id,status_observed_at_utc`；activity提交行新增intent，畫面須分辨平倉與新進場。未知／接受／部分成交的同帳戶同部位平倉禁止跨草稿重送，FILLED等待更新帳戶快照。詳見`docs/live_candles_and_close_20261022.md`。公開Pages未開私人券商API。

## 2026-10-21 本機 DEMO 帳戶與交易紀錄

`GET /api/broker/activity?limit=50&offset=0`：只讀、loopback Host／Origin 限制、no-store；limit 1–200、offset 0–1000000。回應 `source=ctrader_demo_xauusd,environment=demo,connection_status,account_scope,updated_at_utc`；`submissions={items,total,offset,limit,has_more}` 是 SQLite 提交紀錄；`broker_orders`／`broker_deals` 為 `{status,items,has_more,from_utc?,to_utc?,updated_at_utc?}`，各限最近30天500筆。status CURRENT／LOADING／UNAVAILABLE／STALE；本機提交 status 與券商訂單進度同既有契約。未知不重送；列表不回傳 idempotency key、account_key 或憑證。

行情快照 account 新增 `net_unrealized_pnl,xau_net_unrealized_pnl,pnl_status,pnl_updated_at_utc`；positions 新增 `lot,opened_at_utc,gross_pnl,net_pnl`，保留 entry/sl/tp；財務值皆字串或 null。PnL 狀態 CURRENT／LOADING／INCOMPLETE／UNAVAILABLE／STALE。淨值與損益須同時通過連線、帳戶及損益新鮮度檢查才顯示；逐倉回覆須屬同一帳戶快照世代。各類歷史與回放來源分開，詳見 `docs/broker_account_workspace_20261021.md`。公開 Pages 未接此私人 API。

## 2026-10-21 本機情境相似規則更新（優先於下方歷次契約）

本機私人案例 `GET /api/cases`、回放草稿及對話查詢預設 `context_contract_v1`；`GET /api/broker/cases?side=BUY|SELL&method=context_contract_v1` 及 `POST /api/broker/drafts` 的 `retrieval_method` 同樣預設此法。可明選 `dual_path_structure_v1`／`path_indicator_pattern_v1` 作對照。完整規格見 `docs/context_rules_product_20261021.md`。公開Pages仍維持既有靜態混合法，本輪未發布。

新增 `rule_status`: `PASSED|NO_RULE_MATCH|NO_COMPARABLE_CASES|UNCERTAIN_EVENT|INSUFFICIENT_DATA`。`similarity_sufficiency=RULE_PASSED` 只代表通過固定試驗條件，人工校準仍false；其餘無通過回NO_MATCH，資料不足回INSUFFICIENT_DATA。資料不足保留 `query_status=insufficient` 和 `query_reason`，即使券商行情本身已就緒也不能覆寫。空但資料可用時 `candidate_market_unavailable_reason=null`。

`comparison` 新增 `thresholds={d5:0.25,d1h:0.50,dtail:0.12,vol_ratio:2}`、`query_event_stage/label`、`query_tail_direction`、`eligible_rows`、`passed_rows`、`passed_unique`、`rejections`、`first_rejection`、`rejection_labels`。拒絕可重疊計數，`first_rejection`才是每筆只計第一個原因。`total`為全部通過且去重池，歷史損益分布只取此池，每次最多展示五筆。

案例新增 `retrieval_method`、`event_stage/label`、`query_event_stage/label`、`tail_direction`、`query_tail_direction`、`tail_path_distance_pct`、`context_check={passed,score_max,score_sum,thresholds}`；保留 `path_distance_pct`、`hour_path_distance_pct`、`volatility_ratio`。路徑差是百分點，波動是較大／較小倍率，分數非機率。草稿確認、防重送及交易權限不改。API仍用十進位字串傳財務金額；float僅用無單位差距與排名。


## Optional public Groq explanation proxy (2026-10-13)

This Cloudflare Worker is separate from the local `/api` contract. When configured, Pages may POST `/explain` with `{message,facts,token}` after explicit visitor opt-in and Turnstile verification. It returns `{message,provider:"groq_explanation"}`. `facts` contain the synthetic replay snapshot and aggregate counts from the public real-case retrieval; they exclude per-case rows and credentials. The Worker validates the Turnstile token with Siteverify, checks hostname/action, and keeps `GROQ_API_KEY` / `TURNSTILE_SECRET_KEY` in Worker secrets. The response is display-only: it cannot create or confirm drafts, change similarity results, or execute orders. If absent or unavailable, `/chat` remains the local deterministic browser implementation. See `groq-proxy/README.md`.

All amounts/prices/lots are decimal strings. OHLC plotting is numeric. REST base /api. Errors JSON {detail: string}. Modes replay and broker_demo. Synthetic demo is clearly named, private imported data source is labelled.

## Local cTrader DEMO market, retrieval and confirmed orders (2026-10-20)

All `/api/broker/*` routes accept loopback clients and approved local origins only. GET responses use `Cache-Control: no-store`. One DEMO SDK child owns market subscriptions and the confirmed order command channel. Credentials and account ID remain server-side. The browser's global quote bar polls every second; the closed-candle chart polls every 15 seconds. `CURRENT` requires a live connection and recent source timestamp; cached quotes/bars become `STALE` on disconnect. Outside market hours, the last tick may age out.

- `GET /api/broker/market` → `{source:'ctrader_demo_xauusd',environment:'demo',connection_status,token_scope,order_connection:boolean,symbol:{lot_size_cents,min_volume_cents,max_volume_cents,step_volume_cents,digits,trading_schedule:{time_zone,intervals:[{start_second,end_second}]}}|null,quote:{status,bid,ask,source_time_utc,age_seconds},account:{status,balance,equity,currency,positions,pending_orders,all_positions_count,all_pending_orders_count,updated_at_utc}|null}`. `order_connection` requires DEMO, TRADE scope, symbol metadata, current account and tick. The schedule is broker-provided XAUUSD weekly trading sessions; interval seconds are measured from Sunday 00:00 in `time_zone`. Prices, money, and volumes in the account payload are decimal strings. The two position/order lists contain XAUUSD only; counts cover all symbols.
- `GET /api/broker/bars?interval=5m|15m|1h` → `{source,environment:'demo',status,interval,closed_only:true,bars:[{time,open,high,low,close,volume}]}`. `time` is UTC Unix seconds. A forming candle is excluded. OHLC are numeric plotting coordinates, not order prices.
- `GET /api/broker/quote` is a compatibility view of the same cached quote; it does not open a second SDK connection.

`GET /api/broker/cases?side=BUY|SELL` uses the latest cTrader DEMO source timestamp as the query clock, requires the latest closed 5m bar and 5m/15m/1h observed-bar windows, then calls the same `path_indicator_pattern_v1` ranker. A timestamp gap is allowed only when every missing minute is outside the broker-provided XAUUSD weekly trading sessions in the broker's time zone; no candle is synthesized. Missing bars while the market is scheduled open, unknown schedule zones, forming bars and stale bars return an explicit unavailable reason. It returns the normal retrieval object plus `query_source`, `query_as_of_utc`, `query_status`, `query_reason`; no replay or TradingView candle is substituted. `GET /api/broker/cases/{id}` returns the mature historical case detail under the same local guard. Historical reference-clock status stays `UNKNOWN`; rank remains `UNCALIBRATED`.

`POST /api/broker/drafts` accepts `{side,lot,order_type:'MARKET'|'LIMIT',limit_price,sl,tp}` and returns a DEMO `REVIEW` draft with broker-derived lot size and USD nominal risk. It requires a current tick no older than five seconds, current DEMO account, TRADE scope and symbol volume rules. No order is sent at this step. `POST /api/broker/drafts/{id}/confirm` accepts `{revision,idempotency_key}`; it rechecks the account, symbol and quote and rejects expired (30-second) or changed drafts. It durably records one submission before forwarding to the DEMO SDK. Response status is `ACCEPTED`, `FILLED`, `PARTIALLY_FILLED`, `REJECTED` or `UNKNOWN`; accepted is not equivalent to filled, and an unknown result is never auto-retried. `GET /api/broker/drafts/{id}/status` queries the latest in-process broker event or durable record. `POST /api/broker/drafts/{id}/cancel` cancels a `REVIEW` draft only, not a live pending order. Market SL/TP is sent as distance from proposed entry and may shift with actual fill; LIMIT SL/TP is absolute. Live-account endpoints are never used.

The public static Pages build has no broker routes or credentials. It embeds a clearly attributed TradingView OANDA price widget and retains synthetic replay queries. The legacy `/api/drafts` and `/api/state` routes remain replay-only, even if `mode='broker_demo'`; the separate `/api/broker/drafts` flow is the only DEMO order path. External reference charts never enter either similarity rank.

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


### Local live dual-path retrieval (2026-10-21)

`GET /api/broker/cases?side=BUY&method=dual_path_structure_v1` defaults to the new method. `path_indicator_pattern_v1` remains an explicit alternative. `POST /api/broker/drafts` accepts the same optional `retrieval_method`, defaulting to the new method; confirmation/idempotency semantics remain unchanged. No new order endpoint is added.

The new method requires 60 closed 5m candles (plus one for ATR metadata) and 20 closed 1h candles. It uses two normalized close-path RMSE axes, same previous-20-bar high/low state first, then minimax percentile rank, rank sum and ID. One result per group and reference window; top five. Mature same-side historical profiles must end before the query context starts. No lot, P/L or indicator distance participates in ranking.

Results retain the standard case response, add `retrieval_method`, `hour_path_rank`, `hour_path_distance_pct`, structure keys/labels/match, `volatility_ratio` (metadata only), and query/case descriptions. `path_distance_pct` and `hour_path_distance_pct` are percentage-point RMSE, not match probabilities. `comparison.method` preserves the requested method even for insufficient data. Missing private history does not fall back to synthetic ranking. `UNCALIBRATED` means nearest ranked references, not a calibrated similarity threshold. Replay/chat/Pages retain their prior method.

本機live-chat對已收到、同一5分鐘區間且來源僅領先100..250ms的快照，最多等255ms再用真實本機時間執行原100ms／5秒檢查；不重讀報價、不向前設定時間，跨棒／更大偏差直接拒絕。券商草稿／確認不使用此等待。來源領先造成資料不足時回覆明示時鐘原因。
# 2026-10-30：本機案例解讀與 LIVE 唯讀

- `GET /api/live-readonly`：loopback Host/Origin/client守衛，no-store，獨立LIVE程序與設定，回 `{source:ctrader_live_xauusd,environment:live,read_only:true,order_connection:false,quote,account,bars}`。bars為原生5m/15m/1h已收棒；帳戶與損益保留新鮮度。無POST送單／平倉／撤單路由。SDK輸出只允許讀取訊息，TRADE token也不啟用交易。`.env.ctrader.live`須明確指定LIVE帳戶，不繼承DEMO設定。
- 原快照`charts.cases[].execution`：`{status,reason,bars,close_bars,markers,result,mode?,clock_status?,alignment?}`。以既有ledger映射進出秒，floor參考棒標記；主窗口最長288根，長持倉平倉附近另圖。缺棒不補、不移標記；缺圖仍可提供原單價格結果。原快照建立時凍結，後續讀取不重新配單。入場所在未收棒僅在歷史事後圖顯示，不進入查詢特徵。
- `operations.representative.price_result`及`operations.rows[].price_result`：`status,entry_price,exit_price,move_per_oz,price_return_pct,margin_roi_pct:null,basis:DIRECTION_ADJUSTED_PRICE_BEFORE_FEES,reason`。BUY=(exit-entry)、SELL=(entry-exit)，報酬率=方向價差/entry*100。Decimal字串；零／非法價未知。與原報表損益及固定5/30/60分鐘期末變動分別命名。
- `GET /api/assistant/snapshots/{id}/case-preview`：可選query `case_ref`（1–64字元），本機no-store，回`{snapshot_id,case_ref,image_url:data:image/png;base64,...,rows,columns,complete_panels,basis}`。指定時只有查詢與該案例兩列；省略保留最多6列（查詢＋5例）×2欄。只畫進場前OHLC、首收盤歸零，同週期共用比例尺，不含帳戶、ID、日期、價軸、進出價／後續或PNG metadata。無此ref為404，圖表快照不一致為409，不改用其他案例。
- `POST /api/assistant/snapshots/{id}/case-review`：body嚴格`{enabled:false,vision:false,case_ref:null,model?,effort?}`；未知欄位422。回`{snapshot_id,case_ref,provider,llm_status,sections,message,model?,requested_effort?}`。case_ref選填且1–64字元；缺快照409、無此ref404，均不呼叫模型。指定時只提供該原案例的匿名事實，保留原編號（例如案例乙仍history.case2／c2），固定「相同點／重要差異／持倉過程」三段；格式／引用不合格整體回程式三段，不重試。省略ref保持原最多五例介面。無匹配不造例。enabled=false只在本機解說；true仍須全域LLM設定可用。vision=true還需`GOLD_LLM_VISION_MODEL`與完整60/20窗口，否則配置／資料不足而不呼叫；指定ref只送該例＋查詢圖。匿名摘要包含比較與方向調整結果，以token由本機填數值，不轉發自由聊天歷史，不回流檢索。前端用snapshot_id與case_ref共同核對回應；切換案例清空舊文字／圖像，只有按分析才推論。圖像不增加交易權限。
- 公開Pages不提供這些本機能力。新增私人`case_execution_bars.json`不在公開白名單內。

# 2026-10-31 additive contract

圖表、部位管理與對話上下文的新增契約見 [workspace_expansion_20261031.md](docs/workspace_expansion_20261031.md)。原確認／防重送流程及LIVE唯讀不變。新增PROTECT/CANCEL意圖與APPLIED保護結果；不能當成成交。
