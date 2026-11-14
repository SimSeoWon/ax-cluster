"""`#943` — 큐가 스스로 라운드를 rejected 로 끝낼 때도 히스토리에 남는다.

종결 기록(`history_gen.record_work_terminal`)은 PATCH 훅에서만 불렸다. 조각 실패로 큐가 뒤집는
전이는 그 라우트를 지나지 않아, rejected work 8건에 기록이 0건이었다(실측 2026-11-14).

재는 것 (임시 큐 · 임시 트윈 · 네트워크 0):
    ① 조각 실패 → 내부 rejected → 기록 1건 (라운드·실패 조각·사유 · `tags: [pipeline, rejected]`)
    ② 기동 복구의 재공지는 같은 라운드를 다시 쓰지 않는다 (`history_round`, 디스크에 남는다)
    ③ 성공 라운드(ready_for_review)·취소(cancelled)는 쓰지 않는다
    ④ 재작업으로 라운드가 올라간 뒤 다시 rejected 면 그 라운드를 따로 쓴다
    ⑤ 기록이 죽어도 공지는 간다 · 로그가 남는다
    ⑥ 🔴 라이브 큐 루트가 아니면 실트윈을 풀지 않는다
    ⑦ PATCH 로 사람이 반려한 기록도 같은 표시를 남긴다

    .venv/bin/python master/test_history_terminal.py
"""
from __future__ import annotations

import inspect
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
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


class _Twin:
    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="ax-hist-twin-"))
        self.name = "NS"

    def files(self) -> list:
        d = self.root / "history"
        return sorted(d.glob("*.md")) if d.is_dir() else []


class _ImmediateThread:
    def __init__(self, target, **kw):
        self.target = target

    def start(self):
        self.target()


_CFG = lambda *a, **k: {"url": "http://fake", "api_key": "k", "project": "ns"}  # noqa: E731


class _Env:
    """임시 큐 + 임시 트윈. 공지는 동기로 돌고 노트는 목록에 쌓인다."""

    def __init__(self, *, history_paths="twin"):
        self.root = Path(tempfile.mkdtemp(prefix="ax-hist-queue-"))
        self.twin = _Twin()
        self.notes: list = []
        self.logs: list = []
        self._history_paths = history_paths
        self.idx = TaskIndex(self.root)

    def patches(self):
        ps = [patch.object(LC.threading, "Thread", _ImmediateThread),
              patch.object(LC, "_read_redmine_config", _CFG),
              patch.object(LC, "_redmine_add_note",
                           lambda *a, **k: self.notes.append(a[1]) or True),
              patch.object(LC, "_tq_log", lambda m, *_a, **_k: self.logs.append(m))]
        if self._history_paths == "twin":
            ps.append(patch.object(LC, "_history_paths", lambda idx, work: self.twin))
        return ps

    def run(self, fn):
        ps = self.patches()
        for p in ps:
            p.start()
        try:
            return fn()
        finally:
            for p in reversed(ps):
                p.stop()

    def new_work(self, files=("Source/A/N.cpp",)):
        w = register_work(self.idx, title="히트박스 판정 추가", target_repo="/tmp/repo",
                          project="NS", target_branch="task/W/base")
        wid = w["work_id"]
        LC.update_work_meta(self.idx, wid, redmine_issue_id=900)
        tids = [register_task(self.idx, work_id=wid, type="code", task_data={},
                              target_file=f, stem=Path(f).stem.lower())["task_id"] for f in files]
        return wid, tids

    def claim(self):
        return claim_task(self.idx, "192.168.0.2", capabilities=["ue5"], types=["code"])

    def reboot(self):
        self.idx = TaskIndex(self.root)
        self.idx.rebuild()
        return self.run(lambda: recover_stuck_works(self.idx))

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.twin.root, ignore_errors=True)


def _fail_one(env: _Env, reason="층1 불합격", detail="[PSEUDO] 잔재 3곳"):
    c = env.claim()
    return LL.submit_fail(env.idx, c["task_id"], reason, detail,
                          epoch=int(c.get("epoch", 1)), worker_id="192.168.0.2")


