"""🔴 「인프라 판단 불가」 조각 — `failed` 이지만 라운드를 반려로 만들지 않는다 (`#821`).

## 왜 이 파일이 있나 — 실측 2026-10-11

work `#817` 의 한 조각이 마스터 층2 검증기 예외(`verifier_exception`)로 판정을 못 냈다.
그 조각이 평범한 `failed` 로 제출돼 ①즉시 통보(`#780`)가 나갔고 ②라운드가 `rejected` 가
됐으며 ③종결 정리(`#787`)가 **성공 조각 8개의 브랜치**까지 지웠다.
사용자 결정 2026-10-13: 표지(`infra_undecided`)만 달고 계속 · 라운드 공지에만 싣는다 ·
반려 work 의 브랜치는 지우지 않는다.

## 못박는 계약

    ① VERIFICATION 판단 → submit-fail 에 `infra_undecided=True` + 「인프라 서버 오동작」 사유
       CODE 실패 → False (회귀)
    ② 형제가 도는 동안 표지 조각은 즉시 통보 없음 · 진짜 실패는 그대로 통보
    ③ completed_work_status — 성공+표지 → ready_for_review · 진짜 실패+표지 → rejected
    ④ 라운드 공지가 표지 조각을 자기 절에 적는다(태스크 id · 파일 · 사유 · 스풀) · 명령형 없음
       반려 공지는 브랜치를 남겼다고 적는다
    ⑤ survey_terminal — 반려 work 은 삭제 계획 0(보존 사유) · 취소 work 은 그대로 계획
    ⑥ ⑦ 표시(`review`) — split_push_tasks 가 표지·사유를 싣고(머지 대상은 verified 그대로),
       전진 요약·노트가 표지 조각을 따로 적는다(상대 스풀 경로 · 명령형 없음)
    ⑦ reject_work 노트 — 반려 work 브랜치를 남긴다고 적는다(지운다는 서술 없음)

`.venv/bin/python master/test_infra_undecided.py`
"""
from __future__ import annotations

import sys
import tempfile
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.task_queue import logic as Q                                   # noqa: E402
from master.task_queue import logic_cleanup as LC                          # noqa: E402
from master.task_queue import logic_lifecycle as LL                        # noqa: E402
from master.task_queue.logic_persist import completed_work_status          # noqa: E402
from master.task_queue.persistence import TaskIndex                        # noqa: E402
from master.work import cleanup as CL                                      # noqa: E402
from master.work import infer as I                                         # noqa: E402
from master.work import review as RV                                       # noqa: E402
from master.work import runner as R                                        # noqa: E402
from master.work import workmodel as WM                                    # noqa: E402

_fail = 0
_passed = 0

# test_followup.IMPERATIVES 와 같은 목록 — 자동 경로 글의 명령형 검사(리포트 60)
IMPERATIVES = ("하세요", "하라", "해라", "해 주세요", "해주세요", "말고", "보고한다", "묻지",
               "넘겨라", "확인할 것")
WORKER = "192.168.0.2"


def check(label: str, ok: bool, detail: str = "") -> None:
    global _fail, _passed
    if ok:
        _passed += 1
        print(f"  [완료] {label}")
    else:
        _fail += 1
        print(f"  [실패] {label}" + (f" — {detail}" if detail else ""))


class _ImmediateThread:
    def __init__(self, target, **kw):
        self.target = target

    def start(self):
        self.target()


@dataclass
class _Facts:
    host: str = "w1"
    user: str = "u"
    path: str = "/checkout"
    os: str = "linux"
    capabilities: list = field(default_factory=list)


# ── 큐 픽스처 ──────────────────────────────────────────────────────────────

