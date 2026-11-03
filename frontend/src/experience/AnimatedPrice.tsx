import {useEffect,useRef,useState} from 'react';

// Live quotes change several times a second, so rolling digits never settle and leave ghosts.
// Show crisp tabular digits instead and flash the changed tail green/red on each tick.
export default function AnimatedPrice({value,className}:{value:string|number|null|undefined;className?:string}){
 const n=Number(value),valid=value!==null&&value!==undefined&&value!==''&&Number.isFinite(n);
 const digits=valid?Math.max(2,String(value).split('.')[1]?.length??0):2,text=valid?n.toFixed(digits):'—';
 const previous=useRef<{text:string;n:number}|null>(null),[flash,setFlash]=useState<{dir:'up'|'down';from:number;key:number}|null>(null);
 useEffect(()=>{
  const before=previous.current;previous.current=valid?{text,n}:null;
  if(!before||!valid||before.text===text)return;
  let i=0;while(i<text.length&&text[i]===before.text[i])i++;
  setFlash({dir:n>before.n?'up':'down',from:i,key:Date.now()});
 },[text]);
 if(!valid)return <span className={`gx-price ${className??''}`}>—</span>;
 const from=flash?.from??text.length;
 return <span className={`gx-price ${className??''}`}>{text.slice(0,from)}{from<text.length&&<span key={flash!.key} className={`gx-tick gx-tick-${flash!.dir}`}>{text.slice(from)}</span>}</span>;
}
