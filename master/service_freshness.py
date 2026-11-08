"""마스터 서비스가 **도는 코드**가 최신인가 (`#301`).

## [중요] 왜 필요한가 — 실측된 사고

    ax-task-queue 기동   2026-08-23 02:19
    `#293` 코드 변경      2026-08-24 00:48  (프로젝트 축 배선)
    → 파일은 새 코드, **도는 것은 옛 코드**

증상: `.33` 이 `project=NS` 를 보냈는데 목록이 **92건(modularstage)** 을 돌려줬다. 옛 코드에는
그 축이 없으니 기본값을 본 것이다. **하루 동안 `.33` 의 태그가 무시되고 있었다.**

[중요] `#277` 과 **같은 병, 다른 주체**다. 그쪽은 워커의 상주(claimer)를 고쳤고 배달이 그것을
본다. 이쪽은 **마스터 자신의 서비스**인데 아무도 안 본다 — 그래서 같은 문장이 다른 자리에서
재현됐다. 리포트 34 §3 이 *"확인은 파일 해시가 아니라 도는 프로세스로 한다"* 를 적었는데,
그 판정을 마스터 쪽에는 두지 않았다.

## [주의] 판정하고 **말하는 것까지**가 범위다

자동 재기동은 하지 않는다 — `docs/11` §11.5(운영 데몬 재기동은 승인)이고, 그 규칙이 생긴 계기가
*"운영 인프라 PC 의 데몬을 승인 없이 재기동해 강한 항의"* 다.

## [중요] 「상주」와 「발동형」은 다르다

`ax-indexer`·`ax-status` 는 oneshot 이라 **다음 발동이 곧 새 코드**다 — 판정 대상이 아니다.
그것을 섞으면 늘 빨간 줄이 하나 있는 화면이 되고, 그러면 아무도 안 본다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 서비스 → 그 서비스가 읽는 코드 경로 (`ExecStart` 의 모듈에서 왔다).
# [주의] **넓게 잡지 않는다** — 무관한 파일을 넣으면 늘 stale 로 보여 판정이 죽는다.
RESIDENT: dict = {
    "ax-task-queue": ("master/task_queue",),
    "ax-broker": ("master/broker",),
    "ax-projects": ("master/projects", "master/webui", "master/context_search",
                    "master/work/register.py"),
}
# [DOC] #772: ax-projects는 master.work.register 등 상주 의존 파일도 읽는다.
# master/work 전체를 감시하면 oneshot 워커 코드의 변경도 재기동 경고로 섞인다.
# 상주 의존 파일을 명시하고 기존 서비스 경로·공개 API·자동 재기동 금지 정책을 보존한다.
# 허용 수정: 이 파일과 master/test_service_freshness.py. 다른 파일은 읽기 전용이다.
# 파일을 읽기 전 별도 rg --files 호출로 실제 목록을 얻고 그 결과의 경로만 읽는다.
# 발동형 — 판정 대상이 **아니다**(다음 발동이 새 코드다). 이름을 적어 두는 이유는
# 「빠뜨린 것」과 「일부러 뺀 것」을 구분하기 위해서다.
TRIGGERED = ("ax-indexer", "ax-status", "ax-batch")
RECORD_PREFIX = "AX_SERVICE_CODE_V1 "


def _snapshot(paths: tuple, *, require_files: bool = False) -> tuple:
    """선언 경로·파일 목록·내용의 해시. mtime은 코드 정체가 아니다 (#897)."""
    entries = []
    file_count = 0
    missing = []
    try:
        for rel in paths:
            target = REPO / rel
            try:
                target.stat()
                exists = True
            except FileNotFoundError:
                exists = False
            if exists and target.is_file():
                files = [target] if target.suffix == ".py" else []
                kind = "file"
            elif exists and target.is_dir():
                files = []
                def failed(error):
                    raise error
                for base, dirs, names in os.walk(target, onerror=failed):
                    dirs.sort()
                    files.extend(Path(base) / name for name in sorted(names)
                                 if name.endswith(".py"))
                kind = "directory"
            else:
                # 삭제도 비교 대상이다. 전부 사라져도 현재 상태를 해시할 수 있다.
                files, kind = [], "missing"
                missing.append(rel)
            entries.append([rel, kind])
            for path in sorted(files):
                file_count += 1
                entries.append([path.relative_to(REPO).as_posix(),
                                hashlib.sha256(path.read_bytes()).hexdigest()])
        if require_files and (missing or not file_count):
            return "", "기동 때 감시 코드가 없거나 선언 경로가 누락됐다"
        data = json.dumps(entries, ensure_ascii=True, separators=(",", ":"))
        return hashlib.sha256(data.encode("utf-8")).hexdigest(), ""
    except OSError as exc:
        return "", f"코드 내용을 읽지 못했다 ({type(exc).__name__})"


def record_startup(unit: str) -> dict:
    """서비스 import 전에 한 번 기록한다. 읽기 전용 broker도 stdout→journal을 쓴다.

    systemd의 INVOCATION_ID와 결합해 수동 실행·이전 프로세스 기록을 재사용하지 않는다.
    내용 읽기 실패는 기록에 남기고 검사에서 판정 불가로 보고한다. 자동 재기동은 하지 않는다.
    """
    paths = RESIDENT[unit]
    invocation = os.environ.get("INVOCATION_ID", "")
    digest, why = _snapshot(paths, require_files=True)
    if not re.fullmatch(r"[0-9a-f]{32}", invocation):
        why = "systemd INVOCATION_ID가 없다 — 수동 실행은 기준 기록으로 쓰지 않는다"
    record = dict(version=1, unit=unit, invocation_id=invocation,
                  paths=list(paths), digest=digest, why=why)
    print(RECORD_PREFIX + json.dumps(record, ensure_ascii=True), flush=True)
    return record


def _invocation(unit: str, *, runner=None) -> tuple:
    run = runner or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True,
                                                timeout=10))
    try:
        result = run(["systemctl", "show", unit, "-p", "InvocationID", "--value"])
        invocation = (result.stdout or "").strip()
        if result.returncode or not re.fullmatch(r"[0-9a-f]{32}", invocation):
            return "", "현재 서비스 InvocationID를 읽지 못했다"
        return invocation, ""
    except (OSError, subprocess.SubprocessError):
        return "", "현재 서비스 InvocationID 조회에 실패했다"


