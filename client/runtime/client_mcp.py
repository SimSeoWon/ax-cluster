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
[주의] 쓰는 도구가 하나 있다 — `update_fix_status` (`#630`). 수정 항목(R12-3·P3)에 **사람이 정한
결정을 기록**만 한다. 큐 상태(`merge_status`)와 무관하고 따르는 절차가 없어 두 벌이 될 로직이 없다.

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


def projects_write_api(root: Path | None = None):
    """8103 의 **토큰 잠긴** 표면 호출자 (`#336` ④ — 등재).

    [중요] `projects_api` 와 갈라 둔다. 그쪽(`/api/v1/*`)은 **무인증 공개**라 토큰을 실을
    자리가 아니고, 이쪽(`/work/*`)은 `REQUESTER_SCOPE` 로 잠겨 있다. 한 함수가 둘을 겸하면
    다음에 추가되는 경로가 어느 쪽인지 호출부가 판단하게 된다 — 그 판단을 없앤다.
    [주의] 태그는 여기서 붙인다 — `queue_api` 와 같은 이유다(`#258`: 도구마다 넣게 하면
    다음에 추가되는 도구는 태그가 없다).
    """
    cfg = load_config(root)
    base = projects_url(cfg)
    tok = load_token(root)
    project = str(cfg.get("project") or "").strip()

    def api(method: str, path: str, payload=None):
        if project and isinstance(payload, dict) and not str(payload.get("project") or "").strip():
            payload = {**payload, "project": project}
        return _call(method, base + path, tok, payload, root_hint=root)

    return api


def projects_api(root: Path | None = None):
    """8103 읽기 표면 호출자. [중요] **토큰이 없다** — 이 표면은 읽기 전용 공개(ufw LAN 한정)다.
    (사용자 결정 2026-08-13: *"그냥 있는거 보여주는 뷰어"* — 조작 경로가 아니다.)"""
    cfg = load_config(root)
    base = projects_url(cfg)
    project = str(cfg.get("project") or "").strip()

    def api(method: str, path: str, payload=None):
        # 🔴 프로젝트 태그를 싣는다 (`#693`) — 검색은 이 태그로 **자기 프로젝트**를 본다.
        #    종전엔 이 호출자만 태그를 안 실어 NS 체크아웃도 늘 마운트를 검색했다.
        #    [주의] 이미 실린 값은 덮지 않는다 — 다른 두 호출자(`queue_api`)와 같은 규약이다.
        if project and isinstance(payload, dict) and not str(payload.get("project") or "").strip():
            payload = {**payload, "project": project}
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


def tool_register_work(_unused, args: dict, *, root=None) -> dict:
    """분산 작업 등재 (`#336` ④). **8103 의 토큰 잠긴 `/work/register`** 로 간다.

    [중요] 이 도구가 오래 **없었다.** `ax-request` §3 은 등재를 지시했는데 로스터에 없었고
    스코프에도 없어 403 이 정상 동작이었다(실측 2026-08-29) — 절차서가 못 하는 것을 지시하던
    `#297` 부류다. 그동안 마스터가 대신 등재했고, `~/CLAUDE.md` 는 그것을 *"standing in"* 이라
    적어 뒀다. 이제 요청자가 직접 한다.

    [주의] **판단은 마스터가 한다.** 이 함수는 명세를 실어 보내기만 한다 — 분해·골조·게이트·
    매니페스트·carry 는 전부 서버 쪽이다(κ.0 경계).
    """
    title = str(args.get("title") or "").strip()
    if not title:
        raise ClientError("title 이 비었다")
    specs = args.get("specs")
    if specs in (None, "", [], {}):
        raise ClientError("specs 가 비었다 — 태스크 목록이 있어야 등재가 성립한다")
    body = {"title": title, "specs": specs}
    # 🔴 [중요] **등재는 최초 전용이다 — 다음 라운드는 `improve_work`** (사용자 결정 2026-09-05:
    #    *"분산작업 등록과 라운드 값을 받는 분산작업 개선 요청으로 말이야"*). 종전에는 여기에
    #    `work_id` 를 실으면 재활성화로 갈렸는데, 한 입구에 두 뜻이라 라운드를 **상태로 추론**했다.
    if str(args.get("work_id") or "").strip():
        raise ClientError(
            "등재에 work_id 를 실을 수 없다 — 이미 있는 분산 작업의 다음 라운드는 "
            "`improve_work(work_id=…, round=현재+1, specs=[…])` 다")
    # [중요] `fixed_version` 이 여기 있는 것이 `#652` 다 — 등재가 만드는 레드마인 이슈는
    #    이 값으로만 마일스톤에 들어간다. 빼면 무버전이고, 그 상태로 24건이 쌓였다.
    for k in ("target_repo", "original_request", "target_branch", "worker_mode",
              "fixed_version"):
        v = args.get(k)
        if v not in (None, ""):
            body[k] = v
    return _attach_wait(projects_write_api(root)("POST", "/work/register", body), root, 1)


def tool_improve_work(_unused, args: dict, *, root=None) -> dict:
    """🔴 **분산 작업 개선요청** — 이미 있는 work 을 다음 라운드로 연다 (사용자 결정 2026-09-05).

        ① 등록      `register_work`   새 분산 작업 (round = 1)
        ② 개선요청   **여기**          이미 있는 work · round = 현재 + 1
        ③ 마감      `ax-review` → `finalize_work`   main 머지 · 레드마인 완료

    [중요] `round` 는 **확인용**이다 — 값은 큐가 이미 안다(현재+1). 어긋나면 큐가 거절하고
    맞추지 않는다: 요청자와 큐가 서로 다른 라운드를 보고 있다는 뜻이기 때문이다.
    """
    work_id = str(args.get("work_id") or "").strip()
    if not work_id:
        raise ClientError("work_id 가 비었다 — 새 분산 작업이면 `register_work` 를 쓴다")
    try:
        round_no = int(args.get("round") or 0)
    except (TypeError, ValueError):
        raise ClientError(f"round 가 정수가 아니다: {args.get('round')!r}") from None
    if round_no < 2:
        raise ClientError(
            "round 를 실어야 한다(2 이상) — 라운드 1은 **등록**이다. "
            "`get_work` 로 현재 라운드를 보고 +1 을 싣는다")
    specs = args.get("specs")
    if specs in (None, "", [], {}):
        raise ClientError("specs 가 비었다 — 이번 라운드에 무엇을 고칠지가 조각이다")
    body = {"work_id": work_id, "round": round_no, "specs": specs}
    # [주의] **`target_branch` 는 보통 비운다** — 비우면 큐에 저장된 작업 브랜치를 그대로 쓴다.
    #    여기서 지어내면 ⑺ 이 전진시킨 브랜치가 조용히 원복된다.
    v = args.get("target_branch")
    if v not in (None, ""):
        body["target_branch"] = v
    if args.get("worker_mode") not in (None, ""):
        body["worker_mode"] = args["worker_mode"]
    if "rework" in args:
        if not isinstance(args["rework"], bool):
            raise ClientError("rework 는 boolean 이어야 한다")
        body["rework"] = args["rework"]
    if args.get("expected_base_commit") not in (None, ""):
        if not isinstance(args["expected_base_commit"], str):
            raise ClientError("expected_base_commit 은 문자열이어야 한다")
        body["expected_base_commit"] = args["expected_base_commit"]
    return _attach_wait(projects_write_api(root)("POST", "/work/improve", body), root, round_no)


# ── `#799` 대기 명령 — 훅이 없거나(Codex) 죽었거나 2시간을 넘긴 work 의 끝을 받는 길 ─────
#
# 마스터 쪽 짝은 `master/projects/mcp_server.py` `_wait_command`(`#798`)다. 같은 모양으로
# **성공 응답에 명령을 실어** 세션이 곧바로 돌리게 한다. 명령은 배달된 완료 훅의 CLI 모드
# (`.claude/hooks/work_completion.py --wait`)이고, 1분마다 큐를 읽기만 한다.
# 🔴 사실만 싣는다 — 「무엇을 하나」는 `ax-request` 스킬의 몫이다(명령형은 주입으로 거부된다).
WAIT_HOOK_REL = ".claude/hooks/work_completion.py"
WAIT_NOTE = ("wait 는 체크아웃 루트에서 실행하는 명령이다. 이 work·라운드가 ready_for_review·"
             "merged·cancelled·rejected 가 되거나 실패 조각이 생기거나 타임아웃(기본 24시간)될 "
             "때까지 1분마다 큐를 읽기만 한다. 조회마다 stderr 에 [wait] 한 줄, 끝나면 stdout 에 "
             "결과 블록을 남긴다 (종료 코드 0 ready_for_review · 3 그 밖의 종결·실패 신호·라운드 "
             "불일치 · 4 타임아웃 · 2 연결 준비 실패·영구 조회 거절 401·403·404). "
             "wait_argv 는 같은 명령의 인자 목록이다.")


def _wait_arg(text: str) -> str:
    """셸 하나에 기대지 않는 인자 — 역슬래시를 `/` 로 바꾸고 공백이 있을 때만 따옴표로 감싼다.

    [주의] Windows 는 `C:/…/python.exe` 를 그대로 연다. 역슬래시를 남기면 Git Bash(Claude 의
    Bash 도구)가 일부를 이스케이프로 먹는다. 따옴표로 감싼 첫 토큰은 PowerShell 에서 명령이
    아니라 문자열이 되므로 늘 감싸지 않는다 — 그 경우를 위해 `wait_argv` 를 함께 싣는다.
    """
    text = str(text).replace("\\", "/")
    return f'"{text}"' if any(c.isspace() for c in text) else text


