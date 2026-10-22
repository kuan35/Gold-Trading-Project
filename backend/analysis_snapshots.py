"""Bounded in-memory, immutable analysis snapshots. No trading authority."""
from collections import OrderedDict
from copy import deepcopy
import hashlib,json,time
from threading import RLock
from .engine import DomainError


def snapshot_fingerprint(snapshot,side,method='context_contract_v1',*,analysis_time=None,include_cases=None,validity=None):
    q=snapshot.get('quote') or {}
    safe=dict(side=side,method=method,analysis_time=analysis_time,include_cases=include_cases,validity=validity,connection=snapshot.get('connection_status'),
        quote={k:q.get(k) for k in ('source_time_utc','bid','ask','status')},bars=snapshot.get('bars'),
        schedule=(snapshot.get('symbol') or {}).get('trading_schedule'))
    return hashlib.sha256(json.dumps(safe,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()


class SnapshotStore:
    def __init__(self,limit=32,ttl=1200,clock=time.monotonic):
        self.limit,self.ttl,self.clock=limit,ttl,clock
        self.items=OrderedDict();self.drafts={};self.lock=RLock()

    def _clean(self):
        for key,(created,_) in list(self.items.items()):
            if self.clock()-created>self.ttl:del self.items[key]
        self.drafts={key:sid for key,sid in self.drafts.items() if sid in self.items}

    def put(self,bundle,*,draft_id=None):
        with self.lock:
            self._clean();sid=bundle['snapshot_id']
            # Identical source data retain the first immutable capture.
            if sid not in self.items:self.items[sid]=(self.clock(),deepcopy(bundle))
            if draft_id:self.drafts[draft_id]=sid
            while len(self.items)>self.limit:self.items.popitem(last=False)
            self._clean()
            return self.get(sid)

    def get(self,snapshot_id):
        with self.lock:
            self._clean()
            if snapshot_id not in self.items:raise DomainError('分析快照已過期、已釋放或服務已重啟；請重新檢查草稿或提問，不會改用新的行情。',409)
            return deepcopy(self.items[snapshot_id][1])

    def for_draft(self,draft_id):
        with self.lock:
            self._clean()
            if draft_id not in self.drafts:raise DomainError('找不到此草稿的原始分析快照；請重新檢查草稿。',409)
            return self.get(self.drafts[draft_id])
