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
from master.task_queue.logic import (claim_task, register_task,      # noqa: E402
                                     register_work, reopen_work)   # noqa: E402
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


def _work(fixed_version: str = ""):
    root = Path(tempfile.mkdtemp(prefix="ax-rounds-"))
    idx = TaskIndex(root)
    w = register_work(idx, title="상호작용", target_repo="/tmp/repo", project="NS",
                      target_branch="task/W/base", fixed_version=fixed_version)
    return idx, w["work_id"]


def test_improve_request_reopens_the_work() -> None:
    """🔴 **승격은 개선요청 하나뿐이다 — 조각 등재는 거절만 한다** (사용자 결정 2026-09-05).

    *"분산작업 등록과 라운드 값을 받는 분산작업 개선 요청으로 말이야"* ·
    *"라운드는 처음 작업 요청할 때는 1이고 … 머지하고 개선 요청을 받은 경우 +1 이 되서
    2 라운드 시작"*.

    종전에는 `register_task` 가 `ready_for_review` 를 보고 **부수효과로** 승격했다. 그래서
    등재가 「최초냐 개선요청이냐」를 상태로 추론했고, 상태가 예상 밖이면 조용히 틀렸다.
    """
    print("\n[1] 개선요청이 work 을 다음 라운드로 연다 — 조각 등재는 못 연다")
    idx, wid = _work()
    _round(idx, wid, 2)
    check("라운드 1 이 끝나면 `ready_for_review`",
          idx.works[wid]["merge_status"] == "ready_for_review", idx.works[wid]["merge_status"])
    idx.works[wid]["redmine_issue_id"] = 357          # 그 라운드의 공지

    # 🔴 개선요청 없이 조각부터 등재하면 **거절**이다 (종전에는 조용히 승격했다)
    r = register_task(idx, work_id=wid, type="code", task_data={},
                      target_file="Source/A/R0.cpp", stem="r0b")
    check("🔴 조각 등재는 라운드를 못 연다 — 거절하고 사유를 낸다",
          r.get("ok") is False and r.get("reason") == "round_closed", str(r)[:200])
    check("  사유가 무엇을 부르라고 말한다", "개선요청" in str(r.get("error")), str(r)[:200])
    check("  분모는 그대로 (반쪽 등재가 안 남는다)", int(idx.works[wid]["total"]) == 2,
          str(idx.works[wid]["total"]))

    got = reopen_work(idx, work_id=wid, expected_round=2)
    check("🔴 개선요청이 라운드 2를 연다", got.get("ok") and got.get("round") == 2, str(got)[:200])
    check("  **다시 `in_progress`** — 아니면 다음 라운드가 파견되지 않는다",
          idx.works[wid]["merge_status"] == "in_progress", idx.works[wid]["merge_status"])
    check("🔴 **이슈 id 는 그대로 둔다** — work 하나에 이슈 하나, 라운드는 노트로 쌓인다",
          idx.works[wid].get("redmine_issue_id") == 357,
          str(idx.works[wid].get("redmine_issue_id")))

    r2 = register_task(idx, work_id=wid, type="code", task_data={},
                       target_file="Source/A/R0.cpp", stem="r0b")
    check("  연 뒤에는 등재가 된다", bool(r2.get("task_id")), str(r2)[:160])
    check("  분모가 늘어난다 (2 → 3)", int(idx.works[wid]["total"]) == 3,
          str(idx.works[wid]["total"]))


