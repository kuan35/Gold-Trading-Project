import {useEffect,useRef,useState} from 'react';
import {turnstileSiteKey} from './groqProxy';

type Turnstile={render:(node:HTMLElement,options:Record<string,unknown>)=>string;remove:(id:string)=>void};
declare global {interface Window {turnstile?:Turnstile}}

export default function TurnstileGate({onToken}:{onToken:(token:string)=>void}){
  const node=useRef<HTMLDivElement>(null),[error,setError]=useState('');
  const callback=useRef(onToken);callback.current=onToken;
  useEffect(()=>{
    let cancelled=false,widget='';let script:HTMLScriptElement|null=null;
    const render=()=>{
      if(cancelled||!node.current||!window.turnstile)return;
      widget=window.turnstile.render(node.current,{sitekey:turnstileSiteKey,action:'gold_desk_chat',size:'flexible',
        callback:(token:string)=>callback.current(token),'expired-callback':()=>callback.current(''),'error-callback':()=>{callback.current('');setError('驗證失敗，請重試。');}});
    };
    if(window.turnstile)render();
    else {
      script=document.querySelector('script[data-gold-turnstile]');
      if(!script){script=document.createElement('script');script.dataset.goldTurnstile='true';script.src='https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';script.async=true;script.defer=true;document.head.appendChild(script);}
      script.addEventListener('load',render);script.addEventListener('error',()=>setError('無法載入瀏覽器驗證，請檢查網路。'),{once:true});
    }
    return()=>{cancelled=true;script?.removeEventListener('load',render);if(widget&&window.turnstile)window.turnstile.remove(widget);};
  },[]);
  return <div className="groq-verification"><div ref={node}/>{error&&<small role="alert">{error}</small>}</div>;
}
