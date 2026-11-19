$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'This script requires Windows DPAPI.' }
$repo = Split-Path -Parent $PSScriptRoot
$username = Read-Host 'WeMust student ID'
if ([string]::IsNullOrWhiteSpace($username)) { throw 'Student ID is required.' }
$password = Read-Host 'WeMust password (hidden)' -AsSecureString
if ($password.Length -eq 0) { throw 'Password is required.' }
$credential = New-Object System.Management.Automation.PSCredential($username, $password)
$folder = Join-Path $repo '.local'
New-Item -ItemType Directory -Force -Path $folder | Out-Null
$credential | Export-Clixml -LiteralPath (Join-Path $folder 'credential.xml')
Write-Host 'Saved using Windows encryption for this Windows user. No login was attempted.'
Read-Host 'Press Enter to close'
