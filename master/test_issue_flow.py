"""일감 작업 흐름(`#879`) 계약 테스트 — [중요] **플랜 없이 시작하지 않는가, 어긋난 기준에서
브랜치를 만들지 않는가, Redmine 기록 실패를 성공으로 보고하지 않는가.**

실 Redmine 을 두드리지 않는다(getter/noter 주입). git 은 임시 디렉토리의 **실제 저장소**와
bare origin 으로 돈다 — 주입한 git 은 계약만 시험한다(CLAUDE.md 「주입은 계약을 시험한다」).
실행: python3 master/test_issue_flow.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import issue_flow as IF    # noqa: E402

PASS = FAIL = 0

SPEC = "## 목적\n\n무엇을 만든다.\n\n## 플랜\n\n"
PLAN = ("<!-- ax:plan:begin v=1 -->\n"
        "| ID | 상태 | 목표 | 대상 | 선행 | 검증 | 근거 |\n"
        "|---|---|---|---|---|---|---|\n"
        "| T1 | 대기 | 한다 | x | — | y |  |\n"
        "<!-- ax:plan:end -->\n")


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def sh(cwd, *args) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


class Issue:
    def __init__(self, body: str, status: str = "신규", answer: str = "레드마인 #1 갱신 (notes)"):
        self.body, self.status, self.answer, self.notes = body, status, answer, []

    def get(self, iid):
        return {"id": iid, "subject": "제목", "status": self.status, "description": self.body}

    def note(self, iid, *, notes, status_name=""):
        self.notes.append((notes, status_name))
        return self.answer


def make_repo(tmp: Path) -> Path:
    bare, work = tmp / "origin.git", tmp / "work"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    subprocess.run(["git", "clone", "-q", str(bare), str(work)], check=True,
                   capture_output=True)
    sh(work, "config", "user.email", "t@t")
    sh(work, "config", "user.name", "t")
    sh(work, "switch", "-q", "-c", "main")
    (work / "a.txt").write_text("a\n")
    sh(work, "add", "a.txt")
    sh(work, "commit", "-q", "-m", "init")
    sh(work, "push", "-q", "origin", "main")
    return work


def run(fn):
    with tempfile.TemporaryDirectory() as d:
        fn(Path(d))


def t_plan_needed_refuses(tmp):
    repo = make_repo(tmp)
    iss = Issue(SPEC)
    r = IF.start(7, repo=repo, getter=iss.get, noter=iss.note)
    check("플랜 없음 → 거절", not r["ok"] and r["step"] == "plan", str(r))
    check("플랜 없음 → 브랜치 안 만듦", sh(repo, "branch", "--list", "issue/7") == "")
    check("플랜 없음 → 노트 없음", iss.notes == [])


def t_no_spec_refuses(tmp):
    repo = make_repo(tmp)
    iss = Issue("## 플랜\n")
    r = IF.start(7, repo=repo, getter=iss.get, noter=iss.note)
    check("스펙 없음 → 거절", not r["ok"] and r.get("verdict") == "no_spec", str(r))


def t_happy_path(tmp):
    repo = make_repo(tmp)
    ev = tmp / "ev.jsonl"
    iss = Issue(SPEC + PLAN)
    head = sh(repo, "rev-parse", "HEAD")
    r = IF.start(7, repo=repo, getter=iss.get, noter=iss.note, events_path=ev)
    check("정상 → ok", r["ok"] and not r["already"], str(r))
    check("정상 → issue/7 에 서 있다", sh(repo, "rev-parse", "--abbrev-ref", "HEAD") == "issue/7")
    check("정상 → 시작 리비전 = main HEAD", r.get("start_rev") == head)
    check("정상 → 노트에 전체 해시", len(iss.notes) == 1 and head in iss.notes[0][0], str(iss.notes))
    check("신규 → 진행으로", iss.notes and iss.notes[0][1] == "진행")
    lines = [json.loads(x) for x in ev.read_text().splitlines()]
    check("단계 로그가 jsonl 에", [x["step"] for x in lines] == ["plan", "fetch", "base", "branch", "redmine"],
          str([x["step"] for x in lines]))
    # 다시 부르면 새 기록 없이 같은 시작점
    r2 = IF.start(7, repo=repo, getter=iss.get, noter=iss.note)
    check("재호출 → already · 같은 시작점", r2["ok"] and r2["already"] and r2["start_rev"] == head, str(r2))
    check("재호출 → 노트 추가 없음", len(iss.notes) == 1)


def t_status_kept_when_not_new(tmp):
    repo = make_repo(tmp)
    iss = Issue(SPEC + PLAN, status="진행")
    IF.start(7, repo=repo, getter=iss.get, noter=iss.note)
    check("진행 중 일감 → 상태 안 바꿈", iss.notes and iss.notes[0][1] == "")


def t_dirty_refuses(tmp):
    repo = make_repo(tmp)
    (repo / "b.txt").write_text("x")
    iss = Issue(SPEC + PLAN)
    r = IF.start(7, repo=repo, getter=iss.get, noter=iss.note)
    check("dirty → 거절", not r["ok"] and r["step"] == "base", str(r))
    check("dirty → 파일 보존", (repo / "b.txt").exists())
    check("dirty → 브랜치 없음", sh(repo, "branch", "--list", "issue/7") == "")


def t_not_on_main_refuses(tmp):
    repo = make_repo(tmp)
    sh(repo, "switch", "-q", "-c", "other")
    iss = Issue(SPEC + PLAN)
    r = IF.start(7, repo=repo, getter=iss.get, noter=iss.note)
    check("main 아님 → 거절", not r["ok"] and r["step"] == "base", str(r))


def t_ahead_of_origin_refuses(tmp):
    repo = make_repo(tmp)
    (repo / "a.txt").write_text("b\n")
    sh(repo, "commit", "-q", "-am", "local")
    iss = Issue(SPEC + PLAN)
    r = IF.start(7, repo=repo, getter=iss.get, noter=iss.note)
    check("origin 과 어긋남 → 거절", not r["ok"] and r["step"] == "base" and "다르다" in r["why"], str(r))


def t_existing_branch_elsewhere_refuses(tmp):
    repo = make_repo(tmp)
    sh(repo, "branch", "issue/7")
    iss = Issue(SPEC + PLAN)
    r = IF.start(7, repo=repo, getter=iss.get, noter=iss.note)
    check("다른 데 서서 기존 브랜치 → 거절", not r["ok"] and r["step"] == "branch", str(r))


def t_redmine_failure_rolls_back(tmp):
    repo = make_repo(tmp)
    iss = Issue(SPEC + PLAN, answer="[주의] 레드마인 #7 갱신 실패: 503")
    r = IF.start(7, repo=repo, getter=iss.get, noter=iss.note)
    check("기록 실패 → ok 아님", not r["ok"] and r["step"] == "redmine", str(r))
    check("기록 실패 → 브랜치 되돌림", r.get("branch_rolled_back") is True
          and sh(repo, "branch", "--list", "issue/7") == ""
          and sh(repo, "rev-parse", "--abbrev-ref", "HEAD") == "main")


def t_read_failure(tmp):
    repo = make_repo(tmp)
    r = IF.start(7, repo=repo, getter=lambda i: {"error": "404"}, noter=lambda *a, **k: "")
    check("읽기 실패 → 거절", not r["ok"] and "읽지 못했다" in r["why"], str(r))


class Q:
    """리뷰 큐 대역 — 등재 인자를 기록한다."""

    def __init__(self, fail: bool = False):
        self.items, self.fail = [], fail

    def __call__(self, root, **kw):
        if self.fail:
            raise RuntimeError("큐가 깨졌다")
        self.items.append((root, kw))
        return {"state": "pending"}


def started(tmp: Path):
    """시작한 상태 + 커밋 둘."""
    repo = make_repo(tmp)
    iss = Issue(SPEC + PLAN)
    IF.start(7, repo=repo, getter=iss.get, noter=iss.note)
    base = sh(repo, "rev-parse", "HEAD")
    for name in ("b.txt", "c.txt"):
        (repo / name).write_text(name)
        sh(repo, "add", name)
        sh(repo, "commit", "-q", "-m", f"add {name}")
    return repo, iss, base, sh(repo, "rev-parse", "HEAD")


def t_finish_preview_writes_nothing(tmp):
    repo, iss, base, end = started(tmp)
    q = Q()
    n0 = len(iss.notes)
    r = IF.finish(7, repo=repo, noter=iss.note, enqueue=q, review_root=tmp)
    check("종료 미리보기 → ok · 확인 전", r["ok"] and r["confirmed"] is False, str(r))
    check("미리보기 → 범위", r.get("base") == base and r.get("end") == end and len(r["commits"]) == 2)
    check("미리보기 → 원격 그대로", sh(repo, "rev-parse", "origin/main") == base)
    check("미리보기 → 브랜치·노트·등재 0", sh(repo, "rev-parse", "--abbrev-ref", "HEAD") == "issue/7"
          and len(iss.notes) == n0 and not q.items)


def t_finish_confirm(tmp):
    repo, iss, base, end = started(tmp)
    q, ev = Q(), tmp / "ev.jsonl"
    r = IF.finish(7, confirm=True, repo=repo, noter=iss.note, enqueue=q, review_root=tmp,
                  events_path=ev)
    check("승인 → ok", r["ok"], str(r))
    check("승인 → 원격 main = 끝", sh(tmp / "origin.git", "rev-parse", "main") == end)
    check("승인 → 로컬 main 에 서 있고 = 끝", sh(repo, "rev-parse", "--abbrev-ref", "HEAD") == "main"
          and sh(repo, "rev-parse", "main") == end)
    check("승인 → 로컬 브랜치 삭제", sh(repo, "branch", "--list", "issue/7") == "")
    check("승인 → range 등재 1건", len(q.items) == 1 and q.items[0][1]["kind"] == "range"
          and q.items[0][1]["key"] == f"{base}..{end}"
          and q.items[0][1]["meta"] == {"issue_id": 7, "base": base, "end": end}
          and set(q.items[0][1]["files"]) == {"b.txt", "c.txt"}, str(q.items))
    check("승인 → 사람 요청 우선순위", q.items and q.items[0][1]["priority"] > 0)
    note = iss.notes[-1][0]
    check("승인 → 리뷰 요청 노트(범위 전체 해시·커밋 목록)", f"`{base}..{end}`" in note
          and "add b.txt" in note and "add c.txt" in note and "삭제 실패" not in note, note)
    steps = [json.loads(x)["step"] for x in ev.read_text().splitlines()]
    check("단계 로그", steps[-6:] == ["push", "switch", "ff", "delete_branch", "enqueue", "redmine"]
          and "span" in steps, str(steps))


def t_finish_refusals(tmp):
    repo, iss, base, end = started(tmp)
    (repo / "dirty.txt").write_text("x")
    r = IF.finish(7, confirm=True, repo=repo, noter=iss.note, enqueue=Q(), review_root=tmp)
    check("종료 dirty → 거절", not r["ok"] and r["step"] == "tree", str(r))
    (repo / "dirty.txt").unlink()
    sh(repo, "switch", "-q", "main")
    r = IF.finish(7, confirm=True, repo=repo, noter=iss.note, enqueue=Q(), review_root=tmp)
    check("종료 다른 브랜치 → 거절", not r["ok"] and r["step"] == "branch", str(r))


def t_finish_no_commits(tmp):
    repo = make_repo(tmp)
    iss = Issue(SPEC + PLAN)
    IF.start(7, repo=repo, getter=iss.get, noter=iss.note)
    r = IF.finish(7, confirm=True, repo=repo, noter=iss.note, enqueue=Q(), review_root=tmp)
    check("커밋 0 → 거절", not r["ok"] and r["step"] == "span", str(r))


def t_finish_origin_moved(tmp):
    repo, iss, base, end = started(tmp)
    other = tmp / "other"
    subprocess.run(["git", "clone", "-q", str(tmp / "origin.git"), str(other)], check=True,
                   capture_output=True)
    sh(other, "config", "user.email", "o@o"); sh(other, "config", "user.name", "o")
    (other / "z.txt").write_text("z"); sh(other, "add", "z.txt"); sh(other, "commit", "-q", "-m", "z")
    sh(other, "push", "-q", "origin", "main")
    r = IF.finish(7, confirm=True, repo=repo, noter=iss.note, enqueue=Q(), review_root=tmp)
    check("원격이 앞섬 → 거절(ff 불가 · 강제 없음)", not r["ok"] and r["step"] == "base", str(r))
    check("원격이 앞섬 → 브랜치 그대로", sh(repo, "rev-parse", "issue/7") == end)


def t_finish_push_rejected(tmp):
    repo, iss, base, end = started(tmp)
    hook = tmp / "origin.git" / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 거절 >&2\nexit 1\n")
    hook.chmod(0o755)
    q = Q()
    r = IF.finish(7, confirm=True, repo=repo, noter=iss.note, enqueue=q, review_root=tmp)
    check("push 거절 → ok 아님 · step push", not r["ok"] and r["step"] == "push", str(r))
    check("push 거절 → 로컬 그대로", sh(repo, "rev-parse", "--abbrev-ref", "HEAD") == "issue/7"
          and sh(repo, "rev-parse", "main") == base and not q.items)


def t_finish_enqueue_failure_reported(tmp):
    repo, iss, base, end = started(tmp)
    r = IF.finish(7, confirm=True, repo=repo, noter=iss.note, enqueue=Q(fail=True), review_root=tmp)
    check("등재 실패 → ok 아님 · 사유", not r["ok"] and "리뷰 등재" in r["why"], str(r))
    check("등재 실패 → push 는 이미 됨(되돌리지 않음)", "push" in r["done"]
          and sh(tmp / "origin.git", "rev-parse", "main") == end)
    check("등재 실패 → 노트에 실패 표시", "등재 실패" in iss.notes[-1][0])


def t_git_stderr_not_in_value(tmp):
    """`#881` R218-1 — 성공한 git 의 stderr 는 값에 안 섞인다(GIT_TRACE 로 실제 stderr 를 낸다)."""
    import os
    repo = make_repo(tmp)
    head = sh(repo, "rev-parse", "HEAD")
    os.environ["GIT_TRACE"] = "1"
    try:
        rc, out = IF._git(repo, "rev-parse", "HEAD")
        rc2, dirty = IF._git(repo, "status", "--porcelain")
        iss = Issue(SPEC + PLAN)
        r = IF.start(7, repo=repo, getter=iss.get, noter=iss.note)
    finally:
        os.environ.pop("GIT_TRACE", None)
    check("_git 성공 — 값은 stdout 만(해시 그대로)", rc == 0 and out == head, repr(out[:120]))
    check("_git 성공 — 깨끗한 트리는 빈 문자열", rc2 == 0 and dirty == "", repr(dirty[:120]))
    check("stderr 가 많아도 start 가 깨끗한 트리로 읽는다", r["ok"] and r.get("start_rev") == head, str(r)[:300])
    rc3, why = IF._git(repo, "rev-parse", "--verify", "없는-ref")
    check("_git 실패 — 사유에 stderr", rc3 != 0 and ("없는-ref" in why or "fatal" in why), why)


def main() -> int:
    for fn in (t_plan_needed_refuses, t_no_spec_refuses, t_happy_path,
               t_status_kept_when_not_new, t_dirty_refuses, t_not_on_main_refuses,
               t_ahead_of_origin_refuses, t_existing_branch_elsewhere_refuses,
               t_redmine_failure_rolls_back, t_read_failure,
               t_finish_preview_writes_nothing, t_finish_confirm, t_finish_refusals,
               t_finish_no_commits, t_finish_origin_moved, t_finish_push_rejected,
               t_finish_enqueue_failure_reported, t_git_stderr_not_in_value):
        run(fn)
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_issue_flow: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