def _wait_command(root, work_id: str, round_no: int) -> tuple[str, list[str]]:
    """이 체크아웃에서 돌릴 대기 명령 `(문자열, argv)`. 못 만들면 `ClientError` — 사유가 그대로 간다."""
    base = Path(root) if root else Path.cwd()
    if not (base / WAIT_HOOK_REL).is_file():
        raise ClientError(f"대기 스크립트가 없다: {base / WAIT_HOOK_REL} (마스터 배달 전이거나 "
                          "이 체크아웃에 완료 훅이 배달되지 않는 종류다)")
    cfg = load_config(base)
    py = str(((cfg.get("backends") or {}).get("python")) or "").strip()
    if not py:
        # `backends.python` 이 없을 때만 — Windows 는 런처 `py`, 그 밖은 `python3`
        osname = str(((cfg.get("this_host") or {}).get("os")) or "").lower()
        py = "py" if osname.startswith("win") else "python3"
    argv = [py.replace("\\", "/"), WAIT_HOOK_REL, "--wait", str(work_id), "--round", str(int(round_no))]
    return " ".join(_wait_arg(a) for a in argv), argv


def _attach_wait(got, root, round_no: int):
    """성공 응답에 `wait`(+`wait_argv`·`wait_note`)를 싣는다. 못 만들면 `wait_error` — 조용히 빼지 않는다."""
    if not (isinstance(got, dict) and got.get("ok") is True and got.get("work_id")):
        return got
    try:
        rnd = int(got.get("round") or round_no)
    except (TypeError, ValueError):
        rnd = round_no
    try:
        cmd, argv = _wait_command(root, str(got["work_id"]), rnd)
    except Exception as e:                                   # noqa: BLE001
        return {**got, "wait_error": f"{type(e).__name__}: {e}"[:500]}
    return {**got, "wait": cmd, "wait_argv": argv, "wait_note": WAIT_NOTE}


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
                      parent_issue_id=None, priority_name: str = "",
                      subject: str = "", description: str = "",
                      clear_parent: bool = False) -> dict:
    """코멘트·상태·완료율 + **사후 스탬프**(마일스톤·부모, `#303`) + 우선순위·제목·본문(`#752`).

    [주의] 마일스톤이 안 붙어도 갱신 자체는 성공한다 — 사유가 `result` 문장에 붙어 온다.
    새 세 필드는 **줬을 때만** 싣는다 — 안 주면 종전과 같은 페이로드다.
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
    if priority_name:
        payload["priority_name"] = priority_name
    if (subject or "").strip():
        payload["subject"] = subject
    if description:
        payload["description"] = description
    if clear_parent:                                    # `#754` — 줬을 때만 싣는다
        payload["clear_parent"] = True
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


def tool_redmine_get_wiki_page(api, title) -> dict:
    if not isinstance(title, str) or not title.strip():
        raise ClientError("title 은 비어 있지 않은 문자열이어야 한다")
    return api("GET", "/api/v1/redmine/wiki?title=" +
               urllib.parse.quote(title.strip(), safe=""))


def tool_redmine_put_wiki_page(api, title, text, *, mode="append",
                              version=None, comments="") -> dict:
    """본문 보존·버전 검사·쓰기 후 되읽기는 마스터에 한 벌만 둔다 (#769)."""
    if not isinstance(title, str) or not title.strip():
        raise ClientError("title 은 비어 있지 않은 문자열이어야 한다")
    if not isinstance(text, str) or not text.strip():
        raise ClientError("text 는 비어 있지 않은 문자열이어야 한다")
    if mode not in ("append", "replace"):
        raise ClientError("mode 는 append 또는 replace 여야 한다")
    if version is not None and (type(version) is not int or version < 1):
        raise ClientError("version 은 양의 정수여야 한다")
    if not isinstance(comments, str):
        raise ClientError("comments 는 문자열이어야 한다")
    payload = {"title": title.strip(), "text": text, "mode": mode,
               "comments": comments}
    if version is not None:
        payload["version"] = version
    return api("PUT", "/api/v1/redmine/wiki", payload)


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


def tool_redmine_create_version(api, name: str, *, due_date: str = "",
                                description: str = "", status: str = "open") -> dict:
    """🔴 **마일스톤(버전)을 만든다** (`#652`, 사용자 지적 2026-09-20).

    [중요] **이 도구가 없어서 마일스톤 관리가 멈춰 있었다.** 요청자는 이슈에 마일스톤을
    **붙일** 수는 있었지만(`fixed_version`) **만들** 수가 없었다 — 레드마인 키는 마스터에만
    있으니 유일한 길이 「사람이 웹 UI 를 연다」였고, 실측으로 `ns` 는 이슈 24건 전부가
    무버전이었다. `redmine_create_issue` 가 *"fixed_version 을 같이 줄 것"* 이라고 지시하면서
    **그 값을 만들 방법이 없던** 자리다(`#297` 부류 — 절차서가 못 하는 것을 지시한다).

    [주의] 어느 레드마인 프로젝트에 만드는지는 **이 체크아웃의 프로젝트 태그**가 정한다 —
    고를 수 없고, 고를 필요도 없다(`.ax/config.json` 이 안다).
    [주의] 같은 이름이 이미 있으면 **만들지 않고 그 id 를 돌려준다**(`existing: true`).
    """
    nm = (name or "").strip()
    if not nm:
        raise ClientError("name 이 비었다 — 이름 없는 마일스톤은 만들지 않는다")
    payload = {"name": nm, "status": status or "open"}
    if due_date:
        payload["due_date"] = due_date
    if description:
        payload["description"] = description
    return api("POST", "/api/v1/redmine/version", payload)


def tool_redmine_update_version(api, name: str, *, new_name: str = "",
                                description=None, due_date=None,
                                status: str = "") -> dict:
    """마일스톤(버전)의 **이름·설명·마감일**을 고친다 (`#652` 후속, 사용자 요청 2026-09-20).

    [중요] **대상은 지금 이름으로 고르고, 정확히 일치해야 한다.** 부분 일치를 허용하면
    「마일스톤 1」을 고치려다 「마일스톤 10」을 고친다 — 잘못 붙은 마일스톤은 떼면 되지만
    **잘못 바뀐 이름은 무엇이었는지 아무도 모른다.** 못 찾으면 있는 이름을 같이 준다.

    [주의] `description`·`due_date` 는 **안 주면 안 바뀌고, 빈 문자열을 주면 비운다.**
    [주의] `status` 는 안 주면 안 바뀐다 — 마일스톤을 잠그거나 닫는 것은 사람의 결정이다.
    """
    nm = (name or "").strip()
    if not nm:
        raise ClientError("name 이 비었다 — 어느 마일스톤을 고칠지 말해야 한다")
    payload: dict = {"name": nm}
    if (new_name or "").strip():
        payload["new_name"] = new_name.strip()
    if description is not None:
        payload["description"] = description
    if due_date is not None:
        payload["due_date"] = due_date
    if status:
        payload["status"] = status
    if len(payload) == 1:
        raise ClientError("바꿀 것이 없다 — new_name·description·due_date·status 중 "
                          "하나는 줘야 한다")
    return api("PATCH", "/api/v1/redmine/version", payload)


def tool_redmine_delete_version(api, name: str, *, confirm: bool = False) -> dict:
    """마일스톤(버전)을 지운다 — **되돌릴 수 없다** (`#652` 후속).

    🔴 [중요] **`confirm` 없이 부르면 지우지 않고 무엇이 지워질지만 알려 준다.** 그것을
    사람에게 보이고 승인을 받은 뒤 `confirm=true` 로 다시 부른다 — 이 저장소에서 되돌릴 수
    없는 조작의 관례다(`finalize_work`·`advance_work`).

    [중요] 붙은 이슈가 있으면 **거절한다.** 몇 건이 걸렸고 어떤 번호인지 응답이 말해 준다 —
    **대신 떼어 주지 않는다.** 어느 마일스톤으로 옮길지는 사람의 판단이다.
    """
    nm = (name or "").strip()
    if not nm:
        raise ClientError("name 이 비었다 — 어느 마일스톤을 지울지 말해야 한다")
    return api("DELETE", "/api/v1/redmine/version",
               {"name": nm, "confirm": bool(confirm)})


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


USAGE_STR_KEYS = ("lane", "worker", "work_id", "task_id", "mode", "model", "note", "session_id")
USAGE_TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens",
                    "cache_creation_input_tokens", "reasoning_output_tokens", "total_tokens")


