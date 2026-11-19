param(
    [string]$Python = $(if ($env:WEMUST_PYTHON) { $env:WEMUST_PYTHON } else { 'python' })
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$credentialPath = Join-Path $repo '.local\credential.xml'
if (Test-Path -LiteralPath $credentialPath) {
    $credential = Import-Clixml -LiteralPath $credentialPath
    $env:WEMUST_USERNAME = $credential.UserName
    $env:WEMUST_PASSWORD = $credential.GetNetworkCredential().Password
}
# Respect an explicit grades opt-in, just as the Python entry point does.
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
Set-Location -LiteralPath $repo
# Compatibility with an existing local-only install. Normal installs use pip extras.
$localDependencies = Join-Path $repo '.local\python'
if (Test-Path -LiteralPath $localDependencies) {
    $env:PYTHONPATH = $localDependencies + [IO.Path]::PathSeparator + $env:PYTHONPATH
}
try {
    & $Python -m wemust.mcp_server
    $serverExitCode = $LASTEXITCODE
} finally {
    Remove-Item Env:WEMUST_PASSWORD -ErrorAction SilentlyContinue
}
exit $serverExitCode
