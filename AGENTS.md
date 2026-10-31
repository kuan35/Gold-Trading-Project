# Gold Desk local application

Before installation, read AI_SETUP.md and docs/LOCAL_INSTALL.md. This repository
root is the product root. In the original research workspace only, these files
live under product/. Do not add another product/ level after cloning.

Keep the existing frontend/ React/TypeScript interface and backend/ FastAPI.
Windows setup.ps1/start-local.ps1 and macOS setup.sh/start-local.sh share
scripts/local_app.py. Use the project virtual environment. Build frontend with
npm ci then npm run build; build:pages is a separate static demonstration.

For development, run python -m pytest -q backend/tests and frontend npm test /
npm run build. Keep changes small, use codex/ branches, record commands/results
in HANDOFF.md. Do not report macOS runtime success based only on a Windows test.

For provider changes, preserve per-request provider/model/effort, redaction,
fact-token checks and fixed snapshots. Official Codex/Claude local auth stays in
the official tool; do not read, copy or export its auth files. Setup/CI must not
perform paid inference. Never attach broker credentials or raw datasets to LLMs.

For case changes, keep context_contract_v1 and the native tick gate: BUY/SELL,
mature/nonoverlap/closed5m60+1h20, event/tail/paths/volatility and source-compatible
relative tick activity; stable group dedupe, at most5 and allow0. Do not remove
the source check to make another account appear ready. Outcomes do not rank.

For broker changes, retain DEMO-only reviewed drafts, version/quantity/account
revalidation, idempotency and durable UNKNOWN protection. LIVE remains read-only.
Only the account owner confirms actual orders. Setup/tests must not submit one.

For publication, read DATA_POLICY.md and use scripts/package_local.py. Do not
git add the entire research workspace. Preserve .env*, private/, auth stores,
SQLite journals, original statements and logs locally. Existing public data is
not a license for additional private data. No cloud hosting is needed to demo.
