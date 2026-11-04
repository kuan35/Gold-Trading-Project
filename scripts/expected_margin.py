"""Decode only the requested account/volume; broker money is in deposit currency."""
from datetime import datetime, timezone
from decimal import Decimal


def decode_margin(response, account_id, volume, currency):
    if int(response.ctidTraderAccountId) != account_id:
        raise ValueError('margin account mismatch')
    precision = int(response.moneyDigits) if response.HasField('moneyDigits') else 2
    if not 0 <= precision <= 10:
        raise ValueError('invalid money precision')
    rows = [m for m in response.margin if int(m.volume) == volume]
    if len(rows) != 1:
        raise ValueError('margin volume mismatch')
    row = rows[0]
    buy, sell = Decimal(row.buyMargin).scaleb(-precision), Decimal(row.sellMargin).scaleb(-precision)
    if buy <= 0 or sell <= 0:
        raise ValueError('nonpositive margin')
    return dict(status='AVAILABLE', currency=currency, buy=format(buy,'f'), sell=format(sell,'f'),
                updated_at_utc=datetime.now(timezone.utc).isoformat())
