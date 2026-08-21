"""콘솔 UTF-8 강제(`#181`) 계약 테스트.

[중요] **이 칸을 한 번 「해당 없음」으로 미뤘고 그 판단이 틀렸다.** 근거였던 것은 *"마스터는
systemd 아래 stdout=utf-8"* 인데, **이 클러스터는 설계상 OS 2종**이다 — `.2`(janus)와
`.33`(user)이 둘 다 윈도우이고, [중요] 저장소는 *"`.2` 의 콘솔은 CP949"* 를 **이미 적어 두고
있었다**(CLAUDE.md). 마스터만 재고 「해당 없음」이라고 쓴 것이 오류다.

그래서 이 테스트는 **동작**만이 아니라 **적용 범위**를 잰다:

    ① no-op   이미 UTF-8 이면 아무것도 안 바꾼다 (리눅스)
    ② 교정    CP949 면 바꾼다 (윈도우)
    ③ 안전    못 바꿔도 죽지 않는다 · [중요] `errors=replace` 를 쓰지 않는다
    ④ 범위    윈도우로 **배달되는 페이로드**에 이 모듈이 들어간다

실행: python3 master/test_utf8.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import utf8 as U          # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


class Stream:
    def __init__(self, encoding, *, fails=False, no_reconfigure=False):
        self.encoding = encoding
        self.calls = []
        self._fails = fails
        if no_reconfigure:
            del self.__class__.reconfigure           # noqa: B020 — 인스턴스별 제거는 불가

    def reconfigure(self, encoding=None, errors=None):
        self.calls.append({"encoding": encoding, "errors": errors})
        if self._fails:
            raise OSError("바꿀 수 없다")
        self.encoding = encoding


class Bare:
    """`reconfigure` 가 없는 스트림 (감싼 스트림·구버전)."""
    def __init__(self, encoding):
        self.encoding = encoding


def with_streams(out, err, fn):
    so, se = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        return fn()
    finally:
        sys.stdout, sys.stderr = so, se


# ── ① no-op ──────────────────────────────────────────────────

def test_utf8_is_left_alone():
    o, e = Stream("utf-8"), Stream("UTF-8")
    changed = with_streams(o, e, U.enforce)
    check("[중요] 이미 UTF-8 이면 아무것도 안 바꾼다 (리눅스에서 no-op)", changed == [], str(changed))
    check("reconfigure 를 부르지도 않는다", not o.calls and not e.calls)
    check("대소문자·언더바 표기를 같은 것으로 본다",
          not U._needs(Bare("UTF_8")) and not U._needs(Bare("utf8")))


# ── ② 교정 ───────────────────────────────────────────────────

def test_cp949_is_fixed():
    """[중요] `.2`·`.33` 이 여기 해당한다 — 한글 윈도우 콘솔."""
    o, e = Stream("cp949"), Stream("cp949")
    changed = with_streams(o, e, U.enforce)
    check("둘 다 바꾼다", changed == ["stdout", "stderr"], str(changed))
    check("UTF-8 로 바꾼다", o.encoding == "utf-8" and e.encoding == "utf-8")
    check("[중요] `errors` 를 주지 않는다 (치환은 깨진 글자를 성공처럼 보이게 한다)",
          all(c["errors"] is None for c in o.calls), str(o.calls))
    one = with_streams(Stream("cp949"), Stream("utf-8"), U.enforce)
    check("필요한 쪽만 바꾼다", one == ["stdout"], str(one))


# ── ③ 안전 ───────────────────────────────────────────────────

def test_failures_do_not_raise():
    o, e = Stream("cp949", fails=True), Stream("cp949")
    changed = with_streams(o, e, U.enforce)
    check("[중요] 못 바꿔도 예외가 아니다 (인코딩 고치다 프로그램을 죽이면 본말전도)",
          changed == ["stderr"], str(changed))
    check("못 바꾼 것은 목록에 없다 — 호출자가 셀 수 있다", "stdout" not in changed)
    bare = with_streams(Bare("cp949"), Bare("cp949"), U.enforce)
    check("reconfigure 가 없으면 건드리지 않는다", bare == [], str(bare))
    check("인코딩을 모르면 건드리지 않는다 (판정 불가는 보수적으로)",
          not U._needs(Bare("")) and not U._needs(Bare(None)))
    gone = with_streams(None, None, U.enforce)
    check("스트림이 없어도 죽지 않는다", gone == [], str(gone))


# ── ④ 범위 — [중요] 윈도우로 실제로 간다 ─────────────────────────

def test_it_reaches_the_windows_machines():
    """[중요] 오류의 본질은 「우리는 리눅스」였다 — 이 클러스터는 **OS 2종**이다."""
    from master.client import bundle
    pay = bundle.payloads_for("requester")
    check("[중요] 요청자(.33 · 한글 윈도우) 페이로드에 들어간다", "utf8.py" in pay, str(pay))
    check("배달할 원문이 실재한다", len(bundle.payload_text("master/utf8.py")) > 200)
    src = Path(U.__file__).read_text(encoding="utf-8")
    check("왜 한 번 틀렸는지를 모듈이 적어 둔다", "카고 컬트는 다르다" in src or "규칙을 거꾸로" in src)
    check("[중요] 임포트 부작용이 아니다 (진입점에서 부른다)",
          "enforce()" not in src.split('"""')[-1].replace("def enforce", ""), "임포트 시 실행된다")


def test_entry_points_call_it():
    for mod in ("master/client/__main__.py", "master/ontology/__main__.py"):
        t = Path(mod).read_text(encoding="utf-8")
        check(f"{mod} 이 진입점에서 부른다", "_utf8_enforce()" in t, mod)


def main() -> int:
    for fn in (test_utf8_is_left_alone, test_cp949_is_fixed, test_failures_do_not_raise,
               test_it_reaches_the_windows_machines, test_entry_points_call_it):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_utf8: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
