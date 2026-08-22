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


# ── ⑥-d 커밋 제외 대상 (사용자 지적 2026-08-22) ──────────────────

def test_git_excludes() -> None:
    """[중요] **마스터가 체크아웃 안에 쓰는 것은 전부 제외돼야 한다.**

    실측이 이 칸을 만들었다: 종전 목록은 `/.ax/`·`/.mcp.json` 두 줄뿐인데 `.33` 은 안
    더러웠다 — 이유는 **ModularStage `.gitignore` 자신의 세 줄**(`:36 .claude/` ·
    `:40 /.mcp.json` · `:41 /CLAUDE.md`)이었다. 그건 그 프로젝트의 파일이고 새 프로젝트엔
    없다. 즉 종전 목록은 「지금 안 터지는」 것이었을 뿐이다.
    """
    w = spec.git_excludes_for("worker")
    r = spec.git_excludes_for("requester")
    check("부산물 디렉토리", "/.ax/" in w and "/.ax/" in r)
    check("[중요] CLAUDE.md — 모든 역할이 관리 블록을 받는다", "/CLAUDE.md" in w)
    check("[중요] 작업장 자산은 요청자 전용",
          "/.claude/" in r and "/.claude/" not in w, f"{w} / {r}")
    check("전부 저장소 루트 고정(`/` 시작)", all(x.startswith("/") for x in w + r), str(w + r))

    # [중요] **배달하는 것과 제외하는 것이 어긋나면 워킹트리가 더러워진다.** 배달 위치를
    #    제외 목록이 덮는지 잰다 — 이 대조가 없으면 다음에 배달물을 늘릴 때 조용히 깨진다.
    for role in ("worker", "requester"):
        exc = spec.git_excludes_for(role)
        targets = [bundle.CONFIG_REL, "CLAUDE.md"]
        if role == "requester":
            targets += [bundle.WORKSHOP_MD_REL, ".mcp.json"]
        for rel in targets:
            covered = any(rel == e.lstrip("/") or rel.startswith(e.lstrip("/"))
                          for e in exc)
            check(f"[{role}] 배달물이 제외에 덮인다: {rel}", covered, f"{rel} ∉ {exc}")

    # 추적 중인 파일은 exclude 로 막을 수 없다 — 그 목록이 선언돼 있다
    check("ambient 목록이 있다", "CLAUDE.md" in spec.AMBIENT_MANAGED
          and ".mcp.json" in spec.AMBIENT_MANAGED)
    check("[주의] 우리가 고치지 않는다 — 보고 함수만 있다",
          callable(getattr(bundle, "tracked_managed", None)))


# ── ⑥-d2 .gitignore 관리 블록 — 산출물 오염을 막는 쪽 ────────────

