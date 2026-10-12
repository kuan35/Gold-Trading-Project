import type {Explanation} from './types';

const statusLabel:Record<string,string>={disabled:'模型未啟用',rate_limited:'模型額度／頻率受限',timeout:'模型逾時',invalid_selection:'模型資料引用無效',authentication_failed:'模型授權失敗',expired_key:'金鑰到期'};

export default function ExplanationCard({card}:{card:Explanation}) {
  return <section className="evidence-card" aria-label="下單前資料說明">
    <header><strong>下單前資料說明</strong><span>{card.origin==='model_selection'?'模型整理重點 · 程式提供資料':'程式整理重點'}</span></header>
    <p className="evidence-time">快照 {card.as_of_utc.replace('T',' ').replace('+00:00',' UTC')}</p>
    {card.status!=='ok'&&<p className="fine" role="status">{statusLabel[card.status]||'未取得有效模型整理'}；仍呈現完整資料檢查。</p>}
    {card.sections.map(section=><section className="evidence-section" key={section.id} aria-label={section.title}>
      <h4>{section.title}</h4>
      {section.facts.map(fact=><div className="evidence-fact" key={fact.id}>
        <p>{fact.text}</p>
        <details><summary>{fact.source} · 查看依據</summary><pre>{JSON.stringify(fact.evidence,null,2)}</pre></details>
      </div>)}
    </section>)}
    <p className="fine">{card.origin==='model_selection'?`重點編排：${card.model}。`:''}模型沒有計算或預測勝率，也不能確認訂單。</p>
  </section>;
}
