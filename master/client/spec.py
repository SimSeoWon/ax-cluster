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
    # [중요] **훅은 클론과 무관하다** — 저장소(bare)에 붙는 것이고, 이것이 없으면 push 해도
    #    이벤트가 안 생겨 **즉시성이 사라진다**(폴링 5분이 결국 따라잡지만 그건 다른 것이다).
    #    `#227` 절차 ③에 있는데 이 표에 빠져 있어서 NS 온보딩을 「4/6」으로 **분모까지 틀리게**
    #    보고했다(#273).
    # [중요] **무인으로 돈다** — `/usr/local/bin/ax-install-hook` + sudoers NOPASSWD 를 등록했다
    #    (사용자 2026-08-22: *"자동화를 전제로 프로젝트 구성중"*). root 가 필요하다고 사람의
    #    인증창을 기다리면 그 단계는 자동이 아니다.
    Step("hook", "Gitea post-receive 훅 설치 (저장소별 ax-index · ax-project-id)",
         "<bare>/hooks/post-receive.d/ax-index 가 있다"),
    Step("clone", "소스 클론 — <트윈>/<local_clone>/ 에 워킹트리",
         "paths.repo 가 git 저장소다"),
    # [중요] **이 단계가 없어서 NS 가 무방비로 돌았다** (`#330`, 실측 2026-08-28).
    #    `#125` 의 pre-push 가드는 2026-08-14 에 코드로 들어왔지만 **온보딩 단계가 아니었고**,
    #    그때 있던 ModularStage 클론에만 손으로 깔렸다. 2026-08-22 에 온보딩한 NS 는 그 단계를
    #    지나지 않아 **가드 없이 시작했다** — 마스터의 `task/*` 밖 push · `main` 이동 ·
    #    미병합 삭제가 그동안 무방비였다.
    # [중요] **이름을 `guard` 로 둔다 — 위 `hook` 과 겹치지 않게.** 그 겹침이 사고의 원인이다:
    #    `hook` 은 **Gitea 서버**의 post-receive(받은 push → 재색인)이고 이것은 **마스터 자기
    #    클론**의 pre-push(나가는 push 를 막는다)다. 하는 일이 정반대인데 둘 다 "hook" 이라
    #    **있는 줄 알았다.**
    # [주의] **순서가 `clone` 뒤여야 한다** — LFS 저장소를 클론하면 git-lfs 가 자기 pre-push 를
    #    그 자리에 넣는다(NS 가 그랬다). 먼저 깔면 클론이 덮는다. 설치본은 LFS 위임을 포함한다
    #    (`#327` 에서 그렇게 고쳤다 — 그냥 덮으면 `.uasset` push 가 깨진다).
    Step("guard", "마스터 클론에 **pre-push 쓰기 가드** 설치 (`#125` — 오발 push 를 막는다)",
         "<트윈>/repo/.git/hooks/pre-push 가 우리 가드다 (`hook_status.state == ok`)"),
    # [중요] **컨벤션의 원천은 마스터 미러의 `CLAUDE.md` 다** (`#294`, 실측 2026-08-24).
    #    `work/conventions.project_doc` 이 `<트윈>/repo/CLAUDE.md` 의 `## Code conventions` 절을
    #    읽어 **워커 매니페스트**에 싣는다. 그런데 배달은 각 기계의 *체크아웃*에만 갔고 미러는
    #    대상이 아니었다 — NS 미러에 파일이 없어 매니페스트의 컨벤션이 **영구히 비었다.**
    #    ModularStage 는 사람이 그 파일을 놓아 둬서 우연히 돌고 있었다(N=1 에서는 우연과 설계가
    #    구별되지 않는다 — 이 세션 네 번째).
    #    [주의] 프로젝트에서 `/CLAUDE.md` 는 gitignore 대상이라(실측: `.gitignore:41`) 미러에
    #    놓아도 `merge --ff-only` 를 깨지 않는다.
    Step("conventions", "마스터 미러에 CLAUDE.md — **컨벤션의 원천** (워커 매니페스트가 읽는다)",
         "<트윈>/repo/CLAUDE.md 에 `## Code conventions` 절이 있다"),
    Step("graph", "클래스·의존 그래프 전체 구축",
         "class_graph.db · dependency_graph.db 에 행이 있다"),
    # [중요] **컨텍스트 문서 생성은 `Source/` 한정이다** (§5.2-E, 사용자 재확인 2026-08-22).
    #    `Content/` 는 워킹트리의 93%(uasset 바이너리)이고 합성 대상이 아니다. 경계는 세 겹으로
    #    지킨다: `list_source_files` 의 pathspec + 접두 검사, 그리고 `synth.run` 이 **넘겨받은
    #    목록도 거부**한다(호출자가 한 번 잘못 넘기면 조용히 들어오던 자리였다).
    Step("synth", "컨텍스트 MD 최초 합성 — **Source/ 한정** (누락분만, 중단 후 재실행 가능)",
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
SKILLS_BY_ROLE = {
    # 🔴 [중요] **`ax-work` 가 정본이다** (사용자 확정 2026-09-02 · 7단계 ⑸): *"워커들은 …
    #    각각 지정된 서브 브랜치에 커밋하고 작업을 마치고 다음 작업을 요청해"*. 라이브 파견
    #    경로가 `dispatch_task → commit_task → runner.run_worker → INSTRUCTION` 이고 그
    #    INSTRUCTION 이 *"Follow the ax-work skill"* 이다. **없으면 워커가 계약을 못 읽는다.**
    # [주의] **`ax-work` 를 폐지로 표시했던 것은 내 판단이었고 되돌렸다** (같은 날 오전).
    #    근거로 `#320`(상주 철거)과 `INFER_INSTRUCTION` 의 *"not ax-work"* 를 들었는데,
    #    정본이 워커 커밋이므로 둘 다 **되돌릴 목록**에 있던 것이다.
    # [중요] **죽은 절차서를 배달하면 워커가 그것을 집는다** — 실측 2026-09-02 00:02: 매니페스트를
    #    없앤 뒤 `ax-infer` 가 아직 매니페스트를 요구해 4/4 가 `BLOCKED` 됐고, 워커는 스킬 문구를
    #    근거로 댔다("Per skill §2/§8"). 명령줄과 문서가 갈리면 **문서가 이긴다.**
    #    → 그래서 이 목록을 고칠 때는 **SKILL.md 본문이 지금 계약인지 함께 확인한다.**
    # [주의] `ax-infer` 도 남긴다 — `infer.infer_task` 가 아직 살아 있는 코드이고(추론만 필요한
    #    경로·테스트), 파견 지시가 이름으로 고르는 것이 원래 계약이다.
    "worker": ("ax-work", "ax-infer"),
    # [중요] `ax-review` 는 원전의 「리더(TD·팀장)」 자리다 — 우리에겐 그 그룹이 없어
    #   요청자가 그 판단을 한다(사용자 확정 2026-08-16). 가드가 이미 그렇게 적어 뒀다.
    # 🔴 [중요] **`ax-advance` 는 그것과 다른 단계다** (사용자 확정 2026-09-04, 이름도 사용자):
    #   ⑺ **라운드 종결** — 서브 브랜치를 작업 브랜치에 머지·빌드하고 「버그냐 구조냐」를 물어
    #   그 브랜치를 **한 칸 전진**시킨다. `main` 은 만지지 않는다.
    #   [주의] 그 둘을 섞어 **오지시를 냈다** — 라운드가 끝났는데 공지가 `main` 머지를 권했다.
    #   사용자: *"리뷰 요청은 왜한건데? 전혀 다른 스킬을 요청한거 같은데"*. 두 SKILL.md 에
    #   서로를 가리키는 경계 문장을 넣었다(`ax-infer`/`ax-work` 가 갈린 방식과 같다).
    "requester": ("ax-request", "ax-ontology", "ax-advance", "ax-review"),
}

# 폐지된 스킬 — 배달 대상에서 지우는 것만으로는 **이미 놓인 기계가 정리되지 않는다**.
# `plan` 이 제거 항목으로 들고, `deliver` 가 지운다.
# [주의] 사용자가 손으로 만든 스킬은 이 목록에도 위 표에도 없으므로 **영향받지 않는다**
#    (원전 `DEPRECATED_SKILL_NAMES` 와 같은 계약).
DEPRECATED_SKILLS = (
    # 2026-08-20 제거 — 배달 스킬 3종이 제거된 MCP 서버를 부르고 있었다(`#232`).
    "distribute",
    "review-work",
    # [주의] `ax-work` 가 여기 있었다 — 되돌렸다(2026-09-02). 정본 ⑸ 의 계약이므로 지우면
    #    파견이 죽는다. 근거는 `SKILLS_BY_ROLE` 주석.
)

# 역할별 MCP 엔트리 **이름**. 항목의 내용(command·args·header)은 기계마다 다르므로
# `bundle.mcp_entry_for(facts)` 가 실측으로 만든다 — 여기서 선언하는 것은 **누가 받는가**다.
# [주의] 워커가 `.mcp.json` 을 못 받는 것이 지금 상태이고, 그 판단을 조건문 한 줄이 아니라
#    이 표에서 보이게 한다 (`#261`).
MCP_BY_ROLE = {
    # [중요] **워커도 받는다** (사용자 결정 2026-08-23: *"전부 열어 준다"*). 종전엔 비어 있어
    #    워커에 `.mcp.json` 이 안 갔고, 그래서 **코드를 추론하는 자리에서 레시피·안티패턴을
    #    읽을 수 없었다**(`#267` 의 루프가 반 바퀴만 돌았다). 사용자 지적으로 드러났다:
    #    *"워커들이 작동하는 디렉토리는 어디야? … 거기 클로드 문서에 MCP를 추가 안했다는거야?"*
    # [주의] **도구를 여는 것과 권한은 다른 축이다.** 쓰기 대행(시소러스·기록·레드마인)은
    #    워커 토큰 스코프(`auth.WORKER_SCOPE`)가 **403 으로 막는다** — 판단은 마스터, 워커는
    #    실행+보고라는 κ.0 경계는 토큰이 강제한다(§8.4). 열린 것은 **읽기**다.
    "worker": ("ax-client",),
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


# ── 프로젝트 태그 — **명시하고 저장하고 관리한다** ────────────────────
#
# [중요] 사용자 2026-08-22: *"초반 프로젝트 설치하고 설정 과정에서 태그 명시해서 저장하고,
# 관리해."* 그리고 그 앞에: *"아무것도 설정 안하고 폴백에서 처리된다면 그게 폴백 처리냐?"*
#
# 이 태그(`.ax/config.json` 의 `project`)로 **요청·응답이 결정된다**(§12.5-c). 그래서 셋을
# 갈라 지킨다:
#
#     명시   배달 명령에 프로젝트 인자가 **필수**다 — 폴백 없음 (`#227` 소 1.2)
#     저장   `config_for` 가 `project` 로 기록한다 (기계 안에 남는다)
#     관리   `check` 가 **저장된 태그를 기대값과 대조**한다 — 다르면 실패
#
# [주의] 「저장」만 있고 「관리」가 없으면 태그가 조용히 어긋난다. 실측 전례가 그것이다 —
# `.2` 의 `.mcp.json` 이 `.33` 의 경로를 갖고 있었고(글자까지 같았다) 에러 없이 죽어 있었다.
TAG_FIELD = "project"


# ── `.gitignore` 관리 블록 — 산출물 오염을 막는 쪽 ─────────────────
#
# [중요] **문제는 인프라 파일이 게임 저장소의 산출물에 섞이는 것이다** (사용자 2026-08-22:
# *"클로드가 실제 작업 결과물에 포함되는게 문제인거지"* · *"기존에 claude.md 파일이 커밋된 것도
# 잘못 추적되는거야"*). `.git/info/exclude` 는 **클론 로컬**이라 그 기계에만 듣는다 — 팀원이 새로
# 클론하면 없다. 커밋되는 `.gitignore` 만이 저장소 전체에 듣는다.
#
# [중요] **원전의 답이 ModularStage 에 이미 커밋돼 있다** (실측 `.gitignore:30-42`):
# `# AgentWatch:Start ~ End` 마커 블록에 `/watch.exe`·`/config.json`·`/.watch_state`·`.claude/`·
# `/.mcp.json`·`/CLAUDE.md`. 원전 주석이 이유를 둘 다 적었다 — *"서버/클라/개인 PC 가 각자 값을
# 갖고 git 동기화 시 충돌"* · *"추적 시 매 cycle 마다 'M ...' 가 발생해 워커·마스터의 브랜치
# 전환·머지가 막힘"*.
#
# [주의] **그 블록을 우리가 가로채지 않는다.** `# AgentWatch:` 는 원전이 만든 것이고 그 안의
# `/watch.exe` 등은 원전 자산이다 — 지금 그 함대가 어떤 상태인지 우리가 단정할 수 없다.
# 우리 블록은 따로 둔다(사람이 쓴 것을 덮지 않는다는 관례와 같은 결).
#
# [주의] 마스터는 소스 저장소에 push 할 수 없다(§2.1). 그래서 이 블록을 **쓰기만** 하고
# **커밋은 사람이 한다** — 원전도 그랬다(watcher 가 쓰고 개발자가 커밋).
GITIGNORE_BEGIN = "# AX:Begin — 마스터가 생성한다. 이 블록만 덮인다 (직접 편집 금지)"
GITIGNORE_END = "# AX:End"

GITIGNORE_BODY = (
    "# AX 클러스터 산출물 — 기계마다 값이 다른 환경 설정·런타임 데이터다.",
    "# 추적하면 ① 인프라 파일이 게임 산출물에 섞이고 ② 매 배달마다 'M ...' 가 생겨",
    "#          워커·마스터의 브랜치 전환·머지를 방해한다 (원전 .gitignore 주석과 같은 사유).",
    "/.ax/",
    "/.mcp.json",
    "/CLAUDE.md",
    ".claude/",
)


def gitignore_block() -> str:
    """`.gitignore` 에 넣을 관리 블록 전문."""
    return "\n".join((GITIGNORE_BEGIN, *GITIGNORE_BODY, GITIGNORE_END))


# [중요] **추적 중인 파일은 exclude 로 못 막는다.** 프로젝트가 `CLAUDE.md` 를 커밋해 두고 있으면
# 우리 블록이 그것을 **modified** 로 만들고, `info/exclude` 는 그것에 아무 효력이 없다. 원전은
# 그때 index 에서 빼고 디스크를 보존했다(`git rm --cached`). [주의] 그것은 **사람의 저장소
# 인덱스를 고치는 일**이라, 우리는 지금 **찾아서 이름으로 보고**만 한다 — 자동 untrack 여부는
# 사람 결정 자리다(#259 onboard 의 확인 단계).
AMBIENT_MANAGED = ("CLAUDE.md", ".mcp.json", ".claude/CLAUDE.md", ".claude/settings.json")


# ── 관리 훅 — **배달만으로는 안 돈다** (`#337`, 원전 `setup._merge_managed_hooks` 이식) ──
#
# [중요] **훅 파일은 2026-08-20부터 배달됐고 한 번도 안 돌았다.** `bundle.workshop_files` 가
# `hooks/` 를 파일째 보내지만(`bundle.py` `WORKSHOP_ROLES` 절), 훅은 **파일이 있다고 도는 것이
# 아니라 `settings.json` 의 `hooks` 키에 등록돼야** 돈다. 실측 2026-08-30: 배달 코드 전체에
# `settings.json`·`PostToolUse`·`SessionStart` 문자열 **0건**, `.33` 의 `settings.local.json` 은
# `enabledMcpjsonServers` 뿐이고 `~/.claude/settings.json` 은 model/theme 뿐 — `hooks` 키 0건.
# 즉 `workshop/hooks/domain_hint.py` 는 **배달된 채 죽어 있었다.**
# [주의] `#317` 이 지목한 「돌기는 도는데 아무도 모른다」의 뒤집힌 짝이다 — **안 도는데 아무도
# 모른다.** 배달이 성공을 보고했고 파일 해시도 3자 일치였다.
#
# 원전에는 이 배선이 있었다 — `watcher/setup.py:315 _merge_managed_hooks` 가 `domain_hint.py`
# 를 marker 로 삼아 **관리 항목만 교체하고 사용자 훅은 보존**했고, `:414 _update_project_settings`
# 가 `.claude/settings.json` 을 읽어 머지했다. `census.py setup.py` → 인용 7회인데 이 부분만
# 안 따라왔다. **이식 누락이지 새 기능이 아니다.**
#
# [중요] 파일 분담도 원전을 따른다 (`history/2026-03-28_1550_기존Claude환경머지검증및수정.md`):
#
#     .claude/settings.local.json   **건드리지 않는다** — 사람 것 (MCP 토글·permissions)
#     .claude/settings.json         우리가 관리 — 관리 항목만 교체, 나머지 보존
#
# [주의] **선언은 여기 하나다.** 배선을 따로 하드코딩하면 `mcp_for` 가 치른 값을 또 치른다
# (실측 2026-08-23: 선언을 바꿨는데 배달이 안 따라와 워커에 `.mcp.json` 이 안 갔다).
MANAGED_HOOKS = (
    # (event, matcher, 체크아웃 기준 스크립트 경로, timeout초)
    # [중요] marker 는 스크립트 경로다 — 이 문자열이 든 기존 항목만 우리 것으로 보고 교체한다.
    ("PostToolUse", "Edit|Write", ".claude/hooks/domain_hint.py", 10),
    # [중요] **세션 시작 미머지 점검** (`#337` 본체, 사용자 결정 ⓑ 2026-08-30). 승인이 곧
    #    트리거인데 「승인 기다리는 게 있다」를 사람이 찾아야만 알 수 있었다.
    #    [주의] matcher 는 `source` 를 **정규식으로** 가른다 — 실측 2026-08-30(`claude -p`):
    #    "resume" → 미발동 · "startup" → 발동 · "startup|resume|clear" → 발동.
    #    `compact` 는 뺐다 — 압축은 「켠 것」이 아니라 한 세션 안의 일이다.
    ("SessionStart", "startup|resume|clear", ".claude/hooks/pending_works.py", 15),
    # 🔴 [중요] **매 턴에도 고지한다** (사용자 지시 2026-09-04).
    #
    # `SessionStart` 하나로는 **켜져 있는 세션에 아무것도 안 뜬다.** 실측 2026-09-04 01:30:
    # 라운드가 4/4 완주하고 Redmine `#354` 까지 났는데 `.33` 콘솔은 끝난 줄 몰랐다.
    # 사용자: *"작업 요청한 .33이 알 수 없는데 어떻게 알아..."*.
    #
    # [중요] 원전에는 **알림을 받는 주체**가 있었다 — `watcher/skill_defs_collab.py:406`
    # *"리더 그룹이 분산 작업 완료 알림(Redmine 이슈)을 받아"*. 그런데 우리 Redmine 은
    # **메일이 미설정**(`configuration.yml` 없음 · `settings` 에 `mail_from` 0건)이라 이슈가
    # 서버에 쌓이기만 한다. 즉 이식이 절반이었다. 그 절반을 훅으로 메운다.
    #
    # [주의] **소음이 안 되는 근거가 있다** — `pending_works.py:124` 가 열린 work 이 0이면
    # 침묵한다(*"세션마다 「없음」을 찍는 것은 소음이다"*). 있을 때만 말한다.
    #
    # [주의] `UserPromptSubmit` 은 stdout 이 **컨텍스트로 들어간다**(SessionStart 와 같은 계약).
    # timeout 을 짧게 둔다 — 사람의 매 턴을 붙잡지 않기 위해서다.
    ("UserPromptSubmit", "", ".claude/hooks/pending_works.py", 8),
)

# 관리 훅이 실리는 파일. [주의] `settings.local.json` 이 **아니다** — 위 분담 참조.
SETTINGS_REL = ".claude/settings.json"


def managed_hooks_for(role: str) -> tuple:
    """이 역할이 등록받을 관리 훅. 훅 스크립트는 작업장 자산이라 요청자만 받는다."""
    return MANAGED_HOOKS if role == "requester" else ()


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
    # [중요] **요청자 에디터 플러그인** (`#335`). 기본값이 **비어 있는 것이 계약이다** —
    #    선언하지 않은 프로젝트의 `.uproject` 를 우리가 건드릴 이유가 없고, `uproject` 는
    #    **게임 소스**라 §0.05(계획·동의)의 대상이다. 배달이 조용히 켜면 규약 위반이다.
    # [주의] `AllToolsets` 를 여기 넣지 말 것 — Experimental 25종을 프로젝트에 영구히 끌어온다
    #    (`#335` 주의). 최소는 `EditorToolset` 이고 늘리는 것은 프로젝트 결정이다.
    uproject_plugins: tuple = ()                          # ({"name":…, "targets":[…]}, …)

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
            uproject_plugins=_plugins(raw.get("uproject_plugins")),
        )


# [중요] `TargetAllowList: ["Editor"]` 가 **기본값이자 필수**다 (`#335`). `ModelContextProtocol`
#    은 Runtime 모듈도 갖고 있어서 안 묶으면 **인증 없는 MCP 서버가 패키징에 실려 나간다.**
DEFAULT_PLUGIN_TARGETS = ("Editor",)


def _plugins(val) -> tuple:
    """`uproject_plugins` 정규화 — 문자열 목록도 받고, 매핑이면 `targets` 를 존중한다.

    [주의] 조용히 무시하지 않는다 — `_by_role` 과 같은 결이다. 오타 난 항목을 넘기면 사용자는
    켜진 줄 안다.
    """
    if not val:
        return ()
    if not isinstance(val, (list, tuple)):
        raise ValueError(f"`init.uproject_plugins` 는 리스트여야 한다: {type(val).__name__}")
    out = []
    for i, item in enumerate(val):
        if isinstance(item, str):
            out.append({"name": item, "targets": DEFAULT_PLUGIN_TARGETS})
            continue
        if not isinstance(item, dict) or not str(item.get("name") or "").strip():
            raise ValueError(f"`init.uproject_plugins[{i}]` 는 이름 문자열이거나 "
                             f"`name` 을 가진 매핑이어야 한다")
        tg = item.get("targets") or DEFAULT_PLUGIN_TARGETS
        if isinstance(tg, str):
            tg = (tg,)
        out.append({"name": str(item["name"]).strip(), "targets": tuple(tg)})
    return tuple(out)


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