def test_gitignore_block() -> None:
    """사용자 2026-08-22: *"클로드가 실제 작업 결과물에 포함되는게 문제인거지"*.

    [중요] `info/exclude` 는 **클론 로컬**이라 그 기계에만 듣는다 — 팀원이 새로 클론하면
    없다. 커밋되는 `.gitignore` 만 저장소 전체에 듣는다. 원전도 그래서 `.gitignore` 에 마커
    블록을 썼다(ModularStage `.gitignore:30-42` 가 그 결과물이다).
    """
    blk = spec.gitignore_block()
    for line in ("/.ax/", "/.mcp.json", "/CLAUDE.md", ".claude/"):
        check(f"블록이 {line} 를 든다", line in blk, blk)
    check("마커로 감싸였다",
          blk.startswith(spec.GITIGNORE_BEGIN) and blk.endswith(spec.GITIGNORE_END))
    # [중요] 배달물 전부가 블록에 덮여야 한다 — 어긋나면 산출물에 섞인다
    for rel in (bundle.CONFIG_REL, "CLAUDE.md", ".mcp.json", bundle.WORKSHOP_MD_REL):
        top = rel.split("/")[0]
        check(f"배달물이 .gitignore 블록에 덮인다: {rel}",
              f"/{top}" in blk or f"{top}/" in blk or f"/{rel}" in blk, rel)

    # 병합 규약 — merge_claude_md 와 같다
    once = bundle.merge_gitignore("*.tmp\n")
    check("사람이 쓴 줄을 보존한다", "*.tmp" in once)
    check("[중요] 멱등 — 두 번 병합이 같다", bundle.merge_gitignore(once) == once)
    check("블록이 하나만 남는다", once.count(spec.GITIGNORE_BEGIN) == 1)

    dup = bundle.merge_gitignore(once + "\n" + spec.gitignore_block() + "\n")
    check("여러 개면 걷어내고 하나만", dup.count(spec.GITIGNORE_BEGIN) == 1,
          str(dup.count(spec.GITIGNORE_BEGIN)))

    # [주의] 원전 블록은 우리 것이 아니다 — 건드리지 않는다
    orig = "# AgentWatch:Start\n/watch.exe\n/.watch_state\n# AgentWatch:End\n"
    m = bundle.merge_gitignore(orig)
    check("[주의] 원전 AgentWatch 블록을 보존한다",
          "# AgentWatch:Start" in m and "/watch.exe" in m, m)
    check("우리 블록도 함께 있다", spec.GITIGNORE_BEGIN in m)
    check("마커가 겹치지 않는다", spec.GITIGNORE_BEGIN != "# AgentWatch:Start")

    # [중요] **계획이 배달하지 않는 것을 배달한다고 찍으면 안 된다** (실측 2026-08-22:
    #    `plan` 이 `.gitignore` 블록을 `→` 로 찍는데 `deliver` 는 그것을 하지 않았다).
    cli = (Path(__file__).resolve().parent / "client" / "__main__.py").read_text(encoding="utf-8")
    dlv = (Path(__file__).resolve().parent / "client" / "bundle.py").read_text(encoding="utf-8")
    writes = "merge_gitignore" in dlv.split("def deliver(")[1].split("\ndef ")[0]
    line = [l for l in cli.splitlines() if ".gitignore 의" in l]
    check("plan 에 .gitignore 줄이 있다", bool(line), str(line))
    if line and not writes:
        check("[중요] 안 쓰면 배달 기호(→)로 찍지 않는다",
              "→" not in line[0] and "쓰지 않는다" in cli, line[0].strip())


# ── ⑥-e 등록이 기본 설정을 **저장**한다 ─────────────────────────

