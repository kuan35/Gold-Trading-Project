"""Fetch only the owner's DEMO historical M5, without trading or model calls."""
import argparse,json,time
from datetime import datetime,timezone
from pathlib import Path
from scripts.fetch_ctrader_history_volume import fetch
from backend.history_library import HistoryLibrary
ROOT=Path(__file__).resolve().parents[1]
WEEK=7*86400
def history_tasks(start,end):
    end=int(end)//300*300;start=int(start)
    if start>=end or end-start>400*86400:raise ValueError('每次更新日期範圍需在400日內且起點早於終點。')
    first=start//WEEK*WEEK
    return [dict(interval='5m',start=t,end=min(t+WEEK,end)) for t in range(first,end,WEEK)]
def main():
    p=argparse.ArgumentParser();p.add_argument('--from',dest='start',required=True,help='UTC date YYYY-MM-DD');a=p.parse_args()
    try:
        start=datetime.strptime(a.start,'%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp()
        library=HistoryLibrary(ROOT/'private');folder=ROOT/'private/history_native'
        result=fetch(history_tasks(start,time.time()),output_folder=folder)
        if result['status']!='COMPLETE':print('歷史更新未完成；已下載部分保留，可使用同指令續傳。');return 1
        meta=library.build(reference=library.discover(),native=folder)
        print(json.dumps(dict(status=meta['status'],sources=meta['sources'],orders_sent=0),ensure_ascii=True));return 0
    except Exception:
        print('歷史更新失敗；未變更案例索引或送單。請檢查本人DEMO設定及網路，不輸出憑證。');return 1
if __name__=='__main__':raise SystemExit(main())
