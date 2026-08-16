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
    check("도구 7종 (조회 5 + 쓰기 대행 2: redmine·signal)",
          names == ["list_works", "get_work", "search_context", "list_domains",
                    "get_domain", "redmine_note", "log_writer_signal"], str(names))
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


def main() -> int:
    for fn in (test_single_file_stdlib_only, test_protocol_roundtrip,
               test_nonascii_work_id_is_encoded, test_search_caches_and_falls_back,
               test_domain_tools_cache_and_encode, test_live_state_is_never_cached,
               test_cache_loader_is_file_relative,
               test_tools_call_through_protocol, test_serve_loop_survives,
               test_failure_sentences_differ, test_tool_error_is_iserror_content,
               test_no_decision_tools, test_queue_api_matches_review_contract):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_client_mcp: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