def _baseline(unit: str, paths: tuple, *, runner=None, invocation: str = "") -> tuple:
    """현재 systemd invocation의 기록만 읽는다. 로그 유실은 최신으로 보지 않는다."""
    run = runner or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True,
                                                timeout=10))
    try:
        if not invocation:
            invocation, why = _invocation(unit, runner=runner)
            if why:
                return "", why
        result = run(["journalctl", "--no-pager", "--all", "-o", "json", "-n", "2",
                      f"_SYSTEMD_INVOCATION_ID={invocation}",
                      f"--grep=^{RECORD_PREFIX}"])
        if result.returncode:
            return "", f"기동 코드 기록을 읽지 못했다 (journalctl rc={result.returncode})"
        records = []
        for line in (result.stdout or "").splitlines():
            entry = json.loads(line)
            message = entry.get("MESSAGE", "")
            if (entry.get("_SYSTEMD_INVOCATION_ID") != invocation
                    or entry.get("_SYSTEMD_UNIT") != f"{unit}.service"
                    or not isinstance(message, str)
                    or not message.startswith(RECORD_PREFIX)):
                return "", "기동 코드 기록의 서비스·invocation·형식이 일치하지 않는다"
            records.append(json.loads(message[len(RECORD_PREFIX):]))
        if len(records) != 1:
            return "", "현재 기동 코드 기록이 없거나 중복됐다 — 판정할 수 없다"
        record = records[0]
        if (not isinstance(record, dict) or record.get("version") != 1
                or record.get("unit") != unit
                or record.get("invocation_id") != invocation
                or record.get("paths") != list(paths)):
            return "", "기동 코드 기록의 서비스·버전·감시 범위가 일치하지 않는다"
        if record.get("why"):
            return "", f"기동 코드 기록은 판정 불가다: {record['why']}"
        digest = record.get("digest", "")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            return "", "기동 코드 기록의 내용 해시가 올바르지 않다"
        return digest, ""
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, AttributeError):
        return "", "기동 코드 기록 조회 또는 해석에 실패했다"


