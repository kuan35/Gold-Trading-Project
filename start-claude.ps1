$ErrorActionPreference = 'Stop'
$Port = 8765
$goldProduct = $PSScriptRoot
$goldPython = Join-Path $goldProduct '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $goldPython)) { throw 'Python runtime missing; follow product/README.md.' }
if (!(Test-Path -LiteralPath (Join-Path $goldProduct 'frontend/dist/index.html'))) { throw 'Build frontend first: npm run build.' }
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { throw "Port $Port is in use. Stop the existing Gold Desk service before switching providers." }
$goldSaved = @{}
$goldSettings = @{GOLD_ENABLE_LLM='true';GOLD_LLM_PROVIDER='claude_code';GOLD_CLAUDE_MODEL='sonnet';GOLD_CLAUDE_EFFORT='medium';GOLD_CLAUDE_TIMEOUT_SECONDS='120'}
try {
    foreach ($goldName in $goldSettings.Keys) {
        $goldSaved[$goldName] = [Environment]::GetEnvironmentVariable($goldName,'Process')
        [Environment]::SetEnvironmentVariable($goldName,$goldSettings[$goldName],'Process')
    }
    $goldServer = Start-Process -FilePath $goldPython -ArgumentList '-m','uvicorn','backend.app:app','--host','127.0.0.1','--port',"$Port" -WorkingDirectory $goldProduct -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $goldProduct 'server-claude.log') -RedirectStandardError (Join-Path $goldProduct 'server-claude-error.log')
    Write-Output "Gold Desk Claude Code PID $($goldServer.Id): http://127.0.0.1:$Port"
    Write-Output 'Claude Code is ready for user-initiated analysis. Choose model and effort in the web UI.'
} finally {
    foreach ($goldName in $goldSaved.Keys) { [Environment]::SetEnvironmentVariable($goldName,$goldSaved[$goldName],'Process') }
}
