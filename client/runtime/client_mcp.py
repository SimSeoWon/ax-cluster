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

def _call(method: str, url: str, token: str, payload=None, *,
          root_hint: Path | None = None) -> dict | list:
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
            # [주의] **역할을 문구에 박지 않는다.** 종전엔 "requester 토큰으로는" 이었고,
            #    워커에도 MCP 를 열자(`#267`) **워커에서 틀린 말을 했다**(실측 2026-08-23).
            #    역할은 배달된 config 가 안다 — 모르면 말하지 않는다.
            _role = ""
            try:
                _role = str((load_config(root_hint).get("this_host") or {}).get("role") or "")
            except Exception:                                # noqa: BLE001
                _role = ""
            who = f"{_role} 토큰" if _role else "이 기계의 역할 토큰"
            raise ClientError(
                f"[스코프] {who}으로는 이 경로를 열 수 없다(403): {method} {url} — "
                f"판단·쓰기는 마스터가 한다(κ.0 경계는 토큰이 강제한다). 필요하면 마스터에서 "
                f"직접 할 것") from e
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
    # [중요] **태그는 여기 한 곳에서 붙는다** (`#258`). 도구마다 넣게 하면 다음에 추가되는
    #    도구는 태그가 없다 — 실측이 그랬다: `thesaurus/*` 둘만 `project` 를 보내고
    #    `signals`·`history`·`claim` 은 안 보냈다. `.ax/config.json` 이 이 체크아웃의
    #    프로젝트를 알고 있으므로 **요청자가 고르는 값이 아니다**.
    project = str(cfg.get("project") or "").strip()

    def api(method: str, path: str, payload=None):
        # [주의] 이미 값이 있으면 덮지 않는다 — 호출자가 명시한 태그가 더 구체적이다
        #    (예: 다른 프로젝트의 work 를 조회하는 검수 흐름).
        if project and isinstance(payload, dict) and not str(payload.get("project") or "").strip():
            payload = {**payload, "project": project}
        # [중요] GET 은 본문이 없다 → **쿼리로 붙인다.** 서버가 모르는 쿼리는 무시하므로
        #    (FastAPI 기본) 모든 GET 에 안전하게 붙고, 목록 라우트는 그것으로 거른다.
        if method.upper() == "GET" and project and "project=" not in path:
            path += ("&" if "?" in path else "?") + "project=" + urllib.parse.quote(project)
        return _call(method, base + path, tok, payload, root_hint=root)

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
                      done_ratio=None, fixed_version: str = "",
                      parent_issue_id=None) -> dict:
    """코멘트·상태·완료율 + **사후 스탬프**(마일스톤·부모, `#303`).

    [주의] 마일스톤이 안 붙어도 갱신 자체는 성공한다 — 사유가 `result` 문장에 붙어 온다.
    """
    payload = {"issue_id": int(issue_id), "notes": notes or ""}
    if status_name:
        payload["status_name"] = status_name
    if done_ratio is not None:
        payload["done_ratio"] = int(done_ratio)
    if fixed_version:
        payload["fixed_version"] = fixed_version
    if parent_issue_id not in (None, "", 0):
        payload["parent_issue_id"] = int(parent_issue_id)
    return api("POST", "/api/v1/redmine/note", payload)


# ── Redmine 조회·생성·연결 (#226 위임 구멍 ① — 원전 `redmine_tracker` 이식) ──────
# [중요] **읽기도 큐(8101)** 다. 8103 은 무인증 공개라(실측 2026-08-20) 일감 본문·검수 이력을
#    둘 자리가 아니다. 원전은 리더 PC 가 키를 갖고 직접 읽었지만 우리 키는 마스터에만 있다.
# [주의] 서버가 실패를 200 + `error` 문장으로 준다 — 그대로 사람에게 보여 준다(조용한 실패 금지).

def tool_redmine_list_issues(api, *, status: str = "open", tracker: str = "",
                             fixed_version: str = "", limit: int = 25,
                             offset: int = 0) -> dict:
    q = [f"status={urllib.parse.quote(status or 'open')}",
         f"limit={int(limit)}", f"offset={int(offset)}"]
    if tracker:
        q.append(f"tracker={urllib.parse.quote(tracker)}")
    if fixed_version:
        q.append(f"fixed_version={urllib.parse.quote(fixed_version)}")
    return api("GET", "/api/v1/redmine/issues?" + "&".join(q))


def tool_redmine_get_issue(api, issue_id) -> dict:
    if not issue_id:
        raise ClientError("issue_id 가 비었다")
    return api("GET", f"/api/v1/redmine/issue/{int(issue_id)}")


def tool_redmine_meta(api) -> dict:
    return api("GET", "/api/v1/redmine/meta")