def tool_log_usage(api, args: dict) -> dict:
    """사용량 한 줄 (`#763`) — 마스터 트윈 `usage_log.jsonl` 에 남긴다(마스터 대행 `POST /api/v1/usage`).

    [중요] 부르는 쪽은 `axmaster.work.gemini_report --remote` 다 — MCP 도구로는 열지 않는다
    (세션이 손으로 지어 낸 수치를 기록할 길을 만들지 않는다). 모양 판정은 서버 모델이 한다 —
    여기서는 **모르는 값을 0 으로 만들지 않고 빼기만** 한다.
    """
    source = str(args.get("source") or "").strip()
    if not source:
        raise ClientError("source 가 비었다 — 대시보드가 이 값으로 출처를 가른다")
    payload = {"source": source, "rc": int(args.get("rc") or 0),
               "seconds": round(float(args.get("seconds") or 0.0), 1)}
    for k in USAGE_STR_KEYS:
        v = str(args.get(k) or "").strip()
        if v:
            payload[k] = v
    inner = args.get("usage") if isinstance(args.get("usage"), dict) else {}
    tokens = {k: int(inner[k]) for k in USAGE_TOKEN_KEYS
              if isinstance(inner.get(k), int) and not isinstance(inner.get(k), bool)}
    if tokens:
        payload["usage"] = tokens
    cost = args.get("total_cost_usd")
    if isinstance(cost, (int, float)) and not isinstance(cost, bool):
        payload["total_cost_usd"] = float(cost)       # 없으면 서버가 cost_unknown 으로 남긴다
    return api("POST", "/api/v1/usage", payload)


FIX_STATES = ("open", "accepted", "dismissed", "stale", "applied", "failed")


def tool_list_fixes(api) -> dict:
    """번호 붙은 리뷰·플랜 요약 (`#630`) — 본문 없음. 사람이 번호를 고르는 자리다."""
    return api("GET", "/fixes")


def tool_get_fix(api, serial: str) -> dict:
    """번호 하나의 본문·항목 전체. [중요] 리뷰 시점의 지적이다 — 지금 main 대조는 `fix_flow check`."""
    s = (serial or "").strip()
    if not s:
        raise ClientError("serial 이 비었다 — 예: R12 · P3")
    return api("GET", "/fixes/" + urllib.parse.quote(s, safe=""))


def tool_update_fix_status(api, args: dict) -> dict:
    """항목 결정 기록 — **사용자가 정한 뒤에만** 부른다."""
    item = str(args.get("item") or "").strip()
    state = str(args.get("state") or "").strip()
    if not item:
        raise ClientError("item 이 비었다 — 리뷰는 행까지 R12-3, 플랜은 P3")
    if state not in FIX_STATES:
        raise ClientError(f"state 는 {' · '.join(FIX_STATES)} 중 하나다 (받은 값 {state!r})")
    payload = {"state": state}
    for k in ("note", "by", "branch", "commit"):
        v = str(args.get(k) or "").strip()
        if v:
            payload[k] = v
    return api("POST", "/fixes/" + urllib.parse.quote(item, safe="") + "/status", payload)


# ── 일감 흐름·플랜 (`#884` T6) — 8101 `/api/v1/issue/*`·`/api/v1/plan/*` 대행 ─────────────────
# [중요] **git 은 이 기계(요청자 worktree)가 하고 인프라는 기록만 한다** — 잠금·마감 추적·Redmine 노트.
#    마스터 로컬 흐름(`issue_flow`)과 같은 함수(`master/issue_infra.py`)가 서버에서 돈다.
#    프로젝트 태그는 `queue_api` 가 체크아웃 config 에서 붙인다(요청자가 고르는 값이 아니다).
# [주의] 서버 거절은 200 + ok:false + 사유다 — 그대로 돌려준다(장애로 바꾸지 않는다).

def _issue_id(v) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ClientError(f"issue_id 가 일감 번호가 아니다 — {v!r}")
    if n <= 0:
        raise ClientError(f"issue_id 는 양수다 — {n}")
    return n


def _str_list(v, name: str) -> list:
    if v is None:
        return []
    if isinstance(v, str) or not isinstance(v, list):
        raise ClientError(f"{name} 는 문자열 배열이다")
    return [str(x) for x in v]


def tool_issue_start(api, args: dict) -> dict:
    payload = {"issue_id": _issue_id(args.get("issue_id"))}
    if args.get("check_only"):
        payload["check_only"] = True
    for k in ("branch", "start_rev"):
        v = str(args.get(k) or "").strip()
        if v:
            payload[k] = v
    return api("POST", "/api/v1/issue/start", payload)


def issue_branch_end(issue_id: int, root: Path | None = None) -> str:
    """체크아웃의 git 에서 `issue/<N>` 끝 커밋을 구한다 (`#933`).

    🔴 마감 해시는 **세션이 적어 넣지 않는다** — `#929` 에서 에이전트가 짧은 해시만 보고 40자리를 지어내
    넘겼고 리뷰가 하루 넘게 멈췄다. 이 함수가 git 에서 읽은 값만 서버로 간다(서버도 다시 확인한다).
    """
    import re
    import subprocess
    cwd = root or Path.cwd()
    ref = f"refs/heads/issue/{issue_id}"
    try:
        cp = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--verify", "--quiet", ref + "^{commit}"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        raise ClientError(f"[git] `issue/{issue_id}` 끝을 구하지 못했다 — git 실행 실패({cwd}): "
                          f"{type(e).__name__}: {e}") from e
    sha = (cp.stdout or "").strip().lower()
    if cp.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ClientError(f"[git] 로컬 브랜치 `issue/{issue_id}` 가 {cwd} 에 없다(rc={cp.returncode}) — 마감 등록은 "
                          "브랜치를 지우기 전에 부른다. 이 도구는 끝 해시를 git 에서만 읽는다")
    return sha


def tool_issue_finish(api, args: dict, root: Path | None = None) -> dict:
    n = _issue_id(args.get("issue_id"))
    hashes = _str_list(args.get("hashes"), "hashes")
    subs = _str_list(args.get("subjects"), "subjects")
    end = issue_branch_end(n, root)
    given = str(args.get("end") or "").strip().lower()
    if given and given != end:
        raise ClientError(f"[git] 인자 end {given} 가 git 의 `issue/{n}` 끝 {end} 와 다르다 — 서버로 보내지 않았다. "
                          "해시 인자는 생략할 수 있다(도구가 git 에서 구한다)")
    payload = {"issue_id": n, "end": end}
    base = str(args.get("base") or "").strip()
    if base:
        payload["base"] = base
    if hashes:
        payload["hashes"] = hashes
    if subs:
        payload["subjects"] = subs
    if args.get("check_only"):
        payload["check_only"] = True
    print(f"[ax-client] issue_finish #{n} — end {end[:12]} (git issue/{n})"
          f" · base {'인자 ' + base[:12] if base else '서버 잠금'} · 보고 해시 {len(hashes)}개"
          f"{' · check_only' if payload.get('check_only') else ''}", file=sys.stderr)
    return api("POST", "/api/v1/issue/finish", payload)


def tool_issue_pause(api, args: dict) -> dict:
    payload = {"issue_id": _issue_id(args.get("issue_id"))}
    end = str(args.get("end") or "").strip()
    if end:
        payload["end"] = end
    return api("POST", "/api/v1/issue/pause", payload)


def tool_issue_cancel(api, args: dict) -> dict:
    payload = {"issue_id": _issue_id(args.get("issue_id")),
               "confirm": args.get("confirm") is True,
               "delete_branch": args.get("delete_branch") is True,
               "branch_exists": args.get("branch_exists") is not False,
               "commits": _str_list(args.get("commits"), "commits"),
               "local_only": _str_list(args.get("local_only"), "local_only")}
    return api("POST", "/api/v1/issue/cancel", payload)


def tool_plan_start(api, args: dict) -> dict:
    return api("POST", "/api/v1/plan/start", {"issue_id": _issue_id(args.get("issue_id"))})


def tool_plan_set(api, args: dict) -> dict:
    tasks = args.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ClientError("tasks 는 비지 않은 배열이다 — 원하는 전체 목록(표 순서)")
    why = str(args.get("why") or "").strip()
    if not why:
        raise ClientError("why 가 비었다 — 플랜을 왜 바꾸는지가 노트로 남는다")
    return api("POST", "/api/v1/plan/set", {"issue_id": _issue_id(args.get("issue_id")),
                                           "tasks": tasks, "why": why})


def tool_plan_transition(api, args: dict) -> dict:
    task_id = str(args.get("task_id") or "").strip()
    to = str(args.get("to") or "").strip()
    if not task_id or not to:
        raise ClientError("task_id 와 to 는 필수다")
    payload = {"issue_id": _issue_id(args.get("issue_id")), "task_id": task_id, "to": to}
    note = str(args.get("note") or "")
    if note.strip():
        payload["note"] = note
    return api("POST", "/api/v1/plan/transition", payload)


ISSUE_TOOLS = {"issue_start": tool_issue_start, "issue_finish": tool_issue_finish,
               "issue_pause": tool_issue_pause, "issue_cancel": tool_issue_cancel,
               "plan_start": tool_plan_start, "plan_set": tool_plan_set,
               "plan_transition": tool_plan_transition}


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


def capture_rag_request(root: Path, data: dict) -> dict | None:
    """실제 UserPromptSubmit 입력을 요청별로 보관한다. 최신 파일 추측은 하지 않는다."""
    if data.get("hook_event_name") != "UserPromptSubmit" or not isinstance(data.get("prompt"), str):
        return None
    from uuid import uuid4
    record = {"request_id": uuid4().hex, "user_request": data["prompt"],
              "user_request_source": "captured_client_input",
              "session_id": str(data.get("session_id") or ""), "task_type": "user_command"}
    directory = Path(root) / ".ax" / "rag_requests"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (record["request_id"] + ".json")
    with target.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False)
    return record