def test_register_seeds_defaults() -> None:
    """사용자 2026-08-22: *"마스터가 설치해주려고 규격을 정하고 디폴트 설정을 저장하는거잖아"*.

    [중요] 관례가 이미 있었다 — `register_project` 는 `include`/`exclude` 를 새 `config.yaml` 에
    적는다. 사양의 기본값도 같은 자리에 적어야 **사람이 보고 고칠 수 있다.**
    """
    import os
    from master.projects.config import ProjectConfig
    from master.projects.logic import register_project

    tmp = Path(tempfile.mkdtemp(prefix="ax-reg-test-"))
    (tmp / "gitea" / "o" / "r.git").mkdir(parents=True)
    (tmp / "gitea" / "o" / "r.git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (tmp / "root").mkdir()
    (tmp / "root" / "projects.yaml").write_text('version: 1\nactive: ""\nprojects: []\n',
                                                encoding="utf-8")
    keep = (os.environ.get("AX_GITEA_REPO_ROOT"), os.environ.get("AX_PROJECTS_ROOT"))
    try:
        os.environ["AX_GITEA_REPO_ROOT"] = str(tmp / "gitea")
        os.environ["AX_PROJECTS_ROOT"] = str(tmp / "root")
        # [주의] `GITEA_REPO_ROOT` 는 **임포트 시점 상수**라 환경변수를 늦게 넣어도 안 듣는다
        #    (test_projects.py 는 임포트 전에 넣는다). 여기서는 bare_path 를 명시해 우회한다.
        r = register_project("Seeded", "o/r",
                             bare_path=str(tmp / "gitea" / "o" / "r.git"))
        text = Path(r["config"]).read_text(encoding="utf-8")
        check("등록이 init: 을 적는다", "init:" in text, text[:120])
        check("컨벤션 절 기본값이 보인다", "Code conventions" in text)
        # [중요] 순서가 내용이다 — `dict(self.raw)` 로 시작하므로 자리를 정하지 않으면
        #    `init:` 이 `version:` 보다 앞에 찍힌다(실측).
        check("[중요] init: 은 engine: 뒤다",
              text.index("engine:") < text.index("init:"), "순서 뒤집힘")
        check("version: 이 맨 앞이다", text.lstrip().startswith("version:"), text[:40])
        cfg = ProjectConfig.load(Path(r["config"]))
        check("적힌 값이 기본값과 같다 (동작 불변)",
              spec.ProjectInit.from_config(cfg) == spec.EMPTY_INIT,
              str(spec.ProjectInit.from_config(cfg)))
    finally:
        for k, v in zip(("AX_GITEA_REPO_ROOT", "AX_PROJECTS_ROOT"), keep):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ── ⑥-f 컨텍스트 문서 생성은 Source/ 한정 (사용자 재확인 2026-08-22) ──

def test_synth_source_only() -> None:
    """[중요] 경계가 **호출 방식에 딸려 다니지 않게** 한다 (§5.2-E).

    `list_source_files` 는 pathspec + 접두 검사로 두 겹인데, `synth.run(changed=...)` 경로에는
    검사가 **없었다** — 호출자가 한 번 잘못 넘기면 `Content/`(워킹트리의 93%, uasset 바이너리)가
    그대로 합성 대상이 됐다. [주의] 조용히 걸러내지 않고 **거부한다** — 걸러내면 호출자는
    그것도 합성된 줄 안다.
    """
    from master.context_search.paths import SOURCE_SUBDIR
    from master.context_synth import synth

    check("경계 이름이 하나다", SOURCE_SUBDIR == "Source", SOURCE_SUBDIR)
    check("사양의 synth 단계가 경계를 적는다",
          any(s.key == "synth" and "Source/" in s.what for s in spec.SERVER_STEPS))

    src = (Path(__file__).resolve().parent / "context_synth" / "synth.py").read_text(
        encoding="utf-8")
    check("synth 가 SOURCE_SUBDIR 로 검사한다", "SOURCE_SUBDIR}/" in src)

    tmp = Path(tempfile.mkdtemp(prefix="ax-synth-scope-"))
    (tmp / "repo" / "Source").mkdir(parents=True)
    (tmp / "repo" / "Source" / "A.cpp").write_text("int a;\n", encoding="utf-8")
    (tmp / "repo" / "Content").mkdir()
    (tmp / "repo" / "Content" / "B.uasset").write_bytes(b"\x00")
    from master.context_search.paths import ProjectPaths
    paths = ProjectPaths(name="T", root=tmp)

    for bad, label in ((["Content/B.uasset"], "Content/ 단독"),
                       (["Source/A.cpp", "Content/B.uasset"], "섞여 들어옴"),
                       (["../../etc/passwd"], "경로 탈출")):
        try:
            synth.run(paths, changed=bad, dry_run=True)
            check(f"[중요] {label} → 거부", False, "통과해버렸다")
        except synth.SynthError as e:
            check(f"{label} → 거부", "Source/" in str(e), str(e)[:80])

    # 정상 경로는 그대로 돈다 (경계가 기능을 막지 않는다)
    s = synth.run(paths, changed=["Source/A.cpp"], dry_run=True)
    check("Source/ 안은 통과한다", s.groups == 1, str(s.groups))
    # 윈도우 diff 출력(백슬래시)도 같은 판정을 받는다
    s2 = synth.run(paths, changed=["Source\\A.cpp"], dry_run=True)
    check("백슬래시도 정규화 후 통과", s2.groups == 1, str(s2.groups))


# ── ⑥-g 기계↔마스터 커밋 대조 (사용자 2026-08-22) ────────────────

def _fake_facts(windows: bool = False, checkout_ok: bool = True):
    # [주의] `checkout_ok` 기본이 False 라 명시하지 않으면 `sync_check` 가 검사기를 **타지 않고**
    #    「체크아웃 없음」으로 빠진다 — 그래서 칸이 우연히 통과했다(실측 2026-08-22).
    return bundle.HostFacts(host="h", user="u", path="/p", driven="ssh", role="worker",
                            os="windows" if windows else "linux", checkout_ok=checkout_ok,
                            commit="abc1234")


def test_delivered_stamp() -> None:
    """`.ax/config.json` 의 `delivered_by` 를 읽는다. [주의] 「없음」과 「못 읽음」을 가른다."""
    keep = bundle._remote_read
    try:
        bundle._remote_read = lambda f, path: '{"delivered_by": {"commit": "abc", "dirty": false}}'
        check("스탬프를 읽는다", bundle.delivered_stamp(_fake_facts())["commit"] == "abc")

        bundle._remote_read = lambda f, path: '{"other": 1}'
        check("delivered_by 부재를 사유로 말한다",
              "delivered_by" in bundle.delivered_stamp(_fake_facts()).get("error", ""))

        bundle._remote_read = lambda f, path: "{not json"
        check("파싱 실패를 사유로 말한다",
              "JSON" in bundle.delivered_stamp(_fake_facts()).get("error", ""))

        bundle._remote_read = lambda f, path: ""
        check("[중요] 빈 응답을 빈 dict 로 접지 않는다",
              "읽지 못했다" in bundle.delivered_stamp(_fake_facts()).get("error", ""))
    finally:
        bundle._remote_read = keep


def test_compare_version() -> None:
    """[중요] 판정은 `version.compare` 가 한다 — `same` 만 통과다.

    처음에 「뒤처짐은 실패가 아니다」로 짰고 사용자가 정정했다(2026-08-22): *"작업 저장소를
    가리키는 것과 관리 마스터는 하나의 버전 관리만 쓰잖아 … 마스터쪽 통신 규칙이 바뀌었는데 …
    서로 안맞춘다고?"*. 클러스터는 **버전이 하나**다. 그리고 저장소에 이미 그 판정이 있었는데
    (`version.compare`, 호출자 0) 그 독스트링이 *"`same` 으로 접으면 있는 드리프트를 놓친다"*
    라고 못박아 뒀다 — 내가 정확히 그것을 했다.
    """
    keep_read, keep_run = bundle._remote_read, bundle._run_local
    try:
        bundle._run_local = lambda *a: ("HEADHASH" if a[0] == "rev-parse" else "21")

        def stamp(commit, dirty=False):
            import json as _j
            bundle._remote_read = lambda f, p: _j.dumps(
                {"delivered_by": {"commit": commit, "dirty": dirty}})

        stamp("HEADHASH")
        v = bundle.compare_version(_fake_facts(), head="HEADHASH")
        check("HEAD 와 같으면 behind 0", v["ok"] and v["behind"] == 0, str(v))

        stamp("OLD")
        v = bundle.compare_version(_fake_facts(), head="HEADHASH", runner=lambda c, h: True)
        check("[중요] 뒤처지면 실패다 (버전이 하나다)", not v["ok"], str(v))
        check("drifted 로 판정한다", v["verdict"] == "drifted", str(v))
        check("얼마나 뒤인지 말한다", v["behind"] == 21, str(v))
        check("맞춰야 한다고 말한다", "재배달" in v["reason"], v["reason"])

        stamp("OLD", dirty=True)
        v = bundle.compare_version(_fake_facts(), head="HEADHASH", runner=lambda c, h: True)
        check("[중요] dirty 배달을 감추지 않는다",
              v["stamp_dirty"] and "dirty" in v["reason"], str(v))

        stamp("HEADHASH", dirty=True)
        v = bundle.compare_version(_fake_facts(), head="HEADHASH")
        check("[중요] 커밋이 같아도 dirty 면 통과가 아니다 — 추적 불가다",
              not v["ok"] and v["verdict"] == "same", str(v))

        stamp("SIDE")
        v = bundle.compare_version(_fake_facts(), head="HEADHASH", runner=lambda c, h: False)
        check("[중요] 조상이 아니면 실패", not v["ok"] and "조상이 아니다" in v["reason"], str(v))

        v = bundle.compare_version(_fake_facts(), head="HEADHASH", runner=lambda c, h: None)
        check("[중요] 판정 불가를 거짓으로 접지 않는다",
              not v["ok"] and "커밋이 아니다" in v["reason"], str(v))

        stamp("")
        v = bundle.compare_version(_fake_facts(), head="HEADHASH", runner=lambda c, h: True)
        check("[중요] 커밋을 모르면 unknown — 같다고도 다르다고도 않는다",
              not v["ok"] and v["verdict"] == "unknown", str(v))

        # 계약 버전(도구 표면)이 다르면 별도로 시끄럽게 — 커밋 거리와 다른 축이다
        import json as _j
        bundle._remote_read = lambda f, p: _j.dumps(
            {"delivered_by": {"commit": "OLD", "dirty": False, "contract": 99}})
        v = bundle.compare_version(_fake_facts(), head="HEADHASH", runner=lambda c, h: True)
        check("[중요] 계약 버전 차이를 별도로 말한다",
              "계약 버전이 다르다" in v["reason"], v["reason"])

        bundle._remote_read = lambda f, p: ""
        v = bundle.compare_version(_fake_facts(), head="HEADHASH")
        check("못 읽으면 실패", not v["ok"], str(v))
    finally:
        bundle._remote_read, bundle._run_local = keep_read, keep_run


def test_config_documents_comparison() -> None:
    """사용자 2026-08-22: *"config 파일 문서에 명기하면 이것만 비교하면 되는거잖아"*.

    [중요] 파일만 보고도 **무엇을 비교하면 되는지** 알아야 한다.
    """
    src = (Path(__file__).resolve().parent / "client" / "bundle.py").read_text(encoding="utf-8")
    check("config 에 _compare 필드가 있다", '"_compare"' in src)
    check("그 문구가 delivered_by.commit 을 가리킨다",
          "delivered_by.commit` 을 마스터" in src)
    check("dirty 의 뜻도 적었다", "delivered_by.dirty=true" in src)


# ── ⑥-h 전환이 동기화 지점이다 (사용자 2026-08-22) ────────────────

def test_switch_syncs() -> None:
    """*"마운트 하지 않은 프로젝트를 불필요하게 동기화 할 필요는 없지만 마운트 대상을 바꿀때
    체크 한번 해서 맞추면 되는거잖아."*

    [중요] 경계가 둘이다 — ① 마운트가 **실제로 바뀔 때만** 본다(같은 프로젝트 재지정에 SSH 를
    태우지 않는다) ② 미마운트 프로젝트를 순회하지 않는다.
    """
    from master.projects import logic as L

    calls = []

    def fake_sync():
        calls.append(1)
        return {"checked": True, "drifted": ["h1"], "commands": ["deliver X"]}

    reg = type("R", (), {})()
    reg.names = ["A", "B"]
    reg.active = "A"
    reg.save = lambda: None
    reg.config_of = lambda n: type("C", (), {"project_id": "o/r", "branch": "main",
                                             "last_indexed_commit": "abc"})()
    keep_check = L._check_one
    keep_open = L.open_works_in_queue
    try:
        L._check_one = lambda r, n: []
        L.open_works_in_queue = lambda fetcher=None: []

        out = L.set_active("B", registry=reg, sync_fn=fake_sync)
        check("[중요] 전환하면 동기 확인이 돈다", len(calls) == 1 and "sync" in out, str(out))
        check("어긋난 기계를 이름으로 낸다", out["sync"]["drifted"] == ["h1"], str(out["sync"]))

        reg.active = "B"
        calls.clear()
        out2 = L.set_active("B", registry=reg, sync_fn=fake_sync)
        check("[중요] 같은 프로젝트 재지정에는 안 돈다 (불필요한 동기 금지)",
              not calls and "sync" not in out2, str(out2))

        reg.active = "A"
        calls.clear()
        out3 = L.set_active("B", registry=reg, sync=False, sync_fn=fake_sync)
        check("sync=False 로 끌 수 있다", not calls and "sync" not in out3)

        # [주의] 동기 확인이 죽어도 전환을 되돌리지 않는다 — 전환은 이미 됐다
        reg.active = "A"

        def boom():
            raise RuntimeError("ssh 죽음")
        out4 = L.set_active("B", registry=reg, sync_fn=boom)
        check("[주의] 동기 실패가 전환을 되돌리지 않는다",
              out4["ok"] and out4["active"] == "B", str(out4))
        check("실패 사유를 싣는다", "ssh 죽음" in out4["sync"]["reason"], str(out4["sync"]))
    finally:
        L._check_one, L.open_works_in_queue = keep_check, keep_open


def test_sync_check_shape() -> None:
    """`sync_check` — 기본은 **보고**, `align=True` 가 맞춘다 (`finalize_work` 관례)."""
    from master.projects import logic as L

    facts = _fake_facts()
    delivered = []

    import master.client.bundle as B
    keep_ws, keep_probe = B.workshops, B.probe
    try:
        B.workshops = lambda n: [("h1", "u", "/p", "ssh", "worker")]
        B.probe = lambda *a: facts

        drift = lambda f: {"ok": False, "verdict": "drifted", "behind": 3, "reason": "3 뒤"}
        out = L.sync_check("X", checker=drift)
        check("검사기를 실제로 탔다", out["hosts"][0].get("verdict") == "drifted",
              str(out["hosts"]))
        check("어긋나면 명령을 돌려준다", out["commands"] == ["python -m master.client deliver X"],
              str(out))
        check("맞추지는 않는다 (기본)", out["aligned"] == [], str(out))

        out2 = L.sync_check("X", align=True, checker=drift,
                            deliverer=lambda f: delivered.append(f.host))
        check("[중요] align=True 면 맞춘다", delivered == ["h"], str(delivered))
        check("맞췄으면 명령을 안 돌려준다", out2["commands"] == [], str(out2))

        same = lambda f: {"ok": True, "verdict": "same", "behind": 0, "reason": "같다"}
        out3 = L.sync_check("X", checker=same)
        check("같으면 어긋난 기계가 없다", out3["drifted"] == [] and "같은 버전" in out3["note"],
              str(out3))
    finally:
        B.workshops, B.probe = keep_ws, keep_probe


# ── ⑥-i 프로젝트 인자는 필수 — 폴백이 없다 (#227 소 1.2) ──────────

def test_project_arg_required() -> None:
    """사용자 2026-08-22: *"아무것도 설정 안하고 폴백에서 처리된다면 그게 폴백 처리냐?"*

    [중요] `DEFAULT_PROJECT = "ModularStage"` 는 **폴백이 아니라 조용한 오답**이었다.
    `config.json` 의 `project` 는 요청·응답을 결정하는 태그이고, 인자를 한 번 빼먹으면 다른
    프로젝트의 기계가 `ModularStage` 태그를 받아 남의 프로젝트로 일한다.
    """
    from master.client import __main__ as CLI

    check("[중요] 하드코딩 폴백이 사라졌다", not hasattr(CLI, "DEFAULT_PROJECT"))

    src = (Path(__file__).resolve().parent / "client" / "__main__.py").read_text(
        encoding="utf-8")
    # [주의] **언급 금지가 아니라 대입 금지다.** 머리말이 그 상수를 *왜 없앴는지* 설명하려고
    #    이름을 든다 — 그 설명은 남겨야 한다(다음 사람이 되살리지 않게).
    check("대입이 없다", not any(l.startswith("DEFAULT_PROJECT") for l in src.splitlines()))
    # [주의] 줄바꿈을 넘는 문구로 찾으면 안 잡힌다 (실측 — 원문이 "조용한\n오답" 으로 접힌다)
    check("없앤 이유는 문서로 남았다", "폴백이 아니라 조용한" in src)
    check("사용법이 인자를 필수로 적는다",
          "plan  <프로젝트>" in src and "plan  [<프로젝트>]" not in src)

    for cmd in ("probe", "plan", "deliver", "check"):
        check(f"{cmd}: 인자 없으면 rc=2 (거부)", CLI.main([cmd]) == 2, cmd)

    check("모르는 명령도 거부", CLI.main(["없는명령"]) == 2)
    check("빈 인자도 거부", CLI.main([]) == 2)

    # [주의] 이 저장소의 관례와 같은 방향인지 — `projects_root` 도 폴백이 없다
    from master.projects.config import projects_root
    import os
    keep = os.environ.pop("AX_PROJECTS_ROOT", None)
    try:
        try:
            projects_root()
            check("관례 확인: 루트도 폴백이 없다", False, "통과해버렸다")
        except Exception:                                   # noqa: BLE001
            check("관례 확인: 루트도 폴백이 없다", True)
    finally:
        if keep is not None:
            os.environ["AX_PROJECTS_ROOT"] = keep


# ── ⑥-j 태그: 명시·저장·관리 (사용자 2026-08-22) ──────────────────

def test_tag_managed() -> None:
    """*"초반 프로젝트 설치하고 설정 과정에서 태그 명시해서 저장하고, 관리해."*

    [중요] 셋을 갈라 지킨다 — **명시**(인자 필수) · **저장**(config 에 기록) ·
    **관리**(`check` 가 기대값과 대조). 「저장」만 있고 「관리」가 없으면 태그가 조용히
    어긋난다. 실측 전례: `.2` 의 `.mcp.json` 이 `.33` 의 경로를 갖고 있었고 **글자까지 같아서**
    에러 없이 죽어 있었다.
    """
    import json as _j
    keep = bundle._remote_read
    try:
        bundle._remote_read = lambda f, p: _j.dumps({"project": "A"})
        v = bundle.compare_tag(_fake_facts(), "A")
        check("같으면 통과", v["ok"] and v["stored"] == "A", str(v))

        v = bundle.compare_tag(_fake_facts(), "B")
        check("[중요] 다르면 실패", not v["ok"], str(v))
        check("두 값을 다 보여준다", "'A'" in v["reason"] and "'B'" in v["reason"], v["reason"])
        check("무엇이 걸린 일인지 말한다", "요청·응답" in v["reason"], v["reason"])

        bundle._remote_read = lambda f, p: _j.dumps({"project": ""})
        v = bundle.compare_tag(_fake_facts(), "A")
        check("[중요] 빈 태그는 실패 (fail-closed)", not v["ok"] and "비어 있다" in v["reason"],
              str(v))

        bundle._remote_read = lambda f, p: ""
        v = bundle.compare_tag(_fake_facts(), "A")
        check("[중요] 못 읽으면 실패 — 모르면 통과시키지 않는다", not v["ok"], str(v))

        bundle._remote_read = lambda f, p: "{깨짐"
        check("파싱 실패도 실패", not bundle.compare_tag(_fake_facts(), "A")["ok"])
    finally:
        bundle._remote_read = keep

    # 저장 쪽 — config_for 가 인자를 그대로 태그로 쓴다
    cfg = bundle.config_for("어떤프로젝트", _fake_facts())
    check("저장: config 에 태그가 기록된다", cfg[spec.TAG_FIELD] == "어떤프로젝트", str(cfg.get("project")))

    # 관리 쪽 — check 가 실제로 그 대조를 부르는지 (배선 확인)
    cli = (Path(__file__).resolve().parent / "client" / "__main__.py").read_text(encoding="utf-8")
    body = cli.split("def cmd_check(")[1].split("\ndef ")[0]
    check("[중요] check 가 compare_tag 를 부른다", "compare_tag" in body)
    check("태그 불일치가 판정에 들어간다", "ok_tag" in body)
    plan_body = cli.split("def cmd_plan(")[1].split("\ndef ")[0]
    check("plan 이 쓸 태그를 명시한다", "[태그 " in plan_body)


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
               test_init_flag_not_shadowed, test_git_excludes, test_gitignore_block,
               test_register_seeds_defaults, test_synth_source_only,
               test_delivered_stamp, test_compare_version,
               test_config_documents_comparison, test_project_arg_required,
               test_tag_managed,
               test_switch_syncs,
               test_sync_check_shape,
               test_server_steps,
               test_load_init_env,
               test_clone_dir):
        fn()
    # [중요] 형식 A(`N/M 통과`)로 찍는다 — 러너가 읽는 두 형식 중 하나여야 합계에
    #    들어간다. 안 맞으면 "수치 못 읽음"으로 **조용히 분모에서 빠진다**.
    print(f"{'OK' if not FAIL else 'FAIL'} test_client_spec: {PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
