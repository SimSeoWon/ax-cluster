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
