"""`#840` T3 — ⑦ 전진의 로컬 생성 표지·클라우드 후보 표시와 **조각별 명시 채택**.

[중요] **실제 git + 실제 pre-push 훅**으로 돈다 — 임시 bare 원격 + 클론에 `gitea-write` 를 달고
`attempt.install_hook` 으로 원본 훅을 설치한다(`test_branch_prune.py` 와 같은 픽스처). 큐·레드마인은
주입 대역이다(HTTP·LLM·SSH 없음).

    ① 표지 없는 라운드 — 동작·요약이 그대로다
    ② 표지 조각 + 후보 — 행·요약·물음에 보이고, confirm=False 는 push 하지 않는다
    ③ adopt — 원래 조각이 아니라 후보 내용이 머지되고, 머지 커밋이 채택을 기록한다
    ④ 거절 — 표지 없음 · 라운드 밖 · 후보 없음 · 표지 모름 → 오류, 머지·push 없음
    ⑤ ls-remote 실패 → 후보 `unknown`(absent 아님) · 그 상태의 채택은 거절
    ⑥ confirm=True — 채택 후보는 지우고 원래 조각은 사유와 함께 보존 · 미채택 후보는 그대로 ·
       노트에 채택 사실 · 이후 finalize 통합이 원래 조각을 다시 머지하지 않는다
    ⑦ 표지 판독 단위 — self_check 본문 블록 · dict · 판정문 · 절단된 JSON · 근거 없음

`.venv/bin/python master/test_review_adopt.py`
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import attempt as A                              # noqa: E402
from master.work import review as R                                # noqa: E402
from master.work.branch_names import candidate_branch, durable_branch  # noqa: E402

PASS = FAIL = 0
REMOTE = "gitea-write"
W = "20261103_0900_wad_abcd1234"


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _run(cwd: Path, *args: str, ok=True) -> tuple:
    r = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(cwd), *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=dict(os.environ))
    if ok and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} rc={r.returncode}: {r.stderr}")
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


class _Paths:
    def __init__(self, root: Path):
        self.root, self.name = root, "Proj"

    @property
    def repo(self) -> Path:
        return self.root / "repo"


class Fx:
    """bare 원격 + 클론 + 원본 pre-push 훅. 작업 브랜치·조각·후보를 원격에 세운다."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.origin = tmp / "origin.git"
        self.paths = _Paths(tmp / "proj")
        self.paths.root.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.paths.repo)], check=True)
        self.repo = self.paths.repo
        _run(self.repo, "remote", "add", REMOTE, str(self.origin))
        self.main = self.commit("Source/base.cpp", "// base\n", "base")
        _run(self.repo, "push", "-q", REMOTE, "HEAD:refs/heads/main")
        _run(self.repo, "fetch", "-q", REMOTE)
        A.install_hook(self.paths)
        self.base = self.branch_at(f"task/{W}/base", self.main, "Source/S.h", "// skel\n")

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
        _run(self.repo, "checkout", "-q", "--detach", start)
        tip = self.commit(rel, text, f"on {ref}")
        _run(self.repo, "push", "-q", REMOTE, f"{tip}:refs/heads/{ref}")
        return tip

    def remote_refs(self) -> dict:
        out = _run(self.repo, "ls-remote", "--heads", REMOTE)[1]
        return {ln.split()[1][len("refs/heads/"):]: ln.split()[0]
                for ln in out.splitlines() if len(ln.split()) == 2}


def _fb(tid: str, marked: bool) -> str:
    """`infer` wcommit 이 남기는 조각 종결 판정문과 같은 모양."""
    s = (f"조각 작업 완료 — {durable_branch(W, tid, 1)} ← abcd1234. [주의] 검증 아님: 통합 검사는 "
         f"`.33` 이 서브 브랜치를 전부 머지한 뒤 한 번 한다")
    if marked:
        sc = {"needs_revalidation": True, "model": "qwen2.5-coder:14b",
              "provenance": "local", "fingerprint": "f" * 64}
        s += " · needs_revalidation=true " + json.dumps(sc, ensure_ascii=False, sort_keys=True)
    return s


