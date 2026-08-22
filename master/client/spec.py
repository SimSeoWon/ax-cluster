"""초기화 사양 — 「**초기화된 프로젝트란 무엇인가**」의 선언 (`#266`, §12.5-g).

## 왜 선언이 먼저인가

`#259`(서버 몫 초기화)를 명령 하나로 구현하면 스크립트가 나오고, 클라 쪽에 동작을 하나 더
넣거나 스킬·MCP 를 등재하려 할 때 **확장 자리가 다시 없다.** 사용자 요구(2026-08-22):
*"초기화 과정에서 사용할 규격화된 내용이 있어야 추후 클라측 작업할 때 추가 동작기능을
넣는다거나 클라이언트의 클로드 .md 파일에 스킬이나 MCP 를 등록한다거나 할 수 있잖아."*

그래서 여기는 **표**만 둔다. 실행기(`bundle.py` 의 `plan`/`deliver`/`check`, `#259` 의 서버
초기화)는 이 표를 도는 쪽이다. 새 동작을 넣는 것이 **표에 행 추가**가 되지 않으면 실패다.

## 원전이 이미 그 모양이다 (census 2026-08-22, `~/AgentTest`)

    watcher/agent_defs.py        AGENT_DEFINITIONS · SKILL_INDEX
    watcher/skill_templates.py   SKILL_DEFINITIONS + DEPRECATED_SKILL_NAMES
    watcher/agent_templates.py   MCP_SERVERS + DEPRECATED_MCP_NAMES + unreal-mcp 조건부
    watcher/project_claude_md.py <!-- AgentWatch:Start --> ~ End — 그 사이만 덮는다
    watcher/setup.py             _merge_* 일곱 → init_project_dirs() 하나가 멱등 병합

[중요] **`DEPRECATED_*` 목록이 규격의 일부다.** 표에서 지우는 것만으로는 **이미 배달된 기계가
정리되지 않는다** — `#232`(제거된 MCP 서버를 부르는 스킬이 `.33` 에 배달돼 있었다)가 그 부류였고,
그때 실패는 조용했다.

## 세 축을 섞지 않는다

    역할(role)      무엇을 하는 기계인가       worker · requester
    프로젝트        무엇을 만드는 저장소인가   config.yaml 의 `init:` (ProjectInit)
    절(section)     초기화의 어느 단계인가     server · client

[주의] 지금까지 표가 **역할 축뿐**이었다(`*_BY_ROLE`). 그래서 프로젝트마다 다른 값(도메인 목록·
컨벤션 절 이름·추가 스킬)이 들어갈 자리가 없었다. 여기서 **프로젝트 축**을 더한다.

## [중요] 표에 본문을 박지 않는다 — 실파일을 가리킨다

스킬 본문·CLAUDE.md 관리 구역은 수백 줄이다. `workshop_files()` 가 이미 그 관례고, 원전도
`SKILL_DEFINITIONS` 에 본문을 담았다가 2,200줄이 되어 모듈을 쪼갰다. 우리는 실파일이 이미
있으므로 경로만 든다.

[주의] **대상 집합을 이 표로 잡지 않는다.** 파일을 옮길 때 「배달 목록」을 대상 집합으로 쓰면
목록 밖 파일이 조용히 깨진다 — `#263` 에서 `vector_fallback.py` 가 그렇게 깨졌고
`except Exception` 이 삼켜 **테스트 검사 9개가 사라진 채 「통과」로 보고**됐다. 이동·감사는
**디렉토리 전수**로 잰다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ─────────────────────────────────────────────────────────────────────
# 서버 절 — `#259` 가 구현하는 단계들
# ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Step:
    """서버 초기화의 한 단계.

    `probe` 는 「이미 됐는가」를 재는 이름이다 — 멱등의 근거이고, `check` 가 이 이름으로 답한다.
    """

    key: str
    what: str
    probe: str
    required: bool = True


# [중요] **`consumer.process_event` 를 재사용하지 않는다.** 그쪽은 `if changed:` 안에서만
#    합성하므로 새 프로젝트(클론 직후 `from_commit == to_commit`)는 **합성이 아예 돌지 않는데**
#    워터마크는 찍힌다(`#244` 가 그 자리다). 최초 색인은 증분과 다른 진입이어야 한다.
# [주의] 부품은 전부 있다 — 없는 것은 이어 주는 하나였다(실측 2026-08-22):
#    graph/class_graph.py:139 build_full · graph/dependency.py:154 build_full
#    context_synth/synth.py:323 run(changed=None, skip_existing=True)   ← 원전 initial_context_build
#    context_search/rebuild.py:61 rebuild_all
SERVER_STEPS = (
    Step("bare", "Gitea bare 저장소가 있는지 확인한다",
         "resolve_bare_path 가 예외 없이 통과"),
    Step("register", "트윈 디렉토리·config.yaml·gitignore·원본 git 잠금",
         "<트윈>/config.yaml 이 있다"),
    Step("clone", "소스 클론 — <트윈>/<local_clone>/ 에 워킹트리",
         "paths.repo 가 git 저장소다"),
    Step("graph", "클래스·의존 그래프 전체 구축",
         "class_graph.db · dependency_graph.db 에 행이 있다"),
    Step("synth", "컨텍스트 MD 최초 합성 (누락분만 — 중단 후 재실행 가능)",
         "<트윈>/context/ 에 MD 가 있다"),
    Step("index", "벡터·BM25 색인 전체 구축 + 워터마크 기입",
         "config.yaml 의 index.last_indexed_commit 이 비어 있지 않다"),
)

# [중요] **마운트는 이 표에 없다** (§12.5-d [주의]). 첫 프로젝트는 `register_project` 가 자동
#    마운트하지만 둘째부터는 전환이 §12.5-b 의 **되묻기 계약**을 타야 한다. 초기화가 조용히
#    마운트를 바꾸면 그 계약이 깨진다.


# ─────────────────────────────────────────────────────────────────────
# 클라 절 — 역할별 설치물
# ─────────────────────────────────────────────────────────────────────

# [중요] 역할별 스킬 — 요청자에게 워커 절차를 주지 않는다 (사용자 확정 2026-08-09).
#   사람이 편집 중인 트리에서 에이전트가 브랜치를 만들고 파일을 고치는 것이, 더티 체크가
#   막으려던 바로 그 사고다.
# [중요] 워커에 스킬이 **둘** 배달된다 — 파견 지시가 어느 쪽인지 이름으로 고른다.
#   `ax-infer` 가 현 토폴로지(워커는 추론만)이고, `ax-work` 는 구 토폴로지(워커가 커밋)다.
#   구 것을 **지우지 않는 이유**는 settled 결정이다: N-writer 기계장치는 측정으로 뒤집힐
#   여지가 있는 동안 되돌릴 수 있게 둔다(§8.4 [주의]).
SKILLS_BY_ROLE = {
    "worker": ("ax-work", "ax-infer"),
    # [중요] `ax-review` 는 원전의 「리더(TD·팀장)」 자리다 — 우리에겐 그 그룹이 없어
    #   요청자가 그 판단을 한다(사용자 확정 2026-08-16). 가드가 이미 그렇게 적어 뒀다.
    "requester": ("ax-request", "ax-ontology", "ax-review"),
}

# 폐지된 스킬 — 배달 대상에서 지우는 것만으로는 **이미 놓인 기계가 정리되지 않는다**.
# `plan` 이 제거 항목으로 들고, `deliver` 가 지운다.
# [주의] 사용자가 손으로 만든 스킬은 이 목록에도 위 표에도 없으므로 **영향받지 않는다**
#    (원전 `DEPRECATED_SKILL_NAMES` 와 같은 계약).
DEPRECATED_SKILLS = (
    # 2026-08-20 제거 — 배달 스킬 3종이 제거된 MCP 서버를 부르고 있었다(`#232`).
    "distribute",
    "review-work",
)

# 역할별 MCP 엔트리 **이름**. 항목의 내용(command·args·header)은 기계마다 다르므로
# `bundle.mcp_entry_for(facts)` 가 실측으로 만든다 — 여기서 선언하는 것은 **누가 받는가**다.
# [주의] 워커가 `.mcp.json` 을 못 받는 것이 지금 상태이고, 그 판단을 조건문 한 줄이 아니라
#    이 표에서 보이게 한다 (`#261`).
MCP_BY_ROLE = {
    "worker": (),
    "requester": ("ax-client",),
}

# 폐지된 MCP 엔트리 이름 — 자리는 여기고, **지금은 비어 있다.**
#
# [중요] **비워 둔 것이 판단이다.** `#232` 가 죽은 호출을 걷어낸 서버 셋
# (`master-orchestrator`·`context-search`·`task-queue`)은 `.33` 의 `.mcp.json` 11종 안에 있고,
# **그 11종의 귀속 분류가 아직 미결**이다(`#235` 신규 · `#238` 사람 결정 대기). 남의 것일 수도
# 있는 항목을 폐지로 선언하면 다음 배달이 **사람의 파일에서 그것을 지운다.**
# [주의] 그래서 이름을 넣는 것은 `#235` 가 귀속을 적은 **뒤**다. 기계장치(`removals_for`)는
#    지금 만들어 두고 목록만 비운다 — 없는 것을 지어내지 않는 쪽이 fail-closed 다.
DEPRECATED_MCP: tuple = ()


# ── 커밋 제외 대상 ───────────────────────────────────────────────────
#
# [중요] **마스터가 체크아웃 안에 쓰는 것은 전부 여기 들어야 한다.** 배달물이 워킹트리를
# 더럽히면 **더티 체크가 다음 파견을 막는다** — 그것이 이 목록의 존재 이유다.
#
# [중요] **`.gitignore` 가 아니라 `.git/info/exclude` 다.** `.gitignore` 는 커밋해야 효력이 있고
# **마스터는 소스 저장소에 push 할 수 없다**(§2.1). `info/exclude` 는 클론 로컬이라 커밋 없이
# 즉시 듣는다.
#
# [주의] **실측이 이 표를 넓혔다** (2026-08-22, 사용자 지적). 종전에는 `/.ax/`·`/.mcp.json` 두
# 줄뿐이었고 그래도 `.33` 이 안 더러웠는데, 이유는 **ModularStage 저장소 자신의 `.gitignore` 가
# 그 줄을 갖고 있어서**였다(실측: `.gitignore:36 .claude/` · `:40 /.mcp.json` · `:41 /CLAUDE.md`).
# **그건 그 프로젝트의 파일이다** — 새 프로젝트엔 없고, 우리는 그것을 고칠 수 없다. 즉 종전
# 목록은 「지금 안 터지는」 것이었을 뿐 **다음 프로젝트에서 반드시 터지는** 종류였다.
#
# 원전도 그 자리를 넓게 처리했다: `setup._update_project_gitignore` +
# `_untrack_ambient_managed_files`(*"ambient 파일(.mcp.json, CLAUDE.md)이 이미 tracked 였으면
# untrack — 새 .gitignore 가 효력 발휘하려면 index 에서 제거 필요. 디스크 보존"*).
GIT_EXCLUDES = (
    ("/.ax/", ()),                 # 부산물·config·토큰·페이로드 (역할 무관)
    ("/.mcp.json", ()),            # 요청자만 받지만, 있어도 해가 없고 목록이 갈리는 것이 더 나쁘다
    ("/CLAUDE.md", ()),            # 마스터가 관리 블록을 넣는다 — 모든 역할이 받는다
    ("/.claude/", ("requester",)),  # 작업장 자산 29개 (요청자 전용)
)


def git_excludes_for(role: str) -> tuple:
    """이 역할의 체크아웃에서 커밋 제외할 경로들."""
    return tuple(line for line, roles in GIT_EXCLUDES if not roles or role in roles)


# [중요] **추적 중인 파일은 exclude 로 못 막는다.** 프로젝트가 `CLAUDE.md` 를 커밋해 두고 있으면
# 우리 블록이 그것을 **modified** 로 만들고, `info/exclude` 는 그것에 아무 효력이 없다. 원전은
# 그때 index 에서 빼고 디스크를 보존했다(`git rm --cached`). [주의] 그것은 **사람의 저장소
# 인덱스를 고치는 일**이라, 우리는 지금 **찾아서 이름으로 보고**만 한다 — 자동 untrack 여부는
# 사람 결정 자리다(#259 onboard 의 확인 단계).
AMBIENT_MANAGED = ("CLAUDE.md", ".mcp.json", ".claude/CLAUDE.md")


@dataclass(frozen=True)
class MdBlock:
    """마커로 감싼 **관리 구역** 하나. 그 사이만 덮고 사람이 쓴 나머지는 건드리지 않는다."""

    key: str
    rel: str
    begin: str
    end: str
    roles: tuple = ()          # 빈 튜플 = 역할 무관

    def applies(self, role: str) -> bool:
        return not self.roles or role in self.roles


# [중요] 마커 문자열을 **바꾸지 않는다.** 이미 배달된 기계의 파일에 그 글자가 들어 있어,
#    바꾸면 다음 병합이 옛 블록을 못 찾고 **맨 뒤에 하나 더 붙인다**(`.2` 에서 실제로 두 번
#    붙은 파일이 나왔다, 2026-08-09).
MD_BLOCKS = (
    MdBlock("ax", "CLAUDE.md",
            "<!-- AX:Begin — 마스터가 생성한다. 이 블록만 덮인다 -->", "<!-- AX:End -->"),
    MdBlock("workshop", ".claude/CLAUDE.md",
            "<!-- AgentWatch:Start -->", "<!-- AgentWatch:End -->", roles=("requester",)),
)


# ─────────────────────────────────────────────────────────────────────
# 프로젝트 절 — `config.yaml` 의 `init:` 오버레이
# ─────────────────────────────────────────────────────────────────────

# 컨텍스트 도메인 폴더 기본값. [주의] 원전은 이 목록을 **코드에 박아** 뒀다
# (`DEFAULT_CONTEXT_DOMAINS` — ModularStage 의 한국어 도메인 10개). 프로젝트마다 다른 값이
# 코드에 있으면 두 번째 프로젝트에서 곧 틀린다 — 그래서 여기서는 **빈 기본값**이고,
# 프로젝트가 자기 `config.yaml` 에 적는다.
DEFAULT_DOMAINS: tuple = ()

# 프로젝트 문서에서 실어 올 절 이름. `work/conventions.py:37 WANTED_SECTIONS` 의 기본값과
# 같아야 한다 — 그쪽이 **프로젝트의 `repo/CLAUDE.md` 를 읽어서** 매니페스트에 싣는 쪽이다.
# [중요] 규약의 SSOT 는 프로젝트 문서다. 여기서 정하는 것은 **어느 절을 읽을지**뿐이다.
DEFAULT_CONVENTION_SECTIONS = ("Code conventions",)


@dataclass(frozen=True)
class ProjectInit:
    """`config.yaml` 의 `init:` 절. 없으면 전부 기본값 — **선언하지 않은 프로젝트도 돈다.**"""

    domains: tuple = DEFAULT_DOMAINS
    convention_sections: tuple = DEFAULT_CONVENTION_SECTIONS
    extra_skills: dict = field(default_factory=dict)      # role → (name, ...)
    extra_mcp: dict = field(default_factory=dict)         # role → (name, ...)

    @classmethod
    def from_config(cls, cfg) -> "ProjectInit":
        """`ProjectConfig` → 이 값. [주의] `cfg.raw` 를 읽는다 — `to_yaml()` 이
        `dict(self.raw)` 로 시작해 **모르는 키를 보존**하므로 `init:` 이 왕복으로 살아남는다.
        그래서 사양을 별도 파일로 두지 않았다(§12.5-g 근거 ③).
        """
        raw = (getattr(cfg, "raw", None) or {}).get("init") or {}
        if not isinstance(raw, dict):
            raise ValueError(f"config.yaml 의 `init:` 은 매핑이어야 한다: {type(raw).__name__}")
        return cls(
            domains=tuple(raw.get("domains") or DEFAULT_DOMAINS),
            convention_sections=tuple(raw.get("convention_sections")
                                      or DEFAULT_CONVENTION_SECTIONS),
            extra_skills=_by_role(raw.get("extra_skills"), "extra_skills"),
            extra_mcp=_by_role(raw.get("extra_mcp"), "extra_mcp"),
        )


def _by_role(val, label: str) -> dict:
    """`{role: [name, ...]}` 로 정규화. 리스트를 주면 **모든 역할**에 적용한다.

    [주의] 조용히 무시하지 않는다 — 오타 난 키를 무시하면 사용자는 등재된 줄 안다
    (`server.py:426` 의 *"거부도 200 + ok:false 로 말한다"* 와 같은 결).
    """
    if not val:
        return {}
    if isinstance(val, (list, tuple)):
        return {r: tuple(val) for r in SKILLS_BY_ROLE}
    if not isinstance(val, dict):
        raise ValueError(f"`init.{label}` 은 리스트 또는 (역할 → 리스트) 매핑이어야 한다: "
                         f"{type(val).__name__}")
    out = {}
    for role, names in val.items():
        if role not in SKILLS_BY_ROLE:
            raise ValueError(f"`init.{label}` 에 모르는 역할: {role!r} "
                             f"(아는 것: {', '.join(sorted(SKILLS_BY_ROLE))})")
        out[role] = tuple(names or ())
    return out


EMPTY_INIT = ProjectInit()


# ─────────────────────────────────────────────────────────────────────
# 조회 — 실행기가 부르는 자리
# ─────────────────────────────────────────────────────────────────────


def skills_for(role: str, init: ProjectInit | None = None) -> tuple:
    """이 역할이 받을 스킬. 기본 표 + 프로젝트 오버레이, **순서 보존 · 중복 제거**."""
    base = SKILLS_BY_ROLE.get(role, ())
    extra = (init or EMPTY_INIT).extra_skills.get(role, ())
    return _dedup(base + tuple(extra))


def mcp_for(role: str, init: ProjectInit | None = None) -> tuple:
    """이 역할이 받을 MCP 엔트리 **이름**."""
    base = MCP_BY_ROLE.get(role, ())
    extra = (init or EMPTY_INIT).extra_mcp.get(role, ())
    return _dedup(base + tuple(extra))


def removals_for(role: str, init: ProjectInit | None = None) -> dict:
    """이 역할의 기계에서 **지울 것**. 폐지 목록에서, 지금 배달 대상인 것은 뺀다.

    [중요] 뺄셈을 하는 이유: 폐지 이름이 나중에 되살아나면(같은 이름의 새 스킬) 배달과 제거가
    같은 대상을 두고 싸운다. 배달이 이긴다 — 제거는 **배달하지 않는 것만** 지운다.
    """
    keep_skills = set(skills_for(role, init))
    keep_mcp = set(mcp_for(role, init))
    return {
        "skills": tuple(n for n in DEPRECATED_SKILLS if n not in keep_skills),
        "mcp": tuple(n for n in DEPRECATED_MCP if n not in keep_mcp),
    }


def md_blocks_for(role: str) -> tuple:
    return tuple(b for b in MD_BLOCKS if b.applies(role))


def md_block(key: str) -> MdBlock:
    """키로 관리 구역 하나. 없는 키는 **예외** — 마커를 못 찾으면 병합이 블록을 하나 더 붙인다."""
    for b in MD_BLOCKS:
        if b.key == key:
            return b
    raise KeyError(f"모르는 관리 구역: {key!r} (아는 것: {', '.join(b.key for b in MD_BLOCKS)})")


def _dedup(names) -> tuple:
    seen, out = set(), []
    for n in names:
        n = str(n).strip()
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return tuple(out)


def load_init(project: str = "", *, registry=None) -> ProjectInit:
    """프로젝트 이름 → `ProjectInit`. 트윈이나 `config.yaml` 이 없으면 기본값.

    [주의] 여기서 예외를 삼키는 범위는 **부재**뿐이다. `init:` 이 깨졌으면 시끄럽게 실패한다 —
    조용히 기본값으로 접히면 「선언했는데 안 먹는」 상태가 되고, 그건 사양이 없는 것보다 나쁘다.

    [중요] **환경 오류와 부재를 가른다.** 처음엔 `resolve()` 의 `ConfigError` 를 통째로 접었는데,
    실측(2026-08-22 라이브 `plan`)에서 `AX_PROJECTS_ROOT` 미설정이 *"도메인: (선언 없음)"* 으로
    번역됐다 — **환경이 깨진 것을 「선언 안 함」으로 보고**한 것이다. `projects_root()` 를 먼저
    부르는 이유가 그것이고, 그 예외는 접지 않는다.
    """
    from ..context_search.paths import resolve
    from ..projects.config import ConfigError, ProjectConfig, projects_root
    projects_root()                     # 환경 오류는 여기서 터진다 (fail-closed)
    try:
        paths = resolve(project, registry=registry)
    except ConfigError:
        return EMPTY_INIT               # 미등록·미마운트 = 부재. 사양을 안 쓴 것과 같다
    if not paths.config.is_file():
        return EMPTY_INIT
    return ProjectInit.from_config(ProjectConfig.load(paths.config))
