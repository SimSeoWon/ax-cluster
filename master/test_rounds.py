"""🔴 분산 작업(work)은 **여러 라운드**를 돈다 — 라운드가 끝나도 work 은 안 닫힌다.

사용자 2026-09-04: *"분산 작업을 지금 워크라고 말하는거지? 그럼 워크 왜 꺼야해 아직
안끝난거잖아. 내가 개수할게 남았다고 했잖아"*.

    라운드 N   조각 등재 → 파견 → 워커 커밋 → 전부 terminal → `ready_for_review` → `.33` 공지
    ⑺          `.33` 이 서브 브랜치를 작업 브랜치에 머지·빌드 → 전진(push)
    라운드 N+1 더 고칠 것이 있으면 **그 브랜치에 조각을 다시 등재** → ④부터 다시
    마감       사람이 *"더 없다"* 라고 할 때만 work 이 끝난다

[중요] **그래서 재개 전이가 필요하다.** `ready_for_review` 로 남아 있으면
`autodispatch.should_dispatch` 가 *"진행 중인 work 만 민다"* 로 거절해서
**다음 라운드가 영원히 파견되지 않는다.** 조각이 새로 들어온 순간이 곧 「다시 진행 중」이다.

`.venv/bin/python master/test_rounds.py`
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.task_queue import logic_lifecycle as LL                            # noqa: E402
from master.task_queue.logic import claim_task, register_task, register_work   # noqa: E402
from master.task_queue.persistence import TaskIndex                            # noqa: E402
from master.work import autodispatch as AD                                     # noqa: E402

_fail = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global _fail
    if ok:
        print(f"  [완료] {label}")
    else:
        _fail += 1
        print(f"  [실패] {label}" + (f" — {detail}" if detail else ""))


def _round(idx, wid: str, n: int = 1) -> list:
    """조각 `n` 개를 등재하고 전부 정상 종결시킨다 (= 라운드 하나)."""
    tids = []
    for i in range(n):
        r = register_task(idx, work_id=wid, type="code", task_data={},
                          target_file=f"Source/A/R{i}.cpp", stem=f"r{i}")
        tids.append(r["task_id"])
    for t in tids:
        c = claim_task(idx, "192.168.0.2", capabilities=["ue5"], types=["code"])
        LL.submit_result(idx, c["task_id"], branch="b", head_commit="abc1234",
                         self_check={}, epoch=int(c.get("epoch", 1)), worker_id="192.168.0.2")
        LL.verify_task(idx, c["task_id"], passed=True, result="pass")
    return tids


def _work():
    root = Path(tempfile.mkdtemp(prefix="ax-rounds-"))
    idx = TaskIndex(root)
    w = register_work(idx, title="상호작용", target_repo="/tmp/repo", project="NS",
                      target_branch="task/W/base")
    return idx, w["work_id"]


def test_new_tasks_reopen_the_work() -> None:
    print("\n[1] 라운드 N+1 조각이 등재되면 work 이 다시 열린다")
    idx, wid = _work()
    _round(idx, wid, 2)
    check("라운드 1 이 끝나면 `ready_for_review`",
          idx.works[wid]["merge_status"] == "ready_for_review", idx.works[wid]["merge_status"])
    idx.works[wid]["redmine_issue_id"] = 357          # 그 라운드의 공지

    register_task(idx, work_id=wid, type="code", task_data={},
                  target_file="Source/A/R0.cpp", stem="r0b")
    check("🔴 **다시 `in_progress`** — 아니면 다음 라운드가 파견되지 않는다",
          idx.works[wid]["merge_status"] == "in_progress", idx.works[wid]["merge_status"])
    check("  분모가 늘어난다 (2 → 3)", int(idx.works[wid]["total"]) == 3,
          str(idx.works[wid]["total"]))
    check("🔴 **이슈 id 는 그대로 둔다** — work 하나에 이슈 하나, 라운드는 노트로 쌓인다",
          idx.works[wid].get("redmine_issue_id") == 357,
          str(idx.works[wid].get("redmine_issue_id")))


def test_dispatch_gate_agrees() -> None:
    print("\n[2] 파견 게이트가 그 전이를 실제로 받는다")
    idx, wid = _work()
    _round(idx, wid, 1)

    def api(method, path, payload=None, **kw):
        w = dict(idx.works[wid])
        return {"work": w, "tasks": [dict(t) for t in idx.tasks.values()]}

    class _Base:                       # 골조 커밋은 이 테스트의 관심사가 아니다
        checked, exists, commit, branch, error = True, True, "abc1234def", "task/W/base", ""

    import master.work.twin_base as TB
    saved = TB.resolve
    TB.resolve = lambda paths, w: _Base()
    try:
        ok, why = AD.should_dispatch(None, wid, api=api)
        check("라운드 끝난 상태에서는 안 민다", not ok and "진행 중인 work" in why, f"{ok} {why}")
        register_task(idx, work_id=wid, type="code", task_data={},
                      target_file="Source/A/R0.cpp", stem="again")
        ok2, why2 = AD.should_dispatch(None, wid, api=api)
        check("🔴 조각을 등재하면 게이트를 통과한다 (여기서 막히면 라운드가 한 번뿐이다)",
              ok2, f"{ok2} {why2}")
    finally:
        TB.resolve = saved


def test_issue_is_created_at_registration() -> None:
    """🔴 **등재 시점에** 이슈가 난다 — 완료를 기다리지 않는다 (사용자 2026-09-04)."""
    from master.task_queue import logic_cleanup as LC
    made: list = []
    s_cfg, s_new = LC._read_redmine_config, LC._redmine_post_issue
    LC._read_redmine_config = lambda root, project="": {"url": "http://x", "api_key": "k",
                                                        "project": "ns"}
    LC._redmine_post_issue = lambda cfg, subj, desc: (made.append((subj, desc)) or 901)
    try:
        idx, wid = _work()
        for _ in range(200):
            if made:
                break
            time.sleep(0.01)
        check("🔴 등재만으로 이슈가 난다", len(made) == 1, str(made)[:160])
        check("  제목이 분산 작업임을 말한다", made and made[0][0].startswith("[분산 작업]"),
              str(made)[:120])
        check("  work 에 id 가 기록된다", idx.works[wid].get("redmine_issue_id") == 901,
              str(idx.works[wid].get("redmine_issue_id")))
    finally:
        LC._read_redmine_config, LC._redmine_post_issue = s_cfg, s_new


def test_completion_is_a_note_not_a_new_issue() -> None:
    """🔴 이슈는 **등재 때** 만들고, 라운드 완료는 그 이슈에 **노트**로 붙는다.

    사용자 2026-09-04: *"완료시 만들지말고 작업 등재할때 만들라고"* · *"추가 개선 요청했을때
    레드마인에 내용이 기입되어야 할 꺼같은데 지금은 모든 분산 작업이 완료된 후 처리하니까
    이것도 타이밍이 안맞고"*.
    """
    from master.task_queue import logic_cleanup as LC
    made: list = []
    notes: list = []
    s_cfg, s_new, s_note = (LC._read_redmine_config, LC._redmine_post_issue,
                            LC._redmine_add_note)
    LC._read_redmine_config = lambda root, project="": {"url": "http://x", "api_key": "k",
                                                        "project": "ns"}
    LC._redmine_post_issue = lambda cfg, subj, desc: (made.append(subj) or 900)
    LC._redmine_add_note = lambda cfg, iid, notes_, status_name="": (
        notes.append((iid, notes_)) or True)
    try:
        idx, wid = _work()
        idx.works[wid]["redmine_issue_id"] = 900          # 등재 때 만들어진 이슈
        _round(idx, wid, 1)
        for _ in range(200):
            if notes:
                break
            time.sleep(0.01)
        check("🔴 새 이슈를 만들지 않는다", not made, str(made))
        check("  그 이슈에 노트가 붙는다", [i for i, _ in notes] == [900], str(notes))
        check("  노트가 라운드를 말한다", any("라운드 1" in n for _, n in notes),
              str(notes)[:200])
        # 🔴 실측 2026-09-05 00:06 — 노트 본문이 브랜치 이름을 **직접 조립**해서 `r1/` 이
        #    빠졌다. 사람이 읽는 목록이 실물과 다른 브랜치를 가리켰다.
        check("🔴 브랜치 이름에 라운드가 들어간다 (본문에서 조립하지 않는다)",
              all("/r1/" in n for _, n in notes if "서브 브랜치" in n), str(notes)[:400])
        # 🔴 실측 같은 시각 — `update_work_meta` 는 화이트리스트라 없는 키워드에 TypeError 를
        #    냈고, 노트는 붙었는데 멱등 표시가 안 남았다.
        check("🔴 멱등 표시가 저장된다 (같은 라운드를 두 번 안 적는다)",
              int(idx.works[wid].get("noticed_round", 0)) == 1,
              str(idx.works[wid].get("noticed_round")))
    finally:
        (LC._read_redmine_config, LC._redmine_post_issue,
         LC._redmine_add_note) = s_cfg, s_new, s_note


def test_round_is_in_the_branch_name() -> None:
    """🔴 **이름 자체에 라운드가 들어간다** (사용자 2026-09-04).

    *"이미 전진했는데 그냥 다 머지하는게 말이 안되는거니까. 이름 자체에 라운드 번호를
    넣는건 좋은 아이디어"*.
    """
    from master.work.branch_names import durable_branch
    check("라운드 1 → task/W/r1/T", durable_branch("W", "T", 1) == "task/W/r1/T",
          durable_branch("W", "T", 1))
    check("라운드 2 → task/W/r2/T", durable_branch("W", "T", 2) == "task/W/r2/T",
          durable_branch("W", "T", 2))
    check("[주의] 스탬프가 없으면 옛 이름 그대로 (조용히 다른 데로 보내지 않는다)",
          durable_branch("W", "T") == "task/W/T", durable_branch("W", "T"))

    idx, wid = _work()
    t1 = _round(idx, wid, 1)[0]                           # 라운드 1 — 등재부터 종결까지
    check("첫 조각은 라운드 1", idx.tasks[t1]["round"] == 1, str(idx.tasks[t1]["round"]))
    t2 = register_task(idx, work_id=wid, type="code", task_data={},
                       target_file="a.cpp", stem="a2")["task_id"]
    check("🔴 재개하면 work 라운드가 2", int(idx.works[wid]["round"]) == 2,
          str(idx.works[wid]["round"]))
    check("  새 조각에 라운드 2 가 새겨진다", idx.tasks[t2]["round"] == 2,
          str(idx.tasks[t2]["round"]))
    check("  지난 조각은 안 따라간다", idx.tasks[t1]["round"] == 1, str(idx.tasks[t1]["round"]))


# [주의] 전진이 이번 라운드만 머지하는지는 **실물 저장소**가 필요해서
#    `test_review.test_advance_merges_only_this_round` 에 있다 — 여기서 스텁으로 재면
#    `advance_work` 가 fetch 단계에서 먼저 죽어 **필터를 통과했는지조차 못 잰다**(실측).


def test_finished_work_is_not_revived() -> None:
    print("\n[3] 마감된 work 은 되살리지 않는다")
    for st in ("merged", "rejected", "cancelled"):
        idx, wid = _work()
        _round(idx, wid, 1)
        idx.works[wid]["merge_status"] = st
        register_task(idx, work_id=wid, type="code", task_data={},
                      target_file="Source/A/X.cpp", stem="x")
        check(f"  {st} 는 그대로", idx.works[wid]["merge_status"] == st,
              idx.works[wid]["merge_status"])


def main() -> int:
    print("=== work 은 라운드를 여러 번 돈다 — 마감은 사람이 한다 ===")
    for fn in (test_new_tasks_reopen_the_work, test_dispatch_gate_agrees,
               test_issue_is_created_at_registration,
               test_completion_is_a_note_not_a_new_issue,
               test_round_is_in_the_branch_name,
               test_finished_work_is_not_revived):
        fn()
    print(("\nFAIL" if _fail else "\nOK") + f" test_rounds: 실패 {_fail}건")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
