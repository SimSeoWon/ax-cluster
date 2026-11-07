"""프로젝트 등록·전환 MCP 서버 — 대화형으로 처리하기 위해 외부로 노출한다 (PLAN §5.5).

노출 도구:
  · register_project — 디지털 트윈을 생성할 프로젝트를 등록한다(설정 파일 생성부터)
  · set_active       — 가리키는 프로젝트를 바꾼다
  · register_work    — 작업장이 일감을 등록한다 (§4.7 복구 ①)

[주의] 이 서버가 프로젝트 레지스트리를 넘어 **작업장의 단일 창구**가 되고 있다. 의도된 통합이다 —
작업장이 엔드포인트를 여러 개 물게 하는 것보다 낫다. 다만 더 커지면 쪼갤 것.

읽기용(부수): list_projects · check_registry

[중요] **인증 필수** — `task_queue`(8101)·브로커(8102) 와 같은 베어러 토큰을 쓴다
(`master/auth.py`, 2026-08-08). 토큰이 없으면 **서비스가 뜨지 않는다**(fail-closed).
방화벽(LAN 한정)은 그와 **별개의 두 번째 층**이다 —
`ufw allow from 192.168.0.0/24 to any port 8103` 을 `Anywhere` 로 넓히지 말 것.

[중요] **작업 등록은 저장소를 만지지 않는다.** 브랜치 생성·골조 커밋은 작업장 몫이다(§4.7).
여기서 하는 것은 큐 등록과 매니페스트 수집뿐이다.

[주의] 설치된 SDK 는 `mcp` 2.0.0 이라 `mcp.server.fastmcp` 가 **없다**
(`task_queue/mcp_server.py` 는 아직 그 경로를 쓰고 있어 stdio 모드가 깨져 있다).
2.0.0 의 고수준 API 는 `mcp.server.MCPServer` 다.
"""
from __future__ import annotations

import json
from pathlib import Path

from mcp.server import MCPServer

from .config import ConfigError
from .logic import (
    list_projects,
    list_workshops,
    register_project,
    remove_workshop,
    set_active,
    set_workshop,
)
from .config import Registry, projects_root
from .workshop_check import check_project_workshops
from ..context_search.paths import resolve
# [DOC] #734: `get_code` 도구와 `generate.dispatch` import 는 요청자가 골조에서 걷었다(사용자 결정 2026-10-05 ①).
from ..work.register import RegisterError, TaskSpec, register_work

mcp = MCPServer(
    name="ax-projects",
    instructions=(
        "AX 클러스터 마스터가 보유한 디지털 트윈 디렉토리를 관리한다. "
        "프로젝트를 등록하면 그 디렉토리에 컨텍스트 문서와 온톨로지가 쌓이고, "
        "가리키는 프로젝트(active)는 한 번에 하나뿐이다."
    ),
)


def _fail(e: Exception) -> str:
    return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)


@mcp.tool()
def register_project_tool(
    name: str,
    project_id: str,
    bare_path: str = "",
    clone_url: str = "",
    branch: str = "main",
    engine: str = "",
) -> str:
    """디지털 트윈을 생성할 프로젝트를 등록한다.

    설정 파일(config.yaml) 생성부터 시작해 디렉토리·루트 목록·gitignore·원본 잠금까지
    한 번에 처리한다. 소스 클론과 최초 색인은 포함하지 않는다.

    name: 디렉토리명이 된다(예: ModularStage).
    project_id: Gitea 저장소 식별자 '<owner>/<repo>'. 별칭을 지어내지 말 것 —
                훅 이벤트가 이 값으로 온다.
    """
    try:
        return json.dumps(
            register_project(
                name, project_id, bare_path=bare_path, clone_url=clone_url,
                branch=branch, engine=engine,
            ),
            ensure_ascii=False,
        )
    except (ConfigError, OSError) as e:
        return _fail(e)


@mcp.tool()
def set_active_tool(name: str, force: bool = False, align: bool = True) -> str:
    """가리키는 프로젝트를 바꾼다. 디렉토리는 전부 남고 마운트 대상만 바뀐다.

    [중요] 큐에 미종결 work 가 있으면 거부한다 (#210) — 그 work 의 기록·신호가 다른
    프로젝트 트윈에 착지하는 것을 막는 가드다. force=True 는 사람이 감수한다는 뜻.

    [중요] **전환이 동기화 지점이다** (`#266`, 사용자 2026-08-22: *"마운트 대상을 바꿀때 체크
    한번 해서 맞추면 되는거잖아"*). 마운트가 실제로 바뀌면 그 프로젝트의 등재된 기계들이
    마스터와 같은 버전인지 보고 결과를 `sync` 로 낸다 — 미마운트 프로젝트는 순회하지 않는다.
    기본(`align=True`)은 뒤처진 기계에 **재배달까지** 하고 같은 버전은 건너뛴다 (`#655`,
    사용자 2026-10-06 — `master.client update` 가 마운트만 돌기 때문). 보고만 받으려면 align=False.
    """
    try:
        return json.dumps(set_active(name, force=force, align=align), ensure_ascii=False)
    except (ConfigError, OSError) as e:
        return _fail(e)


@mcp.tool()
def list_projects_tool() -> str:
    """등록된 프로젝트와 각각의 갱신 워터마크, 지금 가리키는 것을 돌려준다."""
    try:
        return json.dumps(list_projects(), ensure_ascii=False)
    except (ConfigError, OSError) as e:
        return _fail(e)


@mcp.tool()
def set_workshop_tool(
    name: str,
    host: str,
    driven: str = "interactive",
    path: str = "",
    user: str = "",
    role: str = "worker",
    note: str = "",
    dispatch: str = "",
) -> str:
    """작업장 한 대의 UE5 체크아웃 위치를 등록·갱신한다 (PLAN §5.5.4).

    마스터는 이 경로를 **읽지도 쓰지도 않는다** — 어디로 작업을 보낼지 정하는
    라우팅 정보다.

    host:   작업장 IP 또는 호스트명 (예: 192.168.0.2).
    driven: 'ssh' = 마스터가 밀어넣을 수 있다 / 'interactive' = 사람이 앉아서 한다.
            'ssh' 를 고르면 path 와 user 가 반드시 있어야 한다.
    path:   그 머신의 프로젝트 경로. 윈도우는 역슬래시 그대로 (예: E:\\trunk\\ModularStage).
    role:   'worker' = 큐에서 태스크를 집는다 / 'requester' = 등재·검증만 하고 **파견되지
            않는다**(`.33` 이 그렇다). [중요] 이 인자가 **없어서** 요청자를 이 표면으로는
            등재할 수 없었다(실측 2026-08-23: `logic.set_workshop` 엔 있는데 도구가 안 열어
            뒀다). 역할을 못 정하면 사람의 기계에 작업이 파견된다 — 기본값에 기대면 안 된다.
    dispatch: 지금 파견해도 되나 — `''`(미지정, **role 에서 유도**) / `'always'` / `'never'`.
            [중요] **좁히기 전용**이다 (`#321`): 워커를 점검·자원 부족으로 **잠시 뺄** 때 쓰고,
            요청자를 켜는 데는 쓸 수 없다(`role != worker` 에 `always` 를 적으면 거부된다).
            `role` 은 **자격**, `dispatch` 는 **가용성**이다.
            [주의] 손으로 YAML 을 고치지 말 것 — 이 도구가 유일한 쓰기 표면이다.
    """
    try:
        return json.dumps(
            set_workshop(name, host, driven=driven, path=path, user=user,
                         role=role, note=note, dispatch=dispatch),
            ensure_ascii=False,
        )
    except (ConfigError, OSError) as e:
        return _fail(e)


