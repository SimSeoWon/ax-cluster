"""클라이언트 MCP(`#201`) 계약 테스트.

재는 것 넷:
    ① 스크립트 모드 안전   stdlib 밖·패키지 내부 import 가 **0건**인가 (AST)
    ② 프로토콜             initialize/tools/call 왕복 · 알림 무응답 · 서버가 안 죽는가
    ③ 실패 모드            미연결·401·403 이 **서로 다른 조치 문장**으로 나오는가
    ④ 불변식               결정(PATCH) 도구가 **없는가** — 절차는 review 모듈 한 벌뿐

실행: python3 master/test_client_mcp.py   (실 큐를 부르지 않는다 — 전부 주입)
"""
from __future__ import annotations

import ast
import io
import json
import sys
import tempfile
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.clientside import client_mcp as M     # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


# ── ① 스크립트 모드 안전 ─────────────────────────────────────

def test_single_file_stdlib_only():
    """`.mcp.json` 이 스크립트로 실행한다 — 상대 import 하나면 클라에서 죽는다."""
    src = Path(M.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    STDLIB = {"json", "sys", "urllib", "urllib.error", "urllib.request", "pathlib",
              "__future__", "os", "importlib", "importlib.util"}
    bad = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            bad += [a.name for a in n.names if a.name.split(".")[0] not in
                    {m.split(".")[0] for m in STDLIB}]
        elif isinstance(n, ast.ImportFrom):
            if n.level:                                     # 상대 import = 스크립트 모드 사망
                bad.append(f"상대import:{n.module}")
            elif (n.module or "").split(".")[0] not in {m.split(".")[0] for m in STDLIB}:
                bad.append(n.module)
    check("stdlib 밖·패키지 내부 import 0건", not bad, str(bad))
    check("왜 단일 파일인지 스스로 적어 둔다", "스크립트 모드" in src or "스크립트로" in src)


# ── 가짜 api ─────────────────────────────────────────────────

def fake_api(calls, works=None, work=None):
    def api(method, path, payload=None):
        calls.append((method, path, payload))
        if path == "/api/v1/works":
            return works if works is not None else []
        if path.startswith("/api/v1/works/"):
            return work if work is not None else {"work": {}, "tasks": []}
        if path == "/api/v1/redmine/note":
            return {"ok": True, "result": "레드마인 #%s 갱신" % payload["issue_id"]}
        if path.startswith("/api/v1/redmine/issues?"):
            return {"total_count": 1, "issues": [{"id": 226, "subject": "[AX] 실증",
                                                  "status": "진행"}]}
        if path == "/api/v1/redmine/meta":
            return {"statuses": ["신규", "진행", "해결", "검토", "완료"],
                    "trackers": ["코드리뷰"], "priorities": ["보통"],
                    "versions": [{"name": "마일스톤 6 — 개선·확장", "status": "open"}],
                    "note": "닫힌 상태는 「완료」뿐이다"}
        if path.startswith("/api/v1/redmine/issue/"):
            return {"id": int(path.rsplit("/", 1)[1]), "subject": "[AX] 실증",
                    "journals": [{"user": "u", "notes": "n", "created_on": "t"}]}
        if path == "/api/v1/redmine/issue":
            return {"id": 999}
        if path == "/api/v1/redmine/link-commit":
            return {"ok": True, "result": "레드마인 #%s 갱신 (notes)" % payload["issue_id"],
                    "issue_id": payload["issue_id"]}
        if path == "/api/v1/ontology/tasks":
            return {"status": "ok", "count": 0, "templates": []}
        if path.startswith("/api/v1/ontology/task/"):
            return {"status": "ok", "task_type": "미션태스크추가", "structure": {}}
        raise AssertionError(f"예상 밖 호출: {method} {path}")
    return api


# ── ② 프로토콜 ───────────────────────────────────────────────

def test_protocol_roundtrip():
    r = M.handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    check("initialize 응답", r["result"]["protocolVersion"] == M.PROTOCOL_VERSION, str(r))
    check("tools 능력 선언", "tools" in r["result"]["capabilities"])
    check("알림은 무응답", M.handle_message({"jsonrpc": "2.0",
                                             "method": "notifications/initialized"}) is None)
    r = M.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = [t["name"] for t in r["result"]["tools"]]
    check("도구 21종 (조회 11 + 쓰기 대행 10) — 원전 redmine_tracker·태스크 템플릿 인수 (#226)",
          names == ["list_works", "get_work", "search_context", "list_domains",
                    "get_domain", "get_domain_layer", "get_object_spec", "get_action_spec",
                    "find_invariants_by_class", "add_object_alias", "mark_not_a_class",
                    "redmine_note", "redmine_list_issues", "redmine_get_issue",
                    "redmine_meta", "redmine_create_issue", "redmine_link_commit",
                    "list_task_templates", "get_task_template",
                    "log_writer_signal", "log_history"],
          str(names))
    check("모든 도구에 inputSchema", all("inputSchema" in t for t in r["result"]["tools"]))
    r = M.handle_message({"jsonrpc": "2.0", "id": 3, "method": "없는것"})
    check("모르는 요청은 -32601", r["error"]["code"] == -32601, str(r))
    check("ping", M.handle_message({"jsonrpc": "2.0", "id": 4, "method": "ping"})["result"] == {})


def test_tools_call_through_protocol():
    calls = []
    api = fake_api(calls,
                   works=[{"work_id": "w1", "title": "제목", "merge_status": "ready_for_review",
                           "target_branch": "f/x", "total": 3, "created": "t"},
                          {"work_id": "w2", "merge_status": "merged"}],
                   work={"work": {"work_id": "w1", "merge_status": "ready_for_review"},
                         "tasks": [{"task_id": "t1", "status": "verified"}]})
    r = M.handle_message({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                          "params": {"name": "list_works",
                                     "arguments": {"status": "ready_for_review"}}}, api=api)
    body = json.loads(r["result"]["content"][0]["text"])
    check("status 필터가 듣는다", body["count"] == 1 and body["works"][0]["work_id"] == "w1",
          str(body))
    check("isError=False", r["result"]["isError"] is False)

    r = M.handle_message({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                          "params": {"name": "get_work", "arguments": {"work_id": "w1"}}}, api=api)
    body = json.loads(r["result"]["content"][0]["text"])
    check("get_work 가 review 인자 모양 그대로", set(body) == {"work", "tasks"}
          and body["tasks"][0]["task_id"] == "t1", str(body))

    r = M.handle_message({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                          "params": {"name": "redmine_note",
                                     "arguments": {"issue_id": 141, "notes": "확인"}}}, api=api)
    check("redmine_note 가 마스터 경유 경로를 부른다",
          any(p == "/api/v1/redmine/note" for _m, p, _p2 in calls), str(calls[-1]))
    check("한글이 그대로 실린다", calls[-1][2]["notes"] == "확인")


def test_redmine_delegation_goes_to_queue():
    """[중요] **읽기라도 8103 이 아니라 큐(8101)** — 그 포트의 `/api/v1/*` 는 무인증 공개다.

    이 테스트가 지키는 것은 경로 하나가 아니라 **판단**이다. 8103 으로 옮기면 일감 본문과
    검수 이력이 LAN 아무에게나 열린다(실측 2026-08-20: 토큰 없이 200).
    """
    calls = []
    api = fake_api(calls)
    for name, args, want in (
            ("redmine_list_issues", {"status": "open"}, "/api/v1/redmine/issues?"),
            ("redmine_get_issue", {"issue_id": 226}, "/api/v1/redmine/issue/226"),
            ("redmine_meta", {}, "/api/v1/redmine/meta"),
            ("redmine_create_issue", {"subject": "[AX] 제목"}, "/api/v1/redmine/issue"),
            ("redmine_link_commit", {"issue_id": 226, "commit_hash": "abc1234"},
             "/api/v1/redmine/link-commit")):
        r = M.handle_message({"jsonrpc": "2.0", "id": 90, "method": "tools/call",
                              "params": {"name": name, "arguments": args}}, api=api)
        check(f"{name} → {want}", calls[-1][1].startswith(want), str(calls[-1]))
        check(f"{name} isError=False", r["result"]["isError"] is False, str(r))
    check("이슈 생성은 프로젝트를 인자로 받지 않는다 (새 프로젝트 금지 규칙)",
          "project" not in (calls[-2][2] or {}), str(calls[-2]))
    check("커밋 연결 본문은 해시를 그대로 싣는다", calls[-1][2]["commit_hash"] == "abc1234")

    # 빈 인자는 호출 전에 막는다 — 조용히 전체를 긁어 오거나 제목 없는 이슈를 만들지 않는다
    for name, args in (("redmine_get_issue", {}),
                       ("redmine_create_issue", {"subject": "  "}),
                       ("redmine_link_commit", {"issue_id": 1, "commit_hash": ""})):
        r = M.handle_message({"jsonrpc": "2.0", "id": 91, "method": "tools/call",
                              "params": {"name": name, "arguments": args}}, api=api)
        check(f"{name} 빈 인자 → isError", r["result"]["isError"] is True, str(r))


def test_task_templates_read_surface():
    """태스크 템플릿은 **8103**(공개 읽기) 이다 — 도메인 조회와 같은 등급의 구조 자료.

    [중요] 0건이면 0건이라고 **말한다** (리포트 27 §3: 조용히 0 으로 답하는 입구가 위험하다).
    """
    calls = []
    papi = fake_api(calls)
    r = M.handle_message({"jsonrpc": "2.0", "id": 92, "method": "tools/call",
                          "params": {"name": "list_task_templates", "arguments": {}}}, papi=papi)
    body = json.loads(r["result"]["content"][0]["text"])
    check("목록은 8103 라우트로", calls[-1][1] == "/api/v1/ontology/tasks", str(calls[-1]))
    check("0건을 0건이라고 말한다", body["count"] == 0 and "_note" in body, str(body))
    r = M.handle_message({"jsonrpc": "2.0", "id": 93, "method": "tools/call",
                          "params": {"name": "get_task_template",
                                     "arguments": {"task_type": "미션태스크추가"}}}, papi=papi)
    check("한글 이름이 URL 인코딩돼 나간다", "%" in calls[-1][1], str(calls[-1]))
    check("1건 조회 응답", json.loads(r["result"]["content"][0]["text"])["task_type"]
          == "미션태스크추가")


def test_serve_loop_survives():
    lines = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
        "이건 JSON 이 아니다",
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
    ]
    out = io.StringIO()
    M.serve(stdin=io.StringIO("\n".join(lines) + "\n"), stdout=out)
    resp = [json.loads(l) for l in out.getvalue().splitlines()]
    check("깨진 줄을 건너뛰고 계속 돈다 (응답 2개)", len(resp) == 2, str(len(resp)))
    check("id 가 맞물린다", [r["id"] for r in resp] == [1, 2])


