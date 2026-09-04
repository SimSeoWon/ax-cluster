"""🔴 「할 일 없음」 조각 — **취소가 아니고, 분모에서 빠지지도 않는다** (사용자 결정 2026-09-04).

## 왜 이 파일이 있나 — 실측 2026-09-04 21:32

라운드가 **2/4 에서 멈췄다.** 골조에 `[PSEUDO]` 가 0개인 조각 둘을 파견하지 않은 것까지는
설계대로였는데, 그 종결을 `submit(worker_id="(none)")` 로 적으려다 `#318` 신원 게이트에
막혔다:

    [submit] 거부 — 고지자 '(none)' 가 소유자 '192.168.0.2' 가 아니다 (`#318`)

두 조각이 `claimed` 에 갇혀 `terminal 2/4` → `ready_for_review` 로 안 뒤집힘 →
**완료 공지(⑹)가 안 나가고 `.33` 은 라운드가 끝난 줄 몰랐다.** 어제와 같은 모양의 교착이다.

## 못박는 계약 넷

    ① **claim 앞에서 걷는다** (ⓑ) — 소유자가 없는 조각은 `cancel` 로만 종결된다
    ② **집계 전이가 cancel 경로에도 있다** (`#332`) — 마지막 조각이 취소분이어도 뒤집힌다
    ③ **분모(`total`)는 그대로다** — 「4조각 중 2는 골조가 완성본이었다」가 요청자에게 남는다
    ④ **공지가 「할 일 없음」과 「취소」를 가른다** — 뭉뚱그리면 실패로 읽힌다

`.venv/bin/python master/test_nowork.py`
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.task_queue import logic_cleanup as LC                          # noqa: E402
from master.task_queue import logic_lifecycle as LL                        # noqa: E402
from master.task_queue.logic import claim_task, register_task, register_work   # noqa: E402
from master.task_queue.persistence import TaskIndex                        # noqa: E402

_fail = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global _fail
    if ok:
        print(f"  [완료] {label}")
    else:
        _fail += 1
        print(f"  [실패] {label}" + (f" — {detail}" if detail else ""))


def _work(n: int = 2) -> tuple:
    """work 하나 + 조각 `n` 개 (전부 pending)."""
    root = Path(tempfile.mkdtemp(prefix="ax-nowork-"))
    idx = TaskIndex(root)
    w = register_work(idx, title="상호작용", target_repo="/tmp/repo", project="NS",
                      target_branch="task/W1/base")
    wid = w["work_id"]
    tids = []
    for i in range(n):
        r = register_task(idx, work_id=wid, type="code", task_data={},
                          target_file=f"Source/A/F{i}.cpp", header_file=f"Source/A/F{i}.h",
                          stem=f"f{i}")
        tids.append(r["task_id"])
    return idx, wid, tids


def _finish_one(idx, tid: str) -> None:
    """조각 하나를 정상 종결 (claim → submit → verify)."""
    t = claim_task(idx, "192.168.0.2", capabilities=["ue5"], types=["code"])
    assert t and t["task_id"] == tid, t
    LL.submit_result(idx, tid, branch="task/W1/x", head_commit="abc1234",
                     self_check={}, epoch=int(t.get("epoch", 1)), worker_id="192.168.0.2")
    LL.verify_task(idx, tid, passed=True, result="pass")


# ── ① 종결이 「취소」와 「할 일 없음」을 가른다 ──────────────────────────────────────

def test_no_work_is_recorded_as_its_own_thing() -> None:
    print("\n[1] cancel — `no_work` 는 실패도 취소도 아니다")
    idx, wid, (t1, _t2) = _work()
    r = LL.cancel_task(idx, t1, reason="골조에 `[PSEUDO]` 가 0개다", no_work=True)
    check("종결된다", r.get("ok") and r.get("no_work") is True, str(r))
    rec = idx.tasks[t1]
    check("  상태는 terminal (cancelled)", rec["status"] == "cancelled", rec["status"])
    check("[중요] **레코드에 `no_work` 가 남는다** — 공지가 그것으로 절을 가른다",
          rec.get("no_work") is True, str(rec.get("no_work")))
    check("  사유도 레코드에 (본문에만 있으면 화면이 「왜」를 모른다)",
          "PSEUDO" in (rec.get("cancel_reason") or ""), str(rec.get("cancel_reason")))

    idx2, _wid2, (a, _b) = _work()
    LL.cancel_task(idx2, a, reason="사람이 접었다")
    check("[주의] 그냥 취소는 `no_work` 가 아니다",
          idx2.tasks[a].get("no_work") is False, str(idx2.tasks[a].get("no_work")))


# ── ② `#332` — 집계 전이가 cancel 경로에도 있다 ────────────────────────────────────

def test_cancel_flips_the_work_when_it_is_the_last_piece() -> None:
    print("\n[2] `#332` — 마지막 조각이 취소분이어도 완료 공지가 나간다")
    idx, wid, (t1, t2) = _work()
    called: list = []
    saved = LL._auto_cleanup_work_async
    LL._auto_cleanup_work_async = lambda i, w: called.append(w)
    try:
        _finish_one(idx, t1)
        check("아직 안 뒤집힌다 (1/2)",
              idx.works[wid]["merge_status"] == "in_progress", idx.works[wid]["merge_status"])
        LL.cancel_task(idx, t2, reason="골조에 `[PSEUDO]` 가 0개다", no_work=True)
        check("🔴 **취소로 마지막이 채워지면 뒤집힌다**",
              idx.works[wid]["merge_status"] == "ready_for_review",
              idx.works[wid]["merge_status"])
        check("  그리고 공지가 걸린다 — 이것이 없어서 라운드가 2/4 에서 멈췄다",
              called == [wid], str(called))
    finally:
        LL._auto_cleanup_work_async = saved


def test_all_pieces_nowork_still_notifies() -> None:
    print("\n[3] 전부 「할 일 없음」이어도 요청자는 통보를 받는다")
    idx, wid, tids = _work(3)
    called: list = []
    saved = LL._auto_cleanup_work_async
    LL._auto_cleanup_work_async = lambda i, w: called.append(w)
    try:
        for t in tids:
            LL.cancel_task(idx, t, reason="골조가 완성본이다", no_work=True)
        check("뒤집힌다", idx.works[wid]["merge_status"] == "ready_for_review",
              idx.works[wid]["merge_status"])
        check("  공지는 **한 번만**", called == [wid], str(called))
    finally:
        LL._auto_cleanup_work_async = saved


# ── ③ 분모는 그대로다 (사용자 결정 2026-09-04) ─────────────────────────────────────

def test_the_denominator_does_not_move() -> None:
    print("\n[4] `total` 을 깎지 않는다 — 라운드 중간에 분모가 움직이면 안 된다")
    idx, wid, (t1, t2) = _work()
    LL.cancel_task(idx, t1, reason="골조가 완성본이다", no_work=True)
    check("[중요] `total` 그대로 2", int(idx.works[wid]["total"]) == 2,
          str(idx.works[wid]["total"]))
    check("  `verified` 는 안 올라간다 (완료가 아니다)",
          int(idx.works[wid].get("verified", 0)) == 0, str(idx.works[wid].get("verified")))
    called: list = []
    saved = LL._auto_cleanup_work_async
    LL._auto_cleanup_work_async = lambda i, w: called.append(w)
    try:
        _finish_one(idx, t2)
        check("  나머지가 끝나면 2/2 로 뒤집힌다", called == [wid], str(called))
    finally:
        LL._auto_cleanup_work_async = saved


# ── ④ 공지 본문 — 「할 일 없음」과 「취소」를 가른다 ─────────────────────────────────

def _notice(idx, wid: str) -> tuple:
    """공지를 실제로 만들어 `(제목, 본문)` 을 가로챈다. 네트워크는 안 탄다."""
    got: list = []
    s_cfg, s_post = LC._read_redmine_config, LC._redmine_post_issue
    LC._read_redmine_config = lambda root, project="": {
        "url": "http://x", "api_key": "k", "project": "ns"}
    LC._redmine_post_issue = lambda cfg, subject, desc: (got.append((subject, desc)) or 1)
    try:
        LC._try_create_review_issue_async(idx, wid)
        for _ in range(200):                      # 스레드다 — 기다린다 (최대 2초)
            if got:
                break
            time.sleep(0.01)
    finally:
        LC._read_redmine_config, LC._redmine_post_issue = s_cfg, s_post
    return got[0] if got else ("", "")


def test_notice_separates_no_work_from_cancelled() -> None:
    print("\n[5] 공지 — 「할 일 없음」은 실패가 아니다")
    idx, wid, (t1, t2) = _work()
    _finish_one(idx, t1)
    LL.cancel_task(idx, t2, reason="골조에 `[PSEUDO]` 가 0개다", no_work=True)
    subject, body = _notice(idx, wid)
    check("공지가 나간다", bool(subject), subject)
    check("🔴 **제목에 「일부 미완성」이 붙지 않는다** — 정상 결과다",
          "미완성" not in subject, subject)
    check("본문에 「할 일 없음」 절이 있다", "할 일 없음" in body,
          body[:200])
    check("  그 절이 실패가 아니라고 말한다", "실패가 아니다" in body, body[:400])
    check("  분모를 숨기지 않는다 (건수를 적는다)", "할 일 없음: 1건" in body, body[:400])
    check("[주의] 「취소된 파일」 절은 안 만든다 (취소분이 없다)",
          "취소된 파일" not in body, body[:400])


def test_real_cancel_is_still_called_partial() -> None:
    print("\n[6] 진짜 취소는 종전대로 「일부 미완성」이다")
    idx, wid, (t1, t2) = _work()
    _finish_one(idx, t1)
    LL.cancel_task(idx, t2, reason="사람이 접었다")
    subject, body = _notice(idx, wid)
    check("제목이 「일부 미완성」", "미완성" in subject, subject)
    check("「취소된 파일」 절이 있다", "취소된 파일" in body, body[:400])
    check("  「할 일 없음」 절은 없다", "할 일 없음" not in body, body[:400])


def main() -> int:
    print("=== 「할 일 없음」 조각 — 걷어내되 세고, 실패로 적지 않는다 ===")
    for fn in (test_no_work_is_recorded_as_its_own_thing,
               test_cancel_flips_the_work_when_it_is_the_last_piece,
               test_all_pieces_nowork_still_notifies,
               test_the_denominator_does_not_move,
               test_notice_separates_no_work_from_cancelled,
               test_real_cancel_is_still_called_partial):
        fn()
    print(("\nFAIL" if _fail else "\nOK") + f" test_nowork: 실패 {_fail}건")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