def rag_request_context(root: Path, request_id: str) -> dict:
    """지정 요청 하나만 읽는다. 다른 세션이나 최근 명령으로 대체하지 않는다."""
    from uuid import UUID
    try:
        key = UUID(request_id).hex
    except (ValueError, AttributeError, TypeError):
        return {}
    path = Path(root) / ".ax" / "rag_requests" / (key + ".json")
    if not path.is_file():
        return {}
    record = json.loads(path.read_text(encoding="utf-8"))
    if (record.get("request_id") != key or not isinstance(record.get("user_request"), str)
            or record.get("user_request_source") != "captured_client_input"):
        raise ClientError("RAG 사용자 원문 기록 형식 오류")
    return record


def tool_search_context(papi, query: str, tags=None, n: int = 5, *, cache=None,
                        task_type: str = "", user_request: str | None = None,
                        request_id: str = "", session_id: str = "", work_id: str = "",
                        caller: str = "client_mcp", user_request_source: str = "provided") -> dict:
    """통합 검색 — 8103 의 원전 라우트(`/api/v1/search/combined`) 프록시. 참조 지식이라
    [미연결] 시 마지막 정상 응답으로 폴백한다(`_stale` 표기)."""
    if not (query or "").strip():
        raise ClientError("query 가 비었다")
    payload = {"query": query.strip(), "n": max(1, int(n))}
    payload.update(caller=caller, task_type=task_type or "unclassified")
    for key, value in (("request_id", request_id), ("session_id", session_id), ("work_id", work_id)):
        if value:
            payload[key] = value
    if user_request is not None:
        payload.update(user_request=user_request, user_request_source=user_request_source)
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
    {"name": "get_orchestration", "description": "마스터 담당 기록과 워커 실행 모드를 조회한다. 담당 기록은 프로세스 생존 확인이 아니다.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "set_worker_mode", "description": "사용자 요청으로 워커 전역 모드를 변경한다. 다음 조각부터 적용되며 명시 인자·환경변수가 우선한다.",
     "inputSchema": {"type": "object", "required": ["mode", "why"], "properties": {
         "mode": {"type": "string", "enum": ["lane", "claude", "codex"]},
         "why": {"type": "string"}, "by": {"type": "string"}}}},
    {"name": "record_master_conductor", "description": "마스터 인수 확인 후 담당을 기록한다. 세션을 실행·종료하거나 잠그지 않는다. 예정된 교대를 완료로 기록하지 않는다.",
     "inputSchema": {"type": "object", "required": ["agent", "why"], "properties": {
         "agent": {"type": "string", "enum": ["claude", "codex", "antigravity", "agy"]},
         "why": {"type": "string"}, "by": {"type": "string"}}}},
    {"name": "register_work",
     "description": (
         "분산 작업을 마스터에 등재한다 (work + 태스크 N개) → `work_id` 를 돌려준다. "
         "마스터가 하는 것은 **큐 등록과 매니페스트 수집**이다. "
         "[중요] **골조는 마스터가 만들지 않는다** — 등재 뒤 네가 "
         "`task/<work_id>/base` 브랜치를 만들고 골조(.h + 컴파일되는 .cpp 스텁)를 "
         "**실물로 한 커밋**에 올려야 조각들이 같은 계약을 본다 (`#317`·`#319`). "
         "[중요] **`target_branch` 는 보내지 마라** — 비우면 마스터가 "
         "`task/<work_id>/base` 로 잡는다. `main` 을 넣으면 조각이 main 에서 갈라진다. "
         "[주의] **동기 호출이라 매니페스트 수집만큼 걸린다.** 타임아웃이 나도 서버는 계속 "
         "돈다 — **실패가 아니다.** 먼저 `list_works` 로 들어갔는지 보고, 있으면 "
         "재시도하지 마라(중복 등재가 된다). "
         "[주의] 거절은 200 + `ok:false` 로 온다 — `reason`·`hint`·`valid_fields` 를 "
         "읽고 고친다. "
         "🔴 [중요] **이 도구는 새 분산 작업만 만든다 (라운드 1).** 이미 있는 작업의 "
         "다음 라운드는 **개선요청**이다 — `improve_work(work_id, round=현재+1, specs)`. "
         "`work_id` 를 여기 실으면 거절한다."),
     "inputSchema": {"type": "object", "required": ["title", "specs"],
                     "properties": {
                         "title": {"type": "string", "description": "한국어 그대로 좋다"},
                         # 🔴 **지휘자를 이 work 에 못박는다** (`#389`). 안 주면 등재 시점의
                         #    전역값(`get_orchestration` 이 보여 주는 그것)이 박힌다.
                         "worker_mode": {
                             "type": "string", "enum": ["lane", "claude", "codex"],
                             "description": (
                                 "이 분산 작업의 **지휘자**. 안 주면 지금 전역 설정값이 "
                                 "박힌다. [중요] 한 번 박히면 그 work 의 조각은 전부 이 모드로 "
                                 "돈다 — 도중에 전역을 바꿔도 흔들리지 않는다. "
                                 "라운드가 올라가도 유지된다(비교가 성립해야 하므로).")},
                         # [중요] **필드를 정확히 적는다.** 실측 2026-08-30: 첫 실전 등재가
                         #    `summary` 라는 없는 필드를 실어 거절됐다 — 설명이 "항목마다
                         #    stem·classes·…" 식이라 목록이 닫혀 있는지 열려 있는지 알 수 없었다.
                         "specs": {"type": "array",
                                   "description": (
                                       "태스크 명세 목록. [중요] **아래 필드만** 쓴다 — "
                                       "다른 이름을 넣으면 거절된다. "
                                       "stem(필수, 조각 이름) · classes(문자열 배열) · "
                                       "contracts(**한 문자열** — 동결 인터페이스. 여러 줄이면 "
                                       "줄바꿈으로 이어 붙인다. 워커가 읽는 계약이다) · "
                                       "target_file/target_files(이 조각이 맡는 파일) · "
                                       "header_file · "
                                       "depends_on(**보통 비운다** — 클래스 단위 조각은 "
                                       "서로 **다른 파일**이라 병렬이다. 골조가 모든 클래스의 "
                                       "선언을 미리 다 만들어 두므로 조각끼리 기다릴 이유가 "
                                       "없다. **같은 파일**을 `[PSEUDO:N]` 뎁스로 쪼갤 때만 "
                                       "줄을 세운다) · "
                                       "requires(배열 — **능력 라우팅**이다. 추론에는 UE5 가 "
                                       "필요 없다; `ue5` 는 빌드·층3 판정을 누가 하느냐를 정한다. "
                                       "보통 비운다) · "
                                       "priority(정수) · source_files(배열) · "
                                       "depth_set(**정수 배열** — `[PSEUDO:N]` 의 N 목록, 예 [1,2]. "
                                       "쓸 일 없으면 아예 넣지 마라) · "
                                       "instruction(**보통 넣지 마라** — 골조를 마스터가 만들던 "
                                       "옛 경로의 재료다. 지금은 골조를 요청자가 만든다) · "
                                       "skeleton(감사용 사본. 워커는 작업 브랜치에서 읽는다)"),
                                   "items": {"type": "object",
                                             "required": ["stem"],
                                             "properties": {
                                                 "stem": {"type": "string"},
                                                 "classes": {"type": "array",
                                                             "items": {"type": "string"}},
                                                 "contracts": {"type": "string"},
                                                 "target_file": {"type": "string"},
                                                 "target_files": {"type": "array",
                                                                  "items": {"type": "string"}},
                                                 "header_file": {"type": "string"},
                                                 "depends_on": {"type": "array",
                                                                "items": {"type": "string"}},
                                                 "requires": {"type": "array",
                                                              "items": {"type": "string"}},
                                                 "priority": {"type": "integer"},
                                                 "instruction": {"type": "string"},
                                                 "source_files": {"type": "array",
                                                                  "items": {"type": "string"}}}}},
                         "original_request": {"type": "string",
                                              "description": "[중요] 사용자 원문 그대로"},
                         "target_repo": {"type": "string"},
                         # 🔴 **마일스톤** (`#652`) — 등재가 만드는 레드마인 이슈가 여기로
                         #    들어간다. 빼면 무버전이고, 그 상태로 24건이 쌓였다(실측).
                         "fixed_version": {
                             "type": "string",
                             "description": ("이 분산 작업의 레드마인 **마일스톤** 이름 "
                                             "(부분 일치 허용). `redmine_meta` 로 이 "
                                             "프로젝트의 목록을 보고 고르고, 맞는 것이 "
                                             "없으면 `redmine_create_version` 으로 먼저 "
                                             "만든다. [주의] 생략하면 이슈가 **무버전**으로 "
                                             "떨어진다 — 마스터가 대신 골라 주지 않는다")},
                         "target_branch": {"type": "string"}}}},
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
     "description": "마스터 RAG 통합 검색. 사용자 명령 작업이면 task_type=user_command와 "
                    "실제 명령 원문 user_request(요약 금지)를 보낸다. 입력 훅이 알려준 request_id가 "
                    "있으면 그것을 전달하면 캡처한 원문이 자동 연결된다. 같은 명령의 검색은 request_id를 "
                    "재사용한다. 자동 리뷰는 automatic_review 등으로 분류하고 원문을 만들지 않는다. "
                    "마스터 미연결이면 마지막 정상 응답에 _stale을 표시한다.",
     "inputSchema": {"type": "object", "required": ["query"],
                     "properties": {"query": {"type": "string"},
                                    "tags": {"type": "array", "items": {"type": "string"}},
                                    "n": {"type": "integer", "description": "결과 수 (기본 5)"},
                                    "task_type": {"type": "string"},
                                    "user_request": {"type": "string", "description": "사용자가 쓴 실제 명령 원문, 요약 금지"},
                                    "request_id": {"type": "string"},
                                    "session_id": {"type": "string"},
                                    "work_id": {"type": "string"}}}},
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
                    "우선순위·제목·본문도 바꿀 수 있다(비우면 그대로). "
                    "상태 이름은 실재하는 것만: 신규·진행·해결·검토·완료. "
                    "AX 인프라(ax-cluster) 일감은 마스터가 검증 뒤 완료로 닫을 수 있다. "
                    "게임·분산 작업 일감의 완료는 사람(.33)의 판단이다.",
     "inputSchema": {"type": "object", "required": ["issue_id", "notes"],
                     "properties": {"issue_id": {"type": "integer"},
                                    "notes": {"type": "string"},
                                    "status_name": {"type": "string"},
                                    "done_ratio": {"type": "integer"},
                                    "fixed_version": {"type": "string",
                                                      "description": "마일스톤 이름 (부분 일치). 사후 스탬프용"},
                                    "parent_issue_id": {"type": "integer",
                                                        "description": "부모 이슈 번호 (바꾸기·붙이기)"},
                                    "clear_parent": {"type": "boolean",
                                                     "description": "true 면 부모를 떼어 낸다. "
                                                                    "parent_issue_id 와 함께 주면 거절"},
                                    "priority_name": {"type": "string",
                                                      "description": "낮음·보통·높음 — redmine_meta 로 확인"},
                                    "subject": {"type": "string",
                                                "description": "새 제목"},
                                    "description": {"type": "string",
                                                    "description": "본문 전체를 바꾼다"}}}},
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
                    "말고 여기서 확인한다 — 이 환경은 한국어이고 「반려」에 해당하는 상태가 없다. "
                    "마일스톤 목록은 **이 체크아웃의 프로젝트 것**이다(응답의 versions_project "
                    "가 무엇을 봤는지 말한다).",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "redmine_get_wiki_page",
     "description": "이 체크아웃 프로젝트의 Redmine 위키 본문 전체와 version 을 조회한다. "
                    "교체 전에 반드시 읽어 기존 내용을 보존한다. 마스터 경유이며 키는 필요 없다.",
     "inputSchema": {"type": "object", "required": ["title"],
                     "additionalProperties": False,
                     "properties": {"title": {"type": "string", "minLength": 1}}}},
    {"name": "redmine_put_wiki_page",
     "description": "Redmine 위키를 작성·수정한다. 기본 append 는 기존 본문을 읽고 보존해 "
                    "추가한다. replace 는 기존 페이지 조회에서 받은 version 과 전체 본문이 "
                    "필수다. 없는 페이지는 생성한다. 마스터가 쓰기 후 되읽어 본문을 검증하며 "
                    "충돌·검증 실패는 자동 재시도하지 않는다. 프로젝트는 체크아웃 태그로 고정된다.",
     "inputSchema": {"type": "object", "required": ["title", "text"],
                     "additionalProperties": False,
                     "properties": {"title": {"type": "string", "minLength": 1},
                                    "text": {"type": "string", "minLength": 1},
                                    "mode": {"type": "string", "enum": ["append", "replace"],
                                             "default": "append"},
                                    "version": {"type": "integer", "minimum": 1},
                                    "comments": {"type": "string"}}}},
    {"name": "redmine_create_version",
     "description": "마일스톤(레드마인 버전)을 새로 만든다 (마스터 경유). 만들 프로젝트는 이 "
                    "체크아웃의 프로젝트 태그가 정한다 — 고를 수 없다. redmine_create_issue 의 "
                    "fixed_version 에 줄 값이 아직 없을 때 여기서 먼저 만든다. "
                    "[주의] 같은 이름이 있으면 만들지 않고 그 id 를 돌려준다(existing: true).",
     "inputSchema": {"type": "object", "required": ["name"],
                     "properties": {"name": {"type": "string",
                                             "description": "마일스톤 이름 (예: `마일스톤 2 — 전투 재설계`)"},
                                    "due_date": {"type": "string",
                                                 "description": "`YYYY-MM-DD` 또는 생략"},
                                    "description": {"type": "string"},
                                    "status": {"type": "string",
                                               "description": "open(기본) · locked · closed"}}}},
    {"name": "redmine_create_issue",
     "description": "레드마인 이슈를 새로 만든다 (마스터 경유). 등재될 레드마인 프로젝트는 "
                    "요청의 프로젝트 태그가 정한다 (#293 — 게임 프로젝트가 늘면 자리도 늘어난다). "
                    "AX 인프라 건이면 제목에 [AX] 접두어를 쓰고 ax-cluster(id 3) 에 둔다. "
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
    {"name": "redmine_update_version",
     "description": "마일스톤(레드마인 버전)의 이름·설명·마감일을 고친다 (마스터 경유). "
                    "대상은 **지금 이름**으로 고르고 **정확히 일치해야 한다** — 부분 일치를 "
                    "허용하면 「마일스톤 1」을 고치려다 「마일스톤 10」을 고친다. "
                    "redmine_meta 로 정확한 이름을 먼저 확인하라. "
                    "[주의] description·due_date 는 안 주면 안 바뀌고, 빈 문자열이면 비운다. "
                    "status 도 안 주면 안 바뀐다 — 잠그기·닫기는 사람의 결정이다.",
     "inputSchema": {"type": "object", "required": ["name"],
                     "properties": {"name": {"type": "string",
                                             "description": "지금 이름 (정확 일치)"},
                                    "new_name": {"type": "string",
                                                 "description": "새 이름. 생략하면 안 바꾼다"},
                                    "description": {"type": "string",
                                                    "description": "설명 (최대 255자). 빈 문자열이면 비운다"},
                                    "due_date": {"type": "string",
                                                 "description": "`YYYY-MM-DD`. 빈 문자열이면 비운다"},
                                    "status": {"type": "string",
                                               "description": "open · locked · closed. 생략하면 안 바꾼다"}}}},
    {"name": "redmine_delete_version",
     "description": "마일스톤(레드마인 버전)을 지운다 (마스터 경유). **되돌릴 수 없다.** "
                    "🔴 confirm 없이 부르면 **지우지 않고** 무엇이 지워질지만 알려 준다 — "
                    "그것을 사람에게 보이고 승인을 받은 뒤 confirm=true 로 다시 불러라. "
                    "붙은 이슈가 있으면 몇 건인지 말하고 거절한다(대신 떼어 주지 않는다). "
                    "대상은 지금 이름으로 고르고 **정확히 일치해야 한다**.",
     "inputSchema": {"type": "object", "required": ["name"],
                     "properties": {"name": {"type": "string",
                                             "description": "지울 마일스톤 이름 (정확 일치)"},
                                    "confirm": {"type": "boolean",
                                                "description": "🔴 사람의 승인을 받은 뒤에만 true"}}}},
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
    {"name": "list_fixes",
     "description": "자동 리뷰·주간 플랜의 **번호 목록**(R12 · P3)을 본다 — 번호·날짜·작성자·항목 수·"
                    "심각도 건수·결정 상태. 본문은 없다. 사용자가 번호를 고르면 `get_fix` 로 받는다. "
                    "[중요] 적용 여부는 사람이 정한다 — 리뷰·플랜은 제안이지 지시가 아니다(원전 원칙). "
                    "레드마인 `#N` 과 다른 번호다.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "get_fix",
     "description": "번호 하나(R12 · P3)의 리뷰·플랜을 **본문과 항목 전체**로 받는다 — 리뷰는 행마다 "
                    "파일·라인·설명·권장 수정과 항목 번호(R12-3), 플랜은 대상 파일과 개선안. "
                    "[주의] 리뷰 시점의 지적이다 — 지금 main 에 그대로 맞는지는 `ax-fix` 스킬의 "
                    "대조 단계(`fix_flow.py check`)가 확인한다.",
     "inputSchema": {"type": "object", "required": ["serial"], "properties": {
         "serial": {"type": "string", "description": "R12 · P3"}}}},
    {"name": "update_fix_status",
     "description": "수정 항목 하나의 결정을 마스터에 기록한다 — accepted(적용하기로) · dismissed(기각) · "
                    "stale(지금 main 에 해당 없음) · applied(fix 브랜치에 커밋함) · failed · open(되돌리기). "
                    "[중요] **사용자가 정한 뒤에만** 부른다. 플랜(P3)은 applied/dismissed 가 플랜 MD 의 "
                    "status 도 acted/dismissed 로 맞춘다. 코드·브랜치는 건드리지 않는다.",
     "inputSchema": {"type": "object", "required": ["item", "state"], "properties": {
         "item": {"type": "string", "description": "리뷰는 행까지 R12-3 · 플랜은 P3"},
         "state": {"type": "string", "enum": list(FIX_STATES)},
         "note": {"type": "string", "description": "왜 — 판단 근거 1~3줄"},
         "by": {"type": "string"},
         "branch": {"type": "string", "description": "적용했으면 fix/R12"},
         "commit": {"type": "string"}}}},
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

# ── 🔴 **개선요청** — 등재와 같은 명세, 다른 뜻 (사용자 결정 2026-09-05) ──────────────────
#
#     ① 등록      register_work   새 분산 작업          round = 1
#     ② 개선요청   improve_work    이미 있는 work        round = 현재 + 1
#     ③ 마감      ax-review → finalize_work            main 머지 · 레드마인 완료
#
# [중요] **`specs` 스키마를 복사하지 않는다** — 등재의 것을 그대로 참조한다. 조각 명세의 규칙은
#    하나여야 하고, 갈라 두면 한쪽만 고치는 사고가 난다(등재/개선요청을 가른 이유와 같은 논리).
def _register_specs_schema() -> dict:
    for _t in TOOLS:
        if _t["name"] == "register_work":
            return _t["inputSchema"]["properties"]["specs"]
    raise KeyError("register_work 도구가 없다 — 개선요청이 참조할 명세 스키마가 사라졌다")


TOOLS.append(
    {"name": "improve_work",
     "description": (
         "🔴 **이미 있는 분산 작업의 다음 라운드를 연다** (개선요청). ⑺ 에서 서브 브랜치를 "
         "작업 브랜치에 머지하고 검사한 뒤 **더 고칠 것이 있으면** 이것을 부른다 — 새 등재가 "
         "아니다. 라운드가 +1 되고, 서브 브랜치는 `task/<work_id>/r<N>/<조각>` 으로 갈리며, "
         "⑺ 의 머지 대상도 **그 라운드 조각만**이다. 기록은 그 work 의 레드마인 이슈에 노트로 "
         "쌓인다(라운드마다 새 이슈를 만들지 않는다). "
         "[중요] **`round` 는 확인용이다** — 값은 큐가 이미 안다(현재+1). `get_work` 로 현재 "
         "라운드를 보고 +1 을 실어라. 어긋나면 큐가 **거절**한다(맞추지 않는다) — 너와 큐가 "
         "서로 다른 라운드를 보고 있다는 뜻이기 때문이다. "
         "일반 개선은 `ready_for_review` 에서만 가능하다. 골조 실패 라운드는 재작업 통합 "
         "전진 후 `rework=true` 와 수정 골조의 `expected_base_commit` 을 함께 실어 연다. "
         "통합 기준에서 이어진 골조인지 확인하며 실패 이력은 유지한다. "
         "[주의] **`target_branch` 는 보통 비운다** — 비우면 큐에 저장된 작업 브랜치를 쓴다. "
         "지어내면 ⑺ 이 전진시킨 브랜치가 원복된다. "
         "[주의] 골조는 여기서도 **네가** 만든다 — 전진한 `.h`/`.cpp` 에 `[PSEUDO]` 지시 주석을 "
         "남겨 작업 브랜치에 커밋하고 부른다. **`[FEEDBACK]` 은 쓰지 마라**(게이트가 막는다). "
         "마감(`main` 머지)은 또 다른 호출이다 — `ax-review` 의 `finalize`."),
     "inputSchema": {"type": "object", "required": ["work_id", "round", "specs"],
                     "properties": {
                         "work_id": {"type": "string",
                                     "description": "다시 열 분산 작업 (`list_works` 로 찾는다)"},
                         "round": {"type": "integer",
                                   "description": ("🔴 이번에 여는 라운드 = **현재 + 1** (2 이상). "
                                                   "확인용이라 어긋나면 거절된다")},
                         "specs": _register_specs_schema(),
                         "rework": {"type": "boolean", "default": False,
                                    "description": "골조 실패 라운드의 통합 전진 후 재작업 개선요청"},
                         "expected_base_commit": {"type": "string",
                                    "description": "통합본에서 수정한 골조의 현재 원격 커밋"},
                         "worker_mode": {"type": "string", "enum": ["lane", "claude", "codex"],
                                         "description": "이번 라운드의 실행 모드. 생략하면 기존 값을 유지한다"},
                         "target_branch": {"type": "string",
                                           "description": "보통 비운다 — 저장된 작업 브랜치를 쓴다"}}}})


# ── 일감 흐름·플랜 (`#884` T6) — 설명은 사실만 적는다. 절차·승인 지점은 `ax-issue` 스킬이 말한다 ──
_SHA_DESC = "40자리 커밋 해시"
TOOLS.extend([
    {"name": "plan_start",
     "description": "일감의 시작 판정과 이 프로젝트의 7단계 표를 돌려준다(읽기). 판정: no_spec · plan_needed · "
                    "plan_invalid · plan_violations · resume · next · blocked · plan_done. ok 는 resume·next "
                    "일 때만 참이다. 응답의 next_action 이 그 판정의 다음 행동 문장이다.",
     "inputSchema": {"type": "object", "required": ["issue_id"], "properties": {
         "issue_id": {"type": "integer", "description": "Redmine 일감 번호"}}}},
    {"name": "plan_set",
     "description": "일감 본문의 플랜 영역(ax:plan)을 등록하거나 태스크를 추가·편집한다. tasks 는 원하는 전체 "
                    "목록이다. state·evidence 는 받지 않는다 — 새 태스크는 「대기」, 기존 태스크는 본문 값을 "
                    "유지한다. 시작된 태스크는 목록에서 뺄 수 없다. why 는 노트로 남는다(필수).",
     "inputSchema": {"type": "object", "required": ["issue_id", "tasks", "why"], "properties": {
         "issue_id": {"type": "integer"},
         "tasks": {"type": "array", "items": {"type": "object", "required": ["id", "goal"], "properties": {
             "id": {"type": "string", "description": "T1 · T2 …"},
             "goal": {"type": "string"},
             "target": {"type": "string", "description": "대상 파일·영역"},
             "deps": {"type": "array", "items": {"type": "string"}, "description": "선행 태스크 id"},
             "check": {"type": "string", "description": "검증 방법"},
             "steps": {"type": "array", "items": {"type": "integer"},
                       "description": "이 태스크가 하는 조건부 단계 번호(plan_start 의 steps 표)"}}}},
         "why": {"type": "string", "description": "플랜을 바꾸는 이유 — 사용자 결정"}}}},
    {"name": "plan_transition",
     "description": "플랜 태스크 하나의 상태를 바꾼다 — 상태를 바꾸는 유일한 쓰기. to: 작업중 · 완료 · 차단 · "
                    "해당없음 · 대기. 완료는 근거(커밋 해시·검사 결과), 차단·해당없음은 사유가 note 에 필수다. "
                    "「작업중」은 이 프로젝트의 일감 잠금을 보고, 다른 일감이 활성이면 거절된다. "
                    "응답의 next 가 다음 판정이다.",
     "inputSchema": {"type": "object", "required": ["issue_id", "task_id", "to"], "properties": {
         "issue_id": {"type": "integer"},
         "task_id": {"type": "string"},
         "to": {"type": "string", "enum": ["작업중", "완료", "차단", "해당없음", "대기"]},
         "note": {"type": "string"}}}},
    {"name": "issue_start",
     "description": "일감 작업 시작을 마스터에 기록한다 — 플랜 판정(ok 가 아니면 거절) · 프로젝트 트윈의 일감 "
                    "잠금(다른 일감이 활성이면 거절) · Redmine 시작 리비전 노트(신규 일감은 「진행」으로). "
                    "check_only=true 는 판정과 잠금 상태만 돌려주고 아무것도 쓰지 않는다. 기록 호출은 "
                    "branch=issue/<N> 과 그 브랜치의 시작 리비전(start_rev, origin/main 해시)을 싣는다. "
                    "같은 일감이 보류 중이면 잠금을 재개하고 「재개」 노트를 남긴다(resumed). "
                    "git(worktree·브랜치)은 이 도구가 만지지 않는다.",
     "inputSchema": {"type": "object", "required": ["issue_id"], "properties": {
         "issue_id": {"type": "integer"},
         "check_only": {"type": "boolean", "default": False},
         "branch": {"type": "string", "description": "issue/<N>"},
         "start_rev": {"type": "string", "description": _SHA_DESC + " — worktree 를 만든 origin/main"}}}},
    {"name": "issue_finish",
     "description": "일감 종료를 마스터에 기록한다 — issue/<N> 을 origin main 에 push 한 뒤, 로컬 브랜치를 지우기 "
                    "전에 부른다. 일감 번호만 넘긴다: 끝 해시는 이 도구가 체크아웃의 git(issue/<N>)에서 읽고, "
                    "범위의 해시 목록·제목은 서버가 저장소에서 구한다(#933). 서버는 그 범위가 실제 커밋이고 main 에 "
                    "있는지 확인한 뒤에만 마감 추적(issue_track)을 등록하고, 색인기 리뷰를 잇고, 등록이 성공했을 "
                    "때만 일감 잠금을 풀고 Redmine 「리뷰 요청」 노트와 함께 일감을 「완료」·100 으로 닫는다"
                    "(#889 — main 적용 = 마감, closed 로 알린다). 범위가 git 과 다르거나 조회가 실패하면 "
                    "step=verify 로 거절되고 아무것도 바뀌지 않는다. check_only=true 는 쓰기 없이 서버가 구한 "
                    "범위·커밋 목록만 돌려준다. 해시별 리뷰와 종합 리뷰 결과는 리뷰 큐가 같은 일감에 노트로만 "
                    "남긴다. 등록이 실패하면 잠금이 남고 일감은 열린 채 why 에 사유가 온다. git 은 읽기만 한다.",
     "inputSchema": {"type": "object", "required": ["issue_id"], "properties": {
         "issue_id": {"type": "integer"},
         "check_only": {"type": "boolean", "description": "true 면 범위 확인·도출만(쓰기 0)"},
         "base": {"type": "string", "description": _SHA_DESC + " — 시작 리비전. 생략하면 서버 잠금의 시작 리비전"
                                                              "(rebase 등으로 달라졌을 때만 싣는다)"},
         "end": {"type": "string", "description": _SHA_DESC + " — 생략한다. 실으면 git 의 issue/<N> 끝과 "
                                                             "대조만 하고 다르면 거절한다"},
         "hashes": {"type": "array", "items": {"type": "string"},
                    "description": "생략한다. 실으면 서버가 git 에서 구한 목록과 대조만 하고 다르면 거절한다"},
         "subjects": {"type": "array", "items": {"type": "string"},
                      "description": "생략한다 — 제목은 서버가 git 에서 구한다"}}}},
    {"name": "issue_pause",
     "description": "진행 중인 일감을 보류로 기록한다 — 프로젝트 트윈의 잠금을 보류로 옮기고 Redmine 「보류」 "
                    "노트를 남긴다. 브랜치·worktree 는 그대로 남는다. 재개는 issue_start 다.",
     "inputSchema": {"type": "object", "required": ["issue_id"], "properties": {
         "issue_id": {"type": "integer"},
         "end": {"type": "string", "description": _SHA_DESC + " — 보류 시점의 issue/<N> 끝"}}}},
    {"name": "issue_cancel",
     "description": "일감 작업 취소. confirm=false(기본)는 잠금 상태와 보낸 커밋 목록으로 미리보기만 한다(쓰기 0). "
                    "confirm=true 는 잠금 해제 → Redmine 「취소」 노트(커밋 목록·브랜치 운명)를 남긴다. "
                    "응답의 branch_delete_allowed 가 참일 때만 브랜치 삭제가 노트와 일치한다. "
                    "git(worktree·브랜치)은 이 도구가 만지지 않는다.",
     "inputSchema": {"type": "object", "required": ["issue_id"], "properties": {
         "issue_id": {"type": "integer"},
         "confirm": {"type": "boolean", "default": False},
         "delete_branch": {"type": "boolean", "default": False},
         "branch_exists": {"type": "boolean", "default": True},
         "commits": {"type": "array", "items": {"type": "string"},
                     "description": "origin/main 밖 커밋 — 줄마다 '<40자리 해시> <제목>'"},
         "local_only": {"type": "array", "items": {"type": "string"},
                        "description": "원격 어디에도 없는 커밋 해시"}}}},
])


# 요청자 온톨로지 관리(`#898`) — 판정·파일 쓰기는 인증된 큐의 기존 마스터 함수가 한다.
# 프로젝트 인자는 노출하지 않는다. queue_api 가 체크아웃 태그를 싣고 서버가 마운트와 대조한다.
MANAGEMENT_ROUTES = {
    "resolve_terms": "/api/v1/thesaurus/resolve",
    "create_domain": "/api/v1/ontology/create-domain",
    "edit_ontology_item": "/api/v1/ontology/edit-item",
    "remove_ontology_item": "/api/v1/ontology/remove-item",
    "lock_ontology_item": "/api/v1/ontology/lock-item",
    "list_locked": "/api/v1/ontology/list-locked",
    "unassigned_classes": "/api/v1/ontology/unassigned-classes",
    "sync_ontology": "/api/v1/ontology/sync",
    "list_workshops": "/api/v1/workshops/list",
    "check_workshops_clean": "/api/v1/workshops/check-clean",
    "edit_domain_field": "/api/v1/ontology/edit-domain-field",
    "list_log_tags": "/api/v1/ontology/list-log-tags",
    "set_log_tag": "/api/v1/ontology/set-log-tag",
    "remove_log_tag": "/api/v1/ontology/remove-log-tag",
    "staging_begin": "/api/v1/ontology/staging-begin",
    "staging_commit": "/api/v1/ontology/staging-commit",
    "staging_discard": "/api/v1/ontology/staging-discard",
    "staging_status": "/api/v1/ontology/staging-status",
    "rename_domain": "/api/v1/ontology/rename-domain",
    "rename_class": "/api/v1/ontology/rename-class",
}
TOOLS.extend([
    {"name": "resolve_terms",
     "description": "용어의 시소러스 등록 여부와 미등록 후보·질문을 마스터에서 조회한다. 반환된 후보를 근거와 함께 사용자에게 묻고, 확인 전에는 별칭을 등록하지 않는다.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["terms"], "properties": {
         "terms": {"type": "array", "items": {"type": "string"}}}}},
    {"name": "create_domain",
     "description": "사용자가 선택한 도메인의 씨앗 MD를 마스터에 만든다. 기존 도메인은 덮지 않는다. 이름은 한글도 허용하며 공백·경로 위험 문자는 거부한다.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["name"], "properties": {
         "name": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}, "default": []},
         "parent": {"type": "string", "default": ""}, "summary": {"type": "string", "default": ""}}}},
    {"name": "edit_ontology_item",
     "description": "사용자가 확인한 온톨로지 항목을 마스터에서 얕은 병합으로 수정하고 검수 잠근다. 없는 항목은 생성하지 않는다.",
     "inputSchema": {"type": "object", "additionalProperties": False,
                     "required": ["domain", "kind", "name", "patch"], "properties": {
         "domain": {"type": "string"}, "kind": {"type": "string"}, "name": {"type": "string"},
         "patch": {"type": "object"}}}},
    {"name": "remove_ontology_item",
     "description": "선택한 온톨로지 항목을 마스터에서 삭제한다. 잠긴 항목은 force 없이 삭제하지 않는다. force=true는 사용자에게 추가 확인한 뒤에만 쓴다.",
     "inputSchema": {"type": "object", "additionalProperties": False,
                     "required": ["domain", "kind", "name"], "properties": {
         "domain": {"type": "string"}, "kind": {"type": "string"}, "name": {"type": "string"},
         "force": {"type": "boolean", "default": False}}}},
    {"name": "lock_ontology_item",
     "description": "사용자가 선택한 온톨로지 항목의 검수 잠금을 걸거나 푼다. 실제 처리는 마스터가 한다.",
     "inputSchema": {"type": "object", "additionalProperties": False,
                     "required": ["domain", "kind", "name", "locked"], "properties": {
         "domain": {"type": "string"}, "kind": {"type": "string"}, "name": {"type": "string"},
         "locked": {"type": "boolean"}}}},
    {"name": "list_locked",
     "description": "체크아웃 프로젝트의 검수 잠긴 온톨로지 항목을 인증된 마스터 입구에서 조회한다.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "domain": {"type": "string", "default": ""}}}},
    {"name": "unassigned_classes",
     "description": "어느 도메인에도 배정되지 않은 클래스를 보여준다. 자동 편입·승급은 하지 않는다.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "sample": {"type": "integer", "default": 20}}}},
    {"name": "sync_ontology",
     "description": "온톨로지 경로·선언의 정합성 계획을 조회한다. apply=false가 기본이며 실제 적용은 사용자가 선택한 뒤에만 한다.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "domain": {"type": "string", "default": ""}, "apply": {"type": "boolean", "default": False}}}},
    {"name": "list_workshops",
     "description": "이 체크아웃 프로젝트에 등록된 작업장과 역할을 인증된 마스터 입구에서 조회한다.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}}},
    {"name": "check_workshops_clean",
     "description": "이 체크아웃 프로젝트 작업장의 현재 배달 가능 상태(dispatchable)와 차단 사유를 조회한다. 파일을 정리하거나 배달하지 않는다.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}}},
    {"name": "edit_domain_field",
     "description": "도메인 MD의 지정한 필드만 마스터에서 수정한다. 생략·null은 유지하며 빈 목록은 목록을 지운다. tags는 전체 치환이므로 기존 한국어 태그를 확인한 뒤 사용자 선택대로 보낸다.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["domain"], "properties": {
         "domain": {"type": "string"}, "parent_domain": {"type": ["string", "null"]},
         "status": {"type": ["string", "null"]}, "summary": {"type": ["string", "null"]},
         "tags": {"type": ["array", "null"], "items": {"type": "string"}},
         "collaborates_with": {"type": ["array", "null"], "items": {"type": "string"}}}}},
    {"name": "list_log_tags",
     "description": "도메인의 실증 테스트용 로그 태그·CVar 매핑을 마스터에서 조회한다.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["domain"], "properties": {
         "domain": {"type": "string"}}}},
    {"name": "set_log_tag",
     "description": "실제 코드에 CVar와 태깅 로그를 구현한 뒤 사용자가 확인한 매핑만 등록·수정한다. related_invariants 생략·null은 기존 연결을 유지하고 빈 목록은 연결을 지운다.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["domain", "tag", "cvar"], "properties": {
         "domain": {"type": "string"}, "tag": {"type": "string"}, "cvar": {"type": "string"},
         "related_invariants": {"type": ["array", "null"], "items": {"type": "string"}}}}},
    {"name": "remove_log_tag",
     "description": "사용자에게 삭제할 매핑을 확인받은 뒤 도메인의 로그 태그 한 건을 삭제한다.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["domain", "tag"], "properties": {
         "domain": {"type": "string"}, "tag": {"type": "string"}}}},
    {"name": "staging_begin",
     "description": "도메인 온톨로지의 편집 세션을 마스터에서 시작한다. Git 작업과 별개다.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["domain"], "properties": {
         "domain": {"type": "string"}}}},
    {"name": "staging_commit",
     "description": "사용자가 검토한 도메인 편집 세션을 마스터에서 확정한다. 세션 시작 뒤 라이브 변경 여부는 결과로 알리며 자동 차단하지 않는다. Git 커밋이 아니다.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["domain"], "properties": {
         "domain": {"type": "string"}}}},
    {"name": "staging_discard",
     "description": "사용자에게 확인받은 도메인 편집 세션을 폐기한다. 버리는 세션 변경을 먼저 사용자에게 알린다.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["domain"], "properties": {
         "domain": {"type": "string"}}}},
    {"name": "staging_status",
     "description": "도메인 편집 세션 상태를 마스터에서 조회한다. domain 생략·빈 문자열은 전체 도메인이다.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "domain": {"type": "string", "default": ""}}}},
    {"name": "rename_domain",
     "description": "도메인 이름 변경 계획을 조회한다(apply=false 기본). 계획을 사용자에게 보여주고 승인받은 뒤에만 apply=true로 현재 계획을 다시 계산하여 적용한다. 계획 파일 경로를 입력받지 않는다.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["old", "new"], "properties": {
         "old": {"type": "string"}, "new": {"type": "string"},
         "apply": {"type": "boolean", "default": False}}}},
    {"name": "rename_class",
     "description": "도메인 안 클래스 이름 변경 계획을 조회한다(apply=false 기본). 사용자 승인 뒤에만 apply=true로 현재 계획을 다시 계산하여 적용한다. 게임 소스를 바꾸는 기능이 아니다.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["domain", "old", "new"], "properties": {
         "domain": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"},
         "apply": {"type": "boolean", "default": False}}}},
])


