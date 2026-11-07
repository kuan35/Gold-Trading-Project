"""Local immutable read-only analysis history, separate from expiring order drafts."""
from copy import deepcopy
from hashlib import sha256
import json,os,re,tempfile
from pathlib import Path
from threading import RLock
from .engine import DomainError

MAX_BYTES=32*1024*1024
REPLY_FIELDS={'message','provider','model','requested_effort','llm_status','source','market_status','as_of_utc','quote_time_utc','snapshot_id','query_as_of_utc','analysis_mode','case_comparison','outcome_analysis','sections','followups','evidence','macro_context','gold_relation','knowledge_sources'}
FORBIDDEN={'draft_id','idempotency_key','confirmation_key','confirm_key','access_token','refresh_token','api_key','client_secret','proposal'}
REPLY_FIELDS.add('trade_advice')
def clean(value):
    if isinstance(value,dict):return {k:clean(v) for k,v in value.items() if k not in FORBIDDEN}
    if isinstance(value,list):return [clean(v) for v in value]
    return value
def encoded(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False,default=str).encode('utf8')

class AnalysisHistory:
    def __init__(self,root):self.root=Path(root).resolve();self.lock=RLock()
    def _path(self,kind,ref):
        if not isinstance(ref,str) or re.fullmatch('[0-9a-f]{64}',ref) is None:raise DomainError('分析紀錄編號無效。',422)
        folder=self.root/kind;path=folder/(ref+'.json')
        if folder.is_symlink() or path.is_symlink():raise DomainError('分析紀錄路徑無效。',409)
        return path
    def _write(self,path,payload,kind):
        body=encoded(payload);data=encoded(dict(format=kind,sha256=sha256(body).hexdigest(),payload=payload))
        if len(data)>MAX_BYTES:raise DomainError('分析內容超過本機保存上限。',413)
        path.parent.mkdir(parents=True,exist_ok=True);temporary=None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.analysis-',suffix='.tmp',delete=False) as stream:
                temporary=Path(stream.name);stream.write(data);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,path)
        finally:
            if temporary and temporary.exists():temporary.unlink()
    def _read(self,path,kind):
        try:
            if path.stat().st_size>MAX_BYTES:raise ValueError('size')
            value=json.loads(path.read_text(encoding='utf8'))
            if value['format']!=kind or not isinstance(value['payload'],dict) or value['sha256']!=sha256(encoded(value['payload'])).hexdigest():raise ValueError('integrity')
            return value['payload']
        except (OSError,ValueError,KeyError,TypeError):raise DomainError('原分析紀錄不存在或無法完整讀取；未改用新行情。',404)
    def save(self,reply,bundle=None):
        safe=clean({k:v for k,v in reply.items() if k in REPLY_FIELDS});safe['draft']=None
        with self.lock:
            if bundle is not None:
                sid=bundle['snapshot_id']
                if safe.get('snapshot_id')!=sid:raise DomainError('分析與圖表快照不一致，未保存。',409)
                path=self._path('snapshots',sid)
                if not path.exists():self._write(path,clean(bundle),'gold-analysis-snapshot-v1')
                else:self.snapshot(sid)
            ref=sha256(encoded(safe)).hexdigest();path=self._path('replies',ref)
            if not path.exists():self._write(path,safe,'gold-analysis-reply-v1')
            else:self.reply(ref)
        return dict(deepcopy(safe),analysis_ref=ref)
    def reply(self,ref):
        with self.lock:
            value=self._read(self._path('replies',ref),'gold-analysis-reply-v1')
            if sha256(encoded(value)).hexdigest()!=ref:raise DomainError('分析紀錄完整性未通過。',409)
            return dict(deepcopy(value),analysis_ref=ref,draft=None)
    def snapshot(self,sid):
        with self.lock:
            value=self._read(self._path('snapshots',sid),'gold-analysis-snapshot-v1')
            if value.get('snapshot_id')!=sid or value.get('charts',{}).get('snapshot_id',sid)!=sid or value.get('context',{}).get('snapshot_id',sid)!=sid:
                raise DomainError('原圖表快照不一致。',409)
            return deepcopy(value)
    def delete(self,ref):
        with self.lock:
            path=self._path('replies',ref)
            try:path.unlink(missing_ok=True)
            except OSError:raise DomainError('本機分析副本無法刪除。',409)