def _task(tid: str, *, marked=None, status="verified") -> dict:
    t = {"task_id": tid, "status": status, "distribution_mode": "push", "round": 1}
    if marked is not None:
        t["verdict_feedback"] = _fb(tid, marked)
    return t


def _work(issue=None) -> dict:
    w = {"work_id": W, "round": 1, "distribution_mode": "push"}
    if issue:
        w["redmine_issue_id"] = issue
    return w


def _ok_build(tree):
    return {"passed": True, "summary": "ok"}


def _setup(fx: Fx, *, cands=("p1",)) -> dict:
    """p1·p2·p3 원래 조각 + 지정한 후보. 후보는 같은 파일을 다른 내용으로 바꾼다."""
    tips = {}
    for tid in ("p1", "p2", "p3"):
        tips[tid] = fx.branch_at(durable_branch(W, tid, 1), fx.base,
                                 f"Source/{tid}.cpp", f"// {tid} local\n")
    for tid in cands:
        tips[tid + "-cloud"] = fx.branch_at(candidate_branch(W, tid, 1), fx.base,
                                            f"Source/{tid}.cpp", f"// {tid} cloud\n")
    return tips


def _file(tree: str, rel: str) -> str:
    rc, out = _run(Path(tree), "show", f"HEAD:{rel}", ok=False)
    return out if rc == 0 else ""


# ── ① ───────────────────────────────────────────────────────────────────────

def test_no_marker_round_unchanged():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        _setup(fx, cands=())
        before = fx.remote_refs()
        tasks = [_task("p1", marked=False), _task("p2", marked=False), _task("p3")]
        logs = []
        a = R.advance_work(fx.repo, work_id=W, work=_work(), tasks=tasks, remote=REMOTE,
                           build_fn=_ok_build, logf=lambda k, m: logs.append(m))
        check("① 표지 없음 — 전진 준비 성공", a.ok and not a.error, a.summary)
        check("  세 조각 원래 브랜치 머지", sorted(a.merged) ==
              sorted(durable_branch(W, t, 1) for t in ("p1", "p2", "p3")), str(a.merged))
        rows = {r["task_id"]: r for r in a.revalidation}
        check("  판정문 있음+표지 없음 = no · 판정문 없음 = unknown",
              rows["p1"]["needs_revalidation"] == "no" and rows["p3"]["needs_revalidation"] == "unknown",
              str(rows))
        check("  후보 absent", all(r["candidate"] == "absent" for r in a.revalidation), str(rows))
        check("  요약·물음에 #840 꼬리 없음", "#840" not in a.summary and "adopt=" not in a.question,
              a.summary + " | " + a.question)
        check("  push 없음 · 원격 불변", not a.pushed and fx.remote_refs() == before)
        check("  로그에 재검증 표지 줄", any("재검증 표지" in m for m in logs), str(logs))


# ── ② ③ ─────────────────────────────────────────────────────────────────────

