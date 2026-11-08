"""일감 마감 뒤 단계 (`#921`) — 대역 주입으로 순서·멈춤·재기동 대상·배달을 검사한다.

    .venv/bin/python master/test_issue_wrapup.py

[중요] 실제 systemctl·sudo·배달·Redmine 을 부르지 않는다 — 전부 `Deps` 대역이다.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from master import issue_wrapup as W                     # noqa: E402

PASS = FAIL = 0
END, HEAD = "e" * 40, "h" * 40


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def V(unit, *, stale=False, dep=False, why="", dep_why=""):
    return SimpleNamespace(unit=unit, stale=stale, dep_changed=dep, why=why, dep_why=dep_why)


class World:
    """대역 세계 — 호출을 기록한다."""

    def __init__(self, *, verdicts=None, after=None, handoff=True, dirty="", branch="main",
                 origin=HEAD, track=True, lock=None, busy=0, deliver_rc=0, restart_err=None, note="ok"):
        self.calls: list = []
        self.verdicts = verdicts if verdicts is not None else [V("ax-projects"), V("ax-broker")]
        self.after = after
        self.handoff, self.dirty, self.branch, self.origin = handoff, dirty, branch, origin
        self.track_v = {"round": 1, "end": END} if track else None
        self.lock_v, self.busy, self.deliver_rc = lock, busy, deliver_rc
        self.restart_err, self.note_v = restart_err, note
        self.fresh_n = 0

    def git(self, repo, *args):
        self.calls.append(("git",) + args)
        if args[0] == "rev-parse" and args[1] == "--abbrev-ref":
            return 0, self.branch
        if args[0] == "status":
            return 0, self.dirty
        if args[:2] == ("rev-parse", "HEAD"):
            return 0, HEAD
        if args[:2] == ("rev-parse", "origin/main"):
            return 0, self.origin
        if args[0] == "merge-base":
            return 0, ""
        if args[0] == "log":
            return 0, ("abc1234" if self.handoff else "")
        return 0, ""

    def deps(self):
        def track(n, p):
            self.calls.append(("track", n))
            return self.track_v

        def lock(p):
            return self.lock_v

        def freshness():
            self.fresh_n += 1
            self.calls.append(("fresh", self.fresh_n))
            return self.verdicts if self.fresh_n == 1 or self.after is None else self.after

        def restart(unit):
            self.calls.append(("restart", unit))
            if self.restart_err:
                raise RuntimeError(self.restart_err)
            return ({"ExecMainStartTimestamp": "old"},
                    {"ExecMainStartTimestamp": "new", "ActiveState": "active"})

        def active_state(unit):
            self.calls.append(("active", unit))
            if self.busy > 0 and unit == "ax-review-queue":
                self.busy -= 1
                return "activating"
            return "inactive"

        def deliver(repo):
            self.calls.append(("deliver",))
            return self.deliver_rc, "OK 192.168.0.43\n[완료] 배달·검사"

        def note(n, text):
            self.calls.append(("note", text))
            return self.note_v

        return W.Deps(git=self.git, track=track, lock=lock, freshness=freshness, restart=restart,
                      active_state=active_state, deliver=deliver, note=note,
                      sleep=lambda s: self.calls.append(("sleep", s)))

    def did(self, kind):
        return [c for c in self.calls if c[0] == kind]


def go(world, **kw):
    out = []
    r = W.run(921, repo=Path("/tmp/x"), deps=world.deps(), out=out.append, **kw)
    return r, "\n".join(out)


def test_clean_path() -> None:
    w = World()
    r, log = go(w)
    check("최신·인수인계 있음 → rc0", r.rc == W.RC_DONE, log)
    check("재기동 없음", not w.did("restart"), str(w.calls))
    check("배달 1회 · 노트 1회", len(w.did("deliver")) == 1 and len(w.did("note")) == 1, str(w.calls))
    check("단계마다 로그", all(f"#921 {s}:" in log for s in ("finish", "repo", "fresh", "restart",
                                                            "handoff", "deliver", "note")), log)


def test_restart_only_judged() -> None:
    w = World(verdicts=[V("ax-projects", dep=True), V("ax-broker"), V("ax-task-queue", stale=True)],
              after=[V("ax-projects"), V("ax-broker"), V("ax-task-queue")])
    r, log = go(w)
    got = [c[1] for c in w.did("restart")]
    check("🔴 판정된 서비스만 재기동", got == ["ax-projects", "ax-task-queue"], str(got))
    check("재기동 뒤 다시 판정", w.fresh_n == 2, str(w.fresh_n))
    check("rc0 · 기록에 재기동", r.rc == W.RC_DONE and "ax-projects new" in w.did("note")[0][1], log)
    order = [c[0] for c in w.calls if c[0] in ("restart", "deliver")]
    check("재기동이 배달보다 먼저", order.index("restart") < order.index("deliver"), str(order))


def test_oneshot_wait() -> None:
    w = World(verdicts=[V("ax-broker", dep=True)], after=[V("ax-broker")], busy=2)
    r, log = go(w)
    check("oneshot 이 끝날 때까지 기다린다", len(w.did("sleep")) == 2 and r.rc == W.RC_DONE, log)
    sleeps = [i for i, c in enumerate(w.calls) if c[0] == "sleep"]
    first_restart = next(i for i, c in enumerate(w.calls) if c[0] == "restart")
    check("대기가 재기동보다 먼저", max(sleeps) < first_restart, str(w.calls))
    w2 = World(verdicts=[V("ax-broker", dep=True)], busy=10 ** 6)
    old = W.WAIT_MAX
    W.WAIT_MAX = 30
    try:
        r2, log2 = go(w2)
    finally:
        W.WAIT_MAX = old
    check("대기 상한을 넘으면 재기동 없이 멈춘다", r2.rc == W.RC_FAIL and not w2.did("restart")
          and "oneshot" in log2, log2)


def test_handoff_gate() -> None:
    w = World(verdicts=[V("ax-broker", dep=True)], after=[V("ax-broker")], handoff=False)
    r, log = go(w)
    check("🔴 인수인계 없음 → rc2 · 배달 안 함", r.rc == W.RC_HANDOFF and not w.did("deliver")
          and not w.did("note"), log)
    check("재기동은 이미 했다(배달 전 단계)", [c[1] for c in w.did("restart")] == ["ax-broker"], str(w.calls))
    check("다시 부르라는 사실을 찍는다", "다시 실행" in log and "#916" in log, log)
    logs = [c for c in w.calls if c[0] == "git" and c[1] == "log"]
    check("끝 커밋 뒤 인수인계서만 본다", logs and logs[0][3] == f"{END}..HEAD"
          and logs[0][-1] == W.HANDOFF, str(logs))
    # 재실행 — 이제 최신이고 인수인계 있음 → 재기동 없이 배달
    w2 = World(handoff=True)
    r2, _ = go(w2)
    check("재실행은 재기동 없이 배달부터", r2.rc == W.RC_DONE and not w2.did("restart")
          and w2.did("deliver"), str(w2.calls))


def test_stops() -> None:
    cases = [
        ("마감 기록 없음", World(track=False), "issue_finish"),
        ("잠금 활성", World(lock={"issue_id": 921}), "잠금"),
        ("main 아님", World(branch="issue/921"), "main 이 아니다"),
        ("더러운 트리", World(dirty=" M x.py"), "깨끗하지 않다"),
        ("origin 불일치", World(origin="o" * 40), "origin/main"),
        ("신선도 판정 불가", World(verdicts=[V("ax-projects", why="journal 없음")]), "판정 불가"),
        ("재기동 실패", World(verdicts=[V("ax-broker", stale=True)], restart_err="helper rc=1"), "재기동 실패"),
        ("재기동 뒤에도 남음", World(verdicts=[V("ax-broker", stale=True)],
                               after=[V("ax-broker", stale=True)]), "판정이 남았다"),
        ("배달 실패", World(deliver_rc=1), "update rc=1"),
        ("노트 실패", World(note="[주의] Redmine 401"), "노트 실패"),
    ]
    for name, w, key in cases:
        r, log = go(w)
        check(f"멈춤 — {name} → rc1", r.rc == W.RC_FAIL and key in log and "[중요] 멈춘다" in log, log)
    w = World(lock={"issue_id": 999})
    r, _ = go(w)
    check("다른 일감의 잠금은 막지 않는다", r.rc == W.RC_DONE)
    w = World(verdicts=[V("ax-projects", dep_why="기동 기록에 의존 목록이 없다")])
    r, log = go(w)
    check("의존 판정 불가는 재기동 대상이 아니다(표시만)", r.rc == W.RC_DONE and not w.did("restart")
          and "의존 판정 불가" in log, log)


def test_dry_run() -> None:
    w = World(verdicts=[V("ax-broker", stale=True)])
    r, log = go(w, dry_run=True)
    check("dry-run 은 재기동·배달·노트 없음", r.rc == W.RC_DONE and not w.did("restart")
          and not w.did("deliver") and not w.did("note") and "(dry-run)" in log, log)


def main() -> int:
    for fn in (test_clean_path, test_restart_only_judged, test_oneshot_wait, test_handoff_gate,
               test_stops, test_dry_run):
        fn()
    print(f"{'OK' if not FAIL else 'FAIL'} test_issue_wrapup: {PASS}/{PASS + FAIL} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
