"""Small nonblocking read-only quote cache. Caller holds the stream lock."""
from copy import deepcopy
from uuid import uuid4


class MarginCache:
    def __init__(self):
        self.context = None
        self.pending = None
        self.cached = None
        self.next_request = 0

    def invalidate(self):
        self.context = self.pending = self.cached = None

    def get(self, context, volume, *, now):
        if context != self.context:
            self.invalidate()
            self.context = context
        if self.cached and self.cached['volume'] == volume and 0 <= now-self.cached['started'] < 5:
            return deepcopy(self.cached['data']), None
        if self.pending and now-self.pending['started'] < 10:
            return None, None
        if now < self.next_request:
            return None, None
        command = dict(kind='expected_margin', request_id='gm-'+uuid4().hex, volume_cents=volume)
        self.pending = dict(request_id=command['request_id'], volume=volume, started=now)
        self.next_request = now+1
        return None, command

    def accept(self, data, *, now):
        pending = self.pending
        if not pending or data.get('request_id') != pending['request_id']:
            return False
        self.pending = None
        if not 0 <= now-pending['started'] < 5:
            return False
        self.cached = dict(volume=pending['volume'], started=pending['started'],
                           data={k:v for k,v in data.items() if k != 'request_id'})
        return True
