"""요청자 등재 표면 — `POST /work/register` (`#336` ④).

## 왜 새 라우트인가

`ax-request` §3 은 오래 *"`register_work_tool(...)` 을 부르라"* 고 적어 왔는데 **요청자에게는
그 경로가 없었다**(실측 2026-08-29): 클라 MCP 로스터에 `register_work` 0건이고,
`REQUESTER_SCOPE` 에도 등재 경로가 없어 **403 이 정상 동작**이었다. 절차서가 못 하는 것을
지시하던 `#297` 부류다. 그날은 마스터가 대신 등재해 넘겼고, `~/CLAUDE.md` 가 그것을
*"Registration from the master is only ever standing in for this"* 로 못박아 뒀다.

버린 갈래 둘 (사용자 결정 2026-08-30):

    ⓐ 8103 `/mcp` 를 요청자에게 연다   스코프는 **경로 단위**라 도구별로 못 가른다 —
                                      열면 온톨로지 쓰기·프로젝트 등록까지 전부 열린다
    ⓒ 큐(8101)로 등재를 옮긴다        등재는 트윈·검색기·골조·매니페스트를 만진다.
                                      큐는 「단일 writer」로 상태만 갖는다 — 층이 흐려진다

## [중요] 경로가 `/api/v1/` 밖인 것이 의도다

8103 의 `/api/v1/*` 는 **무인증 공개**다(`webui.app.PREFIXES` → `public_prefixes`). 실측
2026-08-25: 토큰 없이 200, 루프백과 LAN 둘 다. 거기 등재를 두면 **아무나 등재할 수 있다.**
그래서 `/work/register` 로 뺐고, 그 경로는 `BearerAuthMiddleware` 를 정면으로 탄다.

## [주의] 이 모듈은 판단하지 않는다

`register_work` 를 그대로 부른다. 분해·골조·게이트·매니페스트·carry 는 전부 그쪽 몫이고,
여기는 **HTTP 를 파이썬 호출로 바꾸는 얇은 층**이다. 실패는 사유를 실어 200 + `ok:false` 로
낸다 — 이 저장소의 거절 관례다(*"거부도 200 + ok:false 로 말한다"*).
"""
from __future__ import annotations

import json
import traceback

PATH = "/work/register"
MAX_BODY = 1 << 20                      # 1MB — 명세 목록이 커도 이 안이다


async def _read_body(receive) -> bytes:
    chunks, total = [], 0
    while True:
        msg = await receive()
        if msg["type"] != "http.request":
            break
        chunk = msg.get("body") or b""
        total += len(chunk)
        if total > MAX_BODY:
            raise ValueError(f"본문이 {MAX_BODY} 바이트를 넘는다")
        chunks.append(chunk)
        if not msg.get("more_body"):
            break
    return b"".join(chunks)


async def _send_json(send, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json; charset=utf-8"),
                            (b"content-length", str(len(body)).encode()),
                            (b"cache-control", b"no-store")]})
    await send({"type": "http.response.body", "body": body})


def _run(payload: dict) -> dict:
    """등재 한 번. [중요] 여기서 판단하지 않는다 — `register_work` 가 다 한다."""
    from ..context_search.paths import resolve
    from ..work.register import TaskSpec, register_work

    project = str(payload.get("project") or "").strip()
    if not project:
        # [중요] 태그 계약(`#257`) — 쓰는 요청은 프로젝트 태그를 싣는다. 폴백은 없다.
        return {"ok": False, "reason": "no_project_tag",
                "error": "project 태그가 없다 — 쓰는 요청은 태그를 싣는다 (`#257`)"}
    title = str(payload.get("title") or "").strip()
    if not title:
        return {"ok": False, "reason": "no_title", "error": "title 이 비었다"}

    raw_specs = payload.get("specs")
    if isinstance(raw_specs, str):
        try:
            raw_specs = json.loads(raw_specs)
        except ValueError as e:
            return {"ok": False, "reason": "bad_specs",
                    "error": f"specs 가 JSON 이 아니다: {e}"}
    if not isinstance(raw_specs, list) or not raw_specs:
        return {"ok": False, "reason": "bad_specs", "error": "specs 가 비었거나 배열이 아니다"}

    specs = []
    for i, s in enumerate(raw_specs):
        if not isinstance(s, dict):
            return {"ok": False, "reason": "bad_specs", "error": f"specs[{i}] 가 객체가 아니다"}
        try:
            specs.append(TaskSpec(**s))
        except TypeError as e:
            return {"ok": False, "reason": "bad_specs",
                    "error": f"specs[{i}]: 모르는 필드이거나 형이 틀리다 — {e}"}

    paths = resolve(project)
    got = register_work(
        title, specs, paths=paths,
        target_repo=str(payload.get("target_repo") or project),
        original_request=str(payload.get("original_request") or ""),
        target_branch=str(payload.get("target_branch") or ""),
    )
    return {"ok": bool(got.ok), "work_id": got.work_id, "summary": got.summary(),
            "tasks": [{"stem": t.stem, "task_id": t.task_id, "error": t.error,
                       "manifest_degraded": t.manifest_degraded} for t in got.tasks]}


class RegisterApp:
    """`POST /work/register` 만 처리하고 나머지는 뒤로 넘기는 얇은 ASGI 층."""

    def __init__(self, next_app):
        self.next_app = next_app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("path") != PATH:
            return await self.next_app(scope, receive, send)
        if (scope.get("method") or "").upper() != "POST":
            return await _send_json(send, {"ok": False, "error": "POST 만 받는다"}, 405)
        try:
            raw = await _read_body(receive)
        except ValueError as e:
            return await _send_json(send, {"ok": False, "reason": "too_large", "error": str(e)}, 413)
        try:
            payload = json.loads(raw or b"{}")
        except ValueError as e:
            return await _send_json(send, {"ok": False, "reason": "bad_json",
                                           "error": f"본문이 JSON 이 아니다: {e}"})
        if not isinstance(payload, dict):
            return await _send_json(send, {"ok": False, "reason": "bad_json",
                                           "error": "본문 최상위가 객체가 아니다"})
        try:
            import anyio
            got = await anyio.to_thread.run_sync(_run, payload)
        except Exception as e:                              # noqa: BLE001
            # [중요] 스택을 그대로 흘리지 않는다 — 사유 한 줄과 형만 준다.
            #    `validate_spec` 이 값을 치른 자리와 같다: 사유를 말해야 하는 곳에서
            #    생 트레이스백을 보여주면 호출자가 조치를 못 고른다.
            print("[register_route] " + "".join(traceback.format_exception_only(type(e), e)).strip())
            return await _send_json(send, {"ok": False, "reason": "server_error",
                                           "error": f"{type(e).__name__}: {e}"})
        return await _send_json(send, got)
