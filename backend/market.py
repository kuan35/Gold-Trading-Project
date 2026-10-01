"""Closed-bar replay data. The bundled sequence is explicitly synthetic."""
from __future__ import annotations
import json
import random
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = Decimal


def load_bars() -> tuple[list[dict], str]:
    path = ROOT / 'private' / 'bars.json'
    if path.exists():
        data = json.loads(path.read_text(encoding='utf-8'))
        bars = sorted(data['bars'], key=lambda x: x['time'])
        if len(bars) < 360 or len({b['time'] for b in bars}) != len(bars):
            raise ValueError('行情匯入至少需360根且時間不可重複')
        return bars, data.get('source', '本機歷史行情')
    rng = random.Random(35)
    t = int(datetime(2025, 3, 3, tzinfo=timezone.utc).timestamp())
    price = 291620
    bars = []
    for i in range(720):
        movement = rng.randint(-65, 72) + (12 if i % 90 < 45 else -12)
        close = price + movement
        bars.append(dict(time=t+i*300, open=str(D(price)/100),
                         high=str(D(max(price,close)+rng.randint(10,65))/100),
                         low=str(D(min(price,close)-rng.randint(10,65))/100),
                         close=str(D(close)/100), volume=rng.randint(50,240)))
        price = close
    return bars, '合成行情示範・非即時報價'


def aggregate(bars: list[dict], seconds: int, clock: int) -> list[dict]:
    groups: dict[int, list[dict]] = {}
    for b in bars:
        if b['time']+300 > clock:
            continue
        start = b['time']//seconds*seconds
        if start+seconds <= clock:
            groups.setdefault(start, []).append(b)
    result = []
    for start, group in sorted(groups.items()):
        if len(group) != seconds//300 or any(b['time'] != start+i*300 for i,b in enumerate(group)):
            continue
        result.append(dict(time=start,open=float(group[0]['open']),
                           high=float(max(D(b['high']) for b in group)),
                           low=float(min(D(b['low']) for b in group)),
                           close=float(group[-1]['close']),
                           volume=float(sum((D(str(b.get('volume',0))) for b in group),D(0)))))
    return result[-250:]