def test_marked_candidate_shown_and_adopt_dry():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        tips = _setup(fx, cands=("p1",))
        before = fx.remote_refs()
        tasks = [_task("p1", marked=True), _task("p2", marked=False), _task("p3", marked=False)]
        a = R.advance_work(fx.repo, work_id=W, work=_work(), tasks=tasks, remote=REMOTE,
                           build_fn=_ok_build)
        rows = {r["task_id"]: r for r in a.revalidation}
        check("② 표지 조각 yes · 후보 present · 팁", rows["p1"]["needs_revalidation"] == "yes"
              and rows["p1"]["candidate"] == "present"
              and rows["p1"]["candidate_head"] == tips["p1-cloud"]
              and rows["p1"]["model"] == "qwen2.5-coder:14b", str(rows["p1"]))
        check("  p2 no/absent", rows["p2"]["needs_revalidation"] == "no"
              and rows["p2"]["candidate"] == "absent", str(rows["p2"]))
        check("  요약에 건수와 채택 가능 목록", "로컬 생성 1건 · 클라우드 후보 1건" in a.summary
              and "adopt=['p1']" in a.summary, a.summary)
        check("  물음에 채택 선택", "adopt=[...]" in a.question and "p1" in a.question, a.question)
        check("  기본은 원래 조각 머지", durable_branch(W, "p1", 1) in a.merged
              and "p1 local" in _file(a.tree, "Source/p1.cpp"), str(a.merged))
        check("  confirm=False — 원격 불변", not a.pushed and fx.remote_refs() == before)

        logs = []
        b = R.advance_work(fx.repo, work_id=W, work=_work(), tasks=tasks, remote=REMOTE,
                           build_fn=_ok_build, adopt=["p1"], logf=lambda k, m: logs.append(m))
        cand = candidate_branch(W, "p1", 1)
        check("③ adopt — 성공", b.ok and not b.error, b.summary)
        check("  후보가 머지됐고 원래 p1 은 아니다", cand in b.merged
              and durable_branch(W, "p1", 1) not in b.merged, str(b.merged))
        check("  [중요] 트리 내용은 후보다", "p1 cloud" in _file(b.tree, "Source/p1.cpp"),
              _file(b.tree, "Source/p1.cpp"))
        check("  채택 기록", b.adopted == [{"task_id": "p1", "durable": durable_branch(W, "p1", 1),
                                            "candidate": cand, "head": tips["p1-cloud"]}], str(b.adopted))
        rc, msg = _run(Path(b.tree), "log", "--merges", "--format=%s%n%b", f"{b.before}..HEAD")
        check("  머지 커밋에 task·후보·팁", f"← 채택 {cand} @ {tips['p1-cloud'][:12]}" in msg
              and "task p1" in msg and tips["p1-cloud"] in msg, msg)
        check("  요약에 채택 사실 · 더 채택할 것 없음", "채택: p1←" in b.summary
              and "adopt=[" not in b.summary, b.summary)
        check("  행 adopted 표시", any(r["task_id"] == "p1" and r["adopted"] for r in b.revalidation))
        check("  confirm=False — 원격 불변", not b.pushed and fx.remote_refs() == before)
        check("  로그에 채택 줄", any("채택" in m and cand in m for m in logs), str(logs))


# ── ④ ──────────────────────────────────────────────────────────────────────

def test_adopt_refusals():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        _setup(fx, cands=("p1", "p2"))
        before = fx.remote_refs()
        tasks = [_task("p1", marked=True), _task("p2", marked=False), _task("p3", marked=True),
                 _task("p4"), _task("p5", marked=True, status="failed")]
        # p4 는 원격 조각이 없지만 거절이 머지 전이라 상관없다
        cases = [
            (["p2"], "표지가 `no`", "표지 없는 조각"),
            (["zz"], "이번 라운드", "라운드 밖 id"),
            (["p3"], "absent", "후보 없는 표지 조각"),
            (["p4"], "`unknown`", "판정문 없는(표지 모름) 조각"),
            (["p5"], "verified 조각이 아니다", "실패 조각"),
            (["p1", "p3"], "p3", "섞인 목록 — 하나라도 틀리면 전부 거절"),
        ]
        for adopt, needle, label in cases:
            a = R.advance_work(fx.repo, work_id=W, work=_work(), tasks=tasks, remote=REMOTE,
                               build_fn=_ok_build, adopt=adopt, confirm=True)
            label = label or f"adopt={adopt}"
            check(f"④ {label} → 거절", bool(a.error) and needle in a.error and "#840" in a.error,
                  a.error)
            check(f"  {label} — 머지·push 없음", not a.merged and not a.pushed
                  and fx.remote_refs() == before and not Path(a.tree).exists(), str(a.merged))
        # p4 는 판정문이 없다 = 표지 unknown. verified 이고 원격 조각만 없다 → 표지 판정으로 거절
        tasks2 = [_task("p1", marked=True), {"task_id": "p6", "status": "verified",
                                             "distribution_mode": "push", "round": 1}]
        fx.branch_at(durable_branch(W, "p6", 1), fx.base, "Source/p6.cpp", "// p6\n")
        fx.branch_at(candidate_branch(W, "p6", 1), fx.base, "Source/p6.cpp", "// p6 cloud\n")
        before = fx.remote_refs()
        a = R.advance_work(fx.repo, work_id=W, work=_work(), tasks=tasks2, remote=REMOTE,
                           build_fn=_ok_build, adopt=["p6"])
        check("④ 표지 unknown 조각의 채택 → 거절(후보가 있어도)", bool(a.error) and "`unknown`" in a.error,
              a.error)
        check("  원격 불변", fx.remote_refs() == before and not a.merged)
        a = R.advance_work(fx.repo, work_id=W, work=_work(), tasks=tasks2, remote=REMOTE,
                           adopt=["p1"], rework=True)
        check("④ 재작업 통합과 채택은 섞지 않는다", "#840" in (a.error or "") and not a.merged, a.error)

        # 후보 팁이 확인 뒤 바뀌었으면(경합) 통합이 통째 중단한다 — 원래 조각으로 접지 않는다
        tree = Path(tmp) / "wt"
        _run(fx.repo, "fetch", "-q", REMOTE)
        _run(fx.repo, "worktree", "add", "-q", "--detach", str(tree), f"{REMOTE}/task/{W}/base")
        integ = R.integrate_durables(tree, work_id=W, target_branch=f"task/{W}/base",
                                     tasks=[_task("p1", marked=True)], merge_label=f"[ADVANCE] {W}",
                                     remote=REMOTE,
                                     adopt={"p1": {"branch": candidate_branch(W, "p1", 1),
                                                   "head": "0" * 40}})
        check("④ 후보 팁 불일치 → 통째 중단", not integ.ok and "팁" in integ.error
              and not integ.merged, integ.error)


