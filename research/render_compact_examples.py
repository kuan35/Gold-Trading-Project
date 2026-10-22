"""Render the saved live DEMO query against the frozen offline retrieval rule."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

PRODUCT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PRODUCT))

from backend.compact_market import format_compact, rank_compact, volatility_band
from backend.live_candidate_profile import profile_from_live_snapshot


def candles(ax, bars, *, structure=False):
    base=float(bars[0]['close'])
    def pct(value):return (float(value)/base-1)*100
    if structure:
        hi=max(pct(b['high']) for b in bars[-21:-1])
        lo=min(pct(b['low']) for b in bars[-21:-1])
        ax.hlines(hi,len(bars)-21.5,len(bars)-.5,color='#7453a6',linestyle='--',linewidth=.8,label='Previous 20 high')
        ax.hlines(lo,len(bars)-21.5,len(bars)-.5,color='#92743c',linestyle='--',linewidth=.8,label='Previous 20 low')
        ax.legend(loc='lower left',fontsize=7,framealpha=.8)
    for i,b in enumerate(bars):
        op,hi,lo,cl=[pct(b[k]) for k in ('open','high','low','close')]
        color='#177e89' if cl>=op else '#d17a22'
        ax.vlines(i,lo,hi,color=color,linewidth=.7)
        ax.add_patch(Rectangle((i-.3,min(op,cl)),.6,max(abs(cl-op),.003),facecolor=color,edgecolor=color,linewidth=.4))
    for x in ([19,39] if len(bars)==60 else [6,12]):ax.axvline(x,color='#a5afb9',linestyle=':',linewidth=.8)
    ax.axhline(0,color='#a5afb9',linewidth=.5)
    ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    ax.set_xlim(-1,len(bars));ax.set_ylabel('Price from first close (%)',fontsize=8)
    ax.set_xticks([0,len(bars)//2,len(bars)-1],[f'-{len(bars)-1}',f'-{len(bars)-1-len(bars)//2}','0'])
    ax.tick_params(labelsize=8)


def main():
    out=PRODUCT/'private/compact_retrieval_backtest_20261020'
    manifest=json.loads((out/'manifest_PRIVATE.json').read_text(encoding='utf-8'))
    inputs={key.replace('\\','/'):value for key,value in manifest['inputs'].items()}
    for relative in ('private/cases.json','private/case_candidate_market_profiles.json'):
        if sha256((PRODUCT/relative).read_bytes()).hexdigest()!=inputs[relative]:
            raise RuntimeError('Backtest input changed: '+relative)
    descriptions={r['case_id']:r for r in (json.loads(line) for line in (out/'descriptions_PRIVATE.jsonl').read_text(encoding='utf-8').splitlines())}
    cases=json.loads((PRODUCT/'private/cases.json').read_text(encoding='utf-8'))['cases']
    profiles=json.loads((PRODUCT/'private/case_candidate_market_profiles.json').read_text(encoding='utf-8'))['profiles']
    snapshot=PRODUCT/'private/qa/live_text_similarity_20261020/live_bars_PRIVATE.json'
    query=profile_from_live_snapshot(json.loads(snapshot.read_text(encoding='utf-8')))
    if query.get('status')!='candidate_only':raise RuntimeError('Saved live snapshot unavailable')
    from backend.compact_market import describe_compact
    description=describe_compact(query,'BUY')
    result=rank_compact(cases,descriptions,description,top_k=2)
    if len(result['rows'])<2:raise RuntimeError('Fewer than two comparable examples')
    chosen=[('Saved DEMO query: 2026-10-20 08:10 UTC',query,description)]
    for i,row in enumerate(result['rows'],1):
        d=descriptions[row['case_id']]
        chosen.append((f"Case {i}: {row['case_id']} | agreement {row['agreement_count']}/4",profiles[row['case_id']],d))
    figure,axes=plt.subplots(3,2,figsize=(15,10),sharey='col',layout='constrained')
    for row,(label,p,d) in enumerate(chosen):
        for column,interval in enumerate(('5m','1h')):
            candles(axes[row,column],p['pre_entry_bars'][interval],structure=column==0)
            code=d['pattern_5m'] if interval=='5m' else d['pattern_1h']
            axes[row,column].set_title(f'{label}\n{interval}: {code} (S = small net move)',loc='left',fontsize=9,fontweight='bold')
    figure.suptitle('Compact retrieval v1: saved live query + two historical reference charts',fontsize=13)
    figure.savefig(out/'example_5m_1h.png',dpi=300);figure.savefig(out/'example_5m_1h.pdf');plt.close(figure)
    metadata=dict(query=format_compact(description,volatility_band(description['atr_pct_5m'],result['volatility_bounds'])),
                  query_as_of=query['as_of'],status=result['status'],candidates=[dict(**row,text=format_compact(descriptions[row['case_id']],row['candidate_volatility'])) for row in result['rows']],
                  source_snapshot_sha256=sha256(snapshot.read_bytes()).hexdigest(),renderer_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    (out/'example_PRIVATE.json').write_text(json.dumps(metadata,ensure_ascii=False,sort_keys=True,indent=2),encoding='utf-8')
    print(json.dumps(metadata,ensure_ascii=False))


if __name__=='__main__':main()
