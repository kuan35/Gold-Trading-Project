$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
if (Get-Command py -ErrorAction SilentlyContinue) { & py -3 -m scripts.local_app setup @args }
elseif (Get-Command python -ErrorAction SilentlyContinue) { & python -m scripts.local_app setup @args }
else { throw 'Install Python 3.11+, Node.js 24 LTS, then run setup.ps1 again.' }
if ($LASTEXITCODE -ne 0) { throw 'Setup failed; see the diagnostic above.' }