# ── ⑤ ──────────────────────────────────────────────────────────────────────

def test_ls_remote_failure_is_unknown():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        _setup(fx, cands=("p1",))
        heads, err = R.candidate_heads(fx.repo, "no-such-remote", [candidate_branch(W, "p1", 1)])
        check("⑤ 조회 실패 → 빈 dict + 사유", heads == {} and bool(err), err)
        real = R._git_rc

        def flaky(repo, *args):
            if args and args[0] == "ls-remote" and any(str(x).endswith("-cloud") for x in args):
                return 128, "fatal: simulated ls-remote failure"
            return real(repo, *args)

        tasks = [_task("p1", marked=True), _task("p2", marked=False)]
        before = fx.remote_refs()
        with patch.object(R, "_git_rc", flaky):
            a = R.advance_work(fx.repo, work_id=W, work=_work(), tasks=tasks, remote=REMOTE,
                               build_fn=_ok_build)
            b = R.advance_work(fx.repo, work_id=W, work=_work(), tasks=tasks, remote=REMOTE,
                               build_fn=_ok_build, adopt=["p1"], confirm=True)
        rows = {r["task_id"]: r for r in a.revalidation}
        check("⑤ 후보 unknown — absent 아님", all(r["candidate"] == "unknown" for r in rows.values())
              and "simulated" in rows["p1"].get("candidate_reason", ""), str(rows))
        check("  전진 준비 자체는 계속(원래 조각)", a.ok and durable_branch(W, "p1", 1) in a.merged,
              a.summary)
        check("  요약에 조회 불가", "후보 조회 불가(모름) 2건" in a.summary and "adopt=[" not in a.summary,
              a.summary)
        check("  그 상태의 채택은 거절 · push 없음", bool(b.error) and "`unknown`" in b.error
              and not b.pushed and fx.remote_refs() == before, b.error)


# ── ⑥ ──────────────────────────────────────────────────────────────────────

