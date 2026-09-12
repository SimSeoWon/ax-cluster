param([Parameter(Mandatory=$true)][string]$PackageDirectory)
$ErrorActionPreference = 'Stop'
$manifestPath = Join-Path $PackageDirectory 'manifest.json'
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
if ($manifest.schema -ne 1) { throw 'unsupported runtime manifest schema' }
foreach ($entry in $manifest.files) {
    $path = Join-Path $PackageDirectory $entry.name
    if (-not (Test-Path -LiteralPath $path)) { throw "missing package file: $($entry.name)" }
    $item = Get-Item -LiteralPath $path
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
    if ($item.Length -ne [int64]$entry.size -or $hash -ne $entry.sha256) {
        throw "manifest mismatch: $($entry.name)"
    }
}
$codex = Join-Path $PackageDirectory 'codex.exe'
& $codex --version
if ($LASTEXITCODE -ne 0) { throw 'patched codex version check failed' }
& $codex sandbox cmd.exe /d /c echo AX_SESSION0_RUNTIME_OK
if ($LASTEXITCODE -ne 0) { throw "Session 0 sandbox smoke test failed: $LASTEXITCODE" }
Write-Output 'VERIFY=OK'
