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

import ast
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

# [DOC] #918: 「의존」 — 서비스가 실제로 import 하는 저장소 코드 중 `RESIDENT` 직접 경로 밖의 파일.
#       실측 2026-11-08: #917 이 `context_synth/issue_track` 등을 바꿨는데 ax-projects·ax-task-queue 는
#       `issue_infra` 를 거쳐 그것을 쓰면서도 「최신」이었다. 의존은 **진입 모듈에서 정적 import 를 따라가**
#       구한다(함수 안 지연 import 포함 — 언젠가 불리면 그때 메모리에 남는다). 폐포가 크다(약 150 파일,
#       11-01 이후 커밋의 3/4 이 건드린다) — 그래서 **두 등급**이다(사용자 결정 2026-11-08):
#       직접 경로 = 종전 [중요] stale(check·update rc 에 반영), 의존 = [주의] 「재기동 권장」(표시만).
ENTRY: dict = {                          # 서비스 → `ExecStart` 의 `python -m` 모듈
    "ax-task-queue": "master.task_queue",
    "ax-broker": "master.broker",
    "ax-projects": "master.projects",
}
_DEP_PACKAGES = ("master", "client")     # 이 저장소의 최상위 패키지 — 그 밖(표준·서드파티)은 의존이 아니다


def _module_file(name: str):
    """모듈 이름 → 저장소 안 파일(`pkg/__init__.py` 또는 `mod.py`). 없으면 None."""
    base = REPO.joinpath(*name.split("."))
    if (base / "__init__.py").is_file():
        return base / "__init__.py"
    if base.with_suffix(".py").is_file():
        return base.with_suffix(".py")
    return None


def _package_of(path: Path) -> str:
    rel = path.relative_to(REPO).with_suffix("")
    parts = list(rel.parts)
    return ".".join(parts[:-1])          # `pkg/__init__` → pkg · `pkg/mod` → pkg


def _imported(tree, package: str) -> list:
    """AST 의 모든 import(함수 안 포함)가 가리킬 수 있는 모듈 이름들."""
    names: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".") if package else []
                if node.level > 1:
                    base = base[:len(base) - (node.level - 1)]
                mod = ".".join(base + ([node.module] if node.module else []))
            else:
                mod = node.module or ""
            if mod:
                names.append(mod)
                names.extend(f"{mod}.{a.name}" for a in node.names if a.name != "*")
    return names


def _in_direct(rel: str, paths: tuple) -> bool:
    return any(rel == p or rel.startswith(p.rstrip("/") + "/") for p in paths)


def dependencies(unit: str) -> tuple:
    """`(의존 파일들(정렬·저장소 상대), 사유)`. 진입 모듈의 정적 import 폐포에서 직접 경로를 뺀 것.

    읽기만 한다. 실패(진입 모듈 없음·구문 오류·읽기 실패)는 사유로 돌려준다 — 「의존 없음」으로 접지 않는다.
    """
    entry = ENTRY.get(unit, "")
    start = [f for f in (_module_file(entry),
                         REPO.joinpath(*entry.split("."), "__main__.py") if entry else None)
             if f is not None and f.is_file()]
    if not start:
        return (), f"진입 모듈 {entry or '?'} 을 찾지 못했다"
    seen: set = set()
    todo = list(start)
    try:
        while todo:
            f = todo.pop()
            if f in seen:
                continue
            seen.add(f)
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
            for name in _imported(tree, _package_of(f)):
                if name.split(".")[0] not in _DEP_PACKAGES:
                    continue
                parts = name.split(".")
                for i in range(1, len(parts) + 1):       # `a.b.c` 는 a·a.b 의 __init__ 도 돈다
                    mf = _module_file(".".join(parts[:i]))
                    if mf is not None and mf not in seen:
                        todo.append(mf)
    except (OSError, SyntaxError, ValueError) as exc:
        return (), f"의존 import 를 읽지 못했다 ({type(exc).__name__})"
    rels = sorted(p.relative_to(REPO).as_posix() for p in seen)
    return tuple(r for r in rels if not _in_direct(r, RESIDENT.get(unit, ()))), ""


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
    # #918 — 의존 목록·해시를 덧붙인다(옛 판독기와 호환되게 같은 version 의 선택 필드).
    deps, deps_why = dependencies(unit)
    deps_digest = ""
    if not deps_why:
        deps_digest, deps_why = _snapshot(deps)
    record.update(deps=list(deps), deps_digest=deps_digest, deps_why=deps_why)
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
    record, why = _record(unit, paths, runner=runner, invocation=invocation)
    if why:
        return "", why
    if record.get("why"):
        return "", f"기동 코드 기록은 판정 불가다: {record['why']}"
    digest = record.get("digest", "")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        return "", "기동 코드 기록의 내용 해시가 올바르지 않다"
    return digest, ""


