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


def main() -> int:
    for fn in (t_plan_needed_refuses, t_no_spec_refuses, t_happy_path,
               t_status_kept_when_not_new, t_dirty_refuses, t_not_on_main_refuses,
               t_ahead_of_origin_refuses, t_existing_branch_elsewhere_refuses,
               t_redmine_failure_rolls_back, t_read_failure):
        run(fn)
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_issue_flow: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
