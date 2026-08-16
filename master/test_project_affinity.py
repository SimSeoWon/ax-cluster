"""work 프로젝트 귀속 + 활성 전환 가드 (#210) 계약 테스트.

재는 것 셋:
    ① 스탬프        등록 → work 메타에 project · 옛 work(스탬프 없음)는 None
    ② 스탬프 해석    _paths_for 가 활성이 아니라 스탬프로 트윈을 푼다 (없으면 활성 호환)
    ③ 전환 가드     미종결 work 존재 → 거부 · 큐 확인 불가 → 거부 (fail-closed) ·
                   force = 통과하되 무엇이 걸렸는지 결과에 남는다 · 종결뿐이면 통과

실행: .venv/bin/python master/test_project_affinity.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.projects.logic import ConfigError, open_works_in_queue, set_active  # noqa: E402
from master.task_queue.logic import register_work                               # noqa: E402
from master.task_queue.persistence import TaskIndex                             # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


# ── ① 스탬프 ─────────────────────────────────────────────────

def test_stamp_on_register():
    root = Path(tempfile.mkdtemp(prefix="ax-pa-"))
    idx = TaskIndex(root)
    r = register_work(idx, title="스탬프 확인", target_repo="/r", project="ModularStage")
    wid = r.get("work_id")
    check("[중요] 등록된 work 메타에 project 스탬프",
          idx.works[wid].get("project") == "ModularStage", str(idx.works[wid].get("project")))
    r2 = register_work(idx, title="옛 등록 호환", target_repo="/r2")
    check("스탬프 없는 등록은 None (옛 호환 — 활성으로 해석된다)",
          idx.works[r2["work_id"]].get("project") is None)
    idx2 = TaskIndex(root)
    idx2.rebuild()
    check("[중요] 재기동(rebuild) 후에도 스탬프 생존",
          idx2.works[wid].get("project") == "ModularStage",
          str(idx2.works[wid].get("project")))


# ── ② 스탬프 해석 (모양 계약 — server._paths_for 는 클로저라 여기선 같은 규칙을 잰다) ──

def test_resolution_rule():
    # server.py `_paths_for` 의 규칙: work_meta.project → 그 프로젝트, 없으면 활성("")
    # 여기서는 규칙의 핵심(스탬프 우선)을 소스에서 확인한다 — 클로저를 뜯지 않고 계약을 못박는다.
    src = (Path(__file__).parent / "task_queue" / "server.py").read_text(encoding="utf-8")
    check("[중요] 종결 기록이 _paths_for(스탬프) 를 쓴다 — resolve(\"\") 아님",
          '_paths_for(r.get("work"))' in src)
    check("[중요] history/signals 가 work_id 스탬프로 푼다",
          src.count("_paths_for(work_id=req.work_id)") == 2,
          str(src.count("_paths_for(work_id=req.work_id)")))
    check("종결·신호·기록 경로에 resolve(\"\") 직접 호출이 안 남았다",
          'resolve("")' not in src)


# ── ③ 전환 가드 ──────────────────────────────────────────────

class Reg:
    """가짜 레지스트리 — 전환 가드만 잰다."""
    def __init__(self, active="A", names=("A", "B")):
        self.active = active
        self.names = list(names)
        self.saved = False

    def save(self):
        self.saved = True

    def config_of(self, name):
        class C:
            project_id = 1
            branch = "main"
            last_indexed_commit = ""
        return C()


def _patch_checks(monkey=True):
    """set_active 의 이름·상태 검사를 통과시키는 최소 패치."""
    import master.projects.logic as L
    orig = (L.validate_name, L._check_one)
    L.validate_name = lambda n: n
    L._check_one = lambda reg, n: []
    return L, orig


def test_switch_guard():
    L, orig = _patch_checks()
    try:
        reg = Reg()
        try:
            set_active("B", registry=reg,
                       works_fetcher=lambda: [{"work_id": "w1", "merge_status": "in_progress"}])
            check("[중요] 미종결 work 존재 → 거부", False)
        except ConfigError as e:
            check("[중요] 미종결 work 존재 → 거부", "미종결 work 1건" in str(e), str(e)[:80])
        check("거부 시 활성이 안 바뀐다", reg.active == "A" and not reg.saved)

        def boom():
            raise RuntimeError("큐 죽음")
        try:
            set_active("B", registry=reg, works_fetcher=boom)
            check("[중요] 큐 확인 불가 → 거부 (모르는 채 바꾸지 않는다)", False)
        except ConfigError as e:
            check("[중요] 큐 확인 불가 → 거부 (모르는 채 바꾸지 않는다)",
                  "확인하지 못했다" in str(e))

        r = set_active("B", registry=reg, force=True,
                       works_fetcher=lambda: [{"work_id": "w1", "merge_status": "in_progress"}])
        check("[중요] force 는 통과하되 무엇이 걸렸는지 남는다",
              r["ok"] and r.get("forced_over_open_works") == ["w1"]
              and "[중요]" in r.get("warning", ""), str(r.get("forced_over_open_works")))

        reg2 = Reg()
        r2 = set_active("B", registry=reg2,
                        works_fetcher=lambda: [{"work_id": "w0", "merge_status": "merged"}])
        check("종결(merged/rejected/cancelled)뿐이면 통과 — 경고 없음",
              r2["ok"] and "forced_over_open_works" not in r2)

        reg3 = Reg(active="B")
        r3 = set_active("B", registry=reg3, works_fetcher=boom)
        check("같은 프로젝트 재지정은 큐를 안 본다 (전환이 아니다)", r3["ok"])
    finally:
        L.validate_name, L._check_one = orig


def test_open_works_filter():
    got = open_works_in_queue(fetcher=lambda: [
        {"work_id": "a", "merge_status": "in_progress"},
        {"work_id": "b", "merge_status": "merged"},
        {"work_id": "c", "merge_status": "ready_for_review"},
        {"work_id": "d"},                                    # 상태 없음 = in_progress 취급
        {"work_id": "e", "merge_status": "cancelled"},
    ])
    check("[중요] 종결 3종만 걸러진다 (task_queue 와 같은 집합)",
          [w["work_id"] for w in got] == ["a", "c", "d"], str(got))


def main() -> int:
    for fn in (test_stamp_on_register, test_resolution_rule,
               test_switch_guard, test_open_works_filter):
        fn()
    print(f"{'OK' if not FAIL else '[실패]'} test_project_affinity: {PASS}/{PASS + FAIL} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
