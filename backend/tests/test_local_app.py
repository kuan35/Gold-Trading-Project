from pathlib import Path
import pytest
from scripts.local_app import read_settings,ensure_template,venv_python,start_arguments

def test_settings_are_bounded_and_never_overwrite_existing_values(tmp_path):
 template=tmp_path/'template';template.write_text('GOLD_LLM_PROVIDER=program\n',encoding='utf8')
 target=tmp_path/'.env.local';ensure_template(template,target);target.write_text('GOLD_LLM_PROVIDER=codex\nGOLD_ENABLE_LLM=true\n',encoding='utf8')
 ensure_template(template,target);assert read_settings(target)['GOLD_LLM_PROVIDER']=='codex'
 target.write_text('PATH=unsafe',encoding='utf8')
 with pytest.raises(ValueError):read_settings(target)

def test_platform_paths_and_server_arguments_are_local_and_single_worker(tmp_path):
 assert venv_python(tmp_path,'win32')==tmp_path/'.venv/Scripts/python.exe'
 assert venv_python(tmp_path,'darwin')==tmp_path/'.venv/bin/python'
 args=start_arguments(tmp_path,'darwin');assert args[-3:]==['127.0.0.1','--port','8765']
 assert '--reload' not in args and '--workers' not in args