@contextmanager
def _queue(n: int):
    """임시 큐 루트 · 등재 알림·자동 정리 무력화 · 조각 통보는 동기 + 가짜 Redmine."""
    with tempfile.TemporaryDirectory(prefix="ax-821-") as tmp, ExitStack() as st:
        idx = TaskIndex(Path(tmp))
        st.enter_context(patch.object(Q, "_create_work_issue_async", lambda *a: None))
        st.enter_context(patch.object(LL, "_auto_cleanup_work_async", lambda *a: None))
        notes: list = []
        st.enter_context(patch.object(LC.threading, "Thread", _ImmediateThread))
        st.enter_context(patch.object(LC, "_read_redmine_config",
                                      lambda *a: {"url": "http://fake", "api_key": "k",
                                                  "project": "ns"}))
        st.enter_context(patch.object(LC, "_redmine_add_note",
                                      lambda cfg, iid, body, *a: notes.append(body) or True))
        w = Q.register_work(idx, title="인프라", target_repo="/tmp/repo", project="NS",
                            target_branch="task/W/base")
        wid = w["work_id"]
        idx.works[wid]["redmine_issue_id"] = 821
        tids = [Q.register_task(idx, work_id=wid, type="code", task_data={},
                                target_file=f"Source/A/F{i}.cpp", header_file=f"Source/A/F{i}.h",
                                stem=f"f{i}")["task_id"] for i in range(n)]
        yield idx, wid, tids, notes


def _claim(idx):
    return Q.claim_task(idx, WORKER, capabilities=["ue5"], types=["code"])


def _succeed(idx, t) -> None:
    LL.submit_result(idx, t["task_id"], branch=f"task/W/r1/{t['task_id']}", head_commit="abc1234",
                     self_check={}, epoch=int(t.get("epoch", 1)), worker_id=WORKER)
    LL.verify_task(idx, t["task_id"], passed=True, result="pass")


def _fail_piece(idx, t, *, infra: bool) -> dict:
    reason = "인프라 서버 오동작 — 판단 불가 (verifier_exception)" if infra else R.BLOCKED
    return LL.submit_fail(idx, t["task_id"], reason, "[kind:verification] 층2 검증 실패",
                          epoch=int(t.get("epoch", 1)), worker_id=WORKER, infra_undecided=infra)


# ── ① infer → submit-fail ──────────────────────────────────────────────────

def _commit_failure(committed, *, attempt: int = 1) -> dict:
    from master.work import revise as RV, wcommit
    calls, logs = [], []

    def api(method, path, body=None):
        calls.append((method, path, body))
        return {"ok": True}

    usage = {"lane": "", "input_tokens": 0, "output_tokens": 0,
             "cost_known": False, "measured": False}
    with ExitStack() as st:
        st.enter_context(patch("master.work.twin_base.local_baseline", return_value={}))
        st.enter_context(patch.object(wcommit, "run", return_value=committed))
        st.enter_context(patch("master.work.usage.record", return_value=usage))
        st.enter_context(patch.object(I._MODE, "current", return_value=("codex", "test")))
        st.enter_context(patch.object(I, "_notify_blocked"))
        st.enter_context(patch.object(I, "_log", side_effect=logs.append))
        st.enter_context(patch.object(RV, "embed",
                                      return_value=RV.Embedded(task_id="t", error="격리")))
        res = I.commit_task(SimpleNamespace(usage_log=Path("/unused")), _Facts(),
                            {"task_id": "t", "epoch": 3, "attempt_count": attempt},
                            work_id="w", base="1" * 40, want=[], branch="t", api=api)
    body = calls[0][2] if calls else {}
    return {"calls": calls, "body": body, "logs": logs, "res": res}


def test_infer_marks_verification() -> None:
    print("\n[1] infer — VERIFICATION 은 표지, CODE 는 표지 없음")
    from master.work import wcommit
    c = wcommit.Committed(task_id="t", stage="층2", layer2_failure="verifier_exception",
                          reason="층2 검증 실패 — RuntimeError: boom — 커밋하지 않는다")
    out = _commit_failure(c)
    body = out["body"]
    check("submit-fail 1회", len(out["calls"]) == 1
          and out["calls"][0][1] == "/api/v1/tasks/t/submit-fail", str(out["calls"]))
    check("🔴 infra_undecided=True", body.get("infra_undecided") is True, str(body))
    check("  사유 = 인프라 서버 오동작 — 판단 불가 (verifier_exception)",
          body.get("reason") == "인프라 서버 오동작 — 판단 불가 (verifier_exception)", str(body))
    check("  재시도(revise) 아님", body.get("result") != "revise", str(body))
    check("  기존 노트 「코드 재작성 재시도 제외」 유지",
          any("층2 검증 불가(verifier_exception)" in n for n in out["res"].notes), str(out["res"].notes))
    check("  [layer2] 로그 줄", any(m.startswith("[layer2] t 인프라 판단 불가") and "#821" in m
                                  for m in out["logs"]), str(out["logs"]))

    code = wcommit.Committed(task_id="t", stage="층1", layer1_violations=["층1 위반 1: x"],
                             reason="층1 이 막았다")
    out2 = _commit_failure(code)
    check("회귀 — CODE 실패는 infra_undecided=False",
          out2["body"].get("infra_undecided") is False and out2["body"].get("reason") == R.BLOCKED,
          str(out2["body"]))
    check("  CODE 실패엔 인프라 로그 없음", not any("인프라 판단 불가" in m for m in out2["logs"]))


