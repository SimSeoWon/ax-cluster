"""전환 인계 조사 (`#253`) — **다섯 부류 전부, 이름으로**.

완료 조건이 *"큐·워커·원격·스풀·durable 다섯 부류 전부 이름으로 보고한다. 그중 하나라도
빠지면 미완"* 이라 **부류 누락 자체를 실패로** 만든다.

[중요] 이 모듈은 **조사만** 한다 — 지우는 주체·범위·`force` 는 `#253` 의 [미결] 셋이고 사람
결정 자리다. 그래서 「지우지 않는다」도 테스트한다(다음 사람이 여기에 삭제를 넣지 않게).

`.venv/bin/python master/test_handover.py`
"""
from __future__ import annotations

import re
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import handover as H                              # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _paths(tmp: Path):
    (tmp / "repo").mkdir(parents=True, exist_ok=True)
    (tmp / "responses").mkdir(parents=True, exist_ok=True)
    return types.SimpleNamespace(name="X", repo=tmp / "repo", responses=tmp / "responses")


def test_all_five_kinds_present() -> None:
    """[중요] **다섯 부류가 전부 나온다** — 하나라도 빠지면 완료 조건 미달이다."""
    check("KINDS 가 다섯이다", len(H.KINDS) == 5, str(H.KINDS))
    for want in ("queue", "workers", "remote_ephemeral", "remote_durable", "spool"):
        check(f"{want} 가 선언돼 있다", want in H.KINDS)
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    rep = H.survey_project("X", paths=_paths(tmp), api=lambda *a: [],
                           surveyor=lambda f: types.SimpleNamespace(),
                           prober=lambda *a: None,
                           git=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("원격 없음")))
    for want in H.KINDS:
        check(f"보고에 {want} 가 있다", want in rep["kinds"], str(list(rep["kinds"])))
    check("렌더가 다섯 부류를 다 찍는다",
          all(f"[{k}]" in H.render(rep) for k in H.KINDS), H.render(rep)[:120])


def test_names_not_just_counts() -> None:
    """[중요] **셈이 아니라 이름**이다 — 셈만 주면 사람이 판단할 수 없다."""
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    p = _paths(tmp)
    (p.responses / "w1").mkdir()
    (p.responses / "w1" / "a.txt").write_text("x", encoding="utf-8")
    (p.responses / "loose.json").write_text("{}", encoding="utf-8")
    out = H._spool_leftovers(p)
    check("스풀 이름을 낸다", any("w1" in n for n in out.names), str(out.names))
    check("파일도 센다", any("loose.json" in n for n in out.names), str(out.names))
    check("디렉토리는 건수를 붙인다", any("(1건)" in n for n in out.names), str(out.names))
    check("count 는 이름 수다", out.count == len(out.names))


def test_queue_uses_the_project_stamp() -> None:
    """[중요] **스탬프로 거른다** — 백필(`#248`)이 이것의 선결이었다."""
    works = [{"work_id": "w1", "project": "X", "merge_status": "in_progress"},
             {"work_id": "w2", "project": "Y", "merge_status": "in_progress"},
             {"work_id": "w3", "project": "X", "merge_status": "merged"},
             {"work_id": "w4", "project": "", "merge_status": "in_progress"}]
    tasks = [{"task_id": "t1", "work_id": "w1", "status": "claimed"},
             {"task_id": "t2", "work_id": "w1", "status": "verified"},
             {"task_id": "t9", "work_id": "zz", "status": "pending"}]

    def api(method, path):
        return works if "/works" in path else tasks

    out = H._queue_leftovers("X", api=api)
    joined = " ".join(out.names)
    check("[중요] 내 프로젝트의 미종결만", "w1" in joined, joined)
    check("남의 프로젝트는 세지 않는다", "w2" not in joined, joined)
    check("종결된 것은 세지 않는다", "w3" not in joined, joined)
    check("[중요] 스탬프 없는 것도 내 몫으로 세지 않는다 (필터가 남기더라도)",
          "w4" not in joined, joined)
    check("미종결 태스크 수를 붙인다", "태스크 1" in joined, joined)
    check("verified 태스크는 세지 않는다", "t2" not in joined, joined)
    check("고아 태스크를 이름으로 낸다", "t9" in joined, joined)


