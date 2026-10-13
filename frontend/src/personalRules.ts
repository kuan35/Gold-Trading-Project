import Decimal from 'decimal.js';
import type {Draft,MarketReading,State} from './types';
export type RuleKind='order_lot'|'after_lot'|'same_side_count'|'missing_sl'|'stop_loss_usd'|'market_bias';
export type PersonalRule={id:string;kind:RuleKind;value:string|null;op:'gt'|'gte'|'is';enabled:boolean;side:'ANY'|'BUY'|'SELL'};
export type RuleResult={id:string;text:string;status:'triggered'|'clear'|'unknown';actual:string|null;reason:string};
export type RuleCheck={source:'program';reminder_only:true;results:RuleResult[]};
export type RuleProposal={action:'save'|'delete';rule:PersonalRule;before?:string};
export type RuleReply={message:string;proposal?:RuleProposal};
export const RULE_KEY='gold-personal-rules-v1';
export const KINDS:Record<RuleKind,string>={order_lot:'本筆手數',after_lot:'新單後總手數',same_side_count:'既有同向持倉筆數',missing_sl:'未設定停損',stop_loss_usd:'本筆停損情境損失',market_bias:'5分盤面'};
export const BIASES:Record<string,string>={bullish:'短線偏多',bearish:'短線偏空',bullish_pullback:'多方結構中的回檔',bearish_rebound:'空方結構中的反彈',mixed:'多空結構尚不一致'};
export function validateRules(raw:unknown):PersonalRule[]{
 if(!Array.isArray(raw)||raw.length>50)throw Error('規則最多50條，儲存內容須為清單');
 const seen=new Set<string>();
 return raw.map(r=>{
  if(!r||typeof r!=='object'||Object.keys(r).sort().join()!==['id','kind','value','op','enabled','side'].sort().join())throw Error('規則欄位不完整或含不支援欄位');
  if(typeof r.id!=='string'||!/^[A-Za-z0-9_-]{1,80}$/.test(r.id)||seen.has(r.id))throw Error('規則識別碼無效或重複');seen.add(r.id);
  if(!Object.hasOwn(KINDS,r.kind)||typeof r.enabled!=='boolean'||!['ANY','BUY','SELL'].includes(r.side))throw Error('不支援的規則類型或方向');
  if(r.kind==='missing_sl'){if(r.value!==null||r.op!=='is')throw Error('未設定停損條件不能附數字');}
  else if(r.kind==='market_bias'){if(!Object.hasOwn(BIASES,r.value)||r.op!=='is')throw Error('不支援的盤面分類');}
  else{
   if(!['gt','gte'].includes(r.op)||typeof r.value!=='string'||r.value.length>30)throw Error('請輸入有效門檻');
   let value:Decimal;try{value=new Decimal(r.value);}catch{throw Error('請輸入有效門檻');}
   if(!value.isFinite()||value.lte(0)||value.gt('1000000000'))throw Error('門檻須大於零且不超過十億');
   if(r.kind==='same_side_count'&&!value.isInteger())throw Error('筆數須為整數');
  }
  return {...r} as PersonalRule;
 });
}
export function ruleText(r:PersonalRule):string{
 const prefix=r.side==='ANY'?'':r.side==='BUY'?'買進時，':'賣出時，';
 if(r.kind==='missing_sl')return prefix+'未設定停損時提醒';
 if(r.kind==='market_bias')return prefix+`5分盤面為「${BIASES[r.value!]}」時提醒`;
 return prefix+KINDS[r.kind]+(r.op==='gte'?'大於等於':'大於')+r.value+' '+(r.kind==='same_side_count'?'筆':r.kind==='stop_loss_usd'?'USD':'手')+'時提醒';
}
export function changeRules(rules:PersonalRule[],proposal:RuleProposal):PersonalRule[]{
 const old=rules.find(r=>r.id===proposal.rule.id);
 if(proposal.before!==undefined&&JSON.stringify(old)!==proposal.before)throw Error('這條規則已更新，請重新設定');
 const next=proposal.action==='delete'?rules.filter(r=>r.id!==proposal.rule.id):old?rules.map(r=>r.id===proposal.rule.id?proposal.rule:r):[...rules,proposal.rule];
 return validateRules(next);
}
const RULE_INTENT=/規則|提醒|警告|通知|以後|每次|超過|上限|暫停|啟用|停用|刪除|如果|假如|假設|若|不要\s*(?:買|賣|下單|加倉|開倉|平倉)|別買|別賣|不買|不賣|取消|不用|第\s*\d+\s*條/;
export function parseRuleMessage(message:string,rules:PersonalRule[]):RuleReply|null{
 if(!RULE_INTENT.test(message))return null;
 const help='請用「我的規則」選擇條件與門檻，或輸入「單筆超過0.1手提醒我」。設定／假設語句不會建立訂單。';
 if(/列出|查看|有哪些|我的規則/.test(message)&&!/[改刪增]/.test(message))return {message:rules.length?rules.map((r,i)=>`${i+1}. ${r.enabled?'生效':'暫停'}：${ruleText(r)}`).join('\n'):'目前沒有個人規則。'+help};
 if(/而且|並且|或|且|同時|以及|不要|不用|不超過|不大於|不得|假如|假設|如果|^若|(?:15|60)\s*(?:分|m)|小時|1h/.test(message))return {message:help+'目前每條規則設定一個條件，盤面使用5分K；需要多個條件請分開新增。'};
 const index=message.match(/第\s*(\d+)\s*條/);
 if(index){
  const old=rules[Number(index[1])-1];if(!old)return {message:'找不到這條規則，請先列出我的規則。'};
  const r={...old};
  if(/刪除/.test(message))return {message:'請確認是否刪除此規則。',proposal:{action:'delete',rule:r,before:JSON.stringify(old)}};
  if(/暫停|停用/.test(message))r.enabled=false;
  else if(/啟用|恢復/.test(message))r.enabled=true;
  else if(/改/.test(message)&&!['missing_sl','market_bias'].includes(r.kind)){
   const n=message.match(/(?:改成|改為|改到)\s*(\d+(?:\.\d+)?)/);if(!n)return {message:'請說「把第1條改成0.2手」，或點修改選擇條件。'};
   r.value=n[1];
  }else return {message:'請點「我的規則」修改此條件，避免猜錯你的意思。'};
  try{validateRules([r]);}catch(e){return {message:(e as Error).message};}
  return {message:'請確認這次規則變更。',proposal:{action:'save',rule:r,before:JSON.stringify(old)}};
 }
 let kind:RuleKind|null=null,value:string|null=null,op:PersonalRule['op']='gt';
 const side=/買進|買入|做多|BUY/i.test(message)?'BUY':/賣出|賣空|做空|SELL/i.test(message)?'SELL':'ANY';
 if(/沒(?:有)?(?:設(?:定)?)?停損|未(?:設(?:定)?)?停損/.test(message)){kind='missing_sl';op='is';}
 else if(/偏空|偏多|多方.*回檔|空方.*反彈|多空.*不一致/.test(message)){
  kind='market_bias';op='is';value=/空方.*反彈/.test(message)?'bearish_rebound':/多方.*回檔/.test(message)?'bullish_pullback':/偏空/.test(message)?'bearish':/偏多/.test(message)?'bullish':'mixed';
 }else{
  kind=/停損.*(?:損失|風險)|(?:損失|風險).*美元/.test(message)?'stop_loss_usd':/同(?:方向|向).*(?:筆|單)/.test(message)?'same_side_count':/總(?:持倉|部位|手數)|合計|下單後.*手/.test(message)?'after_lot':/單筆|本筆|每筆|買進|賣出|手數/.test(message)?'order_lot':null;
  const m=message.match(/(?:大於等於|至少|達到|大於|超過)\s*(\d+(?:\.\d+)?)/);
  if(m){value=m[1];op=/大於等於|至少|達到/.test(m[0])?'gte':'gt';}
 }
 if(!kind||(kind!=='missing_sl'&&value===null))return {message:help};
 if((['order_lot','after_lot'].includes(kind)&&/美元|USD|筆|%/.test(message))||(kind==='stop_loss_usd'&&/手|%/.test(message)))return {message:'數字單位不符合這個條件。'+help};
 const r:PersonalRule={id:crypto.randomUUID(),kind,value,op,enabled:true,side};
 try{validateRules([r]);}catch(e){return {message:(e as Error).message};}
 return {message:'我理解為以下條件。確認儲存後才會生效。',proposal:{action:'save',rule:r}};
}
export function evaluateRules(raw:PersonalRule[],state:Pick<State,'positions'>,draft:Draft|null=null,reading?:MarketReading):RuleCheck{
 const results:RuleResult[]=validateRules(raw).filter(r=>r.enabled).map(r=>{
  let status:RuleResult['status']='unknown',actual:string|null=null,reason='尚未建立待確認訂單，無法判斷此條件';
  if(draft&&r.side!=='ANY'&&r.side!==draft.side){status='clear';reason='此規則限定另一個買賣方向';}
  else if(r.side!=='ANY'&&!draft)reason='此規則限定下單方向，尚未建立待確認訂單';
  else if(r.kind==='market_bias'){
   if(reading&&Object.hasOwn(BIASES,reading.bias)){actual=reading.label;status=reading.bias===r.value?'triggered':'clear';reason='依回放當時最近已收5分K棒的程式判讀；分類須完全相同';}
   else reason='尚無足夠的已收5分K棒判讀盤面';
  }else if(draft){
   if(r.kind==='missing_sl'){actual=draft.sl||'未設定';status=draft.sl?'clear':'triggered';reason='檢查本筆待確認訂單的停損設定';}
   else{
    actual=r.kind==='order_lot'?draft.lot:r.kind==='same_side_count'?String(state.positions.filter(p=>p.side===draft.side).length):draft.risk[r.kind];
    if(actual!==null&&actual!==undefined){const a=new Decimal(actual),b=new Decimal(r.value!);status=(r.op==='gte'?a.gte(b):a.gt(b))?'triggered':'clear';reason=`實際 ${actual}，條件 ${r.op==='gte'?'≥ ':'> '}${r.value}`;if(r.kind==='stop_loss_usd')reason+=' USD；未含滑價、佣金及跳空影響，不保證損失上限';}
    else{actual=null;reason='未設定停損，無法試算本筆停損情境損失';}
   }
  }
  return {id:r.id,text:ruleText(r),status,actual,reason};
 });return {source:'program',reminder_only:true,results};
}
