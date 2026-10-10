"""`#787` ①② — 종결 work·전진분 서브 브랜치 정리. [중요] **실제 git + 실제 pre-push 훅**으로 돈다.

임시 bare 원격 + 클론에 `gitea-write` remote 를 달고 `attempt.install_hook` 으로 **원본 훅**
(`master/work/pre_push_hook.sh`)을 설치한다. 큐는 주입 대역이다(HTTP 없음).

    ① 훅 — 무관한 미병합 삭제는 여전히 거부 · 예외 변수는 지목한 work 하나만 · 이상한 값은 무효
    ② 훅 — `task/<W>/r<N>/*` 는 **자기** `task/<W>/base` 에서 도달 가능할 때만
    ③ `cleanup.apply_terminal` — 종결 work 만 지우고 보존 ref·노트에 팁 해시 · 재실행은 0건(멱등)
    ④ push 직전 큐 재확인 — 그새 열렸으면 안 지운다 · 낡은 훅이면 전부 건너뛴다
    ⑤ `review.advance_work(confirm=True)` — 이번 라운드 머지분만 지우고 노트에 싣는다
    ⑥ `main` 도달 가능 삭제(finalize 경로)는 그대로 통과

`.venv/bin/python master/test_branch_prune.py`
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import attempt as A                              # noqa: E402
from master.work import cleanup as CL                              # noqa: E402
from master.work import review as R                                # noqa: E402

PASS = FAIL = 0
REMOTE = "gitea-write"
WA = "20261010_0335_wa_aaaa1111"      # rejected
WB = "20261010_0400_wb_bbbb2222"      # cancelled 이지만 조각 하나가 아직 pending
WC = "20261010_0500_wc_cccc3333"      # in_progress
WD = "20261010_0600_wd_dddd4444"      # 전진 대상
WX = "20261010_0700_wx_eeee5555"      # 큐에 없는 무관한 work


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
    for w in (WA, WB, WC, WX):
        t[f"task/{w}/base"] = fx.branch_at(f"task/{w}/base", fx.main, f"Source/{w}.h", "// skel\n")
        t[f"task/{w}/r1/p1"] = fx.branch_at(f"task/{w}/r1/p1", t[f"task/{w}/base"],
                                            f"Source/{w}.cpp", "// body\n")
    return t


def _queue() -> FakeQueue:
    works = {WA: {"work_id": WA, "merge_status": "rejected", "project": "Proj", "redmine_issue_id": 901},
             WB: {"work_id": WB, "merge_status": "cancelled", "project": "Proj", "redmine_issue_id": 902},
             WC: {"work_id": WC, "merge_status": "in_progress", "project": "Proj"}}
    tasks = {WA: [{"task_id": "p1", "status": "failed"}],
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


# ── ③④ 종결 work 정리 ──────────────────────────────────────────────────────

def test_apply_terminal():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        t = _setup_terminal(fx)
        q = _queue()
        plan = CL.survey_terminal(fx.paths, api=q, remote=REMOTE)
        txt = plan.render()
        ids = {w.work_id: w for w in plan.works}
        check("후보는 종결 work 둘(A·B)", set(ids) == {WA, WB}, str(set(ids)))
        check("[중요] B 는 pending 조각 때문에 보존", "pending" in ids[WB].skip or "p2" in ids[WB].skip,
              ids[WB].skip)
        check("드라이런 출력에 ref·팁·상태", f"task/{WA}/base @ {t[f'task/{WA}/base']}" in txt
              and "rejected" in txt, txt)
        check("[중요] survey 는 원격을 바꾸지 않는다", fx.remote_refs().get(f"task/{WA}/base")
              == t[f"task/{WA}/base"])
        check("[중요] survey 는 노트를 안 쓴다", not q.notes)

        logs = []
        done = CL.apply_terminal(fx.paths, plan, api=q, logf=logs.append)
        refs = fx.remote_refs()
        check("A 의 ref 둘이 지워졌다", f"task/{WA}/base" not in refs and f"task/{WA}/r1/p1" not in refs,
              str(done))
        check("[중요] B·C·X 는 그대로", all(refs.get(f"task/{w}/base") == t[f"task/{w}/base"]
                                          for w in (WB, WC, WX)), str(refs))
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


if __name__ == "__main__":
    for fn in (test_hook_direct, test_apply_terminal, test_requeue_and_stale_hook,
               test_advance_prunes_round_subbranches, test_prune_helper_keeps_unmerged_and_foreign):
        try:
            fn()
        except Exception as e:                                    # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{fn.__name__} 예외 없이", False, f"{type(e).__name__}: {e}")
    print(f"\n{PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