@mcp.tool()
def remove_workshop_tool(name: str, host: str) -> str:
    """워크숍 등록을 해제한다. 원격 디렉토리는 건드리지 않는다."""
    try:
        return json.dumps(remove_workshop(name, host), ensure_ascii=False)
    except (ConfigError, OSError) as e:
        return _fail(e)


@mcp.tool()
def list_workshops_tool(name: str = "") -> str:
    """이 프로젝트를 체크아웃해 둔 작업장들을 돌려준다.

    name 을 비우면 지금 가리키는 프로젝트를 본다. `drivable_hosts` 는 마스터가
    SSH 로 작업을 밀어넣을 수 있는 머신 목록이다.
    """
    try:
        return json.dumps(list_workshops(name), ensure_ascii=False)
    except (ConfigError, OSError) as e:
        return _fail(e)


@mcp.tool()
def project_profile_tool(name: str = "") -> str:
    """이 프로젝트의 **프로필**과 아직 안 채워진 칸, 그리고 **사람에게 물을 문장**을 돌려준다.

    🔴 [중요] **여기 나오는 질문은 사람에게 그대로 묻는다.** 모델이 소스를 보고 추론해 답을
    만들어 적립하지 않는다 — 골조 `questions` 와 같은 규약이다(*"모델의 제안을 답으로
    적립하지 않는다"*). 초안을 **보여 주는 것**은 되지만, 저장되는 문장은 사람이 확정한 것이다.

    [중요] 응답의 `measured` 는 **소스 트리 실측**이다(EngineAssociation · 모듈 · 확장자 분포).
    질문할 때 근거로 보여 주라고 싣는 것이고 **저장되지 않는다** — 측정을 결정 자리에 적립하면
    `#294` 가 치른 값을 다시 치른다(*"규약은 결정이지 측정이 아니다"*).

    `blockers` 가 비어 있지 않으면 그 프로젝트는 **분산 작업 등재가 거절된다**.
    """
    from . import profile as PF

    try:
        n = (name or "").strip() or Registry.load().active
        return json.dumps({"project": n, "profile": PF.load(n),
                           "missing": PF.missing(n), "blockers": PF.blockers(n),
                           "measured": PF.measure(n), "questions": PF.questions(n),
                           "path": str(PF.profile_path(n))}, ensure_ascii=False)
    except (ConfigError, OSError) as e:
        return _fail(e)


@mcp.tool()
def set_project_profile_tool(name: str = "", kind: str = "", engine_decided: bool | None = None,
                             engine: str = "", engine_version: str = "",
                             language: str = "", purpose: str = "",
                             genre: str = "", overview: str = "",
                             notes: str = "", work_exts: list[str] | None = None,
                             test_start_dir: str = "", test_pattern: str = "") -> str:
    """사람이 답한 프로필을 적립한다. **부분 저장을 허용**하고, 미완은 미완이라고 계속 말한다.

    🔴 [중요] **사람이 말한 문장만 싣는다.** 이 도구를 모델의 추론으로 채우면 이 단계가
    존재하는 이유가 사라진다 — 2026-09-20 에 지휘자가 남의 프로젝트 설명을 NS 의 사실로
    읽은 것이 그 값이다(`#649`).

    `kind` 는 unreal / index_only / code 중 하나다(`#693`·`#695`) — index_only 는 색인·검색까지만
    받고 분산 작업은 거절된다. code 는 UE 가 아닌 소스에 분산 작업을 받고, 받는 확장자를
    `work_exts` 로 적는다(지금은 `.py` 만). 엔진 세 칸은 unreal 일 때만 필수다.
    `purpose` 는 game / tool / rnd / demo 중 하나이고, `game` 이면 `genre` 도 필수다.
    `overview` 는 **왜 존재하는가**를 한 문단으로 적는다 (핵심 시스템·설계 의도).
    """
    from . import profile as PF

    try:
        n = (name or "").strip() or Registry.load().active
        fields = {k: v for k, v in (
            ("kind", kind), ("engine_decided", engine_decided), ("engine", engine),
            ("engine_version", engine_version), ("language", language),
            ("purpose", purpose), ("genre", genre), ("overview", overview),
            ("notes", notes), ("work_exts", work_exts),
            ("test_start_dir", test_start_dir), ("test_pattern", test_pattern)) if v not in ("", None)}
        if not fields:
            return json.dumps({"ok": False, "error": "적립할 값이 없다 — 사람의 답을 실어라",
                               "questions": PF.questions(n)}, ensure_ascii=False)
        return json.dumps(PF.save(n, **fields), ensure_ascii=False)
    except (ValueError, ConfigError, OSError) as e:
        return _fail(e)


@mcp.tool()
def check_workshops_clean_tool(name: str = "") -> str:
    """작업을 보내기 전에 워크숍 체크아웃이 안전한지 확인한다 (PLAN §5.5.4-⑥-1).

    자동화는 브랜치를 바꾸고 리셋한다 — 사람이 커밋하지 않은 작업이 있으면 날아간다.
    **추적 파일에 변경이 있으면 차단**하고, **미추적(`??`)은 통과**시킨다
    (checkout/reset 이 지우지 않기 때문).

    [중요] 검사하지 못하면(SSH 실패·타임아웃·저장소 아님) **통과가 아니라 차단**이다.
    [중요] 이 도구는 판정만 한다. 정리하지 않으며, `git clean` 은 절대 부르면 안 된다.

    `dispatchable` 이 지금 작업을 보내도 되는 호스트 목록이다.
    name 을 비우면 지금 가리키는 프로젝트를 본다.
    """
    try:
        return json.dumps(check_project_workshops(name), ensure_ascii=False)
    except (ConfigError, OSError) as e:
        return _fail(e)


@mcp.tool()
def check_registry_tool() -> str:
    """3자 일치 검사 — 루트 목록 ↔ 디렉토리 ↔ 각 config.yaml 의 name."""
    try:
        reg = Registry.load()
        problems = reg.check()
        return json.dumps(
            {"ok": not problems, "active": reg.active, "problems": problems},
            ensure_ascii=False,
        )
    except (ConfigError, OSError) as e:
        return _fail(e)