# ── ③ 실패 모드 — 문장이 조치를 담는가 ───────────────────────

def _http_error(code):
    return urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(b"{}"))


def test_failure_sentences_differ():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        try:
            M.load_config(root)
            check("config 없으면 죽는다", False)
        except M.ClientError as e:
            check("[미구성] 이 무엇을 어디서 찾았는지 말한다",
                  "미구성" in str(e) and ".ax" in str(e) and "deliver" in str(e), str(e)[:90])

    def die(exc):
        def api(m, p, pl=None):
            raise exc
        return api

    # 미연결 — urlopen 을 직접 흉내내기 위해 _call 로 잰다
    import unittest.mock as mock
    with mock.patch.object(M.urllib.request, "urlopen",
                           side_effect=urllib.error.URLError("no route")):
        try:
            M._call("GET", "http://192.168.0.57:8101/api/v1/works", "tok")
            check("미연결이면 죽는다", False)
        except M.ClientError as e:
            s = str(e)
            check("[미연결] 조치 3단계를 준다",
                  "미연결" in s and "ax-task-queue" in s and "LAN" in s and "config" in s, s[:80])
    with mock.patch.object(M.urllib.request, "urlopen", side_effect=_http_error(401)):
        try:
            M._call("GET", "http://x/api", "tok")
            check("401 이면 죽는다", False)
        except M.ClientError as e:
            check("[자격] 401 은 토큰 재배달을 안내", "자격" in str(e) and "deliver" in str(e),
                  str(e)[:80])
    with mock.patch.object(M.urllib.request, "urlopen", side_effect=_http_error(403)):
        try:
            M._call("POST", "http://x/api/v1/tasks/claim", "tok")
            check("403 이면 죽는다", False)
        except M.ClientError as e:
            check("[스코프] 403 은 401 과 다른 문장 — 배선 오진을 막는다",
                  "스코프" in str(e) and "자격" not in str(e), str(e)[:80])


