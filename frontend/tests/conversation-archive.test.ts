import test from 'node:test';import assert from 'node:assert/strict';
import {createElement} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import {archiveTurn} from '../src/conversationArchive';
import {DESK_HISTORY_KEY,makeArchiveEntry,mergeArchive,encodeArchive,decodeArchive,saveConversationArchive,renameConversation,deleteConversation} from '../src/deskConversations';
import ConversationWorkspace from '../src/ConversationWorkspace';
import ArchivedConversationReply from '../src/ArchivedConversationReply';
import type {MarketReply} from '../src/LiveAssistant';

const at='2026-10-31T02:00:00Z';
const reply=():MarketReply=>({message:'',provider:'codex_market_analysis',llm_status:'ok',model:'model-a',source:'ctrader_demo_xauusd',market_status:'CURRENT',as_of_utc:at,quote_time_utc:at,snapshot_id:'expired-snapshot',draft:null,followups:[],
 sections:[{title:'五分鐘',text:'五分鐘整理中',fact_ids:[]},{title:'一小時',text:'一小時偏多',fact_ids:[]},{title:'第三段風險',text:'這一段必須完整保存。'.repeat(250),fact_ids:[]}],
 evidence:[{id:'f5.volume',text:'目前tick量比 {{ratio}}',values:{ratio:'1.3'}}],
 case_comparison:{status:'PASSED',label:'相似案例',reason:'找到符合案例',method:'context_contract_v1',side:'BUY',snapshot_id:'expired-snapshot',query_as_of_utc:1,query_state:{event:'跌出後收回',tail_direction:'上行'},counts:{eligible:10,passed:2,displayed:1},cases:[{ref:'案例甲',event:'跌出後收回',tail_direction:'上行',similarities:['同樣收回區間'],differences:['背景稍弱'],representative:{result:'WIN',profit:'18.5',currency:'USD',currency_stated:true,side:'BUY',action:'FIRST',lot:'.1'},metrics:[]}],rejections:[],distribution:{total:2,wins:1,losses:1,flat:0,unknown:0,basis:'完整歷史結果'}},
 outcome_analysis:{status:'AVAILABLE',input_revision:7,matched_cases:2,displayed_cases:1,draft_risk:{status:'AVAILABLE',reason:'',scope:'draft',stop_loss_usd:'45.5',conditional_on_fill:false},cases:[{ref:'案例甲',horizons:{'5':{status:'AVAILABLE',reason:'',minutes:5,change_pct:'.2',mae_pct:'.1',mfe_pct:'.3'}},scenarios:{'5':{status:'AVAILABLE',mae_loss_usd:'12.5',end_pnl_usd:'20',touch_label:'未碰到停損'}}}]}});

test('archive records every answer section, evidence, case and scenario without reviving snapshot actions',()=>{
 const r=reply(),row=archiveTurn({question:'做多風險？',reply:r,note:'原草稿已修改',noteImportant:true,at});
 assert.equal(row.at,at);assert.ok(row.answer.includes(r.sections[2].text));
 for(const text of ['案例甲','背景稍弱','18.5','12.5','45.5','目前tick量比 1.3','原草稿已修改'])assert.ok(row.answer.includes(text),text);
 assert.doesNotMatch(JSON.stringify(row),/expired-snapshot|input_revision|draft_id|idempotency/);
});

test('long conversations survive encode, reload and selecting the same active thread without silent pruning',()=>{
 let items=[] as ReturnType<typeof makeArchiveEntry>[];
 for(let i=0;i<15;i++)items=mergeArchive(items,makeArchiveEntry('c'+i,Array.from({length:27},(_,j)=>({question:'問題'+j,answer:'完整內容'.repeat(700),at})),i));
 const restored=decodeArchive(encodeArchive(items,'c3'));
 assert.equal(restored.items.length,15);assert.equal(restored.items[0].turns.length,27);assert.equal(restored.activeId,'c3');
 assert.equal(restored.items[0].turns[0].answer,'完整內容'.repeat(700));
});