def test_failure_is_not_folded_into_clean() -> None:
    """[중요] **「모르는데 깨끗하다」를 만들지 않는다** (fail-closed)."""
    import tempfile
    tmp = Path(tempfile.mkdtemp())

    def boom(*a, **k):
        raise RuntimeError("큐 다운")

    rep = H.survey_project("X", paths=_paths(tmp), api=boom,
                           surveyor=lambda f: types.SimpleNamespace(),
                           prober=lambda *a: None,
                           git=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("원격 없음")))
    check("남은 것은 0 인데", rep["total"] == 0, str(rep["total"]))
    check("[중요] clean 은 False 다", rep["clean"] is False, str(rep))
    check("못 본 부류를 이름으로 든다", "queue" in rep["unknown"], str(rep["unknown"]))
    check("사유를 남긴다", "판정 불가" in rep["note"] or "못 본" in rep["note"], rep["note"])
    check("렌더가 [주의] 로 말한다", "[주의]" in H.render(rep), H.render(rep)[:200])


def test_durable_is_counted_but_kept() -> None:
    """[중요] durable 미병합은 **보존이 맞다 — 그래도 셈은 남는다** (`#253`)."""
    plan = types.SimpleNamespace(
        error="",
        keep=[("task/t1", "aaaaaaaa1111", "origin/main 에 없다 — 병합 안 됨, 사람 몫"),
              ("attempt/t1/HV/1", "bbbbbbbb2222", "origin/main 에 없다 — 병합 안 됨, 사람 몫")],
        delete=[("attempt/t2/HV/9", "cccccccc3333")])
    import master.work.cleanup as C
    keep_fn = C.survey_remote
    try:
        C.survey_remote = lambda paths, **k: plan
        eph, dur = H._remote_leftovers(types.SimpleNamespace(repo=Path(".")))
    finally:
        C.survey_remote = keep_fn
    check("durable 을 durable 로 가른다", any("task/t1" in n for n in dur.names), str(dur.names))
    check("일회용을 일회용으로 가른다",
          any("attempt/t1" in n for n in eph.names), str(eph.names))
    check("[중요] 갈라 담는다 (섞지 않는다)",
          not any("attempt" in n for n in dur.names), str(dur.names))
    check("durable 은 사람 몫이라고 말한다", "사람 몫" in dur.note, dur.note)
    check("병합 확인분은 남은 것이 아니다 (delete 는 세지 않는다)",
          not any("attempt/t2" in n for n in eph.names + dur.names))
    check("치울 도구를 알려준다", "cleanup remote" in eph.note, eph.note)


def test_worker_dirs_use_real_field_shapes() -> None:
    """[주의] `HostPlan.drop_dirs`/`keep_dirs` 는 **`(task_id, 사유)` 튜플**이다.

    추측해 문자열로 쓰면 보고에 `('t1', 'verified')` 가 실린다 — 실측으로 고친 자리다.
    """
    plan = types.SimpleNamespace(drop_dirs=[("t1", "verified")],
                                 keep_dirs=[("t2", "미종결")],
                                 keep=[("attempt/x", "병합 안 됨")],
                                 errors=["디스크 오류"])
    import master.client.bundle as B
    keep_ws = B.workshops
    try:
        # [주의] `#321` — 워크숍 튜플에 `dispatch` 가 붙었다 (6번째).
        B.workshops = lambda n: [("h1", "u", "/p", "ssh", "worker", ""),
                                 ("h2", "u", "/p", "ssh", "requester", "")]
        out = H._worker_leftovers("X", surveyor=lambda f: plan,
                                  prober=lambda *a: types.SimpleNamespace(host="h1"))
    finally:
        B.workshops = keep_ws
    joined = " ".join(out.names)
    check("task_id 와 사유를 갈라 찍는다", "t1 — verified" in joined, joined)
    check("보존 대상을 표시한다", "t2 — 미종결 (보존)" in joined, joined)
    check("브랜치도 낸다", "attempt/x" in joined, joined)
    check("오류를 삼키지 않는다", "디스크 오류" in joined, joined)
    check("[주의] 튜플이 그대로 실리지 않는다", "('t1'" not in joined, joined)
    check("[중요] 요청자는 세지 않는다 (사람의 기계다)", "h2" not in joined, joined)