def test_tool_error_is_iserror_content():
    """도구 오류는 프로토콜 오류가 아니다 — isError 콘텐츠로 Claude 가 읽는다."""
    def boom(m, p, pl=None):
        raise M.ClientError("[미연결] 마스터에 연결할 수 없다")
    r = M.handle_message({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                          "params": {"name": "list_works", "arguments": {}}}, api=boom)
    check("isError=True 로 온다", r["result"]["isError"] is True, str(r))
    check("조치 문장이 그대로 실린다", "미연결" in r["result"]["content"][0]["text"])
    check("error 필드가 아니다 (연결이 끊겨도 세션은 산다)", "error" not in r)


# ── ④ 불변식 — 결정은 MCP 도구가 아니다 ──────────────────────

class FakeCache:
    """OntologyCache 의 계약만 흉내낸다 — put(성공만) · get_stale(_stale 주입)."""
    def __init__(self):
        self.store = {}
        self.puts = []
    def put(self, key, body):
        self.puts.append(key)
        self.store[key] = body
        return {"stored": True}
    def get_stale(self, key):
        if key not in self.store:
            return None
        obj = json.loads(self.store[key])
        obj["_stale"] = True
        obj["_cached_at"] = "2026-08-16T23:00:00"
        return json.dumps(obj, ensure_ascii=False)


