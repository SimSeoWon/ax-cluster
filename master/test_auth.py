"""인증 계층 테스트 — pytest 없이 그대로 실행한다.

    .venv/bin/python master/test_auth.py

[중요] 이 테스트가 지키는 불변식 (PLAN §9.5.6):
   1. **토큰을 못 읽으면 예외** — 어떤 실패도 "인증 없음" 으로 강등되지 않는다
   2. 약한 토큰·열린 권한도 거부한다
   3. 열린 경로는 `/livez` 하나뿐이고, 정보를 노출하지 않는다
   4. `lifespan` 은 통과, `websocket` 은 거부 (앱이 뜨긴 해야 하고, 인증 안 된
      업그레이드 경로는 열지 않는다)
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="ax-auth-test-"))

from master.auth import (  # noqa: E402
    MIN_TOKEN_LEN,
    AuthError,
    BearerAuthMiddleware,
    auth_headers,
    generate_token,
    load_token,
    parse_bearer,
    verify,
    write_token,
)

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [완료] {label}")
    else:
        FAIL += 1
        print(f"  [실패] {label}" + (f" — {detail}" if detail else ""))


def raises(label, fn, *a, **kw):
    try:
        fn(*a, **kw)
    except AuthError:
        check(label, True)
        return
    check(label, False, "예외가 나지 않았다")


async def call(app, path="/x", headers=None, scope_type="http", method="GET"):
    """미들웨어를 직접 호출해 (status, body) 를 받는다."""
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    scope = {
        "type": scope_type,
        "path": path,
        "method": method,
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }
    await app(scope, receive, send)
    status = next((m["status"] for m in sent if m["type"] == "http.response.start"), None)
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, body, sent


def make_app(token, reached):
    async def inner(scope, receive, send):
        reached.append(scope.get("type"))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    return BearerAuthMiddleware(inner, token)


def main() -> int:
    print("[1] 토큰 생성·적재")
    p = _TMP / "cfg" / "token"
    path, tok = write_token(p)
    check("파일 생성", path.is_file())
    check("권한 0600", oct(path.stat().st_mode)[-3:] == "600", oct(path.stat().st_mode))
    check("길이 충분", len(tok) >= MIN_TOKEN_LEN, str(len(tok)))
    check("읽기 일치", load_token(p) == tok)
    raises("이미 있으면 덮지 않는다", write_token, p)

    print("\n[2] [중요] fail-closed — 어떤 실패도 '인증 없음' 이 되지 않는다")
    raises("파일 없음", load_token, _TMP / "nope")
    empty = _TMP / "empty"
    empty.write_text("  \n", encoding="utf-8")
    os.chmod(empty, 0o600)
    raises("빈 파일", load_token, empty)
    short = _TMP / "short"
    short.write_text("abc123", encoding="utf-8")
    os.chmod(short, 0o600)
    raises("짧은 토큰", load_token, short)
    openp = _TMP / "open"
    openp.write_text(generate_token(), encoding="utf-8")
    os.chmod(openp, 0o644)
    raises("권한이 열린 파일", load_token, openp)
    os.chmod(openp, 0o640)
    raises("그룹 읽기도 거부", load_token, openp)

    print("\n[3] 비교·파싱")
    check("정확히 같아야 통과", verify(tok, tok))
    check("빈 값 거부", not verify("", tok) and not verify(None, tok))
    check("한 글자 달라도 거부", not verify(tok[:-1] + ("x" if tok[-1] != "x" else "y"), tok))
    check("접두어만으론 안 된다", not verify(tok[:10], tok))
    check("Bearer 파싱", parse_bearer(f"Bearer {tok}") == tok)
    check("대소문자 무시", parse_bearer(f"bearer {tok}") == tok)
    check("스킴 없으면 None", parse_bearer(tok) is None)
    check("다른 스킴 거부", parse_bearer(f"Basic {tok}") is None)
    check("빈 헤더 None", parse_bearer("") is None and parse_bearer(None) is None)
    check("토큰 없는 Bearer None", parse_bearer("Bearer ") is None)

    print("\n[4] 미들웨어 — 통과와 차단")
    reached: list = []
    app = make_app(tok, reached)
    st, body, _ = asyncio.run(call(app, headers={"Authorization": f"Bearer {tok}"}))
    check("올바른 토큰 → 200", st == 200 and body == b"ok", f"{st} {body!r}")
    check("  앱까지 도달", reached == ["http"], str(reached))

    for label, hdr in (
        ("헤더 없음", None),
        ("틀린 토큰", {"Authorization": "Bearer wrong-token-value-that-is-long-enough-xx"}),
        ("스킴 없음", {"Authorization": tok}),
        ("빈 Bearer", {"Authorization": "Bearer "}),
    ):
        reached.clear()
        st, body, sent = asyncio.run(call(app, headers=hdr))
        check(f"{label} → 401", st == 401, str(st))
        check(f"  앱에 도달하지 않음", reached == [], str(reached))
    check("본문이 이유를 흘리지 않는다", b"unauthorized" in body and b"token" not in body, str(body))
    hdrs = dict(sent[0]["headers"])
    check("WWW-Authenticate 있음", b"www-authenticate" in hdrs)

    print("\n[5] 열린 경로는 /livez 하나뿐")
    reached.clear()
    st, _, _ = asyncio.run(call(app, path="/livez"))
    check("/livez 는 인증 없이 200", st == 200)
    for path in ("/health", "/api/v1/health", "/mcp", "/", "/livez/x", "/livez2"):
        st, _, _ = asyncio.run(call(app, path=path))
        check(f"  {path} 는 차단", st == 401, f"{path} → {st}")

    print("\n[6] 스코프 타입")
    reached.clear()
    asyncio.run(call(app, scope_type="lifespan"))
    check("lifespan 통과 (앱이 기동은 해야 한다)", reached == ["lifespan"], str(reached))
    reached.clear()
    _, _, sent = asyncio.run(call(app, scope_type="websocket"))
    check("websocket 거부", sent and sent[0]["type"] == "websocket.close", str(sent))
    check("  앱에 도달하지 않음", reached == [], str(reached))

    print("\n[7] 내부 클라이언트 헤더")
    h = auth_headers(tok)
    check("Authorization 키", "Authorization" in h)
    check("Bearer 형식", h["Authorization"] == f"Bearer {tok}")
    check("헤더가 미들웨어를 통과한다",
          asyncio.run(call(app, headers=h))[0] == 200)

    print("\n[8] 토큰은 매번 다르다")
    print("\n[8] 역할 스코프 토큰 (소 3.8.2) — 최소권한이 실제로 최소인가")
    from master.auth import REQUESTER_SCOPE
    req_tok = generate_token()
    reached8: list = []

    async def inner8(scope, receive, send):
        reached8.append(scope["path"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    sapp = BearerAuthMiddleware(inner8, tok, scoped=((req_tok, REQUESTER_SCOPE),))
    H = {"authorization": f"Bearer {req_tok}"}

    st, _b, _ = asyncio.run(call(sapp, "/api/v1/works/w1", headers=H, method="GET"))
    check("스코프 안 GET works → 통과", st == 200, str(st))
    st, _b, _ = asyncio.run(call(sapp, "/api/v1/tasks/t1", headers=H, method="GET"))
    check("스코프 안 GET tasks → 통과", st == 200, str(st))
    st, _b, _ = asyncio.run(call(sapp, "/api/v1/works/w1", headers=H, method="PATCH"))
    check("스코프 안 PATCH works (검수 결정) → 통과", st == 200, str(st))
    st, _b, _ = asyncio.run(call(sapp, "/api/v1/redmine/note", headers=H, method="POST"))
    check("스코프 안 redmine/note → 통과", st == 200, str(st))
    st, _b, _ = asyncio.run(call(sapp, "/api/v1/thesaurus/alias", headers=H, method="POST"))
    check("스코프 안 thesaurus/alias → 통과 (2026-08-20)", st == 200, str(st))
    st, _b, _ = asyncio.run(call(sapp, "/api/v1/thesaurus/not-a-class", headers=H, method="POST"))
    check("스코프 안 thesaurus/not-a-class → 통과", st == 200, str(st))
    st, _b, _ = asyncio.run(call(sapp, "/api/v1/thesaurus/alias", headers=H, method="GET"))
    check("[중요] 같은 경로의 GET 은 열리지 않는다 — 규칙은 (메서드, 접두어)다",
          st == 403, str(st))

    st, body8, _ = asyncio.run(call(sapp, "/api/v1/tasks/claim", headers=H, method="POST"))
    check("[중요] 스코프 밖 POST claim → 403 (401 아님 — 신원은 맞다)", st == 403,
          f"{st} {body8}")
    st, _b, _ = asyncio.run(call(sapp, "/api/v1/works", headers=H, method="POST"))
    check("[중요] work 등록(POST) 은 못 한다 — 읽기와 결정만", st == 403, str(st))
    st, _b, _ = asyncio.run(call(sapp, "/api/v1/admin/reset", headers=H, method="POST"))
    check("[중요] admin 경로는 못 연다", st == 403, str(st))
    st, _b, _ = asyncio.run(call(sapp, "/api/v1/tasks/t1", headers=H, method="DELETE"))
    check("허용 경로라도 다른 메서드는 403", st == 403, str(st))

    st, _b, _ = asyncio.run(call(sapp, "/api/v1/works", headers={"authorization": "Bearer 틀린것"},
                                 method="GET"))
    check("모르는 토큰은 여전히 401", st == 401, str(st))
    st, _b, _ = asyncio.run(call(sapp, "/api/v1/tasks/claim",
                                 headers={"authorization": f"Bearer {tok}"}, method="POST"))
    check("전권 토큰은 스코프와 무관하게 통과", st == 200, str(st))

    napp = BearerAuthMiddleware(inner8, tok, scoped=(((None, REQUESTER_SCOPE),)))
    st, _b, _ = asyncio.run(call(napp, "/api/v1/works", headers=H, method="GET"))
    check("[중요] 토큰 파일이 없으면(None) 그 역할은 닫힌다 — 401", st == 401, str(st))

    check("난수성", len({generate_token() for _ in range(20)}) == 20)

    print(f"\n{'='*46}\n통과 {PASS} · 실패 {FAIL}\n{'='*46}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