def test_deletion_is_gated_and_narrow() -> None:
    """[중요] **삭제가 있지만 좁고 잠겨 있다** (사용자 결정 ③, 2026-08-23).

    [주의] 이 테스트는 한 번 갈아 썼다 — 결정 전에는 *"이 모듈은 아무것도 지우지 않는다"* 가
    계약이었다. 결정으로 `apply(confirm=True)` 가 생겼으니 계약이 바뀌었고, **낡은 계약을
    지키는 테스트는 새 결정을 막는다.**
    """
    src = (Path(__file__).resolve().parent / "work" / "handover.py").read_text(encoding="utf-8")

    # ── ① 조사·계획 경로에는 삭제가 없다
    for fn in ("def survey_project", "def plan("):
        i = src.index(fn)
        body = src[i:src.index("\ndef ", i + 10)]
        for bad in ("unlink", "rmdir", "act(", "doer"):
            check(f"{fn.strip()} 에 {bad} 가 없다", bad not in body, body[:60])

    # ── ② 삭제는 `apply` 안에만, 그리고 confirm 뒤에만
    ap = src[src.index("def apply("):src.index("def _rmdir")]
    check("[중요] apply 는 confirm 없이 실행하지 않는다",
          "if not confirm:" in ap and ap.index("if not confirm:") < ap.index("act("), ap[:80])
    check("[중요] 못 본 부류가 있으면 거부한다",
          ap.index("safe_to_apply") < ap.index("act("), "거부가 삭제 뒤에 있다")

    # ── ③ [주의] **언급 금지가 아니라 호출 금지다** (이 저장소가 이미 배운 구분)
    check("`shutil` 을 import 하지 않는다",
          not re.search(r"^\s*(import shutil|from shutil)", src, re.M),
          "재귀 삭제 도구를 들여왔다")
    check("`rmtree` 를 부르지 않는다", "rmtree(" not in src)
    check("[중요] 그 이유가 문서에 있다 (다음 사람이 들여오지 않게)",
          "rmtree" in src and "깊은 재귀 삭제" in src)
    apply_lines = [l for l in src.splitlines() if "--apply" in l]
    check("`--apply` 는 사람에게 도구를 알려주는 문구다",
          apply_lines and all(("note" in l or 'f"' in l or '"' in l) for l in apply_lines),
          str(apply_lines))

    # ── ④ 보존 결정이 문서에 박혀 있다
    check("보존 결정을 문서가 못박는다",
          "미종결" in src and "보존" in src and "사용자 결정" in src)


def test_switch_reports_leftovers() -> None:
    """[중요] **완료 조건은 「전환 시도가 보고한다」** — 도구만 있으면 미완이다."""
    from master.projects import logic as L
    import inspect
    src = inspect.getsource(L.set_active)
    check("전환이 인계 조사를 부른다", "_handover(" in src, "전환이 부르지 않는다")
    check("떠나는 프로젝트를 조사한다", "leaving" in src)
    check("거절 경로에도 붙는다", src.index("_handover_lines") < src.index("previous = reg.active"))
    check("성공 경로에도 싣는다", '"handover": handover_out' in src)
    check("주입 자리가 있다 (테스트가 SSH 를 타지 않는다)", "handover_fn" in src)

    rep = {"kinds": {"queue": {"count": 2, "names": ["w1", "w2"], "note": "", "error": ""},
                     "spool": {"count": 0, "names": [], "note": "", "error": ""},
                     "workers": {"count": 0, "names": [], "note": "", "error": "못 봄"}}}
    line = L._handover_lines(rep)
    check("[중요] 이름을 낸다", "w1" in line, line)
    check("판정 불가를 구분해 말한다", "판정 불가" in line, line)
    check("0건은 찍지 않는다 (노이즈)", "spool" not in line, line)
    check("조사 자체가 실패하면 그렇게 말한다",
          "[주의]" in L._handover_lines({"error": "큐 다운"}))
    many = {"kinds": {"queue": {"count": 9, "names": [f"w{i}" for i in range(9)],
                                "note": "", "error": ""}}}
    check("길면 줄인다 (+N 로)", "+6" in L._handover_lines(many), L._handover_lines(many))


