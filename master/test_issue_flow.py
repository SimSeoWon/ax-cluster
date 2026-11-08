"""일감 작업 흐름(`#879`) 계약 테스트 — [중요] **플랜 없이 시작하지 않는가, 어긋난 기준에서
브랜치를 만들지 않는가, Redmine 기록 실패를 성공으로 보고하지 않는가.**

실 Redmine 을 두드리지 않는다(getter/noter 주입). git 은 임시 디렉토리의 **실제 저장소**와
bare origin 으로 돈다 — 주입한 git 은 계약만 시험한다(CLAUDE.md 「주입은 계약을 시험한다」).
실행: python3 master/test_issue_flow.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import issue_flow as IF    # noqa: E402
from master import issue_lock as IL    # noqa: E402
from master.context_synth import issue_track as IT    # noqa: E402
from master.context_synth import review_queue as RQ   # noqa: E402

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
        self.ratios: list = []

    def get(self, iid):
        return {"id": iid, "subject": "제목", "status": self.status, "description": self.body}

    def note(self, iid, *, notes, status_name="", done_ratio=None):
        self.notes.append((notes, status_name))
        self.ratios.append(done_ratio)
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
    check("단계 로그가 jsonl 에", [x["step"] for x in lines] == ["plan", "lock", "fetch", "base", "branch", "redmine"],
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


def twin(tmp: Path) -> Path:
    """마감 추적·리뷰 큐가 사는 임시 트윈 루트 (`#884` T5 — 운영 트윈을 쓰지 않는다)."""
    return tmp / "twin"


def no_range_items(root: Path) -> bool:
    """`finish` 가 범위 리뷰를 직접 등재하지 않았다 — 큐 파일이 없거나 range 항목 0."""
    try:
        return not [x for x in RQ.items(root) if x.get("kind") == "range"]
    except Exception:                                   # noqa: BLE001
        return True


def _reg_refused(root, n, **kw):
    return {"ok": False, "reason": "bad_sha", "why": "대역 거절"}


def _reg_boom(root, n, **kw):
    raise RuntimeError("추적 파일이 깨졌다")


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
    n0 = len(iss.notes)
    r = IF.finish(7, repo=repo, noter=iss.note, review_root=twin(tmp))
    check("종료 미리보기 → ok · 확인 전", r["ok"] and r["confirmed"] is False, str(r))
    check("미리보기 → 범위", r.get("base") == base and r.get("end") == end and len(r["commits"]) == 2)
    check("미리보기 → 원격 그대로", sh(repo, "rev-parse", "origin/main") == base)
    check("미리보기 → 브랜치·노트·등재 0", sh(repo, "rev-parse", "--abbrev-ref", "HEAD") == "issue/7"
          and len(iss.notes) == n0 and not IT.state_path(twin(tmp)).exists())
    check("미리보기 → next 에 마감 추적 등록", "마감 추적 등록(해시 2개)" in r["next"]
          and "범위 리뷰 등재" not in r["next"], r["next"])


def t_finish_confirm(tmp):
    repo, iss, base, end = started(tmp)
    ev = tmp / "ev.jsonl"
    hashes = sh(repo, "log", "--reverse", "--format=%H", f"{base}..{end}").split()
    r = IF.finish(7, confirm=True, repo=repo, noter=iss.note, review_root=twin(tmp),
                  events_path=ev)
    check("승인 → ok", r["ok"], str(r))
    check("승인 → 원격 main = 끝", sh(tmp / "origin.git", "rev-parse", "main") == end)
    check("승인 → 로컬 main 에 서 있고 = 끝", sh(repo, "rev-parse", "--abbrev-ref", "HEAD") == "main"
          and sh(repo, "rev-parse", "main") == end)
    check("승인 → 로컬 브랜치 삭제", sh(repo, "branch", "--list", "issue/7") == "")
    rnd = IT.current(twin(tmp), 7)
    check("승인 → 마감 추적 라운드 1 · 해시 전부 순서대로", rnd is not None and rnd["round"] == 1
          and [h["sha"] for h in rnd["hashes"]] == hashes and len(hashes) == 2
          and rnd["base"] == base and rnd["end"] == end and rnd["project"] == "AXCluster"
          and all(h["state"] == "waiting" for h in rnd["hashes"]), str(rnd)[:400])
    check("승인 → 등록 by issue_flow.finish", rnd and "by issue_flow.finish" in rnd["history"][-1]["msg"],
          str(rnd and rnd["history"]))
    check("승인 → range 직접 등재 0", no_range_items(twin(tmp)))
    check("승인 → 반환 registered · round", r.get("registered") is True and r.get("round") == 1, str(r)[:300])
    check("#921 승인 → 반환 next = 마감 뒤 명령", "-m master.issue_wrapup " in (r.get("next") or ""),
          str(r.get("next")))
    note = iss.notes[-1][0]
    check("승인 → 리뷰 요청 노트(범위 전체 해시·커밋 목록)", f"`{base}..{end}`" in note
          and "add b.txt" in note and "add c.txt" in note and "삭제 실패" not in note, note)
    check("승인 → 노트에 추적 등록·종합 리뷰", "마감 추적: 라운드 1 에 해시 2개 등록" in note
          and "종합 리뷰 1회" in note and "관문" not in note
          and "리뷰 큐 등재" not in note, note)
    check("승인 → #889 같은 갱신에서 「완료」·100 으로 닫는다", iss.notes[-1][1] == "완료"
          and iss.ratios[-1] == 100 and "일감 상태: 「완료」·100" in note
          and r.get("closed") is True and "close" in r.get("done", []), str((iss.notes[-1][1], iss.ratios[-1], r)))
    check("승인 → 노트에 잠금(대역 = 미사용)", "일감 잠금: 미사용" in note, note)
    steps = [json.loads(x)["step"] for x in ev.read_text().splitlines()]
    core = []
    for x in steps:                     # 같은 단계의 여러 줄(link_round 자체 로그 + 요약)은 하나로
        if x in ("push", "switch", "ff", "delete_branch", "register", "link", "release", "close", "redmine",
                 "enqueue") and (not core or core[-1] != x):
            core.append(x)
    check("단계 로그", core[-7:] == ["push", "switch", "delete_branch", "register", "link", "close",
                                    "redmine"]
          and "span" in steps and "track" in steps and "enqueue" not in steps and "ff" not in steps, str(steps))


def changed_tree(tmp):
    """옛 main과 수정·추가·삭제가 모두 다른 끝 커밋. mtime은 과거로 고정해 재쓰기를 잡는다."""
    repo = make_repo(tmp)
    (repo / "removed.txt").write_text("old\n")
    sh(repo, "add", "removed.txt")
    sh(repo, "commit", "-q", "-m", "base deletion fixture")
    sh(repo, "push", "-q", "origin", "main")
    iss = Issue(SPEC + PLAN)
    IF.start(7, repo=repo, getter=iss.get, noter=iss.note)
    (repo / "a.txt").write_text("new\n")
    (repo / "added.txt").write_text("added\n")
    (repo / "removed.txt").unlink()
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", "modify add delete")
    for name in ("a.txt", "added.txt"):
        os.utime(repo / name, ns=(1_000_000_000, 1_000_000_000))
    return repo, iss, sh(repo, "rev-parse", "HEAD")


def tree_snapshot(repo):
    result = {}
    for name in ("a.txt", "added.txt", "removed.txt"):
        p = repo / name
        result[name] = (p.read_bytes(), p.stat().st_mtime_ns) if p.exists() else None
    return result


def t_finish_tree_never_reverts(tmp):
    """Git은 실제 실행하고 각 명령 직후 작업 트리를 관측한다 (#896)."""
    repo, iss, end = changed_tree(tmp)
    before = tree_snapshot(repo)
    original, observations = IF._git, []

    def observe(cwd, *args):
        answer = original(cwd, *args)
        observations.append((args, tree_snapshot(repo)))
        return answer

    IF._git = observe
    try:
        r = IF.finish(7, confirm=True, repo=repo, noter=iss.note, review_root=twin(tmp))
    finally:
        IF._git = original
    check("#896 finish 성공", r["ok"], str(r))
    check("#896 모든 Git 단계 뒤 수정·추가·삭제 내용과 mtime 불변", bool(observations)
          and all(tree == before for _, tree in observations), str(observations))
    check("#896 main=origin/main=끝 · main 선택", head_of(repo) == "main"
          and sh(repo, "rev-parse", "main") == sh(repo, "rev-parse", "origin/main") == end)


def t_old_finish_sequence_rewrites_tree(tmp):
    """옛 순서의 실물 대조: 중간에 옛 내용, 끝에는 내용 복원·mtime 변경."""
    repo, _, end = changed_tree(tmp)
    before = tree_snapshot(repo)
    sh(repo, "switch", "main")
    middle = tree_snapshot(repo)
    check("#896 대조 — switch 직후 옛 main 내용", middle["a.txt"][0] == b"a\n"
          and middle["added.txt"] is None and middle["removed.txt"][0] == b"old\n")
    sh(repo, "merge", "--ff-only", end)
    after = tree_snapshot(repo)
    check("#896 대조 — ff 뒤 내용 복원", all((value[0] if value else None)
          == (before[name][0] if before[name] else None) for name, value in after.items()))
    check("#896 대조 — 재작성으로 mtime 변경", after["a.txt"][1] != before["a.txt"][1]
          and after["added.txt"][1] != before["added.txt"][1])


def t_finish_main_in_other_worktree(tmp):
    """방어용 가상 조건: 다른 worktree의 main을 덮지 않는다. 운영 장애 재현은 아니다."""
    repo, iss, end = changed_tree(tmp)
    base = sh(repo, "rev-parse", "main")
    other = tmp / "main-worktree"
    sh(repo, "worktree", "add", "-q", str(other), "main")
    before = tree_snapshot(repo)
    other_before = tree_snapshot(other)
    r = IF.finish(7, confirm=True, repo=repo, noter=iss.note, review_root=twin(tmp))
    check("#896 main 점유 방어 — 명시적으로 거절", not r["ok"] and r["step"] == "worktree"
          and str(other) in r["why"], str(r))
    check("#896 main 점유 — main·issue 브랜치·두 트리 보존", head_of(repo) == "issue/7"
          and sh(repo, "rev-parse", "main") == base and sh(repo, "rev-parse", "issue/7") == end
          and tree_snapshot(repo) == before and sh(other, "rev-parse", "HEAD") == base
          and tree_snapshot(other) == other_before)
    check("#896 main 점유 — push·전환·삭제·등록 미실행", not r.get("done")
          and sh(tmp / "origin.git", "rev-parse", "main") == base
          and not IT.state_path(twin(tmp)).exists())


def t_finish_worktree_query_failure(tmp):
    repo, iss, base, end = started(tmp)
    original = IF._git

    def fail_list(cwd, *args):
        return (1, "목록 조회 대역 거절") if args == ("worktree", "list", "--porcelain") else original(cwd, *args)

    IF._git = fail_list
    try:
        r = IF.finish(7, confirm=True, repo=repo, noter=iss.note, review_root=twin(tmp))
    finally:
        IF._git = original
    check("#896 worktree 조회 실패 — 사유 보고", not r["ok"] and r["step"] == "worktree"
          and "목록 조회 대역 거절" in r["why"], str(r))
    check("#896 worktree 조회 실패 — 원격·로컬 참조 보존", head_of(repo) == "issue/7"
          and sh(repo, "rev-parse", "main") == sh(tmp / "origin.git", "rev-parse", "main") == base
          and sh(repo, "rev-parse", "issue/7") == end and not r.get("done"))


def t_finish_switch_failure_preserves_branch(tmp):
    repo, iss, end = changed_tree(tmp)
    base = sh(repo, "rev-parse", "main")
    before = tree_snapshot(repo)
    original = IF._git

    def fail_switch(cwd, *args):
        return (1, "전환 대역 거절") if args == ("switch", "-C", "main", end) else original(cwd, *args)

    IF._git = fail_switch
    try:
        r = IF.finish(7, confirm=True, repo=repo, noter=iss.note, review_root=twin(tmp))
    finally:
        IF._git = original
    check("#896 switch 실패 — 사유 보고", not r["ok"] and "switch: 전환 대역 거절" in r["why"], str(r))
    check("#896 switch 실패 — main 참조·issue 브랜치·트리 보존", head_of(repo) == "issue/7"
          and sh(repo, "rev-parse", "main") == base and sh(repo, "rev-parse", "issue/7") == end
          and tree_snapshot(repo) == before and "switch" not in r["done"]
          and "ff" not in r["done"] and "delete_branch" not in r["done"])


def t_finish_refusals(tmp):
    repo, iss, base, end = started(tmp)
    (repo / "dirty.txt").write_text("x")
    r = IF.finish(7, confirm=True, repo=repo, noter=iss.note, review_root=twin(tmp))
    check("종료 dirty → 거절", not r["ok"] and r["step"] == "tree", str(r))
    (repo / "dirty.txt").unlink()
    sh(repo, "switch", "-q", "main")
    r = IF.finish(7, confirm=True, repo=repo, noter=iss.note, review_root=twin(tmp))
    check("종료 다른 브랜치 → 거절", not r["ok"] and r["step"] == "branch", str(r))


def t_finish_no_commits(tmp):
    repo = make_repo(tmp)
    iss = Issue(SPEC + PLAN)
    IF.start(7, repo=repo, getter=iss.get, noter=iss.note)
    r = IF.finish(7, confirm=True, repo=repo, noter=iss.note, review_root=twin(tmp))
    check("커밋 0 → 거절", not r["ok"] and r["step"] == "span", str(r))


def t_finish_origin_moved(tmp):
    repo, iss, base, end = started(tmp)
    other = tmp / "other"
    subprocess.run(["git", "clone", "-q", str(tmp / "origin.git"), str(other)], check=True,
                   capture_output=True)
    sh(other, "config", "user.email", "o@o"); sh(other, "config", "user.name", "o")
    (other / "z.txt").write_text("z"); sh(other, "add", "z.txt"); sh(other, "commit", "-q", "-m", "z")
    sh(other, "push", "-q", "origin", "main")
    r = IF.finish(7, confirm=True, repo=repo, noter=iss.note, review_root=twin(tmp))
    check("원격이 앞섬 → 거절(ff 불가 · 강제 없음)", not r["ok"] and r["step"] == "base", str(r))
    check("원격이 앞섬 → 브랜치 그대로", sh(repo, "rev-parse", "issue/7") == end)


def t_finish_push_rejected(tmp):
    repo, iss, base, end = started(tmp)
    hook = tmp / "origin.git" / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 거절 >&2\nexit 1\n")
    hook.chmod(0o755)
    r = IF.finish(7, confirm=True, repo=repo, noter=iss.note, review_root=twin(tmp))
    check("push 거절 → ok 아님 · step push", not r["ok"] and r["step"] == "push", str(r))
    check("push 거절 → 로컬 그대로 · 등록 0", sh(repo, "rev-parse", "--abbrev-ref", "HEAD") == "issue/7"
          and sh(repo, "rev-parse", "main") == base and not IT.state_path(twin(tmp)).exists())


def t_finish_register_failure_reported(tmp):
    repo, iss, base, end = started(tmp)
    r = IF.finish(7, confirm=True, repo=repo, noter=iss.note, register=_reg_boom, review_root=twin(tmp))
    check("등록 예외 → ok 아님 · 사유", not r["ok"] and "마감 추적 등록" in r["why"]
          and "RuntimeError" in r["why"] and r.get("registered") is False, str(r))
    check("등록 예외 → push 는 이미 됨(되돌리지 않음)", "push" in r["done"]
          and sh(tmp / "origin.git", "rev-parse", "main") == end)
    check("등록 예외 → 노트에 실패 표시", "마감 추적: 등록 실패" in iss.notes[-1][0]
          and "이어지지 않는다" in iss.notes[-1][0], iss.notes[-1][0])
    check("등록 예외 → link 안 부름 · range 등재 0", "link" not in r["done"] and no_range_items(twin(tmp)))


def t_finish_injected_without_root(tmp):
    """대역 주입 실행이 review_root 를 안 주면 운영 트윈 대신 등록을 하지 않는다(실패로 다룬다)."""
    repo, iss, base, end = started(tmp)
    called = []
    r = IF.finish(7, confirm=True, repo=repo, noter=iss.note,
                  register=lambda *a, **k: called.append(a) or {"ok": True, "round": 1})
    check("review_root 없음 → register 안 부름 · ok 아님", not called and not r["ok"]
          and "review_root" in r["why"], str(r)[:300])


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


def _boom(*a, **k):
    raise ConnectionError("네트워크 끊김")


def t_start_noter_exception_rolls_back(tmp):
    """`#881` R216-4·R218-2 — noter 예외여도 브랜치를 되돌리고 거절로 답한다."""
    repo = make_repo(tmp)
    iss = Issue(SPEC + PLAN)
    r = IF.start(7, repo=repo, getter=iss.get, noter=_boom)
    check("start noter 예외 → ok 아님 · step redmine", not r["ok"] and r["step"] == "redmine"
          and "ConnectionError" in r["why"], str(r)[:300])
    check("start noter 예외 → 브랜치 되돌림", r.get("branch_rolled_back") is True
          and sh(repo, "branch", "--list", "issue/7") == ""
          and sh(repo, "rev-parse", "--abbrev-ref", "HEAD") == "main")


def t_start_getter_exception(tmp):
    repo = make_repo(tmp)
    r = IF.start(7, repo=repo, getter=_boom, noter=lambda *a, **k: "ok")
    check("start getter 예외 → 거절(plan)", not r["ok"] and r["step"] == "plan"
          and "ConnectionError" in r["why"], str(r)[:300])
    check("start getter 예외 → 브랜치 없음", sh(repo, "branch", "--list", "issue/7") == "")


def t_start_status_read_exception_still_records(tmp):
    """판정은 읽혔는데 상태 읽기만 실패 — 기록은 남기고 상태는 안 바꾼다."""
    repo = make_repo(tmp)
    iss = Issue(SPEC + PLAN)
    calls = {"n": 0}

    def flaky(iid):
        calls["n"] += 1
        if calls["n"] > 1:
            raise TimeoutError("느림")
        return iss.get(iid)
    r = IF.start(7, repo=repo, getter=flaky, noter=iss.note)
    check("상태 읽기 예외 → 시작은 성공 · 상태 미변경", r["ok"] and iss.notes and iss.notes[-1][1] == "",
          str(r)[:200])


def t_finish_noter_exception_reports(tmp):
    """`#881` R216-5 — push 뒤 noter 예외여도 done/why 로 돌려준다."""
    repo, iss, base, end = started(tmp)
    r = IF.finish(7, confirm=True, repo=repo, noter=_boom, review_root=twin(tmp))
    check("finish noter 예외 → 결과 딕셔너리 · ok 아님", isinstance(r, dict) and not r["ok"]
          and "ConnectionError" in r["why"], str(r)[:300])
    check("finish noter 예외 → push·삭제·등록은 done", all(x in r["done"] for x in
          ("push", "switch", "delete_branch", "register", "link")) and "redmine" not in r["done"], str(r.get("done")))


def t_start_already_merge_base_failure(tmp):
    """`#881` R216-6 — 기존 브랜치 경로의 merge-base 실패는 거절로 답한다(main 이 없는 저장소)."""
    repo = make_repo(tmp)
    iss = Issue(SPEC + PLAN)
    sh(repo, "switch", "-q", "--orphan", "issue/7")
    (repo / "o.txt").write_text("o"); sh(repo, "add", "o.txt"); sh(repo, "commit", "-q", "-m", "orphan")
    r = IF.start(7, repo=repo, getter=iss.get, noter=iss.note)
    check("기존 브랜치 merge-base 실패 → 거절(branch)", not r["ok"] and r["step"] == "branch"
          and "시작 리비전을 못 구했다" in r["why"], str(r)[:300])


def t_log_unserializable(tmp):
    """`#881` R218-3 — 직렬화 불가 extra 도 흐름을 바꾸지 않는다."""
    ev = tmp / "ev.jsonl"
    log = IF._Log("t", 7, events_path=ev)
    try:
        log("x", "메시지", obj=object())
        ok = True
    except Exception as e:                              # noqa: BLE001
        ok = False
        print(e)
    check("_Log 직렬화 불가 → 예외 없음 · 목록엔 남음", ok and log.lines and "메시지" in log.lines[-1])


# ── `#883` 일감 하나씩 — 잠금 배선 (lock_root 는 늘 임시 디렉토리) ─────────────────

def two(tmp: Path):
    """저장소 하나 + 잠금 + 플랜 있는 일감 둘(7·8)."""
    repo = make_repo(tmp)
    return repo, tmp / "lock", Issue(SPEC + PLAN), Issue(SPEC + PLAN)


def commit(repo: Path, name: str) -> str:
    (repo / name).write_text(name)
    sh(repo, "add", name)
    sh(repo, "commit", "-q", "-m", f"add {name}")
    return sh(repo, "rev-parse", "HEAD")


def head_of(repo):
    return sh(repo, "rev-parse", "--abbrev-ref", "HEAD")


def t_lock_busy_names_holder(tmp):
    repo, lk, a, b = two(tmp)
    r = IF.start(7, repo=repo, getter=a.get, noter=a.note, lock_root=lk)
    check("잠금 — 첫 시작 ok · acquired", r["ok"] and r.get("lock") == "acquired", str(r)[:300])
    check("잠금 — 7 활성", (IL.current(lk) or {}).get("issue_id") == 7)
    check("잠금 — 시작 로그에 lock 줄", any(".lock:" in x for x in r["log"]), str(r["log"]))
    sh(repo, "switch", "-q", "main")
    r = IF.start(8, repo=repo, getter=b.get, noter=b.note, lock_root=lk)
    check("잠금 — 다른 일감 거절(step lock · holder 7)", not r["ok"] and r["step"] == "lock"
          and r.get("holder") == 7 and "#7" in r["why"] and "보류" in r["why"] and "취소" in r["why"], str(r)[:300])
    check("잠금 — 거절 시 브랜치·노트 없음", sh(repo, "branch", "--list", "issue/8") == "" and b.notes == [])


def t_lock_already_on_branch(tmp):
    repo, lk, a, _ = two(tmp)
    IF.start(7, repo=repo, getter=a.get, noter=a.note, lock_root=lk)
    r = IF.start(7, repo=repo, getter=a.get, noter=a.note, lock_root=lk)
    check("잠금 — 같은 일감 재호출 already", r["ok"] and r["already"] and r.get("lock") == "already", str(r)[:300])


def t_legacy_branch_gets_tracked(tmp):
    repo, lk, a, b = two(tmp)
    sh(repo, "switch", "-q", "-c", "issue/7")          # #883 이전에 만든 브랜치(잠금 기록 없음)
    r = IF.start(7, repo=repo, getter=a.get, noter=a.note, lock_root=lk)
    check("옛 브랜치 — 서 있으면 잠금에 올린다", r["ok"] and r.get("lock") == "acquired"
          and IL.is_tracked(lk, 7), str(r)[:300])
    sh(repo, "switch", "-q", "main")
    r = IF.start(7, repo=repo, getter=a.get, noter=a.note, lock_root=lk)
    check("옛 브랜치 — 다른 데 서 있으면 기존 거절(branch)", not r["ok"] and r["step"] == "branch", str(r)[:300])


def t_legacy_branch_busy_refused(tmp):
    repo, lk, a, b = two(tmp)
    IL.acquire(lk, 8, branch="issue/8", start_rev="x")
    sh(repo, "switch", "-q", "-c", "issue/7")
    r = IF.start(7, repo=repo, getter=a.get, noter=a.note, lock_root=lk)
    check("옛 브랜치 — 다른 일감 활성이면 거절", not r["ok"] and r["step"] == "lock" and r.get("holder") == 8, str(r)[:300])


def t_pause_resume_cycle(tmp):
    repo, lk, a, b = two(tmp)
    ev = tmp / "ev.jsonl"
    IF.start(7, repo=repo, getter=a.get, noter=a.note, lock_root=lk)
    end7 = commit(repo, "p.txt")
    r = IF.pause(7, repo=repo, noter=a.note, lock_root=lk, events_path=ev)
    check("보류 — ok", r["ok"] and r["paused"] and r["end"] == end7, str(r)[:300])
    check("보류 — main 에 서 있고 브랜치 유지", head_of(repo) == "main" and sh(repo, "rev-parse", "issue/7") == end7)
    check("보류 — 잠금 비고 7 보류", IL.current(lk) is None and 7 in IL.paused(lk))
    check("보류 — 노트", "보류" in a.notes[-1][0] and "issue_start" in a.notes[-1][0] and a.notes[-1][1] == "",
          str(a.notes[-1]))
    steps = [json.loads(x)["step"] for x in ev.read_text().splitlines()]
    check("보류 — 단계 로그", steps == ["lock", "switch", "redmine"], str(steps))
    # 다른 일감 시작 가능
    r8 = IF.start(8, repo=repo, getter=b.get, noter=b.note, lock_root=lk)
    check("보류 중 다른 일감 시작 ok", r8["ok"] and head_of(repo) == "issue/8", str(r8)[:300])
    sh(repo, "switch", "-q", "main")
    r = IF.start(7, repo=repo, getter=a.get, noter=a.note, lock_root=lk)
    check("8 활성 중 7 재개 거절(busy)", not r["ok"] and r["step"] == "lock" and r.get("holder") == 8, str(r)[:300])
    check("거절 — main 그대로", head_of(repo) == "main")
    IL.release(lk, 8, op="complete")
    n0 = len(a.notes)
    r = IF.start(7, repo=repo, getter=a.get, noter=a.note, lock_root=lk)
    check("재개 — ok · resumed", r["ok"] and r.get("resumed") is True and r.get("lock") == "resumed", str(r)[:300])
    check("재개 — issue/7 로 옮김", head_of(repo) == "issue/7")
    check("재개 — 7 활성", (IL.current(lk) or {}).get("issue_id") == 7 and 7 not in IL.paused(lk))
    check("재개 — 노트 1건 · 상태 안 바꿈", len(a.notes) == n0 + 1 and "재개" in a.notes[-1][0]
          and a.notes[-1][1] == "", str(a.notes[-1]))


def t_resume_note_failure_undoes(tmp):
    repo, lk, a, _ = two(tmp)
    IF.start(7, repo=repo, getter=a.get, noter=a.note, lock_root=lk)
    IF.pause(7, repo=repo, noter=a.note, lock_root=lk)
    bad = Issue(SPEC + PLAN, answer="[주의] 503")
    r = IF.start(7, repo=repo, getter=bad.get, noter=bad.note, lock_root=lk)
    check("재개 노트 실패 → ok 아님 · step redmine", not r["ok"] and r["step"] == "redmine", str(r)[:300])
    check("재개 노트 실패 → main 복귀 · 다시 보류", head_of(repo) == "main" and IL.current(lk) is None
          and 7 in IL.paused(lk) and r.get("relocked") and r.get("switched_back"), str(r)[:300])
    r = IF.start(7, repo=repo, getter=_boom, noter=_boom, lock_root=lk)
    check("재개 — getter 예외는 plan 단계 거절", not r["ok"] and r["step"] == "plan")


def t_resume_dirty_refused(tmp):
    repo, lk, a, _ = two(tmp)
    IF.start(7, repo=repo, getter=a.get, noter=a.note, lock_root=lk)
    IF.pause(7, repo=repo, noter=a.note, lock_root=lk)
    (repo / "x.txt").write_text("x")
    r = IF.start(7, repo=repo, getter=a.get, noter=a.note, lock_root=lk)
    check("재개 dirty → 거절(base) · 보류 유지", not r["ok"] and r["step"] == "base"
          and 7 in IL.paused(lk) and head_of(repo) == "main", str(r)[:300])


def t_pause_refusals(tmp):
    repo, lk, a, _ = two(tmp)
    IF.start(7, repo=repo, getter=a.get, noter=a.note, lock_root=lk)
    (repo / "d.txt").write_text("x")
    n0 = len(a.notes)
    r = IF.pause(7, repo=repo, noter=a.note, lock_root=lk)
    check("보류 dirty → 거절(tree) · 잠금 활성 그대로", not r["ok"] and r["step"] == "tree"
          and (IL.current(lk) or {}).get("issue_id") == 7 and head_of(repo) == "issue/7"
          and len(a.notes) == n0, str(r)[:300])
    (repo / "d.txt").unlink()
    sh(repo, "switch", "-q", "main")
    r = IF.pause(7, repo=repo, noter=a.note, lock_root=lk)
    check("보류 — 브랜치 밖이면 거절(branch)", not r["ok"] and r["step"] == "branch", str(r)[:300])
    sh(repo, "switch", "-q", "-c", "issue/9")
    r = IF.pause(9, repo=repo, noter=a.note, lock_root=lk)
    check("보류 — 잠금 활성 아님 → 거절(lock)", not r["ok"] and r["step"] == "lock" and "활성 일감이 아니다" in r["why"],
          str(r)[:300])
    r = IF.pause(9, repo=repo, noter=a.note)
    check("보류 — 주입 실행에 lock_root 없음 → 거절", not r["ok"] and r["step"] == "lock", str(r)[:300])


def t_pause_note_failure_keeps_paused(tmp):
    repo, lk, a, _ = two(tmp)
    IF.start(7, repo=repo, getter=a.get, noter=a.note, lock_root=lk)
    r = IF.pause(7, repo=repo, noter=_boom, lock_root=lk)
    check("보류 노트 실패 → ok 아님 · 보류는 유지", not r["ok"] and r["step"] == "redmine" and r["paused"]
          and 7 in IL.paused(lk) and head_of(repo) == "main", str(r)[:300])


def t_pause_switch_failure_relocks(tmp):
    repo, lk, a, _ = two(tmp)
    IF.start(7, repo=repo, getter=a.get, noter=a.note, lock_root=lk)
    real = IF._git

    def fake(repo_, *args):
        if args[:2] == ("switch", "main"):
            return 1, "막힘"
        return real(repo_, *args)
    IF._git = fake
    try:
        r = IF.pause(7, repo=repo, noter=a.note, lock_root=lk)
    finally:
        IF._git = real
    check("보류 switch 실패 → 잠금 다시 활성", not r["ok"] and r["step"] == "switch" and r.get("relocked")
          and (IL.current(lk) or {}).get("issue_id") == 7 and 7 not in IL.paused(lk), str(r)[:300])


def t_cancel_preview_and_keep(tmp):
    repo, lk, a, _ = two(tmp)
    IF.start(7, repo=repo, getter=a.get, noter=a.note, lock_root=lk)
    c1 = commit(repo, "k.txt")
    state_before = IL.state_path(lk).read_text()
    n0 = len(a.notes)
    r = IF.cancel(7, repo=repo, noter=a.note, lock_root=lk, delete_branch=True)
    check("취소 미리보기 — ok · 확인 전", r["ok"] and r["confirmed"] is False and r["lock_state"] == "active", str(r)[:300])
    check("취소 미리보기 — 로컬 전용 커밋 · [중요] 경고", r["local_only"] == [c1] and len(r["commits"]) == 1
          and r["warning"].startswith("[중요]") and "되살릴 수 없다" in r["warning"], str(r)[:400])
    check("취소 미리보기 — 쓰기 0", IL.state_path(lk).read_text() == state_before and len(a.notes) == n0
          and head_of(repo) == "issue/7" and sh(repo, "rev-parse", "issue/7") == c1)
    check("취소 미리보기 — 무엇을 할지", "branch -D" in r["next"] and "main" in r["next"], r["next"])
    r = IF.cancel(7, confirm=True, repo=repo, noter=a.note, lock_root=lk)
    check("취소 승인(기본) — ok · 브랜치 유지", r["ok"] and r["branch_deleted"] is False
          and sh(repo, "rev-parse", "issue/7") == c1, str(r)[:300])
    check("취소 승인 — 브랜치에서 main 으로", head_of(repo) == "main" and "switch" in r["done"])
    check("취소 승인 — 잠금 해제", not IL.is_tracked(lk, 7) and IL.current(lk) is None)
    check("취소 승인 — 노트(커밋 목록 · 유지)", "취소" in a.notes[-1][0] and c1[:12] in a.notes[-1][0]
          and "유지" in a.notes[-1][0], a.notes[-1][0])
    # 잠금 없음 + 브랜치 있음 → 옛 브랜치로 받아 삭제
    r = IF.cancel(7, confirm=True, delete_branch=True, repo=repo, noter=a.note, lock_root=lk)
    check("취소 — 잠금 없는 옛 브랜치 + delete_branch → 삭제", r["ok"] and r["lock_state"] == "absent"
          and r["branch_deleted"] and sh(repo, "branch", "--list", "issue/7") == "", str(r)[:300])
    r = IF.cancel(7, repo=repo, noter=a.note, lock_root=lk)
    check("취소 — 잠금·브랜치 둘 다 없음 → 거절", not r["ok"] and r["step"] == "lock", str(r)[:300])


def t_cancel_paused_delete(tmp):
    repo, lk, a, _ = two(tmp)
    IF.start(7, repo=repo, getter=a.get, noter=a.note, lock_root=lk)
    commit(repo, "q.txt")
    IF.pause(7, repo=repo, noter=a.note, lock_root=lk)
    r = IF.cancel(7, confirm=True, delete_branch=True, repo=repo, noter=a.note, lock_root=lk)
    check("보류 일감 취소 + 삭제", r["ok"] and r["lock_state"] == "paused" and r["branch_deleted"]
          and sh(repo, "branch", "--list", "issue/7") == "" and not IL.is_tracked(lk, 7)
          and "switch" not in r["done"], str(r)[:300])
    check("삭제 기록 — 노트에 삭제", "삭제" in a.notes[-1][0])


def t_cancel_dirty_and_note_failure(tmp):
    repo, lk, a, _ = two(tmp)
    IF.start(7, repo=repo, getter=a.get, noter=a.note, lock_root=lk)
    commit(repo, "w.txt")
    (repo / "dd.txt").write_text("x")
    r = IF.cancel(7, confirm=True, repo=repo, noter=a.note, lock_root=lk)
    check("취소 dirty → 거절(tree) · 잠금 그대로", not r["ok"] and r["step"] == "tree" and IL.is_tracked(lk, 7), str(r)[:300])
    (repo / "dd.txt").unlink()
    r = IF.cancel(7, confirm=True, delete_branch=True, repo=repo, noter=_boom, lock_root=lk)
    check("취소 노트 실패 → 브랜치 안 지움", not r["ok"] and r["step"] == "redmine" and not r["branch_deleted"]
          and sh(repo, "branch", "--list", "issue/7") != "" and "release" in r["done"], str(r)[:300])


def t_finish_lock_rules(tmp):
    repo, lk, a, b = two(tmp)
    IF.start(7, repo=repo, getter=a.get, noter=a.note, lock_root=lk)
    commit(repo, "f.txt")
    IF.pause(7, repo=repo, noter=a.note, lock_root=lk)
    sh(repo, "switch", "-q", "issue/7")                 # 사람이 손으로 옮겼다
    r = IF.finish(7, repo=repo, noter=a.note, review_root=twin(tmp), lock_root=lk)
    check("finish — 보류 중이면 거절(lock)", not r["ok"] and r["step"] == "lock" and "재개" in r["why"], str(r)[:300])
    sh(repo, "switch", "-q", "main")
    IF.start(8, repo=repo, getter=b.get, noter=b.note, lock_root=lk)
    sh(repo, "switch", "-q", "issue/7")
    IL.release(lk, 7, op="cancel")
    r = IF.finish(7, repo=repo, noter=a.note, review_root=twin(tmp), lock_root=lk)
    check("finish — 다른 일감 활성이면 거절", not r["ok"] and r["step"] == "lock" and r.get("holder") == 8, str(r)[:300])


def t_finish_releases_lock_and_legacy(tmp):
    repo, lk, a, _ = two(tmp)
    IF.start(7, repo=repo, getter=a.get, noter=a.note, lock_root=lk)
    g = commit(repo, "g.txt")
    r = IF.finish(7, confirm=True, repo=repo, noter=a.note, review_root=twin(tmp), lock_root=lk)
    check("finish 승인 — ok · 잠금 해제(#884 T5)", r["ok"] and IL.current(lk) is None
          and not IL.is_tracked(lk, 7) and r.get("lock_released") is True and "release" in r["done"],
          str(r)[:300])
    hist = IL._load(lk)["history"][-1]
    check("finish 승인 — 잠금 이력 op=finish · by issue_flow.finish",
          hist["op"] == "finish" and hist["by"] == "issue_flow.finish", str(hist))
    check("finish 승인 — 등록 뒤 해제 순서", r["done"].index("register") < r["done"].index("release")
          < r["done"].index("redmine"), str(r["done"]))
    check("finish 승인 — 노트에 잠금 해제", "일감 잠금: 해제(finish)" in a.notes[-1][0], a.notes[-1][0])
    rnd = IT.current(twin(tmp), 7)
    check("finish 승인 — 해시 등록", rnd and [h["sha"] for h in rnd["hashes"]] == [g], str(rnd)[:300])
    # 다음 일감을 곧바로 시작할 수 있다
    r8 = IF.start(8, repo=repo, getter=a.get, noter=a.note, lock_root=lk, fetch=False)
    check("finish 뒤 — 다른 일감 시작 가능", r8["ok"] and (IL.current(lk) or {}).get("issue_id") == 8, str(r8)[:300])
    sh(repo, "switch", "-q", "main")
    IL.release(lk, 8, op="cancel")
    sh(repo, "branch", "-D", "issue/8")
    # 옛 시작(잠금 기록 없음)
    lk2 = tmp / "lock2"
    sh(repo, "switch", "-q", "-c", "issue/9")
    commit(repo, "h.txt")
    r = IF.finish(9, repo=repo, noter=a.note, review_root=twin(tmp), lock_root=lk2)
    check("finish — 잠금 기록 없음 → [주의] 로그 · 진행", r["ok"] and any("잠금 기록 없음" in x for x in r["log"]),
          str(r)[:300])


def t_finish_register_failure_keeps_lock(tmp):
    """등록이 실패하면 잠금을 풀지 않는다 — 리뷰가 이어지지 않은 채 다음으로 가지 않게."""
    repo, lk, a, _ = two(tmp)
    IF.start(7, repo=repo, getter=a.get, noter=a.note, lock_root=lk)
    commit(repo, "k.txt")
    r = IF.finish(7, confirm=True, repo=repo, noter=a.note, register=_reg_refused,
                  review_root=twin(tmp), lock_root=lk)
    check("등록 거절 → ok 아님 · 잠금 유지", not r["ok"] and IL.is_tracked(lk, 7)
          and "release" not in r["done"] and r.get("lock_released") is False, str(r)[:300])
    check("등록 거절 → 사유(reason)", "bad_sha" in r["why"], r["why"])
    note = a.notes[-1][0]
    check("등록 거절 → 노트: 등록 실패 · 잠금 유지", "마감 추적: 등록 실패 — bad_sha" in note
          and "일감 잠금: 유지" in note, note)
    check("등록 거절 → push·삭제는 됨", all(x in r["done"] for x in ("push", "switch", "delete_branch")))


def t_finish_link_failure_still_releases(tmp):
    """연결 실패는 다음 동기화 회차가 잇는다 — 등록이 됐으면 잠금은 푼다(problems 에는 적는다)."""
    repo, lk, a, _ = two(tmp)
    IF.start(7, repo=repo, getter=a.get, noter=a.note, lock_root=lk)
    commit(repo, "l.txt")
    r = IF.finish(7, confirm=True, repo=repo, noter=a.note, review_root=twin(tmp), lock_root=lk,
                  link=lambda root, n, **k: (_ for _ in ()).throw(OSError("큐 파일")))
    check("연결 예외 → ok 아님 · 사유", not r["ok"] and "리뷰 연결" in r["why"] and "OSError" in r["why"], str(r)[:300])
    check("연결 예외 → 등록됨 · 잠금 해제", r.get("registered") and not IL.is_tracked(lk, 7)
          and "release" in r["done"], str(r)[:300])


def t_finish_link_picks_existing_items(tmp):
    """색인기가 등록 전에 이미 넣은 commit 항목을 link_round 가 줍는다(실배선 · 임시 큐)."""
    repo, iss, base, end = started(tmp)
    hashes = sh(repo, "log", "--reverse", "--format=%H", f"{base}..{end}").split()
    root = twin(tmp)
    RQ.enqueue(root, key=hashes[0], files=["b.txt"])
    r = IF.finish(7, confirm=True, repo=repo, noter=iss.note, review_root=root)
    rnd = IT.current(root, 7)
    st = {h["sha"]: h["state"] for h in rnd["hashes"]}
    item = next(x for x in RQ.items(root) if x["id"] == f"commit:{hashes[0]}")
    check("기존 항목 → queued · 우선순위 10", r["ok"] and st[hashes[0]] == "queued"
          and st[hashes[1]] == "waiting" and item["priority"] == 10, f"{st} {item.get('priority')} {r.get('why')}")
    check("기존 항목 → range 등재 0", no_range_items(root))


def t_new_branch_acquire_race_rolls_back(tmp):
    repo, lk, a, _ = two(tmp)

    class Racer(Issue):
        def note(self, iid, *, notes, status_name="", done_ratio=None):
            IL.acquire(lk, 99, branch="issue/99", start_rev="r")      # 노트 사이에 다른 일감이 잡았다
            return super().note(iid, notes=notes, status_name=status_name, done_ratio=done_ratio)
    rr = Racer(SPEC + PLAN)
    r = IF.start(7, repo=repo, getter=rr.get, noter=rr.note, lock_root=lk)
    check("경합 — ok 아님 · step lock · holder 99", not r["ok"] and r["step"] == "lock" and r.get("holder") == 99, str(r)[:300])
    check("경합 — 브랜치 되돌림 · 노트 기록됨을 알린다", r.get("branch_rolled_back") and head_of(repo) == "main"
          and sh(repo, "branch", "--list", "issue/7") == "" and "이미 기록됐다" in r["why"], str(r)[:300])


def t_paused_without_branch_refused(tmp):
    repo, lk, a, _ = two(tmp)
    IL.acquire(lk, 7, branch="issue/7", start_rev="r")
    IL.pause(lk, 7)
    r = IF.start(7, repo=repo, getter=a.get, noter=a.note, lock_root=lk)
    check("보류 기록만 있고 브랜치 없음 → 거절(lock)", not r["ok"] and r["step"] == "lock"
          and "issue_cancel" in r["why"] and sh(repo, "branch", "--list", "issue/7") == "", str(r)[:300])


def t_corrupt_lock_refuses(tmp):
    repo, lk, a, _ = two(tmp)
    lk.mkdir()
    IL.state_path(lk).write_text("{깨짐")
    r = IF.start(7, repo=repo, getter=a.get, noter=a.note, lock_root=lk)
    check("깨진 잠금 → 거절(lock) · 브랜치 없음", not r["ok"] and r["step"] == "lock"
          and sh(repo, "branch", "--list", "issue/7") == "", str(r)[:300])


def t_default_repo_is_operational_checkout(tmp):
    """`#906` — 기본 작업 저장소는 이 모듈이 든 운영 저장소다. 색인 미러(`track.local_clone`)가 아니다."""
    here = Path(IF.__file__).resolve().parent.parent
    check("#906 기본 repo = 운영 저장소(REPO)", IF.default_repo() == here == IF.REPO, str(IF.default_repo()))
    src = Path(IF.__file__).read_text(encoding="utf-8")
    check("#906 기본 repo 가 track.local_clone 을 해석하지 않는다",
          'resolve("AXCluster").repo' not in src.split("def default_repo", 1)[1].split("\ndef ", 1)[0])


def _seal(repo: Path) -> None:
    sh(repo, "remote", "set-url", "--push", "origin", "DISABLED://마스터는-소스저장소에-push하지-않는다")


def t_sealed_repo_start_refused(tmp):
    """`#906` — 색인 미러처럼 origin push 가 봉인된 저장소에는 일감 브랜치를 세우지 않는다."""
    repo = make_repo(tmp)
    _seal(repo)
    iss = Issue(SPEC + PLAN)
    r = IF.start(7, repo=repo, getter=iss.get, noter=iss.note)
    check("#906 봉인 저장소 start → 거절(repo)", not r["ok"] and r["step"] == "repo"
          and "봉인" in r["why"], str(r)[:300])
    check("#906 봉인 저장소 start → 브랜치·노트 없음 · main 유지",
          sh(repo, "branch", "--list", "issue/7") == "" and iss.notes == []
          and sh(repo, "rev-parse", "--abbrev-ref", "HEAD") == "main")


def t_sealed_repo_finish_refused(tmp):
    """`#906` — 봉인된 저장소에서 마감하면 push 를 시도하기 전에 멈춘다(브랜치·커밋 보존)."""
    repo, iss, base, end = started(tmp)
    _seal(repo)
    n0 = len(iss.notes)
    r = IF.finish(7, repo=repo, confirm=True, noter=iss.note, review_root=twin(tmp))
    check("#906 봉인 저장소 finish → 거절(repo) · push 시도 없음", not r["ok"] and r["step"] == "repo"
          and "봉인" in r["why"] and not r.get("done"), str(r)[:300])
    check("#906 봉인 저장소 finish → 브랜치·원격·노트 그대로",
          sh(repo, "rev-parse", "issue/7") == end and sh(repo, "rev-parse", "origin/main") == base
          and len(iss.notes) == n0)


# ── `#907` worktree 방식 — 운영 저장소는 늘 main ─────────────────────────────────

def _wt_setup(tmp: Path):
    repo, lk, a, b = two(tmp)
    sh(repo, "config", "core.excludesFile", "/dev/null")
    return repo, lk, a, b, tmp / "wt"


def t_wt_full_cycle(tmp):
    """시작 → worktree 에서 커밋 → 보류(worktree 제거·브랜치 유지) → 재개 → 마감(운영 main ff·정리)."""
    repo, lk, a, _, root = _wt_setup(tmp)
    head = sh(repo, "rev-parse", "HEAD")
    r = IF.start(7, repo=repo, worktree_root=root, getter=a.get, noter=a.note, lock_root=lk)
    wt = root / "7"
    check("#907 start → ok · 응답 repo = worktree · checkout = 운영", r["ok"] and r["repo"] == str(wt)
          and r["checkout"] == str(repo) and r["start_rev"] == head, str(r)[:300])
    check("#907 start → 운영 저장소는 main 그대로", head_of(repo) == "main")
    check("#907 start → worktree 는 issue/7", head_of(wt) == "issue/7")
    r2 = IF.start(7, repo=repo, worktree_root=root, getter=a.get, noter=a.note, lock_root=lk)
    check("#907 재호출 → already · 같은 worktree", r2["ok"] and r2["already"] and r2["repo"] == str(wt), str(r2)[:300])
    sh(wt, "config", "user.email", "t@t")
    sh(wt, "config", "user.name", "t")
    end = commit(wt, "w.txt")
    check("#907 worktree 커밋이 운영 작업 트리에 안 나타난다", not (repo / "w.txt").exists())
    (wt / "dirty.txt").write_text("x")
    r = IF.pause(7, repo=repo, worktree_root=root, noter=a.note, lock_root=lk)
    check("#907 dirty worktree 보류 → 거절(tree) · worktree 유지", not r["ok"] and r["step"] == "tree"
          and wt.exists(), str(r)[:300])
    (wt / "dirty.txt").unlink()
    r = IF.pause(7, repo=repo, worktree_root=root, noter=a.note, lock_root=lk)
    check("#907 보류 → worktree 제거 · 브랜치 유지 · 7 보류", r["ok"] and not wt.exists()
          and sh(repo, "rev-parse", "issue/7") == end and 7 in IL.paused(lk), str(r)[:300])
    r = IF.start(7, repo=repo, worktree_root=root, getter=a.get, noter=a.note, lock_root=lk)
    check("#907 재개 → worktree 다시 · issue/7 끝 커밋", r["ok"] and r.get("resumed") and head_of(wt) == "issue/7"
          and sh(wt, "rev-parse", "HEAD") == end, str(r)[:300])
    pv = IF.finish(7, repo=repo, worktree_root=root, noter=a.note, review_root=twin(tmp), lock_root=lk)
    check("#907 finish 미리보기 → repo=worktree · next 에 운영 main ff", pv["ok"] and pv["repo"] == str(wt)
          and "운영 main fast-forward" in pv["next"], str(pv)[:400])
    r = IF.finish(7, repo=repo, worktree_root=root, confirm=True, noter=a.note, review_root=twin(tmp), lock_root=lk)
    check("#907 finish → push·ff·worktree 제거·브랜치 삭제", r["ok"] and r["done"][:4] == ["push", "ff",
          "worktree_remove", "delete_branch"], str(r)[:400])
    check("#907 finish → 운영 main = origin/main = 끝 커밋 · 파일 반영", head_of(repo) == "main"
          and sh(repo, "rev-parse", "HEAD") == end == sh(repo, "rev-parse", "origin/main")
          and (repo / "w.txt").exists())
    check("#907 finish → worktree·브랜치 없음 · 잠금 해제", not wt.exists()
          and sh(repo, "branch", "--list", "issue/7") == "" and IL.current(lk) is None)


def t_wt_refusals(tmp):
    repo, lk, a, _, root = _wt_setup(tmp)
    sh(repo, "switch", "-q", "-c", "side")
    r = IF.start(7, repo=repo, worktree_root=root, getter=a.get, noter=a.note, lock_root=lk)
    check("#907 운영 저장소가 main 아님 → 거절(base) · worktree 없음", not r["ok"] and r["step"] == "base"
          and not (root / "7").exists(), str(r)[:300])
    sh(repo, "switch", "-q", "main")
    (root / "7").mkdir(parents=True)
    r = IF.start(7, repo=repo, worktree_root=root, getter=a.get, noter=a.note, lock_root=lk)
    check("#907 같은 자리에 다른 폴더 → 거절(worktree) · 덮지 않음", not r["ok"] and r["step"] == "worktree",
          str(r)[:300])
    (root / "7").rmdir()
    _seal(repo)
    r = IF.start(7, repo=repo, worktree_root=root, getter=a.get, noter=a.note, lock_root=lk)
    check("#907 봉인 저장소 → 거절(repo)", not r["ok"] and r["step"] == "repo", str(r)[:300])


def t_wt_redmine_failure_undoes(tmp):
    repo, lk, _, _, root = _wt_setup(tmp)
    bad = Issue(SPEC + PLAN, answer="[주의] 레드마인 실패")
    r = IF.start(7, repo=repo, worktree_root=root, getter=bad.get, noter=bad.note, lock_root=lk)
    check("#907 기록 실패 → worktree·브랜치 되돌림", not r["ok"] and r["step"] == "redmine"
          and r.get("branch_rolled_back") and not (root / "7").exists()
          and sh(repo, "branch", "--list", "issue/7") == "", str(r)[:300])


def t_wt_cancel_removes_worktree(tmp):
    repo, lk, a, _, root = _wt_setup(tmp)
    IF.start(7, repo=repo, worktree_root=root, getter=a.get, noter=a.note, lock_root=lk)
    pv = IF.cancel(7, repo=repo, worktree_root=root, noter=a.note, lock_root=lk)
    check("#907 취소 미리보기 → worktree 제거 예고 · 쓰기 0", pv["ok"] and pv["worktree"] == str(root / "7")
          and "worktree" in pv["next"] and (root / "7").exists(), str(pv)[:300])
    r = IF.cancel(7, repo=repo, worktree_root=root, confirm=True, delete_branch=True, noter=a.note, lock_root=lk)
    check("#907 취소 → worktree 제거·브랜치 삭제·운영 main", r["ok"] and not (root / "7").exists()
          and sh(repo, "branch", "--list", "issue/7") == "" and head_of(repo) == "main", str(r)[:300])


def _ws_project(tmp: Path, body: str, kind: str = "code") -> Path:
    """운영 호출 판정용 가짜 프로젝트 루트 — config.yaml·profile."""
    root = tmp / "projroot"
    (root / "P").mkdir(parents=True)
    (root / "projects.yaml").write_text("version: 1\nactive: P\nprojects:\n- P\n", encoding="utf-8")
    (root / "P" / "config.yaml").write_text("version: 1\nname: P\n" + body, encoding="utf-8")
    return root


def t_workspace_operational_refusals(tmp):
    """운영 호출(repo 미지정)은 config 의 master_workspace 가 정한다 — 추정 없이 거절."""
    saved = os.environ.get("AX_PROJECTS_ROOT")
    try:
        for body, want, label in (
            ("requester: master\n", "issue_worktree_root 가 없다", "값 없음"),
            ("", "requester: master", "요청자가 .33(게임 경로)"),
        ):
            sub = tmp / label.replace(" ", "_").replace("(", "").replace(")", "").replace(".", "")
            sub.mkdir()
            os.environ["AX_PROJECTS_ROOT"] = str(_ws_project(sub, body))
            _, wt_root, why = IF._workspace(None, None, "P")
            check(f"#907 운영 호출 {label} → 거절", wt_root is None and want in why, why)
        sub = tmp / "mirror"
        sub.mkdir()
        root = _ws_project(sub, "")
        mirror = root / "P" / "repo"
        (root / "P" / "config.yaml").write_text(
            f"version: 1\nname: P\nrequester: master\nmaster_workspace:\n  issue_worktree_root: {mirror}/x\n",
            encoding="utf-8")
        os.environ["AX_PROJECTS_ROOT"] = str(root)
        _, wt_root, why = IF._workspace(None, None, "P")
        check("#907 운영 호출 색인 미러 안 경로 → 거절", wt_root is None and "색인 미러" in why, why)
        sub = tmp / "okws"
        sub.mkdir()
        os.environ["AX_PROJECTS_ROOT"] = str(_ws_project(
            sub, "requester: master\nmaster_workspace:\n  issue_worktree_root: /srv/ws\n"))
        repo, wt_root, why = IF._workspace(None, None, "P")
        check("#907 운영 호출 master 프로젝트 → 운영 저장소 + 설정 경로", not why and wt_root == Path("/srv/ws")
              and repo == IF.REPO, f"{repo} {wt_root} {why}")
        r = IF.start(7, getter=Issue(SPEC + PLAN).get, noter=Issue(SPEC + PLAN).note, project="NOPE")
        check("#907 운영 호출 설정 없음 → start 거절(workspace) · git 미접촉", not r["ok"] and r["step"] == "workspace",
              str(r)[:300])
    finally:
        if saved is None:
            os.environ.pop("AX_PROJECTS_ROOT", None)
        else:
            os.environ["AX_PROJECTS_ROOT"] = saved


def _no_real_twin(*a, **k):
    raise AssertionError("테스트가 운영 잠금 위치(default_root)를 불렀다")


def main() -> int:
    IL.default_root = _no_real_twin       # 대역 실행은 실 트윈 잠금을 절대 건드리지 않는다
    for fn in (t_plan_needed_refuses, t_no_spec_refuses, t_happy_path,
               t_status_kept_when_not_new, t_dirty_refuses, t_not_on_main_refuses,
               t_ahead_of_origin_refuses, t_existing_branch_elsewhere_refuses,
               t_redmine_failure_rolls_back, t_read_failure,
               t_finish_preview_writes_nothing, t_finish_confirm, t_finish_refusals,
               t_finish_tree_never_reverts, t_old_finish_sequence_rewrites_tree,
               t_finish_main_in_other_worktree, t_finish_worktree_query_failure,
               t_finish_switch_failure_preserves_branch,
               t_finish_no_commits, t_finish_origin_moved, t_finish_push_rejected,
               t_finish_register_failure_reported, t_finish_injected_without_root,
               t_git_stderr_not_in_value,
               t_start_noter_exception_rolls_back, t_start_getter_exception,
               t_start_status_read_exception_still_records, t_finish_noter_exception_reports,
               t_start_already_merge_base_failure, t_log_unserializable,
               t_lock_busy_names_holder, t_lock_already_on_branch, t_legacy_branch_gets_tracked,
               t_legacy_branch_busy_refused, t_pause_resume_cycle, t_resume_note_failure_undoes,
               t_resume_dirty_refused, t_pause_refusals, t_pause_note_failure_keeps_paused,
               t_pause_switch_failure_relocks, t_cancel_preview_and_keep, t_cancel_paused_delete,
               t_cancel_dirty_and_note_failure, t_finish_lock_rules, t_finish_releases_lock_and_legacy,
               t_finish_register_failure_keeps_lock, t_finish_link_failure_still_releases,
               t_finish_link_picks_existing_items,
               t_new_branch_acquire_race_rolls_back, t_paused_without_branch_refused,
               t_corrupt_lock_refuses, t_default_repo_is_operational_checkout,
               t_sealed_repo_start_refused, t_sealed_repo_finish_refused,
               t_wt_full_cycle, t_wt_refusals, t_wt_redmine_failure_undoes, t_wt_cancel_removes_worktree,
               t_workspace_operational_refusals):
        run(fn)
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_issue_flow: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