def tool_redmine_create_issue(api, subject: str, description: str = "",
                              tracker_name: str = "", priority_name: str = "",
                              fixed_version: str = "", parent_issue_id=None) -> dict:
    """이슈 생성. [중요] **마일스톤을 같이 준다** (`#303`) — 안 주면 무버전으로 떨어지고,
    그 상태로 쌓인 것이 실측 13건이다. 부모를 주면 Redmine 네이티브 계층에 들어간다."""
    if not (subject or "").strip():
        raise ClientError("subject 가 비었다 — 제목 없는 이슈는 만들지 않는다")
    payload = {"subject": subject.strip(), "description": description or ""}
    if tracker_name:
        payload["tracker_name"] = tracker_name
    if priority_name:
        payload["priority_name"] = priority_name
    if fixed_version:
        payload["fixed_version"] = fixed_version
    if parent_issue_id not in (None, "", 0):
        payload["parent_issue_id"] = int(parent_issue_id)
    return api("POST", "/api/v1/redmine/issue", payload)


def tool_redmine_link_commit(api, issue_id, commit_hash: str, message: str = "") -> dict:
    if not (commit_hash or "").strip():
        raise ClientError("commit_hash 가 비었다")
    return api("POST", "/api/v1/redmine/link-commit",
               {"issue_id": int(issue_id), "commit_hash": commit_hash.strip(),
                "message": message or ""})


# ── 태스크 템플릿 (#226 위임 구멍 ② — 원전 `context_search.get_task_template`) ────
# [중요] 이쪽은 **8103** 이다 — 태스크 템플릿은 온톨로지 구조 자료이고 도메인 조회와 같은 등급
#    (공개 뷰가 이미 같은 데이터를 보여 준다). 라우트는 이미 있었다: `/api/v1/ontology/tasks`
#    와 `/api/v1/ontology/task/<이름>`.
# [주의] 스토어가 비어 있어도 **0 을 0 이라고 말한다** — 리포트 27 §3 의 교훈(조용히 0 으로
#    답하는 입구가 없다고 답하는 입구보다 위험하다)이 여기 그대로 걸린다.

def tool_list_task_templates(papi, cache=None) -> dict:
    got = cached_fetch(cache, "tasks:list", lambda: papi("GET", "/api/v1/ontology/tasks"))
    if isinstance(got, dict) and not got.get("count"):
        got.setdefault("_note", "등록된 태스크 템플릿이 0건이다 — 이 프로젝트는 아직 안 쓴다")
    return got


def tool_get_task_template(papi, task_type: str, cache=None) -> dict:
    t = (task_type or "").strip()
    if not t:
        raise ClientError("task_type 이 비었다")
    return cached_fetch(cache, f"tasks:one:{t}",
                        lambda: papi("GET", "/api/v1/ontology/task/"
                                     + urllib.parse.quote(t, safe="")))


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


def tool_find_recipes(api, args: dict) -> dict:
    """합성된 레시피 검색 (`#267`) — **작업 시작 직후에 부른다.**

    원전 주석이 호출 시점까지 못박아 뒀다: *"code-writer 에이전트는 작업 시작 직후에 호출해
    step-by-step 가이드를 컨텍스트로 받는다."* 그 호출이 여태 **불가능했다** — 합성은 이식
    됐는데(`recipes_synthesizer`) 읽는 도구가 없어 컨벤션 루프가 한 방향이었다.

    [중요] **레시피 디렉토리를 직접 읽지 않는다** — 마스터 트윈에 있고 이 기계엔 없다.
    `signals`·`log_history` 와 같은 대행 구조다(`#267` 완료 조건 2).
    """
    query = str(args.get("query") or "").strip()
    if not query:
        raise ClientError("query 가 비었다 — 무엇을 하려는지가 매칭의 근거다 "
                          "(예: '미션 태스크 추가')")
    n = int(args.get("n_results") or 3)
    # [중요] **본문으로 보낸다** — 질의는 한글이다(*"미션 태스크 추가"*). URL 에 넣으면 저널이
    #    퍼센트 인코딩으로 남고 손으로 curl 할 수도 없다(사용자 지적 2026-08-23).
    return api("POST", "/api/v1/recipes/search", {"query": query, "n": max(1, n)})


def tool_get_anti_patterns(api, args: dict) -> dict:
    """안티패턴 카탈로그 (`#267`) — *"이 프로젝트에서 거절당한 접근"*.

    작업 시작 시 불러 **알려진 함정을 처음부터 회피**한다(원전 규약).
    [중요] 카탈로그가 없으면 `exists=False` + 사유가 온다 — 빈 값과 고장을 섞지 않는다.
    """
    return api("GET", "/api/v1/anti_patterns")


