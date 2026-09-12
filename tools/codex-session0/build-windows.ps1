param(
    [string]$OutputDirectory = "",
    [string]$SourceDirectory = ""
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$contract = Join-Path $here 'runtime.toml'
$lines = Get-Content -LiteralPath $contract
function Value([string]$key) {
    $pattern = '^{0}\s*=\s*"([^"]+)"' -f [regex]::Escape($key)
    $line = $lines | Where-Object { $_ -match $pattern } | Select-Object -First 1
    if (-not $line) { throw "runtime.toml missing $key" }
    return ([regex]::Match($line, $pattern).Groups[1].Value)
}

$repo = Value 'repository'
$commit = Value 'commit'
$toolchain = Value 'rust_toolchain'
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $here 'artifacts' }
if (-not $SourceDirectory) { $SourceDirectory = Join-Path $env:TEMP ("codex-session0-src-" + $commit.Substring(0, 12)) }

if (-not (Test-Path -LiteralPath $SourceDirectory)) {
    git clone --filter=blob:none --no-checkout $repo $SourceDirectory
}
git -C $SourceDirectory fetch --quiet --depth 1 origin $commit
git -C $SourceDirectory checkout --detach --quiet $commit
if ((git -C $SourceDirectory rev-parse HEAD).Trim() -ne $commit) { throw 'source commit mismatch' }

$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$vsPath = & $vswhere -products * -latest -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vsPath) { throw 'MSVC x64 toolset not found' }
& (Join-Path $vsPath 'Common7\Tools\Launch-VsDevShell.ps1') -Arch amd64 -HostArch amd64 -SkipAutomaticLocation | Out-Null
$cargo = Join-Path $env:USERPROFILE '.cargo\bin\cargo.exe'
if (-not (Test-Path -LiteralPath $cargo)) { throw 'Rust is required on the build machine; install rustup first' }

Set-Location (Join-Path $SourceDirectory 'codex-rs')
& $cargo +$toolchain build --release --bin codex --bin codex-code-mode-host
if ($LASTEXITCODE -ne 0) { throw "cargo build failed: $LASTEXITCODE" }

$release = Join-Path (Get-Location) 'target\release'
$package = Join-Path $OutputDirectory ("codex-session0-" + $commit.Substring(0, 12))
New-Item -ItemType Directory -Force -Path $package | Out-Null
$files = @('codex.exe', 'codex-code-mode-host.exe')
$entries = foreach ($name in $files) {
    $src = Join-Path $release $name
    if (-not (Test-Path -LiteralPath $src)) { throw "build output missing: $name" }
    $dst = Join-Path $package $name
    Copy-Item -LiteralPath $src -Destination $dst -Force
    $item = Get-Item -LiteralPath $dst
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $dst).Hash.ToLowerInvariant()
    [ordered]@{ name = $name; size = $item.Length; sha256 = $hash }
}
$manifest = [ordered]@{
    schema = 1
    repository = $repo
    commit = $commit
    rust_toolchain = $toolchain
    files = @($entries)
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $package 'manifest.json') -Encoding utf8
Write-Output ("PACKAGE={0}" -f $package)
Get-Content -LiteralPath (Join-Path $package 'manifest.json')
