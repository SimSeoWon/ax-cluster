"""🔴 「요청자 인계」 조각 — **취소가 아니고 work 을 `cancelled` 로 만들지 않는다** (`#757`).

## 왜 이 파일이 있나 — 실측 2026-10-09

층2 가 거짓 REQUEST_CHANGES 를 내서 사람이 조각 하나를 접었다. 그 파일은 ⑦ 통합에서
요청자(`.33`)가 손으로 채울 생각이었는데, 그냥 `cancel` 이라 work 이 `cancelled` 로 뒤집혔고
공지는 *"통합·전진 대기 대상이 아니다"* 라고 적었다 — `finalize` 도 다음 라운드도 막혔다.
사용자 결정 2026-10-09 ①: 취소에 `requester_handoff` 표시를 단다.

## 못박는 계약

    ① 인계 취소 + 나머지 verified → work `ready_for_review`
    ② 그냥 취소는 여전히 `cancelled` (회귀)
    ③ `no_work` 와 동시면 거절 · 상태 불변
    ④ 공지가 인계 파일을 **자기 절**에 적고 「취소된 파일」에 섞지 않는다 · 「일부 미완성」 유지
    ⑤ `runner.cancel` 이 필드를 실어 보낸다

`.venv/bin/python master/test_requester_handoff.py`
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.task_queue import logic as Q                                   # noqa: E402
from master.task_queue import logic_cleanup as LC                          # noqa: E402
from master.task_queue import logic_lifecycle as LL                        # noqa: E402
from master.task_queue.persistence import TaskIndex                        # noqa: E402
from master.work import runner                                             # noqa: E402

_fail = 0
_passed = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global _fail, _passed
    if ok:
        _passed += 1
        print(f"  [완료] {label}")
    else:
        _fail += 1
        print(f"  [실패] {label}" + (f" — {detail}" if detail else ""))


class _ImmediateThread:
    """공지 스레드를 동기로 돌린다 — 등재 알림과의 경쟁을 없앤다(`test_nowork` 의 함정)."""
    def __init__(self, target, **kw):
        self.target = target

    def start(self):
        self.target()


def _work(n: int = 2) -> tuple:
    root = Path(tempfile.mkdtemp(prefix="ax-handoff-"))
    idx = TaskIndex(root)
    with patch.object(Q, "_create_work_issue_async", lambda *a: None):
        w = Q.register_work(idx, title="인계", target_repo="/tmp/repo", project="NS",
                            target_branch="task/W1/base")
    wid = w["work_id"]
    tids = [Q.register_task(idx, work_id=wid, type="code", task_data={},
                            target_file=f"Source/A/F{i}.cpp", header_file=f"Source/A/F{i}.h",
                            stem=f"f{i}")["task_id"] for i in range(n)]
    return idx, wid, tids


def _finish_one(idx, tid: str) -> None:
    t = Q.claim_task(idx, "192.168.0.2", capabilities=["ue5"], types=["code"])
    assert t and t["task_id"] == tid, t
    LL.submit_result(idx, tid, branch="task/W1/x", head_commit="abc1234",
                     self_check={}, epoch=int(t.get("epoch", 1)), worker_id="192.168.0.2")
    LL.verify_task(idx, tid, passed=True, result="pass")


def _notice(idx, wid: str) -> list:
    idx.works[wid]["redmine_issue_id"] = 123
    notes: list = []
    with patch.object(LC.threading, "Thread", _ImmediateThread), \
            patch.object(LC, "_read_redmine_config",
                         lambda *a: {"url": "http://fake", "api_key": "k", "project": "ns"}), \
            patch.object(LC, "_redmine_add_note", lambda *a: notes.append(a[-1]) or True):
        LC._try_create_review_issue_async(idx, wid)
    return notes


def test_handoff_keeps_round_reviewable() -> None:
    print("\n[1] 인계 취소 + 나머지 verified → ready_for_review")
    idx, wid, (t1, t2) = _work()
    with patch.object(LL, "_auto_cleanup_work_async", lambda *a: None):
        _finish_one(idx, t1)
        r = LL.cancel_task(idx, t2, reason="층2 거짓 REQUEST_CHANGES", requester_handoff=True)
    check("종결된다 · 반환에 플래그", r.get("ok") and r.get("requester_handoff") is True
          and r.get("no_work") is False, str(r))
    rec = idx.tasks[t2]
    check("  레코드에 `requester_handoff` 가 남는다", rec.get("requester_handoff") is True,
          str(rec.get("requester_handoff")))
    check("  상태는 cancelled (terminal)", rec["status"] == "cancelled", rec["status"])
    check("🔴 **work 은 cancelled 가 아니라 ready_for_review**",
          idx.works[wid]["merge_status"] == "ready_for_review", idx.works[wid]["merge_status"])
    check("  분모 그대로 2", int(idx.works[wid]["total"]) == 2, str(idx.works[wid]["total"]))
    rebuilt = TaskIndex(idx.root)
    rebuilt.rebuild()
    check("  재기동(rebuild) 뒤에도 플래그·상태 유지",
          rebuilt.tasks[t2].get("requester_handoff") is True
          and rebuilt.works[wid]["merge_status"] == "ready_for_review",
          f"{rebuilt.tasks[t2].get('requester_handoff')} {rebuilt.works[wid]['merge_status']}")


def test_plain_cancel_still_cancels() -> None:
    print("\n[2] 회귀 — 그냥 취소는 여전히 cancelled")
    idx, wid, (t1, t2) = _work()
    with patch.object(LL, "_auto_cleanup_work_async", lambda *a: None):
        _finish_one(idx, t1)
        r = LL.cancel_task(idx, t2, reason="사람이 접었다")
    check("반환 플래그 false", r.get("requester_handoff") is False, str(r))
    check("work cancelled", idx.works[wid]["merge_status"] == "cancelled",
          idx.works[wid]["merge_status"])


def test_both_flags_rejected() -> None:
    print("\n[3] `no_work` + `requester_handoff` → 거절 · 상태 불변")
    idx, wid, (t1, _t2) = _work()
    before = dict(idx.tasks[t1])
    r = LL.cancel_task(idx, t1, reason="x", no_work=True, requester_handoff=True)
    check("ok:false", r.get("ok") is False and r.get("reason") == "conflicting_flags", str(r))
    check("  조각 레코드 그대로", idx.tasks[t1] == before,
          f"{before.get('status')} → {idx.tasks[t1].get('status')}")
    check("  work 그대로 in_progress", idx.works[wid]["merge_status"] == "in_progress",
          idx.works[wid]["merge_status"])


def test_notice_lists_handoff_separately() -> None:
    print("\n[4] 공지 — 인계 파일은 자기 절에, 「취소된 파일」엔 없다")
    idx, wid, (t1, t2, t3) = _work(3)
    with patch.object(LL, "_auto_cleanup_work_async", lambda *a: None):
        _finish_one(idx, t1)
        _finish_one(idx, t2)
        LL.cancel_task(idx, t3, reason="층2 거짓 REQUEST_CHANGES", requester_handoff=True)
    notes = _notice(idx, wid)
    body = notes[0] if notes else ""
    check("공지가 나간다", len(notes) == 1, str(len(notes)))
    check("ax-advance 안내가 있다 (종결 공지가 아니다)",
          "ax-advance" in body and "통합·전진 대기 대상이 아니다" not in body, body[:300])
    check("「요청자가 맡은 조각」 절이 있다", "## 요청자가 맡은 조각" in body, body[:600])
    check("  그 절에 파일과 사유", "`Source/A/F2.cpp` — 층2 거짓 REQUEST_CHANGES" in body, body)
    check("  건수 줄에 따로 센다", "요청자 인계: 1건" in body and "취소:" not in body, body[:400])
    check("[주의] 「취소된 파일」 절은 없다", "취소된 파일" not in body, body)
    check("partial 유지 — 미완성 경고 줄", "실패·취소분이 있다" in body, body)
    # 제목은 이슈 생성 경로에서만 보인다 — 이슈 id 를 비우고 한 번 더 만든다.
    idx.works[wid].pop("redmine_issue_id", None)
    idx.works[wid]["noticed_round"] = 0
    posted: list = []
    with patch.object(LC.threading, "Thread", _ImmediateThread), \
            patch.object(LC, "_read_redmine_config",
                         lambda *a: {"url": "http://fake", "api_key": "k", "project": "ns"}), \
            patch.object(LC, "_redmine_post_issue",
                         lambda cfg, subject, desc: posted.append(subject) or 7):
        LC._try_create_review_issue_async(idx, wid)
    check("🔴 제목은 「일부 미완성」 — 사람이 채울 것이 남았다",
          bool(posted) and posted[0].startswith("[리뷰 요청 — 일부 미완성]"), str(posted))


def test_runner_sends_field() -> None:
    print("\n[5] runner.cancel 이 필드를 실어 보낸다")
    calls: list = []
    fake = lambda method, path, body=None: calls.append((method, path, body)) or {"ok": True}  # noqa: E731
    runner.cancel("T1", reason="r", requester_handoff=True, api=fake)
    runner.cancel("T2", reason="r", api=fake)
    check("인계 true 전송", calls[0][2].get("requester_handoff") is True
          and calls[0][1] == "/api/v1/tasks/T1/cancel", str(calls[0]))
    check("  기본값 false 전송", calls[1][2].get("requester_handoff") is False, str(calls[1]))


def main() -> int:
    print("=== 「요청자 인계」 조각 — 취소지만 라운드를 막지 않는다 (#757) ===")
    for fn in (test_handoff_keeps_round_reviewable, test_plain_cancel_still_cancels,
               test_both_flags_rejected, test_notice_lists_handoff_separately,
               test_runner_sends_field):
        fn()
    print(f"\n{_passed}/{_passed + _fail} 통과")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
