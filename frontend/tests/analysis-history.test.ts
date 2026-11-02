import test from 'node:test';import assert from 'node:assert/strict';import {createElement} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import {archiveTurn} from '../src/conversationArchive';import {makeArchiveEntry,encodeArchive,decodeArchive,persistConversationDeletion} from '../src/deskConversations';
import {loadAnalysis,ConversationSessions,normalizeArchivedChart} from '../src/analysisHistory';
import {RestoredConversationReply} from '../src/ArchivedConversationReply';
import type {MarketReply} from '../src/LiveAssistant';
const ref='a'.repeat(64),sid='b'.repeat(64),at='2026-11-02T12:00:00Z';
const reply:MarketReply={analysis_ref:ref,snapshot_id:sid,message:'',provider:'program',model:null,llm_status:'disabled',source:'test',market_status:'CURRENT',as_of_utc:at,quote_time_utc:null,draft:null,followups:[],sections:[{title:'五分鐘',text:'原始盤面',fact_ids:['f5.trend']}],evidence:[],case_comparison:{status:'PASSED',label:'案例',reason:'符合條件',method:'context_contract_v1',side:'BUY',snapshot_id:sid,query_as_of_utc:1,query_state:{event:'收回區間',tail_direction:'上行'},counts:{eligible:3,passed:1,displayed:1},cases:[{ref:'案例甲',event:'收回區間',tail_direction:'上行',similarities:[],differences:[],metrics:[]}],rejections:[]}};

test('archive roundtrip preserves a read-only analysis reference and matching chart view',()=>{
 const turn=archiveTurn({question:'分析盤面',reply,at});assert.equal(turn.analysis_ref,ref);
 const chart={id:sid,analysis_ref:ref,mode:'cases' as const,selection:{caseRef:'案例甲',minutes:30 as const}};
 const entry={...makeArchiveEntry('one',[turn],1),chart};
 const stored=decodeArchive(encodeArchive([entry],'one')).items[0];
 assert.equal(stored.turns[0].analysis_ref,ref);assert.deepEqual(stored.chart,chart);
 assert.doesNotMatch(encodeArchive([entry]),/idempotency|draft_id|confirmation_key/);
 assert.equal(normalizeArchivedChart({...chart,analysis_ref:'c'.repeat(64)},[ref]),undefined);
});
test('switching A to B and back retains full replies and open charts without old proposal actions',()=>{
 const cache=new ConversationSessions<{question:string;reply:MarketReply;proposal?:unknown;proposalRevision?:number}>();
 const chart={id:sid,analysis_ref:ref,mode:'analysis' as const,period:'1h' as const};
 cache.save('A',[{question:'A',reply,proposal:{side:'BUY'},proposalRevision:1}],chart);
 cache.save('B',[{question:'B',reply:{...reply,sections:[{title:'其他',text:'B',fact_ids:[]}]}}],null);
 assert.equal(cache.get('A')?.turns[0].reply.case_comparison?.cases[0].ref,'案例甲');
 assert.deepEqual(cache.get('A')?.chart,chart);assert.equal(cache.get('A')?.turns[0].proposal,undefined);
 cache.delete('A');assert.equal(cache.get('A'),undefined);
});
test('history loader rejects wrong references or executable drafts instead of displaying another analysis',async()=>{
 const fetcher=async()=>new Response(JSON.stringify(reply),{status:200});
 const loaded=await loadAnalysis(ref,{fetcher});assert.deepEqual(loaded.sections,reply.sections);
 await assert.rejects(loadAnalysis('c'.repeat(64),{fetcher}),/一致/);
 await assert.rejects(loadAnalysis('../outside',{fetcher}),/編號/);
 await assert.rejects(loadAnalysis(ref,{fetcher:async()=>new Response(JSON.stringify({...reply,draft:{id:'old'}}))}),/唯讀/);
});
test('restored analyses expose original K-line and case buttons without any order confirmation',()=>{
 const html=renderToStaticMarkup(createElement(RestoredConversationReply,{reply,question:'分析盤面',onChart:()=>{}}));
 assert.match(html,/原始盤面/);assert.match(html,/查看 K 線證據/);assert.match(html,/>看圖</);
 assert.doesNotMatch(html,/確認送出|套用到草稿|確認平倉/);
});
test('failed browser persistence never authorizes deleting a still-referenced server analysis',()=>{
 const entry=makeArchiveEntry('A',[archiveTurn({question:'原分析',reply,at})],1),disk=encodeArchive([entry],'A');
 const failed=persistConversationDeletion({setItem:()=>{throw Error('quota');}},[entry],'A','new');
 assert.equal(failed.ok,false);assert.deepEqual(failed.cleanupRefs,[]);assert.equal(decodeArchive(disk).items[0].turns[0].analysis_ref,ref);
 const success=persistConversationDeletion({setItem:()=>{}},[entry],'A','new');assert.deepEqual(success.cleanupRefs,[ref]);
 const shared=persistConversationDeletion({setItem:()=>{}},[entry,{...entry,id:'B'}],'A','B');assert.deepEqual(shared.cleanupRefs,[]);
});
