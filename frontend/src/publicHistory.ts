/** Static, read-only public history archive. No API credential or trading route. */
import {rankHistoricalCases,toHistoricalRetrieval,type HistoricalIndexCase,type HistoricalQuery} from './historicalCases';
import type {Audit,Case,Retrieval,Side} from './types';

type RawCase=Case&{available_at:number};
type RawArchive={cases:RawCase[];group_sequences:Record<string,Case['sequence']>};
type RankIndex={schema:string;clock_status:string;alignment_scope:string;cases:HistoricalIndexCase[]};
type QueryIndex={schema:string;queries:HistoricalQuery[]};

export class PublicHistoryStore{
  private byId:Map<string,RawCase>;
  private profileById:Map<string,HistoricalIndexCase>;
  private queries:Map<number,HistoricalQuery>;
  constructor(private raw:RawArchive,private rankIndex:RankIndex,queryIndex:QueryIndex){
    if(rankIndex.schema!=='market_rank_index_v1'||queryIndex.schema!=='synthetic_query_profiles_v1')
      throw Error('真實案例資料版本不相容');
    this.byId=new Map(raw.cases.map(row=>[row.id,row]));
    this.profileById=new Map(rankIndex.cases.map(row=>[row.id,row]));
    this.queries=new Map(queryIndex.queries.map(row=>[row.cursor,row]));
    if(this.byId.size!==raw.cases.length||this.queries.size!==queryIndex.queries.length||
       rankIndex.cases.some(row=>!this.byId.has(row.id)))throw Error('真實案例索引不完整');
  }
  retrieve(side:Side,cursor:number):Retrieval{
    const query=this.queries.get(cursor);
    if(!query)throw Error('此回放時點沒有已收 K 線查詢盤面');
    return toHistoricalRetrieval(rankHistoricalCases(this.rankIndex.cases,query,side),query,this.raw.cases);
  }
  detail(id:string,clock:number):Case|null{
    const row=this.byId.get(id);
    if(!row||row.available_at>clock)return null;
    return {...row,sequence:this.raw.group_sequences[row.group]??row.sequence,
      market_path_pct:this.profileById.get(id)?.path,
      comparison_basis:'synthetic_query_real_history',
      bars:[],markers:[],distance:null,match_reasons:[],
      differences:['參考行情依來源時間模型定位；券商原始時鐘尚未獨立核實'],
      chart_reason:'公開索引提供進場前已收 60 根 K 線的百分比收盤路徑；逐棒 OHLC 仍在本機側檔。'};
  }
  audit():Audit{
    return {source_files:0,total_gold_records:this.raw.cases.length,
      period:'可見來源交易，2018–2026；原始時鐘未逐帳戶核實',
      refreshed_at:'2026-10-19',source:'trader_history',
      groups:[],limitations:[
        '公開案例為交易員真實逐筆操作，依使用者明確要求公開；帳單時鐘尚未獨立核實',
        '可比較參考盤面 '+this.rankIndex.cases.length+' 筆，並非獨立交易決策數',
        '當前查詢盤面仍為合成回放；兩種來源在畫面與檢索中分別標示',
        '相似排序未完成人工相關性校準；歷史損益不代表未來獲利',
      ]};
  }
}

let pending:Promise<PublicHistoryStore>|null=null;
export function loadPublicHistory():Promise<PublicHistoryStore>{
  if(pending)return pending;
  const load=async <T>(name:string):Promise<T>=>{
    const url=new URL(`data/${name}`,document.baseURI);
    const response=await fetch(url);
    if(!response.ok)throw Error(`真實案例資料載入失敗（HTTP ${response.status}）`);
    return await response.json() as T;
  };
  pending=Promise.all([
    load<RawArchive>('trader-cases.json'),
    load<RankIndex>('trader-market-index.json'),
    load<QueryIndex>('synthetic-query-profiles.json'),
  ]).then(([raw,rank,query])=>new PublicHistoryStore(raw,rank,query))
    .catch(error=>{pending=null;throw error;});
  return pending;
}
