"""Bounded, read-only historical chart windows, isolated from the replay engine."""
from contextlib import contextmanager
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
import csv,json,re,sqlite3,threading,time
from pathlib import Path

PERIODS={'5m':300,'15m':900,'1h':3600}
START=int(datetime(2020,1,1,tzinfo=timezone.utc).timestamp())
LABELS={'reference':'參考歷史行情','ctrader_demo':'本人 cTrader DEMO 歷史行情'}
class HistoryError(ValueError):pass
def stamp(value):return datetime.fromtimestamp(value,timezone.utc).isoformat()
def seconds(value):
    if isinstance(value,str):
        dt=datetime.fromisoformat(value.replace('Z','+00:00'))
        if dt.tzinfo is None:raise ValueError('timezone missing')
        return int(dt.timestamp())
    if type(value) is not int:raise ValueError('invalid time')
    return value
def bar(row,clock):
    if not isinstance(row,dict):raise ValueError('invalid bar structure')
    t=seconds(row.get('timestamp',row.get('time')))
    if t<START or t%300 or t+300>clock:return None
    v=[Decimal(str(row[k])) for k in ('open','high','low','close')]
    if any(not x.is_finite() or x<=0 for x in v) or v[1]<max(v) or v[2]>min(v):raise ValueError('invalid OHLC')
    if row.get('observed_minutes') not in (None,'') and int(row['observed_minutes'])!=5:return None
    volume=row.get('volume');volume=None if volume in (None,'') or row.get('volume_status') in ('UNAVAILABLE','MISSING','NOT_PROVIDED','UNKNOWN') else Decimal(str(volume))
    if volume is not None and (not volume.is_finite() or volume<0):volume=None
    return (t,*(str(x) for x in v),str(volume) if volume is not None else None)

