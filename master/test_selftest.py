"""클러스터 셀프테스트 드라이런 — 🔴 **게이트가 실제로 막는지**까지 잰다.

정상 경로가 통과하는 것만 재면 *항상 통과하는 게이트*와 구별이 안 된다. 그래서 음성 경로를
같이 태운다 — **매니페스트에서 NONCE 를 빼면 라운드트립 단정이 실패해야 한다.**

`.venv/bin/python master/test_selftest.py`
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import selftest as S      # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def _named(r, frag: str):
    return [c for c in r.checks if frag in c.name]


def test_happy_path():
    r = S.run_dry(tasks=3)
    check("정상 경로 통과", r.ok, f"fails={r.fails} error={r.error}")
    check("예외 없음", not r.error, r.error)
    rt = _named(r, "NONCE 라운드트립")
    check("라운드트립 단정이 존재한다", len(rt) == 1)
    check("라운드트립 통과", bool(rt) and rt[0].passed, rt[0].detail if rt else "")
    git = _named(r, "git 으로")
    check("🔴 매니페스트가 git 으로 도착했다는 단정이 있고 통과한다",
          bool(git) and git[0].passed)
    check("작업장 트리가 깨끗하다는 단정이 통과한다",
          bool(_named(r, "깨끗하다")) and _named(r, "깨끗하다")[0].passed)
    check("정리 단정이 통과한다",
          bool(_named(r, "정리 후")) and _named(r, "정리 후")[0].passed)


def test_gate_actually_blocks():
    """🔴 매니페스트에서 NONCE 를 빼면 라운드트립이 **실패해야** 한다."""
    orig = S.nonce_section
    S.nonce_section = lambda nonces: f"{S.NONCE_HEADING}\n(토큰 없음 — 음성 테스트)\n"
    try:
        r = S.run_dry(tasks=2)
    finally:
        S.nonce_section = orig
    rt = _named(r, "NONCE 라운드트립")
    check("음성 경로에서 라운드트립이 실패한다", bool(rt) and not rt[0].passed,
          "단정이 통과해 버렸다 — 게이트가 아무것도 막지 않는다")
    check("음성 경로 전체는 ok=False", not r.ok, f"fails={r.fails}")
    check("음성 경로도 예외 없이 끝난다", not r.error, r.error)
    check("git 도착 단정은 여전히 통과한다 (매니페스트 자체는 갔다)",
          bool(_named(r, "git 으로")) and _named(r, "git 으로")[0].passed)


def test_extract_nonce():
    txt = "## 셀프테스트 토큰\nNONCE_0=AAA_0\nNONCE_1=AAA_1\n"
    check("NONCE 를 뽑는다", S.extract_nonce(txt, 1) == "AAA_1", S.extract_nonce(txt, 1))
    check("없으면 빈 문자열", S.extract_nonce(txt, 9) == "")
    check("빈 입력도 빈 문자열", S.extract_nonce("", 0) == "")
    check("접두 혼동 방지 (NONCE_1 이 NONCE_10 을 잡지 않는다)",
          S.extract_nonce("NONCE_10=X\n", 1) == "", S.extract_nonce("NONCE_10=X\n", 1))


def test_probe_and_impl_source():
    for i in (0, 3):
        ps = S.probe_source(i)
        check(f"probe[{i}] 에 [SELFTEST] 배너가 있다", "[SELFTEST]" in ps)
        check(f"probe[{i}] 에 [PSEUDO] 가 있다", "[PSEUDO]" in ps)
        check(f"probe[{i}] 가 '실제로 편집' 을 지시한다", "실제로 편집" in ps)
        # 🔴 재는 것은 **실제 NONCE 값**의 부재다. 원전 probe 본문에는 `CSTNONCE...` 가
        # **형식 예시**로 들어 있고 그건 누출이 아니다 — 완전한 값이 다르므로 라운드트립
        # 단정이 여전히 진짜와 환각을 가른다.
        real = f"CSTNONCE20260814_12345_{i}"
        check(f"probe[{i}] 본문에 실제 NONCE 값이 없다", real not in ps)
        check(f"probe[{i}] 는 형식 예시만 갖는다 (원전 규약)", "CSTNONCE" in ps)
        im = S.impl_source(i, "CSTNONCE_X")
        check(f"impl[{i}] 에서 [PSEUDO] 가 제거됐다", "[PSEUDO]" not in im)
        check(f"impl[{i}] 이 NONCE 를 반환한다", 'return "CSTNONCE_X"' in im)


def test_keep_preserves():
    r = S.run_dry(tasks=1, keep=True)
    check("keep 이면 경로를 알려 준다", bool(r.kept_at), r.kept_at)
    check("keep 이면 실제로 남아 있다", bool(r.kept_at) and Path(r.kept_at).exists())
    if r.kept_at and Path(r.kept_at).exists():
        import shutil
        shutil.rmtree(r.kept_at, ignore_errors=True)


def main() -> int:
    for fn in (test_extract_nonce, test_probe_and_impl_source, test_happy_path,
               test_gate_actually_blocks, test_keep_preserves):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_selftest: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
