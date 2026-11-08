"""서비스 신선도 판정 (`#301`) — pytest 없이 그대로 실행.

    .venv/bin/python master/test_service_freshness.py

[중요] 지키는 불변식:
   1. 기동 뒤에 코드가 바뀌면 **stale 이라고 말한다** (실측: 하루 동안 옛 코드로 돌았다)
   2. 현재 systemd invocation의 기동 내용 해시를 비교한다 — mtime은 진단 정보다
   3. **못 읽었으면 「최신」으로 접지 않는다** (모르는 것을 괜찮다고 하지 않는다)
   4. **발동형(oneshot)은 판정 대상이 아니다** — 다음 발동이 곧 새 코드다
   5. 조용할 때는 **아무 줄도 내지 않는다** (늘 빨간 줄이 있으면 아무도 안 본다)
   6. [주의] **자동 재기동을 하지 않는다** — 승인 사항이다 (`docs/11` §11.5)
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import service_freshness as F      # noqa: E402

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [완료] {label}")
    else:
        FAIL += 1
        print(f"  [실패] {label}" + (f" — {detail}" if detail else ""))


INVOCATION = "a" * 32


def startup(unit: str) -> tuple:
    output = io.StringIO()
    with patch.dict(os.environ, {"INVOCATION_ID": INVOCATION}), contextlib.redirect_stdout(output):
        record = F.record_startup(unit)
    return record, output.getvalue().strip()


def fake(records=None, *, rc=0, journal_rc=0, journal=None,
         invocation=INVOCATION, started="Sat 2026-08-23 02:19:20 KST", epoch="100"):
    """가짜 systemctl·date·journal. **실 서비스를 건드리지 않는다.**"""
    records = records or {}
    calls = []
    current = ""

    class R:
        def __init__(self, code, out):
            self.returncode, self.stdout, self.stderr = code, out, ""

    def run(cmd):
        nonlocal current
        calls.append(cmd)
        if cmd[0] == "systemctl":
            current = cmd[2]
            if "InvocationID" in cmd:
                return R(rc, invocation)
            return R(rc, started)
        if cmd[0] == "date":
            return R(0, epoch)
        if cmd[0] == "journalctl":
            if journal is not None:
                return R(journal_rc, journal)
            message = records.get(current, "")
            entry = {"MESSAGE": message, "_SYSTEMD_INVOCATION_ID": invocation,
                     "_SYSTEMD_UNIT": f"{current}.service"}
            return R(journal_rc, json.dumps(entry) if message else "")
        return R(1, "")
    run.calls = calls
    return run


# [DOC] #772: 운영 서비스·원격 파일을 건드리지 않는 회귀 검사다.
# 임시 일반 파일, 결정적 mtime, 가짜 runner로 판정하고 바꾼 F.REPO 등은 반드시 복원한다.
# 이 회귀 검사는 운영 실증이나 Git 조건 검사를 대신하지 않는다.
# 새 테스트는 실제 F.RESIDENT 선언을 사용하여 register.py 감시 누락 회귀를 잡아야 한다.
# 정상/오류 판정과 디렉터리 감시는 기존 정책을 보존한다.
def test_project_dependencies() -> None:
    paths = F.RESIDENT["ax-projects"]
    check("ax-projects가 register.py를 명시적으로 감시한다",
          "master/work/register.py" in paths, str(paths))
    check("master/work 전체와 워커 전용 파일은 감시하지 않는다",
          "master/work" not in paths
          and "master/work/infer.py" not in paths
          and "master/work/autodispatch.py" not in paths, str(paths))

    old_repo = F.REPO
    try:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            F.REPO = root

            for rel in paths:
                target = root / rel
                if target.suffix == ".py":
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text("# resident\n", encoding="utf-8")
                    os.utime(target, (10, 10))
                else:
                    target.mkdir(parents=True, exist_ok=True)
                    resident = target / "resident.py"
                    resident.write_text("# resident\n", encoding="utf-8")
                    os.utime(resident, (10, 10))

            work = root / "master/work"
            for name in ("infer.py", "autodispatch.py"):
                ignored = work / name
                ignored.write_text("# worker only\n", encoding="utf-8")
                os.utime(ignored, (300, 300))
            note = work / "README.md"
            note.write_text("worker documentation\n", encoding="utf-8")
            os.utime(note, (300, 300))

            register = root / "master/work/register.py"
            _, message = startup("ax-projects")
            runner = fake({"ax-projects": message})
            register.write_text("# changed resident\n", encoding="utf-8")
            os.utime(register, (200, 200))
            verdict = F.check("ax-projects", runner=runner)[0]
            check("register.py 내용 변경을 감지한다", verdict.stale, verdict.line)

            register.write_text("# resident\n", encoding="utf-8")
            os.utime(register, (10, 10))
            verdict = F.check("ax-projects", runner=runner)[0]
            check("워커 전용 파일과 문서 변경만으로는 조용하다",
                  not verdict.stale and not verdict.why, verdict.line)
            register.unlink()
            verdict = F.check("ax-projects", runner=runner)[0]
            check("명시 단일 파일 삭제도 감지한다", verdict.stale and not verdict.why, verdict.line)

            single = root / "single.py"
            single.write_text("# single\n", encoding="utf-8")
            os.utime(single, (30, 30))
            nested = root / "tree/nested.py"
            nested.parent.mkdir(parents=True)
            nested.write_text("# nested\n", encoding="utf-8")
            os.utime(nested, (40, 40))
            non_python = root / "note.txt"
            non_python.write_text("not code\n", encoding="utf-8")
            os.utime(non_python, (90, 90))

            newest, who = F._newest(("single.py", "tree", "missing.py", "note.txt"))
            check("단일 .py와 디렉터리 재귀를 함께 탐색한다",
                  newest == 40 and who == "tree/nested.py", f"{newest}, {who}")
            check("누락 및 비Python 경로만 있으면 읽지 못한 것으로 남긴다",
                  F._newest(("missing.py", "note.txt")) == (0, ""))
    finally:
        F.REPO = old_repo


def test_content_and_errors() -> None:
    old_repo = F.REPO
    unit = "ax-task-queue"
    try:
        with tempfile.TemporaryDirectory() as td:
            F.REPO = root = Path(td)
            source = root / "master/task_queue/resident.py"
            source.parent.mkdir(parents=True)
            source.write_text("# resident\n", encoding="utf-8")
            os.utime(source, (10, 10))
            record, message = startup(unit)
            runner = fake({unit: message})
            check("기동 기록에 버전·서비스·현재 invocation이 있다",
                  record.get("version") == 1 and record.get("unit") == unit
                  and record.get("invocation_id") == INVOCATION, str(record))
            check("기동 기록에 내용 해시가 있다", len(record.get("digest", "")) == 64)
            check("기동 기록은 stdout 한 줄이다",
                  message.startswith(F.RECORD_PREFIX) and "\n" not in message)
            verdict = F.check(unit, runner=runner)[0]
            check("같은 내용이면 최신이다", not verdict.stale and not verdict.why, verdict.line)
            source.write_text("# resident\n", encoding="utf-8")
            os.utime(source, (300, 300))
            verdict = F.check(unit, runner=runner)[0]
            check("같은 내용 재작성·mtime만 기동 뒤 바뀌면 최신이다",
                  not verdict.stale and not verdict.why, verdict.line)
            source.write_text("# changed\n", encoding="utf-8")
            os.utime(source, (10, 10))
            verdict = F.check(unit, runner=runner)[0]
            check("mtime이 기동 전이어도 내용이 다르면 stale이다",
                  verdict.stale and not verdict.why, verdict.line)
            check("재기동 명령을 안내한다", "scripts/ax-service-restart ax-task-queue" in verdict.line)
            source.write_text("# resident\n", encoding="utf-8")
            added = source.with_name("added.py")
            added.write_text("# added\n", encoding="utf-8")
            verdict = F.check(unit, runner=runner)[0]
            check("Python 파일 추가를 감지한다", verdict.stale, verdict.line)
            added.unlink()
            source.unlink()
            verdict = F.check(unit, runner=runner)[0]
            check("마지막 Python 파일 삭제도 감지한다", verdict.stale and not verdict.why, verdict.line)
            empty_record, empty_message = startup(unit)
            verdict = F.check(unit, runner=fake({unit: empty_message}))[0]
            check("기동 때 Python 파일이 없으면 최신으로 접지 않는다",
                  bool(empty_record.get("why")) and bool(verdict.why) and not verdict.stale, verdict.line)
            source.write_text("# resident\n", encoding="utf-8")
            cases = [
                ("기동 기록 없음", fake()),
                ("systemctl 읽기 실패", fake({unit: message}, rc=1)),
                ("기동 시각 없음", fake({unit: message}, started="")),
                ("현재 invocation 없음", fake({unit: message}, invocation="")),
                ("journal 읽기 실패", fake({unit: message}, journal_rc=1)),
                ("journal JSON 손상", fake(journal="{broken")),
                ("메시지 JSON 손상", fake({unit: F.RECORD_PREFIX + "{broken"})),
            ]
            for field, value in (("version", 2), ("unit", "ax-broker"),
                                 ("invocation_id", "b" * 32), ("paths", ["other"]),
                                 ("digest", "not-a-hash"), ("why", "기동 읽기 실패")):
                changed = dict(record, **{field: value})
                cases.append((f"기록 {field} 불일치", fake({unit: F.RECORD_PREFIX + json.dumps(changed)})))
            old_entry = json.dumps({"MESSAGE": message, "_SYSTEMD_INVOCATION_ID": "b" * 32,
                                    "_SYSTEMD_UNIT": f"{unit}.service"})
            entry = json.dumps({"MESSAGE": message, "_SYSTEMD_INVOCATION_ID": INVOCATION,
                                "_SYSTEMD_UNIT": f"{unit}.service"})
            cases.extend((("이전 invocation 기록", fake(journal=old_entry)),
                          ("중복 기동 기록", fake(journal=entry + "\n" + entry))))
            for label, injected in cases:
                verdict = F.check(unit, runner=injected)[0]
                check(label + "는 판정 불가다", bool(verdict.why) and not verdict.stale, verdict.line)
            invocations = 0
            stable = fake({unit: message})

            def restarted(cmd):
                nonlocal invocations
                result = stable(cmd)
                if cmd[0] == "systemctl" and "InvocationID" in cmd:
                    invocations += 1
                    if invocations > 1:
                        result.stdout = "b" * 32
                return result

            verdict = F.check(unit, runner=restarted)[0]
            check("판정 중 서비스 재기동은 판정 불가다", bool(verdict.why) and not verdict.stale, verdict.line)
            original_read = Path.read_bytes

            def denied(path):
                if path == source:
                    raise PermissionError("test read denied")
                return original_read(path)

            with patch.object(Path, "read_bytes", denied):
                verdict = F.check(unit, runner=runner)[0]
            check("현재 내용 읽기 실패는 판정 불가다", bool(verdict.why) and not verdict.stale, verdict.line)
            check("journal 조회가 현재 invocation으로 한정된다", any(
                f"_SYSTEMD_INVOCATION_ID={INVOCATION}" in cmd for cmd in runner.calls))
            check("검사 중 자동 재기동·쓰기 명령이 없다", all(
                cmd[0] in ("systemctl", "date", "journalctl") and "restart" not in cmd
                for cmd in runner.calls))
    finally:
        F.REPO = old_repo


def test_entrypoint_order() -> None:
    """진입점의 실제 top-level 실행을 관측하되 서버 import 직전에 멈춘다."""
    import builtins

    original_import = builtins.__import__

    class BeforeServiceImport(Exception):
        pass

    for package, argv, expected in (
        ("projects", ["service"], "ax-projects"),
        ("broker", ["service"], "ax-broker"),
        ("task_queue", ["service", "--serve", "state"], "ax-task-queue"),
        ("task_queue", ["service"], ""),
    ):
        events = []

        def importing(name, globals=None, locals=None, fromlist=(), level=0):
            if name in ("__future__", "sys"):
                return original_import(name, globals, locals, fromlist, level)
            if name == "service_freshness":
                return SimpleNamespace(record_startup=lambda unit: events.append(("record", unit)))
            events.append(("import", name))
            raise BeforeServiceImport

        source = (Path(__file__).resolve().parent / package / "__main__.py").read_text(encoding="utf-8")
        namespace = {"__name__": "__main__", "__package__": f"master.{package}"}
        with patch.object(builtins, "__import__", importing), patch.object(sys, "argv", argv):
            try:
                exec(compile(source, f"master/{package}/__main__.py", "exec"), namespace)
            except BeforeServiceImport:
                pass
        records = [event for event in events if event[0] == "record"]
        if expected:
            check(f"{package} 서버 import 전에 기동 기록을 한 번 남긴다",
                  events[:1] == [("record", expected)] and records == [("record", expected)]
                  and any(event[0] == "import" for event in events), str(events))
        else:
            check("task_queue stdio 실행은 기동 기록으로 stdout을 오염시키지 않는다",
                  not records, str(events))


def test_first_filter_912() -> None:
    """#912 — journal 조회에 `-n` 없음 · mtime 1차 거름(기동 뒤 변경 흔적 없으면 journal 없이 최신)."""
    old_repo = F.REPO
    unit = "ax-task-queue"
    try:
        with tempfile.TemporaryDirectory() as td:
            F.REPO = root = Path(td)
            pkg = root / "master/task_queue"
            pkg.mkdir(parents=True)
            source = pkg / "resident.py"
            source.write_text("# resident\n", encoding="utf-8")
            record, message = startup(unit)
            # 기동 기록은 있는 상태에서 조회 명령 모양을 본다(내용 경로를 타게 mtime 은 지금)
            runner = fake({unit: message})
            F.check(unit, runner=runner)
            jc = [cmd for cmd in runner.calls if cmd[0] == "journalctl"]
            check("#912 journal 조회를 실제로 했다(내용 경로)", bool(jc), str(runner.calls))
            check("#912 journal 조회에 -n 이 없다(systemd 249 는 -n 을 --grep 보다 먼저 적용)",
                  all("-n" not in cmd for cmd in jc), str(jc))

            def settle(t):
                os.utime(source, (t, t))
                os.utime(pkg, (t, t))
            settle(50)                                 # 기동(epoch 100) 전에 모두 확정
            cache = pkg / "__pycache__"
            cache.mkdir()
            os.utime(pkg, (50, 50))
            os.utime(cache, (500, 500))                # 실행 중 pyc 쓰기 — 무시해야 한다
            no_record = fake()                         # journal 에 기동 기록이 없다(보존 만료)
            v = F.check(unit, runner=no_record)[0]
            check("#912 기동 뒤 변경 흔적 없음 → journal 없이 최신", not v.stale and not v.why, v.line)
            check("#912 1차 거름 통과 시 journal 을 부르지 않는다",
                  not any(cmd[0] == "journalctl" for cmd in no_record.calls), str(no_record.calls))
            added = pkg / "added.py"
            added.write_text("# added\n", encoding="utf-8")
            os.utime(added, (50, 50))                  # 파일 mtime 은 옛것이어도
            os.utime(pkg, (300, 300))                  # 디렉터리 mtime 이 추가를 남긴다
            v = F.check(unit, runner=fake())[0]
            check("#912 파일 추가(디렉터리 mtime) → 1차 거름 불통과 · 기록 없으면 판정 불가",
                  bool(v.why) and not v.stale, v.line)
            v = F.check(unit, runner=fake({unit: message}))[0]
            check("#912 파일 추가 → 기록이 있으면 내용 비교로 stale", v.stale and not v.why, v.line)
            added.unlink()
            settle(50)
            os.utime(source, (300, 300))               # 같은 내용 재작성(mtime 만 새것)
            v = F.check(unit, runner=fake({unit: message}))[0]
            check("#912 mtime 만 새것 → 내용 비교로 최신(#897 목적 유지)", not v.stale and not v.why, v.line)
        with tempfile.TemporaryDirectory() as td:
            F.REPO = root = Path(td)
            for rel in F.RESIDENT["ax-projects"]:
                target = root / rel
                if rel.endswith(".py"):
                    continue                           # 단일 파일(register.py)을 일부러 빠뜨린다
                target.mkdir(parents=True)
                (target / "m.py").write_text("x = 1\n", encoding="utf-8")
                os.utime(target / "m.py", (50, 50))
                os.utime(target, (50, 50))
            os.utime(root / "master", (50, 50))
            v = F.check("ax-projects", runner=fake())[0]
            check("#912 선언 경로 누락은 1차 거름을 통과하지 않는다(최신으로 접지 않음)",
                  bool(v.why) and not v.stale, v.line)
    finally:
        F.REPO = old_repo


def main() -> int:
    print("\n[1] 기동 내용·목록 비교와 판정 불가 처리 (#897)")
    test_content_and_errors()
    print("\n[2] 상주 의존 파일·범위 보존 (#772)")
    test_project_dependencies()
    print("\n[3] 최신일 때 조용하고 oneshot을 제외한다")
    records = {unit: startup(unit)[1] for unit in F.RESIDENT}
    check("모두 최신이면 경고 목록이 비어 있다", F.stale_lines(runner=fake(records)) == [])
    check("상주 세 서비스만 판정한다", set(F.RESIDENT) == {"ax-task-queue", "ax-broker", "ax-projects"})
    check("oneshot 서비스는 명시적으로 제외한다", all(
        unit not in F.RESIDENT and F.check(unit, runner=fake()) == [] for unit in F.TRIGGERED))
    print("\n[4] 진입점이 서비스 모듈 import 전에 기록한다")
    test_entrypoint_order()
    print("\n[5] #912 journal 조회 -n 없음 · mtime 1차 거름")
    test_first_filter_912()
    print(f"\n{'='*46}\n통과 {PASS} · 실패 {FAIL}\n{'='*46}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
