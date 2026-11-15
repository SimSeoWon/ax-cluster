"""AXCluster 통합 검사: 명시된 스크립트를 별도 프로세스로 실행하고 검사 건수를 확인한다.

이 모듈은 기존 스크립트형 검사를 unittest discovery에 연결하는 어댑터다.
검사 대상은 JSON 목록으로 고정하며, 종료 코드만으로 통과시키지 않는다.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile


class CheckConfigError(ValueError):
    """명시된 통합 검사 계약이 잘못됐다."""


def _validate(entry: dict, root: Path) -> dict:
    if not isinstance(entry, dict):
        raise CheckConfigError("검사 항목은 객체여야 한다.")
    unknown = set(entry) - {"path", "count_pattern", "failed_count_pattern", "timeout"}
    if unknown:
        raise CheckConfigError(f"모르는 검사 설정: {', '.join(sorted(unknown))}")
    path = entry.get("path")
    if not isinstance(path, str) or not path or "\\" in path:
        raise CheckConfigError("path는 저장소 기준 상대 경로여야 한다.")
    rel = PurePosixPath(path)
    if rel.is_absolute() or ".." in rel.parts or ":" in path:
        raise CheckConfigError(f"저장소 밖 검사 경로: {path}")
    target = (root / path).resolve()
    if not target.is_relative_to(root) or not target.is_file() or target.suffix != ".py":
        raise CheckConfigError(f"검사 파일이 없거나 저장소 밖이다: {path}")
    if len(rel.parts) != 2 or rel.parts[0] != "master" or not rel.name.startswith("test_"):
        raise CheckConfigError(f"검사는 master/test_*.py를 명시해야 한다: {path}")
    for key in ("count_pattern", "failed_count_pattern"):
        pattern = entry.get(key)
        if key == "failed_count_pattern" and pattern is None:
            continue
        if not isinstance(pattern, str) or not pattern:
            raise CheckConfigError(f"{path}: {key}가 비었다.")
        try:
            regex = re.compile(pattern, re.MULTILINE)
        except re.error as e:
            raise CheckConfigError(f"{path}: 잘못된 {key}: {e}") from e
        if "count" not in regex.groupindex:
            raise CheckConfigError(f"{path}: {key}에는 (?P<count>...)가 필요하다.")
    timeout = entry.get("timeout", 120)
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or timeout <= 0):
        raise CheckConfigError(f"{path}: timeout은 양의 유한 초여야 한다.")
    return dict(entry, path=str(rel), timeout=timeout)


PARALLEL_CONFIG = "tests/test-parallel.json"
PARALLEL_KINDS = ("integration_jobs", "sweep_jobs")
PARALLEL_ENV = "AX_TEST_JOBS"


def _jobs_value(raw) -> int | None:
    """양의 정수만 받는다. bool·실수·문자열 숫자가 아닌 값은 None."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, str):
        raw = raw.strip()
        if not re.fullmatch(r"[0-9]+", raw):
            return None
        raw = int(raw)
    if not isinstance(raw, int) or raw < 1:
        return None
    return raw