def test_confirm_prunes_adopted_keeps_original():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        tips = _setup(fx, cands=("p1", "p3"))
        tasks = [_task("p1", marked=True), _task("p2", marked=False), _task("p3", marked=True)]
        notes = []

        def api(method, path, payload=None):
            notes.append(payload)
            return {"ok": True}

        a = R.advance_work(fx.repo, work_id=W, work=_work(issue=840), tasks=tasks, remote=REMOTE,
                           build_fn=_ok_build, adopt=["p1"], confirm=True, api=api,
                           decision_note="버그 아님 · p1 은 클라우드 후보 채택")
        refs = fx.remote_refs()
        c1, c3 = candidate_branch(W, "p1", 1), candidate_branch(W, "p3", 1)
        d1, d2, d3 = (durable_branch(W, t, 1) for t in ("p1", "p2", "p3"))
        check("⑥ 전진 성공", a.ok and a.pushed and refs.get(f"task/{W}/base") == a.head, a.summary)
        check("  채택 후보는 삭제(도달 가능)", c1 not in refs
              and (c1, tips["p1-cloud"]) in a.deleted_subbranches, str(a.deleted_subbranches))
        check("  [중요] 원래 p1 조각은 보존 · 팁 그대로", refs.get(d1) == tips["p1"], str(refs))
        kept = dict(a.subbranch_kept)
        check("  보존 사유에 채택 후보·#840", d1 in kept and c1 in kept[d1] and "#840" in kept[d1],
              str(a.subbranch_kept))
        check("  머지된 p2·p3 원래 조각은 삭제", d2 not in refs and d3 not in refs, str(refs))
        check("  [중요] 미채택 후보 p3 는 손대지 않음", refs.get(c3) == tips["p3-cloud"], str(refs))
        rc, content = _run(fx.repo, "show", f"{a.head}:Source/p1.cpp", ok=False)
        check("  전진분 p1 = 후보 내용", "p1 cloud" in content, content)
        body = (notes[0] or {}).get("notes", "") if notes else ""
        check("  레드마인 노트에 채택 절", "## 클라우드 재검증 후보 채택" in body and c1 in body
              and tips["p1-cloud"] in body and d1 in body, body)
        check("  노트에 미채택 후보 사실", "채택하지 않은 후보: p3" in body, body)
        check("  노트에 원래 조각 보존 사유", "## 지우지 않은 서브 브랜치" in body, body)

        # 이후 finalize 통합이 남은 원래 p1 을 다시 머지하지 않는다
        work_r = dict(_work(), merge_status="ready_for_review", target_branch=f"task/{W}/base")
        d = R.finalize_work(fx.repo, work_id=W, work=work_r, tasks=tasks, confirm=False,
                            remote=REMOTE, api=lambda *x, **k: {"ok": True})
        check("⑥ finalize 통합 통과", not d.error and not d.pushed, d.error)
        check("  원래 p1 은 채택 증거로 인정(머지 안 함)", d1 in d.advanced_durables
              and d1 not in d.merged_durables, f"{d.advanced_durables} / {d.merged_durables}")
        check("  통합 트리 p1 = 후보 내용", "p1 cloud" in _file(d.tree, "Source/p1.cpp"),
              _file(d.tree, "Source/p1.cpp"))


# ── ⑦ ──────────────────────────────────────────────────────────────────────

def test_marker_parsing():
    sc = {"needs_revalidation": True, "model": "m", "provenance": "local", "fingerprint": "x"}
    body = "본문\n## self_check\n```json\n" + json.dumps(sc) + "\n```\n"
    check("⑦ 본문 self_check 블록 → yes", R.revalidation_marker({"body": body})[0] == "yes")
    check("  self_check dict 표지 없음 → no", R.revalidation_marker({"self_check": {}})[0] == "no")
    check("  근거 없음 → unknown", R.revalidation_marker({})[0] == "unknown")
    check("  다른 판정문 → unknown", R.revalidation_marker({"verdict_feedback": "ok"})[0] == "unknown")
    cut = _fb("p1", True)[:-20]
    m, info = R.revalidation_marker({"verdict_feedback": cut})
    check("  절단된 JSON 이어도 표지 → yes", m == "yes" and info == {}, str(info))
    m, info = R.revalidation_marker({"verdict_feedback": _fb("p1", True)})
    check("  판정문 JSON 에서 모델", m == "yes" and info.get("model") == "qwen2.5-coder:14b", str(info))
    check("  깨진 본문 JSON → unknown",
          R.revalidation_marker({"body": "\n## self_check\n```json\n{bad\n```\n"})[0] == "unknown")


if __name__ == "__main__":
    for fn in (test_no_marker_round_unchanged, test_marked_candidate_shown_and_adopt_dry,
               test_adopt_refusals, test_ls_remote_failure_is_unknown,
               test_confirm_prunes_adopted_keeps_original, test_marker_parsing):
        try:
            fn()
        except Exception as e:                                    # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{fn.__name__} 예외 없이", False, f"{type(e).__name__}: {e}")
    print(f"\n{PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
