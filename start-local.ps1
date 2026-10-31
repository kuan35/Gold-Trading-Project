$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
$goldPython=Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $goldPython)) { throw 'Run setup.ps1 first.' }
& $goldPython -m scripts.local_app start @args
if ($LASTEXITCODE -ne 0) { throw 'Start failed; see the diagnostic above.' }