@dataclass
class Verdict:
    unit: str
    started: int = 0            # ExecMainStartTimestamp (epoch)
    newest: int = 0             # 그 서비스가 읽는 코드의 최신 mtime
    newest_file: str = ""
    stale: bool = False
    why: str = ""
    paths: tuple = field(default_factory=tuple)

    @property
    def line(self) -> str:
        if self.why:
            return f"{self.unit}: [주의] {self.why}"
        if self.stale:
            return (f"{self.unit}: [중요] **옛 코드로 돈다** — 기동 뒤에 "
                    f"`{self.newest_file}` 가 바뀌었다. 재기동이 필요하다 "
                    f"(`scripts/ax-service-restart {self.unit}`)")
        return f"{self.unit}: 도는 것이 지금 코드다"


def _started(unit: str, *, runner=None) -> tuple:
    """`(epoch, 사유)`. [중요] 판정 근거는 **`ExecMainStartTimestamp`** 다 — 종료코드도
    `is-active` 도 아니다(리포트 26 §5: 실패한 재기동이 옛 프로세스를 남겨 `active` 였다)."""
    run = runner or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True,
                                                timeout=10))
    r = run(["systemctl", "show", unit, "-p", "ExecMainStartTimestampMonotonic",
             "-p", "ExecMainStartTimestamp", "--value"])
    if r.returncode != 0:
        return 0, f"systemctl 을 읽지 못했다 (rc={r.returncode})"
    lines = [x.strip() for x in (r.stdout or "").splitlines() if x.strip()]
    if not lines:
        return 0, "기동 시각이 비어 있다 — 서비스가 한 번도 안 떴을 수 있다"
    # `date -d` 로 파싱한다 — 로케일·형식이 환경마다 다르므로 우리가 추측하지 않는다
    for text in lines:
        p = run(["date", "-d", text, "+%s"])
        if p.returncode == 0 and (p.stdout or "").strip().isdigit():
            return int(p.stdout.strip()), ""
    return 0, f"기동 시각을 파싱하지 못했다: {lines[0][:40]}"


def _newest(paths: tuple) -> tuple:
    """그 코드 경로들의 최신 `.py` mtime `(epoch, 파일)`."""
    # [DOC] #772: 선언된 디렉터리의 재귀 .py와 단일 .py 파일을 모두 판정한다.
    # 비Python 파일·존재하지 않는 경로는 건너뛰고 stat 실패의 기존 취급을 유지한다.
    best, who = 0, ""
    for rel in paths:
        d = REPO / rel
        if d.is_file() and d.suffix == ".py":
            files = (d,)
        elif d.is_dir():
            files = d.rglob("*.py")
        else:
            continue
        for f in files:
            try:
                m = int(f.stat().st_mtime)
            except OSError:
                continue
            if m > best:
                best, who = m, str(f.relative_to(REPO))
    return best, who


def check(unit: str = "", *, runner=None) -> list:
    """상주 서비스별 판정. `unit` 을 주면 그것만."""
    out: list = []
    for name, paths in RESIDENT.items():
        if unit and name != unit:
            continue
        v = Verdict(unit=name, paths=paths)
        try:
            v.started, v.why = _started(name, runner=runner)
            v.newest, v.newest_file = _newest(paths)
        except (OSError, subprocess.SubprocessError):
            v.why = "기동 시각 또는 코드 시각을 읽지 못했다"
        if not v.why:
            invocation, v.why = _invocation(name, runner=runner)
        if not v.why:
            baseline, v.why = _baseline(name, paths, runner=runner, invocation=invocation)
            if not v.why:
                current, v.why = _snapshot(paths)
                if not v.why:
                    v.stale = current != baseline
                    if v.stale:
                        v.newest_file = "감시 코드 내용 또는 파일 목록"
            if not v.why:
                final_invocation, v.why = _invocation(name, runner=runner)
                if not v.why and final_invocation != invocation:
                    v.why = "검사 중 서비스가 다시 기동됐다 — 판정할 수 없다"
                if v.why:
                    v.stale = False
        out.append(v)
    return out


def stale_lines(*, runner=None) -> list:
    """사람에게 보일 줄 — **문제 있는 것만.** 조용할 때는 아무 줄도 내지 않는다."""
    return [v.line for v in check(runner=runner) if v.stale or v.why]
