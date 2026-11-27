"""지도 다이어그램(`#982` T3) 계약 테스트 — [중요] **같은 지도면 같은 바이트이고, 그 글이 지도 영역에 왕복되는가.**

실행: .venv/bin/python master/test_map_diagram.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import map_block as MB               # noqa: E402
from master import map_diagram as MD             # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _raises(fn, needle: str = "") -> bool:
    try:
        fn()
    except MD.DiagramError as e:
        return needle in str(e)
    return False


def _n(nid: int, state: str = "대기", deps: list[int] | None = None, title: str = "노드",
       typ: str = "작업", parent: int | None = None) -> MB.MapNode:
    return MB.MapNode(nid, title, typ, parent, state, list(deps or []))


def _block(nodes: list[MB.MapNode]) -> MB.MapBlock:
    return MB.MapBlock("HUD 를 붙인다", "", nodes, [], [])


def _sample() -> MB.MapBlock:
    return _block([
        _n(1001, "완료", [], "사전조사", "프리필"),
        _n(1002, "작업중", [1001], "HUD 위젯", "작업", 1001),
        _n(1003, "Frontier", [1001], "체력바", "작업", 1001),
        _n(1004, "차단", [1002, 1003], "통합 검사", "검증", 1001),
    ])


def _boxes(text: str) -> list[list[str]]:
    """상자별 줄(테두리 포함)."""
    out: list[list[str]] = []
    cur: list[str] | None = None
    for ln in text.split("\n"):
        if ln.startswith("+"):
            if cur is None:
                cur = [ln]
            else:
                cur.append(ln)
                out.append(cur)
                cur = None
        elif cur is not None:
            cur.append(ln)
    return out


def test_levels():
    check("다이아몬드 단계", MD.levels(_sample()) == [[1001], [1002, 1003], [1004]], str(MD.levels(_sample())))
    chains = _block([_n(5, deps=[3]), _n(3), _n(9, deps=[7]), _n(7), _n(8, deps=[9])])
    check("독립 사슬 · id 순", MD.levels(chains) == [[3, 7], [5, 9], [8]], str(MD.levels(chains)))
    deep = _block([_n(1), _n(2, deps=[1]), _n(3, deps=[2]), _n(4, deps=[1, 3])])
    check("단계 = 1 + 선행 최대", MD.levels(deep) == [[1], [2], [3], [4]], str(MD.levels(deep)))
    rev = _block(list(reversed(_sample().nodes)))
    check("입력 순서 무관", MD.levels(rev) == MD.levels(_sample()))
    check("빈 표", MD.levels(_block([])) == [])


def test_head_state():
    check("작업중이 가장 앞", MD.head_state(["완료", "대기", "작업중", "Frontier"]) == "작업중")
    check("재검증 > Frontier", MD.head_state(["Frontier", "재검증"]) == "재검증")
    check("Frontier > 차단", MD.head_state(["차단", "Frontier"]) == "Frontier")
    check("차단 > 대기", MD.head_state(["대기", "차단"]) == "차단")
    check("대기 > 완료", MD.head_state(["완료", "대기"]) == "대기")
    check("전부 완료면 완료", MD.head_state(["완료", "완료"]) == "완료")
    text = MD.render(_sample())
    check("머리줄 1단계", "| [완료] 1단계" in text, text)
    check("머리줄 2단계 작업중", "| [작업중] 2단계" in text, text)
    check("머리줄 3단계 차단", "| [차단] 3단계" in text, text)


def test_lines():
    text = MD.render(_sample())
    check("<pre> 로 감싼다", text.startswith("<pre>\n") and text.endswith("\n</pre>"), text)
    check("LF 만", "\r" not in text)
    check("선행 없는 줄엔 화살표 없음", "|  #1001 사전조사 (프리필) [완료] |" in text, text)
    check("선행 하나", "  #1002 HUD 위젯 (작업) [작업중] ← #1001" in text, text)
    check("선행 둘은 · 로", "  #1004 통합 검사 (검증) [차단] ← #1002·#1003" in text, text)
    check("상자 셋", len(_boxes(text)) == 3, text)
    check("연결선 둘", text.count("\n" + " " * (MD.width(_boxes(text)[0][0]) // 2) + "v\n") == 1
          and sum(1 for ln in text.split("\n") if ln.strip() == "v") == 2, text)
    check("ASCII 테두리만", all(set(b[0]) <= {"+", "-"} for b in _boxes(text)))
    long = "아주 " * 30 + "긴 제목"
    t2 = MD.render(_block([_n(1, title=long)]))
    check("긴 제목 안 자름", long in t2)


def test_width():
    check("한글 2칸", MD.width("한글") == 4 and MD.width("ab") == 2 and MD.width("←") == 1)
    check("전각 2칸", MD.width("ＡＢ") == 4)
    for name, blk in (("예시", _sample()),
                      ("섞인 글자", _block([_n(1, title="HUD"), _n(2, title="아주아주긴한글제목입니다",
                                                                deps=[1]), _n(3, title="ＦＵＬＬ", deps=[1])]))):
        for k, box in enumerate(_boxes(MD.render(blk)), start=1):
            ws = {MD.width(ln) for ln in box}
            check(f"{name} 상자{k} 줄 폭 같음", len(ws) == 1, "\n".join(box))
            check(f"{name} 상자{k} 오른쪽 |", all(ln.endswith("|") for ln in box[1:-1]))
    boxes = _boxes(MD.render(_sample()))
    lines = MD.render(_sample()).split("\n")
    i = len(boxes[0])                     # lines[0] 은 <pre>, 첫 상자 아래 테두리 = lines[len(box)]
    col = MD.width(boxes[0][0]) // 2
    check("연결선이 위 상자 가운데", lines[i + 1] == " " * col + "|" and lines[i + 2] == " " * col + "v",
          "\n".join(lines[i:i + 3]))


def test_errors():
    cyc = _block([_n(1, deps=[3]), _n(2, deps=[1]), _n(3, deps=[2]), _n(4)])
    check("순환 거절", _raises(lambda: MD.render(cyc), "순환"))
    check("순환 id 를 이름", _raises(lambda: MD.levels(cyc), "#1") and _raises(lambda: MD.levels(cyc), "#3"))
    unk = _block([_n(1), _n(2, deps=[1, 77])])
    check("표 밖 선행 거절", _raises(lambda: MD.render(unk), "#77"))
    check("표 밖 선행 노드 이름", _raises(lambda: MD.levels(unk), "#2"))
    check("id 중복 거절", _raises(lambda: MD.levels(_block([_n(1), _n(1)])), "#1"))
    check("DiagramError 는 ValueError", issubclass(MD.DiagramError, ValueError))


def test_empty_and_determinism():
    check("빈 표", MD.render(_block([])) == "<pre>\n(노드 없음)\n</pre>")
    a = MD.render(_sample())
    b = MD.render(_block(list(reversed(_sample().nodes))))
    check("같은 지도 같은 바이트", a == MD.render(_sample()) and a.encode() == b.encode())
    shuffled = _sample()
    shuffled.nodes[3].deps = [1003, 1002]
    check("선행 순서 무관", MD.render(shuffled) == a)


def test_map_block_roundtrip():
    for name, blk in (("예시", _sample()), ("빈 표", _block([]))):
        blk.diagram = MD.render(blk)
        try:
            text = MB.render(blk)
        except MB.MapError as e:
            check(f"{name}: map_block.render 통과", False, str(e))
            continue
        check(f"{name}: map_block.render 통과", True)
        back = MB.parse(text)
        check(f"{name}: parse 왕복", back == blk)
        check(f"{name}: 다이어그램 글자 그대로", back.diagram == blk.diagram)
        check(f"{name}: 다시 그려도 같다", MD.render(back) == blk.diagram)


def test_planned_keys_1036():
    """`#1036` — 예정 키 P<n> 이 번호 노드와 섞여도 단계·줄을 그린다(번호 먼저 정렬)."""
    nodes = [MB.MapNode(1032, "현황 실측", "프리필", None, "완료"),
             MB.MapNode("P2", "일감 발주", "작업", "P1", "차단", ["P1"]),
             MB.MapNode("P1", "워커 일감 읽기", "작업", 1032, "Frontier", [1032])]
    blk = MB.MapBlock("목적지", "", nodes, [], [])
    check("#1036 단계", MD.levels(blk) == [[1032], ["P1"], ["P2"]], str(MD.levels(blk)))
    out = MD.render(blk)
    check("#1036 줄 표기", "  P1 워커 일감 읽기 (작업) [Frontier] ← #1032" in out
          and "  P2 일감 발주 (작업) [차단] ← P1" in out, out)
    check("#1036 같은 지도면 같은 바이트", MD.render(blk) == out)
    cyc = [MB.MapNode("P1", "a", "작업", None, "차단", ["P2"]), MB.MapNode("P2", "b", "작업", None, "차단", ["P1"])]
    check("#1036 예정 키 순환 거절", _raises(lambda: MD.levels(MB.MapBlock("d", "", cyc, [], [])), "순환"))


def main() -> int:
    for fn in (test_levels, test_head_state, test_lines, test_width, test_errors,
               test_empty_and_determinism, test_map_block_roundtrip,
               test_planned_keys_1036):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_map_diagram: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
