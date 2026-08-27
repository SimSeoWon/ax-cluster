"""`#321` — 파견 여부를 `role` 에서 뗀 **가용성 축** (`dispatch`).

## [중요] 왜 축을 갈랐나

`role` 하나가 **세 가지**를 겸했다:

    파견 여부      config.Workshop.drivable
    배달 내용물    client/bundle.PAYLOAD_BY_ROLE
    토큰 스코프    auth.WORKER_SCOPE

그래서 `.33` 을 파견 대상으로 만들려고 `requester → worker` 로 바꾸면 **검수·머지에 필요한
`review`·`coordinator` 를 잃고 쓰기가 403 이 된다.** 축 분리 말고는 답이 없었다.

## [중요] 이 필드는 **좁히기 전용**이다

사용자 보완 2026-08-27: *"플래그는 분리하고, 해당 값이 있더라도 롤을 체크해서 작업 요청하는
메인 작업 PC면 무시하면 되겠네"*. **워커를 뺄 수는 있어도 요청자를 켤 수는 없다** — 사람이
편집 중인 트리에서 파이프라인이 브랜치를 다루는 것 자체가 위험이라는 판단이다.

    drivable = (driven == ssh) and (role == worker) and dispatch_resolved
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.client import bundle                                          # noqa: E402
from master.projects.config import (                                      # noqa: E402
    ConfigError, DISPATCH_ALWAYS, DISPATCH_NEVER, Workshop,
)
from master.work import runner as RN                                      # noqa: E402

_fail = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global _fail
    if ok:
        print(f"  [완료] {label}")
    else:
        _fail += 1
        print(f"  [실패] {label}" + (f" — {detail}" if detail else ""))


def _w(**kw) -> Workshop:
    base = dict(host="h", driven="ssh", path="/p", user="u", role="worker")
    base.update(kw)
    return Workshop(**base)


def test_unset_derives_from_role() -> None:
    print("\n[1] 미지정은 role 에서 유도한다 — 기존 레지스트리 무변경 동작 (완료 조건 1)")
    check("worker + 미지정 → 파견 대상", _w().drivable)
    check("requester + 미지정 → 아니다", not _w(role="requester").drivable)
    check("interactive 는 애초에 못 민다", not _w(driven="interactive").drivable)
    check("  유도값이 role 을 그대로 따른다",
          _w().dispatch_resolved and not _w(role="requester").dispatch_resolved)


def test_explicit_narrows_only() -> None:
    print("\n[2] [중요] 명시는 **좁히기만** 한다 (완료 조건 2)")
    check("worker + never → 뺀다", not _w(dispatch=DISPATCH_NEVER).drivable)
    check("worker + always → 그대로 대상", _w(dispatch=DISPATCH_ALWAYS).drivable)
    # [중요] 요청자를 켜는 용도가 아니다 — 스키마 단계에서 막는다
    try:
        _w(role="requester", dispatch=DISPATCH_ALWAYS).validate()
        check("[중요] requester 에 always 는 거부한다", False, "통과해 버렸다")
    except ConfigError as e:
        check("[중요] requester 에 always 는 거부한다", "좁히기 전용" in str(e), str(e)[:80])
    # never 는 요청자에도 쓸 수 있다 (이미 대상이 아니므로 무해하고, 의도를 적을 수 있다)
    r = _w(role="requester", dispatch=DISPATCH_NEVER)
    r.validate()
    check("requester + never 는 받는다 (의도를 적을 수 있다)", not r.drivable)


def test_validate_rejects_unknown() -> None:
    print("\n[3] 모르는 값을 조용히 넘기지 않는다")
    try:
        _w(dispatch="maybe").validate()
        check("모르는 값 거부", False, "통과해 버렸다")
    except ConfigError as e:
        check("모르는 값 거부", "dispatch 는" in str(e), str(e)[:80])


def test_roundtrip() -> None:
    print("\n[4] YAML 왕복 — 빈 값을 쓰지 않는다")
    check("미지정은 파일에 안 쓴다 (미설정과 설정-빈값이 구분된다)",
          "dispatch" not in _w().to_dict(), str(_w().to_dict()))
    check("명시는 쓴다", _w(dispatch=DISPATCH_NEVER).to_dict().get("dispatch") == DISPATCH_NEVER)
    back = Workshop.from_dict("h", _w(dispatch=DISPATCH_NEVER).to_dict())
    check("되읽어도 같다", back.dispatch == DISPATCH_NEVER and not back.drivable)
    check("옛 레코드(필드 없음)도 읽힌다",
          Workshop.from_dict("h", {"driven": "ssh", "path": "/p", "user": "u"}).drivable)


def test_pick_worker_honours_it() -> None:
    """[중요] 완료 조건 6 — 필드가 **실제로 파견을 막나.** 조회 표면만 바뀌면 거짓말이 된다."""
    print("\n[5] [중요] 파견 루프가 그 축을 본다 (완료 조건 6)")

    def facts(**kw):
        f = bundle.HostFacts(host=kw.get("host", "h"), user="u", path="/p", driven="ssh",
                             role=kw.get("role", "worker"), dispatch=kw.get("dispatch", ""))
        f.checkout_ok, f.claude = True, "2.1"
        return f

    ok = RN.pick_worker([facts()])
    check("미지정 워커는 골라진다", ok.chosen is not None, str(ok.rejected))

    off = RN.pick_worker([facts(dispatch="never")])
    check("[중요] never 면 안 골라진다", off.chosen is None, str(off.rejected))
    check("  사유에 축을 밝힌다", any("#321" in r for _h, r in off.rejected), str(off.rejected))

    req = RN.pick_worker([facts(role="requester", dispatch="always")])
    check("[중요] requester 는 always 여도 안 골라진다 (좁히기 전용)",
          req.chosen is None, str(req.rejected))
    check("  거절 사유는 **역할**이다 (dispatch 가 아니라)",
          any("역할이" in r for _h, r in req.rejected), str(req.rejected))

    two = RN.pick_worker([facts(host="a", dispatch="never"), facts(host="b")])
    check("빼도 남은 워커는 골라진다", getattr(two.chosen, "host", "") == "b", str(two.rejected))


def test_one_rule_not_two() -> None:
    """[중요] 레지스트리와 파견 루프가 **같은 규칙**이어야 한다 — 두 벌이면 필드가 거짓말한다."""
    print("\n[6] [중요] 규칙이 한 벌인가 (config ↔ bundle)")
    for role in ("worker", "requester"):
        for dp in ("", "always", "never"):
            if dp == "always" and role != "worker":
                continue                       # 스키마가 막는 조합 — validate 가 이미 잰다
            shop = _w(role=role, dispatch=dp)
            f = bundle.HostFacts(host="h", user="u", path="/p", driven="ssh",
                                 role=role, dispatch=dp)
            check(f"  role={role} dispatch={dp!r} 판정 일치",
                  shop.drivable == f.dispatchable, f"{shop.drivable} vs {f.dispatchable}")


def main() -> int:
    for fn in (test_unset_derives_from_role, test_explicit_narrows_only,
               test_validate_rejects_unknown, test_roundtrip,
               test_pick_worker_honours_it, test_one_rule_not_two):
        fn()
    total = 25
    print(f"\n{'OK' if not _fail else '[실패]'} test_dispatch_axis: {total - _fail}/{total} 통과")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
