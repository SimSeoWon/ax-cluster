"""Git-managed Codex Session 0 runtime delivery.

The package is built outside the worker (normally CI or a designated Windows
builder).  Workers receive only the verified binaries; Rust and Visual Studio
are never installed by onboarding.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from . import bundle

ENV_PACKAGE = "AX_CODEX_RUNTIME_PACKAGE"
INSTALL_REL = ".ax/codex-session0"


class RuntimeError(RuntimeError):
    pass


def package_dir() -> Path | None:
    raw = os.environ.get(ENV_PACKAGE, "").strip()
    return Path(raw).expanduser() if raw else None


def manifest(package: Path) -> dict:
    path = package / "manifest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"runtime manifest 읽기 실패: {path}: {exc}") from exc
    if data.get("schema") != 1 or not data.get("commit"):
        raise RuntimeError(f"runtime manifest 형식 오류: {path}")
    for entry in data.get("files") or []:
        name = str(entry.get("name") or "")
        src = package / name
        if not name or not src.is_file():
            raise RuntimeError(f"runtime 산출물 없음: {src}")
        got = hashlib.sha256(src.read_bytes()).hexdigest()
        if got != str(entry.get("sha256") or "").lower():
            raise RuntimeError(f"runtime 해시 불일치: {name}")
    return data


def _scp(src: Path, facts, target: str) -> None:
    p = subprocess.run(
        ["scp", "-q", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
         str(src), f"{facts.user}@{facts.host}:{target}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=bundle.SSH_TIMEOUT, check=False)
    if p.returncode:
        raise RuntimeError(f"{facts.host}: runtime 전송 실패 — {(p.stderr or '')[:180]}")


def install(facts) -> dict:
    """Install a verified package on one Windows worker; return an audit record."""
    if not facts.windows:
        return {"host": facts.host, "status": "skip", "reason": "Windows 아님"}
    package = package_dir()
    if package is None:
        return {"host": facts.host, "status": "skip", "reason": f"{ENV_PACKAGE} 미설정"}
    data = manifest(package)
    tag = str(data["commit"])[0:12]
    remote = f"C:/Users/{facts.user}/AppData/Local/Temp/ax-codex-runtime-{tag}"
    for entry in data["files"]:
        _scp(package / entry["name"], facts, f"{remote}/{entry['name']}")
    _scp(package / "manifest.json", facts, f"{remote}/manifest.json")
    # The command is deliberately self-contained: no remote script is trusted.
    cmd = (
        "powershell -NoProfile -ExecutionPolicy Bypass -Command "
        f"$src='{remote}'; $dst=Join-Path $env:USERPROFILE '{INSTALL_REL}'; "
        "New-Item -ItemType Directory -Force -Path $dst | Out-Null; "
        "$m=Get-Content -Raw -LiteralPath (Join-Path $src 'manifest.json') | ConvertFrom-Json; "
        "foreach($e in $m.files){$p=Join-Path $src $e.name; "
        "if((Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash.ToLower() -ne $e.sha256){throw 'runtime hash mismatch'}; "
        "Copy-Item -LiteralPath $p -Destination (Join-Path $dst $e.name) -Force}; "
        "& (Join-Path $dst 'codex.exe') --version; "
        "if($LASTEXITCODE -ne 0){throw 'runtime version check failed'}; "
        "Write-Output 'AX_CODEX_RUNTIME_OK'"
    )
    rc, out = bundle._ssh(facts.host, facts.user, cmd, timeout=bundle.SSH_TIMEOUT)
    if rc != 0 or "AX_CODEX_RUNTIME_OK" not in (out or ""):
        raise RuntimeError(f"{facts.host}: runtime 설치 검증 실패 rc={rc} — {(out or '')[-300:]}")
    return {"host": facts.host, "status": "installed", "commit": data["commit"],
            "files": [e["name"] for e in data["files"]], "output": (out or "").strip()[-160:]}
