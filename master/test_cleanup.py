"""워커 찌꺼기 정리 (레드마인 #27).

**SSH 도 git 도 실행하지 않는다** — `runner` 를 주입한다. 지우는 코드라 지키는 계약은
하나로 모인다: 🔴 **커밋이 다른 곳에 살아 있다고 확인한 것만 지우고, 계획 밖은 건드리지 않는다.**

`.venv/bin/python master/test_cleanup.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.client.bundle import HostFacts          # noqa: E402
from master.work import cleanup as C                 # noqa: E402

PASS = FAIL = 0
MERGED = "aaaaaaa1"
UNMERGED = "bbbbbbb2"


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def _facts(host="192.168.0.43", *, os_="linux", path="/home/sim/trunk/ModularStage"):
    f = HostFacts(host=host, user="sim", path=path, driven="ssh", role="worker")
    f.os, f.claude, f.checkout_ok = os_, "2.1", True
    return f


class Fake:
    """워커를 흉내낸다. **부른 명령을 전부 남긴다** — 무엇을 안 불렀는지가 계약이다."""

    def __init__(self, *, branches="", current="main", fetch_rc=0, dirs="",
                 merged=(MERGED,), dirs_rc=0, status="", status_rc=0):
        self.branches, self.current, self.fetch_rc = branches, current, fetch_rc
        self.dirs, self.merged, self.dirs_rc = dirs, set(merged), dirs_rc
        self.status, self.status_rc = status, status_rc
        self.calls = []

    def __call__(self, facts, cmd):
        self.calls.append(cmd)
        if "fetch --prune" in cmd:
            return self.fetch_rc, ("" if self.fetch_rc == 0 else "network down")
        if "branch --show-current" in cmd:
            return 0, self.current
        if "refs/remotes/origin/attempt" in cmd:
            return 0, "origin/attempt/x/y/1\norigin/attempt/x/y/2\n"
        if "for-each-ref" in cmd:
            return 0, self.branches
        if "--is-ancestor" in cmd:
            tip = cmd.split("--is-ancestor ")[1].split()[0]
            if tip == "cccccc3":
                return 128, "fatal: bad object"      # 판정 자체를 못 한 경우
            return (0 if tip in self.merged else 1), ""
        if "status --porcelain" in cmd:
            return self.status_rc, self.status
        if "checkout " in cmd:
            return 0, ""
        if cmd.strip().startswith("ls -1") or "dir /b" in cmd:
            return self.dirs_rc, self.dirs
        if "branch -D" in cmd or "rm -rf" in cmd or "rmdir" in cmd:
            return 0, ""
        return 0, ""

    @property
    def destructive(self):
        return [c for c in self.calls
                if any(k in c for k in ("branch -D", "branch -d", "rm -rf", "rmdir",
                                        "push", "reset", "clean"))]


# ── 브랜치 판정 ──────────────────────────────────────────────────────────────

def test_only_merged_is_deleted() -> None:
    r = Fake(branches=(f"attempt/t1/w/1:{MERGED}\n"
                       f"attempt/t2/w/1:{UNMERGED}\n"
                       f"task/t1:{MERGED}\n"
                       f"main:{MERGED}\n"
                       f"feature/사람작업:{UNMERGED}\n"))
    p = C.survey(_facts(), runner=r)
    names = [n for n, _ in p.delete]
    check("병합된 우리 브랜치만 지운다", sorted(names) == ["attempt/t1/w/1", "task/t1"], str(names))
    # 🔴 사람의 브랜치는 후보조차 아니다
    check("🔴 main·사람 브랜치는 손대지 않는다",
          not any(n in ("main", "feature/사람작업") for n, _ in p.delete + p.keep), str(p.keep))
    check("🔴 미병합은 보존한다", any(n == "attempt/t2/w/1" for n, _ in p.keep), str(p.keep))
    check("보존 사유를 적는다",
          any("병합되지 않았다" in w for _, w in p.keep), str(p.keep))
    check("survey 는 아무것도 지우지 않는다", not r.destructive, str(r.destructive))


def test_format_has_no_space() -> None:
    """🔴 형식 문자열에 공백이 있으면 원격 셸이 쪼갠다 (실측 2026-08-09: 브랜치 0건)."""
    r = Fake(branches=f"attempt/t1/w/1:{MERGED}\n")
    C.survey(_facts(), runner=r)
    fe = [c for c in r.calls if "for-each-ref" in c and "refname" in c and "objectname" in c]
    check("🔴 형식 문자열에 공백이 없다", fe and " " not in fe[0].split("--format=")[1].split()[0],
          str(fe))
    check("두 필드를 다 받는다", fe and "%(objectname)" in fe[0], str(fe))
    # 🔴 %(...) 의 괄호는 POSIX 셸 문법이다 — 감싸지 않으면 리눅스 워커에서 통째로 실패한다
    check("🔴 리눅스는 작은따옴표로 감싼다", "'%(refname:short):%(objectname)'" in fe[0], fe[0])
    w = Fake(); C.survey(_facts("192.168.0.2", os_="windows", path="E:\\x"), runner=w)
    fw = [c for c in w.calls if "for-each-ref" in c and "objectname" in c]
    # cmd 는 작은따옴표를 모른다 — 셸이 다르면 따옴표도 다르다
    check("🔴 윈도우는 큰따옴표로 감싼다", fw and '"%(refname:short):%(objectname)"' in fw[0],
          str(fw))


def test_uncertain_is_kept() -> None:
    """🔴 fail-closed 의 방향은 여기서 **보존**이다."""
    r = Fake(branches=f"attempt/t3/w/1:cccccc3\n")
    p = C.survey(_facts(), runner=r)
    check("🔴 도달 여부를 못 보면 지우지 않는다", not p.delete, str(p.delete))
    check("못 봤다고 적는다", any("확인하지 못했다" in w for _, w in p.keep), str(p.keep))

    # fetch 실패 = origin/main 이 낡았을 수 있다 → 판정 자체를 하지 않는다
    r2 = Fake(branches=f"attempt/t1/w/1:{MERGED}\n", fetch_rc=1)
    p2 = C.survey(_facts(), runner=r2)
    check("🔴 fetch 실패면 아무것도 계획하지 않는다", not p2.delete and p2.errors, p2.summary)
    check("사유를 남긴다", "fetch 실패" in p2.errors[0], str(p2.errors))


def test_current_branch_kept() -> None:
    r = Fake(branches=f"task/t1:{MERGED}\nattempt/t1/w/1:{MERGED}\n", current="task/t1")
    p = C.survey(_facts(), runner=r)
    check("🔴 체크아웃된 브랜치는 지우지 않는다", [n for n, _ in p.delete] == ["attempt/t1/w/1"],
          str(p.delete))
    check("그 사유를 적는다", any("체크아웃" in w for _, w in p.keep), str(p.keep))


def test_never_touches_remote() -> None:
    """🔴 원격 브랜치 삭제는 사람의 판단이다 — 마스터는 세기만 한다."""
    r = Fake(branches=f"attempt/t1/w/1:{MERGED}\n")
    p = C.survey(_facts(), runner=r)
    C.apply(_facts(), p, runner=r)
    check("🔴 push --delete 를 절대 부르지 않는다",
          not any("push" in c for c in r.calls), str([c for c in r.calls if "push" in c]))
    check("🔴 reset·clean 도 부르지 않는다",
          not any(("reset" in c or "clean" in c) for c in r.calls))
    check("원격 attempt 는 세어서 보고만 한다", p.remote_attempts == 2, str(p.remote_attempts))


# ── 부산물 ───────────────────────────────────────────────────────────────────

def test_artifacts() -> None:
    closed = {"aaa": "verified", "bbb": "failed", "ccc": "cancelled", "ddd": "claimed"}
    r = Fake(branches="", dirs="aaa\nbbb\nccc\nddd\neee\n")
    p = C.survey(_facts(), closed=closed, runner=r)
    drop = sorted(t for t, _ in p.drop_dirs)
    check("성공·취소만 지운다", drop == ["aaa", "ccc"], str(drop))
    # 🔴 실패는 왜 실패했는지 볼 유일한 기록이다
    check("🔴 failed 는 남긴다", any(t == "bbb" for t, _ in p.keep_dirs), str(p.keep_dirs))
    check("진행 중도 남긴다", any(t == "ddd" for t, _ in p.keep_dirs))
    check("🔴 큐에 없는 것은 지우지 않는다",
          any(t == "eee" and "모르는 것" in w for t, w in p.keep_dirs), str(p.keep_dirs))

    # closed 를 못 받으면 부산물은 아예 보지 않는다
    p2 = C.survey(_facts(), closed=None, runner=Fake(dirs="aaa\n"))
    check("🔴 큐를 못 읽으면 부산물은 손대지 않는다", not p2.drop_dirs and not p2.keep_dirs)


def test_path_traversal() -> None:
    """🔴 `rm -rf` 를 만드는 코드다 — 이름을 두 번 검사한다."""
    closed = {"../../etc": "verified", "a b; rm -rf /": "verified", "ok1": "verified"}
    r = Fake(dirs="../../etc\na b; rm -rf /\nok1\n")
    p = C.survey(_facts(), closed=closed, runner=r)
    check("🔴 이상한 이름은 후보에서 뺀다", [t for t, _ in p.drop_dirs] == ["ok1"], str(p.drop_dirs))

    # apply 단계에서도 한 번 더 막는다
    p.drop_dirs.append(("../../etc", "verified"))
    r2 = Fake()
    done = C.apply(_facts(), p, runner=r2)
    check("🔴 apply 도 다시 막는다", "ok1" in done["dirs"] and "../../etc" not in done["dirs"],
          str(done))
    check("막았다고 보고한다", any("이상하다" in e for e in done["errors"]), str(done["errors"]))
    check("🔴 위험한 경로로 rm 을 부르지 않았다",
          not any(".." in c for c in r2.calls if "rm -rf" in c), str(r2.calls))


# ── apply 는 계획만 실행한다 ─────────────────────────────────────────────────

def test_apply_follows_plan_only() -> None:
    r = Fake(branches=f"attempt/t1/w/1:{MERGED}\nattempt/t2/w/1:{UNMERGED}\n",
             dirs="aaa\nbbb\n")
    p = C.survey(_facts(), closed={"aaa": "verified", "bbb": "failed"}, runner=r)
    r2 = Fake()
    done = C.apply(_facts(), p, runner=r2)
    check("계획된 브랜치만 지운다", done["branches"] == ["attempt/t1/w/1"], str(done["branches"]))
    check("계획된 부산물만 지운다", done["dirs"] == ["aaa"], str(done["dirs"]))
    # 🔴 보존하기로 한 것이 명령에 등장하면 안 된다
    check("🔴 보존 대상이 명령에 안 나온다",
          not any("t2" in c or "bbb" in c for c in r2.destructive), str(r2.destructive))

    win = C.apply(_facts("192.168.0.2", os_="windows", path="E:\\trunk\\ModularStage"), p,
                  runner=(w := Fake()))
    check("윈도우는 rmdir 를 쓴다", any("rmdir /s /q" in c for c in w.calls), str(w.calls))
    check("윈도우 경로가 역슬래시다", any("E:\\trunk" in c for c in w.calls), str(w.calls))
    check("윈도우도 계획대로만", win["dirs"] == ["aaa"], str(win))



def test_park_to_main() -> None:
    """🔴 우리 브랜치 위에 서 있으면 main 으로 되돌린다 (사용자 결정 2026-08-09)."""
    r = Fake(branches=f"task/t1:{UNMERGED}\nattempt/t1/w/1:{MERGED}\n", current="task/t1")
    p = C.survey(_facts(), runner=r)
    check("🔴 우리 브랜치면 복귀를 계획한다", p.park == "main", p.summary)
    check("survey 단계에선 아직 안 옮긴다",
          not any("checkout " in c for c in r.calls), str(r.calls))

    r2 = Fake()
    done = C.apply(_facts(), p, runner=r2)
    check("apply 가 복귀시킨다", done["parked"] == "main", str(done))
    # 🔴 복귀를 먼저 해야 방금 서 있던 브랜치도 같은 회차에 지울 수 있다
    order = [c for c in r2.calls if "checkout " in c or "branch -D" in c]
    check("🔴 복귀가 삭제보다 먼저다", order and "checkout" in order[0], str(order))

    # ⚠️ 더러우면 되돌리지 않는다 — 체크아웃이 사람의 편집을 건드린다
    dirty = Fake(branches=f"task/t1:{UNMERGED}\n", current="task/t1", status=" M Source/A.cpp\n")
    pd = C.survey(_facts(), runner=dirty)
    check("🔴 Source/ 가 더러우면 되돌리지 않는다", not pd.park, pd.summary)
    check("그 사유를 적는다", any("더럽다" in w for _, w in pd.keep), str(pd.keep))

    # main 위에 있으면 할 일이 없다
    check("main 위면 복귀 안 함", not C.survey(_facts(), runner=Fake(current="main")).park)


def main() -> int:
    for fn in (test_only_merged_is_deleted, test_format_has_no_space, test_uncertain_is_kept, test_current_branch_kept,
               test_never_touches_remote, test_artifacts, test_path_traversal,
               test_apply_follows_plan_only, test_park_to_main):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_cleanup: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
