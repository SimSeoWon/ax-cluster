"""초기화 사양 (`#266`) — 선언 표 · 프로젝트 오버레이 · 폐지 청소 · `local_clone`.

칸을 **완료 조건마다** 하나씩 둔다(§12.6 — 「무엇이 없으면 미완인가」를 검사 하나로 옮긴다).

[중요] **여기서 지키는 첫 계약은 동작 불변**이다. 표를 옮긴 것뿐이라 `bundle` 의 값이 한 글자라도
달라지면 그것은 이 변경의 실패다 — `#262`·`#263` 이 같은 방식으로 검증됐다.

`python3 master/test_client_spec.py`
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.client import bundle, spec                              # noqa: E402
from master.context_search.paths import (                           # noqa: E402
    DEFAULT_CLONE_DIR, ProjectPaths, clone_dir_of,
)
from master.projects.config import ProjectConfig                    # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


# ── ① 표가 한 곳에 있다 (완료 조건 1) ────────────────────────────

def test_single_table() -> None:
    check("bundle 의 스킬 표가 spec 을 가리킨다",
          bundle.SKILLS_BY_ROLE is spec.SKILLS_BY_ROLE)

    # [중요] **값이 아니라 출처를 잰다.** 값만 대조하면 사본을 두고도 통과한다 — 그게
    #    지금 없애려는 상태다.
    src = (Path(__file__).resolve().parent / "client" / "bundle.py").read_text(encoding="utf-8")
    for lit in ('"ax-work"', '"ax-infer"', '"ax-request"', '"ax-ontology"'):
        # `SKILL_NAME = "ax-work"` 하나는 호환용 단수 참조로 남아 있다 — 그것까지 금지하면
        # 되돌릴 이유 없는 곳을 건드린다. 표 모양의 재정의만 잡는다.
        check(f"bundle 에 스킬 표가 다시 없다 {lit}",
              f"{lit}:" not in src and f'    {lit},' not in src, lit)

    check("마커도 spec 이 소유한다",
          bundle.MD_BEGIN == spec.md_block("ax").begin
          and bundle.WS_END == spec.md_block("workshop").end)
    check("MCP 이름도 spec 에서 온다",
          bundle.MCP_SERVER_NAME == spec.MCP_BY_ROLE["requester"][0])
    try:
        spec.md_block("없는키")
        check("[중요] 모르는 관리 구역은 예외", False, "통과해버렸다")
    except KeyError:
        check("모르는 관리 구역은 예외", True)


# ── ② 동작 불변 — 옮긴 것뿐이다 ──────────────────────────────────

def test_unchanged() -> None:
    # 이 값들은 **다른 기계의 파일 안에 이미 들어 있다.** 바뀌면 병합이 옛 블록을 못 찾고
    # 블록을 하나 더 붙인다(`.2` 에서 실제로 일어났다, 2026-08-09).
    check("AX 마커 글자 불변",
          bundle.MD_BEGIN == "<!-- AX:Begin — 마스터가 생성한다. 이 블록만 덮인다 -->"
          and bundle.MD_END == "<!-- AX:End -->", bundle.MD_BEGIN)
    check("작업장 마커 글자 불변",
          bundle.WS_BEGIN == "<!-- AgentWatch:Start -->"
          and bundle.WS_END == "<!-- AgentWatch:End -->", bundle.WS_BEGIN)
    check("작업장 MD 위치 불변", bundle.WORKSHOP_MD_REL == ".claude/CLAUDE.md",
          bundle.WORKSHOP_MD_REL)
    check("MCP 엔트리 이름 불변", bundle.MCP_SERVER_NAME == "ax-client",
          bundle.MCP_SERVER_NAME)
    check("워커 스킬 불변", bundle.skills_for("worker") == ("ax-work", "ax-infer"),
          str(bundle.skills_for("worker")))
    check("요청자 스킬 불변",
          bundle.skills_for("requester") == ("ax-request", "ax-ontology", "ax-review"),
          str(bundle.skills_for("requester")))
    check("오버레이 없음 == 종전",
          bundle.skills_for("requester") == bundle.skills_for("requester", spec.EMPTY_INIT))

    try:
        bundle.skills_for("보스")
        check("[중요] 모르는 role 은 예외 (조용한 빈 배달 금지)", False, "통과해버렸다")
    except bundle.BundleError:
        check("모르는 role 은 예외", True)


# ── ③ 프로젝트 축이 실제로 쓰인다 (완료 조건 2) ──────────────────

def test_project_overlay() -> None:
    init = spec.ProjectInit(domains=("전투", "UI"),
                            extra_skills={"requester": ("ax-extra",)})
    got = bundle.skills_for("requester", init)
    check("선언한 추가 스킬이 실린다", got[-1] == "ax-extra", str(got))
    check("기본 표가 앞에 남는다", got[:3] == ("ax-request", "ax-ontology", "ax-review"), str(got))
    check("[중요] 다른 역할은 영향 없다", bundle.skills_for("worker", init)
          == ("ax-work", "ax-infer"), str(bundle.skills_for("worker", init)))

    # 리스트로 주면 모든 역할 — 원전 표의 「무조건 등록」과 같은 결
    flat = spec.ProjectInit(extra_skills=spec._by_role(["ax-all"], "extra_skills"))
    check("리스트는 모든 역할에 적용",
          "ax-all" in bundle.skills_for("worker", flat)
          and "ax-all" in bundle.skills_for("requester", flat))

    check("중복은 접힌다",
          bundle.skills_for("worker", spec.ProjectInit(
              extra_skills={"worker": ("ax-work",)})) == ("ax-work", "ax-infer"))


def test_overlay_from_config() -> None:
    """`config.yaml` → `ProjectInit`. [중요] **왕복이 사는지**가 이 절의 핵심이다."""
    tmp = Path(tempfile.mkdtemp(prefix="ax-spec-test-"))
    cfg_path = tmp / "config.yaml"
    cfg_path.write_text(
        "version: 1\nname: T\ntrack:\n  project_id: o/r\n  local_clone: mirror\n"
        "init:\n  domains: [전투, UI]\n  convention_sections: [Code conventions, Naming]\n"
        "  extra_skills:\n    requester: [ax-extra]\n",
        encoding="utf-8")
    cfg = ProjectConfig.load(cfg_path)
    init = spec.ProjectInit.from_config(cfg)
    check("도메인을 읽는다", init.domains == ("전투", "UI"), str(init.domains))
    check("컨벤션 절을 읽는다",
          init.convention_sections == ("Code conventions", "Naming"),
          str(init.convention_sections))
    check("역할별 추가 스킬을 읽는다", init.extra_skills == {"requester": ("ax-extra",)},
          str(init.extra_skills))

    # [중요] **왕복** — `to_yaml()` 이 `dict(self.raw)` 로 시작하므로 `init:` 이 살아남아야
    #    한다. 이것이 사양을 별도 파일로 두지 않은 근거다(§12.5-g ③). 죽으면 근거가 죽는다.
    cfg.last_indexed_commit = "abc123"
    cfg_path.write_text(cfg.to_yaml(), encoding="utf-8")
    again = spec.ProjectInit.from_config(ProjectConfig.load(cfg_path))
    check("[중요] 왕복해도 init: 이 산다", again == init, str(again))
    check("왕복 후 local_clone 도 산다",
          ProjectConfig.load(cfg_path).local_clone == "mirror")

    # 선언이 없으면 기본값 — 사양을 안 쓴 프로젝트도 돈다
    plain = tmp / "plain.yaml"
    plain.write_text("version: 1\nname: P\n", encoding="utf-8")
    check("선언 없으면 기본값",
          spec.ProjectInit.from_config(ProjectConfig.load(plain)) == spec.EMPTY_INIT)


def test_overlay_rejects_garbage() -> None:
    """[중요] **조용히 무시하지 않는다** — 오타 난 키를 무시하면 사용자는 등재된 줄 안다."""
    class Fake:
        def __init__(self, raw):
            self.raw = raw

    for bad, label in (({"init": ["a"]}, "init: 이 리스트"),
                       ({"init": {"extra_skills": {"보스": ["x"]}}}, "모르는 역할"),
                       ({"init": {"extra_mcp": 3}}, "extra_mcp 가 스칼라")):
        try:
            spec.ProjectInit.from_config(Fake(bad))
            check(f"[중요] {label} → 거부", False, "통과해버렸다")
        except ValueError:
            check(f"{label} → 거부", True)


# ── ④ 폐지분이 청소 대상으로 나온다 (완료 조건 3) ────────────────

def test_removals() -> None:
    rm = spec.removals_for("requester")
    check("폐지 스킬이 제거 목록에 있다",
          set(rm["skills"]) == {"distribute", "review-work"}, str(rm["skills"]))
    check("[주의] 폐지 MCP 목록은 비어 있다 (귀속 미결 #235)", rm["mcp"] == (), str(rm["mcp"]))

    # [중요] 배달과 제거가 같은 이름을 두고 싸우지 않는다 — 배달이 이긴다
    revived = spec.ProjectInit(extra_skills={"requester": ("distribute",)})
    rm2 = spec.removals_for("requester", revived)
    check("[중요] 되살린 이름은 제거하지 않는다", "distribute" not in rm2["skills"],
          str(rm2["skills"]))
    check("되살린 이름은 배달된다", "distribute" in bundle.skills_for("requester", revived))

    # 폐지 이름이 현행 표에 남아 있으면 배달·제거가 동시에 걸린다 — 그건 표의 버그다
    for role, names in spec.SKILLS_BY_ROLE.items():
        check(f"현행 표({role})와 폐지 목록이 겹치지 않는다",
              not (set(names) & set(spec.DEPRECATED_SKILLS)),
              str(set(names) & set(spec.DEPRECATED_SKILLS)))


# ── ⑤ MCP 는 역할로 갈린다 (#261 을 보이게) ──────────────────────

def test_mcp_roles() -> None:
    check("요청자는 ax-client 를 받는다", spec.mcp_for("requester") == ("ax-client",))
    check("[중요] 워커는 못 받는다 — 그 판단이 표에 보인다", spec.mcp_for("worker") == ())
    check("프로젝트가 추가할 수 있다",
          spec.mcp_for("worker", spec.ProjectInit(extra_mcp={"worker": ("unreal-mcp",)}))
          == ("unreal-mcp",))


# ── ⑥ 관리 구역은 역할로 갈린다 ──────────────────────────────────

def test_md_blocks() -> None:
    check("워커는 AX 블록만", tuple(b.key for b in spec.md_blocks_for("worker")) == ("ax",))
    check("요청자는 둘 다",
          tuple(b.key for b in spec.md_blocks_for("requester")) == ("ax", "workshop"))
    # 배달되는 작업장 자산이 요청자 전용인 것과 같은 축이어야 한다
    check("작업장 역할과 어긋나지 않는다",
          ("workshop" in [b.key for b in spec.md_blocks_for("requester")])
          == ("requester" in bundle.WORKSHOP_ROLES))


# ── ⑦ 서버 절 (완료 조건은 #259 가 갖는다. 여기서는 선언의 온전함만) ──

def test_server_steps() -> None:
    keys = [s.key for s in spec.SERVER_STEPS]
    check("단계 이름이 중복되지 않는다", len(keys) == len(set(keys)), str(keys))
    check("클론이 그래프·합성보다 앞이다",
          keys.index("clone") < keys.index("graph") < keys.index("synth"), str(keys))
    check("색인이 마지막이다", keys[-1] == "index", str(keys))
    check("모든 단계가 판정 문구를 갖는다", all(s.probe for s in spec.SERVER_STEPS))
    # [중요] 마운트는 이 표에 없어야 한다 — 되묻기 계약(§12.5-b)이 깨진다
    check("[중요] 마운트 단계가 없다",
          not any("마운트" in s.what or s.key in ("mount", "activate")
                  for s in spec.SERVER_STEPS))


# ── ⑥-b 선언 검증 — 없는 스킬은 사유로 거부 ─────────────────────

def test_validate_spec() -> None:
    """[중요] 실측이 만든 칸 (2026-08-22 라이브 `plan`).

    없는 스킬을 선언하니 `plan` 이 **생 트레이스백으로 죽고** 뒤 호스트(`.43`)는 계획조차
    나오지 않았다. 사유를 말해야 하는 자리다.
    """
    check("현행 선언은 온전하다", bundle.validate_spec() == (),
          str(bundle.validate_spec()))
    bad = bundle.validate_spec(spec.ProjectInit(extra_skills={"requester": ("없는스킬",)}))
    check("없는 스킬을 잡는다", len(bad) == 1, str(bad))
    check("[중요] 이름으로 답한다", bad and "없는스킬" in bad[0], str(bad))
    check("역할도 말한다", bad and "requester" in bad[0], str(bad))
    # 모든 역할의 선언을 훑는다 — 워커 쪽 오타가 요청자 배달에서만 터지면 늦다
    bad2 = bundle.validate_spec(spec.ProjectInit(extra_skills={"worker": ("없는것",)}))
    check("워커 선언도 훑는다", len(bad2) == 1 and "worker" in bad2[0], str(bad2))


# ── ⑥-c `init` 과 `project_init` 은 다른 것이다 (실측 회귀) ────────

def test_init_flag_not_shadowed() -> None:
    """[중요] **이 세션이 넣었다가 잡은 결함이다.**

    사양 오버레이를 `init` 이라는 지역변수에 담아 `deliver` 의 `init: bool`(= `--init`,
    원격 클로드 `/init` 플래그)을 **가렸다.** `ProjectInit` 인스턴스는 항상 참이라
    `--init` 없이도 `/init` 이 도는 상태가 된다 — 실측 $1.68 짜리 호출이다.
    """
    import inspect
    sig = inspect.signature(bundle.deliver)
    check("두 인자가 따로 있다",
          "init" in sig.parameters and "project_init" in sig.parameters, str(sig))
    check("init 은 여전히 bool 기본 False", sig.parameters["init"].default is False)
    check("project_init 기본은 None (주면 레지스트리를 안 읽는다)",
          sig.parameters["project_init"].default is None)

    src = (Path(__file__).resolve().parent / "client" / "bundle.py").read_text(encoding="utf-8")
    body = src[src.index("            init: bool = False, project_init=None) -> dict:"):]
    body = body[:body.index("\ndef ", 1)]
    check("[중요] deliver 안에서 init 에 재대입하지 않는다",
          "\n    init = " not in body, "가림 재발")
    check("/init 게이트가 여전히 플래그를 본다", "if init and not (prev or" in body)


# ── ⑦-b load_init — 환경 오류와 부재를 가른다 ────────────────────

def test_load_init_env() -> None:
    """[중요] 실측이 만든 칸이다 (2026-08-22 라이브 `plan`).

    `AX_PROJECTS_ROOT` 미설정이 *"도메인: (선언 없음)"* 으로 보고됐다 — **환경이 깨진 것을
    「선언 안 함」으로 번역**한 것이다. 부재는 접고 환경 오류는 터뜨린다.
    """
    import os
    from master.projects.config import ConfigError
    keep = os.environ.get("AX_PROJECTS_ROOT")
    try:
        os.environ.pop("AX_PROJECTS_ROOT", None)
        try:
            spec.load_init("아무개")
            check("[중요] 루트 미설정은 예외 — 기본값으로 접지 않는다", False, "통과해버렸다")
        except ConfigError:
            check("루트 미설정은 예외", True)

        os.environ["AX_PROJECTS_ROOT"] = tempfile.mkdtemp(prefix="ax-root-test-")
        check("미등록 프로젝트는 기본값 (부재는 접는다)",
              spec.load_init("없는프로젝트") == spec.EMPTY_INIT)
    finally:
        if keep is None:
            os.environ.pop("AX_PROJECTS_ROOT", None)
        else:
            os.environ["AX_PROJECTS_ROOT"] = keep


# ── ⑧ local_clone 하드코딩 제거 (완료 조건 5) ────────────────────

def test_clone_dir() -> None:
    src = (Path(__file__).resolve().parent / "context_search" / "paths.py").read_text(
        encoding="utf-8")
    check('[중요] paths.py 에 `root / "repo"` 리터럴이 없다',
          'self.root / "repo"' not in src)

    p = ProjectPaths(name="T", root=Path("/tmp/t"))
    check("기본값은 종전과 같다 (repo)", p.repo == Path("/tmp/t/repo"), str(p.repo))
    check("source 도 따라간다", p.source == Path("/tmp/t/repo/Source"), str(p.source))

    q = ProjectPaths(name="T", root=Path("/tmp/t"), clone_dir="mirror")
    check("선언하면 그 디렉토리를 본다", q.repo == Path("/tmp/t/mirror"), str(q.repo))
    check("빈 값은 기본값으로 접힌다",
          ProjectPaths(name="T", root=Path("/tmp/t"), clone_dir="").repo
          == Path("/tmp/t/repo"))

    tmp = Path(tempfile.mkdtemp(prefix="ax-clone-test-"))
    check("config.yaml 이 없으면 기본값", clone_dir_of(tmp) == DEFAULT_CLONE_DIR)
    (tmp / "config.yaml").write_text(
        "version: 1\nname: T\ntrack:\n  local_clone: mirror\n", encoding="utf-8")
    check("config.yaml 의 값을 읽는다", clone_dir_of(tmp) == "mirror", clone_dir_of(tmp))

    # [주의] **깨진 설정은 시끄럽게** — 조용히 기본값으로 접히면 남의 디렉토리를 색인한다
    (tmp / "config.yaml").write_text("track:\n  local_clone: [\n", encoding="utf-8")
    try:
        clone_dir_of(tmp)
        check("[중요] 깨진 config.yaml 은 예외", False, "통과해버렸다")
    except Exception:                                   # noqa: BLE001 — 종류가 아니라 시끄러움
        check("깨진 config.yaml 은 예외", True)


if __name__ == "__main__":
    for fn in (test_single_table, test_unchanged, test_project_overlay,
               test_overlay_from_config, test_overlay_rejects_garbage, test_removals,
               test_mcp_roles, test_md_blocks, test_validate_spec,
               test_init_flag_not_shadowed, test_server_steps,
               test_load_init_env,
               test_clone_dir):
        fn()
    # [중요] 형식 A(`N/M 통과`)로 찍는다 — 러너가 읽는 두 형식 중 하나여야 합계에
    #    들어간다. 안 맞으면 "수치 못 읽음"으로 **조용히 분모에서 빠진다**.
    print(f"{'OK' if not FAIL else 'FAIL'} test_client_spec: {PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