def _record(unit: str, paths: tuple, *, runner=None, invocation: str = "") -> tuple:
    """`(기동 기록 사전, 사유)` — 현재 invocation 의 기록 하나를 형식·범위까지 검증해 돌려준다(#918 분리)."""
    run = runner or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True,
                                                timeout=10))
    try:
        if not invocation:
            invocation, why = _invocation(unit, runner=runner)
            if why:
                return {}, why
        # 🔴 #912 — `-n` 을 붙이지 않는다. systemd 249 는 `-n` 을 `--grep` 보다 먼저 적용해
        #    마지막 N 줄만 잘라 온 뒤 거른다 — 기동 첫 줄인 기록을 로그 2줄 만에 놓쳤다(실측 2026-11-08).
        #    범위는 이미 `_SYSTEMD_INVOCATION_ID` 가 이번 기동으로 좁힌다.
        result = run(["journalctl", "--no-pager", "--all", "-o", "json",
                      f"_SYSTEMD_INVOCATION_ID={invocation}",
                      f"--grep=^{RECORD_PREFIX}"])
        if result.returncode:
            return {}, f"기동 코드 기록을 읽지 못했다 (journalctl rc={result.returncode})"
        records = []
        for line in (result.stdout or "").splitlines():
            entry = json.loads(line)
            message = entry.get("MESSAGE", "")
            if (entry.get("_SYSTEMD_INVOCATION_ID") != invocation
                    or entry.get("_SYSTEMD_UNIT") != f"{unit}.service"
                    or not isinstance(message, str)
                    or not message.startswith(RECORD_PREFIX)):
                return {}, "기동 코드 기록의 서비스·invocation·형식이 일치하지 않는다"
            records.append(json.loads(message[len(RECORD_PREFIX):]))
        if len(records) != 1:
            return {}, "현재 기동 코드 기록이 없거나 중복됐다 — 판정할 수 없다"
        record = records[0]
        if (not isinstance(record, dict) or record.get("version") != 1
                or record.get("unit") != unit
                or record.get("invocation_id") != invocation
                or record.get("paths") != list(paths)):
            return {}, "기동 코드 기록의 서비스·버전·감시 범위가 일치하지 않는다"
        return record, ""
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, AttributeError):
        return {}, "기동 코드 기록 조회 또는 해석에 실패했다"


@dataclass
class Verdict:
    unit: str
    started: int = 0            # ExecMainStartTimestamp (epoch)
    newest: int = 0             # 그 서비스가 읽는 코드의 최신 mtime
    newest_file: str = ""
    stale: bool = False
    why: str = ""
    paths: tuple = field(default_factory=tuple)
    # #918 의존 판정 — [주의] 등급(표시만). stale·why·stale_lines·update rc 와 섞지 않는다.
    dep_changed: bool = False
    dep_files: list = field(default_factory=list)
    dep_why: str = ""

    @property
    def dep_line(self) -> str:
        """의존 등급 줄 — 바뀌었거나 판정 불가일 때만. 조용하면 빈 문자열."""
        if self.dep_changed:
            shown = ", ".join(f"`{f}`" for f in self.dep_files[:3])
            more = f" 외 {len(self.dep_files) - 3}개" if len(self.dep_files) > 3 else ""
            return (f"{self.unit}: [주의] 기동 뒤 의존 모듈이 바뀌었다 — 재기동 권장"
                    f"{(' (' + shown + more + ')') if shown else ''}"
                    f" (`scripts/ax-service-restart {self.unit}`)")
        if self.dep_why:
            return f"{self.unit}: [주의] 의존 모듈 판정 불가 — {self.dep_why}"
        return ""

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


