# Code and data are distributed separately

Gold Desk program code is MIT licensed. This does not relicense trader records,
broker quotes, historical market data, screenshots or third-party dependencies.

The existing three files in frontend/public/data are the previously authorized
public trade-case / old-index / synthetic-query demonstration. Their inclusion
does not grant general reuse or redistribution of underlying source data.
Exact case times, prices, sizes and historical results in the public case file
are downloadable; never mistake these for synthetic trader records.

The current complete reference dataset and native tick-volume index are a
controlled team-only bundle, not included in the repository or public release.
Obtain the authorized bundle from its owner and import locally. Do not upload
it to public GitHub Releases, frontend/public, or AI chat attachments.

Filled .env files, CLI authentication stores, SQLite submissions, account IDs,
tokens, runtime logs and original broker statements must never be committed.
Each person signs in to their own AI tools and uses their own cTrader DEMO.

Without a private bundle, local replay is explicitly labeled synthetic. Missing
case features or mismatched broker volume stay unavailable; they are not filled
with zero or silently treated as matching. PROJECT_REFERENCE / UNKNOWN clock
labels remain; historical outcomes are descriptions, not forecasts.
