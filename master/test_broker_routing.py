"""브로커 라우팅 계약 테스트 — PLAN §4.

핵심은 **재적재를 피하는 순서로 고르는가**, 그리고 **죽은 노드로 보내지 않는가**.
실행: python3 master/test_broker_routing.py   (venv 불필요 — 순수 로직)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.broker.routing import Endpoint, choose, union_tags  # noqa: E402

CODER = "qwen2.5-coder:14b"
BIG = "hf.co/bartowski/Qwen_Qwen3.5-35B-A3B-GGUF:IQ2_M"


def _bc250(**kw) -> Endpoint:
    d = dict(name="bc250", host="192.168.0.43:11434", prefer=[BIG],
             models=[CODER, BIG], healthy=True)
    d.update(kw)
    return Endpoint(**d)


def _rtx(**kw) -> Endpoint:
    d = dict(name="rtx3060", host="192.168.0.2:11434", prefer=[CODER],
             models=[CODER, "gemma3:12b"], healthy=True)
    d.update(kw)
    return Endpoint(**d)


# ── 정상 라우팅 ──────────────────────────────────────────────

def test_prefer_routes_each_model_to_its_home():
    eps = [_bc250(), _rtx()]
    assert choose(eps, BIG)[0].name == "bc250"
    assert choose(eps, CODER)[0].name == "rtx3060"


def test_resident_beats_prefer():
    """이미 VRAM 에 올라와 있으면 적재가 0이다 — prefer 보다 우선."""
    eps = [_bc250(resident=CODER), _rtx(resident="gemma3:12b")]
    ep, why = choose(eps, CODER)
    assert ep.name == "bc250" and "상주" in why


def test_resident_latest_alias_matches():
    eps = [_rtx(models=["llama3:latest"], prefer=[], resident="llama3:latest")]
    ep, why = choose(eps, "llama3")
    assert ep is not None and "상주" in why


# ── 🔴 `#715` 같은 모델이 여러 노드에 상주 — 처리 중 요청이 적은 쪽 ──────────────────

SYNTH = "gemma4:e4b"


def test_two_resident_nodes_split_by_inflight():
    """설계 규칙 *"마스터가 요청을 나눈다"* — 종전엔 목록의 첫 노드만 골랐다."""
    eps = [_bc250(models=[SYNTH], resident=SYNTH), _rtx(models=[SYNTH], resident=SYNTH)]
    ep, why = choose(eps, SYNTH, {"bc250": 1, "rtx3060": 0})
    assert ep.name == "rtx3060" and "최소" in why, why
    ep, _ = choose(eps, SYNTH, {"bc250": 0, "rtx3060": 2})
    assert ep.name == "bc250"


def test_tie_keeps_list_order():
    eps = [_bc250(models=[SYNTH], resident=SYNTH), _rtx(models=[SYNTH], resident=SYNTH)]
    assert choose(eps, SYNTH, {"bc250": 1, "rtx3060": 1})[0].name == "bc250"


def test_three_resident_nodes_use_idle_3080():
    eps = [_bc250(models=[SYNTH], resident=SYNTH),
           _rtx(models=[SYNTH], resident=SYNTH),
           Endpoint(name="rtx3080", host="192.168.0.33:11434", prefer=[SYNTH],
                    models=[SYNTH], resident=SYNTH, healthy=True)]
    assert choose(eps, SYNTH, {"bc250": 1, "rtx3060": 1, "rtx3080": 0})[0].name == "rtx3080"
    eps[2].healthy = False
    assert choose(eps, SYNTH, {"bc250": 2, "rtx3060": 1, "rtx3080": 0})[0].name == "rtx3060"


def test_no_inflight_given_is_the_old_behaviour():
    """`inflight` 를 안 주는 호출자는 종전 그대로 — 첫 상주 노드."""
    eps = [_bc250(models=[SYNTH], resident=SYNTH), _rtx(models=[SYNTH], resident=SYNTH)]
    assert choose(eps, SYNTH)[0].name == "bc250"


def test_inflight_never_beats_residency():
    """[중요] 한가해도 상주가 아니면 고르지 않는다 — 재적재(최대 45s)가 대기보다 비싸다."""
    eps = [_bc250(models=[SYNTH], resident=SYNTH), _rtx(models=[SYNTH, CODER], resident=CODER)]
    assert choose(eps, SYNTH, {"bc250": 5, "rtx3060": 0})[0].name == "bc250"


# ── [중요] 폴백·실패 ─────────────────────────────────────────────

def test_falls_back_when_prefer_node_is_down():
    """3060 이 죽으면 14b 는 BC-250 으로 — 재적재를 물지만 응답은 된다."""
    eps = [_bc250(), _rtx(healthy=False)]
    ep, why = choose(eps, CODER)
    assert ep.name == "bc250" and "폴백" in why


def test_never_routes_to_unhealthy_node():
    eps = [_bc250(healthy=False), _rtx(healthy=False)]
    ep, why = choose(eps, CODER)
    assert ep is None and "건강한 엔드포인트가 없다" in why


def test_missing_model_is_not_guessed():
    """보유하지 않은 모델을 아무 노드에나 보내면 그쪽에서 pull 이 터진다."""
    eps = [_bc250(models=[BIG]), _rtx(models=["gemma3:12b"])]
    ep, why = choose(eps, CODER)
    assert ep is None and CODER in why


def test_big_model_has_no_fallback_today():
    """35B(12.91GiB)는 3060(12GB)에 안 들어간다 — 보유 목록에 없으니 폴백도 없다."""
    eps = [_bc250(healthy=False), _rtx()]
    ep, _ = choose(eps, BIG)
    assert ep is None


# ── /api/tags 합집합 ─────────────────────────────────────────

def test_union_tags_hides_the_cluster():
    """작업자에게는 클러스터가 Ollama 하나로 보여야 한다."""
    assert union_tags([_bc250(), _rtx()]) == sorted({CODER, BIG, "gemma3:12b"})


def test_union_tags_excludes_dead_nodes():
    assert union_tags([_bc250(healthy=False), _rtx()]) == sorted({CODER, "gemma3:12b"})



# ── #853 노드별 동시 요청 상한 ──────────────────────────────────

def _hot(name, host="h:1"):
    return Endpoint(name, host, models=[CODER], resident=CODER, healthy=True)


def test_cap_skips_full_resident_node_853():
    a, b = _hot("a"), _hot("b")
    ep, why = choose([a, b], CODER, {"a": 2, "b": 1}, cap=2)
    assert ep is b, why


def test_cap_all_resident_full_is_saturated_no_reload_853():
    """상주 노드가 전부 차면 즉시 None(포화) — 비상주 노드 재적재로 흘리지 않는다."""
    a = _hot("a")
    cold = Endpoint("cold", "c:1", models=[CODER], resident="other:1b", healthy=True, prefer=[CODER])
    ep, why = choose([a, cold], CODER, {"a": 2}, cap=2)
    assert ep is None and "포화" in why and "#853" in why, why


def test_cap_under_limit_keeps_old_choice_853():
    a, b = _hot("a"), _hot("b")
    assert choose([a, b], CODER, {"a": 1, "b": 1}, cap=2)[0] is a     # 같으면 목록 순서(종전)


def test_cap_released_node_comes_back_853():
    a = _hot("a")
    assert choose([a], CODER, {"a": 2}, cap=2)[0] is None
    assert choose([a], CODER, {"a": 1}, cap=2)[0] is a


def test_cap_zero_is_unlimited_853():
    a = _hot("a")
    assert choose([a], CODER, {"a": 99}, cap=0)[0] is a
    assert choose([a], CODER, {"a": 99})[0] is a                       # 기본값 = 종전 동작


def test_cap_cold_path_skips_full_and_saturates_853():
    """상주가 없을 때 — prefer·폴백도 찬 노드는 건너뛰고, 전부 차면 포화."""
    p = Endpoint("p", "p:1", models=[CODER], resident=None, healthy=True, prefer=[CODER])
    q = Endpoint("q", "q:1", models=[CODER], resident=None, healthy=True)
    assert choose([p, q], CODER, {"p": 2}, cap=2)[0] is q
    ep, why = choose([p, q], CODER, {"p": 2, "q": 2}, cap=2)
    assert ep is None and "포화" in why, why


def test_server_node_cap_env_853():
    import importlib
    import os
    from master.broker import server as S
    for raw, want in (("", 4), ("3", 3), ("0", 0), ("-1", 0), ("x", 4)):
        os.environ["AX_BROKER_NODE_CAP"] = raw
        assert S._node_cap() == want, (raw, S._node_cap())
    os.environ.pop("AX_BROKER_NODE_CAP", None)
    importlib.reload(S)
    assert S.NODE_CAP == 4 == S.DEFAULT_NODE_CAP      # 사용자 결정 2026-11-01(②)


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