test('pending question and failed replies are saved, and quota errors never report successful storage',()=>{
 assert.match(archiveTurn({question:'問題',at}).answer,/尚未完成/);
 assert.match(archiveTurn({question:'問題',error:'服務逾時',at}).answer,/服務逾時/);
 const disk=new Map([[DESK_HISTORY_KEY,'previous']]);const storage={setItem:(_k:string,_v:string)=>{throw Error('QuotaExceededError');}};
 const result=saveConversationArchive(storage,[makeArchiveEntry('one',[{question:'q',answer:'a',at}],1)],'one');
 assert.equal(result.ok,false);assert.match(result.error,/未儲存/);assert.equal(disk.get(DESK_HISTORY_KEY),'previous');
 assert.throws(()=>encodeArchive([makeArchiveEntry('large',[{question:'q',answer:'長'.repeat(4_000_001),at}],1)]),/空間/);
});

test('v1 text and names migrate, unsupported versions are preserved, secrets remain redacted',()=>{
 const old=JSON.stringify({version:1,items:[{id:'legacy',title:'已改名',customTitle:true,updatedAt:3,turns:[{question:'q',answer:'a',at,draft:{id:'old'}}]}]});
 const loaded=decodeArchive(old);assert.equal(loaded.items[0].title,'已改名');assert.equal(decodeArchive(encodeArchive(loaded.items)).items[0].turns[0].answer,'a');
 assert.equal(decodeArchive('{"version":99,"items":[]}').writable,false);
 assert.doesNotMatch(encodeArchive([makeArchiveEntry('x',[{question:'gsk_abcdefghijklmnopqrstuvwxyz',answer:'a',at}],1)]),/abcdefghijklmnopqrstuvwxyz|"draft"/);
});

test('workspace reload displays the saved active conversation, not an empty new thread or old executable draft',()=>{
 const entries=[makeArchiveEntry('old',[{question:'舊串問題',answer:'舊串答案',at}],1),makeArchiveEntry('active',[{question:'這是上次的問題',answer:'完整回覆第三段',at}],2)];
 const original=Object.getOwnPropertyDescriptor(globalThis,'localStorage');
 Object.defineProperty(globalThis,'localStorage',{configurable:true,value:{getItem:(k:string)=>k===DESK_HISTORY_KEY?encodeArchive(entries,'active'):null}});
 try{const html=renderToStaticMarkup(createElement(ConversationWorkspace,{market:null,light:false,visible:true,onHistory:()=>{}}));assert.match(html,/這是上次的問題/);assert.match(html,/完整回覆第三段/);assert.doesNotMatch(html,/舊串答案|確認送出/);}
 finally{if(original)Object.defineProperty(globalThis,'localStorage',original);else Reflect.deleteProperty(globalThis,'localStorage');}
});

test('long archived replies are expandable and treated as inert text, without old API buttons',()=>{
 const html=renderToStaticMarkup(createElement(ArchivedConversationReply,{record:{question:'q',answer:'內容'.repeat(500)+'<script>oldTrade()</script>',at}}));
 assert.match(html,/<details><summary>展開完整回覆與數據/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>|<button/);
});

test('save, reload, continue, rename and delete retain the complete record at each step',()=>{
 const disk=new Map<string,string>();const storage={setItem:(k:string,v:string)=>{disk.set(k,v);}};
 const read=()=>decodeArchive(disk.get(DESK_HISTORY_KEY)??null);
 let entry=makeArchiveEntry('one',[archiveTurn({question:'第一個問題',reply:reply(),at})],1);
 assert.equal(saveConversationArchive(storage,[entry],'one').ok,true);assert.equal(read().activeId,'one');
 entry=makeArchiveEntry('one',[...read().items[0].turns,archiveTurn({question:'再聊一下',note:'已更新停損說明',at})],2);
 const renamed=renameConversation(mergeArchive(read().items,entry),'one','我的計畫');
 saveConversationArchive(storage,renamed,'one');assert.equal(read().items[0].title,'我的計畫');assert.equal(read().items[0].turns.length,2);
 assert.ok(read().items[0].turns[0].answer.includes(reply().sections[2].text));
 saveConversationArchive(storage,deleteConversation(read().items,'one'),'new-empty');assert.deepEqual(read().items,[]);assert.equal(read().activeId,'new-empty');
});
