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

`register_work` 를 그대로 부른다. 분해·골조·게이트는 전부 그쪽 몫이고,
여기는 **HTTP 를 파이썬 호출로 바꾸는 얇은 층**이다. 실패는 사유를 실어 200 + `ok:false` 로
낸다 — 이 저장소의 거절 관례다(*"거부도 200 + ok:false 로 말한다"*).
"""
from __future__ import annotations

import json
import traceback

PATH = "/work/register"
MAX_BODY = 1 << 20                      # 1MB — 명세 목록이 커도 이 안이다


def _log(scope, msg: str) -> None:
    """저널 한 줄. [중요] **성공도 찍는다** — 거절만 찍으면 「등재가 왔는데 왜 없나」를 못 쫓는다.

    [주의] 큐는 전이마다 `~/ax-state` 에 커밋까지 남기지만(`[work-register]` · `[register]`),
    **여기서 거절되면 큐에 아무것도 안 간다.** 그 구간이 비면 요청자만 사유를 알고 서버는
    모른다 — 사용자 지적(2026-08-30): *"로그를 남기고, 그래야 버그가 있을때 찾지"*.
    """
    cli = (scope.get("client") or ("?", 0))[0]
    print(f"[register] {cli} {msg}", flush=True)


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

    # [중요] **형을 여기서 검사한다** (실측 2026-08-30). `TaskSpec(**s)` 는 dataclass 라
    #    **형을 검사하지 않는다** — `.33` 이 `contracts` 를 리스트로 보냈고 그대로 통과한 뒤
    #    등재가 `'list' object has no attribute 'strip'` 로 터졌다. 그때는 이미
    #    work 과 태스크 일부가 만들어진 뒤라 **반쪽 등재**가 남았다(`#336` ③).
    #    깊은 곳에서 터지는 것보다 **입구에서 사유를 말하고 거절하는 것**이 낫다.
    import dataclasses as _dc
    _TYPES = {f.name: f.type for f in _dc.fields(TaskSpec)}
    _STR = {"stem", "contracts", "skeleton", "target_file", "header_file", "instruction"}
    _LIST = {"classes", "target_files", "depends_on", "requires", "source_files", "depth_set"}

    specs = []
    for i, s in enumerate(raw_specs):
        if not isinstance(s, dict):
            return {"ok": False, "reason": "bad_specs", "error": f"specs[{i}] 가 객체가 아니다"}
        for k, v in s.items():
            if k in _STR and not isinstance(v, str):
                return {"ok": False, "reason": "bad_specs",
                        "error": f"specs[{i}].{k} 는 문자열이어야 한다 — {type(v).__name__} 이 왔다",
                        "hint": (f"`{k}` 가 여러 줄이면 줄바꿈으로 이어 붙인 **한 문자열**로 보낸다"
                                 if isinstance(v, list) else f"`{k}` 의 값 형을 확인하라")}
            if k in _LIST and not isinstance(v, list):
                return {"ok": False, "reason": "bad_specs",
                        "error": f"specs[{i}].{k} 는 배열이어야 한다 — {type(v).__name__} 이 왔다"}
            if k == "priority" and not isinstance(v, int):
                return {"ok": False, "reason": "bad_specs",
                        "error": f"specs[{i}].priority 는 정수여야 한다 — {type(v).__name__} 이 왔다"}
        try:
            specs.append(TaskSpec(**s))
        except TypeError as e:
            # [중요] **무엇이 유효한지 말한다.** 종전에는 파이썬 `TypeError` 를 그대로 흘려서
            #    (`got an unexpected keyword argument 'summary'`) 호출자가 **고칠 근거가
            #    없었다.** 실측 2026-08-30: `.33` 이 첫 실전 등재에서 `summary` 를 지어내 실었고
            #    거절 사유만 보고는 무엇을 빼야 하는지 알 수 없었다.
            #    이 저장소 관례다 — *"거부도 200 + ok:false 로 말한다"* 는 **사유와 조치**를
            #    준다는 뜻이지 예외 문자열을 전달한다는 뜻이 아니다.
            import dataclasses
            valid = [f.name for f in dataclasses.fields(TaskSpec)]
            unknown = sorted(set(s) - set(valid))
            return {"ok": False, "reason": "bad_specs",
                    "error": f"specs[{i}]: {e}",
                    "unknown_fields": unknown,
                    "valid_fields": valid,
                    "hint": (f"모르는 필드를 빼라: {', '.join(unknown)}" if unknown
                             else "필드 이름은 맞는데 형이 틀리다 — 값 타입을 확인하라")}

    paths = resolve(project)
    got = register_work(
        title, specs, paths=paths,
        target_repo=str(payload.get("target_repo") or project),
        original_request=str(payload.get("original_request") or ""),
        target_branch=str(payload.get("target_branch") or ""),
    )
    return {"ok": bool(got.ok), "work_id": got.work_id, "summary": got.summary(),
            "tasks": [{"stem": t.stem, "task_id": t.task_id, "error": t.error}
                      for t in got.tasks]}


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
            _log(scope, f"거절 too_large — {e}")
            return await _send_json(send, {"ok": False, "reason": "too_large", "error": str(e)}, 413)
        try:
            payload = json.loads(raw or b"{}")
        except ValueError as e:
            _log(scope, f"거절 bad_json — {e}")
            return await _send_json(send, {"ok": False, "reason": "bad_json",
                                           "error": f"본문이 JSON 이 아니다: {e}"})
        if not isinstance(payload, dict):
            _log(scope, "거절 bad_json — 최상위가 객체가 아니다")
            return await _send_json(send, {"ok": False, "reason": "bad_json",
                                           "error": "본문 최상위가 객체가 아니다"})
        _log(scope, f"수신 project={payload.get('project') or '(없음)'} "
                    f"title={str(payload.get('title') or '')[:60]!r} "
                    f"specs={len(payload.get('specs') or []) if isinstance(payload.get('specs'), list) else '?'}")
        try:
            import anyio
            got = await anyio.to_thread.run_sync(_run, payload)
        except Exception as e:                              # noqa: BLE001
            # [중요] 스택을 그대로 흘리지 않는다 — 사유 한 줄과 형만 준다.
            #    `validate_spec` 이 값을 치른 자리와 같다: 사유를 말해야 하는 곳에서
            #    생 트레이스백을 보여주면 호출자가 조치를 못 고른다.
            #    [주의] 다만 **저널에는 전체 트레이스백을 남긴다** — 서버에서 못 쫓으면
            #    사유만으로는 고칠 수 없다.
            print("[register] 예외:\n" + traceback.format_exc(), flush=True)
            return await _send_json(send, {"ok": False, "reason": "server_error",
                                           "error": f"{type(e).__name__}: {e}"})
        if got.get("ok"):
            _log(scope, f"[완료] work={got.get('work_id')} "
                        f"태스크={len(got.get('tasks') or [])}")
        else:
            _log(scope, f"거절 {got.get('reason') or '?'} — {str(got.get('error') or '')[:200]}")
        return await _send_json(send, got)
