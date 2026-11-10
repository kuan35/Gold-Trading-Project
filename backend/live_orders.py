"""LIVE-only reviewed orders with a separate journal and local risk limits."""

from pathlib import Path

from .broker_orders import BrokerOrders
from .engine import DomainError
from .live_risk import LiveLimits, check_live_open
from scripts.live_readonly_policy import load_live_trade_config


LIVE_JOURNAL = Path(__file__).resolve().parents[1] / 'private' / 'broker_live_orders.sqlite3'


def local_limits() -> LiveLimits:
    try:
        values = load_live_trade_config()
        return LiveLimits(values['GOLD_LIVE_MAX_ORDER_STOP_USD'], values['GOLD_LIVE_MAX_GROSS_LOTS'])
    except ValueError as exc:
        raise DomainError(f'LIVE 尚未啟用：{exc}', 503) from exc


class LiveBrokerOrders(BrokerOrders):
    def __init__(self, stream, journal: Path = LIVE_JOURNAL, *, limits_provider=local_limits):
        super().__init__(stream, journal, environment='live')
        self.limits_provider = limits_provider

    def _limits(self):
        value = self.limits_provider()
        if not isinstance(value, LiveLimits):
            raise DomainError('LIVE 本機風險上限尚未就緒', 503)
        return value

    def _check_open_risk(self, snapshot, draft, limits):
        margin = self.stream.expected_margin(snapshot, draft['volume_cents'])
        return check_live_open(snapshot, draft, limits, margin)

    def create(self, snapshot, **kwargs):
        limits = self._limits()
        with self.lock:
            public = super().create(snapshot, **kwargs)
            draft = self.drafts[public['id']]
            try:
                risk = self._check_open_risk(snapshot, draft, limits)
            except Exception:
                self.drafts.pop(public['id'], None)
                raise
            draft['risk']['live'] = risk
            draft['risk']['warnings'] = [
                'cTrader LIVE 真實資金委託；券商可能因跳空、滑價、佣金或強平造成超過停損情境的損失。',
                '確認時會再次檢查帳戶、報價、商品規格、保證金與本機風險上限。',
            ]
            draft['explanation'] = '這是 LIVE 真實資金草稿；確認前請核對完整風險，助手不能代你送單。'
            return self._public_draft(draft)

    def _pre_submit_review(self, snapshot, draft, current_price):
        limits = self._limits()
        if draft.get('intent') == 'OPEN':
            self._check_open_risk(snapshot, draft, limits)

    def create_close(self, snapshot, position_id, *, order_type='MARKET', limit_price=None):
        self._limits()
        if order_type != 'MARKET' or limit_price is not None:
            raise DomainError('LIVE 限價平倉尚未開放；請使用原生市價平倉', 422)
        return super().create_close(snapshot, position_id, order_type='MARKET')

    def create_protection(self, snapshot, position_id, changes):
        self._limits()
        return super().create_protection(snapshot, position_id, changes)

    def create_pending_cancel(self, snapshot, order_id):
        self._limits()
        return super().create_pending_cancel(snapshot, order_id)

    def _confirm_management(self, draft, key, quote, account, symbol):
        self._limits()
        return super()._confirm_management(draft, key, quote, account, symbol)
