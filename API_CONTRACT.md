# Frontend API contract v1

All amounts/prices/lots are decimal strings. OHLC plotting is numeric. REST base /api. Errors JSON {detail: string}. Modes replay and broker_demo. Synthetic demo is clearly named, private imported data source is labelled.

- GET /api/state → {mode,version,clock,data_source,broker_connected:false,llm_enabled:false,quote:{bid,ask,time},account:{balance,equity},positions:[{id,side,lot,entry,sl,tp,pnl,opened_at}],orders:[{id,side,lot,price,status,time,action,pnl}],market:{change_pct,range_pct,high,low,ma20,ma60},data_quality:[string]}
- GET /api/bars?interval=5m|15m|1h → {bars:[{time:unix seconds,open,high,low,close,volume}],markers:[{time,position:'belowBar'|'aboveBar',color,shape:'arrowUp'|'arrowDown'|'circle',text}],source,interval}
- POST /api/replay/step {bars:1|6|12} → state; POST /api/replay/reset {} → state; POST /api/mode {mode:'replay'|'broker_demo'} → state. Switching mode to unconfigured demo clearly disables submitting; no synthetic broker response.
- POST /api/drafts {side:'BUY'|'SELL',lot:'0.10',sl:null|string,tp:null|string} → {id,revision,side,lot,sl,tp,price,action:'FIRST'|'ADD'|'OPPOSITE',status:'REVIEW',risk:{before_lot,after_lot,average_entry,stop_loss_usd:null|string,reward_risk:null|string,scenarios:[{move,loss}],warnings:[string]},retrieval:{total,wins,losses,flat,unknown,win_rate:null|string,cases:[Case],limitations:[string]},explanation:string}
- POST /api/drafts/{id}/confirm {revision:number,idempotency_key:string} → {status:'FILLED',order_id:string,state}; 409 stale/repeated other-version, 503 unconnected broker. POST /api/drafts/{id}/cancel {} → {status:'CANCELLED'}.
- POST /api/positions/{id}/close {confirmed:true,idempotency_key:string} → {status,order_id,state}. UI confirmation required; close must still work when entry cases absent.
- POST /api/chat {message:string,lot?:string,side?:string} → {message:string,draft:Draft|null,provider:'local_rules'|'configured_llm'}. Never auto-confirm.
- GET /api/cases?side=BUY&action=FIRST&lot=0.1 → retrieval (same fields as draft).
- GET /api/cases/{id} → Case + {bars:[],markers:[]} when true verified OHLC exists, otherwise clear empty-chart reason; no invented chart.
- GET /api/audit → {source_files,total_gold_records,period,groups:[{code,label,count,description}],limitations:[string],refreshed_at,source:'synthetic_demo'|'private_audit'}.

Case = {id,label,side,action,lot,entry,exit,opened_at,closed_at,profit,distance,match_reasons:[string],differences:[string],group,source_kind:'synthetic_demo'|'trader_history',time_alignment:'confirmed'|'unknown',behavior,sequence:[{index,side,lot,entry,exit,profit,role}]}. Historical outcomes are available only before query clock. UI must show source and limitations; never call win_rate a forecast.
