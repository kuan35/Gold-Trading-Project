import {percent} from './caseOutcomes';
export type HoldingObservationData={status:string;reason:string;bars_used:number;observed_mae_pct:string|null;observed_mfe_pct:string|null;reference_return_pct:string|null};

export default function HoldingObservation({observation:h}:{observation:HoldingObservationData}){
 const available=h.status==='AVAILABLE'||h.status==='PARTIAL';
 return <details className="holding-observation"><summary>參考行情的持倉過程</summary>
  {available?<>
   {h.status==='PARTIAL'&&<p className="scenario-warning">期間有時間間隔，以下只涵蓋已知完整K棒。</p>}
   <dl className="scenario-metrics"><div><dt>已知最大逆向</dt><dd className="negative">{percent(h.observed_mae_pct)}</dd></div><div><dt>已知最大順向</dt><dd className="positive">{percent(h.observed_mfe_pct)}</dd></div><div><dt>觀察段收尾變動</dt><dd>{percent(h.reference_return_pct)}</dd></div></dl>
   <p className="fine">以參考首根完整棒開盤起算，只看進出場之間已收完的 {h.bars_used} 根K棒，變動依做多／做空方向調整；不是原單實際損益。</p>
  </>:<p>{h.reason||'完整持倉參考資料不足，未推算過程。'}</p>}
 </details>;
}
