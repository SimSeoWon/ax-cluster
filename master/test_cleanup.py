"""워커 찌꺼기 정리 (레드마인 #27).

**SSH 도 git 도 실행하지 않는다** — `runner` 를 주입한다. 지우는 코드라 지키는 계약은
하나로 모인다: [중요] **커밋이 다른 곳에 살아 있다고 확인한 것만 지우고, 계획 밖은 건드리지 않는다.**

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
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _facts(host="192.168.0.43", *, os_="linux", path="/home/sim/trunk/ModularStage"):
    f = HostFacts(host=host, user="sim", path=path, driven="ssh", role="worker")
    f.os, f.claude, f.checkout_ok = os_, "2.1", True
    return f


class Fake:
    """워커를 흉내낸다. **부른 명령을 전부 남긴다** — 무엇을 안 불렀는지가 계약이다."""

    def __init__(self, *, branches="", current="main", fetch_rc=0, dirs="",
                 merged=(MERGED,), dirs_rc=0, status="", status_rc=0, behind=0, ahead=0, lag_rc=0):
        self.behind, self.ahead, self.lag_rc = behind, ahead, lag_rc
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
        if "rev-list --count" in cmd:                 # `#333` ⓒ — main..origin/main · origin/main..main
            if self.lag_rc:
                return self.lag_rc, "fatal"
            return 0, str(self.behind if ".." in cmd and cmd.split("rev-list --count ")[1].startswith("main..") else self.ahead)
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
    # [중요] 사람의 브랜치는 후보조차 아니다
    check("[중요] main·사람 브랜치는 손대지 않는다",
          not any(n in ("main", "feature/사람작업") for n, _ in p.delete + p.keep), str(p.keep))
    check("[중요] 미병합은 보존한다", any(n == "attempt/t2/w/1" for n, _ in p.keep), str(p.keep))
    check("보존 사유를 적는다",
          any("병합되지 않았다" in w for _, w in p.keep), str(p.keep))
    check("survey 는 아무것도 지우지 않는다", not r.destructive, str(r.destructive))


def test_format_has_no_space() -> None:
    """[중요] 형식 문자열에 공백이 있으면 원격 셸이 쪼갠다 (실측 2026-08-09: 브랜치 0건)."""
    r = Fake(branches=f"attempt/t1/w/1:{MERGED}\n")
    C.survey(_facts(), runner=r)
    fe = [c for c in r.calls if "for-each-ref" in c and "refname" in c and "objectname" in c]
    check("[중요] 형식 문자열에 공백이 없다", fe and " " not in fe[0].split("--format=")[1].split()[0],
          str(fe))
    check("두 필드를 다 받는다", fe and "%(objectname)" in fe[0], str(fe))
    # [중요] %(...) 의 괄호는 POSIX 셸 문법이다 — 감싸지 않으면 리눅스 워커에서 통째로 실패한다
    check("[중요] 리눅스는 작은따옴표로 감싼다", "'%(refname:short):%(objectname)'" in fe[0], fe[0])
    w = Fake(); C.survey(_facts("192.168.0.2", os_="windows", path="E:\\x"), runner=w)
    fw = [c for c in w.calls if "for-each-ref" in c and "objectname" in c]
    # cmd 는 작은따옴표를 모른다 — 셸이 다르면 따옴표도 다르다
    check("[중요] 윈도우는 큰따옴표로 감싼다", fw and '"%(refname:short):%(objectname)"' in fw[0],
          str(fw))


def test_uncertain_is_kept() -> None:
    """[중요] fail-closed 의 방향은 여기서 **보존**이다."""
    r = Fake(branches=f"attempt/t3/w/1:cccccc3\n")
    p = C.survey(_facts(), runner=r)
    check("[중요] 도달 여부를 못 보면 지우지 않는다", not p.delete, str(p.delete))
    check("못 봤다고 적는다", any("확인하지 못했다" in w for _, w in p.keep), str(p.keep))

    # fetch 실패 = origin/main 이 낡았을 수 있다 → 판정 자체를 하지 않는다
    r2 = Fake(branches=f"attempt/t1/w/1:{MERGED}\n", fetch_rc=1)
    p2 = C.survey(_facts(), runner=r2)
    check("[중요] fetch 실패면 아무것도 계획하지 않는다", not p2.delete and p2.errors, p2.summary)
    check("사유를 남긴다", "fetch 실패" in p2.errors[0], str(p2.errors))


def test_current_branch_kept() -> None:
    r = Fake(branches=f"task/t1:{MERGED}\nattempt/t1/w/1:{MERGED}\n", current="task/t1")
    p = C.survey(_facts(), runner=r)
    check("[중요] 체크아웃된 브랜치는 지우지 않는다", [n for n, _ in p.delete] == ["attempt/t1/w/1"],
          str(p.delete))
    check("그 사유를 적는다", any("체크아웃" in w for _, w in p.keep), str(p.keep))


def test_never_touches_remote() -> None:
    """[중요] 원격 브랜치 삭제는 사람의 판단이다 — 마스터는 세기만 한다."""
    r = Fake(branches=f"attempt/t1/w/1:{MERGED}\n")
    p = C.survey(_facts(), runner=r)
    C.apply(_facts(), p, runner=r)
    check("[중요] push --delete 를 절대 부르지 않는다",
          not any("push" in c for c in r.calls), str([c for c in r.calls if "push" in c]))
    check("[중요] reset·clean 도 부르지 않는다",
          not any(("reset" in c or "clean" in c) for c in r.calls))
    check("원격 attempt 는 세어서 보고만 한다", p.remote_attempts == 2, str(p.remote_attempts))


# ── 부산물 ───────────────────────────────────────────────────────────────────

def test_artifacts() -> None:
    closed = {"aaa": "verified", "bbb": "failed", "ccc": "cancelled", "ddd": "claimed"}
    r = Fake(branches="", dirs="aaa\nbbb\nccc\nddd\neee\n")
    p = C.survey(_facts(), closed=closed, runner=r)
    drop = sorted(t for t, _ in p.drop_dirs)
    check("성공·취소만 지운다", drop == ["aaa", "ccc"], str(drop))
    # [중요] 실패는 왜 실패했는지 볼 유일한 기록이다
    check("[중요] failed 는 남긴다", any(t == "bbb" for t, _ in p.keep_dirs), str(p.keep_dirs))
    check("진행 중도 남긴다", any(t == "ddd" for t, _ in p.keep_dirs))
    check("[중요] 큐에 없는 것은 지우지 않는다",
          any(t == "eee" and "모르는 것" in w for t, w in p.keep_dirs), str(p.keep_dirs))

    # closed 를 못 받으면 부산물은 아예 보지 않는다
    p2 = C.survey(_facts(), closed=None, runner=Fake(dirs="aaa\n"))
    check("[중요] 큐를 못 읽으면 부산물은 손대지 않는다", not p2.drop_dirs and not p2.keep_dirs)


def test_path_traversal() -> None:
    """[중요] `rm -rf` 를 만드는 코드다 — 이름을 두 번 검사한다."""
    closed = {"../../etc": "verified", "a b; rm -rf /": "verified", "ok1": "verified"}
    r = Fake(dirs="../../etc\na b; rm -rf /\nok1\n")
    p = C.survey(_facts(), closed=closed, runner=r)
    check("[중요] 이상한 이름은 후보에서 뺀다", [t for t, _ in p.drop_dirs] == ["ok1"], str(p.drop_dirs))

    # apply 단계에서도 한 번 더 막는다
    p.drop_dirs.append(("../../etc", "verified"))
    r2 = Fake()
    done = C.apply(_facts(), p, runner=r2)
    check("[중요] apply 도 다시 막는다", "ok1" in done["dirs"] and "../../etc" not in done["dirs"],
          str(done))
    check("막았다고 보고한다", any("이상하다" in e for e in done["errors"]), str(done["errors"]))
    check("[중요] 위험한 경로로 rm 을 부르지 않았다",
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
    # [중요] 보존하기로 한 것이 명령에 등장하면 안 된다
    check("[중요] 보존 대상이 명령에 안 나온다",
          not any("t2" in c or "bbb" in c for c in r2.destructive), str(r2.destructive))

    win = C.apply(_facts("192.168.0.2", os_="windows", path="E:\\trunk\\ModularStage"), p,
                  runner=(w := Fake()))
    check("윈도우는 rmdir 를 쓴다", any("rmdir /s /q" in c for c in w.calls), str(w.calls))
    check("윈도우 경로가 역슬래시다", any("E:\\trunk" in c for c in w.calls), str(w.calls))
    check("윈도우도 계획대로만", win["dirs"] == ["aaa"], str(win))



def test_park_to_main() -> None:
    """[중요] 우리 브랜치 위에 서 있으면 main 으로 되돌린다 (사용자 결정 2026-08-09)."""
    r = Fake(branches=f"task/t1:{UNMERGED}\nattempt/t1/w/1:{MERGED}\n", current="task/t1")
    p = C.survey(_facts(), runner=r)
    check("[중요] 우리 브랜치면 복귀를 계획한다", p.park == "main", p.summary)
    check("survey 단계에선 아직 안 옮긴다",
          not any("checkout " in c for c in r.calls), str(r.calls))

    r2 = Fake()
    done = C.apply(_facts(), p, runner=r2)
    check("apply 가 복귀시킨다", done["parked"] == "main", str(done))
    # [중요] 복귀를 먼저 해야 방금 서 있던 브랜치도 같은 회차에 지울 수 있다
    order = [c for c in r2.calls if "checkout " in c or "branch -D" in c]
    check("[중요] 복귀가 삭제보다 먼저다", order and "checkout" in order[0], str(order))

    # [주의] 더러우면 되돌리지 않는다 — 체크아웃이 사람의 편집을 건드린다
    dirty = Fake(branches=f"task/t1:{UNMERGED}\n", current="task/t1", status=" M Source/A.cpp\n")
    pd = C.survey(_facts(), runner=dirty)
    check("[중요] Source/ 가 더러우면 되돌리지 않는다", not pd.park, pd.summary)
    check("그 사유를 적는다", any("더럽다" in w for _, w in pd.keep), str(pd.keep))

    # main 위에 있으면 할 일이 없다
    check("main 위면 복귀 안 함", not C.survey(_facts(), runner=Fake(current="main")).park)


# ── 원격 정리 (사용자 결정 2026-08-18 — 병합 확인분만 마스터가 지운다) ────────────────

class FakeGit:
    """마스터 정본 저장소의 git 을 흉내낸다 — is-ancestor 판정과 push 를 전부 기록한다."""

    def __init__(self, refs, merged):
        # refs: {ref이름: tip} · merged: 도달 가능한 tip 집합
        self.refs, self.merged = refs, set(merged)
        self.pushes = []

    def __call__(self, repo, *args):
        from master.work.coordinator import GitError
        if args[0] == "fetch":
            return ""
        if args[0] == "ls-remote":
            return "\n".join(f"{tip}\trefs/heads/{ref}" for ref, tip in self.refs.items())
        if args[:2] == ("merge-base", "--is-ancestor"):
            if args[2] in self.merged:
                return ""
            raise GitError("not an ancestor")
        if args[0] == "push":
            self.pushes.append(args)
            return ""
        raise AssertionError(args)


class _Paths:
    repo = "/tmp/fake-repo"
    name = "P"


def test_remote_only_merged_is_deleted():
    g = FakeGit({"task/merged1": MERGED, "attempt/t/w/1": MERGED,
                 "task/probe": UNMERGED}, merged=[MERGED])
    p = C.survey_remote(_Paths(), git=g)
    check("[중요] 병합분만 삭제 후보다", {r for r, _ in p.delete}
          == {"task/merged1", "attempt/t/w/1"}, str(p.delete))
    check("[중요] 미병합은 보존 + 사람 몫 사유", p.keep and "사람 몫" in p.keep[0][2],
          str(p.keep))


def test_remote_ls_failure_judges_nothing():
    from master.work.coordinator import GitError

    def boom(repo, *args):
        raise GitError("연결 실패")
    p = C.survey_remote(_Paths(), git=boom)
    check("[중요] 원격을 못 보면 아무것도 판정하지 않는다",
          not p.delete and not p.keep and "판정하지 않는다" in p.error, p.error)


def test_remote_apply_follows_plan_only():
    g = FakeGit({"task/merged1": MERGED, "task/probe": UNMERGED}, merged=[MERGED])
    p = C.survey_remote(_Paths(), git=g)
    done = C.apply_remote(_Paths(), p, git=g)
    check("계획된 것만 지운다", done["deleted"] == ["task/merged1"], str(done))
    check("push --delete 형태다", g.pushes and g.pushes[0][:2] == ("push", "gitea-write")
          and "--delete" in g.pushes[0], str(g.pushes))
    check("보존분은 push 되지 않았다",
          not any("task/probe" in " ".join(x) for x in g.pushes))


def test_machine_scan_real_git_333() -> None:
    """`#333` ⓐ — 실 git: 죽은 등록·미추적·도달 불가·깨끗한 worktree · 지워진 원격의 추적 ref. 쓰기 0."""
    import os
    import shutil
    import subprocess
    import tempfile
    from master.work import cleanup as C

    def g(cwd, *a):
        return subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True, check=True).stdout.strip()
    with tempfile.TemporaryDirectory() as td:
        bare, repo = os.path.join(td, "o.git"), os.path.join(td, "r")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", bare], check=True)
        subprocess.run(["git", "clone", "-q", bare, repo], check=True, capture_output=True)
        g(repo, "config", "user.email", "t@t"); g(repo, "config", "user.name", "t")
        open(os.path.join(repo, "a"), "w").write("a\n")
        g(repo, "add", "a"); g(repo, "commit", "-q", "-m", "a"); g(repo, "push", "-q", "origin", "main")
        main_sha = g(repo, "rev-parse", "HEAD")
        clean, dirty, dead, lost = (os.path.join(td, n) for n in ("wt-clean", "wt-dirty", "wt-dead", "wt-lost"))
        g(repo, "worktree", "add", "-q", "--detach", clean, "main")
        g(repo, "worktree", "add", "-q", "--detach", dirty, "main")
        open(os.path.join(dirty, "new.txt"), "w").write("x\n")             # 미추적
        g(repo, "worktree", "add", "-q", "--detach", dead, "main")
        shutil.rmtree(dead)                                                   # 죽은 등록
        g(repo, "worktree", "add", "-q", "-b", "probe", lost, "main")         # 이름 패턴 밖 · 미병합 커밋
        open(os.path.join(lost, "p"), "w").write("p\n")
        g(lost, "add", "p"); g(lost, "commit", "-q", "-m", "probe")
        lost_sha = g(lost, "rev-parse", "HEAD")
        g(repo, "update-ref", "refs/remotes/gw/ok", main_sha)                 # 지워진 원격 `gw`
        g(repo, "update-ref", "refs/remotes/gw/only", lost_sha)
        calls = []

        def run(path, args):
            calls.append(args)
            return C._local_run(path, args)
        r = C.scan_repo(run, repo, machine="m", label="P · worker")
        cand = " | ".join(w for w, _ in r.candidates)
        rev = " | ".join(f"{w} — {why}" for w, why in r.review)
        check("#333 기준 ref = origin/main", r.base_ref == "origin/main", r.base_ref)
        check("#333 worktree 4개 열거(주 트리 제외 · 이름 패턴 무관)", r.worktrees == 4, str(r))
        check("#333 깨끗·도달 → 후보", "wt-clean" in cand, cand)
        check("#333 미추적 있는 worktree → 볼 것(미추적 1)", "wt-dirty" in rev and "미추적 1" in rev, rev)
        check("#333 죽은 등록(도달) → 후보 · prune 안내", "wt-dead" in cand
              and any("죽은 등록" in why for w, why in r.candidates if "wt-dead" in w), str(r.candidates))
        check("#333 미병합 커밋 worktree → 볼 것(도달 불가)", "wt-lost" in rev and "도달 불가" in rev, rev)
        check("#333 지워진 원격 ref — 도달은 후보 · 유일 사본은 볼 것",
              "refs/remotes/gw/ok" in cand and "refs/remotes/gw/only" in rev, f"{cand} // {rev}")
        bad = [a for a in calls if any(w in a for w in ("prune", "remove", "delete", " -d", " -D",
                                                         "update-ref", "push", "reset", "checkout", "clean"))]
        check("🔴 #333 쓰기 명령 0 — 읽기 전용", bad == [], str(bad))
        check("#333 실제로 아무것도 안 지웠다(죽은 등록·ref 그대로)",
              "prunable" in g(repo, "worktree", "list", "--porcelain")
              and g(repo, "rev-parse", "refs/remotes/gw/only") == lost_sha)
        out = C.render_scan(r)
        check("#333 출력 — 후보와 볼 것이 다른 줄", "    후보   " in out and "    볼 것  " in out, out)


def test_machine_scan_failures_333() -> None:
    """기준 ref 없음·목록 실패는 지울 것 후보를 만들지 않는다(전부 사람이 볼 것 · 오류 기록)."""
    from master.work import cleanup as C

    def run(path, args):
        if args.startswith("rev-parse"):
            return 1, ""
        if args.startswith("worktree list"):
            return 0, "worktree /r\nHEAD aaaa\nbranch refs/heads/main\n\nworktree /r-x\nHEAD bbbb\ndetached\n"
        if args.startswith("status"):
            return 0, ""
        if args == "remote":
            return 128, "fatal"
        return 0, ""
    r = C.scan_repo(run, "/r", machine="m")
    check("#333 기준 ref 없음 → 후보 0 · 볼 것 1 · 오류 기록",
          r.candidates == [] and len(r.review) == 1 and any("기준 ref" in e for e in r.errors), str(r))
    check("#333 원격 목록 실패 → 추적 ref 판정 생략 기록", any("원격 목록 실패" in e for e in r.errors), str(r.errors))
    p = C.parse_worktrees("worktree /a\nHEAD 1\nbranch refs/heads/main\n\nworktree /b\nHEAD 2\ndetached\n"
                          "prunable gitdir file points to non-existent location\n")
    check("#333 porcelain 해석 — 주 트리·detached·prunable",
          p[0]["branch"] == "main" and p[1]["detached"] and p[1]["prunable"].startswith("gitdir"), str(p))


def test_main_lag_sync_333() -> None:
    """`#333` ⓒ (가) — main 이 뒤처졌으면 plan 이 보이고, 깨끗·앞선 커밋 없음일 때만 apply 가 ff 로 앞당긴다."""
    r = Fake(current="main", behind=5)
    p = C.survey(_facts(), runner=r)
    check("#333 뒤처진 main → 앞당기기 계획 · 표시", p.park == "main" and "5 커밋 뒤" in p.summary, p.summary)
    check("#333 survey 는 옮기지 않는다", not any(k in c for c in r.calls for k in ("checkout ", "merge ")), str(r.calls))
    r2 = Fake()
    done = C.apply(_facts(), p, runner=r2)
    check("#333 apply — checkout main 뒤 merge --ff-only origin/main",
          done["parked"] == "main" and any("merge --ff-only -q origin/main" in c for c in r2.calls), str(r2.calls))
    check("#333 reset·-B 를 쓰지 않는다(커밋 잃는 경로 없음)",
          not any("reset" in c or "checkout -B" in c for c in r2.calls), str(r2.calls))
    pd = C.survey(_facts(), runner=Fake(current="main", behind=3, status=" M a.py\n"))
    check("#333 추적 파일이 더러우면 앞당기지 않고 사유", not pd.park and "더럽다" in pd.lag, pd.summary)
    pa = C.survey(_facts(), runner=Fake(current="main", behind=2, ahead=1))
    check("#333 origin 에 없는 커밋이 있으면 앞당기지 않음(사람이 볼 것)", not pa.park and "사람이 볼 것" in pa.lag, pa.summary)
    pu = C.survey(_facts(), runner=Fake(current="main", lag_rc=128))
    check("#333 재지 못하면 아무것도 안 함", not pu.park and "재지 못했다" in pu.lag, pu.summary)
    p0 = C.survey(_facts(), runner=Fake(current="main"))
    check("#333 최신 main 이면 할 일 없음 · 표시 없음", not p0.park and not p0.lag, p0.summary)
    pt = C.survey(_facts(), runner=Fake(branches=f"task/t1:{UNMERGED}\n", current="task/t1"))
    d2 = C.apply(_facts(), pt, runner=Fake())
    check("#333 우리 브랜치에서 복귀할 때도 main 을 ff 로 맞춘다", d2["parked"] == "main", str(d2))

    class FF(Fake):
        def __call__(self, facts, cmd):
            if "merge --ff-only" in cmd:
                self.calls.append(cmd)
                return 1, "fatal: Not possible to fast-forward"
            return Fake.__call__(self, facts, cmd)
    d3 = C.apply(_facts(), C.survey(_facts(), runner=Fake(current="main", behind=1)), runner=FF())
    check("#333 ff 실패는 기록만(그대로 둔다)", any("ff) 실패" in e for e in d3["errors"]), str(d3))


def test_main_lag_real_git_333() -> None:
    """`#333` ⓒ 실 git — 원격이 앞선 워커 클론: plan 이 N 뒤를 보이고 apply 가 ff 로 맞춘다."""
    import os
    import subprocess
    import tempfile

    def g(cwd, *a):
        return subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True, check=True).stdout.strip()

    def shell(facts, cmd):
        p_ = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
        return p_.returncode, (p_.stdout or "") + (p_.stderr or "")
    with tempfile.TemporaryDirectory() as td:
        bare, seed, wk = (os.path.join(td, n) for n in ("o.git", "seed", "worker"))
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", bare], check=True)
        subprocess.run(["git", "clone", "-q", bare, seed], check=True, capture_output=True)
        for d in (seed,):
            g(d, "config", "user.email", "t@t"); g(d, "config", "user.name", "t")
        open(os.path.join(seed, "a"), "w").write("1\n")
        g(seed, "add", "a"); g(seed, "commit", "-q", "-m", "1"); g(seed, "push", "-q", "origin", "main")
        subprocess.run(["git", "clone", "-q", bare, wk], check=True, capture_output=True)
        for i in (2, 3):                                               # 워커 클론 뒤 원격이 2 커밋 앞선다
            open(os.path.join(seed, "a"), "w").write(f"{i}\n")
            g(seed, "commit", "-qam", str(i))
        g(seed, "push", "-q", "origin", "main")
        f = _facts(path=wk)
        p = C.survey(f, runner=shell)
        check("#333 실 git — 2 커밋 뒤를 본다", p.park == "main" and "2 커밋 뒤" in p.lag, p.summary)
        done = C.apply(f, p, runner=shell)
        check("#333 실 git — apply 뒤 로컬 main == origin/main",
              not done["errors"] and g(wk, "rev-parse", "main") == g(bare, "rev-parse", "main"), str(done))
        check("#333 실 git — 다시 보면 할 일 없음", not C.survey(f, runner=shell).park)


def test_machine_scan_queue_and_local_branches_874() -> None:
    """`#874` — 이름의 work_id 로 큐 대조(취소·반려·진행·모름) · 마스터 로컬 task/attempt 열거. 쓰기 0."""
    import os
    import subprocess
    import tempfile
    from master.work import cleanup as C

    def g(cwd, *a):
        return subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True, check=True).stdout.strip()
    W1, W2, W3, W4, W5 = ("20261101_2208_t5_cancel_aa", "20261010_1742_788_rej_bb", "20261101_2300_open_cc",
                          "20261101_2301_unknown_dd", "20261101_2302_merged_ee")
    status = {W1: "cancelled", W2: "rejected", W3: "ready_for_review", W5: "merged"}
    with tempfile.TemporaryDirectory() as td:
        bare, repo = os.path.join(td, "o.git"), os.path.join(td, "r")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", bare], check=True)
        subprocess.run(["git", "clone", "-q", bare, repo], check=True, capture_output=True)
        g(repo, "config", "user.email", "t@t"); g(repo, "config", "user.name", "t")
        open(os.path.join(repo, "a"), "w").write("a\n")
        g(repo, "add", "a"); g(repo, "commit", "-q", "-m", "a"); g(repo, "push", "-q", "origin", "main")

        def side(name):                                   # main 에서 갈라진 미병합 커밋 하나
            g(repo, "checkout", "-q", "-b", f"tmp-{name}", "main")
            open(os.path.join(repo, name), "w").write(name + "\n")
            g(repo, "add", name); g(repo, "commit", "-q", "-m", name)
            sha = g(repo, "rev-parse", "HEAD"); g(repo, "checkout", "-q", "main")
            g(repo, "branch", "-q", "-D", f"tmp-{name}")
            return sha
        for wid in (W1, W2, W3, W4):
            g(repo, "worktree", "add", "-q", "--detach", os.path.join(td, f"ax-advance-{wid}"), side(wid))
        g(repo, "branch", f"task/{W1}/base", side("b1"))                      # 취소 work 로컬 브랜치
        g(repo, "branch", f"task/{W5}/base", "main")                          # 병합 — 도달
        lost = side("lost")
        g(repo, "branch", "attempt/x/y/1", lost)                              # work_id 없음 · 미병합
        kept = side("kept")
        g(repo, "branch", "attempt/x/y/2", kept)
        g(repo, "update-ref", "refs/ax/pruned/x", kept)                       # 미러 보존 → 고유 0
        calls = []

        def run(path, args):
            calls.append(args)
            return C._local_run(path, args)
        r = C.scan_repo(run, repo, machine="마스터", work_status=lambda w: status.get(w), local_branches=True)
        cand = {w: why for w, why in r.candidates}
        rev = {w: why for w, why in r.review}

        def find(d, key):
            return next((why for w, why in d.items() if key in w), "")
        check("#874 취소 work worktree → 후보 · 고유 커밋 1개", "취소 work" in find(cand, f"ax-advance-{W1}")
              and "고유 커밋 1개" in find(cand, f"ax-advance-{W1}"), str(cand))
        check("#874 반려 work worktree → 볼 것 #821", "#821" in find(rev, f"ax-advance-{W2}"), str(rev))
        check("#874 진행 중 work → 볼 것", "진행 중 work" in find(rev, f"ax-advance-{W3}"), str(rev))
        check("#874 큐가 모르는 work → 종전(도달 불가 · 볼 것)", "도달 불가" in find(rev, f"ax-advance-{W4}"), str(rev))
        check("#874 worktree 밖 로컬 task/<취소>/base → 후보", "취소 work" in find(cand, f"task/{W1}/base"), str(cand))
        check("#874 병합 work 로컬 브랜치 → 도달 후보", "도달" in find(cand, f"task/{W5}/base"), str(cand))
        check("#874 id 없는 미병합 attempt → 볼 것 · 고유 1", "고유 커밋 1개" in find(rev, "attempt/x/y/1"), str(rev))
        check("#874 미러(refs/ax) 보존분은 고유 0", "고유 커밋 0개" in find(rev, "attempt/x/y/2"), str(rev))
        bad = [a for a in calls if any(k in a for k in ("prune", "remove", "delete", " -d", " -D", "update-ref",
                                                        "push", "reset", "checkout", "clean"))]
        check("🔴 #874 쓰기 명령 0", bad == [], str(bad))
        r2 = C.scan_repo(run, repo, machine="마스터", work_status=lambda w: (_ for _ in ()).throw(RuntimeError("큐")),
                         local_branches=True)
        check("#874 큐 조회 예외 → 종전 판정(취소 worktree 도 볼 것)",
              any(f"ax-advance-{W1}" in w for w, _ in r2.review), str(r2.review))
        r3 = C.scan_repo(run, repo, machine="m")
        check("#874 local_branches 끄면 로컬 브랜치 줄 없음",
              not any("로컬 브랜치" in w for w, _ in r3.candidates + r3.review))
    check("#874 work_id_of — 경로·브랜치", C.work_id_of("/home/sim/ax-advance-20261101_2208_x_y", "")
          == "20261101_2208_x_y" and C.work_id_of("", "task/20261010_1742_a_b/r1/c") == "20261010_1742_a_b"
          and C.work_id_of("/home/sim/ax-788-work", "") == "")


def test_machine_scan_other_local_branches_886() -> None:
    """`#886` — task/·attempt/ 밖 로컬 브랜치(fix/R* 등)도 열거 · issue/<N> 은 볼 것 · 기준 브랜치 제외. 쓰기 0."""
    import os
    import subprocess
    import tempfile
    from master.work import cleanup as C

    def g(cwd, *a):
        return subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True, check=True).stdout.strip()
    with tempfile.TemporaryDirectory() as td:
        bare, repo = os.path.join(td, "o.git"), os.path.join(td, "r")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", bare], check=True)
        subprocess.run(["git", "clone", "-q", bare, repo], check=True, capture_output=True)
        g(repo, "config", "user.email", "t@t"); g(repo, "config", "user.name", "t")
        open(os.path.join(repo, "a"), "w").write("a\n")
        g(repo, "add", "a"); g(repo, "commit", "-q", "-m", "a"); g(repo, "push", "-q", "origin", "main")
        g(repo, "branch", "fix/R1", "main")                                   # 병합 — 도달
        g(repo, "checkout", "-q", "-b", "fix/R2", "main")                      # 미병합 커밋 1
        open(os.path.join(repo, "b"), "w").write("b\n")
        g(repo, "add", "b"); g(repo, "commit", "-q", "-m", "b"); g(repo, "checkout", "-q", "main")
        g(repo, "branch", "issue/9", "main")                                  # 보류 일감 — 도달해도 볼 것
        g(repo, "worktree", "add", "-q", os.path.join(td, "wt10"), "-b", "issue/10", "main")   # worktree 소유
        calls = []

        def run(path, args):
            calls.append(args)
            return C._local_run(path, args)
        r = C.scan_repo(run, repo, machine="마스터", work_status=lambda w: None, local_branches=True)
        cand = {w: why for w, why in r.candidates}
        rev = {w: why for w, why in r.review}

        def find(d, key):
            return next((why for w, why in d.items() if f"로컬 브랜치 {key} @" in w), "")
        check("#886 병합 fix/R1 → 후보(도달)", "도달" in find(cand, "fix/R1"), str(cand))
        check("#886 미병합 fix/R2 → 볼 것 · 고유 1", "고유 커밋 1개" in find(rev, "fix/R2"), str(rev))
        check("#886 issue/9(main 도달) → 후보가 아니라 볼 것", "issue_flow" in find(rev, "issue/9")
              and not find(cand, "issue/9"), str(cand) + str(rev))
        allw = [w for w, _ in r.candidates + r.review]
        check("#886 기준 브랜치 main 은 로컬 브랜치 줄에 없다", not any("로컬 브랜치 main @" in w for w in allw), str(allw))
        check("#886 worktree 소유 issue/10 은 worktree 줄에서만", not any("로컬 브랜치 issue/10 @" in w for w in allw)
              and any("[issue/10]" in w for w in allw), str(allw))
        bad = [a for a in calls if any(k in a for k in ("prune", "remove", "delete", " -d", " -D", "update-ref",
                                                        "push", "reset", "checkout", "clean"))]
        check("🔴 #886 쓰기 명령 0", bad == [], str(bad))


def main() -> int:
    for fn in (test_only_merged_is_deleted, test_format_has_no_space, test_uncertain_is_kept, test_current_branch_kept,
               test_never_touches_remote, test_artifacts, test_path_traversal,
               test_apply_follows_plan_only, test_park_to_main,
               test_remote_only_merged_is_deleted, test_remote_ls_failure_judges_nothing,
               test_remote_apply_follows_plan_only, test_machine_scan_real_git_333,
               test_machine_scan_failures_333, test_main_lag_sync_333,
               test_main_lag_real_git_333, test_machine_scan_queue_and_local_branches_874,
               test_machine_scan_other_local_branches_886):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_cleanup: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
