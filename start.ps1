$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$goldPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $goldPython)) { throw '請先依 README 安裝 Python 依賴。' }
if (!(Test-Path -LiteralPath (Join-Path $PSScriptRoot 'frontend/dist/index.html'))) { throw '請先在 frontend 執行 npm ci 與 npm run build。' }
if (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) { throw '8765 已有人使用，請確認既有伺服器。' }
$goldServer = Start-Process -FilePath $goldPython -ArgumentList '-m','uvicorn','backend.app:app','--host','127.0.0.1','--port','8765' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot 'server.log') -RedirectStandardError (Join-Path $PSScriptRoot 'server-error.log')
Write-Output "伺服器 PID $($goldServer.Id)，請開啟 http://127.0.0.1:8765"
