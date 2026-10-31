from scripts.package_local import public_files

def test_public_whitelist_excludes_secrets_runtime_and_new_data(tmp_path):
 for name in ['backend/app.py','frontend/src/App.tsx','frontend/src/demo-data.json','frontend/public/data/trader-cases.json','.env.local','.env.local.example','private/cases.json','backend/__pycache__/bad.py','server.log','frontend/public/data/private-new.json']:
  p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture')
 names=public_files(tmp_path)
 assert 'backend/app.py' in names and '.env.local.example' in names and 'frontend/public/data/trader-cases.json' in names
 assert '.env.local' not in names and 'private/cases.json' not in names and 'frontend/public/data/private-new.json' not in names
 assert not any('__pycache__' in n for n in names)
 assert 'frontend/src/demo-data.json' in names