def tool_manage_project(api, name: str, args: dict) -> dict:
    """얇은 8101 대행. 쓰기·실시간 상태는 캐시나 실패 폴백을 거치지 않는다."""
    schema = next(t["inputSchema"] for t in TOOLS if t["name"] == name)
    props = schema["properties"]
    if not isinstance(args, dict):
        raise ClientError("관리 도구 인자는 객체여야 한다")
    unknown = set(args) - set(props)
    if unknown:
        raise ClientError("관리 도구에 알 수 없는 인자: " + ", ".join(sorted(unknown)))
    missing = set(schema.get("required", [])) - set(args)
    if missing:
        raise ClientError("관리 도구 필수 인자가 없다: " + ", ".join(sorted(missing)))
    payload = {key: spec["default"] for key, spec in props.items() if "default" in spec}
    payload.update(args)
    types = {"string": str, "boolean": bool, "integer": int, "array": list, "object": dict}
    for key, value in payload.items():
        spec = props[key]
        kind = spec["type"]
        if isinstance(kind, list):
            if value is None and "null" in kind:
                continue
            kind = next(t for t in kind if t != "null")
        expected = types[kind]
        if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
            raise ClientError(f"{key} 인자는 {spec['type']} 형식이어야 한다")
        if kind == "array" and not all(isinstance(v, str) for v in value):
            raise ClientError(f"{key} 인자는 문자열 목록이어야 한다")
        if (key in schema.get("required", []) and key != "cvar"
                and isinstance(value, str) and not value.strip()):
            raise ClientError(f"{key} 인자가 비었다")
    return api("POST", MANAGEMENT_ROUTES[name], payload)


