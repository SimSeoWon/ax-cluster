"""`verdict.py` 계약 테스트 — 핵심은 **어떤 실패 경로도 APPROVE 로 새지 않는다**는 것.

실행: python3 -m pytest master/test_verdict.py -q   (또는 python3 master/test_verdict.py)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from verdict import APPROVE, REQUEST_CHANGES, contract_text, parse_verdict  # noqa: E402


# ── 정상 경로 ────────────────────────────────────────────────

def test_approve():
    v = parse_verdict(f"Looks fine.\n{APPROVE}")
    assert v.approved and v.failure is None


def test_request_changes_with_findings():
    v = parse_verdict(f"- foo.cpp: 세미콜론 누락\n- bar.h: UPROPERTY 오용\n{REQUEST_CHANGES}")
    assert not v.approved and v.failure is None
    assert v.findings == ["foo.cpp: 세미콜론 누락", "bar.h: UPROPERTY 오용"]


def test_trailing_blank_lines_ignored():
    v = parse_verdict(f"{APPROVE}\n\n   \n")
    assert v.approved


# ── [중요] fail-closed 경로 — 전부 승인되지 않아야 한다 ──────────────

def test_none_output_is_blocked():
    """백엔드 부재·타임아웃·예외. 기존 syntax_check 는 여기서 통과시켰다."""
    v = parse_verdict(None, backend="agy")
    assert not v.approved and v.failure == "no_output"


def test_empty_output_is_blocked():
    assert not parse_verdict("").approved
    assert not parse_verdict("   \n\n  ").approved
    assert parse_verdict("").failure == "empty"


def test_missing_verdict_line_is_blocked():
    v = parse_verdict("The code looks good to me, no issues found.")
    assert not v.approved and v.failure == "malformed"


def test_verdict_not_on_last_line_is_blocked():
    """판정 뒤에 뭔가 따라오면 계약 위반이다."""
    v = parse_verdict(f"{APPROVE}\nHope this helps!")
    assert not v.approved and v.failure == "malformed"


def test_lookalike_tokens_are_blocked():
    for bad in ["VERDICT: APPROVED", "VERDICT:APPROVE", "APPROVE",
                "verdict: approve", "VERDICT: OK", "VERDICT: LGTM"]:
        v = parse_verdict(f"검토함\n{bad}")
        assert not v.approved, f"{bad!r} 가 통과했다"
        assert v.failure == "malformed"


def test_json_style_old_output_is_blocked():
    """기존 프롬프트가 시키던 JSON 응답은 새 계약에서 통과하면 안 된다(마이그레이션 안전)."""
    v = parse_verdict('{"ok": true, "errors": []}')
    assert not v.approved and v.failure == "malformed"


# ── 장식 정규화 ──────────────────────────────────────────────

def test_markdown_decoration_is_stripped_but_warned():
    for decorated in [f"**{APPROVE}**", f"`{APPROVE}`", f"> {APPROVE}", f"{APPROVE}."]:
        v = parse_verdict(f"검토함\n{decorated}")
        assert v.approved, f"{decorated!r} 를 못 읽었다"
        assert v.warnings, "장식을 벗겨냈으면 경고를 남겨야 한다"


def test_echoed_token_in_body_warns_but_last_line_wins():
    v = parse_verdict(f"계약대로 {REQUEST_CHANGES} 를 내겠다\n- a.cpp: 오류\n{REQUEST_CHANGES}")
    assert not v.approved and v.failure is None      # 계약 위반이 아니라 정상 REQUEST_CHANGES
    v2 = parse_verdict(f"{REQUEST_CHANGES}\n- a.cpp: 오류\n{APPROVE}")
    assert v2.approved and any("본문에도" in w for w in v2.warnings)


def test_request_changes_without_findings_warns():
    v = parse_verdict(REQUEST_CHANGES)
    assert not v.approved and v.failure is None
    assert any("지적 항목이 없다" in w for w in v.warnings)


# ── 계약 지시문 ──────────────────────────────────────────────

def test_contract_text_contains_both_tokens():
    t = contract_text()
    assert APPROVE in t and REQUEST_CHANGES in t


def test_summary_distinguishes_violation_from_rejection():
    assert "계약 위반" in parse_verdict(None).summary()
    assert "REQUEST_CHANGES" in parse_verdict(f"- x\n{REQUEST_CHANGES}").summary()
    assert parse_verdict(APPROVE).summary() == "APPROVE"


# ── verify_files 의 백엔드 체이닝 ────────────────────────────
# 규칙: "응답 없음"은 다음 백엔드로 넘어가고, "응답은 왔는데 계약 위반"은 거기서 차단한다.
# 후자를 다음 백엔드로 덮어주면 fail-open 이 되살아난다.

from layer2_verify import clear_cooldown, cooldown_state, verify_files  # noqa: E402

_FILES = [("Foo.cpp", "void f() {}")]


def _backend(name, result):
    return (name, lambda prompt, timeout=0: result)


def _chain(*backends):
    """[중요] **쿨다운은 프로세스 전역이다 — 테스트마다 지운다.**

    실측 2026-08-13: `test_chain_approve_passes_through` 와 `test_chain_skips_unavailable_backend`
    가 **번갈아 실패**했다(17/19). 원인은 계약이 아니라 **테스트 간 상태 누출**이었다 —
    앞선 테스트에서 `None` 을 돌려준 백엔드 `a` 가 600초 쿨다운에 들어가고, 다음 테스트가 같은
    이름 `a` 를 쓰면 호출조차 되지 않아 `no_backend` 가 된다.

    [주의] **`layer2_verify` 쪽을 고칠 문제가 아니다.** 전역 쿨다운은 의도한 동작이다(죽은 백엔드를
    조각마다 다시 두드리지 않는다 — 소 2.2.3). 순서 의존이 숨어 있던 쪽은 테스트다. 그래서
    여기서 지운다. [중요] 이름이 겹치는 스텁을 쓰는 새 테스트도 반드시 이 함수를 거칠 것.
    """
    clear_cooldown()
    return verify_files(_FILES, backends=list(backends))


def test_chain_skips_unavailable_backend():
    v = _chain(_backend("a", None), _backend("b", f"- x\n{REQUEST_CHANGES}"))
    assert not v.approved and v.failure is None
    assert "backend=b" in v.warnings


def test_chain_stops_on_contract_violation_does_not_fall_through():
    """계약을 어긴 백엔드를 다음 백엔드가 구제하면 안 된다."""
    v = _chain(_backend("bad", "looks fine to me"), _backend("good", APPROVE))
    assert not v.approved, "계약 위반이 다음 백엔드로 덮여 통과했다"
    assert v.failure == "malformed" and "backend=bad" in v.warnings


def test_chain_all_unavailable_is_blocked():
    v = _chain(_backend("a", None), _backend("b", None))
    assert not v.approved and v.failure == "no_backend"


def test_chain_empty_backend_list_is_blocked():
    v = _chain()
    assert not v.approved and v.failure == "no_backend"


def test_chain_approve_passes_through():
    v = _chain(_backend("a", f"No issues.\n{APPROVE}"))
    assert v.approved and v.failure is None


def test_cooldown_is_process_wide_and_never_approves():
    """[중요] 쿨다운은 **통과 사유가 아니다** — 전부 쿨다운이면 차단이다.

    위 `_chain` 이 감춘 동작을 여기서 **드러내 놓고** 검사한다. 순서 의존을 지우는 것과
    그 동작이 없는 척하는 것은 다르다.
    """
    clear_cooldown()
    dead = _backend("only", None)
    assert verify_files(_FILES, backends=[dead]).failure == "no_backend"
    assert "only" in cooldown_state(), "죽은 백엔드가 쿨다운에 들어가지 않았다"
    # 두 번째 호출은 백엔드를 **부르지도 않는다** — 그래도 승인되지 않는다
    called = []

    def watch(prompt, timeout=0):
        called.append(1)
        return APPROVE

    v = verify_files(_FILES, backends=[("only", watch)])
    assert not v.approved and v.failure == "no_backend"
    assert not called, "쿨다운 중인데 백엔드를 불렀다"
    clear_cooldown()


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
