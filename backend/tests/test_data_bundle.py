import hashlib,json,zipfile,stat
import pytest
from scripts.data_bundle import import_bundle
from scripts.data_bundle import export_bundle

def bundle(path,files,extra=None):
 manifest={'format':'gold-desk-private-v1','files':{n:{'sha256':hashlib.sha256(v).hexdigest(),'size':len(v)} for n,v in files.items()}}
 with zipfile.ZipFile(path,'w') as z:
  z.writestr('manifest.json',json.dumps(manifest))
  for n,v in files.items():z.writestr(n,v)
  if extra:z.writestr(*extra)

def test_private_import_rejects_traversal_and_hash_failure_without_touching_old_files(tmp_path):
 root=tmp_path/'private';root.mkdir();(root/'cases.json').write_text('old')
 z=tmp_path/'bad.zip';bundle(z,{'../escape':b'bad'})
 with pytest.raises(ValueError):import_bundle(z,root)
 bundle(z,{'cases.json':b'new'},('unexpected.env',b'secret'))
 with pytest.raises(ValueError):import_bundle(z,root)
 assert (root/'cases.json').read_text()=='old' and not (tmp_path/'escape').exists()

def test_import_is_repeatable_and_refuses_overwrite_without_explicit_replace(tmp_path,monkeypatch):
 monkeypatch.setattr('scripts.data_bundle.validate_runtime',lambda p:None)
 z=tmp_path/'ok.zip';bundle(z,{'cases.json':b'{"cases":[]}'})
 root=tmp_path/'private';assert import_bundle(z,root)['status']=='imported'
 assert import_bundle(z,root)['status']=='unchanged'
 bundle(z,{'cases.json':b'{"cases":[1]}'})
 with pytest.raises(ValueError):import_bundle(z,root)
 assert import_bundle(z,root,replace=True)['status']=='imported'

def test_export_minimizes_utf8_alignment_and_keeps_source_unchanged(tmp_path):
 root=tmp_path/'private';root.mkdir();(root/'original.csv').write_text('time,close\n',encoding='utf8')
 def put(n,v):
  p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False),encoding='utf8')
 put('original.json',[dict(case_id='a',source_private='私人帳戶',timezone_status='UNKNOWN')])
 put('cases.json',{'cases':[]});put('case_size_profiles.json',{})
 put('case_candidate_market_profiles.json',dict(inputs={'bars':{'path':'original.csv'},'alignment':{'path':'original.json'}},profiles={}))
 for n in ['case_execution_bars_v2.json','case_forward_outcomes.json']:put(n,dict(inputs={k:{} for k in ['cases','profiles','bars']}))
 put('ctrader_history_volume_20261030/case_volume_references_PRIVATE.json',dict(chunk_hashes={}))
 old=(root/'original.json').read_bytes();target=tmp_path/'bundle.zip';export_bundle(root,target)
 with zipfile.ZipFile(target) as z:assert 'source_private' not in z.read('reference/alignment.json').decode('utf8')
 assert (root/'original.json').read_bytes()==old

def test_receipt_failure_rolls_back_data(tmp_path,monkeypatch):
 monkeypatch.setattr('scripts.data_bundle.validate_runtime',lambda p:None)
 from scripts import data_bundle as module
 root=tmp_path/'private';root.mkdir();(root/'cases.json').write_text('old')
 z=tmp_path/'new.zip';bundle(z,{'cases.json':b'new'})
 def fail(*args):raise OSError('fixture receipt failure')
 monkeypatch.setattr(module,'write',fail)
 with pytest.raises(OSError):import_bundle(z,root,replace=True)
 assert (root/'cases.json').read_text()=='old'

def test_manifest_types_fail_closed(tmp_path):
 z=tmp_path/'bad.zip'
 with zipfile.ZipFile(z,'w') as archive:archive.writestr('manifest.json','[]')
 with pytest.raises(ValueError):import_bundle(z,tmp_path/'private')

def test_incomplete_but_hash_correct_bundle_never_replaces_existing_data(tmp_path):
 root=tmp_path/'private';root.mkdir();(root/'cases.json').write_text('old')
 z=tmp_path/'partial.zip';bundle(z,{'cases.json':b'{}'})
 with pytest.raises(ValueError,match='runtime'):import_bundle(z,root,replace=True)
 assert (root/'cases.json').read_text()=='old'
