"""프로젝트 등록·전환 MCP 서버 — 대화형으로 처리하기 위해 외부로 노출한다 (PLAN §5.5).

노출 도구:
  · register_project — 디지털 트윈을 생성할 프로젝트를 등록한다(설정 파일 생성부터)
  · set_active       — 가리키는 프로젝트를 바꾼다
  · register_work    — 작업장이 일감을 등록한다 (§4.7 복구 ①)
  · get_manifest     — 작업장이 컨텍스트 매니페스트를 받아 간다 (§4.2)
  · get_code         — 🔴 생성 + 층2 를 거친 **코드 뭉치**를 받아 간다 (§4.2 ②③④)

⚠️ 이 서버가 프로젝트 레지스트리를 넘어 **작업장의 단일 창구**가 되고 있다. 의도된 통합이다 —
작업장이 엔드포인트를 여러 개 물게 하는 것보다 낫다. 다만 더 커지면 쪼갤 것.

읽기용(부수): list_projects · check_registry

🔴 **인증 필수** — `task_queue`(8101)·브로커(8102) 와 같은 베어러 토큰을 쓴다
(`master/auth.py`, 2026-08-08). 토큰이 없으면 **서비스가 뜨지 않는다**(fail-closed).
방화벽(LAN 한정)은 그와 **별개의 두 번째 층**이다 —
`ufw allow from 192.168.0.0/24 to any port 8103` 을 `Anywhere` 로 넓히지 말 것.

🔴 **작업 등록은 저장소를 만지지 않는다.** 브랜치 생성·골조 커밋은 작업장 몫이다(§4.7).
여기서 하는 것은 큐 등록과 매니페스트 수집뿐이다.

⚠️ 설치된 SDK 는 `mcp` 2.0.0 이라 `mcp.server.fastmcp` 가 **없다**
(`task_queue/mcp_server.py` 는 아직 그 경로를 쓰고 있어 stdio 모드가 깨져 있다).
2.0.0 의 고수준 API 는 `mcp.server.MCPServer` 다.
"""
from __future__ import annotations

import json

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
from .config import Registry
from .workshop_check import check_project_workshops
from ..context_search.paths import resolve
from ..work import manifest as _mf
from ..work.generate import GenerateError, dispatch
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
def set_active_tool(name: str) -> str:
    """가리키는 프로젝트를 바꾼다. 디렉토리는 전부 남고 마운트 대상만 바뀐다."""
    try:
        return json.dumps(set_active(name), ensure_ascii=False)
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
    note: str = "",
) -> str:
    """작업장 한 대의 UE5 체크아웃 위치를 등록·갱신한다 (PLAN §5.5.4).

    마스터는 이 경로를 **읽지도 쓰지도 않는다** — 어디로 작업을 보낼지 정하는
    라우팅 정보다.

    host:   작업장 IP 또는 호스트명 (예: 192.168.0.2).
    driven: 'ssh' = 마스터가 밀어넣을 수 있다 / 'interactive' = 사람이 앉아서 한다.
            'ssh' 를 고르면 path 와 user 가 반드시 있어야 한다.
    path:   그 머신의 프로젝트 경로. 윈도우는 역슬래시 그대로 (예: E:\\trunk\\ModularStage).
    """
    try:
        return json.dumps(
            set_workshop(name, host, driven=driven, path=path, user=user, note=note),
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
def check_workshops_clean_tool(name: str = "") -> str:
    """작업을 보내기 전에 워크숍 체크아웃이 안전한지 확인한다 (PLAN §5.5.4-⑥-1).

    자동화는 브랜치를 바꾸고 리셋한다 — 사람이 커밋하지 않은 작업이 있으면 날아간다.
    **추적 파일에 변경이 있으면 차단**하고, **미추적(`??`)은 통과**시킨다
    (checkout/reset 이 지우지 않기 때문).

    🔴 검사하지 못하면(SSH 실패·타임아웃·저장소 아님) **통과가 아니라 차단**이다.
    🔴 이 도구는 판정만 한다. 정리하지 않으며, `git clean` 은 절대 부르면 안 된다.

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

    🔴 **저장소를 만지지 않는다.** 브랜치 생성·골조 커밋은 작업장(파일 소유자) 몫이다.
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
    return json.dumps({
        "ok": got.ok,
        "work_id": got.work_id,
        "summary": got.summary(),
        "tasks": [
            {"stem": t.stem, "task_id": t.task_id, "manifest": t.manifest_path,
             "hits": t.manifest_hits, "degraded": t.manifest_degraded, "error": t.error}
            for t in got.tasks
        ],
    }, ensure_ascii=False)


@mcp.tool()
def get_manifest(task_id: str, project: str = "") -> str:
    """태스크의 컨텍스트 매니페스트를 반환한다.

    🔴 **작업장은 이것을 읽고 작업한다 — 재검색할 필요가 없다.** 마스터가 등록 시 1회
    수집해 둔 것이고, 로컬 LLM(도구 호출 불가)도 이 텍스트로 grounding 을 받는다 (§4.2).

    없으면 `ok:false` 다 — 빈 매니페스트와 구분된다.
    """
    try:
        paths = resolve(project)
        body = _mf.read(paths, task_id)
    except ConfigError as e:
        return _fail(e)
    if body is None:
        return json.dumps({
            "ok": False, "task_id": task_id,
            "error": f"매니페스트가 없다: {_mf.manifest_path(paths, task_id)}",
        }, ensure_ascii=False)
    return json.dumps({"ok": True, "task_id": task_id, "project": paths.name,
                       "manifest": body}, ensure_ascii=False)


@mcp.tool()
def get_code(task_id: str, instruction: str, target_file: str = "",
             project: str = "") -> str:
    """태스크의 코드를 생성해 **층2 검사를 통과시킨 뒤** 돌려준다 (§4.2 ②③④).

    🔴 **`ok` 가 false 면 코드를 적용하지 말 것.** 층2(상용 모델 문법·API 검사)를 못 넘었거나
    생성이 실패한 상태다. 코드를 함께 돌려주는 것은 진단용이지 쓰라는 뜻이 아니다.

    마스터의 역할은 여기서 끝난다 — **파일 적용·빌드·테스트·커밋은 작업장 몫이다.**
    층3(UE5 빌드 + RunTests)이 최종 권위이고, 층2 는 그 호출 횟수를 줄이는 선제 필터다.

    Args:
        task_id: `register_work` 가 돌려준 태스크 id (매니페스트가 있어야 한다)
        instruction: 무엇을 구현할지. 골조·계약·RAG 는 매니페스트가 이미 싣고 있다
        target_file: 대상 파일 경로 (층2 프롬프트와 진단에 쓰인다)
        project: 비우면 지금 마운트된 프로젝트
    """
    try:
        paths = resolve(project)
        d = dispatch(paths, task_id, instruction=instruction, target_file=target_file)
    except (ConfigError, GenerateError) as e:
        return _fail(e)
    v = d.verdict
    return json.dumps({
        "ok": d.ok,
        "task_id": task_id,
        "summary": d.summary(),
        "code": d.code,
        "notes": d.notes,
        "error": d.error,
        "verdict": None if v is None else {
            "approved": v.approved,
            "failure": v.failure,      # None 이면 모델이 실제 판정을 냈다는 뜻
            "findings": v.findings,
            "backend": next((w for w in v.warnings if w.startswith("backend=")), ""),
        },
    }, ensure_ascii=False)
