import Decimal from 'decimal.js';
export type AccountZero={status:string;reason:string|null;zero_bid_price:string|null;direction:'UP'|'DOWN'|null;basis:string;conditional_on_fill?:boolean;reference_bid_price?:string|null;net_quantity_oz?:string|null;equity_at_fill_usd?:string|null};
export type PositionReturn={price_return_pct?:string|null;estimated_margin_roi_pct?:string|null;margin_roi_pct?:string|null;actual_margin_roi_pct?:string|null;margin_return_source?:string;used_margin?:string|null;return_currency?:string|null;return_basis?:string;return_reason?:string|null};
export const displayReturn=(value?:string|null)=>value!=null&&/^-?\d+(\.\d+)?$/.test(value)?(value.startsWith('-')?'':'+')+new Decimal(value).toFixed(4)+'%':null;
const price=(value:string)=>new Decimal(value).toFixed(2);
export function PositionReturns({value}:{value:PositionReturn}){
 const priceReturn=displayReturn(value.price_return_pct),primary=value.margin_roi_pct===undefined?value.estimated_margin_roi_pct:value.margin_roi_pct,margin=displayReturn(primary);
 const actual=value.margin_return_source==='BROKER_POSITION';
 return <span className="position-returns" role="group" aria-label="持倉報酬率">
  {margin?<strong className={primary?.startsWith('-')?'negative':'positive'}>{actual?'持倉報酬率':'預估保證金報酬率'} {margin}</strong>:<small>持倉報酬率待更新</small>}
  <details><summary>報酬率依據</summary>{actual&&value.used_margin&&<p>券商目前占用保證金 {value.used_margin} {value.return_currency}</p>}{priceReturn&&<small>價格報酬率 {priceReturn}</small>}<p>{value.return_basis??'浮動淨損益除以持倉保證金；缺少券商實際保證金時，以槓桿估算並明示。'}</p>{value.return_reason&&<p>{value.return_reason}</p>}</details>
 </span>;
}
export function AccountZeroEstimate({value,pending=false}:{value?:AccountZero|null;pending?:boolean}){
 if(!value)return null;
 return <section className="account-zero-estimate" aria-label="帳戶淨值歸零情境" aria-busy={pending}>
  {value.status==='AVAILABLE'&&value.zero_bid_price?<><p><strong>{value.conditional_on_fill?'假設本單成交且持續持有：':'若持續持有：'}可賣出價{value.direction==='DOWN'?'跌至':'漲至'} {price(value.zero_bid_price)}，估算帳戶淨值歸零。</strong></p><p className="fine">實際可能先停損或被券商強平，這不是強平價。</p></>:<p className="fine">歸零情境：{value.reason??'尚無法估算'}</p>}
  <details><summary>歸零情境計算依據</summary><p>{value.basis}</p>{value.reference_bid_price&&<p>成交情境參考可賣出價 {value.reference_bid_price} · 淨曝險 {value.net_quantity_oz} 盎司</p>}</details>
 </section>;
}