def test_search_caches_and_falls_back():
    """[중요] #162 캐시의 첫 실 소비자 — 성공은 적재, 미연결은 _stale 폴백."""
    cache = FakeCache()
    ok_api = lambda m, p, pl=None: {"query": pl["query"], "count": 1,
                                    "results": [{"file": "X.h"}]}
    got = M.tool_search_context(ok_api, "미션 완료", n=2, cache=cache)
    check("성공 응답이 그대로 온다", got["count"] == 1, str(got))
    check("[중요] 성공이 캐시에 적재된다", len(cache.puts) == 1, str(cache.puts))

    def dead(m, p, pl=None):
        raise M.ClientError("[미연결] 마스터(http://x:8103)에 연결할 수 없다")
    stale = M.tool_search_context(dead, "미션 완료", n=2, cache=cache)
    check("[중요] 미연결이면 마지막 정상 응답으로 폴백한다", stale["count"] == 1, str(stale))
    check("[중요] _stale 표기가 주입된다 — 낡은 값임을 소비자가 안다",
          stale.get("_stale") is True and "_cached_at" in stale, str(stale))
    check("미연결 사유도 실린다", "[미연결]" in (stale.get("_note") or ""), str(stale.get("_note")))

    try:
        M.tool_search_context(dead, "캐시에 없는 질의", cache=cache)
        check("캐시에도 없으면 원래 오류가 나간다", False)
    except M.ClientError as e:
        check("캐시에도 없으면 원래 오류가 나간다", "[미연결]" in str(e))
    try:
        M.tool_search_context(ok_api, "  ", cache=cache)
        check("빈 질의 거부", False)
    except M.ClientError:
        check("빈 질의 거부", True)


def test_domain_tools_cache_and_encode():
    cache = FakeCache()
    papi = lambda m, p, pl=None: {"domains": ["MissionRuntime"]} if "domains" in p else {}
    got = M.tool_list_domains(papi, cache=cache)
    check("도메인 목록", got["domains"] == ["MissionRuntime"], str(got))
    calls = []
    papi2 = lambda m, p, pl=None: calls.append(p) or {"domain": "X"}
    M.tool_get_domain(papi2, "미션 런타임", cache=None)
    check("[중요] 도메인 이름도 URL 인코딩 (#197 의 교훈)", "%EB%AF%B8" in calls[0], calls[0])


def test_live_state_is_never_cached():
    """[중요] 불변식 — works/tasks 는 캐시를 거치지 않는다. 낡은 merge_status 위에서
    검수가 결정하면 안 된다."""
    cache = FakeCache()
    api = fake_api([], works=[{"work_id": "w", "merge_status": "ready_for_review"}])
    M.dispatch_tool("list_works", {}, api=api, cache=cache)
    M.dispatch_tool("get_work", {"work_id": "w"}, api=api, cache=cache)
    check("[중요] 큐 조회가 캐시에 아무것도 적재하지 않았다", cache.puts == [], str(cache.puts))
    import ast as _ast
    src = Path(M.__file__).read_text(encoding="utf-8")
    for fn in ("tool_list_works", "tool_get_work"):
        seg = src[src.index(f"def {fn}"):]
        seg = seg[:seg.index("\ndef ")]
        check(f"{fn} 시그니처에 cache 자체가 없다", "cache" not in seg, fn)


def test_cache_loader_is_file_relative():
    """패키지 이름에 기대지 않는다 — 저장소/배달본 두 집 + 스크립트 모드를 한 번에 푼다."""
    src = Path(M.__file__).read_text(encoding="utf-8")
    check("spec_from_file_location 을 쓴다", "spec_from_file_location" in src)
    check("axmaster/master 패키지명이 로더에 없다",
          "import axmaster" not in src and "from axmaster" not in src)
    check("실패해도 도구는 계속 돈다고 적어 둔다", "도구는 계속 돈다" in src)
    # 실 로드 — 옆에 ontology_cache.py 가 실재하므로 성공해야 한다
    M._CACHE = None
    c = M._load_cache()
    check("[중요] 옆 파일 실 로드가 된다 (저장소 배치)", c is not None,
          "옆에 ontology_cache.py 가 있는데 로드 실패")
    M._CACHE = None