def tool_find_history(api, args: dict) -> dict:
    """작업 기록 검색 (`#306`) — **작업 시작 직후에 부른다** (`find_recipes` 와 같은 자리).

    [중요] `log_history` 는 여태 **쓰기만** 있었다. 쓰기만 있는 기록은 다음 세션에게 없는 것과
    같다 — 실측: 한 세션이 자기가 남긴 기록을 못 찾아 *"히스토리가 없다"* 고 판단했다(`#304`).
    [주의] 같은 자리를 앞서 건드린 결정이 있으면 **그 결정이 이 프로젝트의 전제**다. 특히
    `supersedes` 가 달린 기록은 *뒤집힌* 결정이라, 옛것을 근거로 삼으면 되돌린 것을 되돌린다.
    """
    payload = {}
    for k in ("query", "decision_type"):
        v = str(args.get(k) or "").strip()
        if v:
            payload[k] = v
    for k in ("classes", "tags"):
        v = args.get(k) or []
        if v:
            payload[k] = [str(x) for x in v]
    if args.get("supersedes_only"):
        payload["supersedes_only"] = True
    if args.get("limit"):
        payload["limit"] = int(args["limit"])
    return api("POST", "/api/v1/history/search", payload)


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


def _bare(name: str) -> str:
    """UE 접두 한 글자를 뗀 이름. 파일 stem 은 접두가 없다 (`UActorComponent_X` →
    `ActorComponent_X.cpp`), 그래서 evidence(파일:줄) 대조에는 이쪽이 필요하다."""
    n = (name or "").strip()
    return n[1:] if len(n) > 2 and n[0] in "UAFET" and n[1].isupper() else n


def tool_find_invariants_by_class(papi, class_name: str, *, cache=None) -> dict:
    """그 클래스가 얽힌 불변식을 **모든 도메인에서** 찾는다 (원전 `find_invariants_by_class`).

    [중요] 서버에 전용 라우트가 없어 **도메인 스윕**으로 만든다 — 도메인이 7개이고 응답이
    캐시를 타므로(`get_domain_layer` 와 같은 키) 비용이 작다. 라우트가 생기면 이 함수만 바뀐다.

    [주의] **휴리스틱이다.** 우리 `evidence` 는 산문이 아니라 `파일.cpp:84-90` 형태라
    클래스명이 그대로 안 들어 있다 — 그래서 ① 불변식 `text` 에 클래스명이 있거나
    ② `evidence` 에 접두 뗀 이름(파일 stem)이 있으면 맞힌 것으로 본다. 어느 규칙으로
    맞았는지 `matched_by` 로 **말해 준다** — 판단은 호출자가 한다.
    """
    c = (class_name or "").strip()
    if not c:
        raise ClientError("클래스명이 비었다")
    cat = cached_fetch(cache, "ontology/domains",
                       lambda: papi("GET", "/api/v1/ontology/domains"))
    names = [x.get("name") for x in ((cat or {}).get("domains") or []) if isinstance(x, dict)]
    bare = _bare(c)
    hits, stale = [], {}
    for dn in [n for n in names if n]:
        q = urllib.parse.quote(dn, safe="")
        got = cached_fetch(cache, f"ontology/domain/{q}",
                           lambda q=q: papi("GET", f"/api/v1/ontology/domain/{q}"))
        if not isinstance(got, dict):
            continue
        for m in MARKERS:
            if m in got:
                stale[m] = got[m]
        for inv in (got.get("invariants") or []):
            if not isinstance(inv, dict):
                continue
            why = []
            if c in (inv.get("text") or ""):
                why.append("text")
            if bare and bare in (inv.get("evidence") or ""):
                why.append("evidence")
            if why:
                hits.append({"domain": dn, "name": inv.get("name"),
                             "layer": inv.get("layer"), "text": inv.get("text"),
                             "evidence": inv.get("evidence"),
                             "confidence": inv.get("confidence"),
                             "matched_by": "+".join(why)})
    out = {"class": c, "bare": bare, "domains_swept": len(names),
           "count": len(hits), "invariants": hits}
    if not hits:
        out["_note"] = (f"'{c}' 로 맞은 불변식이 없다 — 이름을 확인하거나 "
                        f"get_domain_layer(도메인) 의 invariants 목록을 직접 본다")
    out.update(stale)
    return out


# ── 시소러스 쓰기 (2026-08-20) ────────────────────────────────
# [중요] 큐(8101)로 간다. 온톨로지 읽기는 8103 이지만 그쪽 `/api/v1/*` 는 **무인증 공개**라
#   쓰기를 둘 자리가 아니다(실측: 토큰 없이 200). 그리고 범용어 가드(#213)는 서버의
#   `thesaurus.register` 안에 있어 이 경로도 그것을 탄다 — 클라가 판정을 흉내내지 않는다.
# [주의] **캐시를 타지 않는다** — 쓰기는 last-known-good 이 있을 수 없다.


