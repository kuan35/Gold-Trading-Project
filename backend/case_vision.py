"""Identifier-free normalized pre-entry candle PNG, using only stdlib."""
import base64,math,struct,zlib


def preview(charts):
    rows=[('查詢',charts.get('query',{}))]+[(c['ref'],c) for c in charts.get('cases',[])[:5]]
    width,height=1000,150*len(rows);pixels=bytearray([246,248,251])*(width*height)
    def point(x,y,color):
        if 0<=x<width and 0<=y<height:pixels[(y*width+x)*3:(y*width+x)*3+3]=bytes(color)
    def rect(x1,y1,x2,y2,c):
        for y in range(max(0,y1),min(height,y2+1)):
            for x in range(max(0,x1),min(width,x2+1)):point(x,y,c)
    all_frames={}
    for interval in ('5m','1h'):
        frames=[]
        for _,row in rows:
            raw=row.get(interval,[])
            limit=60 if interval=='5m' else 20
            if not isinstance(raw,list) or not raw or len(raw)>limit:
                frames.append([]);continue
            try:
                base=float(raw[0]['close']);frame=[{k:(float(b[k])/base-1)*100 for k in ('open','high','low','close')} for b in raw]
                if base<=0 or any(not math.isfinite(v) for b in frame for v in b.values()):raise ValueError('invalid')
                if any(not b['low']<=min(b['open'],b['close'])<=max(b['open'],b['close'])<=b['high'] for b in frame):raise ValueError('invalid')
                frames.append(frame)
            except (ValueError,TypeError,KeyError,ArithmeticError):frames.append([])
        all_frames[interval]=frames
        values=[v for f in frames for b in f for v in (b['low'],b['high'])]
        lo,hi=(min(values),max(values)) if values else (-1,1)
        span=max(.001,hi-lo)
        col=0 if interval=='5m' else 500
        for i,frame in enumerate(frames):
            def yy(v):return int(i*150+132-(v-lo)/span*114)
            rect(col+12,i*150+10,col+488,i*150+138,(226,232,240))
            rect(col+13,i*150+11,col+487,i*150+137,(255,255,255))
            for j,b in enumerate(frame):
                x=int(col+22+(j+.5)*455/max(1,len(frame)));color=(13,137,114) if b['close']>=b['open'] else (194,70,86)
                rect(x,yy(b['high']),x,yy(b['low']),color)
                rect(x-2,min(yy(b['open']),yy(b['close'])),x+2,max(yy(b['open']),yy(b['close'])),color)
    raw=b''.join(b'\x00'+pixels[y*width*3:(y+1)*width*3] for y in range(height))
    def chunk(kind,data):return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')
    complete=sum(len(f)==(60 if k=='5m' else 20) for k,frames in all_frames.items() for f in frames)
    return dict(image_url='data:image/png;base64,'+base64.b64encode(png).decode(),rows=[r[0] for r in rows],complete_panels=complete,
                columns=['五分鐘進場前','一小時進場前'],basis='首棒收盤歸零，同週期共用比例尺；無價位、日期、帳戶、案例ID或歷史後續。')
