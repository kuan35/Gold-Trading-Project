"""Separate, explicitly enabled LIVE child. No automatic order submission."""

from scripts.live_readonly_policy import load_live_trade_config
from scripts.stream_ctrader_demo import emit, run


def main():
    try:
        config = load_live_trade_config()
    except ValueError as error:
        emit('status', {'status': str(error)})
        return 2
    try:
        run(config, trade_live=True)
    except Exception:
        emit('status', {'status': 'LIVE_TRADE_CONNECTION_ERROR'})
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