@mcp.tool()
def register_work_tool(
    title: str,
    target_repo: str,
    specs_json: str,
    original_request: str = "",
    target_branch: str = "",
    project: str = "",
) -> str:
    """일감을 큐에 등록하고 태스크마다 컨텍스트 매니페스트를 1회 수집한다.

    [중요] **저장소를 만지지 않는다.** 브랜치 생성·골조 커밋은 작업장(파일 소유자) 몫이다.
    골조는 텍스트로 실려 가고, 작업장이 그것을 파일로 쓴다 (§4.7).

    Args:
        title: 일감 제목
        target_repo: 대상 저장소 (작업장이 체크아웃해 쓸 것)
        specs_json: 태스크 명세 JSON 배열. **이미 클래스 단위로 쪼개진 것**을 넣는다(§4.5).
            각 항목: `{"stem": 필수, "classes": [...], "contracts": "동결 인터페이스",
            "skeleton": "골조 텍스트", "target_file": "", "header_file": "",
            "depends_on": [], "requires": ["ue5"], "priority": 0}`
        original_request: 사용자 원문 (비우면 title)
        target_branch: 통합 대상 브랜치
        project: 비우면 지금 마운트된 프로젝트
    """
    try:
        raw = json.loads(specs_json)
        if not isinstance(raw, list):
            raise RegisterError("specs_json 은 배열이어야 한다")
        specs = [TaskSpec(**s) for s in raw]
        paths = resolve(project)
        got = register_work(title, specs, paths=paths, target_repo=target_repo,
                            original_request=original_request, target_branch=target_branch)
    except (RegisterError, ConfigError, ValueError, TypeError) as e:
        return _fail(e)
    out = {
        "ok": got.ok,
        "work_id": got.work_id,
        "summary": got.summary(),
        "tasks": [
            {"stem": t.stem, "task_id": t.task_id, "error": t.error}
            for t in got.tasks
        ],
    }
    if got.ok and got.work_id:
        # `#798` ① — 등재와 대기를 한 입구로. 준비는 `ax-followup.timer` 가 하고, 이 명령은
        # 그 결과를 읽기만 하다 끝난다. 🔴 사실만 싣는다(명령형 없음) — 무엇을 하나는 스킬 몫이다.
        out["wait"] = _wait_command(got.work_id)
        out["wait_note"] = WAIT_NOTE
    return json.dumps(out, ensure_ascii=False)


# 대기 명령의 자리 — 이 서버가 도는 체크아웃(`master/projects/` 의 두 단계 위)과 그 venv.
# `AX_PROJECTS_ROOT` 는 서버가 받은 값을 그대로 싣는다(없으면 체크아웃). 마스터에서는 셋 다
# `/home/sim/ax-cluster` 다 — `ax-followup.service` 의 `--repo` 와 같아야 준비 기록 키가 맞는다.
_CODE_ROOT = Path(__file__).resolve().parents[2]
WAIT_NOTE = ("wait 는 이 work 의 지금 라운드 ⑦ 준비 결과(at_gate·stopped·error)나 work 종결"
             "(rejected·cancelled·merged)·타임아웃까지 큐와 준비 기록을 읽기만 하는 명령이다. "
             "준비는 ax-followup.timer 가 한다. 조회마다 stderr 에 한 줄, 끝나면 stdout 에 결과 "
             "블록을 남기고 종료한다 (종료 코드 0 at_gate · 3 멈춤·실패·종결 · 4 타임아웃).")


def _wait_command(work_id: str) -> str:
    import shlex
    try:
        root = str(projects_root())
    except ConfigError:
        root = str(_CODE_ROOT)
    repo = str(_CODE_ROOT)
    py = str(_CODE_ROOT / ".venv" / "bin" / "python")
    return (f"AX_PROJECTS_ROOT={shlex.quote(root)} {shlex.quote(py)} -m master.work.followup "
            f"{shlex.quote(work_id)} --wait --repo {shlex.quote(repo)}")


# ── 시소러스 (중 1.4) — [중요] **마스터는 사람에게 묻지 않는다. 물을 재료를 준다.** ─────────
#
# 작업 PC 의 Claude 가 이 도구로 대괄호 토큰을 먼저 조회하고, **미등록이면 사용자에게
# 묻는다.** 마스터가 입력을 기다리면 서비스가 멈춘다(§2 — 인프라지 작업장이 아니다).
#
#   Claude: resolve_terms(["몬스터", "미션시스템"])
#     → known: {"미션시스템": "AlphaManager_Mission"}
#     → unresolved: [{term:"몬스터", question:"…혹시 `AMonster`·`MonsterCharacter` 인가?"}]
#   Claude → 사용자에게 그 질문을 던진다
#   사용자 → "AMonster 맞아"
#   Claude: add_alias("AMonster", "몬스터")   → 다음 검색부터 자동 확장, 영구히 남는다