def test_runner_and_queue_carry_flag() -> None:
    print("\n[1b] runner.submit_fail 이 필드를 싣고 큐가 레코드에 남긴다")
    calls: list = []
    fake = lambda m, p, b=None: calls.append(b) or {"ok": True}  # noqa: E731
    R.submit_fail("T1", "r", infra_undecided=True, api=fake)
    R.submit_fail("T2", "r", api=fake)
    check("true 전송", calls[0].get("infra_undecided") is True, str(calls[0]))
    check("  옛 호출자 기본값 false", calls[1].get("infra_undecided") is False, str(calls[1]))
    from master.task_queue.models import SubmitFailReq
    check("  요청 모델 기본값 false", SubmitFailReq(reason="x").infra_undecided is False)
    with _queue(2) as (idx, wid, _tids, _notes):
        t = _claim(idx)
        r = _fail_piece(idx, t, infra=True)
        rec = idx.tasks[t["task_id"]]
        check("큐 — status failed + 표지 + 사유", r.get("ok") and rec["status"] == "failed"
              and rec.get("infra_undecided") is True and "인프라 서버 오동작" in rec["fail_reason"],
              str(rec))
        rebuilt = TaskIndex(idx.root)
        rebuilt.rebuild()
        check("  재기동(rebuild) 뒤에도 표지 유지",
              rebuilt.tasks[t["task_id"]].get("infra_undecided") is True)
        kind, why = WM.Task(rec).classify()
        check("  workmodel 분류 = verification", kind == WM.VERIFICATION and "infra_undecided" in why,
              f"{kind} {why}")


# ── ② 즉시 통보 ────────────────────────────────────────────────────────────

def test_no_immediate_notice() -> None:
    print("\n[2] 형제가 도는 동안 — 표지 조각은 즉시 통보 없음, 진짜 실패는 통보")
    with _queue(3) as (idx, wid, _tids, notes):
        t1 = _claim(idx)
        _fail_piece(idx, t1, infra=True)
        check("표지 조각 — 노트 0", notes == [], str(notes))
        check("  조각 레코드에 통보 흔적 없음", not idx.tasks[t1["task_id"]].get("fail_notice_at"))
        check("  work 은 계속 in_progress", idx.works[wid]["merge_status"] == "in_progress",
              idx.works[wid]["merge_status"])
        check("  다른 조각은 그대로 pending",
              sorted(t["status"] for k, t in idx.tasks.items() if k != t1["task_id"])
              == ["pending", "pending"])
        t2 = _claim(idx)
        _fail_piece(idx, t2, infra=False)
        check("회귀 — 진짜 실패는 즉시 노트 1건",
              len(notes) == 1 and t2["task_id"] in notes[0], str(notes))


# ── ③ 라운드 판정 ──────────────────────────────────────────────────────────

