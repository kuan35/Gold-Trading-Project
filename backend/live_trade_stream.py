"""Independent LIVE trading transport; enabled only with local limits and token."""

import atexit

from .demo_market_stream import DemoMarketStream
from .demo_quote_bridge import PRODUCT


class LiveTradeStream(DemoMarketStream):
    def __init__(self):
        super().__init__(config_path=PRODUCT / '.env.ctrader.live', module='scripts.stream_ctrader_live_trade')

    def _snapshot_locked(self):
        result = super()._snapshot_locked()
        result.update(source='ctrader_live_xauusd', environment='live', read_only=False)
        result['quote'].update(source='ctrader_live_xauusd', environment='live')
        return result

    def bars(self, interval):
        result = super().bars(interval)
        return dict(result, source='ctrader_live_xauusd', environment='live', read_only=False)


stream = LiveTradeStream()
atexit.register(stream.stop)
