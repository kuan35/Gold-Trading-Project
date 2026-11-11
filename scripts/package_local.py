"""Build a fresh, reviewable publication folder from an exact file policy."""
import argparse,hashlib,json,shutil,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FILES={'README.md','AI_SETUP.md','AGENTS.md','CLAUDE.md','API_CONTRACT.md','LICENSE','DATA_POLICY.md','THIRD_PARTY_NOTICES.md','.gitignore','.env.example','.env.local.example','ctrader.env.example','.env.ctrader.live.example','requirements.txt','requirements-ctrader.txt','setup.ps1','setup.sh','start-local.ps1','start-local.sh','start.ps1','start-groq.ps1','start-claude.ps1','frontend/package.json','frontend/package-lock.json','frontend/index.html','frontend/tsconfig.json','frontend/vite.config.ts','research/requirements.txt','.github/workflows/local-ci.yml','.github/workflows/pages.yml','docs/LOCAL_INSTALL.md'}
FILES.add('TEAM_HANDOFF.md')
FILES.add('docs/TEAM_START_20261104.md')
FILES.add('.github/workflows/verify.yml')
FILES.add('frontend/src/demo-data.json')
FILES.add('docs/LOCAL_RELEASE_CHECK.md')
FILES.add('HANDOFF.md')
FILES.add('docs/conversation_history_20261031.md')
FILES.add('docs/gold_macro_assistant_20261101.md')
FILES.update({'docs/PEER_UI_PREVIEW.md','frontend/previewProxy.ts','frontend/playwright.config.ts','frontend/e2e/peer-ui.spec.ts'})
FILES.add('frontend/e2e/interaction-quality.spec.ts')
FILES.add('frontend/e2e/draft-assistance.spec.ts')
FILES.update({'frontend/e2e/trader-workflow.spec.ts','docs/TRADER_WORKFLOW.md'})
FILES.update({'frontend/e2e/history-browser.spec.ts','docs/HISTORY_BROWSER.md'})
FILES.update({
 'frontend/e2e/live-environment.spec.ts',
 'frontend/e2e/nonblocking-chat.spec.ts',
 'frontend/e2e/pending-cancel.spec.ts',
 'frontend/e2e/position-protection.spec.ts',
 'docs/PEPPERSTONE_LIVE.md',
 'docs/account_scenarios_20261110.md',
 'docs/agent_history_and_next_order_20261109.md',
 'docs/clear_agent_plan_20261109.md',
 'docs/coherent_order_review_20261110.md',
 'docs/market_case_agent_evidence_20261110.md',
 'docs/matched_pool_results_20261110.md',
 'docs/order_controls_20261110.md',
 'docs/pending_cancel_and_refresh_20261110.md',
})
PUBLIC_DATA={'trader-cases.json','trader-market-index.json','trader-case-reference-times.json','synthetic-query-profiles.json'}
def public_files(root=ROOT):
 root=Path(root).resolve();out=[]
 excluded={'private','.venv','node_modules','__pycache__','.pytest_cache','.git','qa','dist','dist-pages'}
 paths=[]
 for directory,dirs,files in os.walk(root,followlinks=False):
  dirs[:]=[d for d in dirs if d not in excluded and not (Path(directory)/d).is_symlink()]
  paths.extend(Path(directory)/name for name in files)
 for p in paths:
  rel=p.relative_to(root);parts=rel.parts;name=rel.as_posix()
  if any(v in excluded for v in parts):continue
  include=name in FILES or (parts[0] in ('backend','scripts','research') and p.suffix=='.py') or (len(parts)>=3 and parts[:2] in (('frontend','src'),('frontend','tests')) and p.suffix in ('.ts','.tsx','.css','.svg')) or (parts[:3]==('frontend','public','data') and len(parts)==4 and p.name in PUBLIC_DATA)
  if include and p.is_file():
   if p.is_symlink() or not p.resolve().is_relative_to(root):raise ValueError('公開檔案含不允許的連結')
   out.append(name)
 return sorted(out)
def package(destination,root=ROOT):
 destination=Path(destination).resolve();root=Path(root).resolve()
 if destination.exists():raise ValueError('發布目錄必須是新的空路徑，不覆蓋現有checkout')
 names=public_files(root);destination.mkdir(parents=True);manifest={}
 for name in names:
  source=root/name;target=destination/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
  manifest[name]=dict(bytes=target.stat().st_size,sha256=hashlib.sha256(target.read_bytes()).hexdigest())
 (destination/'PUBLICATION_MANIFEST.json').write_text(json.dumps(dict(format='gold-desk-public-v1',files=manifest),indent=2),encoding='utf8')
 return dict(status='prepared_not_pushed',files=len(names),destination=str(destination))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('destination');a=p.parse_args();print(json.dumps(package(a.destination),ensure_ascii=False))
