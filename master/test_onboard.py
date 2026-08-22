"""온보딩 판정기 (`#259` 1차) — **읽기 전용 판정만.** 실행기는 아직 없다.

[중요] **판정기부터 검증하는 순서다.** 새 프로젝트에 처음 돌리기 전에, 이미 초기화된 프로젝트
(ModularStage)에서 여섯 단계가 **전부 참**으로 나오는지 · 아무것도 없는 프로젝트에서 **남은 것을
이름으로** 답하는지 본다. 판정이 틀린 실행기는 「했다」고 거짓 보고한다.

`python3 master/test_onboard.py`
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _sandbox():
    """빈 Gitea bare + 빈 레지스트리. [주의] `AX_PROJECTS_ROOT` 는 **호출 시점**에 읽히므로
    환경변수로 돌릴 수 있다(`GITEA_REPO_ROOT` 는 임포트 상수라 `bare_path` 를 명시한다)."""
    tmp = Path(tempfile.mkdtemp(prefix="ax-onboard-test-"))
    (tmp / "gitea" / "o" / "r.git").mkdir(parents=True)
    (tmp / "gitea" / "o" / "r.git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (tmp / "root").mkdir()
    (tmp / "root" / "projects.yaml").write_text('version: 1\nactive: ""\nprojects: []\n',
                                                encoding="utf-8")
    return tmp


def test_step_source_is_spec() -> None:
    """[중요] 단계 목록을 `onboard.py` 가 **다시 적지 않는다** — 선언은 `spec.SERVER_STEPS` 다."""
    from master.client import spec
    from master.projects import onboard

    check("판정기가 선언의 모든 단계를 덮는다",
          set(onboard.PROBES) == {s.key for s in spec.SERVER_STEPS},
          f"{set(onboard.PROBES)} vs {[s.key for s in spec.SERVER_STEPS]}")

    src = (Path(__file__).resolve().parent / "projects" / "onboard.py").read_text(
        encoding="utf-8")
    # 단계 순서를 여기 리터럴로 다시 적으면 두 벌이 된다
    check("순서를 다시 적지 않는다 (spec 을 돈다)", "for step in spec.SERVER_STEPS" in src)


def test_uninitialized() -> None:
    """등록조차 안 된 프로젝트 → 여섯 단계 전부 남았다고 **이름으로** 답한다."""
    from master.projects.onboard import plan
    tmp = _sandbox()
    keep = os.environ.get("AX_PROJECTS_ROOT")
    try:
        os.environ["AX_PROJECTS_ROOT"] = str(tmp / "root")
        d = plan("없는것", hosts=False).to_dict()
        # [주의] 개수를 박지 않는다 — 단계가 늘면(2026-08-22 에 `hook` 이 늘었다) 칸이 조용히
        #    거짓이 된다. **사양에서 세는 것**이 옳다.
        from master.client import spec
        check("모든 단계가 남았다", len(d["remaining"]) == len(spec.SERVER_STEPS),
              f"{d['remaining']} vs {len(spec.SERVER_STEPS)}")
        check("이름으로 답한다", "bare" in d["remaining"] and "index" in d["remaining"])
        # [중요] 선결이 깨진 단계는 **판정을 시도하지 않는다** — "비었다" 와 "잴 수 없다" 는 다르다
        blocked = [s for s in d["steps"] if s.get("blocked")]
        check("[중요] 선결 미충족은 blocked 로 갈린다", len(blocked) == 4, str(len(blocked)))
        check("[주의] hook 은 blocked 가 아니다 — 레지스트리만 있으면 잴 수 있다",
              not next(s for s in d["steps"] if s["step"] == "hook").get("blocked"))
        check("blocked 가 사유를 말한다", all("아직이다" in s["blocked"] for s in blocked))
        check("판정 실패가 아니라 계획이다 (ok=True)", d["ok"], str(d))
    finally:
        if keep is None:
            os.environ.pop("AX_PROJECTS_ROOT", None)
        else:
            os.environ["AX_PROJECTS_ROOT"] = keep


def test_registered_only() -> None:
    """등록만 된 프로젝트 → `bare`·`register` 만 참, 나머지 넷이 남는다."""
    from master.projects.logic import register_project
    from master.projects.onboard import plan
    tmp = _sandbox()
    keep = os.environ.get("AX_PROJECTS_ROOT")
    try:
        os.environ["AX_PROJECTS_ROOT"] = str(tmp / "root")
        register_project("Fresh", "o/r", bare_path=str(tmp / "gitea" / "o" / "r.git"))
        d = plan("Fresh", hosts=False).to_dict()
        by = {s["step"]: s for s in d["steps"]}
        check("bare 통과", by["bare"]["done"], str(by["bare"]))
        check("register 통과", by["register"]["done"], str(by["register"]))
        check("clone 은 남았다", not by["clone"]["done"] and "클론이 없다" in by["clone"]["detail"],
              str(by["clone"]))
        check("남은 것을 이름으로", d["remaining"] == ["hook", "clone", "graph", "synth", "index"],
              str(d["remaining"]))
        # [중요] clone 이 아직이면 그래프·합성·색인은 **잴 수 없다** (0건과 구분한다)
        check("[중요] clone 미완이 뒤 셋을 blocked 로 만든다",
              all(by[k].get("blocked") for k in ("graph", "synth", "index")),
              str({k: by[k].get("blocked") for k in ("graph", "synth", "index")}))

        # 빈 디렉토리를 통과시키지 않는다
        (tmp / "root" / "Fresh" / "repo").mkdir()
        by2 = {s["step"]: s for s in plan("Fresh", hosts=False).to_dict()["steps"]}
        check("[중요] 빈 디렉토리는 클론이 아니다",
              not by2["clone"]["done"] and "git 저장소가 아니다" in by2["clone"]["detail"],
              str(by2["clone"]))
    finally:
        if keep is None:
            os.environ.pop("AX_PROJECTS_ROOT", None)
        else:
            os.environ["AX_PROJECTS_ROOT"] = keep


def test_synth_stamps_commit() -> None:
    """[중요] **최초 합성도 `source_commit` 을 박는다** (사용자 지적 2026-08-22).

    처음엔 `do_synth` 가 `commit` 을 넘기지 않아 **신규 프로젝트의 문서 전부가 스탬프 없이**
    만들어졌다. `md.py:153` 이 *"`commit` 이 비면 그 줄이 안 붙는다"* 고 적어 뒀고, `md.py:19` 는
    그 값이 **중 1.3 stale 판정의 한쪽**이라고 못박았다. 훅 경로(`consumer._synthesize`)는
    넘기는데 온보딩 경로는 안 넘겼다 — **두 경로가 같은 계약이어야 한다.**
    """
    import inspect
    from master.projects import onboard

    src = inspect.getsource(onboard.do_synth)
    check("[중요] synth.run 에 commit 을 넘긴다", "commit=head.strip()" in src, src[-200:])
    check("HEAD 를 못 읽으면 합성하지 않는다", "HEAD 를 읽지 못해 합성하지 않는다" in src)
    # 훅 경로와 대조 — 두 곳이 같은 계약인지
    from master.events import consumer
    hook_src = inspect.getsource(consumer._synthesize)
    check("훅 경로도 commit 을 넘긴다 (대조군)", "commit=r.to_commit" in hook_src)

    # 넘기지 않으면 스탬프가 안 붙는다는 것 자체를 잰다 (md 계약 확인)
    # [주의] `finalize` 는 **형식 게이트를 통과한 문서**에만 스탬프를 찍는다 — 최소 문서로
    #    부르면 게이트에서 막혀 스탬프를 못 본다(내가 그렇게 짜서 칸이 빨갛게 됐다).
    #    그래서 `stamp()` 를 직접 잰다 — 이 계약이 요점이다.
    from master.context_synth import md as M
    doc = ("---\ntags: [x]\ncategory: a/b/c\nrelated_classes:\n  - UX: a.h\n---\n\n"
           "## 요약\nUX 는 무엇을 한다.\n\n## 개선 필요 사항\n없음\n")
    check("[중요] commit 을 주면 박힌다",
          "source_commit: abc1234" in M.stamp(doc, commit="abc1234"))
    check("[주의] 안 주면 안 박힌다 (그래서 넘겨야 한다)",
          "source_commit:" not in M.stamp(doc, commit=""))
    # 형식을 갖춘 문서로 finalize 왕복도 확인한다
    out, verdict = M.finalize(doc, existing="", commit="abc1234")
    check("finalize 도 같은 결과", verdict.ok and "source_commit: abc1234" in out,
          f"{verdict} {out[:80]}")


def test_live_modularstage() -> None:
    """[중요] **라이브 판정** — 이미 초기화된 실물에서 여섯 단계가 전부 참이어야 한다.

    이것이 판정기의 진짜 검증이다. 유닛 샌드박스는 우리가 만든 상태를 되읽는 것이라
    *"판정이 실물을 재는가"* 를 답하지 못한다(이 저장소가 반복해 물린 부류다).
    [주의] 마스터에서만 유효하다 — 트윈이 없으면 **건너뛰지 않고 사유를 찍는다**.
    """
    from master.projects.onboard import plan
    root = Path("/home/sim/ax-cluster")
    if not (root / "ModularStage" / "config.yaml").is_file():
        print("  [주의] ModularStage 트윈이 없다 — 라이브 판정을 건너뛴다 (마스터가 아니다)")
        return
    keep = os.environ.get("AX_PROJECTS_ROOT")
    try:
        os.environ["AX_PROJECTS_ROOT"] = str(root)
        d = plan("ModularStage", hosts=False).to_dict()
        check("[중요] 라이브: 남은 단계가 없다", d["remaining"] == [], str(d["remaining"]))
        by = {s["step"]: s for s in d["steps"]}
        check("근거가 실물이다 (그래프 건수)", "classes=" in by["graph"]["detail"],
              by["graph"]["detail"])
        # [중요] 재귀로 세지 않으면 0 이 나온다 — 실물은 하위 디렉토리에 있다
        check("[중요] synth 를 재귀로 센다 (context/*.md 는 0건이다)",
              by["synth"]["done"] and "MD " in by["synth"]["detail"], by["synth"]["detail"])
        check("index 가 워터마크를 근거로 든다", "@" in by["index"]["detail"],
              by["index"]["detail"])
    finally:
        if keep is None:
            os.environ.pop("AX_PROJECTS_ROOT", None)
        else:
            os.environ["AX_PROJECTS_ROOT"] = keep


if __name__ == "__main__":
    for fn in (test_step_source_is_spec, test_uninitialized, test_registered_only,
               test_synth_stamps_commit, test_live_modularstage):
        fn()
    print(f"{'OK' if not FAIL else 'FAIL'} test_onboard: {PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
