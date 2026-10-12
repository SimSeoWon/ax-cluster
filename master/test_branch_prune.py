"""`#787` ①② — 종결 work·전진분 서브 브랜치 정리. [중요] **실제 git + 실제 pre-push 훅**으로 돈다.

임시 bare 원격 + 클론에 `gitea-write` remote 를 달고 `attempt.install_hook` 으로 **원본 훅**
(`master/work/pre_push_hook.sh`)을 설치한다. 큐는 주입 대역이다(HTTP 없음).

    ① 훅 — 무관한 미병합 삭제는 여전히 거부 · 예외 변수는 지목한 work 하나만 · 이상한 값은 무효
    ② 훅 — `task/<W>/r<N>/*` 는 **자기** `task/<W>/base` 에서 도달 가능할 때만
    ③ `cleanup.apply_terminal` — 종결 work 만 지우고 보존 ref·노트에 팁 해시 · 재실행은 0건(멱등)
    ④ push 직전 큐 재확인 — 그새 열렸으면 안 지운다 · 낡은 훅이면 전부 건너뛴다
    ⑤ `review.advance_work(confirm=True)` — 이번 라운드 머지분만 지우고 노트에 싣는다
    ⑥ `main` 도달 가능 삭제(finalize 경로)는 그대로 통과
    ⑦ `autodispatch.drain(catchup=True)` 기본 배선 — 실제 sweep·apply·원격 삭제와 멱등
    ⑧ `sweep_terminal` 보존 줄은 (work, 사유)마다 한 번 · 사유가 바뀌면 다시 · 상태 실패면 찍고 알린다
    ⑨ `#821` 인프라 판단 불가 조각 — ⑦ 전진이 머지하지 않고 노트·요약에 따로 적는다

[중요] 보존 고지 상태(`AX_PRUNE_STATE_DIR`)는 이 파일이 임시 디렉토리로 돌린다 — 홈의
`~/.cache/ax-dispatch/` 를 건드리지 않는다.

`.venv/bin/python master/test_branch_prune.py`
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import attempt as A                              # noqa: E402
from master.work import autodispatch as AD                         # noqa: E402
from master.work import cleanup as CL                              # noqa: E402
from master.work import review as R                                # noqa: E402

PASS = FAIL = 0
REMOTE = "gitea-write"
WA = "20261010_0335_wa_aaaa1111"      # cancelled · 조각 전부 terminal → 지운다
WB = "20261010_0400_wb_bbbb2222"      # cancelled 이지만 조각 하나가 아직 pending
WC = "20261010_0500_wc_cccc3333"      # in_progress
WD = "20261010_0600_wd_dddd4444"      # 전진 대상
WX = "20261010_0700_wx_eeee5555"      # 큐에 없는 무관한 work
# 🔴 `#821` (사용자 결정 2026-10-13) — 반려 work 은 조각이 전부 terminal 이어도 **지우지 않는다**.
#    종전 WA 가 rejected 였고 그 삭제를 못박았다 — 그 계약이 뒤집혀 WA 를 cancelled 로 옮겼다.
WR = "20261010_0800_wr_ffff6666"      # rejected · 성공+실패 조각 → 보존


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _run(cwd: Path, *args: str, env=None, ok=True) -> tuple:
    e = {k: v for k, v in os.environ.items() if k != CL.TERMINAL_WORK_ENV}
    e.update(env or {})
    r = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(cwd), *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=e)
    if ok and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} rc={r.returncode}: {r.stderr}")
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


@dataclass
class Paths:
    root: Path
    name: str = "Proj"

    @property
    def repo(self) -> Path:
        return self.root / "repo"


class Fx:
    def __init__(self, tmp: Path):
        self.origin = tmp / "origin.git"
        self.paths = Paths(root=tmp / "proj")
        self.paths.root.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.paths.repo)], check=True)
        self.repo = self.paths.repo
        _run(self.repo, "remote", "add", REMOTE, str(self.origin))
        self.commit("Source/base.cpp", "// base\n", "base")
        _run(self.repo, "push", "-q", REMOTE, "HEAD:refs/heads/main")
        _run(self.repo, "fetch", "-q", REMOTE)
        self.main = self.head()
        A.install_hook(self.paths)

    def head(self) -> str:
        return _run(self.repo, "rev-parse", "HEAD")[1]

    def commit(self, rel: str, text: str, msg: str) -> str:
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        _run(self.repo, "add", "-A")
        _run(self.repo, "commit", "-q", "-m", msg)
        return self.head()

    def branch_at(self, ref: str, start: str, rel: str, text: str) -> str:
        """`start` 에서 갈라 커밋 하나를 얹고 원격 `ref` 로 push. 팁을 돌려준다."""
        _run(self.repo, "checkout", "-q", "--detach", start)
        tip = self.commit(rel, text, f"on {ref}")
        _run(self.repo, "push", "-q", REMOTE, f"{tip}:refs/heads/{ref}")
        return tip

    def remote_refs(self) -> dict:
        out = _run(self.repo, "ls-remote", "--heads", REMOTE)[1]
        return {ln.split()[1][len("refs/heads/"):]: ln.split()[0]
                for ln in out.splitlines() if len(ln.split()) == 2}

    def delete(self, ref: str, env=None) -> tuple:
        return _run(self.repo, "push", REMOTE, "--delete", ref, env=env, ok=False)


class FakeQueue:
    def __init__(self, works: dict, tasks: dict):
        self.works, self.tasks, self.calls, self.notes = works, tasks, [], []

    def __call__(self, method, path, payload=None):
        self.calls.append((method, path))
        if method == "GET" and path.startswith("/api/v1/works?"):
            return list(self.works.values())
        if method == "GET" and path.startswith("/api/v1/works/"):
            wid = path.rsplit("/", 1)[1]
            return {"work": self.works.get(wid) or {}, "tasks": self.tasks.get(wid) or []}
        if method == "POST" and path == "/api/v1/redmine/note":
            self.notes.append(payload)
            return {"ok": True}
        raise AssertionError(f"예상 밖 호출 {method} {path}")


def _setup_terminal(fx: Fx) -> dict:
    t = {}
    for w in (WA, WB, WC, WX, WR):
        t[f"task/{w}/base"] = fx.branch_at(f"task/{w}/base", fx.main, f"Source/{w}.h", "// skel\n")
        t[f"task/{w}/r1/p1"] = fx.branch_at(f"task/{w}/r1/p1", t[f"task/{w}/base"],
                                            f"Source/{w}.cpp", "// body\n")
    return t


def _queue() -> FakeQueue:
    works = {WA: {"work_id": WA, "merge_status": "cancelled", "project": "Proj", "redmine_issue_id": 901},
             WR: {"work_id": WR, "merge_status": "rejected", "project": "Proj", "redmine_issue_id": 903},
             WB: {"work_id": WB, "merge_status": "cancelled", "project": "Proj", "redmine_issue_id": 902},
             WC: {"work_id": WC, "merge_status": "in_progress", "project": "Proj"}}
    tasks = {WA: [{"task_id": "p1", "status": "cancelled"}],
             WR: [{"task_id": "p1", "status": "verified"}, {"task_id": "p2", "status": "failed"}],
             WB: [{"task_id": "p1", "status": "cancelled"}, {"task_id": "p2", "status": "pending"}],
             WC: [{"task_id": "p1", "status": "claimed"}]}
    return FakeQueue(works, tasks)


# ── ①② 훅 그 자체 ──────────────────────────────────────────────────────────

def test_hook_direct():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        check("훅 원본과 같다(state ok)", A.hook_status(fx.paths)["state"] == A.STATE_OK)
        t = _setup_terminal(fx)
        rc, out = fx.delete(f"task/{WX}/base")
        check("[중요] 무관한 미병합 삭제는 여전히 거부", rc != 0 and "pre-push 거부" in out, out[-200:])
        rc, out = fx.delete(f"task/{WB}/base", env={CL.TERMINAL_WORK_ENV: WA})
        check("[중요] work A 허용이 work B 를 통과시키지 않는다", rc != 0, out[-200:])
        rc, out = fx.delete("main", env={CL.TERMINAL_WORK_ENV: WA})
        check("[중요] 예외 변수로 main 은 못 지운다", rc != 0, out[-200:])
        for bad in ("", "*", f"{WA}/..", "../x", f"{WA}/r1", "-x"):
            rc, out = fx.delete(f"task/{WA}/r1/p1", env={CL.TERMINAL_WORK_ENV: bad})
            check(f"이상한 예외 값 {bad!r} 은 무효", rc != 0, out[-160:])
        rc, out = fx.delete(f"task/{WA}/r1/p1", env={CL.TERMINAL_WORK_ENV: WA})
        check("지목한 work 의 r1 조각은 지워진다", rc == 0, out[-200:])
        check("  허용 줄을 남긴다", "#787" in out, out[-200:])
        check("  원격에서 사라졌다", f"task/{WA}/r1/p1" not in fx.remote_refs())
        check("  다른 work 은 그대로", fx.remote_refs().get(f"task/{WB}/base") == t[f"task/{WB}/base"])

        # ② 서브 브랜치 — 자기 base 에서 도달 가능할 때만
        base = fx.branch_at(f"task/{WD}/base", fx.main, "Source/D.h", "// d skel\n")
        p1 = fx.branch_at(f"task/{WD}/r1/p1", base, "Source/D1.cpp", "// d1\n")
        p2 = fx.branch_at(f"task/{WD}/r1/p2", base, "Source/D2.cpp", "// d2\n")
        _run(fx.repo, "checkout", "-q", "--detach", base)
        _run(fx.repo, "merge", "-q", "--no-ff", p1, "-m", "advance")
        _run(fx.repo, "push", "-q", REMOTE, f"HEAD:refs/heads/task/{WD}/base")
        _run(fx.repo, "fetch", "-q", REMOTE)
        rc, out = fx.delete(f"task/{WD}/r1/p2")
        check("[중요] base 에 안 들어간 서브 브랜치는 거부", rc != 0, out[-200:])
        # 다른 work 의 이름으로 같은 커밋을 올려도 **그 work 의 base** 로 판정한다
        _run(fx.repo, "push", "-q", REMOTE, f"{p1}:refs/heads/task/{WX}/r1/stolen")
        _run(fx.repo, "fetch", "-q", REMOTE)
        rc, out = fx.delete(f"task/{WX}/r1/stolen")
        check("[중요] 남의 base 에서만 도달 가능하면 거부", rc != 0, out[-200:])
        rc, out = fx.delete(f"task/{WD}/r1/p1")
        check("base 에서 도달 가능한 서브 브랜치는 통과", rc == 0, out[-200:])
        rc, out = fx.delete(f"task/{WD}/base")
        check("[중요] base 자체는 예외 밖 — 거부", rc != 0, out[-200:])

        # ⑥ finalize 경로 — main 에서 도달 가능하면 예전처럼 통과
        merged = fx.branch_at("task/old/merged", fx.main, "Source/m.cpp", "// m\n")
        # 사람이 main 을 옮긴 것을 흉내낸다(가드 밖의 자리 — 픽스처라 --no-verify)
        _run(fx.repo, "push", "-q", "--no-verify", REMOTE, f"{merged}:refs/heads/main")
        _run(fx.repo, "fetch", "-q", REMOTE)
        rc, out = fx.delete("task/old/merged")
        check("main 도달 가능 삭제는 그대로 통과(finalize 경로)", rc == 0, out[-200:])
        check("  예외 줄 없이 조용히 통과", "#787" not in out, out[-200:])


# ── #396 판정 기준은 원격의 실제 팁 ────────────────────────────────────────────

def _advance_main_elsewhere(fx: Fx, tmp: Path, branch: str) -> str:
    """다른 클론에서 `branch` 를 main 에 머지해 올린다 — fx 클론의 추적 ref 는 그대로(낡는다)."""
    other = tmp / "other"
    subprocess.run(["git", "clone", "-q", str(fx.origin), str(other)], check=True)
    _run(other, "checkout", "-q", "main")
    _run(other, "merge", "-q", "--no-ff", f"origin/{branch}", "-m", f"merge {branch}")
    _run(other, "push", "-q", "origin", "HEAD:refs/heads/main")
    return _run(other, "rev-parse", "HEAD")[1]


def test_stale_tracking_396():
    track = f"refs/remotes/{REMOTE}/main"
    # ① 추적 ref 가 낡았고, 실제 main 의 머지 커밋은 이 클론에 아직 없다 → ls-remote + fetch 로 통과
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        fx.branch_at("task/s1/r1/p1", fx.main, "Source/s1.cpp", "// s1\n")
        real = _advance_main_elsewhere(fx, Path(tmp), "task/s1/r1/p1")
        stale = _run(fx.repo, "rev-parse", track)[1]
        check("픽스처: 추적 ref 가 낡았다", stale == fx.main and stale != real, stale)
        rc, _ = _run(fx.repo, "cat-file", "-e", f"{real}^{{commit}}", ok=False)
        check("픽스처: 실제 팁 커밋이 로컬에 없다", rc != 0)
        rc, out = fx.delete("task/s1/r1/p1")
        check("[중요] #396 낡은 추적 ref 라도 실제 main 에 병합됐으면 삭제 허용", rc == 0, out[-300:])
        check("  추적 ref 가 실제 팁으로 갱신됐다", _run(fx.repo, "rev-parse", track)[1] == real)

    # ② 추적 ref 가 낡았고 실제 팁 커밋은 로컬에 있다 → fetch 없이 실제 팁으로 판정
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        tip = fx.branch_at("task/s2/r1/p1", fx.main, "Source/s2.cpp", "// s2\n")
        _run(fx.repo, "push", "-q", "--no-verify", REMOTE, f"{tip}:refs/heads/main")
        _run(fx.repo, "update-ref", track, fx.main)          # 낡게 되돌린다
        rc, out = fx.delete("task/s2/r1/p1")
        check("[중요] #396 실제 팁이 로컬에 있으면 그것으로 판정해 허용", rc == 0, out[-300:])

        # ③ 거부 메시지에 판정에 쓴 ref·해시, 낡은 추적 ref 의 해시
        un = fx.branch_at("task/s2/r1/p2", fx.main, "Source/s2b.cpp", "// s2b\n")
        _run(fx.repo, "update-ref", track, fx.main)
        rc, out = fx.delete("task/s2/r1/p2")
        check("[중요] 미병합은 여전히 거부", rc != 0 and "pre-push 거부" in out, out[-300:])
        check("  거부 메시지에 판정 ref 와 실제 팁 해시",
              f"{REMOTE} refs/heads/main = {tip}" in out, out[-400:])
        check("  낡은 추적 ref 와 그 해시를 따로 찍는다", f"{track} = {fx.main}" in out and "낡았다" in out,
              out[-400:])
        check("  지우려던 팁 해시", un in out, out[-400:])

    # ④ 원격을 못 읽으면 거부(fail-closed) — fetch URL 만 끊고 push URL 은 살린다
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        un = fx.branch_at("task/s3/r1/p1", fx.main, "Source/s3.cpp", "// s3\n")
        ok_tip = fx.branch_at("task/s3/r1/p2", fx.main, "Source/s3b.cpp", "// s3b\n")
        _run(fx.repo, "push", "-q", "--no-verify", REMOTE, f"{ok_tip}:refs/heads/main")
        _run(fx.repo, "config", f"remote.{REMOTE}.pushurl", str(fx.origin))
        _run(fx.repo, "config", f"remote.{REMOTE}.url", str(Path(tmp) / "missing.git"))
        rc, out = fx.delete("task/s3/r1/p1")
        check("[중요] #396 원격 불통 + 미병합 → 거부", rc != 0 and "pre-push 거부" in out, out[-300:])
        check("  메시지에 추적 ref 이름과 해시", f"{track} = {ok_tip}" in out, out[-400:])
        check("  사유가 ls-remote 실패 · fail-closed", "ls-remote" in out and "fail-closed" in out,
              out[-400:])
        rc, out = fx.delete("task/s3/r1/p2")
        check("[중요] 원격 불통이면 로컬 추적 ref 상 병합분도 판정하지 않는다(보존)", rc != 0, out[-300:])
        check("  원격에 그대로 남았다", "task/s3/r1/p1" in _remote_heads(fx.origin)
              and "task/s3/r1/p2" in _remote_heads(fx.origin))
        # ⓑ 는 원격 판정과 무관하게 그대로 돈다
        rc, out = fx.delete("task/s3/r1/p1", env={CL.TERMINAL_WORK_ENV: "s3"})
        check("  예외 ⓑ 는 원격 불통이어도 그대로", rc == 0 and "#787" in out, out[-300:])

    # ⑤ 한 push 에 삭제가 여럿이어도 원격 목록은 한 번만 읽고, 루프가 끝까지 돈다
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        a = fx.branch_at("task/s5/r1/p1", fx.main, "Source/s5a.cpp", "// a\n")
        _run(fx.repo, "checkout", "-q", "--detach", a)
        b = fx.commit("Source/s5b.cpp", "// b\n", "b")
        _run(fx.repo, "push", "-q", REMOTE, f"{b}:refs/heads/task/s5/r1/p2")
        _run(fx.repo, "push", "-q", "--no-verify", REMOTE, f"{b}:refs/heads/main")
        _run(fx.repo, "update-ref", track, fx.main)
        trace = Path(tmp) / "trace.log"           # 훅이 stderr 를 버리므로 파일로 받는다
        rc, out = _run(fx.repo, "push", REMOTE, "--delete", "task/s5/r1/p1", "task/s5/r1/p2",
                       env={"GIT_TRACE": str(trace)}, ok=False)
        tlog = trace.read_text(encoding="utf-8", errors="replace") if trace.exists() else ""
        check("삭제 둘을 한 push 로 — 둘 다 허용", rc == 0 and not ({"task/s5/r1/p1", "task/s5/r1/p2"}
              & _remote_heads(fx.origin)), out[-300:])
        n = sum(1 for ln in tlog.splitlines()
                if "built-in: git ls-remote" in ln and "--heads" in ln and "-q" not in ln.split())
        check("[중요] 원격 목록 읽기는 훅 실행당 한 번", n == 1, str(n))

    # ⑥ 삭제가 없는 push 는 원격을 따로 읽지 않는다 — 불통이어도 통과
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        _run(fx.repo, "config", f"remote.{REMOTE}.pushurl", str(fx.origin))
        _run(fx.repo, "config", f"remote.{REMOTE}.url", str(Path(tmp) / "missing.git"))
        tip = fx.commit("Source/s4.cpp", "// s4\n", "s4")
        rc, out = _run(fx.repo, "push", REMOTE, f"{tip}:refs/heads/task/s4/base", ok=False)
        check("삭제 없는 push 는 원격 읽기 없이 통과", rc == 0, out[-300:])


def _remote_heads(origin: Path) -> set:
    out = subprocess.run(["git", "-C", str(origin), "for-each-ref", "--format=%(refname:short)",
                          "refs/heads/"], capture_output=True, text=True).stdout
    return set(out.split())


# ── ③④ 종결 work 정리 ──────────────────────────────────────────────────────

def test_apply_terminal():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        t = _setup_terminal(fx)
        q = _queue()
        plan = CL.survey_terminal(fx.paths, api=q, remote=REMOTE)
        txt = plan.render()
        ids = {w.work_id: w for w in plan.works}
        check("후보는 종결 work 셋(A·B·R)", set(ids) == {WA, WB, WR}, str(set(ids)))
        check("🔴 #821 반려 R 은 보존 — 사유가 계획에 실린다",
              ids[WR].skip == CL.REJECTED_KEEP_REASON and "#821" in ids[WR].skip, ids[WR].skip)
        check("  드라이런에 R 의 [보존] 줄", f"[보존] task/{WR}/base" in txt, txt)
        check("[중요] B 는 pending 조각 때문에 보존", "pending" in ids[WB].skip or "p2" in ids[WB].skip,
              ids[WB].skip)
        check("드라이런 출력에 ref·팁·상태", f"task/{WA}/base @ {t[f'task/{WA}/base']}" in txt
              and "cancelled" in txt, txt)
        check("[중요] survey 는 원격을 바꾸지 않는다", fx.remote_refs().get(f"task/{WA}/base")
              == t[f"task/{WA}/base"])
        check("[중요] survey 는 노트를 안 쓴다", not q.notes)

        logs = []
        done = CL.apply_terminal(fx.paths, plan, api=q, logf=logs.append)
        refs = fx.remote_refs()
        check("A 의 ref 둘이 지워졌다", f"task/{WA}/base" not in refs and f"task/{WA}/r1/p1" not in refs,
              str(done))
        check("[중요] B·C·X·R 은 그대로", all(refs.get(f"task/{w}/base") == t[f"task/{w}/base"]
                                            for w in (WB, WC, WX, WR)), str(refs))
        check("🔴 #821 반려 R 의 서브 브랜치도 그대로",
              refs.get(f"task/{WR}/r1/p1") == t[f"task/{WR}/r1/p1"], str(refs))
        check("  R 은 건너뜀 목록에 보존 사유로", (WR, CL.REJECTED_KEEP_REASON) in done["skipped"],
              str(done["skipped"]))
        check("실패 0", not done["failed"], str(done["failed"]))
        kept = _run(fx.repo, "rev-parse", f"{CL.PRUNED_NS}/task/{WA}/base")[1]
        check("[중요] 지우기 전에 로컬 보존 ref 가 팁과 같다", kept == t[f"task/{WA}/base"], kept)
        check("저널 줄에 ref·팁·복원 명령", any(t[f"task/{WA}/base"] in m and "복원" in m for m in logs),
              "\n".join(logs))
        check("레드마인 노트 하나 — A 이슈", len(q.notes) == 1 and q.notes[0]["issue_id"] == 901,
              str(q.notes))
        body = q.notes[0]["notes"] if q.notes else ""
        check("  노트에 두 팁 해시", t[f"task/{WA}/base"] in body and t[f"task/{WA}/r1/p1"] in body, body)
        check("  노트에 프로젝트 태그", q.notes and q.notes[0].get("project") == "Proj")
        # 복원 가능 — 보존된 해시로 되살린다
        rc, out = _run(fx.repo, "push", REMOTE,
                       f"{t[f'task/{WA}/base']}:refs/heads/task/{WA}/base", ok=False)
        check("해시로 복원된다", rc == 0 and fx.remote_refs().get(f"task/{WA}/base")
              == t[f"task/{WA}/base"], out[-200:])
        fx.delete(f"task/{WA}/base", env={CL.TERMINAL_WORK_ENV: WA})

        # 멱등 — 남은 것이 없으면 아무것도 안 한다
        q2 = _queue()
        plan2 = CL.survey_terminal(fx.paths, api=q2, remote=REMOTE)
        d2 = CL.apply_terminal(fx.paths, plan2, api=q2, logf=lambda m: None)
        check("재실행은 0건(멱등)", not d2["deleted"] and not q2.notes, str(d2))


def test_requeue_and_stale_hook():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        t = _setup_terminal(fx)
        q = _queue()
        plan = CL.survey_terminal(fx.paths, api=q, remote=REMOTE)
        q.works[WA] = dict(q.works[WA], merge_status="in_progress")      # 그새 다시 열렸다
        done = CL.apply_terminal(fx.paths, plan, api=q, logf=lambda m: None)
        check("[중요] push 직전 재확인 — 열린 work 는 안 지운다",
              not done["deleted"] and fx.remote_refs().get(f"task/{WA}/base") == t[f"task/{WA}/base"],
              str(done))

        q = _queue()
        plan = CL.survey_terminal(fx.paths, api=q, remote=REMOTE)
        hook = A.hook_target(fx.paths)
        hook.write_text(hook.read_text(encoding="utf-8") + "\n# 낡은 사본\n", encoding="utf-8")
        check("훅이 stale 로 읽힌다", A.hook_status(fx.paths)["state"] == A.STATE_STALE)
        done = CL.apply_terminal(fx.paths, plan, api=q, logf=lambda m: None)
        check("[중요] 낡은 훅이면 전부 건너뛴다", not done["deleted"]
              and any(w == "*" for w, _ in done["skipped"]), str(done))
        check("  원격 그대로", fx.remote_refs().get(f"task/{WA}/base") == t[f"task/{WA}/base"])

        # 큐를 못 읽으면 아무것도 판정하지 않는다
        def broken(*a, **k):
            raise RuntimeError("queue down")
        p3 = CL.survey_terminal(fx.paths, api=broken, remote=REMOTE)
        check("큐 불통이면 판정 0 · 오류 문장", not p3.works and "큐를 못 읽었다" in p3.error, p3.error)


def test_catchup_prunes_terminal():
    """운영 큐·레지스트리·스풀 대신 픽스처를 연결하되 정리 배선과 Git 은 실제로 돈다."""
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        tips = _setup_terminal(fx)
        q = _queue()
        before = fx.remote_refs()
        resolved = []

        def resolve(name):
            if name not in ("", "Proj"):
                raise AssertionError(f"픽스처 밖 프로젝트: {name!r}")
            resolved.append(name)
            return fx.paths

        # catchup 의 열린 work 경로는 파견·통합을 하지 않는다. 종결 정리 함수는 감시만 한다.
        with patch("master.projects.config.Registry.load", return_value=SimpleNamespace(names=["Proj"])), \
             patch("master.context_search.paths.resolve", side_effect=resolve), \
             patch.object(AD, "_read_triggers", return_value=[]), \
             patch.object(AD, "hold_active", return_value=(False, "")), \
             patch.object(AD, "dispatch", return_value={"dispatched": False}) as dispatch, \
             patch.object(AD, "needs_integration", return_value=(False, "fixture")), \
             patch.object(AD, "_log"), \
             patch.object(CL, "sweep_terminal", wraps=CL.sweep_terminal) as sweep, \
             patch.object(CL, "apply_terminal", wraps=CL.apply_terminal) as apply:
            idle = AD.drain(catchup=False, api=q)
            check("catchup=False 는 실제 원격 그대로", fx.remote_refs() == before, str(idle))
            check("catchup=False 는 정리·큐·경로 조회 없음",
                  not sweep.called and not apply.called and not q.calls and not resolved)

            done = AD.drain(catchup=True, api=q)  # prune_fn=None: 운영 기본 배선을 그대로 사용
            check("catchup 기본 배선은 실제 sweep·apply 를 한 번 호출",
                  sweep.call_count == 1 and apply.call_count == 1)
            check("catchup 삭제 2건·정리 실패 0·파견 예외 0",
                  done.get("pruned") == 2 and done.get("prune_errors") == 0 and done["errors"] == 0,
                  str(done))
            check("catchup 은 마운트 경로를 실제 resolve 에 요청", "" in resolved, str(resolved))
            check("열린 work 만 파견 판정", [c.args[1] for c in dispatch.call_args_list] == [WC],
                  str(dispatch.call_args_list))
            refs = fx.remote_refs()
            deleted = {f"task/{WA}/base", f"task/{WA}/r1/p1"}
            check("catchup 원격에서 종결 A 만 삭제", refs == {r: t for r, t in before.items()
                                                                     if r not in deleted}, str(refs))
            check("catchup pending B·진행 C·unknown X·반려 R(#821) 의 모든 ref 보존",
                  all(refs.get(ref) == tip for ref, tip in tips.items() if ref not in deleted))
            for ref in sorted(deleted):
                kept = _run(fx.repo, "rev-parse", f"{CL.PRUNED_NS}/{ref}")[1]
                check(f"catchup 로컬 보존 ref {ref} 팁 일치", kept == tips[ref], kept)
            check("catchup 노트는 A 이슈 한 건·프로젝트 일치",
                  len(q.notes) == 1 and q.notes[0]["issue_id"] == 901
                  and q.notes[0].get("project") == "Proj", str(q.notes))
            body = q.notes[0]["notes"] if q.notes else ""
            check("catchup 노트에 삭제 ref·두 팁 해시",
                  all(ref in body and tips[ref] in body for ref in deleted), body)

            again = AD.drain(catchup=True, api=q)
            check("catchup 재실행 삭제 0·실패 0·추가 노트 없음",
                  again.get("pruned") == 0 and again.get("prune_errors") == 0
                  and again["errors"] == 0 and len(q.notes) == 1, str(again))
            check("catchup 재실행 원격 동일·apply 재호출 없음",
                  fx.remote_refs() == refs and sweep.call_count == 2 and apply.call_count == 1)


# ── ⑤ ⑺ 전진 뒤 서브 브랜치 정리 ─────────────────────────────────────────────

def test_advance_prunes_round_subbranches():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        base = fx.branch_at(f"task/{WD}/base", fx.main, "Source/D.h", "// d skel\n")
        p1 = fx.branch_at(f"task/{WD}/r1/p1", base, "Source/D1.cpp", "// d1\n")
        p2 = fx.branch_at(f"task/{WD}/r1/p2", base, "Source/D2.cpp", "// d2\n")
        tasks = [{"task_id": "p1", "status": "verified", "distribution_mode": "push", "round": 1},
                 {"task_id": "p2", "status": "verified", "distribution_mode": "push", "round": 1}]
        work = {"work_id": WD, "round": 1, "redmine_issue_id": 904, "distribution_mode": "push"}
        notes = []

        def api(method, path, payload=None):
            notes.append(payload)
            return {"ok": True}

        a = R.advance_work(fx.repo, work_id=WD, work=work, tasks=tasks, confirm=True, remote=REMOTE,
                           build_fn=lambda tree: {"passed": True, "summary": "ok"}, api=api)
        check("전진 성공", a.ok and a.pushed, a.summary)
        refs = fx.remote_refs()
        check("[중요] 이번 라운드 머지분 둘이 지워졌다",
              f"task/{WD}/r1/p1" not in refs and f"task/{WD}/r1/p2" not in refs, str(refs))
        check("[중요] 작업 브랜치(base)는 남았다", refs.get(f"task/{WD}/base") == a.head, str(refs))
        check("결과에 지운 ref·팁", sorted(a.deleted_subbranches) ==
              sorted([(f"task/{WD}/r1/p1", p1), (f"task/{WD}/r1/p2", p2)]), str(a.deleted_subbranches))
        body = (notes[0] or {}).get("notes", "") if notes else ""
        check("레드마인 노트에 지운 서브 브랜치·해시", p1 in body and p2 in body and "#787" in body, body)

        # 🔴 #787 실측 2026-10-10: 전진 뒤 서브 브랜치가 없어서 finalize 가 「durable 이 없다 — 통째 중단」.
        #    작업 브랜치의 `[ADVANCE]` 머지 커밋이 증거면 통과해야 한다 — main 에 두 조각이 다 들어간다.
        work_r = dict(work, merge_status="ready_for_review", target_branch=f"task/{WD}/base")
        # [주의] 이 픽스처의 원격은 가드(pre-push)가 main push 를 막는다 — 통합까지만 잰다(confirm=False).
        d = R.finalize_work(fx.repo, work_id=WD, work=work_r, tasks=tasks, confirm=False,
                            remote=REMOTE, api=lambda *a, **k: {"ok": True})
        check("[중요] 전진·정리 뒤 finalize 통합이 통과한다", not d.error and not d.pushed, d.error)
        check("  전진분으로 인정한 조각 둘", sorted(d.advanced_durables) ==
              sorted([f"task/{WD}/r1/p1", f"task/{WD}/r1/p2"]), str(d.advanced_durables))
        rc, files = _run(Path(d.tree), "ls-tree", "-r", "--name-only", "HEAD", ok=False)
        check("  통합 트리에 두 조각의 파일이 다 있다",
              "Source/D1.cpp" in files and "Source/D2.cpp" in files, files)

    # 증거 없는 누락은 여전히 통째 중단 — 다른 work 이름의 머지 커밋으로 통과하지 않는다
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        base = fx.branch_at(f"task/{WD}/base", fx.main, "Source/E.h", "// e skel\n")
        tasks = [{"task_id": "q1", "status": "verified", "distribution_mode": "push", "round": 1}]
        work_r = {"work_id": WD, "round": 1, "merge_status": "ready_for_review",
                  "target_branch": f"task/{WD}/base", "distribution_mode": "push"}
        d = R.finalize_work(fx.repo, work_id=WD, work=work_r, tasks=tasks, confirm=True,
                            remote=REMOTE, api=lambda *a, **k: {"ok": True})
        check("[중요] 전진 증거 없는 durable 누락은 여전히 중단", (not d.ok) and not d.pushed
              and "통째 중단" in (d.error or ""), d.error)
        check("  증거 판정은 제목이 정확히 같아야 한다",
              R.advanced_merge(fx.repo, REMOTE, f"task/{WD}/base", WD, f"task/{WD}/r1/q1") == "")


def test_prune_helper_keeps_unmerged_and_foreign():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        base = fx.branch_at(f"task/{WD}/base", fx.main, "Source/D.h", "// d skel\n")
        p1 = fx.branch_at(f"task/{WD}/r1/p1", base, "Source/D1.cpp", "// d1\n")
        p2 = fx.branch_at(f"task/{WD}/r1/p2", base, "Source/D2.cpp", "// d2\n")
        old = fx.branch_at(f"task/{WD}/r0leg", base, "Source/D3.cpp", "// d3\n")
        _run(fx.repo, "checkout", "-q", "--detach", base)
        _run(fx.repo, "merge", "-q", "--no-ff", p1, "-m", "advance")
        _run(fx.repo, "push", "-q", REMOTE, f"HEAD:refs/heads/task/{WD}/base")
        d, k = R.prune_merged_subbranches(
            fx.repo, work_id=WD, round_no=1, target=f"task/{WD}/base", remote=REMOTE,
            merged=[f"task/{WD}/r1/p1", f"task/{WD}/r1/p2", f"task/{WD}/r0leg", f"task/{WD}/r2/p9"])
        check("도달 가능분만 삭제", d == [(f"task/{WD}/r1/p1", p1)], str(d))
        kept = dict(k)
        check("[중요] 미병합은 보존", f"task/{WD}/r1/p2" in kept, str(k))
        check("[중요] 라운드 밖·옛 이름은 보존", f"task/{WD}/r0leg" in kept and f"task/{WD}/r2/p9" in kept,
              str(k))
        refs = fx.remote_refs()
        check("  원격: p2·옛 이름 그대로", refs.get(f"task/{WD}/r1/p2") == p2
              and refs.get(f"task/{WD}/r0leg") == old, str(refs))
        d, k = R.prune_merged_subbranches(fx.repo, work_id=WD, round_no=1, target="feature/x",
                                          merged=[f"task/{WD}/r1/p2"], remote=REMOTE)
        check("작업 브랜치가 task/<W>/base 가 아니면 손대지 않는다", not d and k, str(k))


# ── ⑧ 보존 줄은 한 번만 (`#821` 후속) ─────────────────────────────────────────

def test_sweep_kept_logged_once():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        _setup_terminal(fx)
        state = Path(tmp) / "state"

        def run(env_dir) -> list:
            logs = []
            with patch.dict(os.environ, {CL.PRUNE_STATE_ENV: str(env_dir)}):
                CL.sweep_terminal(fx.paths, api=_queue(), apply_=False, logf=logs.append)
            return logs

        def kept(logs, wid):
            return [m for m in logs if m.startswith(f"{wid}: 보존 — ")]

        first = run(state)
        check("1회차 — 반려 R 의 보존 줄", len(kept(first, WR)) == 1, "\n".join(first))
        check("  1회차 — pending B 의 보존 줄", len(kept(first, WB)) == 1, "\n".join(first))
        check("  상태 파일이 생겼다", (state / CL.PRUNE_STATE_FILE).exists())
        second = run(state)
        check("[중요] 2회차 — 같은 사유면 보존 줄 없음", not kept(second, WR) and not kept(second, WB),
              "\n".join(second))
        check("  2회차 — 상태 실패 줄 없음", not any("보존 고지 상태" in m for m in second),
              "\n".join(second))
        check("  2회차 — 정리 계획 줄은 그대로", any("정리 시작" in m for m in second), "\n".join(second))
        with patch.object(CL, "REJECTED_KEEP_REASON", "다른 보존 사유(시험)"):
            third = run(state)
        check("사유가 바뀌면 다시 찍는다", kept(third, WR) == [f"{WR}: 보존 — 다른 보존 사유(시험)"]
              and not kept(third, WB), "\n".join(third))
        fourth = run(state)
        check("  원래 사유로 돌아와도 다시 찍는다(바뀐 것이다)", len(kept(fourth, WR)) == 1,
              "\n".join(fourth))

        blocker = Path(tmp) / "blocker"
        blocker.write_text("파일이라 디렉토리를 못 만든다\n", encoding="utf-8")
        for n in (1, 2):
            bad = run(blocker / "sub")
            check(f"[중요] 상태 저장 불가 {n}회차 — 보존 줄은 그대로 찍힌다",
                  len(kept(bad, WR)) == 1 and len(kept(bad, WB)) == 1, "\n".join(bad))
            check(f"  상태 저장 불가 {n}회차 — 실패 한 줄",
                  sum("보존 고지 상태를 저장하지 못했다" in m for m in bad) == 1, "\n".join(bad))

        broken = Path(tmp) / "broken"
        broken.mkdir()
        (broken / CL.PRUNE_STATE_FILE).write_text("{깨진", encoding="utf-8")
        bad = run(broken)
        check("상태 읽기 실패 — 전부 찍고 한 줄 알린다", len(kept(bad, WR)) == 1
              and sum("보존 고지 상태를 읽지 못했다" in m for m in bad) == 1, "\n".join(bad))
        check("  읽기 실패 뒤 다시 저장돼 다음 회차는 조용하다", not kept(run(broken), WR))
        check("[중요] 원격은 그대로(apply_=False)", fx.remote_refs().get(f"task/{WR}/base") is not None)


# ── ⑨ `#821` 인프라 판단 불가 조각 — ⑦ 전진 표시 ─────────────────────────────

def test_advance_lists_infra_undecided():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        base = fx.branch_at(f"task/{WD}/base", fx.main, "Source/F.h", "// f skel\n")
        p1 = fx.branch_at(f"task/{WD}/r1/p1", base, "Source/F1.cpp", "// f1\n")
        p3 = fx.branch_at(f"task/{WD}/r1/p3", base, "Source/F3.cpp", "// f3\n")
        why = "인프라 서버 오동작 — 판단 불가 (verifier_exception)"
        tasks = [{"task_id": "p1", "status": "verified", "distribution_mode": "push", "round": 1},
                 {"task_id": "p3", "status": "failed", "distribution_mode": "push", "round": 1,
                  "infra_undecided": True, "fail_reason": why}]
        work = {"work_id": WD, "round": 1, "redmine_issue_id": 905, "distribution_mode": "push"}
        notes = []

        def api(method, path, payload=None):
            notes.append(payload)
            return {"ok": True}

        a = R.advance_work(fx.repo, work_id=WD, work=work, tasks=tasks, confirm=True, remote=REMOTE,
                           build_fn=lambda tree: {"passed": True, "summary": "ok"}, api=api)
        spool = f"responses/{WD}/p3.json"
        check("전진 성공 · 머지는 verified 하나", a.ok and a.pushed
              and a.merged == [f"task/{WD}/r1/p1"], a.summary)
        check("[중요] 표지 조각 브랜치는 머지·삭제되지 않았다",
              fx.remote_refs().get(f"task/{WD}/r1/p3") == p3, str(fx.remote_refs()))
        check("  p1 은 전진분으로 지워졌다", f"task/{WD}/r1/p1" not in fx.remote_refs()
              and (f"task/{WD}/r1/p1", p1) in a.deleted_subbranches)
        check("요약에 표지 조각·사유·상대 스풀", "p3" in a.summary and why in a.summary
              and spool in a.summary, a.summary)
        body = (notes[0] or {}).get("notes", "") if notes else ""
        check("레드마인 노트에 인프라 판단 불가 절", "## 인프라 판단 불가" in body and "p3" in body
              and why in body and f"`{spool}`" in body, body)
        check("  노트·요약에 임시(절대) 경로 없음", tmp not in body and tmp not in a.summary)


if __name__ == "__main__":
    # [중요] 보존 고지 상태가 홈(`~/.cache/ax-dispatch/`)에 쌓이지 않게 — 실행 동안만 임시 디렉토리
    _state_tmp = tempfile.TemporaryDirectory()
    os.environ[CL.PRUNE_STATE_ENV] = _state_tmp.name
    for fn in (test_hook_direct, test_stale_tracking_396, test_apply_terminal, test_requeue_and_stale_hook, test_catchup_prunes_terminal,
               test_advance_prunes_round_subbranches, test_prune_helper_keeps_unmerged_and_foreign,
               test_sweep_kept_logged_once, test_advance_lists_infra_undecided):
        try:
            fn()
        except Exception as e:                                    # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{fn.__name__} 예외 없이", False, f"{type(e).__name__}: {e}")
    print(f"\n{PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
