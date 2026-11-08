"""일감 마감 뒤 단계 (`#921`) — 공용 규칙 §1.9 의 「마감 뒤」를 **코드가 순서대로** 집행한다.

    .venv/bin/python -m master.issue_wrapup <일감번호> [--dry-run] [--project AXCluster]

## 왜

2026-11-08 하루에 세 지휘자(Claude·Codex·Antigravity)가 모두 마감 뒤 단계를 한 번 이상 빠뜨렸다 —
배달 누락으로 워커 `check` rc=1(#913·#882·#820), 배달 **뒤** 인수인계 커밋으로 1커밋 뒤처짐(#916, 4회),
재기동 직전 oneshot 확인 누락(#918). 규칙은 진입 지침에 이미 있었다 — 그래서 문서가 아니라 코드다.

## 순서 (공용 규칙 §1.9)

    ① 마감 확인     — 그 일감의 마감 추적 기록(끝 커밋)이 있고, 일감 잠금이 그 일감에 잡혀 있지 않다
    ② 저장소 확인   — 운영 저장소가 main · 깨끗 · origin/main 과 같다 · 끝 커밋이 main 에 들어 있다
    ③ 신선도 판정   — `service_freshness.check()`: [중요] 옛 코드·[주의] 의존 변경으로 **판정된** 상주만 대상
    ④ 재기동        — 그 상주를 실행 중에 쓰는 oneshot 만(`WAIT_FOR`, #922) 끝나길 기다린 뒤 `service_restart.restart`(기동 시각·상태 검증),
                      재기동 뒤 그 서비스를 다시 판정한다. 판정에 없는 서비스는 건드리지 않는다
    ⑤ 인수인계 확인 — 끝 커밋 **뒤에** 인수인계서 커밋이 main 에 있어야 한다. 없으면 **배달 전에 멈춘다(rc 2)** —
                      인수인계 내용은 지휘자가 쓴다(이때도 그때까지의 재기동을 노트로 남긴다, #922). 커밋·push 뒤 같은 명령을 다시 부르면 ③④는 할 일이 없어 지나간다
    ⑥ 배달          — `master.client update`(마운트된 프로젝트) rc0
    ⑦ 기록          — 그 일감 Redmine 에 결과 노트

종료 코드: 0 = 끝까지 완료 · 1 = 실패(사유를 찍고 멈춘다 — 고치지 않는다) · 2 = 인수인계서 대기.
[주의] 자동으로 고치는 것은 없다. 판정 불가(신선도 why)·잠금·더러운 트리는 **보고하고 멈춘다.**
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parent.parent
HANDOFF = "docs/orchestrator-handoff.md"
ONESHOTS = ("ax-review-queue", "ax-dispatch", "ax-indexer")
# `#922` — 재기동할 상주가 **실행 중에 쓰이는** oneshot 만 기다린다(소스 대조 2026-11-08):
#   리뷰 큐 → broker 8102(초고, review_runner) · 색인기 → broker(합성, synth) — 8101 은 시작 때 게이트 1회
#   파견(autodispatch --drain) → task-queue 8101 · ax-projects(8103)를 실행 중 부르는 oneshot 은 없다.
#   [주의] 종전에는 셋 다 기다려, 마감 push 가 깨운 색인(510초)을 ax-projects 재기동이 기다렸다(#921 실경로).
WAIT_FOR: dict = {
    "ax-broker": ("ax-review-queue", "ax-indexer"),
    "ax-task-queue": ("ax-dispatch",),
    "ax-projects": (),
}
RC_DONE, RC_FAIL, RC_HANDOFF = 0, 1, 2
WAIT_MAX = 900                       # oneshot 대기 상한(초) — 넘기면 재기동하지 않고 멈춘다
WAIT_STEP = 10


def _git(repo: Path, *args: str) -> tuple[int, str]:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def _active_state(unit: str) -> str:
    r = subprocess.run(["systemctl", "show", f"{unit}.service", "-p", "ActiveState", "--value"],
                       capture_output=True, text=True, timeout=15)
    return (r.stdout or "").strip() if r.returncode == 0 else "?"


def _deliver(repo: Path) -> tuple[int, str]:
    env = dict(os.environ, AX_PROJECTS_ROOT=str(repo))
    r = subprocess.run([sys.executable, "-m", "master.client", "update"], cwd=str(repo), env=env,
                       capture_output=True, text=True, timeout=1800)
    return r.returncode, (r.stdout + r.stderr)


def _track(issue_id: int, project: str):
    from master.context_search.paths import resolve
    from master.context_synth import issue_track as it
    return it.current(Path(resolve(project).root), issue_id)


def _lock(project: str):
    from master import issue_lock
    return issue_lock.current(issue_lock.default_root(project))


def _freshness():
    from master import service_freshness as F
    return F.check()


def _restart(unit: str):
    from master import service_restart
    return service_restart.restart(unit)


def _note(issue_id: int, notes: str) -> str:
    from master import issue_infra as INF
    return INF.default_noter(issue_id, notes=notes)


@dataclass
class Deps:
    """대역 주입 자리 — 검사가 실제 systemctl·배달·Redmine 을 건드리지 않게 한다."""
    git: Callable = _git
    track: Callable = _track
    lock: Callable = _lock
    freshness: Callable = _freshness
    restart: Callable = _restart
    active_state: Callable = _active_state
    deliver: Callable = _deliver
    note: Callable = _note
    sleep: Callable = time.sleep


@dataclass
class Result:
    rc: int = RC_FAIL
    lines: list = field(default_factory=list)
    restarted: list = field(default_factory=list)
    head: str = ""


def run(issue_id: int, *, project: str = "AXCluster", repo: Path | None = None, dry_run: bool = False,
        deps: Deps | None = None, out=print) -> Result:
    d = deps or Deps()
    repo = Path(repo or REPO)
    res = Result()

    def say(step: str, msg: str) -> None:
        line = f"[wrapup] #{issue_id} {step}: {msg}"
        res.lines.append(line)
        out(line)

    def fail(step: str, msg: str) -> Result:
        say(step, f"[중요] 멈춘다 — {msg}")
        res.rc = RC_FAIL
        return res

    # ① 마감 확인
    try:
        track = d.track(issue_id, project)
    except Exception as e:                                          # noqa: BLE001
        return fail("finish", f"마감 추적 기록을 읽지 못했다 ({type(e).__name__}: {e})")
    if not track or not track.get("end"):
        return fail("finish", "마감 추적 기록이 없다 — `ax-projects:issue_finish_tool(confirm=True)` 가 먼저다")
    end = str(track["end"])
    try:
        lk = d.lock(project)
    except Exception as e:                                          # noqa: BLE001
        return fail("finish", f"일감 잠금을 읽지 못했다 ({type(e).__name__}: {e})")
    if lk and int(lk.get("issue_id", -1)) == int(issue_id):
        return fail("finish", f"#{issue_id} 잠금이 아직 활성이다 — 마감(finish)이 끝나지 않았다")
    say("finish", f"마감 추적 회차 {track.get('round')} · 끝 커밋 {end[:12]}")

    # ② 저장소 확인
    d.git(repo, "fetch", "-q", "origin")
    rc, branch = d.git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if rc or branch != "main":
        return fail("repo", f"운영 저장소가 main 이 아니다 ({branch})")
    rc, dirty = d.git(repo, "status", "--porcelain")
    if rc or dirty:
        return fail("repo", f"운영 저장소가 깨끗하지 않다 ({len(dirty.splitlines())}건)")
    _, head = d.git(repo, "rev-parse", "HEAD")
    _, origin = d.git(repo, "rev-parse", "origin/main")
    if head != origin:
        return fail("repo", f"main({head[:12]}) ≠ origin/main({origin[:12]}) — push·pull 이 먼저다")
    rc, _ = d.git(repo, "merge-base", "--is-ancestor", end, "HEAD")
    if rc:
        return fail("repo", f"끝 커밋 {end[:12]} 이 main 에 없다")
    res.head = head
    say("repo", f"main=origin/main={head[:12]} · 깨끗함")

    # ③ 신선도 판정
    try:
        verdicts = d.freshness()
    except Exception as e:                                          # noqa: BLE001
        return fail("fresh", f"서비스 신선도를 재지 못했다 ({type(e).__name__}: {e})")
    unknown = [v for v in verdicts if v.why]
    if unknown:
        return fail("fresh", "판정 불가 — " + " · ".join(f"{v.unit}: {v.why}" for v in unknown))
    targets = [v.unit for v in verdicts if v.stale or v.dep_changed]
    for v in verdicts:
        tag = "[중요] 옛 코드" if v.stale else ("[주의] 의존 변경" if v.dep_changed else
                                              (f"[주의] 의존 판정 불가({v.dep_why})" if v.dep_why else "최신"))
        say("fresh", f"{v.unit}: {tag}")

    # ④ 재기동 — 판정된 것만
    if targets and dry_run:
        say("restart", f"(dry-run) 재기동 대상 {targets}")
    elif targets:
        waited = 0
        watch = sorted({o for t in targets for o in WAIT_FOR.get(t, ONESHOTS)})   # 모르는 상주는 전부 기다린다
        say("restart", f"기다릴 oneshot {watch or '없음'} (대상 {targets})")
        while True:
            busy = [u for u in watch if d.active_state(u) in ("active", "activating", "deactivating")]
            if not busy:
                break
            if waited >= WAIT_MAX:
                return fail("restart", f"oneshot 이 {WAIT_MAX}초 넘게 돈다 {busy} — 재기동하지 않았다")
            say("restart", f"oneshot 실행 중 {busy} — {WAIT_STEP}초 대기(누적 {waited}초)")
            d.sleep(WAIT_STEP)
            waited += WAIT_STEP
        for unit in targets:
            try:
                before, after = d.restart(unit)
            except Exception as e:                                  # noqa: BLE001
                return fail("restart", f"{unit} 재기동 실패 ({type(e).__name__}: {e})")
            res.restarted.append((unit, after.get("ExecMainStartTimestamp", "")))
            say("restart", f"{unit}: {before.get('ExecMainStartTimestamp', '?')} → "
                           f"{after.get('ExecMainStartTimestamp', '?')} · {after.get('ActiveState', '?')}")
        try:
            again = [v for v in d.freshness() if v.unit in targets]
        except Exception as e:                                      # noqa: BLE001
            return fail("restart", f"재기동 뒤 신선도를 재지 못했다 ({type(e).__name__}: {e})")
        left = [v.unit for v in again if v.stale or v.dep_changed or v.why]
        if left:
            return fail("restart", f"재기동 뒤에도 판정이 남았다 {left}")
        say("restart", f"재기동 뒤 판정 깨끗 {targets}")
    else:
        say("restart", "재기동 대상 없음")

    # ⑤ 인수인계 확인 — 배달 전에
    rc, commits = d.git(repo, "log", "--format=%h", f"{end}..HEAD", "--", HANDOFF)
    if rc or not commits.strip():
        say("handoff", f"인수인계서 대기 — 끝 커밋 {end[:12]} 뒤 `{HANDOFF}` 커밋이 main 에 없다. "
                       "배달하지 않았다(배달 뒤 커밋하면 워커가 뒤처진다 #916). "
                       "인수인계서 커밋·push 뒤 같은 명령을 다시 실행하면 배달부터 이어진다")
        res.rc = RC_HANDOFF
        # `#922` — rc 2 에서도 그때까지의 판정·재기동을 남긴다(재실행 노트는 그 회차 것만 적는다)
        if not dry_run:
            restarted = ", ".join(f"{u} {t}" for u, t in res.restarted) or "없음"
            try:
                got = d.note(issue_id, f"마감 뒤 단계(`master.issue_wrapup`) 1단계: main {head[:12]} · "
                                       f"재기동 {restarted} · 인수인계서 대기(배달 전 정지, rc 2).")
                if isinstance(got, str) and got.startswith("[주의]"):
                    say("note", f"[주의] Redmine 노트 실패 — {got}")
                else:
                    say("note", "Redmine 노트 남김(인수인계 대기)")
            except Exception as e:                                  # noqa: BLE001
                say("note", f"[주의] Redmine 노트 실패 ({type(e).__name__}: {e})")
        return res
    say("handoff", f"인수인계서 커밋 {commits.split()[0]} (끝 커밋 뒤)")

    # ⑥ 배달
    if dry_run:
        say("deliver", "(dry-run) master.client update 생략")
        res.rc = RC_DONE
        return res
    rc, text = d.deliver(repo)
    tail = " · ".join(ln.strip() for ln in text.splitlines()[-3:] if ln.strip())
    if rc:
        return fail("deliver", f"master.client update rc={rc} — {tail[-300:]}")
    say("deliver", f"master.client update rc0 — {tail[-200:]}")

    # ⑦ 기록
    restarted = ", ".join(f"{u} {t}" for u, t in res.restarted) or "없음"
    note = (f"마감 뒤 단계(`master.issue_wrapup`, 공용 규칙 §1.9): main {head[:12]} · "
            f"재기동 {restarted} · 배달 master.client update rc0.")
    try:
        got = d.note(issue_id, note)
    except Exception as e:                                          # noqa: BLE001
        return fail("note", f"Redmine 노트 실패 ({type(e).__name__}: {e}) — 배달·재기동은 끝났다")
    if isinstance(got, str) and got.startswith("[주의]"):
        return fail("note", f"Redmine 노트 실패 — {got} — 배달·재기동은 끝났다")
    say("note", "Redmine 노트 남김")
    res.rc = RC_DONE
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m master.issue_wrapup",
                                 description="일감 마감 뒤 단계 — 신선도 판정·재기동·인수인계 확인·배달·기록 (#921)")
    ap.add_argument("issue_id", type=int)
    ap.add_argument("--project", default="AXCluster")
    ap.add_argument("--dry-run", action="store_true", help="판정·확인만 하고 재기동·배달·노트는 하지 않는다")
    a = ap.parse_args(argv)
    return run(a.issue_id, project=a.project, dry_run=a.dry_run).rc


if __name__ == "__main__":
    sys.exit(main())