def test_internal_rejected_is_recorded_once() -> None:
    env = _Env()
    wid, _ = env.new_work()
    env.run(lambda: _fail_one(env))
    w = env.idx.works[wid]
    check("(준비) 큐가 스스로 rejected 로 뒤집었다", w.get("merge_status") == "rejected",
          str(w.get("merge_status")))
    files = env.twin.files()
    check("[중요] ① 히스토리 1건", len(files) == 1, str([f.name for f in files]))
    text = files[0].read_text(encoding="utf-8") if files else ""
    check("① 태그·work_id 가 PATCH 기록과 같은 모양",
          "pipeline" in text and "rejected" in text and wid in text, text[:300])
    check("① 라운드 번호가 본문에 있다", "- 라운드 1" in text, text)
    check("[중요] ① 실패 조각과 사유가 본문에 있다",
          "## 실패 조각" in text and "Source/A/N.cpp" in text
          and ("PSEUDO" in text or "층1" in text), text)
    check("① 로그 한 줄 (볼 사건 = 기록)",
          any("[history]" in m and wid in m and "큐 내부 종결" in m for m in env.logs),
          str(env.logs))
    check("① 공지도 그대로 갔다", env.notes == [900] or len(env.notes) >= 1, str(env.notes))

    disk = TaskIndex(env.root)
    disk.rebuild()
    check("[중요] ② 표시가 디스크에 남는다", int(disk.works[wid].get("history_round") or 0) == 1,
          str(disk.works[wid].get("history_round")))
    # 공지 대기 표시가 남은 것처럼 만들어 재기동 — 재공지가 `_auto_cleanup_work_async` 를 다시 부른다
    env.idx.works[wid]["notice_pending"] = 1
    LC._save_work(env.idx, wid)
    env.logs.clear()
    env.reboot()
    check("[중요] ② 재공지는 같은 라운드를 다시 쓰지 않는다", len(env.twin.files()) == 1,
          str([f.name for f in env.twin.files()]))
    check("② 생략도 로그로 말한다", any("이미 있다" in m for m in env.logs), str(env.logs))
    env.close()


def test_success_and_cancel_are_not_recorded() -> None:
    env = _Env()
    wid, tids = env.new_work()

    def ok():
        c = env.claim()
        LL.submit_result(env.idx, c["task_id"], branch="b", head_commit="abc1234",
                         self_check={}, epoch=int(c.get("epoch", 1)), worker_id="192.168.0.2")
        LL.verify_task(env.idx, tids[0], passed=True, result="pass")

    env.run(ok)
    check("(준비) 성공 라운드는 ready_for_review",
          env.idx.works[wid].get("merge_status") == "ready_for_review",
          str(env.idx.works[wid].get("merge_status")))
    check("③ 성공 라운드는 쓰지 않는다", env.twin.files() == [], str(env.twin.files()))

    # 취소 — 상태를 직접 놓고 후처리만 부른다(사용자 결정: cancelled 는 기록하지 않는다)
    env.idx.works[wid]["merge_status"] = "cancelled"
    got = env.run(lambda: LC._record_rejected_history(env.idx, wid))
    check("[중요] ③ cancelled 는 쓰지 않는다", got == "" and env.twin.files() == [], str(got))
    env.close()


def test_rework_round_gets_its_own_record() -> None:
    env = _Env()
    wid, _ = env.new_work()
    env.run(lambda: _fail_one(env))
    check("(준비) 라운드 1 기록 1건", len(env.twin.files()) == 1)
    # 재작업으로 다시 열려 라운드가 올라간 뒤 또 실패한 상태
    w = env.idx.works[wid]
    w["round"] = 2
    w["merge_status"] = "in_progress"
    tid = register_task(env.idx, work_id=wid, type="code", task_data={},
                        target_file="Source/A/M.cpp", stem="m")["task_id"]
    env.run(lambda: _fail_one(env, reason="빌드 실패", detail="C2065 미선언 식별자"))
    check("(준비) 라운드 2 도 rejected", env.idx.works[wid].get("merge_status") == "rejected",
          f"{env.idx.works[wid].get('merge_status')} {env.idx.tasks[tid].get('status')}")
    texts = [f.read_text(encoding="utf-8") for f in env.twin.files()]
    check("[중요] ④ 라운드별로 따로 남는다 (2건)", len(texts) == 2, str(len(texts)))
    r2 = next((t for t in texts if "- 라운드 2" in t), "")
    check("④ 라운드 2 기록은 그 라운드의 실패만 싣는다",
          "Source/A/M.cpp" in r2 and "Source/A/N.cpp" not in r2.split("## 실패 조각")[-1], r2)
    check("④ 표시가 라운드 2 로 올라갔다",
          int(env.idx.works[wid].get("history_round") or 0) == 2,
          str(env.idx.works[wid].get("history_round")))
    env.close()


