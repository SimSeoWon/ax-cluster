"""마스터 브로커 HTTP 계층 — PLAN §4 (오케스트레이터는 여럿, 브로커는 하나).

작업자(윈도우 gjc·하네스)에게 **클러스터가 Ollama 하나로 보이게** 한다. gjc 가 실제로
부르는 엔드포인트는 `/api/chat`·`/api/tags`·`/api/show` 3종뿐이라(리포트 06 §3.5) 표면이 작다.
`/api/generate` 는 마스터 자신이 쓴다.

[중요] **브로커는 상태를 갖지 않는다.** 요청을 그대로 흘려보낼 뿐 `context` 를 붙이거나
재사용하지 않는다 (PLAN §2.4 stateless 원칙). 브로커가 아는 상태는 **어느 노드가 살아 있고
무엇을 상주 중인가** 뿐이고, 그건 라우팅에만 쓴다.

실행:
  AX_BROKER_PORT=8102 .venv/bin/python -m master.broker
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os

import httpx2 as httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..auth import BearerAuthMiddleware, load_token
from .config import DEFAULT_NUM_CTX, load_endpoints
from .health import ensure_pinned, refresh
from .routing import choose, union_tags

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("ax-broker")


def _same_model(a: str, b: str) -> bool:
    """Ollama 는 `x` 와 `x:latest` 를 같게 취급한다."""
    return a.removesuffix(":latest") == b.removesuffix(":latest")

HEALTH_INTERVAL_SEC = int(os.environ.get("AX_BROKER_HEALTH_SEC", "30"))
# 모델 적재가 붙으면 첫 응답이 60초를 넘는다(35B 냉시작 61.2s 실측). 읽기는 넉넉히,
# 연결은 짧게 — 죽은 노드를 빨리 판정해야 폴백이 의미가 있다.
_TIMEOUT = httpx.Timeout(connect=5.0, read=900.0, write=60.0, pool=10.0)


def create_app():
    """ASGI 앱. 반환형이 `FastAPI` 가 아니라 **인증 미들웨어로 감싼 ASGI 콜러블**이다."""
    endpoints, pins = load_endpoints()
    state: dict = {"inflight": {e.name: 0 for e in endpoints}, "repin_at": {}}
    app = FastAPI(title="AX cluster inference broker")

    # [중요] 인증 (PLAN §9.5.6). 토큰이 없으면 여기서 예외가 나고 서비스가 뜨지 않는다.
    #    `/health` 는 노드 주소와 적재 모델을 드러내므로 **인증 뒤에** 둔다.
    _auth_token = load_token()

    @app.get("/livez")
    def livez():
        """인증 없이 열린 유일한 경로. 살아 있다는 것 외에는 아무것도 알려주지 않는다."""
        return {"ok": True}
    app.state.endpoints = endpoints
    app.state.pins = pins
    app.state.broker = state
    client = httpx.AsyncClient(timeout=_TIMEOUT)
    app.state.client = client

    async def health_loop():
        while True:
            for ep in endpoints:
                await refresh(ep, client)
            for ep in endpoints:
                pin = pins.get(ep.name)
                if pin:
                    await ensure_pinned(ep, pin, client, state)
            await asyncio.sleep(HEALTH_INTERVAL_SEC)

    @app.on_event("startup")
    async def _startup():
        # 첫 갱신은 기다린다 — 아무것도 모르는 상태로 요청을 받으면 전부 503 이 된다.
        for ep in endpoints:
            await refresh(ep, client)
        app.state.task = asyncio.create_task(health_loop())
        log.info("브로커 기동 — 엔드포인트 %d개: %s", len(endpoints),
                 ", ".join(f"{e.name}({'up' if e.healthy else 'DOWN'})" for e in endpoints))

    @app.on_event("shutdown")
    async def _shutdown():
        t = getattr(app.state, "task", None)
        if t:
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t
        await client.aclose()

    # ── 관측 ──────────────────────────────────────────────────
    @app.get("/health")
    def health_ep():
        return {"endpoints": [
            {"name": e.name, "host": e.host, "healthy": e.healthy,
             "resident": e.resident, "pin": pins.get(e.name),
             "models": e.models, "inflight": state["inflight"].get(e.name, 0),
             "last_error": e.last_error}
            for e in endpoints]}

    # ── Ollama 호환 표면 ──────────────────────────────────────
    @app.get("/api/tags")
    def tags_ep():
        """건강한 노드들의 합집합 — 작업자에겐 클러스터가 하나로 보여야 한다."""
        return {"models": [{"name": n} for n in union_tags(endpoints)]}

    @app.get("/api/ps")
    def ps_ep():
        return {"models": [{"name": e.resident, "endpoint": e.name}
                           for e in endpoints if e.resident]}

    async def _proxy(request: Request, path: str, inject: bool = True):
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "본문이 JSON 이 아니다"}, status_code=400)
        model = (body.get("model") or "").strip()
        if not model:
            return JSONResponse({"error": "model 필드가 필요하다"}, status_code=400)
        ep, why = choose(endpoints, model)
        if ep is None:
            # [중요] fail-closed — 아무 노드에나 보내면 그쪽에서 pull 이 터진다.
            log.warning("[route] 거부 model=%s — %s", model, why)
            return JSONResponse({"error": why, "model": model}, status_code=503)
        log.info("[route] %s → %s (%s)", model, ep.name, why)

        # [중요] 상주 보호 (2026-08-08 실측 버그). 프록시한 요청에 `keep_alive` 가 없으면 Ollama 가
        # **노드 기본값으로 덮어쓴다** — BC-250 유닛은 `KEEP_ALIVE=30m` 이라, 브로커가 요청 하나
        # 흘려보낸 것만으로 영구 상주가 시한부로 풀렸다. 이 노드가 상주시켜야 할 모델이면
        # `-1` 을 넣어 지킨다. **호출자가 명시했으면 존중한다** — 일시 사용은 그쪽 의도다.
        # (`/api/show` 는 추론 호출이 아니라 메타 조회다 — 이 필드들을 받지 않으므로 주입하지 않는다.)
        if inject:
            if ("keep_alive" not in body and pins.get(ep.name)
                    and _same_model(model, pins[ep.name])):
                body["keep_alive"] = -1
            # [중요] 재적재 방지. `num_ctx` 가 요청마다 다르면 모델을 통째로 다시 올린다(61.6s 실측).
            opts = body.setdefault("options", {})
            if isinstance(opts, dict) and "num_ctx" not in opts:
                opts["num_ctx"] = DEFAULT_NUM_CTX

        state["inflight"][ep.name] = state["inflight"].get(ep.name, 0) + 1
        url = f"http://{ep.host}{path}"
        stream = bool(body.get("stream", False))

        if not stream:
            try:
                r = await client.post(url, json=body)
                return JSONResponse(json.loads(r.text), status_code=r.status_code,
                                    headers={"X-AX-Endpoint": ep.name})
            except Exception as e:
                ep.healthy = False   # 다음 헬스 사이클이 되살리거나 확정한다
                log.error("[route] %s 실패: %s: %s", ep.name, type(e).__name__, e)
                return JSONResponse({"error": f"{ep.name}: {type(e).__name__}: {e}"},
                                    status_code=502)
            finally:
                state["inflight"][ep.name] -= 1

        async def gen():
            try:
                async with client.stream("POST", url, json=body) as r:
                    async for chunk in r.aiter_bytes():
                        yield chunk
            except Exception as e:
                ep.healthy = False
                log.error("[route] %s 스트림 실패: %s: %s", ep.name, type(e).__name__, e)
                yield json.dumps({"error": f"{ep.name}: {e}"}).encode() + b"\n"
            finally:
                state["inflight"][ep.name] -= 1

        return StreamingResponse(gen(), media_type="application/x-ndjson",
                                 headers={"X-AX-Endpoint": ep.name})

    @app.post("/api/chat")
    async def chat_ep(request: Request):
        return await _proxy(request, "/api/chat")

    @app.post("/api/generate")
    async def generate_ep(request: Request):
        return await _proxy(request, "/api/generate")

    @app.post("/api/show")
    async def show_ep(request: Request):
        return await _proxy(request, "/api/show", inject=False)

    # [중요] 라우트를 전부 등록한 **뒤** 감싼다. 미들웨어는 바깥이므로 순서가 중요하다.
    return BearerAuthMiddleware(app, _auth_token)
