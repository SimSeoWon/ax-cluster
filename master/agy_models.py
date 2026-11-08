"""agy canonical model policy and process-shared availability (#830)."""
from __future__ import annotations

import fcntl
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MODEL = "gemini-3.8-flash-medium"
CATALOG_TTL = 300
COOLDOWN_SECONDS = 600
_PARSER_LOCK = threading.Lock()


def usage_parser():
    """Use the canonical parser, also for the existing bare layer2_verify entry."""
    try:
        from master.work import usage
        return usage
    except ModuleNotFoundError as exc:
        if exc.name not in ("master", "master.work", "master.work.usage"):
            raise
    # The standalone script puts master/, rather than its parent, on sys.path.
    # Load that same verified parser file without importing work/__init__.py.
    name = "_ax_agy_usage_parser"
    with _PARSER_LOCK:
        if name in sys.modules:
            return sys.modules[name]
        spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / "work" / "usage.py")
        if spec is None or spec.loader is None:
            raise ImportError("cannot load existing agy usage parser")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(name, None)
            raise
        return module


@dataclass
class AgyResult:
    raw: str | None = None
    rc: int = -1
    why: str = ""
    requested_model: str = ""
    actual_model: str = ""
    model_source: str = ""
    attempts: list = field(default_factory=list)


def default_state_path() -> Path:
    override = os.environ.get("AX_AGY_STATE_PATH")
    if override:
        return Path(override)
    root = os.environ.get("AX_PROJECTS_ROOT")
    if root:
        return Path(root) / ".ax" / "agy" / "models.json"
    return Path.home() / ".cache" / "ax-agy" / "models.json"


