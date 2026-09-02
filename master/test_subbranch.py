"""정본 ⑷ — 조각 서브 브랜치 생성 (사용자 확정 2026-09-02).

**실물 git 저장소를 쓴다** — bare 를 하나 세우고 거기에 밀어 본다. 여기서 지키는 계약은
「명령을 불렀나」가 아니라 **ref 가 실제로 그 커밋에 섰나 · 이미 있는 것을 덮지 않나**이고,
그것은 주입으로는 증명이 안 된다(`~/CLAUDE.md`: *"만들었으면 실물 한 번"*).

`python3 master/test_subbranch.py`
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import branch_names, subbranch                     # noqa: E402

PASS = FAIL = 0
WORK = "20260902_0035_ns_1_ea254ff3"
TASK = "58ff3406"


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def sh(cwd: Path, *args: str) -> str:
    r = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} → rc={r.returncode} {r.stderr[:200]}")
    return r.stdout.strip()


class _Paths:
    """`paths.repo` 만 쓴다 — 실제 `ProjectPaths` 의 그 한 필드를 대신한다."""

    def __init__(self, repo: Path):
        self.repo = repo
        self.name = "T"


def _world(tmp: Path):
    """bare 원격 + 작업 브랜치(골조 커밋 1개)를 가진 미러. `(paths, bare, base_commit)`."""
    bare = tmp / "origin.git"
    bare.mkdir()
    sh(bare, "git", "init", "--bare", "-q", "-b", "main", ".")

    repo = tmp / "mirror"
    repo.mkdir()
    sh(repo, "git", "init", "-q", "-b", "main", ".")
    sh(repo, "git", "config", "user.email", "t@t")
    sh(repo, "git", "config", "user.name", "t")
    (repo / "seed.txt").write_text("main\n", encoding="utf-8")
    sh(repo, "git", "add", "seed.txt")
    sh(repo, "git", "commit", "-q", "-m", "main")
    sh(repo, "git", "remote", "add", "gitea-write", str(bare))
    sh(repo, "git", "push", "-q", "gitea-write", "main")

    # 골조 = 작업 브랜치의 커밋 하나
    base_br = branch_names.base_branch(WORK)
    sh(repo, "git", "checkout", "-q", "-b", "skel")
    (repo / "NSInteract.h").write_text("// [DOC] 골조\n", encoding="utf-8")
    sh(repo, "git", "add", "NSInteract.h")
    sh(repo, "git", "commit", "-q", "-m", "skeleton")
    base = sh(repo, "git", "rev-parse", "HEAD")
    sh(repo, "git", "push", "-q", "gitea-write", f"HEAD:refs/heads/{base_br}")
    sh(repo, "git", "checkout", "-q", "main")
    return _Paths(repo), bare, base


def _heads(bare: Path) -> dict:
    out = sh(bare, "git", "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads")
    return dict(ln.split() for ln in out.splitlines() if ln.strip())


def test_names():
    check("이름은 계층형이다", branch_names.durable_branch(WORK, TASK) == f"task/{WORK}/{TASK}")
    try:
        branch_names.durable_branch(WORK, "base")
        check("[중요] task_id 로 base 는 거절한다", False, "예외가 안 났다")
    except branch_names.BranchNameError:
        check("[중요] task_id 로 base 는 거절한다", True)


def test_create(monkey_guard):
    with tempfile.TemporaryDirectory() as td:
        paths, bare, base = _world(Path(td))
        c = subbranch.create(paths, WORK, TASK, base_commit=base)
        check("신설 성공", c.ok and c.created and not c.existed, f"{c}")
        check("tip 이 골조 커밋이다", c.tip == base, f"{c.tip[:8]} vs {base[:8]}")
        heads = _heads(bare)
        want = f"task/{WORK}/{TASK}"
        check("[중요] 원격에 ref 가 실제로 섰다", heads.get(want) == base, f"{heads}")
        check("[중요] 작업 브랜치에서 갈라졌다 (같은 커밋)",
              heads.get(branch_names.base_branch(WORK)) == base, f"{heads}")


def test_idempotent(monkey_guard):
    with tempfile.TemporaryDirectory() as td:
        paths, bare, base = _world(Path(td))
        subbranch.create(paths, WORK, TASK, base_commit=base)

        # 워커가 그 브랜치에 커밋한 상태를 만든다
        repo = Path(paths.repo)
        sh(repo, "git", "fetch", "-q", "gitea-write", f"refs/heads/task/{WORK}/{TASK}")
        sh(repo, "git", "checkout", "-q", "-B", "wk", "FETCH_HEAD")
        (repo / "NSInteract.cpp").write_text("// 워커 구현\n", encoding="utf-8")
        sh(repo, "git", "add", "NSInteract.cpp")
        sh(repo, "git", "commit", "-q", "-m", "worker impl")
        worker_head = sh(repo, "git", "rev-parse", "HEAD")
        sh(repo, "git", "push", "-q", "gitea-write", f"HEAD:refs/heads/task/{WORK}/{TASK}")
        sh(repo, "git", "checkout", "-q", "main")

        c = subbranch.create(paths, WORK, TASK, base_commit=base)
        check("두 번째 호출은 만들지 않는다", c.ok and c.existed and not c.created, f"{c}")
        check("[중요] **워커 커밋을 덮지 않는다**",
              _heads(bare).get(f"task/{WORK}/{TASK}") == worker_head,
              f"{_heads(bare)}")
        check("tip 으로 워커 커밋을 돌려준다", c.tip == worker_head, c.tip[:8])


def test_refusals(monkey_guard):
    with tempfile.TemporaryDirectory() as td:
        paths, _bare, _base = _world(Path(td))
        c = subbranch.create(paths, WORK, TASK, base_commit="")
        check("[중요] 기준 커밋이 비면 거절한다", not c.ok and "기준 커밋" in c.error, c.error[:80])

        c2 = subbranch.create(paths, WORK, TASK, base_commit="0" * 40)
        check("[중요] 없는 커밋이면 거절한다 (지어내지 않는다)",
              not c2.ok and "기준 커밋" in c2.error, c2.error[:120])
        check("  거절이면 ref 를 만들지 않는다",
              f"task/{WORK}/{TASK}" not in _heads(_bare), f"{_heads(_bare)}")


def test_guard_blocks():
    """[중요] 쓰기 가드가 없으면 **막는다** — fail-closed (`#329`)."""
    with tempfile.TemporaryDirectory() as td:
        paths, bare, base = _world(Path(td))
        orig = subbranch._guard_or_reason
        subbranch._guard_or_reason = lambda p: "[중요] 쓰기 가드가 서 있지 않다 — 테스트"
        try:
            c = subbranch.create(paths, WORK, TASK, base_commit=base)
        finally:
            subbranch._guard_or_reason = orig
        check("가드가 없으면 push 하지 않는다", not c.ok and "가드" in c.error, c.error[:80])
        check("  그리고 ref 도 안 생긴다", f"task/{WORK}/{TASK}" not in _heads(bare))


def test_create_all(monkey_guard):
    with tempfile.TemporaryDirectory() as td:
        paths, bare, base = _world(Path(td))
        rs = subbranch.create_all(paths, WORK, ["aaa1", "bbb2", "base"], base_commit=base)
        check("전수를 돌려준다 (하나 실패해도 멈추지 않는다)", len(rs) == 3, str(len(rs)))
        check("  둘은 성공", sum(1 for r in rs if r.ok) == 2, str([r.ok for r in rs]))
        check("  예약어는 실패로 남는다", not rs[2].ok and "base" in rs[2].error, rs[2].error[:80])
        heads = _heads(bare)
        check("[중요] 조각마다 별개 ref 가 섰다",
              heads.get(f"task/{WORK}/aaa1") == base and heads.get(f"task/{WORK}/bbb2") == base,
              f"{heads}")


def main() -> int:
    # 가드는 실 프로젝트 훅을 보므로 테스트에서는 통과로 둔다 (없을 때는 test_guard_blocks 가 잰다)
    orig = subbranch._guard_or_reason
    subbranch._guard_or_reason = lambda p: ""
    try:
        test_names()
        for fn in (test_create, test_idempotent, test_refusals, test_create_all):
            fn(None)
    finally:
        subbranch._guard_or_reason = orig
    test_guard_blocks()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_subbranch: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