def tool_add_object_alias(api, class_name: str, term: str, *, project: str = "") -> dict:
    """사용자가 **명시로 확인해 준** 별칭 하나를 등록한다.

    [중요] 추측으로 부르지 않는다 — 별칭은 검색 질의에 클래스명을 덧붙여 확장하므로 잘못
    등록되면 검색이 조용히 오염된다(원전 규약: silently auto-add 금지).
    거부(`rejected_short`/`rejected_generic`)도 오류가 아니라 **사유 문장**으로 온다.
    """
    c, tm = (class_name or "").strip(), (term or "").strip()
    if not c:
        raise ClientError("클래스명이 비었다")
    if not tm:
        raise ClientError("별칭 표현이 비었다")
    payload = {"class_name": c, "term": tm}
    if project:
        payload["project"] = project
    return api("POST", "/api/v1/thesaurus/alias", payload)


def tool_mark_not_a_class(api, term: str, *, project: str = "") -> dict:
    """`그건 클래스가 아니다` 를 마스터에 기억시킨다 — 다음부터 묻지 않는다."""
    tm = (term or "").strip()
    if not tm:
        raise ClientError("표현이 비었다")
    payload = {"term": tm}
    if project:
        payload["project"] = project
    return api("POST", "/api/v1/thesaurus/not-a-class", payload)


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


# ── 온톨로지 세밀 조회 (2026-08-20) ───────────────────────────
# [중요] 원전의 `get_object_spec` · `get_action_spec` · `get_domain_layer` 자리다. 그 셋은
#   `.33` 의 **로컬 인덱스**를 읽었고, 온톨로지가 마스터로 옮겨진 뒤 그 인덱스는 정본이 아니다.
#   실측 2026-08-20: 로컬 240항목은 전부 서버에 있었고(로컬 단독 0건) 서버가 54항목 앞서 있었다
#   — 그런데도 로컬 exe 는 objects/actions 를 0/0 으로 답했다. **조용히 틀린 답**이 나오는
#   입구를 남겨 두는 것이 문제이므로, 세밀 조회도 마스터로 위임한다.
MARKERS = ("_stale", "_cached_at", "_note")


def _ontology_item(papi, kind: str, domain: str, name: str, *, cache=None) -> dict:
    d, n = (domain or "").strip(), (name or "").strip()
    if not d:
        raise ClientError("도메인 이름이 비었다")
    if not n:
        raise ClientError(f"{kind} 이름이 비었다")
    qd = urllib.parse.quote(d, safe="")
    qn = urllib.parse.quote(n, safe="")
    return cached_fetch(cache, f"ontology/{kind}/{qd}/{qn}",
                        lambda: papi("GET", f"/api/v1/ontology/{kind}/{qd}/{qn}"))


def tool_get_object_spec(papi, domain: str, name: str, *, cache=None) -> dict:
    """클래스 1건의 스펙 — 8103 `/api/v1/ontology/object/<도메인>/<이름>` 프록시."""
    return _ontology_item(papi, "object", domain, name, cache=cache)


def tool_get_action_spec(papi, domain: str, name: str, *, cache=None) -> dict:
    """행위 1건의 스펙 — 같은 라우트의 `action` 쪽."""
    return _ontology_item(papi, "action", domain, name, cache=cache)


