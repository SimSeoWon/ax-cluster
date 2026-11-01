"""#234 — 옛 2-tier 실행부 제거 뒤 공용 Git 헬퍼의 실제 동작을 검증한다.

임시 로컬 저장소만 사용한다. 커밋 신원 고정·인자 경계·실패 반환 계약은 현행
review/followup/cleanup/revise/attempt가 공유하므로 유지되어야 한다.
실행: .venv/bin/python -B master/test_coordinator.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from master.work import coordinator as C  # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name} — {detail}")


def test_shared_git_contract() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo with spaces"
        repo.mkdir()
        C._git(repo, "init", "-q", "-b", "main")
        C._git(repo, "config", "user.name", "unrelated local identity")
        C._git(repo, "config", "user.email", "unrelated@example.invalid")
        (repo / "한글 file.txt").write_text("내용\n", encoding="utf-8")
        C._git(repo, "add", "--", "한글 file.txt")
        C._git(repo, "commit", "-q", "-m", "probe")
        check("공용 헬퍼 커밋 신원이 로컬 설정과 무관하게 고정된다",
              C._git(repo, "log", "-1", "--format=%an <%ae>") == "ax-cluster <cluster@local>")
        check("공백·한글 경로를 shell 없이 전달한다",
              C._git(repo, "show", "HEAD:한글 file.txt") == "내용")
        rc, out = C._git_rc(repo, "rev-parse", "--verify", "HEAD")
        check("성공 시 rc와 stdout을 반환한다", rc == 0 and len(out) == 40, str((rc, out)))
        rc, out = C._git_rc(repo, "rev-parse", "--verify", "missing-ref")
        check("실패 시 rc와 stderr를 반환한다", rc != 0 and bool(out), str((rc, out)))
        try:
            C._git(repo, "rev-parse", "--verify", "missing-ref")
        except C.GitError as exc:
            check("기본 호출은 GitError로 실패를 드러낸다", "rc=" in str(exc), str(exc))
        else:
            check("기본 호출은 GitError로 실패를 드러낸다", False)
        check("명시적 비차단 호출은 빈 stdout을 반환한다",
              C._git(repo, "rev-parse", "--verify", "missing-ref", check=False) == "")


if __name__ == "__main__":
    test_shared_git_contract()
    print(f"{'OK' if not FAIL else 'FAIL'} test_coordinator: {PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
