"""One read-only XAUUSD bid/ask snapshot from an authorized cTrader DEMO account."""

from __future__ import annotations

import json
import sys

from scripts.check_ctrader_demo import check_demo, load_local_config


def main() -> int:
    try:
        config = load_local_config()
    except ValueError as error:
        print(json.dumps({'status': str(error), 'orders_sent': 0}))
        return 2
    try:
        result = check_demo(config, timeout_seconds=25, spot=True)
    except Exception:
        print(json.dumps({'status': 'SDK_OR_CONNECTION_ERROR', 'orders_sent': 0}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0 if result['quote_status'] in ('CURRENT', 'STALE', 'TIMESTAMP_UNAVAILABLE') else 1


if __name__ == '__main__':
    sys.exit(main())