def tool_get_domain_layer(papi, domain: str, layer: int = 0, *, cache=None) -> dict:
    """한 도메인의 층 서술 + 그 층의 항목 이름 목록.

    [중요] 원전의 `get_domain_layer` 와 `list_actions` 를 **한 도구로** 받는다 — 층 서술과
    그 층의 항목은 늘 같이 필요했고, 나눠 두면 왕복만 둘로 는다. 상세는 이름을 들고
    `get_object_spec` / `get_action_spec` 으로 간다. `layer=0` 이면 전체 층.

    [주의] `_stale` 표기는 **변환 뒤에도 그대로 실어 보낸다** — 떨어뜨리면 마스터가 죽은 것을
    아무도 모른다(#162 계약). 이 함수는 응답을 줄이는 유일한 위임이라 그 위험이 여기만 있다.
    """
    d = (domain or "").strip()
    if not d:
        raise ClientError("도메인 이름이 비었다")
    try:
        lv = int(layer or 0)
    except (TypeError, ValueError):
        raise ClientError(f"layer 는 정수다 (받은 값: {layer!r})") from None
    q = urllib.parse.quote(d, safe="")
    got = cached_fetch(cache, f"ontology/domain/{q}",
                       lambda: papi("GET", f"/api/v1/ontology/domain/{q}"))
    if not isinstance(got, dict):
        raise ClientError(f"도메인 응답이 객체가 아니다 ({type(got).__name__}) — "
                          "마스터 버전을 확인할 것")
    descs = got.get("layer_descriptions") or {}
    man = got.get("manifest") or {}
    out = {"domain": got.get("name") or d, "layer": lv or "all",
           # [중요] 매니페스트·네비게이션도 같이 준다 (2026-08-20). 원전의 `get_domain_manifest`
           #   자리이고, 이것이 없으면 계층·연관(넓이) 탐색이 작업장에서 아예 불가능했다 —
           #   서버 응답에 이미 실려 오는 값이라 왕복이 늘지 않는다.
           "tier": man.get("tier"), "summary": man.get("summary"),
           "layer_counts": man.get("layer_counts"),
           "parent_domain": got.get("parent_domain") or "",
           "sub_domains": got.get("sub_domains") or [],
           "collaborated_by": got.get("collaborated_by") or [],
           "layer_descriptions": ({k: v for k, v in descs.items() if k == f"L{lv}"}
                                  if lv else descs)}
    for kind in ("objects", "actions", "invariants"):
        rows = []
        for x in (got.get(kind) or []):
            if not isinstance(x, dict):
                continue
            if lv and int(x.get("layer") or 0) != lv:
                continue
            row = {"name": x.get("name"), "layer": x.get("layer")}
            if x.get("file"):
                row["file"] = x["file"]
            rows.append(row)
        out[kind] = rows
    if lv and not (out["objects"] or out["actions"] or out["invariants"]):
        out["_note"] = (f"L{lv} 에 항목이 없다 — 이 도메인이 가진 층은 "
                        f"{sorted(descs) or '없음'} 이다")
    for m in MARKERS:                      # 마스터가 준 표기가 내 주석을 이긴다
        if m in got:
            out[m] = got[m]
    return out


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
    {"name": "get_domain_layer",
     "description": "도메인의 층 서술 + 그 층의 objects·actions·invariants 이름 목록 "
                    "(읽기 전용 · _stale 폴백 있음). layer 생략/0 이면 전체 층. "
                    "[중요] 온톨로지 조회는 이 입구가 정본이다 — 로컬 인덱스는 낡았다.",
     "inputSchema": {"type": "object", "required": ["domain"],
                     "properties": {"domain": {"type": "string"},
                                    "layer": {"type": "integer",
                                              "description": "1 또는 3 (0/생략=전체)"}}}},
    {"name": "get_object_spec",
     "description": "클래스 1건의 온톨로지 스펙 — 시그니처·부모·불변식 근거까지 "
                    "(읽기 전용 · _stale 폴백 있음). 도메인을 모르면 list_domains → "
                    "get_domain_layer 로 찾는다. [주의] 사실 확인은 최종적으로 소스 선언부다.",
     "inputSchema": {"type": "object", "required": ["domain", "name"],
                     "properties": {"domain": {"type": "string"},
                                    "name": {"type": "string",
                                             "description": "클래스명 (예: UMissionTaskExecutor)"}}}},
    {"name": "get_action_spec",
     "description": "행위(action) 1건의 온톨로지 스펙 — 트리거·흐름·영향 객체 "
                    "(읽기 전용 · _stale 폴백 있음).",
     "inputSchema": {"type": "object", "required": ["domain", "name"],
                     "properties": {"domain": {"type": "string"},
                                    "name": {"type": "string",
                                             "description": "행위명 (예: AdvanceTaskOnTick)"}}}},
    {"name": "find_invariants_by_class",
     "description": "그 클래스가 얽힌 불변식을 모든 도메인에서 찾는다 (읽기 전용). "
                    "[주의] 휴리스틱이다 — 불변식 text 의 클래스명 또는 evidence(파일:줄)의 "
                    "접두 뗀 이름으로 맞힌다. 어느 규칙으로 맞았는지 matched_by 로 온다.",
     "inputSchema": {"type": "object", "required": ["class_name"],
                     "properties": {"class_name": {"type": "string"}}}},
    {"name": "add_object_alias",
     "description": "사용자가 확인해 준 시소러스 별칭 1건을 등록한다 (마스터 경유 — 온톨로지 "
                    "yaml 은 여기 없다). [중요] **추측으로 부르지 않는다** — 사용자가 명시로 "
                    "확인한 표현만. 범용어·짧은 표현은 마스터 가드가 거부하고 사유를 돌려준다 "
                    "(오류가 아니라 status=rejected_… 로 온다).",
     "inputSchema": {"type": "object", "required": ["class_name", "term"],
                     "properties": {"class_name": {"type": "string",
                                                   "description": "클래스명 (예: UMissionTaskExecutor)"},
                                    "term": {"type": "string",
                                             "description": "사용자가 쓰는 한국어 표현 (예: 미션 태스크)"}}}},
    {"name": "mark_not_a_class",
     "description": "사용자가 \"그건 클래스가 아니다\" 라고 답한 표현을 기억시킨다 — 다음부터 "
                    "묻지 않는다. 상태·개념어([완료]·[연출] 같은)가 여기로 간다.",
     "inputSchema": {"type": "object", "required": ["term"],
                     "properties": {"term": {"type": "string"}}}},
    {"name": "redmine_note",
     "description": "레드마인 이슈에 코멘트를 남긴다 (마스터 경유 — 키는 이 PC 에 없다). "
                    "상태 이름은 실재하는 것만: 신규·진행·해결·검토·완료. "
                    "완료로 닫는 것은 사람의 판단이다.",
     "inputSchema": {"type": "object", "required": ["issue_id", "notes"],
                     "properties": {"issue_id": {"type": "integer"},
                                    "notes": {"type": "string"},
                                    "status_name": {"type": "string"},
                                    "done_ratio": {"type": "integer"},
                                    "fixed_version": {"type": "string",
                                                      "description": "마일스톤 이름 (부분 일치). 사후 스탬프용"},
                                    "parent_issue_id": {"type": "integer",
                                                        "description": "부모 이슈 번호"}}}},
    {"name": "redmine_list_issues",
     "description": "레드마인 이슈 목록 (마스터 경유 — 키는 이 PC 에 없다). status 는 open(기본)/"
                    "closed/*. [중요] 우리 규약에서 닫힌 상태는 「완료」뿐이라 「해결」은 open 에 "
                    "들어온다. tracker·fixed_version(마일스톤)으로 좁힐 수 있다.",
     "inputSchema": {"type": "object", "properties": {
         "status": {"type": "string", "description": "open(기본) · closed · *"},
         "tracker": {"type": "string", "description": "예: 코드리뷰"},
         "fixed_version": {"type": "string", "description": "마일스톤 이름 (부분 일치 허용)"},
         "limit": {"type": "integer"}, "offset": {"type": "integer"}}}},
    {"name": "redmine_get_issue",
     "description": "레드마인 이슈 1건 상세 + 노트 이력. 없는 번호는 error 로 답한다(조용히 "
                    "빈 것을 주지 않는다). 리뷰 지적 상담·검증 전에 이걸로 본문을 확보한다.",
     "inputSchema": {"type": "object", "required": ["issue_id"],
                     "properties": {"issue_id": {"type": "integer"}}}},
    {"name": "redmine_meta",
     "description": "이 레드마인의 상태·트래커·우선순위·마일스톤 카탈로그. 상태 이름을 추측하지 "
                    "말고 여기서 확인한다 — 이 환경은 한국어이고 「반려」에 해당하는 상태가 없다.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "redmine_create_issue",
     "description": "레드마인 이슈를 새로 만든다 (마스터 경유). 등재될 레드마인 프로젝트는 "
                    "요청의 프로젝트 태그가 정한다 (#293 — 게임 프로젝트가 늘면 자리도 늘어난다). "
                    "AX 인프라 건이면 제목에 [AX] 접두어를 쓰고 ModularStage 에 둔다. "
                    "[중요] fixed_version(마일스톤)을 같이 줄 것 — 빼면 무버전으로 떨어진다.",
     "inputSchema": {"type": "object", "required": ["subject"],
                     "properties": {"subject": {"type": "string"},
                                    "description": {"type": "string"},
                                    "tracker_name": {"type": "string"},
                                    "priority_name": {"type": "string"},
                                    "fixed_version": {"type": "string",
                                                      "description": "마일스톤 이름 (부분 일치 허용)"},
                                    "parent_issue_id": {"type": "integer",
                                                        "description": "부모 이슈 번호 — 소분류를 낼 때"}}}},
    {"name": "redmine_link_commit",
     "description": "커밋 해시를 이슈에 노트로 연결한다 (원전과 같은 「커밋 연결: `<해시>`」 형식 — "
                    "형식이 같아야 이력을 한 규칙으로 훑을 수 있다).",
     "inputSchema": {"type": "object", "required": ["issue_id", "commit_hash"],
                     "properties": {"issue_id": {"type": "integer"},
                                    "commit_hash": {"type": "string"},
                                    "message": {"type": "string"}}}},
    {"name": "list_task_templates",
     "description": "등록된 태스크 템플릿 목록 (구조 레지스트리 — 도메인 검색 채널과 분리돼 있다). "
                    "0건이면 0건이라고 답한다.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "get_task_template",
     "description": "태스크 템플릿 1건 — 구조·예시·계약·test_spec. 골조를 짜기 전에 같은 종류의 "
                    "작업이 이미 표준화돼 있는지 여기서 확인한다.",
     "inputSchema": {"type": "object", "required": ["task_type"],
                     "properties": {"task_type": {"type": "string"}}}},
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
    {"name": "find_history",
     "description": "이 프로젝트의 **과거 결정 기록**을 찾는다 (원전 α′ history — 온톨로지 시드의 "
                    "1순위 원천). 작업 시작 직후에 `find_recipes`·`get_anti_patterns` 와 함께 "
                    "부른다. 같은 자리를 앞서 건드린 결정이 있으면 **그것이 이 프로젝트의 전제**다. "
                    "[중요] 기록은 마스터 트윈에 있고 이 기계엔 없다 — 로컬 파일을 찾지 말 것. "
                    "[주의] supersedes 가 달린 기록은 뒤집힌 결정이다: 옛것을 근거로 삼으면 "
                    "되돌린 것을 되돌린다. 0건이면 dir·exists 로 「없다」와 「못 봤다」를 갈라 답한다.",
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "자유 질의 — 제목·요지·태그·클래스를 훑는다. 한글 가능"},
         "decision_type": {"type": "string",
                           "description": "architecture · policy · experiment · revert · bugfix · refactor · infra · feature"},
         "classes": {"type": "array", "items": {"type": "string"},
                     "description": "클래스명 (UE prefix 관용 — UManager_X 와 Manager_X 가 같이 걸린다)"},
         "tags": {"type": "array", "items": {"type": "string"}},
         "supersedes_only": {"type": "boolean", "description": "뒤집힌 결정만 본다"},
         "limit": {"type": "integer"}}}},
    {"name": "log_history",
     "description": "비자명한 의사결정·아키텍처 변경·정책 변경을 처리한 **직후** 작업 기록을 "
                    "남긴다 (원전 α′ 규약 — 온톨로지 시드의 1순위 원천). 단순 버그 수정·"
                    "리네이밍·오탈자 같은 trivial 작업은 쓰지 않는다. 파이프라인 완주는 "
                    "자동 기록되므로 여기는 사람 주도 작업의 결정만. user_quote 에는 사용자 "
                    "직접 발화 1~3줄을 담는다 — WHY 신호로 본문보다 강하다. "
                    "[중요] 기록은 **마스터 트윈의 `history/`** 에 생긴다 — 이 기계에는 파일이 "
                    "안 생긴다(쓰는 것은 서버 하나다). 로컬에서 찾지 말 것: 실제로 한 세션이 "
                    "그걸 「기록이 없다」로 읽었다(#304). 리스트 인자는 배열로 주면 마스터가 "
                    "대시 리스트로 렌더한다.",
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
    # [중요] **컨벤션 루프의 반대 방향** (`#267`). 합성은 이식됐는데(`recipes_synthesizer`)
    #    읽는 도구가 없어 한 방향이었다. 원전 주석이 호출 시점까지 못박아 뒀다:
    #    *"code-writer 에이전트는 **작업 시작 직후에 호출**해 step-by-step 가이드를 컨텍스트로
    #    받는다."* 그래서 설명도 그 시점을 말한다 — 도구가 있어도 안 부르면 루프는 여전히 한
    #    방향이다.
    {"name": "find_recipes",
     "description": "**작업을 시작하기 직전에 부른다.** 이 프로젝트에 합성된 코드 레시피"
                    "(step-by-step 가이드)를 의도·키워드로 찾는다 — 같은 일을 앞서 한 기록이 "
                    "있으면 그 관습을 따르는 것이 이 프로젝트의 컨벤션이다. 없으면 사유가 "
                    "온다(「없음」과 「고장」을 구분한다).",
     "inputSchema": {"type": "object", "required": ["query"],
                     "properties": {
                         "query": {"type": "string",
                                   "description": "작업 의도 또는 키워드 (예: '미션 태스크 추가')"},
                         "n_results": {"type": "integer",
                                       "description": "반환 최대 건수 (기본 3)"}}}},
    {"name": "get_anti_patterns",
     "description": "**작업을 시작하기 직전에 부른다.** 이 프로젝트에서 **거절당한 접근**의 "
                    "카탈로그를 받아 알려진 함정을 처음부터 회피한다(누적된 "
                    "rejected_approaches·error_recoveries 를 dedupe 한 결과). 아직 없으면 "
                    "`exists=false` 와 사유가 온다.",
     "inputSchema": {"type": "object", "properties": {}}},
]


