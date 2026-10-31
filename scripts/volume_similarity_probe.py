"""Offline volume-only ablation on a preselected pool; no production import."""
import json,math
from pathlib import Path


def relative_volume(rows):
    if not isinstance(rows,list) or len(rows)<21:return None
    values=[b.get('volume') for b in rows[-21:]]
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in values):return None
    baseline=sum(values[:-1])/20
    ratio=values[-1]/baseline if baseline>0 and math.isfinite(baseline) else None
    return ratio if ratio is not None and math.isfinite(ratio) else None


def compare_volume(query,case,query_source,case_source,limit):
    if not 1<=limit<=10:raise ValueError('invalid limit')
    if not query_source or query_source!=case_source:return dict(status='INCOMPARABLE_SOURCE',passed=None)
    a,b=relative_volume(query),relative_volume(case)
    if a is None or b is None:return dict(status='MISSING_VOLUME',passed=None)
    ratio=1 if a==b==0 else None if min(a,b)==0 else max(a,b)/min(a,b)
    return dict(status='AVAILABLE',ratio=ratio,passed=ratio is not None and ratio<=limit)


def audit_existing(root):
    data=json.loads((root/'case_candidate_market_profiles.json').read_text(encoding='utf-8'))
    rows=list(data['profiles'].values())
    complete=sum(relative_volume(p.get('pre_entry_bars',{}).get('5m',[])) is not None for p in rows)
    return dict(status='BLOCKED_MISSING_VOLUME' if not complete else 'READY_FOR_SOURCE_AUDIT',
       profiles=len(rows),volume_complete=complete,coverage=complete/len(rows) if rows else None,
       experiment_limits=[1.5,2,3],production_changed=False,
       reason='需同源原生tick量及固定查詢池；缺量不補零，不能據此宣稱效果優劣。')


if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    report=audit_existing(root/'private')
    (root/'docs/volume_probe_20261030.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
