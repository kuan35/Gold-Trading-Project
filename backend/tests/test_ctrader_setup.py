import pytest
from scripts.setup_ctrader_local import checked_callback,choose_demo,write_config

def test_callback_requires_exact_path_and_state():
 assert checked_callback('/callback?code=abc&state=nonce','nonce')=='abc'
 for path in ['/callback?code=abc&state=wrong','/other?code=abc&state=nonce','/callback?code=a&code=b&state=nonce']:
  with pytest.raises(ValueError):checked_callback(path,'nonce')

def test_only_demo_account_can_be_selected_and_secrets_not_returned(tmp_path):
 accounts=[{'id':'1','is_live':True},{'id':'2','is_live':False}]
 assert choose_demo(accounts,0)=='2'
 with pytest.raises(ValueError):choose_demo([accounts[0]],0)
 p=tmp_path/'.env.ctrader';write_config(p,{'CTRADER_CLIENT_ID':'app','CTRADER_CLIENT_SECRET':'private','CTRADER_ACCESS_TOKEN':'token','CTRADER_ACCOUNT_ID':'2','CTRADER_ENVIRONMENT':'demo'})
 assert 'CTRADER_CLIENT_SECRET=private' in p.read_text()
 assert not (p.stat().st_mode & 0o077) if __import__('os').name!='nt' else True