# ── 정리 — 계획 → 승인 → 실행 (사용자 결정 2026-08-23) ────────────────────────

def _rep(spool=(), queue=(), durable=(), eph=(), unknown=()):
    kinds = {k: {"count": 0, "names": [], "note": "", "error": ""} for k in H.KINDS}
    kinds["spool"]["names"] = list(spool); kinds["spool"]["count"] = len(spool)
    kinds["queue"]["names"] = list(queue); kinds["queue"]["count"] = len(queue)
    kinds["remote_durable"]["names"] = list(durable)
    kinds["remote_durable"]["count"] = len(durable)
    kinds["remote_ephemeral"]["names"] = list(eph); kinds["remote_ephemeral"]["count"] = len(eph)
    for u in unknown:
        kinds[u]["error"] = "못 봄"
    total = sum(v["count"] for v in kinds.values())
    return {"project": "X", "kinds": kinds, "total": total, "unknown": list(unknown),
            "clean": total == 0 and not unknown, "note": ""}


def test_plan_preserves_what_the_user_chose() -> None:
    """[중요] **미종결·failed·미병합 durable 은 전환에도 보존** (사용자 결정 2026-08-23)."""
    works = [{"work_id": "w-done", "project": "X", "merge_status": "merged"},
             {"work_id": "w-open", "project": "X", "merge_status": "in_progress"},
             {"work_id": "w-fail", "project": "X", "merge_status": "failed"}]
    api = lambda m, p: works
    rep = _rep(spool=["w-done (1건)", "w-open (2건)", "w-fail (1건)", "live-itg (1건)"],
               queue=["w-open [in_progress]", "w-fail [failed]"],
               durable=["task/t1 @aaaa — 병합 안 됨"],
               eph=["attempt/t2/HV/1 @bbbb — 병합 안 됨"])
    pl = H.plan("X", api=api, rep=rep)
    dropped = [e for e, _ in pl["drop"]["spool"]]
    kept = " ".join(w for w, _ in pl["keep"])
    check("[중요] 종결 work 의 스풀만 지운다", dropped == ["w-done"], str(dropped))
    check("미종결 work 의 스풀은 보존", "spool:w-open" in kept, kept)
    check("[중요] failed 의 스풀도 보존 (증거)", "spool:w-fail" in kept, kept)
    check("[중요] 큐에 없는 이름은 보존 (모르는 것은 손대지 않는다)",
          "spool:live-itg" in kept, kept)
    check("미종결 work 레코드는 보존", "queue:w-open [in_progress]" in kept, kept)
    check("[중요] 미병합 durable 은 보존", "remote_durable:task/t1" in kept, kept)
    check("미병합 attempt 도 보존", "remote_ephemeral:attempt/t2/HV/1" in kept, kept)
    check("보존 사유를 남긴다 (사람이 판단할 근거)",
          all(why for _, why in pl["keep"]), str(pl["keep"]))
    check("실행 명령을 준다", "handover apply X --confirm" in pl["command"], pl["command"])


def test_plan_never_invents_deletion() -> None:
    """[중요] **새 삭제 의미를 만들지 않는다** — 기존 도구가 지우는 것만 조합한다."""
    pl = H.plan("X", api=lambda m, p: [], rep=_rep())
    check("워커는 cleanup 에 넘긴다", "cleanup.apply" in pl["drop"]["worker_dirs"],
          pl["drop"]["worker_dirs"])
    check("원격은 cleanup_remote 에 넘긴다", "apply_remote" in pl["drop"]["remote"],
          pl["drop"]["remote"])
    check("도달 가능한 것만이라고 못박는다", "도달 가능" in pl["drop"]["remote"])


