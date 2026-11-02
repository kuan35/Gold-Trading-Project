from copy import deepcopy
import json
import pytest
from backend.analysis_history import AnalysisHistory
from backend.analysis_snapshots import SnapshotStore
from backend.engine import DomainError

SID='a'*64
def capture():
 reply=dict(snapshot_id=SID,message='原分析',provider='program',model=None,llm_status='disabled',source='test',market_status='CURRENT',as_of_utc='2026-11-02T12:00:00Z',quote_time_utc=None,draft={'id':'must-not-return'},draft_id='secret-draft',idempotency_key='secret-key',sections=[dict(title='分析',text='全部段落',fact_ids=[])],evidence=[],followups=[],case_comparison={'cases':[{'ref':'案例甲'}]})
 bundle=dict(snapshot_id=SID,context=dict(snapshot_id=SID,as_of_utc=reply['as_of_utc']),charts=dict(snapshot_id=SID,query={'5m':[{'time':100,'close':3900}]},cases=[{'ref':'案例甲'}]),outcomes={'案例甲':{'60':{'history':{'bars':[{'close':'3901'}]}}}},operations={'案例甲':{'rows':[]}})
 return reply,bundle

def test_analysis_and_charts_survive_restart_without_reviving_draft_authority(tmp_path):
 r,b=capture();before=deepcopy(b)
 saved=AnalysisHistory(tmp_path).save(r,b)
 assert len(saved['analysis_ref'])==64 and saved['draft'] is None
 assert 'draft_id' not in saved and 'idempotency_key' not in saved
 restarted=AnalysisHistory(tmp_path)
 assert restarted.reply(saved['analysis_ref'])==saved
 assert restarted.snapshot(SID)==before
 state=SnapshotStore(ttl=1,clock=lambda:0);state.put(b,draft_id='old-draft')
 empty=SnapshotStore()
 with pytest.raises(DomainError):empty.for_draft('old-draft')

def test_same_snapshot_keeps_distinct_answers_and_immutable_original_charts(tmp_path):
 history=AnalysisHistory(tmp_path);r,b=capture();first=history.save(r,b)
 r['sections'][0]['text']='另一個問題的回覆';b['charts']['query']['5m'][0]['close']=9999
 second=history.save(r,b)
 assert first['analysis_ref']!=second['analysis_ref']
 assert history.snapshot(SID)['charts']['query']['5m'][0]['close']==3900
 assert history.reply(first['analysis_ref'])['sections'][0]['text']=='全部段落'

def test_missing_corrupt_or_traversal_history_never_reads_new_market_data(tmp_path):
 h=AnalysisHistory(tmp_path)
 for ref in ['../outside','b'*64]:
  with pytest.raises(DomainError):h.reply(ref)
 r,b=capture();v=h.save(r,b)
 path=tmp_path/'replies'/(v['analysis_ref']+'.json');raw=json.loads(path.read_text(encoding='utf8'));raw['payload']['message']='tampered';path.write_text(json.dumps(raw),encoding='utf8')
 with pytest.raises(DomainError):h.reply(v['analysis_ref'])

def test_delete_reply_retains_shared_snapshot_and_other_answers(tmp_path):
 h=AnalysisHistory(tmp_path);r,b=capture();one=h.save(r,b);r['message']='second';two=h.save(r,b)
 h.delete(one['analysis_ref'])
 with pytest.raises(DomainError):h.reply(one['analysis_ref'])
 assert h.reply(two['analysis_ref'])['message']=='second' and h.snapshot(SID)['snapshot_id']==SID