def test_completed_status() -> None:
    print("\n[3] completed_work_status")
    with _queue(2) as (idx, wid, _tids, _notes):
        _succeed(idx, _claim(idx))
        _fail_piece(idx, _claim(idx), infra=True)
        check("🔴 성공 + 표지 → ready_for_review", completed_work_status(idx, wid) == "ready_for_review",
              completed_work_status(idx, wid))
        check("  work merge_status 도 ready_for_review",
              idx.works[wid]["merge_status"] == "ready_for_review", idx.works[wid]["merge_status"])
    with _queue(3) as (idx, wid, _tids, _notes):
        _succeed(idx, _claim(idx))
        _fail_piece(idx, _claim(idx), infra=True)
        _fail_piece(idx, _claim(idx), infra=False)
        check("진짜 실패 + 표지 → rejected", completed_work_status(idx, wid) == "rejected",
              completed_work_status(idx, wid))
    with _queue(2) as (idx, wid, _tids, _notes):
        _succeed(idx, _claim(idx))
        _succeed(idx, _claim(idx))
        check("회귀 — 전부 성공 → ready_for_review",
              completed_work_status(idx, wid) == "ready_for_review", completed_work_status(idx, wid))
    with _queue(2) as (idx, wid, tids, _notes):
        _fail_piece(idx, _claim(idx), infra=True)
        LL.cancel_task(idx, tids[1], reason="골조 완성", no_work=True)
        check("표지 + no_work → ready_for_review",
              completed_work_status(idx, wid) == "ready_for_review", completed_work_status(idx, wid))


# ── ④ 라운드 공지 ──────────────────────────────────────────────────────────

def _round_notice(idx, wid) -> str:
    idx.works[wid]["noticed_round"] = 0
    notes: list = []
    with patch.object(LC.threading, "Thread", _ImmediateThread), \
            patch.object(LC, "_read_redmine_config",
                         lambda *a: {"url": "http://fake", "api_key": "k", "project": "ns"}), \
            patch.object(LC, "_redmine_add_note", lambda cfg, iid, body, *a: notes.append(body) or True):
        LC._try_create_review_issue_async(idx, wid)
    return notes[0] if notes else ""


def _section(body: str, head: str) -> str:
    i = body.find(head)
    if i < 0:
        return ""
    j = body.find("\n## ", i + 1)
    return body[i:j if j > 0 else len(body)]


def test_round_notice_section() -> None:
    print("\n[4] 라운드 공지 — 표지 조각은 자기 절 · 사실만")
    with _queue(2) as (idx, wid, tids, _notes):
        _succeed(idx, _claim(idx))
        t = _claim(idx)
        _fail_piece(idx, t, infra=True)
        body = _round_notice(idx, wid)
        sec = _section(body, "## 인프라 판단 불가")
        check("공지가 나간다 · ax-advance 안내(종결 공지 아님)",
              "ax-advance" in body and "통합·전진 대기 대상이 아니다" not in body, body[:300])
        check("「인프라 판단 불가」 절이 있다", bool(sec), body)
        tid = t["task_id"]
        check("  태스크 id · 대상 파일", tid in sec and "Source/A/F1.cpp" in sec
              and "Source/A/F1.h" in sec, sec)
        check("  사유", "인프라 서버 오동작 — 판단 불가 (verifier_exception)" in sec, sec)
        check("  스풀 상대 경로", f"responses/{wid}/{tid}.json" in sec, sec)
        check("  절대 경로 없음", "/home/" not in body and str(idx.root) not in body, sec)
        check("  「미완성 파일 (failed)」 절에 섞이지 않는다", "미완성 파일 (failed)" not in body, body)
        check("  건수 줄에 따로 센다", "인프라 판단 불가: 1건" in body and "/ 실패:" not in body, body[:400])
        for bad in IMPERATIVES:
            check(f"  절에 명령형 `{bad}` 없음", bad not in sec, sec)
    with _queue(2) as (idx, wid, _tids, _notes):
        _fail_piece(idx, _claim(idx), infra=True)
        _fail_piece(idx, _claim(idx), infra=False)
        body = _round_notice(idx, wid)
        check("반려 공지 — rejected · 표지 절 포함", "rejected" in body and "## 인프라 판단 불가" in body,
              body)
        check("🔴 반려 공지는 브랜치를 남겼다고 적는다",
              "지우지 않고 그대로 남아 있다" in body and "#821" in body, body)
        check("  「#787 이 지운다」 문구 없음", "정리 주기(#787)가 지우고" not in body, body)


# ── ⑤ 종결 정리 계획 ───────────────────────────────────────────────────────