class HistoryLibrary:
    def __init__(self,private):
        self.root=Path(private).resolve();self.path=self.root/'history_library.sqlite'
        self._lock=threading.RLock();self._building=False;self._error=None;self._checked=0
        self.personal_source=None
        status=self.root/'personal_history_status.json'
        if status.is_file():
            try:self.personal_source=json.loads(status.read_text(encoding='utf-8')).get('source')
            except (OSError,ValueError):pass

    def source_label(self,source):
        return self.personal_source+' 個人歷史行情' if source=='reference' and self.personal_source else LABELS[source]

    def volume_label(self,source):
        return '券商 tick 量' if source=='ctrader_demo' or (source=='reference' and self.personal_source) else '來源量欄位（非全球成交量）'
    @contextmanager
    def _read(self):
        db=sqlite3.connect(f'{self.path.as_uri()}?mode=ro',uri=True,timeout=3)
        try:yield db
        finally:db.close()
    def discover(self):
        p=self.root/'reference/bars.csv'
        if p.is_file():return p
        manifest=self.root/'case_candidate_market_profiles.json'
        if manifest.is_file():
            with manifest.open(encoding='utf-8-sig') as f:header=f.read(262144)
            part=header.split('"profiles"',1)[0]
            match=re.search(r'"bars"\s*:\s*\{[^{}]*?"path"\s*:\s*("(?:[^"\\]|\\.)*")',part)
            if match:
                p=(self.root/json.loads(match[1])).resolve()
                if p.is_relative_to(self.root) and p.suffix.lower()=='.csv' and p.is_file():return p
        return None
    def _fingerprint(self,reference,native):
        paths=([Path(reference)] if reference else [])+sorted(Path(native).glob('5m-*.json'))
        return json.dumps([(str(p.resolve()),p.stat().st_size,p.stat().st_mtime_ns) for p in paths],separators=(',',':'))
    def refresh(self,force=False):
        with self._lock:
            if self._building or (not force and time.monotonic()-self._checked<60):return
            self._checked=time.monotonic();self._building=True
        def work():
            try:
                reference=self.discover();native=self.root/'history_native'
                fingerprint=self._fingerprint(reference,native)
                previous=None
                if self.path.exists():
                    with self._read() as db:
                        row=db.execute("SELECT value FROM meta WHERE key='fingerprint'").fetchone();previous=row[0] if row else None
                if force or fingerprint!=previous:self.build(reference=reference,native=native)
            except (OSError,ValueError,sqlite3.Error):self._error='歷史資料索引更新失敗，保留前次可用資料。'
            finally:
                with self._lock:self._building=False
        threading.Thread(target=work,name='gold-history-index',daemon=True).start()
    def build(self,*,reference=None,native=None,now=None):
        clock=time.time() if now is None else now;native=Path(native or self.root/'history_native')
        fingerprint=self._fingerprint(reference,native)
        self.root.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(self.path,timeout=15)
        try:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('CREATE TABLE IF NOT EXISTS bars(source TEXT,interval TEXT,time INTEGER,open TEXT,high TEXT,low TEXT,close TEXT,volume TEXT,PRIMARY KEY(source,interval,time));CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);')
            with db:
                db.execute('DELETE FROM bars');db.execute('DELETE FROM meta');skipped=0;identity=None
                def insert(source,items):
                    nonlocal skipped
                    batch=[]
                    for row in items:
                        try:item=bar(row,clock)
                        except (ValueError,KeyError,TypeError,InvalidOperation):skipped+=1;continue
                        if item is None:continue
                        batch.append((source,'5m',*item))
                        if len(batch)>=2000:db.executemany('INSERT OR REPLACE INTO bars VALUES(?,?,?,?,?,?,?,?)',batch);batch=[]
                    if batch:db.executemany('INSERT OR REPLACE INTO bars VALUES(?,?,?,?,?,?,?,?)',batch)
                if reference:
                    with Path(reference).open(encoding='utf-8-sig',newline='') as f:
                        reader=csv.DictReader(f)
                        if not {'timestamp','open','high','low','close'}<=set(reader.fieldnames or []):raise HistoryError('歷史CSV欄位不完整')
                        insert('reference',reader)
                    if not db.execute("SELECT 1 FROM bars WHERE source='reference' LIMIT 1").fetchone():raise HistoryError('參考行情沒有有效完整五分棒，保留前次索引')
                for path in sorted(native.glob('5m-*.json')):
                    data=json.loads(path.read_text(encoding='utf8'))
                    if not isinstance(data,dict):raise HistoryError('原生行情結構無效')
                    if data.get('interval')!='5m' or data.get('status') not in ('AVAILABLE','EMPTY'):continue
                    if not isinstance(data.get('bars'),list):raise HistoryError('原生行情K棒結構無效')
                    key=data.get('source_key')
                    if not isinstance(key,str) or not key:raise HistoryError('原生行情缺來源識別')
                    if identity is not None and key!=identity:raise HistoryError('不可混合不同DEMO來源')
                    identity=key;insert('ctrader_demo',data.get('bars',[]))
                for source in LABELS:
                    for interval,span in [('15m',900),('1h',3600)]:
                        group=[];bucket=None;batch=[]
                        def flush():
                            if len(group)!=span//300 or any(row[0]!=bucket+i*300 for i,row in enumerate(group)):return
                            volume=sum((Decimal(row[5]) for row in group),Decimal(0)) if all(row[5] is not None for row in group) else None
                            batch.append((source,interval,bucket,group[0][1],str(max(Decimal(r[2]) for r in group)),str(min(Decimal(r[3]) for r in group)),group[-1][4],str(volume) if volume is not None else None))
                        for row in db.execute("SELECT time,open,high,low,close,volume FROM bars WHERE source=? AND interval='5m' ORDER BY time",(source,)):
                            b=row[0]//span*span
                            if bucket is not None and bucket!=b:flush();group=[]
                            bucket=b;group.append(row)
                            if len(batch)>=2000:db.executemany('INSERT INTO bars VALUES(?,?,?,?,?,?,?,?)',batch);batch=[]
                        if group:flush()
                        if batch:db.executemany('INSERT INTO bars VALUES(?,?,?,?,?,?,?,?)',batch)
                ranges=[dict(id=s,interval=iv,first=lo,last=hi,count=n) for s,iv,lo,hi,n in db.execute('SELECT source,interval,MIN(time),MAX(time),COUNT(*) FROM bars GROUP BY source,interval')]
                if self._fingerprint(reference,native)!=fingerprint:raise HistoryError('來源檔案正在變更，請重新整理資料索引')
                db.executemany('INSERT INTO meta VALUES(?,?)',[('ranges',json.dumps(ranges)),('fingerprint',fingerprint),('built_at_utc',stamp(clock)),('skipped',str(skipped))])
            self._error=None
        except (OSError,ValueError,sqlite3.Error):raise
        finally:db.close()
        return self.metadata()
    def metadata(self):
        result=dict(status='UNAVAILABLE',indexing=self._building,error=self._error,sources=[],first=None,last=None,earliest_year=2020)
        if not self.path.is_file():return result
        try:
            with self._read() as db:
                values=dict(db.execute('SELECT key,value FROM meta'))
                ranges=json.loads(values['ranges']) if 'ranges' in values else [dict(id=s,interval=iv,first=lo,last=hi,count=n) for s,iv,lo,hi,n in db.execute('SELECT source,interval,MIN(time),MAX(time),COUNT(*) FROM bars GROUP BY source,interval')]
                for r in ranges:
                    source=r['id']
                    if r['interval']=='5m':result['sources'].append(dict(id=source,label=self.source_label(source),first=r['first'],last=r['last'],count=r['count'],quote_side='BID',volume_basis=self.volume_label(source)))
                result.update(built_at_utc=values.get('built_at_utc'),skipped_rows=int(values.get('skipped','0')))
            if result['sources']:result.update(status='AVAILABLE',first=min(s['first'] for s in result['sources']),last=max(s['last'] for s in result['sources']))
        except sqlite3.Error:result['error']='歷史索引尚未就緒。'
        if result['status']!='AVAILABLE' and self._building:result['status']='INDEXING'
        return result
    def window(self,at,*,interval='5m',source='auto',limit=600,direction='around'):
        if type(at) is not int or not START<=at<4102444800:raise HistoryError('日期超出2020至2099範圍')
        if interval not in PERIODS or type(limit) is not int or not 10<=limit<=1200 or direction not in ('around','before','after') or source not in (*LABELS,'auto'):raise HistoryError('歷史查詢參數無效')
        meta=self.metadata();result=dict(status=meta['status'],bars=[],requested_at=at,interval=interval,source=None,has_before=False,has_after=False,gaps=[],shifted=False)
        if meta['status']!='AVAILABLE':return result
        with self._read() as db:
            db.execute('BEGIN')
            stored=db.execute("SELECT value FROM meta WHERE key='ranges'").fetchone()
            ranges=json.loads(stored[0]) if stored else [dict(id=s,interval=iv,first=lo,last=hi,count=n) for s,iv,lo,hi,n in db.execute('SELECT source,interval,MIN(time),MAX(time),COUNT(*) FROM bars GROUP BY source,interval')]
            available=[r for r in ranges if r['interval']==interval]
            span=PERIODS[interval];point=at//span*span
            coverage={r['id']:r for r in ranges if r['interval']=='5m'}
            def in_range(r):return coverage[r['id']]['first']<=at<coverage[r['id']]['last']+300
            row=next((r for r in available if r['id']==source),None) if source!='auto' else next((r for r in sorted(available,key=lambda r:r['id']!='ctrader_demo') if in_range(r)),None)
            if row is None or (direction=='around' and not in_range(row)):return dict(result,status='OUT_OF_RANGE',reason='選定日期不在此來源可用範圍，請另選日期或來源。')
            source=row['id'];args=(source,interval)
            fields='time,open,high,low,close,volume'
            if direction=='before':rows=list(reversed(db.execute(f'SELECT {fields} FROM bars WHERE source=? AND interval=? AND time<? ORDER BY time DESC LIMIT ?',(*args,at,limit)).fetchall()));anchor=rows[-1][0] if rows else None
            elif direction=='after':rows=db.execute(f'SELECT {fields} FROM bars WHERE source=? AND interval=? AND time>? ORDER BY time LIMIT ?',(*args,at,limit)).fetchall();anchor=rows[0][0] if rows else None
            else:
                anchor=db.execute('SELECT MIN(time) FROM bars WHERE source=? AND interval=? AND time>=?',(*args,min(point,row['last']))).fetchone()[0]
                left=list(reversed(db.execute(f'SELECT {fields} FROM bars WHERE source=? AND interval=? AND time<? ORDER BY time DESC LIMIT ?',(*args,anchor,int(limit*.7))).fetchall()))
                right=db.execute(f'SELECT {fields} FROM bars WHERE source=? AND interval=? AND time>=? ORDER BY time LIMIT ?',(*args,anchor,limit-len(left))).fetchall();rows=left+right
            bars=[dict(time=r[0],open=float(r[1]),high=float(r[2]),low=float(r[3]),close=float(r[4]),**({'volume':float(r[5])} if r[5] is not None else {})) for r in rows]
            gaps=[dict(from_time=a['time']+span,to_time=b['time'],seconds=b['time']-a['time']-span) for a,b in zip(bars,bars[1:]) if b['time']-a['time']>span]
            return dict(result,status='AVAILABLE' if bars else 'EMPTY',bars=bars,source=source,source_label=self.source_label(source),quote_side='BID',volume_basis=self.volume_label(source),available_range=dict(first=row['first'],last=row['last']),anchor_time=anchor,shifted=direction=='around' and anchor!=point,gaps=gaps,has_before=bool(rows and row['first']<rows[0][0]),has_after=bool(rows and row['last']>rows[-1][0]))