def test_round_value_is_a_check_not_a_command() -> None:
    """🔴 **라운드 값은 확인용이다 — 어긋나면 맞추지 않고 거절한다** (사용자 결정 2026-09-05).

    값은 큐가 이미 안다(현재+1). 요청자가 싣는 것은 *"내가 아는 라운드가 이거다"* 라는 대조이고,
    어긋난다는 것은 **둘이 서로 다른 라운드를 보고 있다**는 뜻이라 그대로 진행하면 지난 라운드
    브랜치와 섞인다.
    """
    print("\n[1.5] 라운드 값 대조")
    idx, wid = _work()
    _round(idx, wid, 1)
    bad = reopen_work(idx, work_id=wid, expected_round=5)
    check("🔴 어긋난 라운드는 거절 — 맞추지 않는다",
          bad.get("ok") is False and bad.get("reason") == "round_mismatch", str(bad)[:200])
    check("  큐가 아는 다음 라운드를 말해 준다", bad.get("next_round") == 2, str(bad)[:200])
    check("  거절이 상태를 바꾸지 않는다",
          idx.works[wid]["merge_status"] == "ready_for_review" and idx.works[wid]["round"] == 1,
          f"{idx.works[wid]['merge_status']} r{idx.works[wid]['round']}")
    none = reopen_work(idx, work_id=wid)
    check("  값이 없으면 거절 (몇 라운드를 여는지 말하는 호출이다)",
          none.get("ok") is False and none.get("reason") == "round_required", str(none)[:160])

    ok = reopen_work(idx, work_id=wid, expected_round=2)
    check("맞는 값이면 연다", ok.get("ok") and ok.get("reopened") is True, str(ok)[:160])
    again = reopen_work(idx, work_id=wid, expected_round=2)
    check("🔴 **승격만 되고 등재가 실패한 재시도는 통과한다** (그 라운드 조각 0건)",
          again.get("ok") and again.get("reopened") is False, str(again)[:200])
    register_task(idx, work_id=wid, type="code", task_data={}, target_file="a.cpp", stem="a")
    stuck = reopen_work(idx, work_id=wid, expected_round=2)
    check("  조각이 들어온 뒤에는 도는 라운드에 못 밀어 넣는다",
          stuck.get("ok") is False and stuck.get("reason") == "not_reopenable", str(stuck)[:200])


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
        reopen_work(idx, work_id=wid, expected_round=2)          # 개선요청이 연다
        register_task(idx, work_id=wid, type="code", task_data={},
                      target_file="Source/A/R0.cpp", stem="again")
        ok2, why2 = AD.should_dispatch(None, wid, api=api)
        check("🔴 개선요청 + 조각 등재면 게이트를 통과한다 (막히면 라운드가 한 번뿐이다)",
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
    LC._redmine_post_issue = lambda cfg, subj, desc, fv="": (made.append((subj, desc, fv)) or 901)
    try:
        idx, wid = _work(fixed_version="마일스톤 1")
        for _ in range(200):
            if made:
                break
            time.sleep(0.01)
        check("🔴 등재만으로 이슈가 난다", len(made) == 1, str(made)[:160])
        check("  제목이 분산 작업임을 말한다", made and made[0][0].startswith("[분산 작업]"),
              str(made)[:120])
        check("  work 에 id 가 기록된다", idx.works[wid].get("redmine_issue_id") == 901,
              str(idx.works[wid].get("redmine_issue_id")))
        # 🔴 `#652` — 등재가 실은 마일스톤이 **이슈 생성까지 간다**. 종전에는 이 인자가
        #    아예 없어서 `[분산 작업]` 이슈가 구조적으로 무버전이었다(실측 `ns` 24/24).
        check("  🔴 마일스톤이 이슈 생성까지 간다", made and made[0][2] == "마일스톤 1",
              str(made and made[0][2]))
        check("  work 에도 스탬프가 남는다", idx.works[wid].get("fixed_version") == "마일스톤 1",
              str(idx.works[wid].get("fixed_version")))
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
    LC._redmine_post_issue = lambda cfg, subj, desc, fv="": (made.append(subj) or 900)
    LC._redmine_add_note = lambda cfg, iid, notes_, status_name="": (
        notes.append((iid, notes_)) or True)
    try:
        idx, wid = _work()
        idx.works[wid]["redmine_issue_id"] = 900          # 등재 때 만들어진 이슈
        _round(idx, wid, 1)
        # `#895` — 노트 전송 뒤 멱등 표시가 저장된다. 저장 잠금이 풀릴 때까지 기다린다.
        for _ in range(200):
            with idx.lock:
                if int(idx.works[wid].get("noticed_round", 0)) == 1:
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


# ── `#814` 요청자 분기 — 트윈 `config.yaml` 이 정한다 (`.33` 을 기본값으로 박지 않는다) ──────────
_TWIN_SHOPS = {
    "workshop": ("workshops:\n"
                 "  192.168.0.33:\n    driven: ssh\n    role: requester\n    user: user\n"
                 "    path: C:\\x\n"
                 "  192.168.0.2:\n    driven: ssh\n    role: worker\n    user: janus\n"
                 "    path: E:\\x\n"),
    # AXCluster 모양 — `.33` 이 있어도 **워커**이고 요청자는 마스터다
    "master": ("requester: master\n"
               "workshops:\n"
               "  192.168.0.33:\n    driven: ssh\n    role: worker\n    user: user\n"
               "    path: C:\\x\n"),
    "unknown": ("requester: Master57\n"
                "workshops:\n"
                "  192.168.0.33:\n    driven: ssh\n    role: requester\n    user: user\n"
                "    path: C:\\x\n"),
    "none": ("workshops:\n"
             "  192.168.0.2:\n    driven: ssh\n    role: worker\n    user: janus\n"
             "    path: E:\\x\n"),
}


def _twin_root(kind: str) -> Path:
    root = Path(tempfile.mkdtemp(prefix="ax-twin-"))
    (root / "projects.yaml").write_text("version: 1\nactive: NS\nprojects:\n- NS\n",
                                        encoding="utf-8")
    (root / "NS").mkdir()
    (root / "NS" / "config.yaml").write_text(
        "version: 1\nname: NS\nredmine:\n  project: ns\n" + _TWIN_SHOPS[kind], encoding="utf-8")
    return root


def _texts_for(kind: str, target_branch: str = "task/W/base") -> tuple:
    """(등재 이슈 본문, 라운드 완료 노트, work_id, 큐 로그) — 레드마인은 가짜, 트윈은 임시 루트."""
    import os
    from unittest.mock import patch
    from master.task_queue import logic_cleanup as LC
    made: list = []
    notes: list = []
    logs: list = []     # `_tq_log` 은 하루 한 파일(첫 루트)에 쓰므로 파일이 아니라 호출을 본다
    with patch.dict(os.environ, {"AX_PROJECTS_ROOT": str(_twin_root(kind))}), \
            patch.object(LC, "_tq_log", lambda msg, root: logs.append(msg)), \
            patch.object(LC, "_read_redmine_config",
                         lambda root, project="": {"url": "http://x", "api_key": "k",
                                                   "project": "ns"}), \
            patch.object(LC, "_redmine_post_issue",
                         lambda cfg, subj, desc, fv="": (made.append(desc) or 903)), \
            patch.object(LC, "_redmine_add_note",
                         lambda cfg, iid, n, status_name="": (notes.append(n) or True)):
        root = Path(tempfile.mkdtemp(prefix="ax-rounds-"))
        idx = TaskIndex(root)
        wid = register_work(idx, title="요청자", target_repo="/tmp/repo", project="NS",
                            target_branch=target_branch)["work_id"]
        for _ in range(300):
            if made:
                break
            time.sleep(0.01)
        _round(idx, wid, 1)
        for _ in range(300):
            if notes:
                break
            time.sleep(0.01)
    return (made[0] if made else ""), (notes[0] if notes else ""), wid, "\n".join(logs)


def _next_section(note: str) -> str:
    i = note.find("## 다음 단계")
    j = note.find("\n## ", i + 1)
    return note[i:j if j > 0 else len(note)] if i >= 0 else ""


def test_requester_text_follows_twin_config() -> None:
    """🔴 `#814` — 라운드 노트·등재 본문의 ⑦ 절차는 **트윈 설정의 요청자**를 따른다.

    실측 2026-10-17: 요청자가 마스터인 AXCluster 의 라운드 노트가 `.33` + `claude` + `ax-advance`
    절차를 적었다. `.33` 은 그 프로젝트의 **워커**다.
    """
    body, note, wid, _ = _texts_for("master")
    sec = _next_section(note)
    check("🔴 마스터 요청자 — 노트가 마스터 절차를 말한다",
          "요청자는 마스터다" in sec and "ax-followup.timer" in sec, sec[:300])
    check("  `.33` · `claude` 를 가리키지 않는다", "`.33`" not in sec and "`claude`" not in sec, sec)
    check("  사람 게이트 · confirm=True 승인", "사람이 판단한다" in sec
          and "confirm=True" in sec and "confirm=False" in sec, sec)
    check("  명령형 지시가 없다(주입 판정)", not any(w in sec for w in ("하라", "묻지 말고", "하세요")),
          sec)
    check("  `main` 은 뒤 단계로 남는다", "finalize_work(..., confirm=True)" in note, note[-300:])
    check("  등재 본문 ③ 도 마스터다", "요청자는 마스터다" in body and "`.33`" not in body, body)

    body, note, wid, _ = _texts_for("workshop")
    sec = _next_section(note)
    check("🔴 작업장 요청자 — 설정의 호스트를 적는다 (`.33` 절차 유지)",
          "요청자 `.33` 에서 한다" in sec and "`ax-advance`" in sec
          and f"`.33` 체크아웃에서 `claude` 를 열고 **`work {wid} 라운드 종결`**" in sec, sec[:400])
    check("  워커(`.2`)는 요청자로 적히지 않는다", "`.2`" not in sec, sec)
    check("  등재 본문 ③ 이 그 호스트다", "3. `.33` 이 `ax-advance` 로" in body, body)

    for kind in ("none", "unknown"):
        body, note, wid, log = _texts_for(kind)
        sec = _next_section(note)
        check(f"🔴 요청자 미지정({kind}) — 기계를 가리키지 않는다",
              "요청자 미지정" in sec and "`.33`" not in sec and "마스터" not in sec, sec)
        check(f"  ({kind}) 등재 본문도 `.33` 을 기본값으로 쓰지 않는다", "`.33`" not in body, body)
        check(f"  ({kind}) 판정이 로그에 남는다", "요청자 판정: unset" in log, log[-300:])
    check("  모르는 값은 그 값과 함께 사유를 적는다",
          "`requester: Master57` 는 인식하지 않는 값이다" in sec, sec)


def test_unreadable_twin_is_neutral_and_logged() -> None:
    """설정을 못 읽으면(`AX_PROJECTS_ROOT` 없음) 미지정 문구 · 사유는 로그로 (침묵하지 않는다)."""
    import os
    from unittest.mock import patch
    from master.task_queue import logic_cleanup as LC
    root = Path(tempfile.mkdtemp(prefix="ax-rounds-"))
    env = {k: v for k, v in os.environ.items() if k != "AX_PROJECTS_ROOT"}
    logs: list = []
    with patch.dict(os.environ, env, clear=True), \
            patch.object(LC, "_tq_log", lambda msg, r: logs.append(msg)):
        prof = LC._requester_profile(root, "W9", "NS")
    log = "\n".join(logs)
    check("설정 못 읽음 → unset · unreadable", prof["kind"] == "unset"
          and prof["why"] == "unreadable", str(prof))
    check("  사유가 로그에 남는다", "트윈 설정을 못 읽었다" in log, log[-300:])
    check("  노트 사유 줄에 절대 경로가 없다", "/" not in LC._unset_reason_line(prof),
          LC._unset_reason_line(prof))


def test_work_branch_is_derived_when_unstored() -> None:
    """🔴 `#814` ③ — `target_branch` 를 비워 등재해도 노트는 실재 브랜치를 적는다(`(unknown)` 아님)."""
    body, note, wid, _ = _texts_for("master", target_branch="")
    want = f"task/{wid}/base"
    check("🔴 라운드 노트가 유도된 작업 브랜치를 적는다", f"`origin/{want}`" in note
          and "(unknown)" not in note, note[:300])
    check("  등재 본문도 같다", f"`{want}`" in body and "(unknown)" not in body, body)
    body, note, wid, _ = _texts_for("master", target_branch="feature/kept")
    check("  저장값이 이긴다", "`origin/feature/kept`" in note and "`feature/kept`" in body,
          note[:300])


def test_requester_key_round_trips() -> None:
    """`requester:` 는 `ProjectConfig` 왕복에서 살아남는다 — 모르는 값도 지우지 않는다."""
    from master.projects.config import ProjectConfig
    for kind, want, is_master in (("master", "master", True), ("unknown", "Master57", False),
                                  ("workshop", "", False)):
        p = _twin_root(kind) / "NS" / "config.yaml"
        cfg = ProjectConfig.load(p)
        p.write_text(cfg.to_yaml(), encoding="utf-8")
        again = ProjectConfig.load(p)
        check(f"왕복 ({kind}) requester={want!r}", cfg.requester == want == again.requester
              and again.requester_is_master is is_master, f"{cfg.requester!r} {again.requester!r}")
        check(f"  ({kind}) 빈 값은 키를 만들지 않는다", ("requester:" in p.read_text("utf-8")) == bool(want),
              p.read_text("utf-8")[:200])
    cfg = ProjectConfig.load(_twin_root("workshop") / "NS" / "config.yaml")
    check("  requester_hosts 는 role: requester 작업장만", cfg.requester_hosts() == ["192.168.0.33"],
          str(cfg.requester_hosts()))


def test_registration_itself_triggers_dispatch() -> None:
    """🔴 **등재도 트리거다 — 단 라이브 큐일 때만** (사용자 2026-09-05).

    종전 트리거는 골조 push 하나뿐이었다. 라운드 2 실측: 요청자가 push(01:35:01) → 등재
    (01:35:53) 순으로 했더니 그 push 는 *"진행 중인 work 만 민다"* 로 거절됐고, 등재 뒤에는
    새 push 가 없어 **트리거가 다시 안 울렸다.** 조각 3건이 catchup(10분)을 기다렸다.

    🔴 [주의] **임시 큐 루트에서는 쓰지 않는다.** 이 가드가 없어서 테스트가 라이브 스풀
    (`~/ax-spool/dispatch`)에 가짜 신호를 썼고, 파견 유닛이 15초에 다섯 번 깨어나
    `start-limit-hit` 으로 죽었다(2026-09-05). `#345` 와 같은 뿌리다.
    """
    import os as _os
    from master.work import autodispatch as AD
    calls: list = []
    saved = AD.note_trigger
    AD.note_trigger = lambda wid, project, ref="": calls.append((wid, project, ref))
    try:
        # ⓐ 임시 루트 — 신호를 쓰지 않는다 (기본 상태)
        idx, wid = _work()
        register_task(idx, work_id=wid, type="code", task_data={},
                      target_file="Source/A/T.cpp", stem="t")
        check("🔴 임시 큐 루트에서는 신호를 안 쓴다 (라이브 스풀 오염 금지)",
              calls == [], str(calls))

        # ⓑ 그 루트를 라이브로 선언하면 — 쓴다
        prev = _os.environ.get("AX_TASK_QUEUE_ROOT")
        _os.environ["AX_TASK_QUEUE_ROOT"] = str(idx.root)
        try:
            register_task(idx, work_id=wid, type="code", task_data={},
                          target_file="Source/A/U.cpp", stem="u")
        finally:
            if prev is None:
                _os.environ.pop("AX_TASK_QUEUE_ROOT", None)
            else:
                _os.environ["AX_TASK_QUEUE_ROOT"] = prev
        check("🔴 라이브 큐면 등재가 신호를 남긴다", [c[0] for c in calls] == [wid], str(calls))
        check("  프로젝트 스탬프를 싣는다", calls and calls[0][1] == "NS", str(calls))
        check("  출처를 적는다 (push 와 구분된다)", calls and calls[0][2] == "register",
              str(calls))
    finally:
        AD.note_trigger = saved


def test_bad_trigger_is_quarantined_not_left_to_thrash() -> None:
    """🔴 **못 쓰는 트리거는 `*.json` 밖으로 치운다** (실측 2026-09-05).

    `ax-dispatch.path` 는 `PathExistsGlob=…/*.json` 이라 그 파일이 남아 있는 한 계속 깨운다.
    종전 규칙은 *"못 읽는 파일은 지우지 않고 사유만 찍는다"*(증거 보존)였고, 그 하나가
    유닛을 `start-limit-hit` 으로 죽였다 — 그 뒤로는 push 트리거가 **아예** 안 걸린다.
    지우지 않고 이름만 바꾼다: 증거는 남고 glob 에서는 빠진다.
    """
    import tempfile as _tf
    from pathlib import Path as _P
    from master.work import autodispatch as AD
    d = _P(_tf.mkdtemp(prefix="ax-trig-"))
    saved = AD.TRIGGER_DIR
    AD.TRIGGER_DIR = d
    try:
        (d / "broken.json").write_text("{ 이건 JSON 이 아니다", encoding="utf-8")
        (d / "noid.json").write_text('{"ref": "register"}', encoding="utf-8")
        (d / "good.json").write_text('{"work_id": "w1", "project": "NS"}', encoding="utf-8")
        got = AD._read_triggers()
        check("정상 트리거만 돌려준다", [g[0] for g in got] == ["w1"], str(got))
        left = sorted(f.name for f in d.glob("*.json"))
        check("🔴 못 쓰는 것은 glob 에서 빠진다 (유닛이 다시 안 깨어난다)",
              left == ["good.json"], str(left))
        bad = sorted(f.name for f in d.glob("*.json.bad"))
        check("  증거는 남는다", bad == ["broken.json.bad", "noid.json.bad"], str(bad))
    finally:
        AD.TRIGGER_DIR = saved


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
    reopen_work(idx, work_id=wid, expected_round=2)           # 🔴 개선요청이 라운드를 올린다
    t2 = register_task(idx, work_id=wid, type="code", task_data={},
                       target_file="a.cpp", stem="a2")["task_id"]
    check("🔴 개선요청 뒤 work 라운드가 2", int(idx.works[wid]["round"]) == 2,
          str(idx.works[wid]["round"]))
    check("  새 조각에 라운드 2 가 새겨진다", idx.tasks[t2]["round"] == 2,
          str(idx.tasks[t2]["round"]))
    check("  지난 조각은 안 따라간다", idx.tasks[t1]["round"] == 1, str(idx.tasks[t1]["round"]))


# [주의] 전진이 이번 라운드만 머지하는지는 **실물 저장소**가 필요해서
#    `test_review.test_advance_merges_only_this_round` 에 있다 — 여기서 스텁으로 재면
#    `advance_work` 가 fetch 단계에서 먼저 죽어 **필터를 통과했는지조차 못 잰다**(실측).


def test_finished_work_is_not_revived() -> None:
    print("\n[3] 마감된 work 은 되살리지 않는다 — 조각도 안 받는다")
    for st in ("merged", "rejected", "cancelled"):
        idx, wid = _work()
        _round(idx, wid, 1)
        idx.works[wid]["merge_status"] = st
        r = register_task(idx, work_id=wid, type="code", task_data={},
                          target_file="Source/A/X.cpp", stem="x")
        # 🔴 종전에는 **등재가 성공**했다 — 조각이 pending 에 박히고 파견 게이트가 영원히
        #    거절해 조용한 교착이 됐다. 이제 입구에서 사유를 내고 거절한다.
        check(f"  {st}: 조각 등재를 거절한다",
              r.get("ok") is False and r.get("reason") == "work_closed", str(r)[:160])
        check(f"  {st} 는 그대로", idx.works[wid]["merge_status"] == st,
              idx.works[wid]["merge_status"])
        ro = reopen_work(idx, work_id=wid, expected_round=2)
        check(f"  {st}: 개선요청도 거절한다",
              ro.get("ok") is False and ro.get("reason") == "not_reopenable", str(ro)[:160])


def test_skeleton_rework_reopens_only_with_advance_evidence():
    from master.task_queue.logic_persist import completed_work_status
    idx, wid = _work()
    registered = register_task(idx, work_id=wid, type="code", task_data={},
                               target_file="Source/A/Failed.cpp", stem="failed")
    claimed = claim_task(idx, "192.168.0.2", capabilities=["ue5"], types=["code"])
    LL.submit_fail(idx, claimed["task_id"], "BLOCKED", "[kind:skeleton] 동결 위반",
                   worker_id="192.168.0.2", epoch=claimed["epoch"])
    check("골조실패상태이력유지", idx.tasks[registered["task_id"]]["status"] == "failed")
    no_evidence = reopen_work(idx, work_id=wid, expected_round=2)
    check("전진근거없으면골조실패재개거절", not no_evidence["ok"])
    evidence = {"result": "rework_advanced", "round": 1,
                "head": "a" * 40, "target_branch": "task/W/base"}
    for key, value in (("round", 9), ("target_branch", "main"), ("head", "bad")):
        idx.works[wid]["review_decision"] = dict(evidence, **{key: value})
        check(f"전진근거{key}불일치거절", not reopen_work(idx, work_id=wid, expected_round=2, rework=True)["ok"])
    idx.works[wid]["review_decision"] = evidence
    check("전진근거있어도rework명시없으면거절", not reopen_work(idx, work_id=wid, expected_round=2)["ok"])
    result = reopen_work(idx, work_id=wid, expected_round=2, rework=True)
    check("정확한전진근거면2라운드재개", result["ok"] and result["round"] == 2, str(result))
    second = register_task(idx, work_id=wid, type="code", task_data={},
                           target_file="Source/A/Repaired.cpp", stem="repaired")
    third = register_task(idx, work_id=wid, type="code", task_data={},
                          target_file="Source/A/Repaired2.cpp", stem="repaired2")
    check("지난라운드failed로2차pending종결안함", completed_work_status(idx, wid) == "")
    check("지난라운드failed이력보존", idx.tasks[registered["task_id"]]["status"] == "failed")
    claim = claim_task(idx, "192.168.0.2", capabilities=["ue5"], types=["code"])
    LL.submit_result(idx, second["task_id"], branch="b", head_commit="abc1234", self_check={},
                     epoch=claim["epoch"], worker_id="192.168.0.2")
    LL.verify_task(idx, second["task_id"], passed=True, result="pass")
    check("2차한조각성공다른pending이면in_progress유지", idx.works[wid]["merge_status"] == "in_progress")
    claim2 = claim_task(idx, "192.168.0.2", capabilities=["ue5"], types=["code"])
    check("2차다른claimed도종결안함", completed_work_status(idx, wid) == "")
    LL.submit_result(idx, third["task_id"], branch="b2", head_commit="def1234", self_check={},
                     epoch=claim2["epoch"], worker_id="192.168.0.2")
    LL.verify_task(idx, third["task_id"], passed=True, result="pass")
    check("2차성공은지난failed와분리되어ready", idx.works[wid]["merge_status"] == "ready_for_review")
    rebuilt = TaskIndex(idx.root)
    rebuilt.rebuild()
    check("전진기준기록rebuild보존", rebuilt.works[wid]["rework_base_commit"] == "a" * 40)


def main() -> int:
    print("=== work 은 라운드를 여러 번 돈다 — 마감은 사람이 한다 ===")
    for fn in (test_improve_request_reopens_the_work,
               test_round_value_is_a_check_not_a_command, test_dispatch_gate_agrees,
               test_issue_is_created_at_registration,
               test_completion_is_a_note_not_a_new_issue,
               test_registration_itself_triggers_dispatch,
               test_bad_trigger_is_quarantined_not_left_to_thrash,
               test_round_is_in_the_branch_name,
               test_finished_work_is_not_revived,
               test_skeleton_rework_reopens_only_with_advance_evidence,
               test_requester_text_follows_twin_config,
               test_unreadable_twin_is_neutral_and_logged,
               test_work_branch_is_derived_when_unstored,
               test_requester_key_round_trips):
        fn()
    print(("\nFAIL" if _fail else "\nOK") + f" test_rounds: 실패 {_fail}건")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
