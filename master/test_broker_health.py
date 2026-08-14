"""헬스루프·상주 재확립 계약 테스트 — PLAN §9.4.2.

핵심은 **재확립이 쓰이고 있는 모델을 쫓아내지 않는가**다. `MAX_LOADED_MODELS=1` 이라
다른 모델을 올리는 것은 곧 지금 것을 내리는 것이고, 폴백 요청 처리 중에 그러면 그 요청이 죽는다.

실행: .venv/bin/python master/test_broker_health.py   (asyncio 필요, 네트워크는 안 씀)
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.broker.health import ensure_pinned, refresh  # noqa: E402
from master.broker.routing import Endpoint  # noqa: E402

PIN = "driver:big"


class FakeResp:
    def __init__(self, data, code=200):
        self._d, self.status_code = data, code

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeClient:
    """/api/tags·/api/ps 응답을 흉내내고 POST(적재) 호출을 기록한다."""

    def __init__(self, tags=None, ps=None, fail_get=False):
        self.tags = tags if tags is not None else ["driver:big", "coder:small"]
        self.ps = ps
        self.fail_get = fail_get
        self.posts: list[dict] = []

    async def get(self, url, timeout=None):
        if self.fail_get:
            raise ConnectionError("노드 죽음")
        if url.endswith("/api/tags"):
            return FakeResp({"models": [{"name": n} for n in self.tags]})
        return FakeResp({"models": ([{"name": self.ps}] if self.ps else [])})

    async def post(self, url, json=None, timeout=None):
        self.posts.append(json or {})
        return FakeResp({"done": True})


def _ep(**kw) -> Endpoint:
    d = dict(name="n1", host="h:1", healthy=True)
    d.update(kw)
    return Endpoint(**d)


def _state(inflight=0):
    return {"inflight": {"n1": inflight}, "repin_at": {}}


# ── refresh ──────────────────────────────────────────────────

def test_refresh_records_models_and_resident():
    ep = _ep(healthy=False)
    asyncio.run(refresh(ep, FakeClient(ps="coder:small")))
    assert ep.healthy and ep.models == ["driver:big", "coder:small"]
    assert ep.resident == "coder:small"


def test_refresh_marks_dead_node_and_clears_state():
    """죽은 노드가 옛 보유 목록을 들고 있으면 라우팅이 거기로 보낸다."""
    ep = _ep(models=["driver:big"], resident="driver:big")
    asyncio.run(refresh(ep, FakeClient(fail_get=True)))
    assert not ep.healthy and ep.models == [] and ep.resident is None
    assert "ConnectionError" in ep.last_error


# ── 🔴 상주 재확립 ───────────────────────────────────────────

def test_repins_when_pin_fell_off():
    ep = _ep(resident=None)
    st = _state()
    c = FakeClient()
    assert asyncio.run(ensure_pinned(ep, PIN, c, st)) is True
    assert c.posts and c.posts[0]["model"] == PIN
    assert c.posts[0]["keep_alive"] == -1     # 영구 상주로 올려야 의미가 있다
    assert ep.resident == PIN


def test_repin_carries_num_ctx():
    """🔴 **워밍업에 `num_ctx` 가 없으면 노드가 죽는다** (2026-08-15 실측).

    안 실으면 Ollama 가 모델 기본 `context_length`(35B 는 262144) 전제로 KV 를 잡는다.
    BC-250 여유가 2.2GB 인데 그 할당이 ~2.0GB 다(리포트 10 §8). 프록시 경로에는 이 가드가
    있었고 **이 경로에만 없어서** repin 직후 보드가 멈췄다.
    """
    from master.broker.config import DEFAULT_NUM_CTX
    c = FakeClient()
    assert asyncio.run(ensure_pinned(_ep(resident=None), PIN, c, _state())) is True
    opts = c.posts[0].get("options") or {}
    assert opts.get("num_ctx") == DEFAULT_NUM_CTX, opts
    # 🔴 프록시와 **같은 값**이어야 한다 — 다르면 다음 요청이 통째로 재적재된다(61.6s 실측)
    from master.broker import server as srv
    assert srv.DEFAULT_NUM_CTX == DEFAULT_NUM_CTX


def test_no_repin_when_resident_unknown():
    """🔴 **「상주 없음」과 「못 읽었다」는 다르다.** `/api/ps` 가 실패한 노드에 재적재를 걸면
    힘들어하는 보드에 **가장 비싼 일**을 시킨다. 판정 불가는 보존이다(리포트 16 §10)."""
    ep = _ep(models=["driver:big"], resident="driver:big")

    class PsFails(FakeClient):
        async def get(self, url, timeout=None):
            if url.endswith("/api/ps"):
                raise ConnectionError("ps 실패")
            return await FakeClient.get(self, url, timeout)

    c = PsFails()
    asyncio.run(refresh(ep, c))
    assert ep.healthy and ep.resident is None and ep.resident_known is False
    assert "ps:" in ep.last_error
    assert asyncio.run(ensure_pinned(ep, PIN, c, _state())) is False
    assert c.posts == [], c.posts          # 🔴 적재 요청을 보내지 않았다


def test_repin_still_runs_when_ps_says_empty():
    """반대쪽도 고정한다 — `/api/ps` 가 **정상적으로** 「없음」을 말하면 재적재는 해야 한다."""
    ep = _ep()
    c = FakeClient(ps=None)
    asyncio.run(refresh(ep, c))
    assert ep.resident is None and ep.resident_known is True
    assert asyncio.run(ensure_pinned(ep, PIN, c, _state())) is True
    assert c.posts and c.posts[0]["model"] == PIN


def test_no_repin_when_already_resident():
    ep = _ep(resident=PIN)
    c = FakeClient()
    assert asyncio.run(ensure_pinned(ep, PIN, c, _state())) is False
    assert c.posts == []


def test_latest_alias_counts_as_resident():
    ep = _ep(resident="driver:big")
    c = FakeClient()
    assert asyncio.run(ensure_pinned(ep, "driver:big:latest", c, _state())) is False
    assert c.posts == []


def test_never_evicts_a_model_in_use():
    """🔴 이 테스트가 이 모듈의 존재 이유다 — 처리 중인 요청을 죽이면 안 된다."""
    ep = _ep(resident="coder:small")     # 폴백으로 다른 모델을 쓰는 중
    c = FakeClient()
    assert asyncio.run(ensure_pinned(ep, PIN, c, _state(inflight=1))) is False
    assert c.posts == []                 # 적재 시도 자체가 없어야 한다


def test_no_repin_on_dead_node():
    ep = _ep(healthy=False, resident=None)
    c = FakeClient()
    assert asyncio.run(ensure_pinned(ep, PIN, c, _state())) is False
    assert c.posts == []


def test_backoff_prevents_hammering():
    """적재는 비싸다(35B 61s). 실패해도 매 사이클 두드리면 안 된다."""
    ep = _ep(resident=None)
    st = _state()
    c = FakeClient()
    asyncio.run(ensure_pinned(ep, PIN, c, st))
    ep.resident = None                    # 적재가 사실은 실패했다고 치고
    assert asyncio.run(ensure_pinned(ep, PIN, c, st)) is False
    assert len(c.posts) == 1


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} 통과")
    sys.exit(1 if failed else 0)