def test_no_decision_tools():
    names = {t["name"] for t in M.TOOLS}
    for banned in ("decide", "patch", "merge", "reject", "finalize", "approve"):
        check(f"결정 도구가 없다: {banned}", not any(banned in n for n in names), str(names))
    check("대신 queue_api 를 내보낸다 (review 모듈 주입 자리)", callable(M.queue_api))
    src = Path(M.__file__).read_text(encoding="utf-8")
    check("왜 없는지 스스로 적어 둔다", "로직이 두 벌" in src)


def test_nonascii_work_id_is_encoded():
    """.33 첫 실 왕복이 잡은 결함 — 비ASCII id 가 내부 오류로 죽었다."""
    calls = []
    def api(m, p, pl=None):
        calls.append(p)
        return {"work": {}, "tasks": []}
    M.tool_get_work(api, "없는것")
    check("[중요] 비ASCII id 가 URL 인코딩된다", "%EC%97%86" in calls[0], calls[0])
    M.tool_get_work(api, "w 1")
    check("공백도 인코딩된다", "w%201" in calls[1], calls[1])
    # 프로토콜 층에서도 isError 콘텐츠로 나와야 한다 (내부 오류 아님)
    def api404(m, p, pl=None):
        raise M.ClientError("[서버] 404")
    r = M.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                          "params": {"name": "get_work", "arguments": {"work_id": "없는것"}}},
                         api=api404)
    check("없는 work 도 isError 콘텐츠다 (세션이 산다)", "result" in r and r["result"]["isError"],
          str(r)[:80])


