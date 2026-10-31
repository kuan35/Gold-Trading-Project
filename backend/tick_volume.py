"""Independent, source-bound native tick activity; never a traded-volume estimate."""
from bisect import bisect_right
from decimal import Decimal
from hashlib import sha256
import json,re
from threading import RLock

RULESET='context_tick_activity_v2'
LIMIT=Decimal('2')
BASIS='broker_native_tick_count'


def unavailable(reason):
    return dict(status='UNAVAILABLE',reason=reason,relative_volume_ratio=None,volume_basis=BASIS)


def tick_frame(rows,as_of,source_key):
    if not isinstance(source_key,str) or re.fullmatch('[0-9a-f]{64}',source_key) is None:return unavailable('SOURCE_UNAVAILABLE')
    if type(as_of) is not int:return unavailable('INVALID_TIME')
    try:
        if not isinstance(rows,list) or any(type(b.get('time')) is not int for b in rows):return unavailable('INVALID_TIME')
        chosen=sorted((b for b in rows if b['time']+300<=as_of),key=lambda b:b['time'])[-21:]
        if len(chosen)!=21:return unavailable('INSUFFICIENT_HISTORY')
        if as_of-(chosen[-1]['time']+300)>=300:return unavailable('STALE_VOLUME')
        if any(b['time']%300 for b in chosen) or any(b['time']-a['time']!=300 for a,b in zip(chosen,chosen[1:])):return unavailable('GAPPED_BASELINE')
        volumes=[b.get('volume') for b in chosen]
        if any(type(v) is not int or v<0 for v in volumes):return unavailable('UNKNOWN_VOLUME')
        mean=sum((Decimal(v) for v in volumes[:-1]),Decimal(0))/20
        if not mean:return unavailable('ZERO_BASELINE')
        ratio=Decimal(volumes[-1])/mean
        if not ratio:return unavailable('ZERO_TICK_RATIO')
        return dict(status='AVAILABLE',source_key=source_key,volume_basis=BASIS,relative_volume_ratio=format(ratio,'f'),
                    last_volume=str(volumes[-1]),prior20_mean=format(mean,'f'),last_closed_at=chosen[-1]['time']+300)
    except (KeyError,TypeError,ValueError,ArithmeticError,AttributeError):return unavailable('INVALID_VOLUME_BARS')


def compare_tick(query,candidate):
    if query.get('status')!='AVAILABLE':return dict(passed=False,reason=query.get('reason','QUERY_VOLUME_UNAVAILABLE'))
    if candidate.get('status')!='AVAILABLE':return dict(passed=False,reason=candidate.get('reason','CASE_VOLUME_UNAVAILABLE'))
    if not query.get('source_key') or query['source_key']!=candidate.get('source_key'):return dict(passed=False,reason='SOURCE_MISMATCH')
    if query.get('volume_basis')!=BASIS or candidate.get('volume_basis')!=BASIS:return dict(passed=False,reason='SOURCE_MISMATCH')
    try:
        a,b=(Decimal(item['relative_volume_ratio']) for item in (query,candidate))
        if not all(v.is_finite() and v>0 for v in (a,b)):raise ValueError('invalid ratio')
        multiplier=max(a/b,b/a)
        return dict(passed=multiplier<=LIMIT,reason=None if multiplier<=LIMIT else 'TICK_RATIO_EXCEEDS_LIMIT',
                    multiplier=format(multiplier,'f'),query_relative=format(a,'f'),case_relative=format(b,'f'),limit=str(LIMIT))
    except (KeyError,TypeError,ValueError,ArithmeticError):return dict(passed=False,reason='INVALID_TICK_RATIO')


class NativeTickStore:
    """Recalculate independent native volume references from hashed original chunks."""
    def __init__(self,root):
        from .volume_paths import volume_folder
        self.root=root.resolve();self.folder=volume_folder(self.root)
        self.path=self.folder/'case_volume_references_PRIVATE.json'
        self.profile_path=self.root/'case_candidate_market_profiles.json'
        self.paths=[self.path,self.profile_path];self.signature=None;self.data=None;self.lock=RLock()

    def _load(self):
        try:
            sig=tuple((str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in self.paths)
            if self.data is not None and sig==self.signature:return True
            self.data=None
            meta=json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(meta,dict) or not isinstance(meta.get('cases'),dict) or not isinstance(meta.get('chunk_hashes'),dict) or not meta['chunk_hashes']:return False
            if sha256(self.profile_path.read_bytes()).hexdigest()!=meta['profiles_sha256']:return False
            key=meta['source_key']
            if not isinstance(key,str) or re.fullmatch('[0-9a-f]{64}',key) is None:return False
            paths=[self.path,self.profile_path];index={}
            for name,digest in sorted(meta['chunk_hashes'].items()):
                p=(self.folder/name).resolve()
                if p.parent!=self.folder or p.suffix!='.json':return False
                raw=p.read_bytes()
                if sha256(raw).hexdigest()!=digest:return False
                chunk=json.loads(raw);iv=chunk['interval']
                if iv not in ('5m','1h') or chunk['source_key']!=key or chunk['volume_basis']!=BASIS:return False
                paths.append(p)
                if iv!='5m':continue
                if type(chunk['start']) is not int or type(chunk['end']) is not int or chunk['start']>=chunk['end']:return False
                if chunk.get('status') not in ('AVAILABLE','EMPTY') or not isinstance(chunk.get('bars'),list) or (chunk['status']=='EMPTY')!=(not chunk['bars']):return False
                previous=-1
                for bar in chunk['bars']:
                    t=bar['time'];v=bar['volume']
                    if type(t) is not int or t%300 or not chunk['start']<=t<chunk['end'] or t<=previous or type(v) is not int or v<0:return False
                    op,hi,lo,cl=(Decimal(str(bar[k])) for k in ('open','high','low','close'))
                    if not all(x.is_finite() for x in (op,hi,lo,cl)) or not 0<lo<=min(op,cl)<=max(op,cl)<=hi:return False
                    if t in index and index[t]!=bar:return False
                    index[t]=bar;previous=t
            self.paths=paths;self.signature=tuple((str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in paths)
            self.data=dict(meta=meta,index=index,times=sorted(index));return True
        except (OSError,ValueError,TypeError,KeyError,ArithmeticError,AttributeError):
            self.data=None;return False

    def reference(self,case_id,profile):
        return self.capture()(case_id,profile)

    def capture(self):
        """Validate once per query; keep one immutable source capture for its pool."""
        with self.lock:
            if not self._load():return lambda ident,p:unavailable('VOLUME_INDEX_UNAVAILABLE')
            data=self.data
        return lambda ident,p:self._reference(data,ident,p)

    @staticmethod
    def _reference(data,case_id,profile):
        record=data['meta']['cases'].get(case_id)
        if not isinstance(record,dict) or record.get('as_of')!=profile.get('as_of'):return unavailable('REFERENCE_TIME_MISMATCH')
        if record.get('source_key')!=data['meta']['source_key']:return unavailable('SOURCE_MISMATCH')
        stamp=profile.get('as_of')
        if type(stamp) is not int:return unavailable('INVALID_TIME')
        times=data['times'];end=bisect_right(times,stamp-300)
        return tick_frame([data['index'][t] for t in times[max(0,end-21):end]],stamp,data['meta']['source_key'])
