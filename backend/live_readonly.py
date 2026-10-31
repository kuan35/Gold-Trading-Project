"""Independent LIVE cache; never accepted by BrokerOrders."""
import atexit
from .demo_market_stream import DemoMarketStream
from .demo_quote_bridge import PRODUCT


class LiveReadOnlyStream(DemoMarketStream):
    def __init__(self):
        super().__init__(config_path=PRODUCT/'.env.ctrader.live',module='scripts.stream_ctrader_live_readonly')

    def _snapshot_locked(self):
        value=super()._snapshot_locked()
        value.update(source='ctrader_live_xauusd',environment='live',read_only=True,order_connection=False)
        value['quote'].update(source='ctrader_live_xauusd',environment='live',order_connection=False)
        # Never expose actual account ID; the connection owner uses a hashed key.
        return value

    def place_order(self,*args,**kwargs):raise ValueError('LIVE_READ_ONLY')
    def bars(self,interval):
        value=super().bars(interval)
        return dict(value,source='ctrader_live_xauusd',environment='live',read_only=True)


stream=LiveReadOnlyStream()
atexit.register(stream.stop)