def test_record_failure_does_not_block_notice() -> None:
    env = _Env()
    wid, _ = env.new_work()

    def boom(*a, **k):
        raise OSError("디스크가 찼다")

    with patch("master.context_synth.history_gen.record_work_terminal", boom):
        env.run(lambda: _fail_one(env))
    check("[중요] ⑤ 기록이 죽어도 공지는 간다", len(env.notes) >= 1, str(env.notes))
    check("⑤ 실패가 로그에 남는다",
          any("[history]" in m and "실패" in m and "디스크가 찼다" in m for m in env.logs),
          str(env.logs))
    check("⑤ 표시는 남지 않는다 (다음 재공지 때 다시 시도)",
          "history_round" not in env.idx.works[wid], str(env.idx.works[wid].get("history_round")))
    env.close()


def test_non_live_root_never_resolves_a_real_twin() -> None:
    env = _Env(history_paths="real")          # `_history_paths` 를 바꿔 끼우지 않는다
    wid, _ = env.new_work()
    resolved = []
    with patch("master.context_search.paths.resolve",
               lambda name="": resolved.append(name) or env.twin):
        env.run(lambda: _fail_one(env))
    check("[중요] ⑥ 임시 루트는 실트윈을 풀지 않는다", resolved == [], str(resolved))
    check("⑥ 아무것도 안 썼고 생략을 로그로 말한다",
          env.twin.files() == [] and any("라이브 큐 루트가 아니다" in m for m in env.logs),
          str(env.logs))
    check("⑥ 표시도 남지 않는다", "history_round" not in env.idx.works[wid])
    check("⑥ 라이브 판정은 persistence 의 한 함수를 쓴다",
          "is_live_queue_root(idx.root)" in inspect.getsource(LC._history_paths))
    env.close()


def test_patch_rejected_leaves_the_same_mark() -> None:
    env = _Env()
    wid, _ = env.new_work()
    LC.mark_history_recorded(env.idx, wid, 1)
    disk = TaskIndex(env.root)
    disk.rebuild()
    check("⑦ 표시 함수가 디스크에 쓴다", int(disk.works[wid].get("history_round") or 0) == 1)
    env.idx.works[wid]["merge_status"] = "rejected"
    got = env.run(lambda: LC._record_rejected_history(env.idx, wid))
    check("[중요] ⑦ 사람이 PATCH 로 반려해 이미 적힌 라운드는 다시 쓰지 않는다",
          got == "" and env.twin.files() == [], str(got))
    from master.task_queue.server import _run_http_server
    src = inspect.getsource(_run_http_server)
    check("⑦ PATCH 훅이 rejected 기록 뒤 그 표시를 남긴다",
          "mark_history_recorded(idx, work_id" in src and 'req.merge_status == "rejected"' in src)
    LC.mark_history_recorded(env.idx, "없는-work", 1)        # 없는 work 는 조용히 지나간다
    check("⑦ 없는 work 에 표시를 요청해도 죽지 않는다", True)
    env.close()


def main() -> int:
    for fn in (test_internal_rejected_is_recorded_once,
               test_success_and_cancel_are_not_recorded,
               test_rework_round_gets_its_own_record,
               test_record_failure_does_not_block_notice,
               test_non_live_root_never_resolves_a_real_twin,
               test_patch_rejected_leaves_the_same_mark):
        fn()
    print(f"{'OK' if not FAIL else 'FAIL'} test_history_terminal: {PASS}/{PASS + FAIL} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
