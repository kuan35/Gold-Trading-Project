$ErrorActionPreference = 'Stop'
$goldProduct = $PSScriptRoot
$goldPython = Join-Path $goldProduct '.venv/Scripts/python.exe'
$goldCredential = Join-Path $goldProduct 'private/groq_20261012/credential.dpapi'
if (!(Test-Path -LiteralPath $goldPython)) { throw 'Python runtime missing; follow product README.' }
if (!(Test-Path -LiteralPath $goldCredential)) { throw 'Local encrypted Groq credential missing. Configure your own environment variables instead.' }
if (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 8765 is already in use; stop the existing Gold Desk server first.' }
try {
    $goldSecure = Get-Content -LiteralPath $goldCredential | ConvertTo-SecureString
    $env:GOLD_LLM_API_KEY = [System.Net.NetworkCredential]::new('', $goldSecure).Password
    $env:GOLD_ENABLE_LLM = 'true'
    $env:GOLD_LLM_PROVIDER = 'openai_compatible'
    $env:GOLD_LLM_BASE_URL = 'https://api.groq.com/openai/v1'
    $env:GOLD_LLM_MODEL = 'openai/gpt-oss-120b'
    $env:GOLD_LLM_TOKEN_FIELD = 'max_completion_tokens'
    $env:GOLD_LLM_MAX_TOKENS = '2048'
    $env:GOLD_LLM_REASONING_EFFORT = 'low'
    $env:GOLD_LLM_TIMEOUT_SECONDS = '40'
    $goldServer = Start-Process -FilePath $goldPython -ArgumentList '-m','uvicorn','backend.app:app','--host','127.0.0.1','--port','8765' -WorkingDirectory $goldProduct -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $goldProduct 'server.log') -RedirectStandardError (Join-Path $goldProduct 'server-error.log')
    Write-Output "Gold Desk Groq server PID $($goldServer.Id): http://127.0.0.1:8765"
} finally {
    Remove-Item Env:GOLD_LLM_API_KEY -ErrorAction SilentlyContinue
    Remove-Variable goldSecure -ErrorAction SilentlyContinue
}
