import type {OutcomeHorizon,Scenario} from './caseOutcomes';import {percent} from './caseOutcomes';
export default function OutcomeSummary({history:h,scenario,stale=false,frozen=false}:{history:OutcomeHorizon;scenario?:Scenario;stale?:boolean;frozen?:boolean}){
 if(h.status!=='AVAILABLE')return <p className="scenario-empty">此觀察期間資料不足：{h.reason} 可切換另一個期間查看。</p>;
 return <><dl className="scenario-metrics"><div><dt>方向調整後期末變動</dt><dd>{percent(h.change_pct)}</dd></div><div><dt>途中最大逆向</dt><dd>{percent(h.mae_pct)}</dd></div><div><dt>途中最大順向</dt><dd>{percent(h.mfe_pct)}</dd></div></dl>
  {scenario?.status==='AVAILABLE'?<div className="scenario-projection"><p>{stale?'原草稿':frozen?'原分析草稿':'本筆'}未套退出的逆向情境損失 <strong>{scenario.mae_loss_usd} USD</strong></p><p>{scenario.touch_label}{scenario.gap_at_first_touch?'；發生跳空，不能假設在停損價成交。':''}</p>{stale&&<p className="scenario-warning">欄位已變更，這是原草稿情境；請重新檢查。</p>}</div>:scenario&&<p className="fine">{scenario.reason}</p>}
 </>;
}
