"""stale 판정의 「판정 불가」 축 (`#275`) — **「모른다」와 「최신이다」를 가른다**.

## 왜 이 파일이 있나

실측 2026-08-23: 컨텍스트 문서 1,055건 중 **1,010건(95%)에 `source_commit` 이 없다**. 그리고
`stored` 와 `latest` 가 **둘 다 없으면 `s == l`** 이라 판정이 **조용히 통과**했다 — 도메인 멤버
112건 중 **92건(82%)** 이 그 상태였고, 판정이 실제로 보고 있던 것은 20건뿐이었다.

[중요] 이 세션이 여섯 번 가르친 병(*"판정을 했는데 안 보이면 「안 한 것」과 구분되지 않는다"*)의
**한 단계 더 나쁜 형태**다: 판정이 **거짓으로 통과**한다.

[주의] **일괄 스탬프는 증거로 배제됐다** — 이관 문서 mtime 이 한 시점이 아니다(2026-05-22
641건 · 04-06 74건 · 04-08 44건 …, 넉 달에 걸쳐 쌓였다). 한 커밋으로 찍으면 그 문서가 보지도
않은 트리를 반영했다고 주장하는 **거짓 정확성**이다. `#275` 본문이 *"가장 싸다"* 던 길은 닫혔다.

`.venv/bin/python master/test_stale_unknown.py`
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.ontology import stale as S                              # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def test_both_missing_is_not_fresh() -> None:
    """[중요] **양쪽 부재는 「최신」이 아니다** — 이것이 구멍이었다."""
    d = S.DomainStale(domain="X", total=3)
    d.unknown, d.unknown_members = 2, [("A", "-1", "-1"), ("B", "-1", "-1")]
    check("판정 불가를 센다", d.unknown == 2)
    check("[중요] 판정 불가는 stale 이 아니다 (재합성을 부르지 않는다)", not d.stale)
    check("그래도 undecidable 로 드러난다", d.undecidable)
    check("[중요] reason 에 나온다", "판정불가=2" in d.reason, d.reason)
    check("stale 수치도 그대로 보인다", "stale=0/3" in d.reason, d.reason)
    d2 = S.DomainStale(domain="Y", total=2, changed=1)
    check("판정 불가가 없으면 reason 이 조용하다", "판정불가" not in d2.reason, d2.reason)


def test_undecidable_never_triggers_resynthesis() -> None:
    """[중요] **M2 금기를 지킨다** — 판정 불가 92건이 재합성 대상이 되면 그것이
    「1,055건 일괄 재생성」이다(로컬 모델이 받아온 스냅샷보다 **나쁘게** 측정됐다).

    [주의] 소비자가 `r.stale` 로 거르는지 **소스로** 확인한다 — 여기가 계약이다.
    """
    src = (Path(__file__).resolve().parent / "ontology" / "synth.py").read_text(encoding="utf-8")
    check("[중요] synth 는 r.stale 로 거른다", "if r.stale]" in src, "판정 불가가 재합성된다")
    inv = (Path(__file__).resolve().parent / "ontology" / "invalidate.py").read_text(
        encoding="utf-8")
    check("[중요] invalidate 는 members(바뀐 것)만 지운다",
          "for name, _stored, _latest in r.members" in inv, "판정 불가 문서를 지운다")
    check("[주의] unknown_members 를 무효화에 쓰지 않는다", "unknown_members" not in inv)
    ssrc = (Path(__file__).resolve().parent / "ontology" / "stale.py").read_text(encoding="utf-8")
    check("stale 속성이 changed 만 본다", "return self.changed > 0" in ssrc)
    check("그 이유가 주석에 있다", "일괄 재생성" in ssrc)


def test_summary_does_not_lie() -> None:
    """[중요] *"재합성할 것이 없다"* 를 **판정 불가가 있을 때** 그대로 말하지 않는다."""
    check("아무것도 없으면 종전 문구", "재합성할 것이 없다" in S.summary([]))
    only_unknown = S.DomainStale(domain="X", total=67)
    only_unknown.unknown = 67
    out = S.summary([only_unknown])
    check("[중요] 「알 수 없다」를 말한다", "알 수 없다" in out, out)
    check("건수를 낸다", "67건" in out, out)
    check("[중요] 「최신이다」로 읽히지 않는다", "재합성할 것이 없다" not in out, out)
    check("고쳐지는 경로를 알려준다", "재합성되면" in out or "재합성될" in out, out)
    mixed = S.DomainStale(domain="Y", total=9, changed=5)
    mixed.unknown = 3
    out2 = S.summary([mixed, only_unknown])
    check("섞였으면 [주의] 로 덧붙인다", "판정 불가 70건" in out2, out2)
    normal = S.DomainStale(domain="Z", total=2, changed=1)
    check("판정 불가가 없으면 덧붙이지 않는다", "판정 불가" not in S.summary([normal]))


def test_compute_surfaces_unknown_only_domains() -> None:
    """[중요] **판정 불가만 있는 도메인도 결과에 나온다** — 안 나오면 그것이 침묵이다."""
    src = (Path(__file__).resolve().parent / "ontology" / "stale.py").read_text(encoding="utf-8")
    body = src[src.index("def compute("):]
    check("append 조건이 undecidable 을 포함한다",
          "if st.stale or st.undecidable:" in body, "판정 불가만 있는 도메인이 사라진다")
    check("양쪽 부재를 먼저 가른다",
          body.index("s == MISSING and l == MISSING") < body.index("elif s != l"), body[:80])
    check("[주의] 한쪽만 부재는 changed 로 남긴다 (재합성이 스탬프를 박는다 — 자기 치유)",
          "자기 치유" in src)


def test_synth_error_mentions_unknown() -> None:
    """[중요] 「최신이라서 없다」와 「알 수 없어서 없다」를 가른다."""
    src = (Path(__file__).resolve().parent / "ontology" / "synth.py").read_text(encoding="utf-8")
    i = src.index("stale 한 도메인이 없다")
    body = src[i - 400:i + 700]
    check("판정 불가 수를 센다", "sum(r.unknown for r in results)" in body, body[:80])
    check("[중요] 그 사실을 메시지에 싣는다", "판정 불가" in body)
    check("거짓 안심을 주지 않는다", "「알 수 없음」" in body)


def test_missing_doc_is_not_undecidable() -> None:
    """[주의] **문서가 아예 없는 것은 판정 불가가 아니다** — 합성이 필요한 것이다.

    실측 2026-08-23: 지금 그런 멤버는 **0건**이라 라이브로는 드러나지 않는다. 그래서 계약을
    유닛으로 못박는다 — 나중에 생겼을 때 조용히 판정 불가로 접히면 합성이 안 돈다.
    """
    tmp = Path(tempfile.mkdtemp())
    (tmp / "context").mkdir()
    import types
    paths = types.SimpleNamespace(context=tmp / "context", ontology=tmp / "ontology")
    check("문서가 없으면 MISSING", S.latest_commit(paths, "Source/A/B.cpp") == S.MISSING)
    doc = tmp / "context" / "Source" / "A"
    doc.mkdir(parents=True)
    (doc / "B.md").write_text("---\nsource_commit: abc123\n---\n본문\n", encoding="utf-8")
    check("스탬프가 있으면 그 값", S.latest_commit(paths, "Source/A/B.cpp") == "abc123")
    (doc / "C.md").write_text("---\ntitle: x\n---\n본문\n", encoding="utf-8")
    check("스탬프가 없으면 MISSING", S.latest_commit(paths, "Source/A/C.cpp") == S.MISSING)


if __name__ == "__main__":
    for fn in (test_both_missing_is_not_fresh, test_undecidable_never_triggers_resynthesis,
               test_summary_does_not_lie, test_compute_surfaces_unknown_only_domains,
               test_synth_error_mentions_unknown, test_missing_doc_is_not_undecidable):
        fn()
    print(f"{'OK' if not FAIL else 'FAIL'} test_stale_unknown: {PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
