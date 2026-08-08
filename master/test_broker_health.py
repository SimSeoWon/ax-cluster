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