def test_apply_needs_confirm() -> None:
    """[중요] `confirm=False`(기본)는 **계획만** — `finalize_work` 관례 그대로."""
    import tempfile
    calls = []
    works = [{"work_id": "w1", "project": "X", "merge_status": "merged"}]
    import master.client.bundle as B
    import master.work.cleanup as C
    keep_ws, keep_sr = B.workshops, C.survey_remote
    try:
        B.workshops = lambda n: []
        C.survey_remote = lambda paths, **k: types.SimpleNamespace(error="", keep=[], delete=[])
        r = H.apply("X", api=lambda m, p: works, paths=_paths(Path(tempfile.mkdtemp())),
                    doer=lambda t: calls.append(t),
                    surveyor=lambda f: types.SimpleNamespace(), prober=lambda *a: None)
    finally:
        B.workshops, C.survey_remote = keep_ws, keep_sr
    check("[중요] 기본은 실행하지 않는다", r["applied"] is False, str(r)[:120])
    check("아무것도 부르지 않았다", calls == [], str(calls))
    check("무엇을 하면 실행되는지 말한다", "confirm" in r["note"], r["note"])


def test_apply_refuses_when_it_cannot_see() -> None:
    """[중요] **모르는 채 지우지 않는다** — 못 본 부류가 있으면 거부한다."""
    def boom(*a, **k):
        raise RuntimeError("큐 다운")
    import tempfile
    calls = []
    r = H.apply("X", confirm=True, api=boom, paths=_paths(Path(tempfile.mkdtemp())),
                doer=lambda t: calls.append(t),
                surveyor=lambda f: types.SimpleNamespace(),
                prober=lambda *a: None,
                git=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("원격 없음")))
    check("[중요] 거부한다", r["applied"] is False and r.get("refused"), str(r)[:160])
    check("사유에 못 본 부류를 든다", "queue" in (r.get("refused") or ""), str(r.get("refused")))
    check("아무것도 지우지 않았다", calls == [], str(calls))


def test_apply_deletes_only_the_planned_spool() -> None:
    """실행 경로 — 계획에 든 것만, 실물 파일로 확인."""
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    p = _paths(tmp)
    for n in ("w-done", "w-open"):
        (p.responses / n).mkdir()
        (p.responses / n / "r.json").write_text("{}", encoding="utf-8")
    works = [{"work_id": "w-done", "project": "X", "merge_status": "merged"},
             {"work_id": "w-open", "project": "X", "merge_status": "in_progress"}]
    # [중요] **네 부류를 다 보이게 만들어야 실행된다** — 하나라도 못 보면 `apply` 가 거부한다.
    #    처음엔 workers·remote 를 stub 하지 않았고 거부가 났다. 그것이 옳은 동작이다.
    import master.client.bundle as B
    import master.work.cleanup as C
    keep_ws, keep_sr = B.workshops, C.survey_remote
    try:
        B.workshops = lambda n: []                  # 워커 없음 = 볼 것이 없다(오류가 아니다)
        C.survey_remote = lambda paths, **k: types.SimpleNamespace(error="", keep=[], delete=[])
        r = H.apply("X", confirm=True, api=lambda m, pa: works, paths=p,
                    surveyor=lambda f: types.SimpleNamespace(),
                    prober=lambda *a: None, git=None)
    finally:
        B.workshops, C.survey_remote = keep_ws, keep_sr
    check("실행했다", r["applied"] is True, str(r)[:120])
    check("[중요] 종결분은 사라졌다", not (p.responses / "w-done").exists())
    check("[중요] 미종결분은 남았다", (p.responses / "w-open").is_dir())
    check("무엇을 지웠는지 이름으로 보고한다",
          any("w-done" in x for x in r["done"]["spool"]), str(r["done"]))
    check("실패를 삼키지 않는 자리가 있다", "errors" in r["done"])
    check("[주의] 한 겹만 지운다 (재귀 삭제 도구를 안 쓴다)",
          not re.search(r"^\s*import shutil",
                        (Path(__file__).resolve().parent / "work" / "handover.py")
                        .read_text(encoding="utf-8"), re.M))


if __name__ == "__main__":
    for fn in (test_all_five_kinds_present, test_names_not_just_counts,
               test_queue_uses_the_project_stamp, test_failure_is_not_folded_into_clean,
               test_durable_is_counted_but_kept, test_worker_dirs_use_real_field_shapes,
               test_deletion_is_gated_and_narrow, test_switch_reports_leftovers,
               test_plan_preserves_what_the_user_chose,
               test_plan_never_invents_deletion, test_apply_needs_confirm,
               test_apply_refuses_when_it_cannot_see,
               test_apply_deletes_only_the_planned_spool):
        fn()
    print(f"{'OK' if not FAIL else 'FAIL'} test_handover: {PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
