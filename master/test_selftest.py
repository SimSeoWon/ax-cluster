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


# ─────────────────────────────────────────────────────────────
# 2단계 이식분 (`#141`) — 폴링 워커 수 · 병렬 판정 · 백엔드 레인
# ─────────────────────────────────────────────────────────────

def test_count_polling():
    """🔴 **존재가 아니라 신선도로 센다** — 원전 판정식을 그대로 옮기면 우리 큐에서 거짓말을 한다."""
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 8, 16, 20, 0, 0, tzinfo=timezone(timedelta(hours=9)))
    iso = lambda **kw: (now - timedelta(**kw)).isoformat()   # noqa: E731
    ws = [
        {"worker_id": "fresh", "last_seen": iso(seconds=30)},
        {"worker_id": "edge", "last_seen": iso(seconds=S.POLLING_FRESH_SEC - 1)},
        {"worker_id": "stale", "last_seen": iso(days=7)},
        {"worker_id": "never", "last_seen": None},
        {"worker_id": "broken", "last_seen": "어제쯤"},
    ]
    n, ages = S.count_polling(ws, now=now)
    check("신선한 워커만 센다 (2명)", n == 2, f"n={n}")
    check("경과 초를 같이 돌려준다", len(ages) == 5 and ages[0][1] is not None)
    check("파싱 못 한 stamp 는 폴링 아님", ages[4][1] is None)
    # 🔴 같은 입력에서 두 판정식이 갈린다 — 이 갈림이 이식의 근거다(리포트 16 §12.7 부류).
    origin_style = sum(1 for w in ws if w.get("last_seen"))
    check("🔴 원전식(존재)이면 4, 신선도면 2 — 같은 입력에서 판정이 갈린다",
          origin_style == 4 and n == 2, f"원전식={origin_style} 우리={n}")
    check("빈 목록은 0", S.count_polling([], now=now)[0] == 0)
    check("None 도 0", S.count_polling(None, now=now)[0] == 0)
    # 🔴 미래 stamp(시계 어긋남)를 "신선" 으로 세지 않는다 — 판정 불가는 단정하지 않는 쪽으로.
    future = [{"worker_id": "clock-skew", "last_seen": (now + timedelta(hours=1)).isoformat()}]
    check("미래 stamp 는 폴링으로 세지 않는다", S.count_polling(future, now=now)[0] == 0)


def test_overlapping_pair():
    """🔴 *"서로 다른 워커가 처리했다"* 는 병렬이 아니다 — 구간이 겹쳐야 병렬이다."""
    from datetime import datetime
    t = lambda h, m: datetime(2026, 8, 16, h, m)      # noqa: E731
    overlap = [("w1", t(10, 0), t(10, 30), 0), ("w2", t(10, 15), t(10, 45), 1)]
    serial = [("w1", t(10, 0), t(10, 10), 0), ("w2", t(10, 20), t(10, 30), 1)]
    same = [("w1", t(10, 0), t(10, 30), 0), ("w1", t(10, 15), t(10, 45), 1)]
    p = S.overlapping_pair(overlap)
    check("겹치면 쌍을 돌려준다", p is not None and p[0] == 0 and p[2] == 1, str(p))
    check("직렬이면 None", S.overlapping_pair(serial) is None)
    check("🔴 같은 워커의 겹침은 병렬이 아니다", S.overlapping_pair(same) is None)
    check("빈 입력은 None", S.overlapping_pair([]) is None and S.overlapping_pair(None) is None)
    check("한 건은 None", S.overlapping_pair(overlap[:1]) is None)


def test_build_specs():
    specs = S.build_specs(["local", "claude"], 2, "TS", "NB")
    check("backends × per (2×2=4)", len(specs) == 4, str(len(specs)))
    check("🔴 gidx 가 전역 유일", sorted(s["gidx"] for s in specs) == [0, 1, 2, 3])
    check("레인이 고르게 나뉜다",
          [s["backend"] for s in specs] == ["local", "local", "claude", "claude"])
    check("NONCE 가 전부 다르다", len({s["nonce"] for s in specs}) == 4)
    check("probe 경로가 전부 다르다", len({s["probe_rel"] for s in specs}) == 4)
    d = S.build_specs(None, 3, "TS", "NB")
    check("기본은 1레인이고 per 가 곧 총 개수", len(d) == 3 and
          all(s["backend"] == S.DEFAULT_LANE for s in d))
    check("빈 문자열 레인은 걸러진다", len(S.build_specs(["", "  "], 1, "TS", "NB")) == 1)
    check("per 는 최소 1", len(S.build_specs(None, 0, "TS", "NB")) == 1)


def test_call_work_fn():
    """🔴 인자 수를 **세서** 부른다 — `TypeError` 를 삼키면 콜러 내부 결함이 숨는다."""
    seen = {}

    def four(gidx, probe_rel, nonce_key, work_id):
        seen["four"] = (gidx, work_id)
        return "CMD4"

    def five(gidx, probe_rel, nonce_key, work_id, backend):
        seen["five"] = backend
        return "CMD5"

    def varargs(*a):
        seen["var"] = len(a)
        return "CMDV"

    check("옛 4인자 콜러가 그대로 돈다",
          S._call_work_fn(four, 1, "p.py", "NONCE_1", "w", "local") == "CMD4")
    check("5인자 콜러는 backend 를 받는다",
          S._call_work_fn(five, 1, "p.py", "NONCE_1", "w", "local") == "CMD5"
          and seen.get("five") == "local")
    check("*args 콜러는 5개를 받는다",
          S._call_work_fn(varargs, 1, "p.py", "NONCE_1", "w", "local") == "CMDV"
          and seen.get("var") == 5)

    def boom(gidx, probe_rel, nonce_key, work_id, backend):
        raise TypeError("콜러 안에서 난 오류")

    try:
        S._call_work_fn(boom, 1, "p.py", "NONCE_1", "w", "local")
        check("🔴 콜러 내부 TypeError 는 삼켜지지 않는다", False, "예외가 안 났다")
    except TypeError as e:
        check("🔴 콜러 내부 TypeError 는 삼켜지지 않는다", "콜러 안에서" in str(e), str(e))


def main() -> int:
    for fn in (test_extract_nonce, test_probe_and_impl_source, test_happy_path,
               test_gate_actually_blocks, test_keep_preserves,
               test_count_polling, test_overlapping_pair, test_build_specs,
               test_call_work_fn):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_selftest: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