@contextmanager
def _state(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(data, dict):
            raise ValueError("agy model state must be an object")
        yield data
        fd, name = tempfile.mkstemp(prefix=".models-", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(data, out, ensure_ascii=False)
                out.flush()
                os.fsync(out.fileno())
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)


def parse_catalog(stdout: str) -> dict:
    """`agy models`: canonical id TAB display label (no alias resolution API)."""
    rows = {}
    for line in stdout.splitlines():
        bits = line.strip().split("\t", 1)
        if len(bits) == 2 and re.fullmatch(r"[a-z0-9][a-z0-9.-]*", bits[0]):
            rows[bits[0]] = bits[1].strip()
    if not rows:
        raise ValueError("agy models returned no canonical model rows")
    return rows


def _catalog_run(exe: str, timeout: float) -> str:
    proc = subprocess.run([exe, "models"], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout,
                          stdin=subprocess.DEVNULL)
    if proc.returncode:
        raise RuntimeError(f"agy models rc={proc.returncode}: {(proc.stderr or proc.stdout).strip()}")
    return proc.stdout


def reset_deadline(text: str, now: float) -> float:
    """Relative quota reset durations; absent/unknown resets use a bounded cooldown."""
    match = re.search(r"resets?\s+in\s*[:=]?\s*~?\s*((?:\d+(?:\.\d+)?\s*(?:hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s|days?|d)\s*)+)",
                      text, re.I)
    seconds = 0.0
    if match:
        for number, unit in re.findall(r"(\d+(?:\.\d+)?)\s*([a-z]+)", match.group(1), re.I):
            factor = {"d": 86400, "h": 3600, "m": 60, "s": 1}[unit[0].lower()]
            seconds += float(number) * factor
    return now + (seconds if seconds > 0 else COOLDOWN_SECONDS)


# 🔴 `#845` — 한도 신호만 잡는다. 종전 `\b429\b|…|quota|…` 는 agy CLI 정상 로그(`quota_manager.go`
#    · `doRefreshQuota` · `quotaProject=`)와 glog 스레드 번호 열(`… 429 cache.go`)에 걸려, 실측 로그
#    248개 중 247개가 「한도」였다 — 타임아웃이든 빈 출력이든 실패마다 600초 쿨다운이 걸렸다.
#    실제 소진(2026-10-18): `RESOURCE_EXHAUSTED (code 429): Individual quota reached. … Resets in 150h53m7s.`
_LIMIT_RE = re.compile(
    r"RESOURCE_EXHAUSTED|\b(?:code|status|http)[\s:=]*429\b|\b429\s+too many requests"
    r"|quota\s+(?:reached|exceeded|exhausted)|rate[\s_-]?limit(?:ed|\s+exceeded|\s+reached)"
    r"|too many requests", re.I)


def _limited(text: str) -> bool:
    return bool(_LIMIT_RE.search(text))


def cooldown_left(model: str, *, state_path=None, clock=time.time) -> float:
    """모델의 남은 쿨다운 초(`#920`). 지난 429 의 기록일 뿐 잔여 한도를 재는 값이 아니다."""
    path = Path(state_path) if state_path is not None else default_state_path()
    with _state(path) as data:
        until = float(data.setdefault("cooldowns", {}).get(model, 0))
    return max(0.0, until - clock())


def note_limit(model: str, evidence: str, *, state_path=None, clock=time.time) -> float:
    """한도 응답을 쿨다운으로 남긴다(`#920`) — 다음 호출이 한도에 다시 부딪히지 않게."""
    path = Path(state_path) if state_path is not None else default_state_path()
    until = reset_deadline(evidence, clock())
    with _state(path) as data:
        data.setdefault("cooldowns", {})[model] = until
    return until


def execute(exe, build_command, runner, *, timeout, model="", allow_argon=False,
            fallback_models=(), state_path=None, catalog_runner=None,
            clock=time.time) -> AgyResult:
    """Run explicit models; runner returns `(output, why, rc, raw_stdout)`."""
    result = AgyResult()
    path = Path(state_path) if state_path is not None else default_state_path()
    deadline = time.monotonic() + timeout
    explicit = bool(model)
    models = tuple(dict.fromkeys((model or DEFAULT_MODEL, *fallback_models)))
    try:
        # Policy is checked before metadata or generation, including labels and aliases.
        for selected in models:
            if not isinstance(selected, str) or not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", selected):
                raise ValueError(f"canonical model id required: {selected!r}")
            if "argon" in selected.casefold():
                if not (explicit and allow_argon and selected == model and not fallback_models):
                    raise ValueError("Argon requires an explicit model and allow_argon=True; no automatic fallback")
            elif not selected.startswith("gemini-"):
                raise ValueError(f"automatic agy models must be Gemini: {selected}")
        now = clock()
        with _state(path) as data:
            cached = data.get("catalog", {})
            valid_cache = (cached.get("exe") == exe and
                           0 <= now - float(cached.get("at", 0)) < CATALOG_TTL and
                           isinstance(cached.get("models"), dict) and cached["models"])
            if valid_cache:
                catalog = cached["models"]
            else:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("agy deadline before model catalog")
                catalog = parse_catalog((catalog_runner or _catalog_run)(exe, remaining))
                data["catalog"] = {"exe": exe, "at": now, "models": catalog}
            for selected in models:
                if selected not in catalog:
                    raise ValueError(f"model absent from agy models (aliases rejected): {selected}")
                if "argon" in str(catalog[selected]).casefold() and not (explicit and allow_argon):
                    raise ValueError(f"automatic model resolves to Argon label: {selected}")
        for selected in models:
            result.requested_model = selected
            with _state(path) as data:
                until = float(data.setdefault("cooldowns", {}).get(selected, 0))
            if until > clock():
                result.why = f"{selected}: model cooldown {until - clock():.0f}s"
                result.attempts.append({"requested_model": selected, "skipped": result.why})
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                result.why = "agy total timeout"
                break
            with tempfile.TemporaryDirectory(prefix="ax-agy-model-") as td:
                log_path = Path(td) / "attempt.log"
                started = time.monotonic()
                out, why, rc, raw = runner(build_command(selected, str(log_path)),
                                           timeout=remaining)
                elapsed = time.monotonic() - started
                log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
            # Import only on master execution; usage.py is also shipped as a parser to requesters.
            usage = usage_parser()
            trace = usage.parse_agy_log(log)
            parsed = usage.parse_agy_json(raw or out or "")
            actual = trace["model"] or (parsed[3] if parsed else "")
            source = trace.get("model_source", "log") if trace["model"] else ("envelope" if actual else "")
            error = usage.agy_envelope_error(raw or out or "")
            evidence = "\n".join((why or "", error, log))
            failure = why or trace["final_failure"]
            if parsed is not None and not parsed[0].strip():
                failure = failure or "빈 출력 (rc=0)" + (f" status={parsed[2]}" if parsed[2] != "SUCCESS" else "")
            mismatch = bool(actual and actual != selected)
            if mismatch:
                failure = f"agy model mismatch: requested={selected}, actual={actual}; output rejected"
            elif parsed and parsed[2] == "ERROR" and not trace["recovered"]:
                failure = failure or error or "agy status=ERROR without proven recovery"
            if out is None:
                failure = failure or f"agy failed rc={rc}"
            # 사용자 결정(#830): 실제 모델을 증명하지 못한 출력은 쓰지 않는다. 별칭이 조용히
            # 다른 모델로 풀린 사고가 바로 이 「미상」 상태였다. 쿨다운·폴백 없이 실패로 닫는다.
            unknown = not failure and not actual
            if unknown:
                failure = f"agy 실제 모델 미상 — 출력 사용 금지 (requested={selected})"
            result.raw, result.rc, result.why = (None if unknown else raw or out), rc, failure
            result.actual_model, result.model_source = actual, source
            result.attempts.append({"requested_model": selected, "actual_model": actual,
                                    "model_source": source, "raw": raw or out,
                                    "rc": rc, "why": failure, "seconds": elapsed})
            with _state(path) as data:
                cooldowns = data.setdefault("cooldowns", {})
                if (failure and not mismatch and not unknown and _limited(evidence)
                        and not trace["recovered"]):
                    cooldowns[selected] = reset_deadline(evidence, clock())
                elif not failure:
                    cooldowns.pop(selected, None)
            if not failure:
                return result
            # Unknown failures, unknown models and alias mismatches are not hidden by model fallback.
            if mismatch or unknown or not (_limited(evidence) and not trace["recovered"]):
                break
    except (OSError, ValueError, TypeError, RuntimeError, TimeoutError,
            subprocess.SubprocessError) as exc:
        result.why = f"agy model policy: {type(exc).__name__}: {exc}"
    return result
