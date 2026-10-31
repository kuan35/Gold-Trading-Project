"""Check the actual Windows PowerShell parser without launching the service."""
import os
from pathlib import Path
import shutil
import subprocess
import pytest


@pytest.mark.skipif(os.name!='nt',reason='Windows PowerShell encoding regression')
def test_claude_launcher_parses_in_windows_powershell():
    powershell=shutil.which('powershell.exe')
    if not powershell:pytest.skip('Windows PowerShell unavailable')
    env=dict(os.environ,GOLD_TEST_CLAUDE_SCRIPT=str(Path(__file__).resolve().parents[2]/'start-claude.ps1'))
    code='$t=$null;$e=$null;[System.Management.Automation.Language.Parser]::ParseFile($env:GOLD_TEST_CLAUDE_SCRIPT,[ref]$t,[ref]$e)>$null;if($e.Count){exit 1}'
    result=subprocess.run([powershell,'-NoProfile','-Command',code],env=env,stdin=subprocess.DEVNULL,
      stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode==0,'Launcher must parse in Windows PowerShell, not only PowerShell 7'