def parallel_jobs(kind: str, root: Path, *, env=None) -> dict:
    """검사 병렬 개수 (`#965`) — `{jobs, source, reason}`. 1 이면 순차다.

    순서: 환경변수 `AX_TEST_JOBS`(두 kind 공통, 급할 때 커밋 없이 덮어쓴다) → 저장소의
    `tests/test-parallel.json` 의 `kind` 값 → 없으면 1(설정 없는 저장소는 종전 순차 그대로).
    잘못된 값은 조용히 넘기지 않는다 — 1 로 돌리고 `reason` 에 무엇이 왜 잘못됐는지 남긴다.
    """
    if kind not in PARALLEL_KINDS:
        raise ValueError(f"모르는 병렬 설정 이름: {kind}")
    env = os.environ if env is None else env
    raw_env = env.get(PARALLEL_ENV)
    if raw_env is not None and str(raw_env).strip() != "":
        value = _jobs_value(str(raw_env))
        if value is None:
            return {"jobs": 1, "source": f"env {PARALLEL_ENV}",
                    "reason": f"[주의] {PARALLEL_ENV}={raw_env!r} 는 양의 정수가 아니다 — 순차(1)로 돈다"}
        return {"jobs": value, "source": f"env {PARALLEL_ENV}", "reason": ""}
    path = Path(root) / PARALLEL_CONFIG
    if not path.is_file():
        return {"jobs": 1, "source": "설정 없음", "reason": f"{PARALLEL_CONFIG} 없음 — 순차(1)"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return {"jobs": 1, "source": PARALLEL_CONFIG,
                "reason": f"[주의] {PARALLEL_CONFIG} 읽기 실패({type(e).__name__}) — 순차(1)로 돈다"}
    if not isinstance(data, dict) or kind not in data:
        return {"jobs": 1, "source": PARALLEL_CONFIG,
                "reason": f"[주의] {PARALLEL_CONFIG} 에 {kind} 가 없다 — 순차(1)로 돈다"}
    value = _jobs_value(data[kind])
    if value is None:
        return {"jobs": 1, "source": PARALLEL_CONFIG,
                "reason": f"[주의] {PARALLEL_CONFIG} {kind}={data[kind]!r} 는 양의 정수가 아니다 — 순차(1)로 돈다"}
    return {"jobs": value, "source": PARALLEL_CONFIG, "reason": ""}


def load_checks(manifest: Path, root: Path) -> list[dict]:
    """JSON 배열을 검증해 읽는다. 빈 목록·중복·잘못된 경계는 예외다."""
    root = Path(root).resolve()
    try:
        entries = json.loads(Path(manifest).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise CheckConfigError(f"검사 목록 읽기 실패: {e}") from e
    if not isinstance(entries, list) or not entries:
        raise CheckConfigError("검사 목록은 비어 있지 않은 JSON 배열이어야 한다.")
    checks = [_validate(entry, root) for entry in entries]
    paths = [(root / entry["path"]).resolve() for entry in checks]
    if len(set(paths)) != len(paths):
        raise CheckConfigError("검사 목록에 중복 파일이 있다.")
    return checks


def _text(value) -> str:
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else (value or "")


def _evidence(pattern: str, output: str) -> dict | None:
    matches = list(re.finditer(pattern, output, re.MULTILINE))
    if not matches:
        return None
    match = matches[-1]
    values = {}
    for key in ("count", "total", "failed", "skipped"):
        if key not in match.re.groupindex:
            continue
        raw = match.group(key)
        if raw is None and key != "count":
            values[key] = 0
            continue
        if raw is None or not re.fullmatch(r"[0-9]+", raw):
            raise ValueError(f"{key} 건수가 음수이거나 정수가 아니다.")
        values[key] = int(raw)
    values["text"] = match.group(0)
    return values


def run_check(root: Path, entry: dict, python: str = sys.executable, runner=None) -> dict:
    """검사별 Python 프로세스. import 전역 상태·환경 변경은 다음 검사에 전파되지 않는다.

    count_pattern은 마지막 요약의 실제 실행 건수를 포착해야 한다. 스크립트형 검사는
    failed_count_pattern으로 실패 건수 요약도 명시한다. 명시한 실패 요약이 없으면 차단한다.
    runner는 subprocess.run과 같은 키워드 인자를 받는 테스트 주입점이다.
    """
    root = Path(root).resolve()
    result = {"ok": False, "count": 0, "reason": "", "stdout": "", "stderr": "", "rc": None}
    try:
        check = _validate(entry, root)
    except CheckConfigError as e:
        result["reason"] = str(e)
        return result
    run = runner or subprocess.run
    try:
        with tempfile.TemporaryDirectory(prefix="ax-integration-check-") as temporary:
            isolated = Path(temporary)
            (isolated / "projects").mkdir()
            (isolated / "gitea").mkdir()
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
                       AX_PROJECTS_ROOT=str(isolated / "projects"),
                       AX_GITEA_REPO_ROOT=str(isolated / "gitea"))
            proc = run([python, "-B", str((root / check["path"]).resolve())], cwd=str(root),
                       shell=False, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=check["timeout"], env=env)
    except subprocess.TimeoutExpired as e:
        result.update(reason=f"타임아웃 {check['timeout']}초", stdout=_text(e.stdout), stderr=_text(e.stderr))
        return result
    except OSError as e:
        result["reason"] = f"검사 실행 실패: {e}"
        return result
    result.update(rc=proc.returncode, stdout=_text(proc.stdout), stderr=_text(proc.stderr))
    output = result["stdout"] + "\n" + result["stderr"]
    if proc.returncode != 0:
        result["reason"] = f"검사 실패: exit {proc.returncode}"
        return result
    try:
        evidence = _evidence(check["count_pattern"], output)
        count = evidence["count"] if evidence else 0
        result["count"] = count
        if count < 1:
            result["reason"] = "실행 건수 증거가 없거나 0개 실행이다."
            return result
        if evidence.get("total", count) != count or evidence.get("failed", 0) > 0:
            result["reason"] = "통과 건수와 전체 건수가 다르거나 실패 건수가 남았다."
            return result
        skipped = evidence.get("skipped", 0)
        if re.search(r"^Ran [0-9]+ tests? in", evidence["text"], re.MULTILINE):
            status = re.findall(r"^OK(?: \(skipped=([0-9]+)\))?\s*$", output, re.MULTILINE)
            if not status:
                result["reason"] = "unittest OK 완료 신호가 없다."
                return result
            skipped = int(status[-1] or "0")
        count -= skipped
        result["count"] = max(0, count)
        if count < 1:
            result["reason"] = "실제 실행 검사가 0건이다(전부 skip)."
            return result
        if check.get("failed_count_pattern"):
            failure = _evidence(check["failed_count_pattern"], output)
            if failure is None or failure["count"] > 0:
                result["reason"] = "실패 건수 증거가 없거나 실패가 1건 이상이다."
                return result
    except ValueError as e:
        result["reason"] = f"잘못된 실행 증거: {e}"
        return result
    # unittest의 FAILED 신호는 rc=0이어도 성공으로 덮지 않는다.
    if re.search(r"^FAILED(?:\s|$)", output, re.MULTILINE):
        result["reason"] = "unittest FAILED 신호를 확인했다."
        return result
    result.update(ok=True, reason=f"검사 {count}건 통과")
    return result
