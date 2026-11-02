"""`#840` T4 — 클라우드 재검증 후보 브랜치의 이름 규칙·정리 계획·마감 보고.

[중요] **실제 git + 실제 pre-push 훅**으로 돈다(`test_review_adopt.py` 픽스처). 큐·레드마인은
주입 대역이다(HTTP·LLM·SSH 없음). 사용자 결정: 미채택 후보와 채택으로 대체된 원래 조각은
**새 코드가 지우지 않는다 — 보고만 한다.**

    ① 이름 — `parse_candidate`(round 0·N) · `parse_durable` 은 후보를 조각으로 안 읽는다 ·
       task_id 접미어 예약 · 왕복이 안 되는 이름은 None
    ② `survey_remote` — 미채택 후보 `candidates` · 대체된 원래 조각 `replaced` · 둘 다 안 지운다 ·
       도달 가능한 후보(채택분)는 종전대로 삭제(실제 훅 통과)
    ③ 후보가 없으면 계획·출력이 종전과 같다
    ④ 종결(cancelled) work — 계획·노트·로그가 후보를 따로 이름 대고, 처분은 종전대로(보존 ref)
    ⑤ 수동 `merged-subs` — 후보 줄머리가 다르고 판정은 그대로(도달 가능만 지운다)
    ⑥ `finalize_work` — 남은 미채택 후보·대체된 원래 조각을 결과·노트에 싣고 지우지 않는다 ·
       후보 없는 work 은 노트에 그 절이 없다

`.venv/bin/python master/test_candidate_cleanup.py`
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import attempt as A                              # noqa: E402
from master.work import branch_names as B                          # noqa: E402
from master.work import cleanup as CL                              # noqa: E402
from master.work import review as R                                # noqa: E402
from master.test_review_adopt import Fx, _run, _task, _work, _ok_build, REMOTE, W  # noqa: E402

PASS = FAIL = 0
WT = "20261103_1000_wtc_cafe0001"     # 취소 work


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


class Queue:
    def __init__(self, works: dict, tasks: dict):
        self.works, self.tasks, self.notes = works, tasks, []

    def __call__(self, method, path, payload=None):
        if method == "GET" and path.startswith("/api/v1/works?"):
            return list(self.works.values())
        if method == "GET" and path.startswith("/api/v1/works/"):
            wid = path.rsplit("/", 1)[1]
            return {"work": self.works.get(wid) or {}, "tasks": self.tasks.get(wid) or []}
        if method == "POST" and path == "/api/v1/redmine/note":
            self.notes.append(payload)
            return {"ok": True}
        if method == "PATCH":
            return {"ok": True}
        raise AssertionError(f"예상 밖 호출 {method} {path}")


def _adopted_round(fx: Fx) -> dict:
    """p1·p2·p3 원래 조각 + 후보 p1·p3 → p1 채택 전진(confirm=True). 팁 dict."""
    tips = {}
    for tid in ("p1", "p2", "p3"):
        tips[tid] = fx.branch_at(B.durable_branch(W, tid, 1), fx.base, f"Source/{tid}.cpp",
                                 f"// {tid} local\n")
    for tid in ("p1", "p3"):
        tips[tid + "-cloud"] = fx.branch_at(B.candidate_branch(W, tid, 1), fx.base,
                                            f"Source/{tid}.cpp", f"// {tid} cloud\n")
    tasks = [_task("p1", marked=True), _task("p2", marked=False), _task("p3", marked=True)]
    a = R.advance_work(fx.repo, work_id=W, work=_work(issue=840), tasks=tasks, remote=REMOTE,
                       build_fn=_ok_build, adopt=["p1"], confirm=True,
                       api=lambda *x, **k: {"ok": True}, decision_note="p1 채택")
    if not (a.ok and a.pushed):
        raise RuntimeError(f"전진 실패: {a.error or a.summary}")
    tips["base"] = a.head
    tips["tasks"] = tasks
    return tips


# ── ① ───────────────────────────────────────────────────────────────────────

def test_names():
    check("① r0 후보 파싱", B.parse_candidate("task/W1/T1-cloud")
          == {"work_id": "W1", "task_id": "T1", "round": 0})
    check("  rN 후보 파싱", B.parse_candidate("task/W1/r3/T1-cloud")
          == {"work_id": "W1", "task_id": "T1", "round": 3})
    for n in ("task/W1/T1", "task/W1/r3/T1", "task/W1/base", "task/W1/r0/T1-cloud",
              "task/W1/base-cloud", "task/W1/-cloud", "task/T1-cloud", "attempt/W1/T1-cloud/x/y",
              "task/W1/r3/T1-cloud/x", ""):
        check(f"  후보 아님: {n!r}", B.parse_candidate(n) is None, str(B.parse_candidate(n)))
    check("  [중요] parse_durable 은 r0 후보를 조각으로 안 읽는다",
          B.parse_durable("task/W1/T1-cloud") is None)
    check("  parse_durable 종전 동작 유지", B.parse_durable("task/W1/T1")
          == {"work_id": "W1", "task_id": "T1"} and B.parse_durable("task/W1/base") is None)
    check("  옛 한 칸짜리는 종전 그대로(후보가 될 수 없는 모양)",
          (B.parse_durable("task/x-cloud") or {}).get("legacy") is True)
    for bad in ("x-cloud", "T1-cloud"):
        try:
            B.durable_branch("W1", bad, 1)
            ok = False
        except B.BranchNameError:
            ok = True
        check(f"  [중요] task_id {bad!r} 는 예약 접미어라 거절", ok)
    check("  'cloud' 로 끝나도 접미어가 아니면 허용", B.durable_branch("W1", "xcloud") == "task/W1/xcloud")
    for r in (0, 1, 7):
        n = B.candidate_branch("W1", "ab12cd34", r)
        got = B.parse_candidate(n) or {}
        check(f"  왕복 r{r}", B.candidate_branch(got.get("work_id", ""), got.get("task_id", "x"),
                                                 got.get("round", 0)) == n, n)
    check("  is_candidate", B.is_candidate("task/W1/r1/T-cloud") and not B.is_candidate("task/W1/r1/T"))


# ── ② ③ ─────────────────────────────────────────────────────────────────────

def test_survey_remote():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        tips = _adopted_round(fx)
        c1, c3 = B.candidate_branch(W, "p1", 1), B.candidate_branch(W, "p3", 1)
        d1 = B.durable_branch(W, "p1", 1)
        # 도달 가능한 후보(채택분인데 아직 남은 것) — 다른 work 의 r0 후보를 main 팁에 세운다
        reach = "task/20261103_1100_wrc_beef0002/q1-cloud"
        _run(fx.repo, "push", "-q", REMOTE, f"{fx.main}:refs/heads/{reach}")
        before = fx.remote_refs()
        logs = []
        p = CL.survey_remote(fx.paths, git=None, logf=logs.append)
        check("② 원격 조회 성공", not p.error, p.error)
        check("  [중요] 미채택 후보 c3 = candidates", [r for r, _, _ in p.candidates] == [c3],
              str(p.candidates))
        check("  [중요] 채택으로 대체된 원래 p1 = replaced", [r for r, _, _ in p.replaced] == [d1]
              and c1 in p.replaced[0][2], str(p.replaced))
        check("  일반 keep 에는 둘 다 없다", all(r not in (c3, d1) for r, _, _ in p.keep), str(p.keep))
        check("  작업 브랜치는 일반 keep", any(r == f"task/{W}/base" for r, _, _ in p.keep), str(p.keep))
        check("  도달 가능 후보는 종전대로 delete", (reach, fx.main) in p.delete, str(p.delete))
        txt = p.render()
        check("  출력에 두 범주 이름", "[보존·클라우드 후보(미채택)] " + c3 in txt
              and "[보존·채택으로 대체된 원래 조각] " + d1 in txt
              and "클라우드 후보(미채택) 1" in txt, txt)
        check("  로그 — 후보·대체 줄", any("클라우드 후보(미채택) 1건" in m for m in logs)
              and any("채택으로 대체된 원래 조각 1건" in m for m in logs), str(logs))
        check("  survey 는 원격을 안 바꾼다", fx.remote_refs() == before)
        done = CL.apply_remote(fx.paths, p)
        after = fx.remote_refs()
        check("  apply — 도달 가능 후보만 지웠다(실제 훅 통과)", done["deleted"] == [reach]
              and not done["errors"] and reach not in after, str(done))
        check("  [중요] apply — 미채택 후보·원래 조각은 그대로", after.get(c3) == tips["p3-cloud"]
              and after.get(d1) == tips["p1"], str(after))


def test_no_candidates_unchanged():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        tip = fx.branch_at(B.durable_branch(W, "p1", 1), fx.base, "Source/p1.cpp", "// p1\n")
        logs = []
        p = CL.survey_remote(fx.paths, logf=logs.append)
        check("③ 후보 없음 — candidates·replaced 비었다", not p.candidates and not p.replaced,
              f"{p.candidates} / {p.replaced}")
        check("  keep 은 종전대로(조각·base 둘)", sorted(r for r, _, _ in p.keep)
              == sorted([B.durable_branch(W, "p1", 1), f"task/{W}/base"])
              and all("사람 몫" in w for _, _, w in p.keep), str(p.keep))
        txt = p.render()
        check("  출력에 새 범주 없음", "클라우드" not in txt and "대체" not in txt, txt)
        check("  로그 없음", not logs, str(logs))
        check("  팁 그대로", fx.remote_refs().get(B.durable_branch(W, "p1", 1)) == tip)


# ── ④ ───────────────────────────────────────────────────────────────────────

def test_terminal_names_candidates():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        base = fx.branch_at(f"task/{WT}/base", fx.main, "Source/T.h", "// t\n")
        d = B.durable_branch(WT, "p1", 1)
        c = B.candidate_branch(WT, "p1", 1)
        tip_d = fx.branch_at(d, base, "Source/T.cpp", "// local\n")
        tip_c = fx.branch_at(c, base, "Source/T.cpp", "// cloud\n")
        q = Queue({WT: {"work_id": WT, "merge_status": "cancelled", "project": "Proj",
                        "redmine_issue_id": 905}},
                  {WT: [{"task_id": "p1", "status": "cancelled"}]})
        plan = CL.survey_terminal(fx.paths, api=q, remote=REMOTE)
        txt = plan.render()
        check("④ 계획 — work 줄에 후보 수", "클라우드 후보 1" in txt, txt)
        check("  후보 줄머리가 다르다", f"[삭제·클라우드 후보] {c}" in txt and f"[삭제] {d}" in txt, txt)
        logs = []
        done = CL.apply_terminal(fx.paths, plan, api=q, logf=logs.append)
        refs = fx.remote_refs()
        check("  [중요] 처분은 종전대로 — 후보도 지웠다", c not in refs and d not in refs
              and f"task/{WT}/base" not in refs, str(refs))
        rc, kept = _run(fx.repo, "rev-parse", f"{CL.PRUNED_NS}/{c}", ok=False)
        check("  후보 팁은 보존 ref 에", rc == 0 and kept == tip_c, kept)
        body = (q.notes[0] or {}).get("notes", "") if q.notes else ""
        check("  노트에 후보 절", "클라우드 재검증 후보 1건" in body and f"{c} @ {tip_c}" in body
              and tip_d in body, body)
        check("  로그 — 후보 고지 줄과 삭제 줄 꼬리", any("클라우드 후보 1건도" in m for m in logs)
              and any(m.startswith(f"삭제 {c}") and "클라우드 후보 #840" in m for m in logs), str(logs))
        check("  삭제 결과", len(done["deleted"]) == 3 and not done["failed"], str(done))


# ── ⑤ ───────────────────────────────────────────────────────────────────────

def test_merged_subs_labels():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        cr = B.candidate_branch(W, "pa", 1)          # 작업 브랜치에서 도달 가능(채택분)
        cu = B.candidate_branch(W, "pb", 1)          # 미채택
        c0 = B.candidate_branch(W, "pc", 0)          # 라운드 없는 후보
        dr = B.durable_branch(W, "pd", 1)            # 평범한 머지된 조각
        t_cr = fx.branch_at(cr, fx.base, "Source/pa.cpp", "// pa cloud\n")
        t_dr = fx.branch_at(dr, t_cr, "Source/pd.cpp", "// pd\n")
        fx.branch_at(f"task/{W}/base", t_dr, "Source/adv.txt", "advanced\n")   # 둘을 품고 전진
        t_cu = fx.branch_at(cu, fx.base, "Source/pb.cpp", "// pb cloud\n")
        t_c0 = fx.branch_at(c0, fx.base, "Source/pc.cpp", "// pc cloud\n")
        with patch("master.context_search.paths.resolve", lambda name="", **k: fx.paths):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = CL.main(["merged-subs", W])
            out = buf.getvalue()
            check("⑤ 드라이런 rc 0", rc == 0, out)
            check("  채택분 후보 줄머리", f"[삭제·클라우드 후보(채택분)] {cr} @ {t_cr}" in out, out)
            check("  미채택 후보 줄머리", f"[보존·클라우드 후보(미채택)] {cu} @ {t_cu}" in out
                  and "보고만" in out, out)
            check("  r0 후보 — 대상 밖으로 표시", f"[보존·클라우드 후보] {c0} @ {t_c0}" in out
                  and "대상 밖" in out, out)
            check("  평범한 조각 줄머리 그대로", f"[삭제] {dr} @ {t_dr}" in out, out)
            check("  드라이런은 원격 불변", {cr, cu, c0, dr} <= set(fx.remote_refs()))
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = CL.main(["merged-subs", W, "--apply"])
            refs = fx.remote_refs()
            check("  apply — 도달 가능분(채택 후보·조각)만 지웠다", rc == 0 and cr not in refs
                  and dr not in refs, buf.getvalue())
            check("  [중요] apply — 미채택·r0 후보는 그대로", refs.get(cu) == t_cu
                  and refs.get(c0) == t_c0, str(refs))
        check("  subbranch_label 단위", CL.subbranch_label("task/W/r1/x", True) == "[삭제]"
              and CL.subbranch_label("task/W/r1/x", False) == "[보존]")


# ── ⑥ ───────────────────────────────────────────────────────────────────────

def _finalize(fx: Fx, tasks, notes: list, work: dict):
    """[주의] 이 픽스처의 훅은 main push 를 막는다 — 마감 push 동안만 훅을 비킨다(삭제는 도달분뿐)."""
    hook = A.hook_target(fx.paths)
    off = hook.with_name("pre-push.off")
    os.replace(hook, off)
    try:
        def api(method, path, payload=None):
            if method == "POST":
                notes.append(payload)
            return {"ok": True}
        logs = []
        d = R.finalize_work(fx.repo, work_id=W, work=work, tasks=tasks, confirm=True, remote=REMOTE,
                            api=api, logf=lambda k, m: logs.append(m))
    finally:
        os.replace(off, hook)
    return d, logs


def test_finalize_reports_leftovers():
    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        tips = _adopted_round(fx)
        c1, c3 = B.candidate_branch(W, "p1", 1), B.candidate_branch(W, "p3", 1)
        d1 = B.durable_branch(W, "p1", 1)
        notes = []
        work = dict(_work(issue=840), merge_status="ready_for_review", target_branch=f"task/{W}/base")
        d, logs = _finalize(fx, tips["tasks"], notes, work)
        check("⑥ 마감 성공", d.ok and d.pushed, d.error)
        check("  [중요] 미채택 후보 보고", d.leftover_candidates == [c3], str(d.leftover_candidates))
        check("  [중요] 대체된 원래 조각 보고", d.replaced_originals == [(d1, c1)], str(d.replaced_originals))
        refs = fx.remote_refs()
        check("  [중요] 둘 다 원격에 그대로", refs.get(c3) == tips["p3-cloud"] and refs.get(d1) == tips["p1"],
              str(refs))
        check("  작업 브랜치는 종전대로 삭제(도달 가능)", f"task/{W}/base" not in refs, str(refs))
        body = (notes[-1] or {}).get("notes", "") if notes else ""
        check("  노트 절", "클라우드 재검증 (#840)" in body and f"클라우드 후보(미채택): `{c3}`" in body
              and f"채택으로 대체된 원래 조각: `{d1}` (채택 `{c1}`)" in body, body)
        check("  로그 한 줄", any("남은 클라우드 후보(미채택) 1건" in m and "대체된 원래 조각 1건" in m
                                for m in logs), str(logs))

    with tempfile.TemporaryDirectory() as tmp:
        fx = Fx(Path(tmp))
        fx.branch_at(B.durable_branch(W, "p1", 1), fx.base, "Source/p1.cpp", "// p1\n")
        tasks = [_task("p1", marked=False)]
        notes = []
        work = dict(_work(issue=841), merge_status="ready_for_review", target_branch=f"task/{W}/base")
        d, logs = _finalize(fx, tasks, notes, work)
        body = (notes[-1] or {}).get("notes", "") if notes else ""
        check("⑥ 후보 없는 마감 — 성공·보고 빈 값", d.ok and d.pushed and not d.leftover_candidates
              and not d.replaced_originals, d.error)
        check("  노트에 #840 절 없음", "클라우드" not in body and "#840" not in body, body)
        check("  조각·base 종전대로 삭제", not any(r.startswith(f"task/{W}/") for r in fx.remote_refs()),
              str(fx.remote_refs()))


if __name__ == "__main__":
    for fn in (test_names, test_survey_remote, test_no_candidates_unchanged,
               test_terminal_names_candidates, test_merged_subs_labels,
               test_finalize_reports_leftovers):
        try:
            fn()
        except Exception as e:                                    # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{fn.__name__} 예외 없이", False, f"{type(e).__name__}: {e}")
    print(f"\n{PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
