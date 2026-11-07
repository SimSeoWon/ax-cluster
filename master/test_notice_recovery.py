"""`#891` — 라운드 완료 공지가 큐 종료로 사라지지 않는다.

공지는 daemon 스레드(`logic_cleanup._try_create_review_issue_async`)다. 상태 전이는 공지보다
먼저 저장되므로, 그 사이에 큐가 끝나면 기동 복구는 뒤집을 것이 없어 공지가 영영 안 나갔다
(재현 2026-11-07 — 노트 0건 · `noticed_round`·`notification_error` 둘 다 없음).

처방 1(사용자 결정 2026-11-07): 전이와 같은 저장에 `notice_pending=<라운드>` 를 남기고, 공지가
성공하면 지우고, 기동 복구(`recover_stuck_works`)가 남은 표시를 보고 다시 공지한다.

    .venv/bin/python master/test_notice_recovery.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.task_queue import logic_cleanup as LC                              # noqa: E402
from master.task_queue import logic_lifecycle as LL                            # noqa: E402
from master.task_queue.logic import (claim_task, recover_stuck_works,          # noqa: E402
                                     register_task, register_work)
from master.task_queue.persistence import TaskIndex                            # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [완료] {name}")
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


class _DeadThread:
    """공지 스레드가 일을 하기 전에 프로세스가 끝난 것과 같다 — 시작해도 아무것도 안 한다."""
    def __init__(self, target, **kw):
        self.target = target

    def start(self):
        pass


class _ImmediateThread:
    """공지 스레드를 동기로 돌린다."""
    def __init__(self, target, **kw):
        self.target = target

    def start(self):
        self.target()


_CFG = lambda *a, **k: {"url": "http://fake", "api_key": "k", "project": "ns"}  # noqa: E731


def _finished_round(thread_cls, note_fn):
    """work 1개 · 조각 1개 라운드를 종결시킨다. 공지 스레드는 `thread_cls` 로 돈다."""
    root = Path(tempfile.mkdtemp(prefix="ax-notice-"))
    idx = TaskIndex(root)
    w = register_work(idx, title="공지", target_repo="/tmp/repo", project="NS",
                      target_branch="task/W/base")
    wid = w["work_id"]
    LC.update_work_meta(idx, wid, redmine_issue_id=900)
    r = register_task(idx, work_id=wid, type="code", task_data={},
                      target_file="Source/A/N.cpp", stem="n")
    with patch.object(LC.threading, "Thread", thread_cls), \
            patch.object(LC, "_read_redmine_config", _CFG), \
            patch.object(LC, "_redmine_add_note", note_fn):
        c = claim_task(idx, "192.168.0.2", capabilities=["ue5"], types=["code"])
        LL.submit_result(idx, c["task_id"], branch="b", head_commit="abc1234",
                         self_check={}, epoch=int(c.get("epoch", 1)), worker_id="192.168.0.2")
        LL.verify_task(idx, r["task_id"], passed=True, result="pass")
    return root, wid


def _reboot(root: Path, note_fn, thread_cls=_ImmediateThread):
    """재기동 — 디스크에서 다시 읽고 기동 복구를 돈다."""
    idx = TaskIndex(root)
    idx.rebuild()
    with patch.object(LC.threading, "Thread", thread_cls), \
            patch.object(LC, "_read_redmine_config", _CFG), \
            patch.object(LC, "_redmine_add_note", note_fn):
        rec = recover_stuck_works(idx)
    return idx, rec


def test_killed_notice_is_resent() -> None:
    print("\n[1] 공지 스레드가 죽은 뒤 재기동하면 다시 공지한다")
    notes: list = []
    root, wid = _finished_round(_DeadThread, lambda *a, **k: notes.append(a[1]) or True)
    disk = TaskIndex(root)
    disk.rebuild()
    w = disk.works[wid]
    check("전이는 저장됐다(ready_for_review)", w.get("merge_status") == "ready_for_review",
          str(w.get("merge_status")))
    check("공지 대기 표시가 전이와 함께 디스크에 있다", int(w.get("notice_pending") or 0) == 1,
          str(w.get("notice_pending")))
    check("죽은 스레드는 노트를 안 보냈다", notes == [], str(notes))
    idx, rec = _reboot(root, lambda *a, **k: notes.append(a[1]) or True)
    w = idx.works[wid]
    check("기동 복구가 노트를 1건 보냈다", notes == [900], str(notes))
    check("기동 복구 반환은 전이 목록 그대로(재공지는 포함 안 함)", rec == [], str(rec))
    check("표시가 지워졌다", "notice_pending" not in w, str(w.get("notice_pending")))
    check("멱등 표시가 남았다", int(w.get("noticed_round") or 0) == 1, str(w.get("noticed_round")))
    disk = TaskIndex(root)
    disk.rebuild()
    check("디스크에서도 표시가 지워졌다", "notice_pending" not in disk.works[wid],
          str(disk.works[wid].get("notice_pending")))
    _reboot(root, lambda *a, **k: notes.append(a[1]) or True)
    check("한 번 더 재기동해도 다시 안 보낸다", notes == [900], str(notes))
    shutil.rmtree(root, ignore_errors=True)


def test_failed_note_retries_next_boot() -> None:
    print("\n[2] 노트 전송이 실패하면 표시가 남고 다음 기동에 다시 보낸다")
    root, wid = _finished_round(_ImmediateThread, lambda *a, **k: False)
    disk = TaskIndex(root)
    disk.rebuild()
    w = disk.works[wid]
    check("실패 기록(#701)은 그대로", bool(w.get("notification_error")),
          str(w.get("notification_error")))
    check("표시가 남았다", int(w.get("notice_pending") or 0) == 1, str(w.get("notice_pending")))
    notes: list = []
    idx, _ = _reboot(root, lambda *a, **k: notes.append(a[1]) or True)
    w = idx.works[wid]
    check("다음 기동에 1건 보냈다", notes == [900], str(notes))
    check("성공 뒤 표시·오류가 지워졌다",
          "notice_pending" not in w and not w.get("notification_error"),
          f"{w.get('notice_pending')} {w.get('notification_error')!r}")
    shutil.rmtree(root, ignore_errors=True)


def test_normal_path_clears() -> None:
    print("\n[3] 정상 경로 — 노트 1건, 표시는 남지 않는다, 재기동은 아무것도 안 한다")
    notes: list = []
    root, wid = _finished_round(_ImmediateThread, lambda *a, **k: notes.append(a[1]) or True)
    disk = TaskIndex(root)
    disk.rebuild()
    w = disk.works[wid]
    check("노트 1건", notes == [900], str(notes))
    check("표시 없음 · 멱등 표시 1",
          "notice_pending" not in w and int(w.get("noticed_round") or 0) == 1,
          f"{w.get('notice_pending')} {w.get('noticed_round')}")
    _reboot(root, lambda *a, **k: notes.append(a[1]) or True)
    check("재기동이 다시 보내지 않는다", notes == [900], str(notes))
    shutil.rmtree(root, ignore_errors=True)


def test_stale_round_is_ignored() -> None:
    print("\n[4] 지난 라운드의 표시는 기동 복구가 무시한다")
    root, wid = _finished_round(_DeadThread, lambda *a, **k: True)
    idx = TaskIndex(root)
    idx.rebuild()
    idx.works[wid]["round"] = 2                       # 개선요청으로 라운드가 올라간 상태
    LC._save_work(idx, wid)
    notes: list = []
    _reboot(root, lambda *a, **k: notes.append(a[1]) or True)
    check("지난 라운드 표시로는 공지하지 않는다", notes == [], str(notes))
    shutil.rmtree(root, ignore_errors=True)


def test_already_noticed_clears_marker() -> None:
    print("\n[5] 이미 공지된 라운드에 표시만 남았으면(저장 사이 종료) 다시 안 보내고 표시를 지운다")
    notes: list = []
    root, wid = _finished_round(_ImmediateThread, lambda *a, **k: notes.append(a[1]) or True)
    idx = TaskIndex(root)
    idx.rebuild()
    idx.works[wid]["notice_pending"] = 1
    LC._save_work(idx, wid)
    idx, _ = _reboot(root, lambda *a, **k: notes.append(a[1]) or True)
    check("중복 노트 없음", notes == [900], str(notes))
    check("표시가 지워졌다", "notice_pending" not in idx.works[wid],
          str(idx.works[wid].get("notice_pending")))
    shutil.rmtree(root, ignore_errors=True)


# ── `#902` 조각 즉시 실패 통보(#780) — 표시 선저장과 기동 재전송 ──────────────────
def _piece_failed(thread_cls, note_fn):
    """조각 2개 work 에서 하나를 실패시킨다(다른 하나는 진행 중). 즉시 통보 스레드는 `thread_cls`."""
    root = Path(tempfile.mkdtemp(prefix="ax-piecefail-"))
    idx = TaskIndex(root)
    w = register_work(idx, title="조각실패", target_repo="/tmp/repo", project="NS",
                      target_branch="task/W/base")
    wid = w["work_id"]
    LC.update_work_meta(idx, wid, redmine_issue_id=902)
    for stem in ("a", "b"):
        register_task(idx, work_id=wid, type="code", task_data={},
                      target_file=f"Source/A/{stem}.cpp", stem=stem)
    with patch.object(LC.threading, "Thread", thread_cls), \
            patch.object(LC, "_read_redmine_config", _CFG), \
            patch.object(LC, "_redmine_add_note", note_fn):
        c1 = claim_task(idx, "192.168.0.2", capabilities=["ue5"], types=["code"])
        c2 = claim_task(idx, "192.168.0.43", capabilities=[], types=["code"])
        LL.submit_fail(idx, c1["task_id"], "층1", "dry", epoch=int(c1.get("epoch", 1)),
                       worker_id="192.168.0.2")
    return root, wid, c1["task_id"], c2


def _disk_task(root: Path, tid: str) -> dict:
    disk = TaskIndex(root)
    disk.rebuild()
    return disk.tasks[tid]


def test_piece_fail_marker_is_on_disk() -> None:
    print("\n[6] #902 즉시 통보 스레드가 노트 전에 죽어도 대기 표시가 디스크에 남는다")
    root, _, tid, _ = _piece_failed(_DeadThread, lambda *a, **k: True)
    t = _disk_task(root, tid)
    check("실패는 저장됐다", t.get("status") == "failed", str(t.get("status")))
    check("🔴 대기 표시가 디스크에 있다", t.get("fail_notice_pending") is True,
          str(t.get("fail_notice_pending")))
    check("아직 보낸 기록은 없다", not t.get("fail_notice_at"), str(t.get("fail_notice_at")))
    shutil.rmtree(root, ignore_errors=True)


def test_piece_fail_resent_while_round_runs() -> None:
    print("\n[7] #902 라운드가 아직 돌면 재기동이 즉시 노트를 한 번 다시 보낸다")
    root, wid, tid, _ = _piece_failed(_DeadThread, lambda *a, **k: True)
    notes: list = []
    idx, _ = _reboot(root, lambda *a, **k: notes.append(a[1]) or True)
    t = idx.tasks[tid]
    check("노트 1건(#902 이슈)", notes == [902], str(notes))
    check("표시가 풀리고 보낸 기록이 남았다",
          not t.get("fail_notice_pending") and bool(t.get("fail_notice_at")),
          f"{t.get('fail_notice_pending')} {t.get('fail_notice_at')}")
    t = _disk_task(root, tid)
    check("디스크도 같다", not t.get("fail_notice_pending") and bool(t.get("fail_notice_at")),
          f"{t.get('fail_notice_pending')} {t.get('fail_notice_at')}")
    check("work 는 여전히 진행 중", idx.works[wid].get("merge_status") == "in_progress",
          str(idx.works[wid].get("merge_status")))
    _reboot(root, lambda *a, **k: notes.append(a[1]) or True)
    check("한 번 더 재기동해도 다시 안 보낸다", notes == [902], str(notes))
    shutil.rmtree(root, ignore_errors=True)


def test_piece_fail_skipped_after_round_ends() -> None:
    print("\n[8] #902 라운드가 이미 끝났으면 즉시 노트는 생략한다 — 라운드 공지가 사유를 실었다")
    root, wid, tid, c2 = _piece_failed(_DeadThread, lambda *a, **k: True)
    round_notes: list = []
    idx = TaskIndex(root)
    idx.rebuild()
    with patch.object(LC.threading, "Thread", _ImmediateThread), \
            patch.object(LC, "_read_redmine_config", _CFG), \
            patch.object(LC, "_redmine_add_note", lambda *a, **k: round_notes.append(a[2]) or True):
        LL.submit_result(idx, c2["task_id"], branch="b", head_commit="abc1234", self_check={},
                         epoch=int(c2.get("epoch", 1)), worker_id="192.168.0.43")
        LL.verify_task(idx, c2["task_id"], passed=True, result="pass")
    check("라운드 공지가 나갔고 실패 사유를 실었다",
          len(round_notes) == 1 and "Source/A/a.cpp" in round_notes[0], str(round_notes)[:200])
    notes: list = []
    idx, _ = _reboot(root, lambda *a, **k: notes.append(a[1]) or True)
    t = idx.tasks[tid]
    check("🔴 재기동은 즉시 노트를 보내지 않는다", notes == [], str(notes))
    check("표시는 풀리고 생략 사유가 남는다",
          not t.get("fail_notice_pending") and "라운드" in str(t.get("fail_notice_error") or ""),
          f"{t.get('fail_notice_pending')} {t.get('fail_notice_error')!r}")
    check("디스크에서도 풀렸다", not _disk_task(root, tid).get("fail_notice_pending"))
    shutil.rmtree(root, ignore_errors=True)


def test_piece_fail_send_failure_not_resent() -> None:
    print("\n[9] #902 전송 실패는 종전대로 재전송하지 않는다(기록이 남는다)")
    root, _, tid, _ = _piece_failed(_ImmediateThread, lambda *a, **k: False)
    t = _disk_task(root, tid)
    check("실패 기록 · 표시 없음",
          bool(t.get("fail_notice_error")) and not t.get("fail_notice_pending"),
          f"{t.get('fail_notice_error')!r} {t.get('fail_notice_pending')}")
    notes: list = []
    _reboot(root, lambda *a, **k: notes.append(a[1]) or True)
    check("재기동이 다시 보내지 않는다", notes == [], str(notes))
    shutil.rmtree(root, ignore_errors=True)


def test_piece_fail_normal_path() -> None:
    print("\n[10] #902 정상 경로 — 노트 1건, 표시 없음, 재기동은 아무것도 안 한다")
    notes: list = []
    root, _, tid, _ = _piece_failed(_ImmediateThread, lambda *a, **k: notes.append(a[1]) or True)
    t = _disk_task(root, tid)
    check("노트 1건 · 표시 없음 · 기록 있음",
          notes == [902] and not t.get("fail_notice_pending") and bool(t.get("fail_notice_at")),
          f"{notes} {t.get('fail_notice_pending')} {t.get('fail_notice_at')}")
    _reboot(root, lambda *a, **k: notes.append(a[1]) or True)
    check("재기동이 다시 보내지 않는다", notes == [902], str(notes))
    shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    print("=== #891 라운드 완료 공지 — 공지 대기 표시와 기동 복구 재공지 ===")
    for fn in (test_killed_notice_is_resent, test_failed_note_retries_next_boot,
               test_normal_path_clears, test_stale_round_is_ignored,
               test_already_noticed_clears_marker,
               test_piece_fail_marker_is_on_disk, test_piece_fail_resent_while_round_runs,
               test_piece_fail_skipped_after_round_ends, test_piece_fail_send_failure_not_resent,
               test_piece_fail_normal_path):
        fn()
    print(f"\n{PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