class _FakeQueue:
    def __init__(self, works: dict, tasks: dict):
        self.works, self.tasks = works, tasks

    def __call__(self, method, path, payload=None):
        if method == "GET" and path.startswith("/api/v1/works?"):
            return list(self.works.values())
        if method == "GET" and path.startswith("/api/v1/works/"):
            wid = path.rsplit("/", 1)[-1]
            return {"work": self.works.get(wid) or {}, "tasks": self.tasks.get(wid) or []}
        raise AssertionError(f"예상 밖 호출 {method} {path}")


def test_survey_terminal() -> None:
    print("\n[5] survey_terminal — 반려 work 보존 · 취소 work 계획")
    wr, wc = "20261013_0100_wr_aaaa1111", "20261013_0200_wc_bbbb2222"
    q = _FakeQueue(
        {wr: {"work_id": wr, "merge_status": "rejected", "project": "Proj"},
         wc: {"work_id": wc, "merge_status": "cancelled", "project": "Proj"}},
        {wr: [{"task_id": "p1", "status": "verified"}, {"task_id": "p2", "status": "failed"}],
         wc: [{"task_id": "p1", "status": "cancelled"}]})
    found = {wr: [(f"task/{wr}/base", "a" * 40), (f"task/{wr}/r1/p1", "b" * 40)],
             wc: [(f"task/{wc}/base", "c" * 40)]}
    paths = SimpleNamespace(name="Proj", repo="/nonexistent")
    with patch("master.work.attempt.hook_status", return_value={"state": "ok"}), \
            patch.object(CL, "_ls_task_refs", return_value=found):
        plan = CL.survey_terminal(paths, api=q, remote="gitea-write")
    ids = {w.work_id: w for w in plan.works}
    planned = [ref for w in plan.works if not w.skip for ref, _ in w.refs]
    check("두 종결 work 모두 계획에 보인다", set(ids) == {wr, wc}, str(set(ids)))
    check("🔴 반려 work — 삭제 계획 0 · 보존 사유", ids[wr].skip == CL.REJECTED_KEEP_REASON
          and not any(r.startswith(f"task/{wr}/") for r in planned), f"{ids[wr].skip} {planned}")
    check("  보존 사유에 #821", "#821" in ids[wr].skip, ids[wr].skip)
    check("회귀 — 취소 work 은 그대로 삭제 계획", not ids[wc].skip and planned == [f"task/{wc}/base"],
          f"{ids[wc].skip} {planned}")
    check("terminal_skip_reason — 반려는 보존", CL.terminal_skip_reason(
        q.works[wr], q.tasks[wr]) == CL.REJECTED_KEEP_REASON)
    check("terminal_skip_reason — 취소+전부 terminal 은 \"\"",
          CL.terminal_skip_reason(q.works[wc], q.tasks[wc]) == "")


# ── ⑥ ⑦ 표시 — review.split_push_tasks · Advance 요약 · 상세 절 ─────────────────────────

_IU_REASON = "인프라 서버 오동작 — 판단 불가 (verifier_exception)"


def _review_tasks() -> list:
    return [
        {"task_id": "T_ok", "status": "verified", "distribution_mode": "push"},
        {"task_id": "T_iu", "status": "failed", "distribution_mode": "push",
         "infra_undecided": True, "fail_reason": _IU_REASON},
        {"task_id": "T_bad", "status": "failed", "distribution_mode": "push",
         "fail_reason": "층1 위반"},
        {"task_id": "T_pull", "status": "failed", "distribution_mode": "pull",
         "infra_undecided": True},
    ]


def test_split_push_tasks() -> None:
    verified, skipped = RV.split_push_tasks(_review_tasks())
    by = {s["task_id"]: s for s in skipped}
    check("verified 만 통합 대상 — 그대로", [t["task_id"] for t in verified] == ["T_ok"],
          str(verified))
    check("표지 조각은 건너뜀에 표지·사유와 함께",
          by.get("T_iu", {}).get("infra_undecided") is True
          and by["T_iu"].get("fail_reason") == _IU_REASON, str(by.get("T_iu")))
    check("일반 실패는 표지 False · 사유 키 없음",
          by.get("T_bad", {}).get("infra_undecided") is False and "fail_reason" not in by["T_bad"],
          str(by.get("T_bad")))
    check("pull 조각은 여전히 push 분류 밖", "T_pull" not in by, str(by))