@mcp.tool()
def resolve_terms_tool(terms: list[str]) -> str:
    """`[대괄호]` 토큰이 시소러스에 있는지 조회하고, **없으면 후보를 붙여 돌려준다.**

    사용자에게 묻는 것은 **호출자(Claude)의 몫**이다 — `unresolved[].question` 을 그대로
    쓰면 된다. 후보는 클래스 그래프 실측과 검색 결과에서만 만든다(지어내지 않는다).
    """
    try:
        from ..context_search import thesaurus as th
        from ..context_search.paths import resolve as resolve_paths
        from ..context_search.search import open_search

        paths = resolve_paths("")
        try:
            searcher = open_search("")
        except Exception:                                # noqa: BLE001
            searcher = None                              # 색인이 없어도 별칭 조회는 된다
        r = th.resolve(paths, list(terms or []), searcher=searcher)
        return json.dumps({
            "ok": True,
            "project": paths.name,
            "known": r.known,
            "expansion": r.expansion,
            "needs_user": r.needs_user,
            "unresolved": [
                {"term": u.term,
                 "question": u.question,
                 "candidates": [{"class": c.class_name, "why": c.why, "file": c.file}
                                for c in u.candidates]}
                for u in r.unresolved
            ],
            "summary": r.summary,
        }, ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def add_alias_tool(class_name: str, term: str) -> str:
    """사용자가 확인해 준 별칭을 등록한다. **기존 별칭에 합친다 — 덮어쓰지 않는다.**

    [중요] 사용자가 **명시로 확인한 것만** 부를 것. 추측으로 등록하면 검색이 조용히 오염된다
    (원본 규약: silently auto-add 금지).
    """
    try:
        from ..context_search import thesaurus as th
        from ..context_search.paths import resolve as resolve_paths

        paths = resolve_paths("")
        status = th.register(paths, class_name, term)
        notes = {
            "added": "등록했다(온톨로지 yaml). 다음 검색부터 자동 확장된다",
            "added_unmeasured": "등록했다 — [주의] DF 를 잴 수 없어 범용어 판정은 못 했다",
            "added_side": "등록했다(폴백 저장소 — 그 클래스의 온톨로지 yaml 이 아직 없다). "
                          "다음 검색부터 자동 확장된다",
            "added_side_unmeasured": "등록했다(폴백 저장소) — [주의] DF 를 잴 수 없어 "
                                     "범용어 판정은 못 했다",
            "noop": "이미 등록돼 있다",
            "not_found": f"`{class_name}` 은 클래스 그래프에 없다 — 클래스명을 확인하라",
        }
        # rejected_short / rejected_generic 은 status 자체가 사유 문장을 담는다
        return json.dumps({
            "ok": status.startswith("added") or status == "noop",
            "status": status,
            "class": class_name,
            "term": term,
            "note": notes.get(status, status),
        }, ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def mark_not_a_class_tool(term: str) -> str:
    """사용자가 "그건 클래스가 아니다" 라고 답했을 때 기억한다. **다음부터 묻지 않는다.**

    [중요] 실측으로 필요해진 도구다 — `[완료]`·`[연출]` 같은 **상태·개념**은 대응 클래스가
    없는데 후보 생성기가 어휘상 가까운 무관한 클래스를 내민다. 기록하지 않으면 같은 말을
    매번 다시 묻게 되고, 그러면 사용자가 이 기능을 꺼 버린다.
    """
    try:
        from ..context_search import thesaurus as th
        from ..context_search.paths import resolve as resolve_paths

        paths = resolve_paths("")
        status = th.ignore(paths, term)
        return json.dumps({
            "ok": status != "not_found",
            "status": status,
            "term": term,
            "note": "다음부터 이 표현은 묻지 않는다" if status == "added" else "이미 기록돼 있다",
        }, ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def search_context_tool(query: str, limit: int = 8, *, task_type: str = "",
                        user_request: str | None = None, request_id: str = "",
                        session_id: str = "", work_id: str = "") -> str:
    """[중요] **검색 입구는 이것 하나다.** 대괄호 해석 → 시소러스 확장 → 검색을 한 번에 한다.

    작업장의 Claude 는 이 도구만 부르면 된다. 순서를 스스로 조립할 필요가 없다 —
    따로 두면 순서를 틀리거나 시소러스를 건너뛴다.

        query: "[미션시스템]에서 [완료]시 [연출] 부분이 어디야?"
          ① 대괄호 토큰 추출        → ["미션시스템","완료","연출"]
          ② 시소러스 조회           → known / unresolved(+후보)
          ③ 아는 별칭을 질의에 덧붙임 → "미션시스템 완료 연출 UAlphaManager_Mission"
          ④ 벡터+BM25 융합 검색

    사용자 명령으로 검색하면 task_type='user_command', user_request에는 실제 명령을
    요약하지 않고 그대로 넣는다. 같은 명령의 후속 검색에는 반환 request_id를 재사용한다.
    자동 리뷰 등은 task_type='automatic_review'처럼 작업을 분류하고 원문을 만들지 않는다.

    반환에 `ask` 가 있으면 **그 문장을 사용자에게 그대로 물어라.** 답을 받으면
    `add_alias_tool(클래스, 표현)` 으로 등록한다 — 다음 검색부터 자동 확장된다.
    클래스가 아니라고 하면 `mark_not_a_class_tool(표현)`.
    [중요] **대괄호는 클래스에만 쓴다** — 상태·개념(`[완료]`)에 쓰면 매번 되묻게 된다.

    등록은 **검색을 막지 않는다.** 모르는 별칭이 있어도 결과는 그대로 돌려준다 —
    사람을 기다리는 인프라를 만들지 않는다(§2).
    """
    # #837: user_request is the original command, never a paraphrase of query.
    # Native MCP callers supply it explicitly; only input hooks can mark it captured.
    from ..context_search import search_log
    with search_log.search_context(caller="mcp_direct", task_type=task_type or "unclassified",
                                   user_request=user_request,
                                   user_request_source="provided" if user_request is not None else "missing",
                                   request_id=request_id, session_id=session_id, work_id=work_id,
                                   llm_query=query):
        return _search_context(query, limit)


def _search_context(query: str, limit: int) -> str:
    paths = None
    searcher = None
    try:
        from ..context_search import thesaurus as th
        from ..context_search.paths import resolve as resolve_paths
        from ..context_search.search import focus, open_search

        paths = resolve_paths("")
        searcher = open_search("")
        terms = [t for t in focus(query).split() if t] if query else []
        bracketed = focus(query) != (query or "")

        res = th.resolve(paths, terms, searcher=searcher) if bracketed else th.Resolution()
        # ③ 아는 별칭을 덧붙인다 — 대괄호를 안 썼으면 원문 그대로 간다.
        q = " ".join([focus(query)] + res.expansion) if bracketed else query
        hits = searcher.search(q, limit=limit)

        # ⑤ [중요] **실증 로그** (소 3.4.5 · `#193`) — 원전도 MCP/HTTP **표면**에서 기록한다.
        #    기록하는 질의는 **받은 그대로**(`query`)다 — 원전 `combined_search` 가 확장 전
        #    파라미터를 넘기는 것과 같다. 기록 실패는 **검색을 막지 않는다**(fail-open)지만
        #    조용하지도 않다 — 응답의 `logged` 로 나간다.
        logged = getattr(searcher, "last_log_result", {"ok": False})

        return json.dumps({
            "ok": True,
            "project": paths.name,
            "query_used": q,
            "bracket_terms": terms if bracketed else [],
            "thesaurus": {
                "known": res.known,
                "expansion": res.expansion,
                "summary": res.summary,
            },
            # [중요] 사용자에게 물을 문장. 비어 있으면 물을 것이 없다.
            "ask": [u.question for u in res.unresolved],
            "unresolved_terms": [u.term for u in res.unresolved],
            "hits": [h.to_dict() for h in hits],
            # [주의] 기록이 실패하면 사유를 그대로 실어 보낸다 — 조용히 사라지지 않게.
            "logged": logged.get("ok", False),
            "search_id": logged.get("search_id"),
            "request_id": logged.get("request_id"),
            **({"log_error": logged.get("reason", "")} if not logged.get("ok") else {}),
        }, ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        if paths is not None and not getattr(searcher, "last_log_result", None):
            from ..context_search import search_log
            logged = search_log.log_search(paths, query=query, error=f"{type(e).__name__}: {e}")
            if not logged.get("ok"):
                import logging
                logging.getLogger(__name__).error("RAG log write failed: %s", logged.get("reason"))
        return _fail(e)


@mcp.tool()
def audit_context_tool(sample: int = 5, repair: bool = False) -> str:
    """트윈 문서(컨텍스트 MD) 건강 진단 — [중요] **읽기 전용이 기본, LLM 0** (소 3.4.1).

    원전 `audit_context_md` 이식. 8분류로 나눈다:

        valid · pence_wrapped · natural_prefix · shell_only · empty_summary
        no_frontmatter · dir_named · [중요] orphan_stem (대응 소스가 없는 좀비 문서)

    `repair=True` 를 주면 **LLM 0 으로 고칠 수 있는 것만**(펜스·자연어 도입부) 고친다.
    [중요] `dir_named`·`orphan_stem` 은 **절대 옮기지 않는다** — 트윈 문서를 이동하는 것은
    사람의 판단이다(`work/cleanup.py` 와 같은 결).

    [주의] 걷어낸 뒤 **다시 분류해서 나아지는 것만** 고친다 — 고쳐서 더 나빠지는 것을 막는다.
    """
    try:
        from ..context_search import context_audit as ca
        from ..context_search.paths import resolve as resolve_paths

        paths = resolve_paths("")
        result = ca.audit(paths.context, paths.repo)
        if result.get("error"):
            return json.dumps({"ok": False, "error": result["error"]}, ensure_ascii=False)

        payload = {
            "ok": True,
            "project": paths.name,
            "total": result["total"],
            "counts": {k: len(v) for k, v in result["categories"].items()},
            "unreadable": result["unreadable"][:sample],
            "samples": {k: v[:sample] for k, v in result["categories"].items()
                        if v and k != "valid"},
            "report": ca.format_report(result, sample_per_cat=sample),
        }
        plan = ca.plan_repair(paths.context, result)
        payload["repair_plan"] = {"fixable": len(plan["fixable"]),
                                  "refused": plan["refused"][:sample]}
        if repair:
            applied = ca.apply_repair(paths.context, plan)
            payload["repaired"] = {"fixed": len(applied["fixed"]),
                                   "failed": applied["failed"][:sample]}
        return json.dumps(payload, ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def analyze_search_log_tool(since: str = "", until: str = "", compare_at: str = "") -> str:
    """검색 로그 분석 리포트 — 채널 기여도·언어 갭·RRF k 튜닝 (소 3.4.2, **stdlib·LLM 0**).

    원전 `audit_tools.analyze_search_log` 이식. [중요] **표본이 30건 미만이면 판단을 보류**하고
    수치만 낸다 — 얇은 데이터로 채널 결론을 내리지 않는다.

    `compare_at` 에 날짜를 주면 그 시점 기준 **Pre/Post 두 창**으로 비교한다(색인·가중치를
    바꾼 뒤 효과를 보는 자리).
    """
    try:
        from ..context_search import search_log_analyzer as sla
        from ..context_search.paths import resolve as resolve_paths

        paths = resolve_paths("")
        return json.dumps({
            "ok": True,
            "project": paths.name,
            "log": str(paths.search_log),
            "report": sla.analyze(paths.search_log, since=since, until=until,
                                  compare_at=compare_at),
        }, ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def get_master_version_tool() -> str:
    """마스터의 정체 — [중요] **버전 핸드셰이크** (소 3.1.8, κ.9 계약 표면).

    원전 `get_server_version` 이식. 원전은 exe 빌드 번호를 냈지만 우리는 exe 를 안 만들므로
    **git 커밋**이 그 자리에 온다(같은 기제, 우리 신호원).

    무엇을 막나: ① 세 클론 드리프트 ② 배달 드리프트(작업장 번들이 어느 마스터에서 왔나)
    ③ 클라이언트 계약(`.33` 의 폴백 캐시가 호환되는 마스터와 말하나).

    [중요] **`contract` 는 커밋과 다르다** — 도구 표면이 바뀔 때만 올린다. 커밋마다 바뀌면
    소비자가 매 커밋에 불호환을 의심한다.
    [주의] 모르는 값은 빈 문자열 + 사유다 — `"unknown"` 을 넣으면 두 「모름」이 같다고 판정된다.
    """
    try:
        from ..context_search.paths import resolve as resolve_paths
        from ..version import identity

        try:
            paths = resolve_paths("")
        except Exception:                                # noqa: BLE001 — 마운트 없이도 답한다
            paths = None
        return json.dumps({"ok": True, **identity(paths=paths)}, ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


# ── 온톨로지 큐레이션 (소 1.3.1 · 1.3.2 · 1.3.6 · 1.3.7 · 1.3.9) ─────────────
#
# [중요] **전부 사람이 시켜야 부른다.** 자동 승급은 폐기됐다(2026-06-01 영구 비활성) — 도구가
# 스스로 개념을 만들거나 지우면 그 사고가 그대로 재현된다. 요청자의 Claude 는 사용자의
# 말을 받아 부르는 창구지 판단 주체가 아니다.

def _onto_paths():
    from ..context_search.paths import resolve as resolve_paths
    return resolve_paths("")


@mcp.tool()
def create_domain_tool(name: str, tags: list = [], parent: str = "",
                       summary: str = "") -> str:
    """새 도메인의 **씨앗 MD** 를 만든다 (패키지가 아니다 — 합성이 나중에 만든다).

    [중요] **덮지 않는다.** 이미 있으면 실패한다 — 고치려면 그 파일을 편집한다.
    [중요] 이름은 **영문 PascalCase** 다. 한글은 `tags` 와 별칭으로 넣는다(그쪽이 검색에 쓰인다).
    `status: draft` 로 시작하고, 활성화는 사람이 명시한다.
    """
    try:
        from ..ontology import create as oc
        r = oc.create(_onto_paths(), name, tags=list(tags or []), parent=parent,
                      summary=summary)
        return json.dumps({"ok": True, "domain": r.domain, "path": r.path,
                           "parent": r.parent, "linked": r.linked, "notes": r.notes,
                           "next": "그 MD 의 절(특히 `## 도메인 경계`)을 채운 뒤 "
                                   "`python -m master.ontology refresh` 로 합성한다"},
                          ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def get_layer_description_tool(domain: str, layer: int = 0) -> str:
    """도메인의 **레이어별 책임 서술** — *"이 레이어가 여기서 무엇을 책임지나"* (소 3.1.4).

    `layer` 를 0 으로 두면 있는 레이어를 전부 준다. 원전 대응:
    `GET /api/v1/ontology/description/<domain>/<layer>` + `get_layer_description`.

    [중요] **읽기 전용이고 생성하지 않는다.** 초안 생성은 재합성(full)이 하거나 사람이
    `python -m master.ontology describe` 로 부른다 — 조회가 LLM 을 태우면 안 된다.
    `verified`/`protected` 를 함께 주므로 소비자가 **사람이 손본 것인지** 알 수 있다.
    """
    try:
        from ..ontology import descriptions as dm
        paths = _onto_paths()
        root = paths.ontology / "domains" / domain
        if not root.is_dir():
            return json.dumps({"ok": False, "error": f"도메인이 없다: {domain}"},
                              ensure_ascii=False)
        layers = [int(layer)] if layer else [1, 2, 3]
        out = []
        for n in layers:
            got = dm.read(root / f"L{n}" / dm.FILENAME)
            if got:
                out.append({"layer": n, "body": got["body"],
                            "verified_by_user": got["verified_by_user"],
                            "protected": got["protected"], "created": got["created"]})
        return json.dumps({"ok": True, "domain": domain, "descriptions": out,
                           "note": ("서술이 없다 — 재합성(full) 또는 "
                                    "`python -m master.ontology describe` 가 만든다")
                                   if not out else ""}, ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def edit_domain_field_tool(domain: str, parent_domain: str = None, status: str = None,
                           tags: list = None, collaborates_with: list = None,
                           summary: str = None) -> str:
    """도메인 MD 를 **필드 단위**로 고친다 (#189 — 원전 edit_domain_field 이식).

    제공한 인자만 적용: parent_domain/status/tags 는 frontmatter, collaborates_with 는
    `## 협력 도메인`, summary 는 `## 시스템 개요`. parent_domain/tags/collaborates_with 는
    manifest 직접 패치 + 인덱스 재빌드(LLM 0), summary/status 는 MD-only.
    [중요] tags 는 통째 치환이다 — 치환으로 한글 태그가 사라지면 결과에 크게 표시된다
    (가중치 3.0 검색 채널). 기존 태그를 유지하려면 결과의 목록을 도로 합쳐 다시 불러라.
    """
    try:
        from ..ontology.edit_field import edit_domain_field
        r = edit_domain_field(_onto_paths(), domain, parent_domain=parent_domain,
                              status=status, tags=list(tags) if tags is not None else None,
                              collaborates_with=(list(collaborates_with)
                                                 if collaborates_with is not None else None),
                              summary=summary)
        return json.dumps(r, ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def edit_ontology_item_tool(domain: str, kind: str, name: str, patch: dict) -> str:
    """온톨로지 항목 하나를 고친다. [중요] **고치면 곧 검수 잠금이 걸린다.**

    `kind` 는 `objects`·`actions`·`invariants`. `patch` 는 **top-level 얕은 병합**이라
    중첩 값은 키 전체를 다시 넘겨야 한다. `name`·`layer` 는 파일 경로의 근거라 바꿀 수 없다.
    없는 항목은 **만들지 않고 실패**한다.
    """
    try:
        from ..ontology import edit as oe
        r = oe.edit(_onto_paths(), domain, kind, name, dict(patch or {}))
        return json.dumps({"ok": True, "summary": r.summary, "changed": r.changed,
                           "ignored": r.ignored, "locked": r.locked,
                           "note": " 이 항목은 이제 재합성이 덮지 않는다"},
                          ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def list_log_tags_tool(domain: str) -> str:
    """도메인의 실증 테스트용 로그 태그/CVar 매핑 조회 (#169, 원전 η.12.3 — read-only).

    사이드카 `log_categories.yaml` 가 SSOT — 로그 태그 문자열을 임의로 추측하지 말고
    이걸 본다. 뷰어의 invariant 목록에도 같은 매핑이 `log_tags` 로 자동 첨부된다.
    """
    try:
        from ..ontology import log_tags as lt
        return json.dumps(lt.list_impl(_onto_paths(), domain), ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def get_worker_mode_tool() -> str:
    """**워커 지휘자 모드**를 조회한다 (`#385`) — `lane` · `claude` · `codex`.

    [중요] 이것은 **워커에서 서브태스크를 수행·지휘하는 주체**를 고르는 값이고, 본문 작성
    레인(`codex`→`agy`→로컬)과는 **다른 층**이다. 지휘자가 그 레인에 위임하는 것이 아래 층이다.

    [주의] 마스터 **기계 전역** 값이라 프로젝트 태그가 없다 — 프로젝트별로 갈리는 값이 아니다.
    """
    try:
        from ..work import mode as wm
        m, src = wm.current()
        return json.dumps({"ok": True, "mode": m, "source": src,
                           "modes": list(wm.MODES), "describe": wm.describe(),
                           "state": wm.read_state()}, ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def set_worker_mode_tool(mode: str, why: str = "", by: str = "", work_id: str = "") -> str:
    """워커 지휘자 모드를 바꾼다 (`#385`). `mode` 는 `lane` · `claude` · `codex`.

    [중요] **기록이지 잠금이 아니다** — 호출부가 명시한 인자와 `AX_WORKER_MODE` 가 여전히
    이긴다. 재부팅은 넘는다(`~/.cache/ax-dispatch/mode.json`).

    [중요] **표면은 이 한 벌이다** — Claude 스킬과 Codex 스킬이 **같은 이 도구를 부른다**
    (사용자 정정 2026-09-08: *"MCP와 스킬은 양자택일이 아니야"*). 도구마다 로직을 따로
    구현하면 두 벌이 갈라진다.

    [주의] 모르는 값은 **거절한다** — 조용히 기본값으로 접지 않는다.

    `work_id` 를 주면 **그 work 하나만** 바꾼다(`#392` ② — 장애 대응, 다음 파견부터 적용,
    파견이 도는 중이면 거절). 비우면 종전대로 새 등재의 전역 기본값을 바꾼다.
    """
    # [DOC] #392 ②: work_id 가 비어 있지 않으면 `wc.set_work_worker_mode(work_id.strip(), mode, why, by)` 로 간다. ValueError 는 기존과 같은 `{"ok": False, "reason": …, "modes": …}` 모양으로 돌려준다.
    try:
        from ..work import conductor as wc
        if work_id.strip():
            got = wc.set_work_worker_mode(work_id.strip(), mode, why, by)
        else:
            got = wc.set_worker(mode, why=why, by=by)
        return json.dumps(got, ensure_ascii=False)
    except ValueError as e:
        return json.dumps({"ok": False, "reason": str(e),
                           "modes": list(__import__("master.work.mode",
                                                    fromlist=["MODES"]).MODES)},
                          ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def set_log_tag_tool(domain: str, tag: str, cvar: str,
                     related_invariants: list = None) -> str:
    """로그 태그/CVar 매핑 확정 기입 — tag 기준 upsert (#169).

    [중요] **저작 방향 (b) — 게임팀이 실제 코드에 CVar+태깅 로그를 구현한 뒤에만** 기입한다
    (원전 2026-07-12 확정, 자동 생성·자동 편입 없음). 제안 목록은
    `python -m master.ontology log-candidates` 리포트가 따로 만든다.
    """
    try:
        from ..ontology import log_tags as lt
        r = lt.set_impl(_onto_paths(), domain, tag, cvar,
                        related_invariants=(list(related_invariants)
                                            if related_invariants is not None else None))
        return json.dumps(r, ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def remove_log_tag_tool(domain: str, tag: str) -> str:
    """로그 태그 1건 삭제 (#169). [중요] 되돌릴 수 없다 — 지우기 전 사람에게 확정 표시."""
    try:
        from ..ontology import log_tags as lt
        return json.dumps(lt.remove_impl(_onto_paths(), domain, tag), ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def remove_ontology_item_tool(domain: str, kind: str, name: str,
                              force: bool = False) -> str:
    """온톨로지 항목 하나를 지운다. [중요] **검수 잠금이 걸린 것은 `force` 없이는 안 지운다.**

    잠금은 *"사람이 검수했다"* 는 뜻이다 — 재합성이 못 덮는 것을 삭제가 덮으면 안 된다.
    `force` 를 쓰기 전에 **사용자에게 한 번 더 확인**할 것.
    """
    try:
        from ..ontology import edit as oe
        r = oe.remove(_onto_paths(), domain, kind, name, force=bool(force))
        return json.dumps({"ok": r.removed, "summary": r.summary,
                           "was_locked": r.was_locked, "reason": r.reason},
                          ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def lock_ontology_item_tool(domain: str, kind: str, name: str,
                            locked: bool = True) -> str:
    """검수 잠금을 걸거나 푼다. [중요] **풀면 다음 재합성이 그 항목을 덮는다.**"""
    try:
        from ..ontology import edit as oe
        r = oe.set_lock(_onto_paths(), domain, kind, name, bool(locked))
        return json.dumps({"ok": True, "summary": r.summary, "locked": r.locked,
                           "note": r.note}, ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def list_locked_tool(domain: str = "") -> str:
    """지금 검수 잠금이 걸린 항목들. **무엇을 잠갔는지 못 보면 사람이 잊는다.**"""
    try:
        from ..ontology import edit as oe
        rows = oe.locked_items(_onto_paths(), domain)
        return json.dumps({"ok": True, "count": len(rows), "items": rows},
                          ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def unassigned_classes_tool(sample: int = 20) -> str:
    """어느 도메인에도 없는 클래스를 **보여준다. [중요] 자동 편입은 하지 않는다.**

    실측: 1,806개 중 배정된 것은 111(6%)뿐이라 평평한 목록은 쓸모가 없다. 그래서
    **인접**(배정된 클래스의 조상·자식·#include 이웃 — 어느 도메인에 왜 붙을지까지)과
    **고립**(어디에도 안 닿는 것, 규모 순 표본)으로 갈라 준다.
    고립이 대부분이면 그건 클래스가 하찮은 게 아니라 **도메인이 모자라다는 신호**다.
    """
    try:
        from ..ontology import unassigned as ou
        rep = ou.scan(_onto_paths(), sample=int(sample))
        return json.dumps({
            "ok": True, "summary": rep.summary,
            "total_classes": rep.total_classes, "assigned": rep.assigned,
            "adjacent": [{"name": a.name, "domain": a.domain, "why": a.why, "via": a.via}
                         for a in rep.adjacent[:int(sample)]],
            "adjacent_total": len(rep.adjacent),
            "isolated_sample": [{"name": n, "methods": m} for n, m in rep.isolated],
            "isolated_total": rep.isolated_total,
            "notes": rep.notes,
        }, ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def sync_ontology_tool(domain: str = "", apply: bool = False) -> str:
    """소스와 맞춘다 — 옮겨진 파일 경로, 선언 메서드. [중요] **기본은 계획만.**

    경로·선언은 *기계의 사실*이라 잠긴 항목에도 넣지만 **그 두 필드 말고는 안 건드린다.**
    그래프에 없는 클래스는 **지우지 않고 보고**한다(삭제됐는지 그래프가 낡았는지 모른다).
    """
    try:
        from ..ontology import sync as osync
        paths = _onto_paths()
        stats = ([osync.sync_domain(paths, domain, apply=bool(apply))] if domain
                 else osync.sync_all(paths, apply=bool(apply)))
        return json.dumps({
            "ok": True, "applied": bool(apply),
            "domains": [{"domain": s.domain, "summary": s.summary,
                         "path_fixed": s.path_fixed[:10], "missing": s.missing[:10],
                         "declared": len(s.declared_set)} for s in stats],
            "note": "" if apply else "[중요] 아무것도 쓰지 않았다. 반영하려면 apply=true",
        }, ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def protect_ontology_tool(domain: str = "", reason: str = "", kinds: list = [],
                          on: bool = True, apply: bool = False) -> str:
    """받아온 스냅샷처럼 **재생성으로 대체하면 안 되는** 항목을 일괄 표시한다. [중요] 기본은 계획만.

    [중요] **검수 잠금(`lock_ontology_item_tool`)과 다른 표식이다.** 뜻이 다르다 —
    잠금은 *"사람이 이 항목을 검수했다"*, 보호는 *"이 내용을 재생성으로 대체하지 않는다"*.
    247건에 잠금을 찍으면 나중에 **진짜로 검수한 것**을 구분할 수 없다.

    [중요] `reason` 이 필요하다(켤 때). 실측 근거: 로컬 레인 합성은 스냅샷보다 얕았고, `claude`
    레인도 깊이는 맞췄지만 **스냅샷 개념 5개 중 3개를 잃었다**(리포트 11 §20).
    [주의] **합성이 만든 것은 보호하지 말 것** — 개선돼야 한다. 보호는 *재생산 못 하는 것*에만.
    """
    try:
        from ..ontology import edit as oe
        r = oe.protect_all(_onto_paths(), domain=domain, kinds=tuple(kinds or ()),
                           reason=reason, on=bool(on), apply=bool(apply))
        return json.dumps({"ok": True, "summary": r.summary, "applied": r.applied,
                           "changed": len(r.changed), "already": r.already,
                           "base_commit": r.at,
                           "sample": [f"{d}/{k}/{n}" for d, k, n in r.changed[:10]],
                           "note": "" if apply else "[중요] 아무것도 쓰지 않았다. 반영하려면 apply=true"},
                          ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def list_protected_tool(domain: str = "") -> str:
    """무엇이 **왜, 어느 커밋 기준으로** 보호돼 있나. drift 를 볼 때 기준이 된다."""
    try:
        from ..ontology import edit as oe
        rows = oe.protected_items(_onto_paths(), domain)
        return json.dumps({"ok": True, "count": len(rows), "items": rows[:50]},
                          ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def drift_audit_tool(domain: str = "") -> str:
    """트윈과 소스가 **어긋난 곳**을 훑는다. [중요] **보고만 한다 — 아무것도 지우지 않는다.**

    [중요] 판정을 *"기준 커밋이 다르다"* 로 하지 않는다 — 커밋 하나만 지나도 전부 다르므로
    240건이 한꺼번에 떠서 아무도 안 본다. **그 사이 그 도메인의 근거 파일이 실제로 바뀌었나**
    로 좁힌다(bare 저장소 `git diff --name-only`, 읽기 전용).

    함께 모으는 것: 사실 게이트(유령 호출) · 그래프에서 사라진 클래스 · 경로 어긋남.
    [주의] **설계 규칙 서술**(호출 표기 없는 문장)은 자동으로 못 잡는다 — 그 경우 '소스 변경'이
    유일한 단서다. 무엇을 할지는 사람이 정한다: `edit` · `remove(force=true)` · 보호 해제 후 재합성.
    """
    try:
        from ..ontology import drift as dr
        rep = dr.audit(_onto_paths(), domain=domain)
        return json.dumps({
            "ok": True, "head": rep.head, "domains": len(rep.domains),
            "suspects": [{"domain": d.domain, "protected": d.protected,
                          "since": d.stale_since, "changed_files": d.changed_files[:10],
                          "ghosts": d.ghosts[:5], "missing": d.missing[:10],
                          "path_fixes": d.path_fixes} for d in rep.suspects],
            "notes": rep.notes,
            "report": rep.render(),
        }, ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def infer_domain_tool(query: str) -> str:
    """질의가 **어느 도메인 얘기인지** 결정적으로 짚는다 (LLM 0).

    [중요] `search_context_tool` 과 다르다 — 그쪽은 *닮은 것*을 통계로 찾고 언제나 뭔가 낸다.
    이 도구는 **질의에 나온 클래스의 소속을 표에서 읽고**, 근거를 댄다
    (*"`UMissionTaskExecutor` 가 MissionRuntime 소속"*). 한글 질의는 시소러스 별칭을 타고 간다.

    [중요] **모르면 빈 결과다.** 산문에서 도메인 이름을 닮은 말을 찾아 추측하지 않는다 —
    추측하면 "결정적" 이라는 이 도구의 유일한 값어치가 사라진다.
    """
    try:
        from ..context_search import infer as inf_mod
        r = inf_mod.infer_for(_onto_paths(), query)
        return json.dumps({
            "ok": r.ok, "domains": r.domains, "summary": r.summary,
            "evidence": [{"class": e.cls, "domain": e.domain, "via": e.via} for e in r.evidence],
            "unassigned_candidates": r.unknown, "notes": r.notes,
        }, ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def get_orchestration_tool() -> str:
    """마스터 마지막 담당 기록과 워커 모드를 조회한다. 실행 생존 판정은 아니다."""
    from ..work import conductor
    try:
        return json.dumps(conductor.snapshot(), ensure_ascii=False)
    except (ValueError, OSError) as exc:
        return _fail(exc)


@mcp.tool()
def record_master_conductor_tool(agent: str, why: str, by: str = "") -> str:
    """실제 인수 후 claude/codex 담당을 기록한다. 세션 실행·종료·잠금이 아니다."""
    from ..work import conductor
    try:
        return json.dumps(conductor.record_master(agent, why, by), ensure_ascii=False)
    except (ValueError, OSError) as exc:
        return _fail(exc)


# ── 플랜 영역 (`#826` T5) — 본체는 `master/plan_tools.py`. 상태는 plan_transition_tool 로만 바뀐다 ──

@mcp.tool()
def plan_start_tool(issue_id: int, project: str = "") -> str:
    """일감을 시작하기 **전에** 부른다 — 스펙·플랜 판정과 프로젝트 7단계 표(읽기 전용, `#826`).

    판정이 `ok: false` 면 구현으로 넘어가지 않는다. 특히 `plan_needed` 는 RAG·현재 소스 대조 뒤
    사용자와 플랜을 쓰고 `plan_set_tool` 로 등록하라는 뜻이다. `project` 를 비우면 마운트된 프로젝트.
    """
    from .. import plan_tools
    try:
        return json.dumps(plan_tools.start(issue_id, project=project), ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def plan_set_tool(issue_id: int, tasks: list[dict], why: str) -> str:
    """이슈 본문의 플랜 영역을 등록하거나 태스크를 추가·편집한다 (`#826`).

    `tasks` 는 원하는 **전체 목록**(표 순서): 항목마다 `id`·`goal` 필수, `target`·`deps`·`check`·
    `steps`(이 태스크가 하는 조건부 단계 번호, 예 `[2, 6]` — 형식 v2) 선택.
    [중요] `state`·`evidence` 는 받지 않는다 — 새 태스크는 「대기」, 기존 태스크는 본문 값 유지.
    시작된 태스크는 뺄 수 없다. `why` 는 노트로 남는다(필수).
    """
    from .. import plan_tools
    try:
        return json.dumps(plan_tools.set_plan(issue_id, tasks, why), ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def plan_transition_tool(issue_id: int, task_id: str, to: str, note: str = "") -> str:
    """플랜 태스크 하나의 상태를 바꾼다 (`#826`) — 상태를 바꾸는 **유일한** 쓰기.

    `to`: 작업중 · 완료 · 차단 · 해당없음 · 대기. 완료는 근거(커밋 해시·검사 결과), 차단·해당없음은
    사유가 `note` 에 필수다. 선행이 안 끝났거나 허용되지 않는 전이는 거절된다. 응답의 `next` 가
    다음 판정이다.
    """
    from .. import plan_tools
    try:
        return json.dumps(plan_tools.transition(issue_id, task_id, to, note), ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


# ── 일감 작업 흐름 (`#879` T5) — 본체는 `master/issue_flow.py` ─────────────────────────────

@mcp.tool()
def issue_start_tool(issue_id: int) -> str:
    """일감 작업을 **시작**한다 (`#879`) — 구현에 손대기 전에 부른다.

    `plan_start` 판정이 ok가 아니면 거절한다(플랜 강제). 작업 repo는 기존 설정으로 결정한다.
    AXCluster/config.yaml의 track.local_clone을 기존 ProjectPaths.repo를 통해 읽는다.
    설정 repo의 깨끗한 main=origin/main을 기준으로 issue/<N>을 만들고 시작 리비전을 기록한다.
    응답 repo가 편집·커밋 위치다. 운영 서비스의 소스 위치에서 작업 경로를 추정하지 않는다.
    """
    from .. import issue_flow
    try:
        return json.dumps(issue_flow.start(issue_id), ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def issue_finish_tool(issue_id: int, confirm: bool = False) -> str:
    """일감 작업을 **마친다** (`#879`). [중요] `confirm=False`(기본)는 범위·커밋 목록만 보여 주고 아무것도
    바꾸지 않는다 — 사용자 승인을 받은 뒤에만 `confirm=True`.

    설정된 작업 저장소의 로컬 `issue/<N>` 커밋을 승인 후 main에 반영하고 브랜치를 정리한다.
    운영 서비스 배포·재기동은 별도 승인이다. 기존 remote·쓰기 가드는 우회하지 않는다.
    마감 추적 등록(`issue_track` · 범위의 해시 전부) → 색인기 리뷰 연결 → 일감 잠금 해제(**등록이 성공했을
    때만**) → Redmine 「리뷰 요청」 노트 + **「완료」·100 닫기**(등록 성공 시 — `#889`, main 적용 = 마감).
    범위 리뷰를 직접 등재하지 않는다 — 해시별 커밋 리뷰가 끝날 때마다 진행 노트가, 모두 끝나면 종합 리뷰
    1회의 결과가 같은 일감에 노트로만 남는다(닫힌 뒤에도). 등록이 실패하면 잠금이 남고 일감은 열린 채다.
    실패 단계는 `why`, 끝난 단계는 `done`, 닫혔는지는 `closed` 다.
    `.33` 요청자는 같은 기록을 `ax-client` 의 `issue_finish`(8101)로 한다(`ax-issue` 스킬).
    """
    from .. import issue_flow
    try:
        return json.dumps(issue_flow.finish(issue_id, confirm=confirm), ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def issue_pause_tool(issue_id: int) -> str:
    """진행 중인 일감을 **보류**한다 (`#883`) — 일감 잠금을 풀고 `issue/<N>` 브랜치는 남긴다.

    설정된 작업 저장소의 `issue/<N>`이 깨끗해야 한다(미커밋 변경은 거절). 잠금을 보류로
    옮기고 같은 저장소의 main으로 돌아간 뒤 노트를 남긴다. 재개는 `issue_start_tool(N)`이다.
    """
    from .. import issue_flow
    try:
        return json.dumps(issue_flow.pause(issue_id), ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)


@mcp.tool()
def issue_cancel_tool(issue_id: int, confirm: bool = False, delete_branch: bool = False) -> str:
    """일감 작업을 **취소**한다 (`#883`). [중요] `confirm=False`(기본)는 잠금 상태·브랜치·
    로컬에만 있는 커밋 목록만 보여 주고 아무것도 바꾸지 않는다 — 사용자 승인 뒤에만 `confirm=True`.

    설정된 작업 저장소에서 승인 시 main 복귀 → 잠금 해제 → Redmine 「취소」 노트(커밋 목록).
    브랜치는 기본으로 남긴다. `delete_branch=True`일 때만 `git branch -D` — 로컬 전용 커밋은
    되살릴 수 없으므로 그 목록을 사용자에게 보여 주고 삭제 승인을 따로 받는다.
    """
    from .. import issue_flow
    try:
        return json.dumps(issue_flow.cancel(issue_id, confirm=confirm, delete_branch=delete_branch),
                          ensure_ascii=False)
    except Exception as e:                               # noqa: BLE001
        return _fail(e)