def dispatch_tool(name: str, args: dict, *, api=None, papi=None, cache=None,
                  root: Path | None = None) -> dict:
    """도구 실행. `api`/`papi`/`cache` 주입은 테스트 자리 — 실전은 config·token 에서 만든다."""
    args = args or {}
    if name in ("list_works", "get_work", "redmine_note", "log_writer_signal", "log_history",
                "add_object_alias", "mark_not_a_class", "redmine_list_issues",
                "redmine_get_issue", "redmine_meta", "redmine_create_issue",
                "redmine_link_commit",
                # 레시피·안티패턴 읽기 — 큐 대행이므로 같은 자리다 (`#267`)
                "find_recipes", "get_anti_patterns",
                # history 읽기 (`#306`) — 쓰기(`log_history`)와 같은 대행 자리
                "find_history"):
        a = api or queue_api(root)
        if name in ("add_object_alias", "mark_not_a_class"):
            # 프로젝트는 배달된 config 가 안다 — #210(활성 스위치)에 흔들리지 않게 실어 보낸다
            proj = ""
            try:
                proj = str(load_config(root).get("project") or "")
            except ClientError:
                pass
            if name == "add_object_alias":
                return tool_add_object_alias(a, str(args.get("class_name") or ""),
                                             str(args.get("term") or ""), project=proj)
            return tool_mark_not_a_class(a, str(args.get("term") or ""), project=proj)
        if name == "list_works":
            return tool_list_works(a, status=str(args.get("status") or ""))
        if name == "get_work":
            return tool_get_work(a, str(args.get("work_id") or ""))
        if name == "log_writer_signal":
            return tool_log_writer_signal(a, args)
        if name == "find_recipes":
            return tool_find_recipes(a, args)
        if name == "get_anti_patterns":
            return tool_get_anti_patterns(a, args)
        if name == "find_history":
            return tool_find_history(a, args)
        if name == "log_history":
            return tool_log_history(a, args)
        if name == "redmine_list_issues":
            return tool_redmine_list_issues(a, status=str(args.get("status") or "open"),
                                            tracker=str(args.get("tracker") or ""),
                                            fixed_version=str(args.get("fixed_version") or ""),
                                            limit=args.get("limit") or 25,
                                            offset=args.get("offset") or 0)
        if name == "redmine_get_issue":
            return tool_redmine_get_issue(a, args.get("issue_id"))
        if name == "redmine_meta":
            return tool_redmine_meta(a)
        if name == "redmine_create_issue":
            return tool_redmine_create_issue(a, str(args.get("subject") or ""),
                                             str(args.get("description") or ""),
                                             str(args.get("tracker_name") or ""),
                                             str(args.get("priority_name") or ""),
                                             str(args.get("fixed_version") or ""),
                                             args.get("parent_issue_id"))
        if name == "redmine_link_commit":
            return tool_redmine_link_commit(a, args.get("issue_id"),
                                            str(args.get("commit_hash") or ""),
                                            str(args.get("message") or ""))
        return tool_redmine_note(a, args.get("issue_id"), str(args.get("notes") or ""),
                                 status_name=str(args.get("status_name") or ""),
                                 done_ratio=args.get("done_ratio"),
                                 fixed_version=str(args.get("fixed_version") or ""),
                                 parent_issue_id=args.get("parent_issue_id"))
    if name in ("search_context", "list_domains", "get_domain", "get_domain_layer",
                "get_object_spec", "get_action_spec", "find_invariants_by_class",
                "list_task_templates", "get_task_template"):
        pa = papi or projects_api(root)
        c = cache if cache is not None else _load_cache()
        if name == "list_task_templates":
            return tool_list_task_templates(pa, cache=c)
        if name == "get_task_template":
            return tool_get_task_template(pa, str(args.get("task_type") or ""), cache=c)
        if name == "search_context":
            return tool_search_context(pa, str(args.get("query") or ""),
                                       tags=args.get("tags"), n=args.get("n") or 5, cache=c)
        if name == "list_domains":
            return tool_list_domains(pa, cache=c)
        if name == "get_domain_layer":
            return tool_get_domain_layer(pa, str(args.get("domain") or ""),
                                         layer=args.get("layer") or 0, cache=c)
        if name == "find_invariants_by_class":
            return tool_find_invariants_by_class(pa, str(args.get("class_name") or ""), cache=c)
        if name in ("get_object_spec", "get_action_spec"):
            kind = "object" if name == "get_object_spec" else "action"
            return _ontology_item(pa, kind, str(args.get("domain") or ""),
                                  str(args.get("name") or ""), cache=c)
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