def test_advance_rendering() -> None:
    wid = "20261013_0100_iu_aaaa1111"
    _, skipped = RV.split_push_tasks(_review_tasks())
    a = RV.Advance(work_id=wid, target_branch=f"task/{wid}/base", before="a" * 40, head="b" * 40,
                   merged=[f"task/{wid}/r1/T_ok"], skipped=skipped, build_passed=True)
    summ = a.summary
    spool = f"responses/{wid}/T_iu.json"
    check("요약에 표지 조각 id·사유·상대 스풀 경로", "T_iu" in summ and _IU_REASON in summ
          and spool in summ and "인프라 판단 불가 1건" in summ, summ)
    check("  일반 실패 조각은 표지 꼬리에 없다", "T_bad" not in a.infra_undecided_tail, summ)
    lines = RV.infra_undecided_lines(wid, skipped)
    body = "\n".join(lines)
    check("상세 절 — 머리·조각·사유·스풀", lines and "인프라 판단 불가" in lines[0]
          and "T_iu" in body and _IU_REASON in body and f"`{spool}`" in body
          and "T_bad" not in body, body)
    check("  머지하지 않았다는 사실", "머지하지 않" in body and "머지되지 않았다" in body, body)
    blob = summ + "\n" + body
    check("  절대 경로 없음", "/home" not in blob and "\\" not in blob and " /" not in blob, blob)
    check("  명령형 없음(리포트 60)", not any(w in blob for w in IMPERATIVES),
          str([w for w in IMPERATIVES if w in blob]))
    plain = RV.Advance(work_id=wid, target_branch="t", before="a" * 8, head="b" * 8,
                       skipped=[{"task_id": "T_bad", "status": "failed", "infra_undecided": False}],
                       build_passed=True)
    check("표지 없으면 꼬리·절 없음", plain.infra_undecided_tail == ""
          and RV.infra_undecided_lines(wid, plain.skipped) == [], plain.summary)


def test_reject_note_keeps_branches() -> None:
    calls = []

    def api(method, path, payload=None):
        calls.append((method, path, payload))
        return {"ok": True}

    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        with patch.object(RV, "plan_branch_cleanup",
                          return_value=SimpleNamespace(commands=lambda remote: [])):
            d = RV.reject_work(repo, work_id="20261013_0200_rj_bbbb2222",
                               work={"merge_status": "ready_for_review", "redmine_issue_id": 7},
                               tasks=[], reviewer="사람", reason="검증 실패", api=api)
    note = d.redmine_note
    check("반려 성공·큐 PATCH", d.ok and d.queue_patched and calls
          and calls[0][2]["merge_status"] == "rejected", d.error)
    check("노트 — 브랜치를 남긴다(#821)", "지우지 않고 그대로 남겨 둔다" in note and "#821" in note, note)
    check("노트 — 지운다는 서술 없음", "정리(#787)가 지우" not in note and "지운 ref" not in note
          and "해시로 복원" not in note, note)
    check("노트 — main 미변경·영구 종결은 사람", "`main` 은 변경되지 않았다" in note
          and "영구 종결은 사람이 판단한다" in note, note)
    check("docstring — 반려 브랜치 자동 삭제 서술 없음",
          "`rejected` 를\n    보면 `task/<W>/*` 를 지우고" not in (RV.reject_work.__doc__ or "")
          and "#821" in (RV.reject_work.__doc__ or ""))


def main() -> int:
    print("=== 「인프라 판단 불가」 조각 — 표지만 남기고 계속 (#821) ===")
    for fn in (test_infer_marks_verification, test_runner_and_queue_carry_flag,
               test_no_immediate_notice, test_completed_status, test_round_notice_section,
               test_survey_terminal, test_split_push_tasks, test_advance_rendering,
               test_reject_note_keeps_branches):
        try:
            fn()
        except Exception as e:                               # noqa: BLE001
            check(f"{fn.__name__} 예외 없이", False, f"{type(e).__name__}: {e}")
    print(f"\n{_passed}/{_passed + _fail} 통과")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