def test_queue_api_matches_review_contract():
    """`review.reject_work(api=…)` 가 기대하는 시그니처: api(method, path, payload)."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        ax = root / ".ax"
        ax.mkdir()
        (ax / "config.json").write_text(json.dumps(
            {"master": {"host": "192.168.0.57", "services": {"task_queue": 8101}}}), "utf-8")
        (ax / "token").write_text("tok-abcdefghijklmnopqrstuvwxyz012345\n", "utf-8")
        api = M.queue_api(root)
        check("호출자가 만들어진다", callable(api))
        import inspect
        params = list(inspect.signature(api).parameters)
        check("시그니처 (method, path, payload)", params[:2] == ["method", "path"], str(params))
    check("빈 work_id 는 시작 전에 막는다", True)
    try:
        M.tool_get_work(lambda *a, **k: {}, "  ")
        check("빈 work_id 거부", False)
    except M.ClientError:
        check("빈 work_id 거부", True)


def _domain_payload():
    return {"name": "MissionRuntime",
            "manifest": {"tier": 3, "summary": "미션 실행 계층",
                         "layer_counts": {"L1": 1, "L2": 0, "L3": 10}},
            "parent_domain": "", "sub_domains": [], "collaborated_by": ["MissionEditor"],
            "layer_descriptions": {"L1": {"body": "L1 서술"}, "L3": {"body": "L3 서술"}},
            "objects": [{"name": "UMissionTaskBase", "layer": 1,
                         "file": "Source/.../MissionTaskBase.h"},
                        {"name": "UMissionTaskExecutor", "layer": 3, "file": "X.h"}],
            "actions": [{"name": "AdvanceTaskOnTick", "layer": 1},
                        {"name": "InitTaskChain", "layer": 3}],
            "invariants": [{"name": "ClientAutoRegisterOnce", "layer": 3}]}


def test_ontology_item_tools_encode_and_cache():
    """[중요] 원전의 get_object_spec/get_action_spec 자리 — 로컬 인덱스가 아니라 마스터로 간다."""
    calls = []
    def papi(m, path, pl=None):
        calls.append(path)
        return {"name": "UMissionTaskExecutor", "kind": "Object", "layer": 3}
    cache = FakeCache()
    got = M.tool_get_object_spec(papi, "MissionRuntime", "UMissionTaskExecutor", cache=cache)
    check("클래스 스펙이 온다", got["kind"] == "Object", str(got))
    check("object 라우트로 간다", calls[0] == "/api/v1/ontology/object/MissionRuntime/UMissionTaskExecutor",
          calls[0])
    check("[중요] 성공이 캐시에 적재된다", cache.puts and "ontology/object/" in cache.puts[0],
          str(cache.puts))

    M.tool_get_action_spec(papi, "MissionRuntime", "AdvanceTaskOnTick", cache=None)
    check("action 은 action 라우트로 간다", calls[-1].startswith("/api/v1/ontology/action/"), calls[-1])

    M.tool_get_object_spec(papi, "미션 런타임", "U태스크", cache=None)
    check("[중요] 도메인·이름 **양쪽** 다 URL 인코딩 (#197 의 교훈)",
          "%EB%AF%B8" in calls[-1] and "%ED%83%9C%EC%8A%A4%ED%81%AC" in calls[-1], calls[-1])

    def dead(m, path, pl=None):
        raise M.ClientError("[미연결] 마스터(http://x:8103)에 연결할 수 없다")
    stale = M.tool_get_object_spec(dead, "MissionRuntime", "UMissionTaskExecutor", cache=cache)
    check("[중요] 미연결이면 _stale 폴백", stale.get("_stale") is True, str(stale))

    for bad in (("", "UX"), ("MissionRuntime", "  ")):
        try:
            M.tool_get_object_spec(papi, *bad, cache=None)
            check(f"빈 인자 거부 {bad}", False)
        except M.ClientError:
            check(f"빈 인자 거부 {bad}", True)


def test_domain_layer_filters_and_keeps_markers():
    """[주의] 이 위임만 응답을 **줄인다** — 줄이면서 _stale 을 떨어뜨리면 마스터가 죽은 것을
    아무도 모른다(#162 계약). 그 한 줄이 이 테스트의 이유다."""
    papi = lambda m, path, pl=None: _domain_payload()
    all_l = M.tool_get_domain_layer(papi, "MissionRuntime", cache=None)
    check("layer 생략은 전체", all_l["layer"] == "all" and len(all_l["objects"]) == 2, str(all_l))
    check("층 서술도 전체가 온다", set(all_l["layer_descriptions"]) == {"L1", "L3"},
          str(all_l["layer_descriptions"]))

    l1 = M.tool_get_domain_layer(papi, "MissionRuntime", layer=1, cache=None)
    check("[중요] layer=1 은 1층만 남긴다",
          [o["name"] for o in l1["objects"]] == ["UMissionTaskBase"]
          and [a["name"] for a in l1["actions"]] == ["AdvanceTaskOnTick"]
          and l1["invariants"] == [], str(l1))
    check("그 층의 서술만 온다", set(l1["layer_descriptions"]) == {"L1"},
          str(l1["layer_descriptions"]))
    check("objects 는 파일 경로도 실어 준다 — 선언부로 갈 수 있다",
          "file" in l1["objects"][0], str(l1["objects"][0]))

    empty = M.tool_get_domain_layer(papi, "MissionRuntime", layer=2, cache=None)
    check("빈 층은 조용히 비지 않고 사유를 말한다", "L2 에 항목이 없다" in (empty.get("_note") or ""),
          str(empty.get("_note")))

    cache = FakeCache()
    M.tool_get_domain_layer(papi, "MissionRuntime", layer=1, cache=cache)
    def dead(m, path, pl=None):
        raise M.ClientError("[미연결] 마스터에 연결할 수 없다")
    stale = M.tool_get_domain_layer(dead, "MissionRuntime", layer=1, cache=cache)
    check("[중요] 변환 뒤에도 _stale·_cached_at 이 살아 남는다",
          stale.get("_stale") is True and "_cached_at" in stale, str(stale))
    check("[중요] 미연결 사유가 층 사유를 이긴다", "[미연결]" in (stale.get("_note") or ""),
          str(stale.get("_note")))
    check("폴백도 층 필터가 유지된다", [o["name"] for o in stale["objects"]] == ["UMissionTaskBase"],
          str(stale["objects"]))

    try:
        M.tool_get_domain_layer(papi, "MissionRuntime", layer="셋", cache=None)
        check("정수 아닌 layer 거부", False)
    except M.ClientError as e:
        check("정수 아닌 layer 거부", "정수" in str(e), str(e))
    try:
        M.tool_get_domain_layer(lambda m, p, pl=None: ["배열"], "MissionRuntime", cache=None)
        check("객체 아닌 응답 거부", False)
    except M.ClientError as e:
        check("객체 아닌 응답 거부", "객체가 아니다" in str(e), str(e))


def test_ontology_read_tools_are_registered():
    """스키마가 없으면 클라가 호출 자체를 못 한다 — 함수만 만들고 끝나는 실패를 막는다."""
    names = {t["name"] for t in M.TOOLS}
    for n in ("get_domain_layer", "get_object_spec", "get_action_spec"):
        check(f"{n} 이 TOOLS 에 있다", n in names, str(sorted(names)))
        t = next(x for x in M.TOOLS if x["name"] == n)
        check(f"{n} 스키마에 domain 이 있다", "domain" in t["inputSchema"]["properties"], str(t))
    calls = []
    papi = lambda m, path, pl=None: calls.append(path) or _domain_payload()
    M.dispatch_tool("get_domain_layer", {"domain": "MissionRuntime", "layer": 3},
                    papi=papi, cache=FakeCache())
    M.dispatch_tool("get_object_spec", {"domain": "MissionRuntime", "name": "UX"},
                    papi=papi, cache=FakeCache())
    M.dispatch_tool("get_action_spec", {"domain": "MissionRuntime", "name": "AX"},
                    papi=papi, cache=FakeCache())
    check("[중요] 디스패치가 셋 다 라우팅한다",
          [c.split("/")[4] for c in calls] == ["domain", "object", "action"], str(calls))
    check("읽기 전용이다 — GET 만 쓴다",
          "ontology" in calls[0] and all("/api/v1/ontology/" in c for c in calls), str(calls))


def test_thesaurus_writes_go_to_queue_uncached():
    """[중요] 쓰기는 큐(8101)로 간다 — 8103 의 /api/v1/* 은 **무인증 공개**라(실측 2026-08-20)
    쓰기를 둘 자리가 아니다. 그리고 쓰기는 캐시를 타지 않는다 — last-known-good 이 없다."""
    calls = []
    def fake_api(method, path, payload=None):
        calls.append((method, path, payload))
        return {"ok": True, "status": "added", "class": (payload or {}).get("class_name"),
                "term": (payload or {}).get("term")}
    cache = FakeCache()
    got = M.dispatch_tool("add_object_alias",
                          {"class_name": "UMissionTaskExecutor", "term": "미션 태스크 실행기"},
                          api=fake_api, cache=cache)
    m, path, payload = calls[0]
    check("[중요] POST /api/v1/thesaurus/alias (redmine_note·signals 와 같은 대행 구조)",
          (m, path) == ("POST", "/api/v1/thesaurus/alias"), f"{m} {path}")
    check("본문에 클래스와 표현이 실린다",
          payload["class_name"] == "UMissionTaskExecutor" and payload["term"] == "미션 태스크 실행기",
          str(payload))
    check("응답 그대로 반환", got.get("status") == "added", str(got))
    M.dispatch_tool("mark_not_a_class", {"term": "완료 처리"}, api=fake_api, cache=cache)
    check("not-a-class 도 큐로", calls[1][1] == "/api/v1/thesaurus/not-a-class", str(calls[1]))
    check("[중요] 쓰기가 캐시에 아무것도 적재하지 않았다", cache.puts == [], str(cache.puts))

    for name, args in (("add_object_alias", {"class_name": "", "term": "미션 태스크"}),
                       ("add_object_alias", {"class_name": "UFoo", "term": "  "}),
                       ("mark_not_a_class", {"term": ""})):
        try:
            M.dispatch_tool(name, args, api=fake_api)
            check(f"빈 인자는 왕복 전에 막는다 {name} {args}", False)
        except M.ClientError:
            check(f"빈 인자는 왕복 전에 막는다 {name} {args}", True)


def test_guard_verdict_passes_through_not_as_error():
    """[중요] 거부는 오류가 아니라 **사유 문장**으로 온다 — 클라가 판정을 흉내내면 서버의
    가드(#213)와 두 벌이 되고, 문턱값이 바뀔 때 갈라진다."""
    rejected = {"ok": False, "status": "rejected_generic: 정확 구 DF 32/961 = 3.3% > 2.5% — ...",
                "class": "UFoo", "term": "연출"}
    got = M.dispatch_tool("add_object_alias", {"class_name": "UFoo", "term": "연출"},
                          api=lambda m, p, pl=None: rejected)
    check("거부가 예외가 아니라 응답으로 온다", got["ok"] is False, str(got))
    check("사유가 그대로 보인다", "rejected_generic" in got["status"], str(got))
    src = Path(M.__file__).read_text(encoding="utf-8")
    for dup in ("GUARD_MIN_CHARS", "0.025", "2.5"):
        check(f"클라에 가드 문턱이 복제돼 있지 않다: {dup}", dup not in src)
    from master.auth import REQUESTER_SCOPE
    check("[중요] requester 스코프가 POST /api/v1/thesaurus/ 를 연다",
          ("POST", "/api/v1/thesaurus/") in REQUESTER_SCOPE, str(REQUESTER_SCOPE))


def test_domain_layer_carries_manifest_and_navigation():
    """[중요] 넓이(계층·연관) 탐색이 작업장에서 되는가 — 원전 `get_domain_manifest` 자리.
    서버 응답에 이미 실려 오는 값이라 왕복이 늘지 않는다."""
    papi = lambda m, path, pl=None: _domain_payload()
    got = M.tool_get_domain_layer(papi, "MissionRuntime", layer=1, cache=None)
    check("tier·summary·layer_counts 가 온다",
          got["tier"] == 3 and got["summary"] and got["layer_counts"]["L3"] == 10, str(got)[:200])
    check("[중요] 연관(역참조)도 온다 — 옆 도메인으로 이동할 수 있다",
          got["collaborated_by"] == ["MissionEditor"], str(got.get("collaborated_by")))
    check("계층 필드는 비어도 키가 있다 (없음과 모름을 가른다)",
          got["parent_domain"] == "" and got["sub_domains"] == [], str(got)[:120])


def test_find_invariants_sweeps_and_says_how_it_matched():
    """[주의] 우리 evidence 는 `파일.cpp:84-90` 이라 클래스명이 안 들어 있다 — 접두 뗀 이름으로
    맞히는 휴리스틱이고, 그 사실을 matched_by 로 **말해야** 한다."""
    calls = []
    def papi(m, path, pl=None):
        calls.append(path)
        if path.endswith("/ontology/domains"):
            return {"domains": [{"name": "MissionRuntime"}, {"name": "MissionEditor"}]}
        if path.endswith("MissionRuntime"):
            d = _domain_payload()
            d["invariants"] = [
                {"name": "A", "layer": 3, "text": "UMissionTaskExecutor 는 서버에서만 등록한다",
                 "evidence": "Manager_Mission.cpp:10", "confidence": 0.9},
                {"name": "B", "layer": 3, "text": "무관한 규칙",
                 "evidence": "ActorComponent_MissionTaskExecutor.cpp:84-90", "confidence": 0.8},
                {"name": "C", "layer": 3, "text": "무관", "evidence": "Other.cpp:1"}]
            return d
        d = _domain_payload(); d["invariants"] = []; d["name"] = "MissionEditor"
        return d

    got = M.tool_find_invariants_by_class(papi, "UMissionTaskExecutor", cache=None)
    check("도메인 전체를 훑는다", got["domains_swept"] == 2, str(got["domains_swept"]))
    check("[중요] text 로 맞은 것과 evidence(접두 뗀 이름)로 맞은 것 둘 다 잡는다",
          got["count"] == 2 and {h["name"] for h in got["invariants"]} == {"A", "B"}, str(got))
    by = {h["name"]: h["matched_by"] for h in got["invariants"]}
    check("[중요] 어느 규칙으로 맞았는지 말한다", by == {"A": "text", "B": "evidence"}, str(by))
    check("접두 뗀 이름도 돌려준다 (호출자가 판단할 근거)",
          got["bare"] == "MissionTaskExecutor", str(got.get("bare")))
    check("도메인 카탈로그를 먼저 부른다", calls[0].endswith("/ontology/domains"), calls[0])

    none = M.tool_find_invariants_by_class(papi, "UNoSuch", cache=None)
    check("0건이면 조용히 비지 않고 다음 수를 말한다",
          none["count"] == 0 and "get_domain_layer" in (none.get("_note") or ""),
          str(none.get("_note")))
    try:
        M.tool_find_invariants_by_class(papi, "  ", cache=None)
        check("빈 클래스명 거부", False)
    except M.ClientError:
        check("빈 클래스명 거부", True)

    cache = FakeCache()
    M.tool_find_invariants_by_class(papi, "UMissionTaskExecutor", cache=cache)
    check("[중요] 스윕이 get_domain_layer 와 **같은 캐시 키**를 쓴다 — 두 벌 적재 안 한다",
          any(k == "ontology/domain/MissionRuntime" for k in cache.puts), str(cache.puts))


def main() -> int:
    for fn in (test_single_file_stdlib_only, test_protocol_roundtrip,
               test_nonascii_work_id_is_encoded, test_search_caches_and_falls_back,
               test_domain_tools_cache_and_encode, test_live_state_is_never_cached,
               test_cache_loader_is_file_relative,
               test_tools_call_through_protocol, test_serve_loop_survives,
               test_failure_sentences_differ, test_tool_error_is_iserror_content,
               test_no_decision_tools, test_queue_api_matches_review_contract,
               test_ontology_item_tools_encode_and_cache,
               test_domain_layer_filters_and_keeps_markers,
               test_ontology_read_tools_are_registered,
               test_thesaurus_writes_go_to_queue_uncached,
               test_guard_verdict_passes_through_not_as_error,
               test_domain_layer_carries_manifest_and_navigation,
               test_find_invariants_sweeps_and_says_how_it_matched,
               test_redmine_delegation_goes_to_queue,
               test_task_templates_read_surface):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_client_mcp: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