def dispatch_tool(name: str, args: dict, *, api=None, papi=None, cache=None,
                  root: Path | None = None) -> dict:
    """도구 실행. `api`/`papi`/`cache` 주입은 테스트 자리 — 실전은 config·token 에서 만든다."""
    args = args or {}
    if name in MANAGEMENT_ROUTES:
        return tool_manage_project(api or queue_api(root), name, args)
    controls = {"get_orchestration": ("GET", "/control/orchestration"),
                "set_worker_mode": ("POST", "/control/worker-mode"),
                "record_master_conductor": ("POST", "/control/master-conductor")}
    if name in controls:
        method, path = controls[name]
        return (papi or projects_write_api(root))(method, path, args if method == "POST" else None)
    # [중요] **표면이 다르다** — 등재는 8103 의 토큰 잠긴 `/work/register` 로 간다 (`#336` ④).
    #    큐(8101)도 아니고 8103 의 공개 `/api/v1/*` 도 아니다. 그래서 큐 호출자를 만들기 전에
    #    여기서 가른다 — 섞으면 다음에 추가되는 도구가 어느 표면인지 호출부가 판단하게 된다.
    if name == "register_work":
        return tool_register_work(None, args, root=root)
    if name == "improve_work":
        return tool_improve_work(None, args, root=root)
    if name == "issue_finish":                      # `#933` — 끝 해시는 체크아웃의 git 에서 구한다
        return tool_issue_finish(api or queue_api(root), args, root=root)
    if name in ISSUE_TOOLS:                         # 일감 흐름·플랜 (`#884` T6) — 큐(8101) 대행
        return ISSUE_TOOLS[name](api or queue_api(root), args)
    if name in ("list_works", "get_work", "redmine_note", "log_writer_signal", "log_history",
                "add_object_alias", "mark_not_a_class", "redmine_list_issues",
                "redmine_get_issue", "redmine_meta", "redmine_create_issue",
                "redmine_create_version", "redmine_update_version",
                "redmine_delete_version", "redmine_link_commit",
                "redmine_get_wiki_page", "redmine_put_wiki_page",
                # 레시피·안티패턴 읽기 — 큐 대행이므로 같은 자리다 (`#267`)
                "find_recipes", "get_anti_patterns",
                # history 읽기 (`#306`) — 쓰기(`log_history`)와 같은 대행 자리
                "find_history",
                # 수정 항목 (`#630`) — 8101 `/fixes` 대행
                "list_fixes", "get_fix", "update_fix_status"):
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
        if name == "list_fixes":
            return tool_list_fixes(a)
        if name == "get_fix":
            return tool_get_fix(a, str(args.get("serial") or ""))
        if name == "update_fix_status":
            return tool_update_fix_status(a, args)
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
        if name in ("redmine_get_wiki_page", "redmine_put_wiki_page"):
            allowed = ({"title"} if name == "redmine_get_wiki_page" else
                       {"title", "text", "mode", "version", "comments"})
            if set(args) - allowed:
                raise ClientError("위키 도구에 허용되지 않은 인자가 있다 — 프로젝트는 체크아웃 태그로 정한다")
            if name == "redmine_get_wiki_page":
                return tool_redmine_get_wiki_page(a, args.get("title"))
            return tool_redmine_put_wiki_page(
                a, args.get("title"), args.get("text"), mode=args.get("mode", "append"),
                version=args.get("version"), comments=args.get("comments", ""))
        if name == "redmine_create_version":
            return tool_redmine_create_version(a, str(args.get("name") or ""),
                                               due_date=str(args.get("due_date") or ""),
                                               description=str(args.get("description") or ""),
                                               status=str(args.get("status") or "open"))
        if name == "redmine_create_issue":
            return tool_redmine_create_issue(a, str(args.get("subject") or ""),
                                             str(args.get("description") or ""),
                                             str(args.get("tracker_name") or ""),
                                             str(args.get("priority_name") or ""),
                                             str(args.get("fixed_version") or ""),
                                             args.get("parent_issue_id"))
        if name == "redmine_update_version":
            return tool_redmine_update_version(
                a, str(args.get("name") or ""),
                new_name=str(args.get("new_name") or ""),
                description=args.get("description"),
                due_date=args.get("due_date"),
                status=str(args.get("status") or ""))
        if name == "redmine_delete_version":
            return tool_redmine_delete_version(a, str(args.get("name") or ""),
                                               confirm=bool(args.get("confirm")))
        if name == "redmine_link_commit":
            return tool_redmine_link_commit(a, args.get("issue_id"),
                                            str(args.get("commit_hash") or ""),
                                            str(args.get("message") or ""))
        return tool_redmine_note(a, args.get("issue_id"), str(args.get("notes") or ""),
                                 status_name=str(args.get("status_name") or ""),
                                 done_ratio=args.get("done_ratio"),
                                 fixed_version=str(args.get("fixed_version") or ""),
                                 parent_issue_id=args.get("parent_issue_id"),
                                 priority_name=str(args.get("priority_name") or ""),
                                 subject=str(args.get("subject") or ""),
                                 description=str(args.get("description") or ""),
                                 clear_parent=args.get("clear_parent") is True)
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
            trace = {key: args[key] for key in
                     ("task_type", "user_request", "request_id", "session_id", "work_id") if key in args}
            captured = rag_request_context(root or Path.cwd(), str(args.get("request_id") or ""))
            if captured:
                if "user_request" in trace and trace["user_request"] != captured["user_request"]:
                    raise ClientError("RAG 사용자 원문이 캡처한 입력과 다르다")
                trace.update(captured)
            return tool_search_context(pa, str(args.get("query") or ""),
                                       tags=args.get("tags"), n=args.get("n") or 5, cache=c, **trace)
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
