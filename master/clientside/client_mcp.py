"""클라이언트 MCP — 원전 `context_search` 클라 모드의 이식 (소 3.8.3 · `#201`).

원전 구조: 팀원 PC 에서 MCP 프로세스가 로컬로 돌고, 실 데이터는 서버 HTTP 에 위임한다.
우리 구조도 같다 — 이 파일이 `.33` 에서 stdio MCP 로 돌고, 마스터 큐(8101)에 위임한다.

## [중요] 이 파일은 단일 파일이고 패키지 내부 import 가 없다 — 우연이 아니다

`.mcp.json` 이 이것을 **스크립트로**(`py .ax/lib/axmaster/clientside/client_mcp.py`) 실행하는데,
스크립트 모드에는 패키지 문맥이 없어 상대 import 가 죽는다. 배달 때문에 소스에 try/except
이중 import 를 심는 것은 이 저장소가 거부한 방식이다(`review.py` 이식 때의 결정) — 그래서
**stdlib 만 쓰고 아무것도 import 하지 않는 단일 파일**로 만든다. 클라이언트에 pip 이 없다는
전제와도 맞는다(실측: `.33` 은 py 3.12 뿐).

## [중요] 도구는 조회 + redmine 코멘트뿐이다 — 결정(PATCH)은 없다

반려·승인은 배달된 `axmaster.work.review` 가 이미 검증된 절차(통째 중단·`confirm=False`
기본·push 후에만 merged)로 한다. MCP 에 decide 도구를 또 만들면 **로직이 두 벌**이 되고,
MCP 쪽이 절차(예: push 전에 merged 로 찍기)를 우회하는 길이 된다. 대신 `queue_api()` 를
내보낸다 — 스킬이 `review.reject_work(api=queue_api())` 식으로 주입한다.

## [중요] 캐시는 참조 지식에만 — 큐 상태에는 없다

    참조 지식 (검색·온톨로지)   미연결 시 마지막 정상 응답을 `_stale` 표기로 내준다 (#162 배선)
    라이브 상태 (works/tasks)  캐시 금지 — 낡은 `merge_status` 위에서 검수가 결정하게 된다.
                              미연결이면 **명확한 오류**가 답이다 (원전 wiki_disconnected_error)

캐시 모듈(`ontology_cache.py`)은 **옆 파일을 경로로 로드**한다(`_load_cache`) — 패키지 이름에
기대지 않아 저장소(`master.clientside`)와 배달본(`axmaster.clientside`) **두 집 문제**가 없고
스크립트 모드 제약도 지킨다. 로드가 실패하면 캐시만 꺼지고 도구는 계속 돈다(사유는 stderr).

## [중요] 역할 게이팅 — 원전 wiki_mode 의 대응물

이 MCP 가 노출하는 도구는 전부 **읽기 + redmine 코멘트**다. mutation(온톨로지 편집·도메인
생성·큐 조작)은 등록 자체가 없다 — 원전이 wiki_mode 에서 mutation 도구를 아예 등록하지 않은
것과 같은 방식이고, 스크러빙보다 강하다.

## 설정과 자격

    ./.ax/config.json   master.host · master.services.task_queue   (마스터가 배달)
    ./.ax/token         requester 역할 토큰 (0600, 마스터가 배달)

둘 다 **cwd 기준 고정 경로**다 — Claude Code 가 `.mcp.json` 이 있는 체크아웃 루트를 cwd 로
MCP 를 띄우는 규약에 기댄다(`.ax/` 를 cwd 고정으로 둔 기존 결정과 같은 근거).
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "ax-client", "version": "1.0"}
HTTP_TIMEOUT = 30

CONFIG_REL = Path(".ax/config.json")
TOKEN_REL = Path(".ax/token")


_CACHE = None          # None=미시도 · False=실패(재시도 안 함 — 원전 규약) · 객체=사용 가능


def _load_cache():
    """옆 파일 `ontology_cache.py` 를 **파일 경로로** 로드한다.

    [중요] 패키지 import 를 쓰지 않는 이유: 이 파일은 저장소에선 `master.clientside`,
    배달본에선 `axmaster.clientside` 로 **집이 둘**이고, 스크립트 모드에는 패키지 문맥이
    아예 없다. 파일 상대 로드는 세 경우 모두에서 같은 한 가지로 동작한다.
    """
    global _CACHE
    if _CACHE is not None:
        return _CACHE or None
    try:
        import importlib.util
        src = Path(__file__).with_name("ontology_cache.py")
        spec = importlib.util.spec_from_file_location("ax_ontology_cache", src)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _CACHE = mod.OntologyCache(Path.cwd() / ".ax")
    except Exception as e:                                   # noqa: BLE001
        print(f"[ax-client] 참조 캐시 비활성 (도구는 계속 돈다): {e}", file=sys.stderr)
        _CACHE = False
        return None
    return _CACHE


class ClientError(RuntimeError):
    """사람이 읽고 조치할 수 있는 오류. [중요] 조용한 빈 결과 대신 이것을 던진다."""


# ─────────────────────────────────────────────────────────────
# 설정·자격 — cwd 고정, 없으면 무엇을 어디서 찾았는지 말한다
# ─────────────────────────────────────────────────────────────

def load_config(root: Path | None = None) -> dict:
    p = (root or Path.cwd()) / CONFIG_REL
    if not p.is_file():
        raise ClientError(
            f"[미구성] {p} 이 없다 — 이 MCP 는 체크아웃 루트(cwd)에서 돌아야 한다. "
            "마스터에서 재배달: python -m master.client deliver")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ClientError(f"[미구성] {p} 을 읽지 못했다: {e}") from e


def load_token(root: Path | None = None) -> str:
    p = (root or Path.cwd()) / TOKEN_REL
    if not p.is_file():
        raise ClientError(
            f"[미구성] 역할 토큰({p})이 없다 — 마스터에서 재배달: python -m master.client deliver")
    tok = p.read_text(encoding="utf-8").strip()
    if not tok:
        raise ClientError(f"[미구성] 역할 토큰({p})이 비어 있다")
    return tok


def queue_url(cfg: dict) -> str:
    m = cfg.get("master") or {}
    host = m.get("host") or ""
    port = (m.get("services") or {}).get("task_queue")
    if not host or not port:
        raise ClientError("[미구성] config 의 master.host / services.task_queue 가 비어 있다")
    return f"http://{host}:{port}"


# ─────────────────────────────────────────────────────────────
# 큐 호출 — 실패 모드마다 다른 문장. 401/403 구분이 배선 오진을 막는다
# ─────────────────────────────────────────────────────────────

def _call(method: str, url: str, token: str, payload=None) -> dict | list:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as r:
            body = r.read().decode("utf-8", "replace").strip()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise ClientError(
                "[자격] 토큰이 거부됐다(401) — .ax/token 이 마스터의 requester 토큰과 다르다. "
                "마스터에서 재배달: python -m master.client deliver") from e
        if e.code == 403:
            raise ClientError(
                f"[스코프] requester 토큰으로는 이 경로를 열 수 없다(403): {method} {url} — "
                "검수 흐름 밖의 조작이다. 필요하면 마스터에서 직접 할 것") from e
        detail = e.read().decode("utf-8", "replace")[:300]
        raise ClientError(f"[서버] {method} {url} → {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        # [중요] 원전 wiki_disconnected_error 패턴 — 조용한 빈 결과 금지, 조치 순서를 준다
        raise ClientError(
            f"[미연결] 마스터({url})에 연결할 수 없다: {e.reason}\n"
            "  1) 마스터에서 ax-task-queue 가 떠 있는가 (systemctl status ax-task-queue)\n"
            "  2) 이 PC 가 LAN(192.168.0.x)에 있는가\n"
            "  3) .ax/config.json 의 master 주소가 맞는가") from e


def projects_url(cfg: dict) -> str:
    m = cfg.get("master") or {}
    host = m.get("host") or ""
    port = (m.get("services") or {}).get("projects")
    if not host or not port:
        raise ClientError("[미구성] config 의 master.host / services.projects 가 비어 있다")
    return f"http://{host}:{port}"


def projects_api(root: Path | None = None):
    """8103 읽기 표면 호출자. [중요] **토큰이 없다** — 이 표면은 읽기 전용 공개(ufw LAN 한정)다.
    (사용자 결정 2026-08-13: *"그냥 있는거 보여주는 뷰어"* — 조작 경로가 아니다.)"""
    cfg = load_config(root)
    base = projects_url(cfg)

    def api(method: str, path: str, payload=None):
        return _call(method, base + path, "", payload)

    return api


def cached_fetch(cache, key: str, fetch):
    """참조 지식 읽기 한 번 — 성공은 적재, [미연결] 은 마지막 정상 응답으로 폴백.

    [중요] 폴백은 `_stale`·`_cached_at` 표기가 주입된 채 나간다(#162 계약) — 표기 없이 내주면
    마스터가 죽은 것을 아무도 모른다. 캐시에도 없으면 원래의 [미연결] 오류가 그대로 나간다.
    """
    try:
        got = fetch()
    except ClientError as e:
        if "[미연결]" in str(e) and cache is not None:
            stale = cache.get_stale(key)
            if stale:
                out = json.loads(stale)
                out["_note"] = str(e).splitlines()[0]
                return out
        raise
    if cache is not None and isinstance(got, (dict, list)):
        cache.put(key, json.dumps(got, ensure_ascii=False))
    return got


def queue_api(root: Path | None = None):
    """`review.reject_work(api=…)` / `finalize_work(api=…)` 에 꽂을 호출자.

    [중요] 결정이 이 경로로만 가게 하는 것이 이 함수의 존재 이유다 — 절차는 review 모듈에
    한 벌만 있다.
    """
    cfg = load_config(root)
    base = queue_url(cfg)
    tok = load_token(root)

    def api(method: str, path: str, payload=None):
        return _call(method, base + path, tok, payload)

    return api


# ─────────────────────────────────────────────────────────────
# 도구
# ─────────────────────────────────────────────────────────────

def tool_list_works(api, status: str = "") -> dict:
    got = api("GET", "/api/v1/works")
    works = got if isinstance(got, list) else (got.get("works") or [])
    if status:
        works = [w for w in works if w.get("merge_status") == status]
    slim = [{"work_id": w.get("work_id"), "title": w.get("title"),
             "merge_status": w.get("merge_status"), "target_branch": w.get("target_branch"),
             "total": w.get("total"), "created": w.get("created")} for w in works]
    return {"count": len(slim), "works": slim}


def tool_get_work(api, work_id: str) -> dict:
    if not (work_id or "").strip():
        raise ClientError("work_id 가 비었다")
    # [중요] URL 인코딩 — 비ASCII·공백이 든 id 가 그대로 URL 에 들어가면 urllib 이
    # 조치 문장 없는 내부 오류로 죽는다 (.33 첫 실 왕복이 잡은 실결함, 2026-08-16).
    got = api("GET", f"/api/v1/works/{urllib.parse.quote(work_id.strip(), safe='')}")
    # 검수에 필요한 그대로 — review.review_work(work=…, tasks=…) 에 바로 넣는 모양
    return {"work": got.get("work") or {}, "tasks": got.get("tasks") or []}


def tool_redmine_note(api, issue_id: int, notes: str, status_name: str = "",
                      done_ratio=None) -> dict:
    payload = {"issue_id": int(issue_id), "notes": notes or ""}
    if status_name:
        payload["status_name"] = status_name
    if done_ratio is not None:
        payload["done_ratio"] = int(done_ratio)
    return api("POST", "/api/v1/redmine/note", payload)


def tool_log_writer_signal(api, args: dict) -> dict:
    """code-writer 신호 적재 (#206) — 원전 `log_writer_signal` 의 클라 자리.

    신호 파일은 마스터의 트윈 디렉토리에 있으므로 본문만 만들어 마스터에 보낸다
    (redmine_note 와 같은 대행 구조). [중요] 저장 대상은 코드가 아니라 **작업 과정**이다.
    """
    intent = str(args.get("intent") or "").strip()
    if not intent:
        raise ClientError("intent 가 비었다 — 작업 의도 한 줄이 신호의 축이다")
    payload = {"intent": intent}
    for k in ("queries", "files_read", "files_modified",
              "rejected_approaches", "error_recoveries"):
        if args.get(k):
            payload[k] = list(args[k])
    if args.get("iterations"):
        payload["iterations"] = int(args["iterations"])
    for k in ("feedback_notes", "session_id", "work_id"):
        if str(args.get(k) or "").strip():
            payload[k] = str(args[k]).strip()
    return api("POST", "/api/v1/signals", payload)


def tool_log_history(api, args: dict) -> dict:
    """작업 기록 적재 (#207) — 원전 α′ 규약의 클라 자리 (마스터 대행)."""
    title = str(args.get("title") or "").strip()
    if not title:
        raise ClientError("title 이 비었다 — 무엇을 결정했는지가 기록의 축이다")
    payload = {"title": title}
    for k in ("decision_type", "body", "work_id", "session_id",
              "supersedes", "user_quote"):
        if str(args.get(k) or "").strip():
            payload[k] = str(args[k]).strip()
    for k in ("affected_classes", "affected_domains", "alternatives_considered", "tags"):
        if args.get(k):
            payload[k] = list(args[k])
    return api("POST", "/api/v1/history", payload)


def tool_search_context(papi, query: str, tags=None, n: int = 5, *, cache=None) -> dict:
    """통합 검색 — 8103 의 원전 라우트(`/api/v1/search/combined`) 프록시. 참조 지식이라
    [미연결] 시 마지막 정상 응답으로 폴백한다(`_stale` 표기)."""
    if not (query or "").strip():
        raise ClientError("query 가 비었다")
    payload = {"query": query.strip(), "n": max(1, int(n))}
    if tags:
        payload["tags"] = list(tags)
    key = "search/combined?" + json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return cached_fetch(cache, key,
                        lambda: papi("POST", "/api/v1/search/combined", payload))


def tool_list_domains(papi, *, cache=None) -> dict:
    got = cached_fetch(cache, "ontology/domains",
                       lambda: papi("GET", "/api/v1/ontology/domains"))
    return got if isinstance(got, dict) else {"domains": got}


def tool_get_domain(papi, name: str, *, cache=None) -> dict:
    if not (name or "").strip():
        raise ClientError("도메인 이름이 비었다")
    q = urllib.parse.quote(name.strip(), safe="")
    return cached_fetch(cache, f"domains/{q}",
                        lambda: papi("GET", f"/api/v1/domains/{q}"))


TOOLS = [
    {"name": "list_works",
     "description": "큐의 work 목록 (검수 대상 파악). status 로 거를 수 있다 — "
                    "검수 대상은 보통 ready_for_review.",
     "inputSchema": {"type": "object",
                     "properties": {"status": {"type": "string",
                                               "description": "merge_status 필터 (옵션)"}}}},
    {"name": "get_work",
     "description": "work 하나의 메타와 tasks 전체. 반환 그대로 review.review_work 의 "
                    "work=/tasks= 인자에 넣는 모양이다.",
     "inputSchema": {"type": "object", "required": ["work_id"],
                     "properties": {"work_id": {"type": "string"}}}},
    {"name": "search_context",
     "description": "마스터 RAG 통합 검색 (읽기 전용 · 한국어 질의 가능). 마스터 미연결이면 "
                    "마지막 정상 응답을 _stale 표기로 준다 — _stale 이 보이면 낡은 값이다.",
     "inputSchema": {"type": "object", "required": ["query"],
                     "properties": {"query": {"type": "string"},
                                    "tags": {"type": "array", "items": {"type": "string"}},
                                    "n": {"type": "integer", "description": "결과 수 (기본 5)"}}}},
    {"name": "list_domains",
     "description": "온톨로지 도메인 카탈로그 (읽기 전용 · _stale 폴백 있음).",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "get_domain",
     "description": "도메인 상세 (읽기 전용 · _stale 폴백 있음).",
     "inputSchema": {"type": "object", "required": ["name"],
                     "properties": {"name": {"type": "string"}}}},
    {"name": "redmine_note",
     "description": "레드마인 이슈에 코멘트를 남긴다 (마스터 경유 — 키는 이 PC 에 없다). "
                    "상태 이름은 실재하는 것만: 신규·진행·해결·검토·완료. "
                    "완료로 닫는 것은 사람의 판단이다.",
     "inputSchema": {"type": "object", "required": ["issue_id", "notes"],
                     "properties": {"issue_id": {"type": "integer"},
                                    "notes": {"type": "string"},
                                    "status_name": {"type": "string"},
                                    "done_ratio": {"type": "integer"}}}},
    {"name": "log_writer_signal",
     "description": "코드 작성 작업 1건의 **과정**을 마스터에 적재한다 (되먹임 원료 — 코드가 "
                    "아니라 과정이다). 작업 종료 직전, 사용자 최종 승인 후에 호출한다 — "
                    "누락되면 이 작업의 패턴은 학습되지 않는다. 한국어 서술 속 코드 식별자는 "
                    "[대괄호]로 감싼다: 예) \"미션 매니저[Manager_Mission]에 태스크 추가\".",
     "inputSchema": {"type": "object", "required": ["intent"],
                     "properties": {
                         "intent": {"type": "string",
                                    "description": "작업 의도 한 줄 요약"},
                         "queries": {"type": "array", "items": {"type": "string"},
                                     "description": "이 작업에서 쓴 RAG 검색 쿼리"},
                         "files_read": {"type": "array", "items": {"type": "string"},
                                        "description": "직접 읽은 소스 경로 (프로젝트 상대)"},
                         "files_modified": {"type": "array",
                                            "description": "[{path, summary}] — 고친/만든 파일과 한 줄 요약"},
                         "iterations": {"type": "integer",
                                        "description": "계획→피드백 라운드 수 (1=원샷)"},
                         "feedback_notes": {"type": "string",
                                            "description": "사용자 피드백이 결과를 어떻게 바꿨나 2-3줄. 단순 승인이면 빈 값"},
                         "rejected_approaches": {"type": "array",
                                                 "description": "[{approach, reason}] — 사용자가 거절한 접근"},
                         "error_recoveries": {"type": "array",
                                              "description": "[{error: 증상, fix: 해결}] — 빌드 실패·크래시 복구"},
                         "session_id": {"type": "string"},
                         "work_id": {"type": "string",
                                     "description": "분산 작업이면 work_id"}}}},
    {"name": "log_history",
     "description": "비자명한 의사결정·아키텍처 변경·정책 변경을 처리한 **직후** 작업 기록을 "
                    "남긴다 (원전 α′ 규약 — 온톨로지 시드의 1순위 원천). 단순 버그 수정·"
                    "리네이밍·오탈자 같은 trivial 작업은 쓰지 않는다. 파이프라인 완주는 "
                    "자동 기록되므로 여기는 사람 주도 작업의 결정만. user_quote 에는 사용자 "
                    "직접 발화 1~3줄을 담는다 — WHY 신호로 본문보다 강하다.",
     "inputSchema": {"type": "object", "required": ["title"],
                     "properties": {
                         "title": {"type": "string", "description": "결정/작업 한 줄 요약"},
                         "decision_type": {"type": "string",
                                           "enum": ["architecture", "policy", "experiment",
                                                    "revert", "bugfix", "refactor", "infra",
                                                    "feature"]},
                         "body": {"type": "string",
                                  "description": "자유 본문 — 작업 개요 / 수정 파일 / 주요 설계 결정 / 후속"},
                         "work_id": {"type": "string", "description": "분산 작업이면 work_id"},
                         "session_id": {"type": "string"},
                         "affected_classes": {"type": "array", "items": {"type": "string"},
                                              "description": "CamelCase 식별자만"},
                         "affected_domains": {"type": "array", "items": {"type": "string"}},
                         "supersedes": {"type": "string",
                                        "description": "이전 결정을 뒤집을 때만 — 그 history 파일명"},
                         "alternatives_considered": {"type": "array", "items": {"type": "string"},
                                                     "description": "검토했으나 채택 안 한 옵션"},
                         "tags": {"type": "array", "items": {"type": "string"}},
                         "user_quote": {"type": "string",
                                        "description": "사용자 직접 발화 인용 1~3줄"}}}},
]


def dispatch_tool(name: str, args: dict, *, api=None, papi=None, cache=None,
                  root: Path | None = None) -> dict:
    """도구 실행. `api`/`papi`/`cache` 주입은 테스트 자리 — 실전은 config·token 에서 만든다."""
    args = args or {}
    if name in ("list_works", "get_work", "redmine_note", "log_writer_signal", "log_history"):
        a = api or queue_api(root)
        if name == "list_works":
            return tool_list_works(a, status=str(args.get("status") or ""))
        if name == "get_work":
            return tool_get_work(a, str(args.get("work_id") or ""))
        if name == "log_writer_signal":
            return tool_log_writer_signal(a, args)
        if name == "log_history":
            return tool_log_history(a, args)
        return tool_redmine_note(a, args.get("issue_id"), str(args.get("notes") or ""),
                                 status_name=str(args.get("status_name") or ""),
                                 done_ratio=args.get("done_ratio"))
    if name in ("search_context", "list_domains", "get_domain"):
        pa = papi or projects_api(root)
        c = cache if cache is not None else _load_cache()
        if name == "search_context":
            return tool_search_context(pa, str(args.get("query") or ""),
                                       tags=args.get("tags"), n=args.get("n") or 5, cache=c)
        if name == "list_domains":
            return tool_list_domains(pa, cache=c)
        return tool_get_domain(pa, str(args.get("name") or ""), cache=c)
    raise ClientError(f"모르는 도구: {name}")


# ─────────────────────────────────────────────────────────────
# MCP stdio 서버 — 줄 단위 JSON-RPC
# ─────────────────────────────────────────────────────────────

def handle_message(msg: dict, *, api=None, papi=None, cache=None,
                   root: Path | None = None) -> dict | None:
    """요청 하나 → 응답 하나. 알림(id 없음)은 `None`. [중요] 순수 함수 — 테스트가 이것을 잰다."""
    method = msg.get("method") or ""
    has_id = "id" in msg
    mid = msg.get("id")

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid,
                "result": {"protocolVersion": PROTOCOL_VERSION,
                           "capabilities": {"tools": {"listChanged": False}},
                           "serverInfo": SERVER_INFO}}
    if method.startswith("notifications/"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = msg.get("params") or {}
        try:
            got = dispatch_tool(str(params.get("name") or ""), params.get("arguments") or {},
                                api=api, papi=papi, cache=cache, root=root)
            text = json.dumps(got, ensure_ascii=False, indent=2)
            return {"jsonrpc": "2.0", "id": mid,
                    "result": {"content": [{"type": "text", "text": text}], "isError": False}}
        except ClientError as e:
            # [중요] 도구 오류는 isError 콘텐츠로 — 프로토콜 오류가 아니다. 문장이 조치를 담는다.
            return {"jsonrpc": "2.0", "id": mid,
                    "result": {"content": [{"type": "text", "text": str(e)}], "isError": True}}
    if has_id:
        return {"jsonrpc": "2.0", "id": mid,
                "error": {"code": -32601, "message": f"method not found: {method}"}}
    return None


def serve(stdin=None, stdout=None) -> None:
    """stdio 루프. [중요] stdout 은 MCP 채널이다 — 로그는 stderr 로만."""
    fin = stdin or sys.stdin
    fout = stdout or sys.stdout
    for line in fin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            print("[ax-client] JSON 파싱 실패 — 무시", file=sys.stderr)
            continue
        try:
            resp = handle_message(msg)
        except Exception as e:                               # noqa: BLE001
            # 서버가 죽으면 안 된다 — 요청이면 오류로 답하고 계속 돈다
            resp = ({"jsonrpc": "2.0", "id": msg.get("id"),
                     "error": {"code": -32603, "message": f"{type(e).__name__}: {e}"}}
                    if "id" in msg else None)
        if resp is not None:
            fout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            fout.flush()


def main() -> int:
    # [중요] 윈도우 파이프의 기본 인코딩은 로케일(CP949)이다 — 한글 JSON 이 여기서 깨진다.
    # 소 3.5.5 의 같은 처방을 stdio 양방향에 준다. 단일 파일 제약(스크립트 모드)이라
    # utf8 모듈을 import 하지 않고 같은 원칙(치환 금지·실패해도 죽지 않음)만 그대로 쓴다.
    for st in (sys.stdin, sys.stdout, sys.stderr):
        try:
            if st and hasattr(st, "reconfigure"):
                st.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass
    serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
