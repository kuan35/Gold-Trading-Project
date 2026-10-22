import type {DraftInputState,InputPatch} from './conversationState';
export default function SharedTicket({value:v,onPatch,disabled=false,id}:{value:DraftInputState;onPatch:(patch:InputPatch)=>void;disabled?:boolean;id:string}){
 return <fieldset className="cw-ticket" disabled={disabled}><legend className="sr-only">共用準備中委託</legend>
  <div className="cw-segments" role="group" aria-label="委託方向"><button type="button" className="cw-sell" aria-pressed={v.side==='SELL'} onClick={()=>onPatch({side:'SELL'})}>做空 SELL</button><button type="button" className="cw-buy" aria-pressed={v.side==='BUY'} onClick={()=>onPatch({side:'BUY'})}>做多 BUY</button></div>
  {!v.side&&<small>尚未選擇方向</small>}
  <div className="cw-segments" role="group" aria-label="委託單型"><button type="button" aria-pressed={v.order_type==='MARKET'} onClick={()=>onPatch({order_type:'MARKET'})}>市價</button><button type="button" aria-pressed={v.order_type==='LIMIT'} onClick={()=>onPatch({order_type:'LIMIT'})}>限價</button></div>
  <label htmlFor={id+'-lot'}>手數 <span>Lot</span></label><input id={id+'-lot'} inputMode="decimal" type="number" min="0.01" step="0.01" value={v.lot} onChange={e=>onPatch({lot:e.target.value})} placeholder="請輸入手數"/>
  {v.order_type==='LIMIT'&&<><label htmlFor={id+'-limit'}>指定限價</label><input id={id+'-limit'} type="number" min="0.01" step="0.01" value={v.limit_price} onChange={e=>onPatch({limit_price:e.target.value})} placeholder="請輸入黃金價格"/></>}
  <div className="cw-two"><label htmlFor={id+'-sl'}>停損 <small>選填</small><input id={id+'-sl'} type="number" min="0.01" step="0.01" value={v.sl} onChange={e=>onPatch({sl:e.target.value})} placeholder="未設定"/></label><label htmlFor={id+'-tp'}>停利 <small>選填</small><input id={id+'-tp'} type="number" min="0.01" step="0.01" value={v.tp} onChange={e=>onPatch({tp:e.target.value})} placeholder="未設定"/></label></div>
 </fieldset>;
}