def _untouched_since(paths: tuple, started: int) -> bool:
    """#912 1차 거름 — 기동 뒤 감시 경로에 **아무 변경 흔적이 없는가**.

    `.py` 파일 mtime 과 디렉터리 mtime(파일 추가·삭제·이름 변경이 남긴다)을 함께 본다.
    `__pycache__` 는 실행 중 pyc 쓰기로 바뀌므로 뺀다. 선언 경로가 없거나 읽기에 실패하면
    거짓 — 최종 판정(기동 기록·내용 해시)으로 넘긴다. **참일 때만** journal 없이 최신으로 본다:
    journal 보존이 짧아(실측 ≈18시간) 오래 돈 서비스의 기동 기록은 사라진다.
    """
    try:
        for rel in paths:
            target = REPO / rel
            if target.is_file():
                if target.stat().st_mtime > started:
                    return False
                continue
            if not target.is_dir():
                return False
            for base, dirs, names in os.walk(target):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                if Path(base).stat().st_mtime > started:
                    return False
                for name in names:
                    if name.endswith(".py") and (Path(base) / name).stat().st_mtime > started:
                        return False
        return True
    except OSError:
        return False


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
        if not v.why and v.started and _untouched_since(paths, v.started):
            _judge_deps(v, name, paths, runner=runner)   # #912 1차 거름 — 직접 경로는 기동 뒤 변경 흔적 없음
            out.append(v)
            continue
        invocation = ""
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
        if not v.why and not v.stale:
            _judge_deps(v, name, paths, runner=runner, invocation=invocation)
        out.append(v)
    return out


def _judge_deps(v: Verdict, unit: str, paths: tuple, *, runner=None, invocation: str = "") -> None:
    """#918 — 의존 등급 판정을 `v.dep_*` 에 채운다. 직접 판정(stale·why)은 건드리지 않는다.

    1차 거름: 지금 의존 파일들에 기동 뒤 변경 흔적이 없으면 조용하다(import 목록이 바뀌려면 이미 있는
    파일이 바뀌어야 하므로 그것도 여기 걸린다). 흔적이 있으면 기동 기록의 의존 목록·해시와 대조한다.
    """
    deps, why = dependencies(unit)
    if why:
        v.dep_why = why
        return
    if v.started and _untouched_since(deps, v.started):
        return
    if not invocation:
        invocation, why = _invocation(unit, runner=runner)
        if why:
            v.dep_why = why
            return
    record, why = _record(unit, paths, runner=runner, invocation=invocation)
    if why:
        v.dep_why = why
        return
    if "deps" not in record:
        v.dep_why = "기동 기록에 의존 목록이 없다(#918 이전 기동) — 다음 재기동부터 판정한다"
        return
    if record.get("deps_why"):
        v.dep_why = f"기동 때 의존을 읽지 못했다: {record['deps_why']}"
        return
    recorded = list(record.get("deps") or [])
    current, why = _snapshot(deps)
    if why:
        v.dep_why = why
        return
    if recorded != list(deps) or current != record.get("deps_digest"):
        v.dep_changed = True
        added = sorted(set(deps) - set(recorded))
        removed = sorted(set(recorded) - set(deps))
        touched = []
        for rel in deps:
            try:
                if (REPO / rel).stat().st_mtime > v.started:
                    touched.append(rel)
            except OSError:
                continue
        v.dep_files = added + [f"-{r}" for r in removed] + [t for t in touched if t not in added]


def dep_lines(*, runner=None, verdicts=None) -> list:
    """#918 의존 등급 줄 — [주의] 「재기동 권장」·판정 불가만. `stale_lines` 와 따로 둔다(rc 에 섞지 않는다)."""
    vs = verdicts if verdicts is not None else check(runner=runner)
    return [v.dep_line for v in vs if v.dep_line]


def stale_lines(*, runner=None) -> list:
    """사람에게 보일 줄 — **문제 있는 것만.** 조용할 때는 아무 줄도 내지 않는다."""
    return [v.line for v in check(runner=runner) if v.stale or v.why]
