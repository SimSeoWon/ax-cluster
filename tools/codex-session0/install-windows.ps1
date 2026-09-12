param(
    [Parameter(Mandatory=$true)][string]$PackageDirectory,
    [string]$InstallDirectory = ""
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $here 'verify-windows.ps1') -PackageDirectory $PackageDirectory
if (-not $InstallDirectory) {
    $InstallDirectory = Join-Path $env:USERPROFILE '.ax\codex-session0'
}
New-Item -ItemType Directory -Force -Path $InstallDirectory | Out-Null
foreach ($name in @('codex.exe', 'codex-code-mode-host.exe', 'manifest.json')) {
    Copy-Item -LiteralPath (Join-Path $PackageDirectory $name) -Destination (Join-Path $InstallDirectory $name) -Force
}
$wrapper = Join-Path $InstallDirectory 'codex-session0.cmd'
Set-Content -LiteralPath $wrapper -Encoding ascii -Value @('@echo off', '"%~dp0codex.exe" %*')
Write-Output ("INSTALLED={0}" -f $InstallDirectory)
