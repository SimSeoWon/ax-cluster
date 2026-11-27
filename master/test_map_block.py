"""지도 영역(`#982` T2) 계약 테스트 — [중요] **형식이 어긋나면 거절하고, 영역 밖 본문은 바이트 그대로인가.**

실행: .venv/bin/python master/test_map_block.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import map_block as MB               # noqa: E402

PASS = FAIL = 0
ORIGINAL = "## 요청\n\n사용자가 쓴 원문 — `백틱` 과 표\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
HEADER = "| 노드 | 제목 | 타입 | 부모 | 상태 | 선행 | 담당 | 요약 |\n|---|---|---|---|---|---|---|---|"


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
    except MB.MapError as e:
        return needle in str(e)
    return False


def _sample() -> MB.MapBlock:
    return MB.MapBlock(
        destination="HUD 를 붙인다\n둘째 줄",
        diagram="<pre>\n  [Root]\n    └ #1001\n\n  # 들여쓴 줄\n</pre>",
        nodes=[
            MB.MapNode(1001, "사전조사", "프리필", None, "완료", [], "", "HUD 기능 필요"),
            MB.MapNode(1002, "HUD", "작업", 1001, "Frontier", [1001], "", ""),
            MB.MapNode(1003, "검증", "검증", 1002, "대기", [1001, 1002], "codex", "끝 검사"),
        ],
        fog=["아직 모르는 것"],
        out_of_scope=["멀티플레이 — 이번 목적 밖"],
    )


def _region(nodes: str = "", dest: str = "목적", diagram: str = "", fog: str = "", oos: str = "",
            begin: str = "<!-- ax:map:begin v=1 -->") -> str:
    return (f"{begin}\n## 목적지\n{dest}\n\n## 다이어그램\n{diagram}\n\n## 노드\n{HEADER}\n{nodes}\n\n"
            f"## 안개\n{fog}\n\n## 범위 밖\n{oos}\n<!-- ax:map:end -->")


def test_roundtrip():
    b = _sample()
    text = MB.render(b)
    check("render 는 태그로 감싼다", text.startswith("<!-- ax:map:begin v=1 -->") and text.endswith(MB.END_TAG))
    check("render 는 LF", "\r" not in text)
    check("왕복 parse(render(x)) == x", MB.parse(text) == b, text)
    check("node() 조회", MB.parse(text).node(1002).parent == 1001 and MB.parse(text).node(9) is None)
    check("Root 부모는 None", MB.parse(text).node(1001).parent is None)
    check("담당 없음은 — 로 쓴다", "| #1001 | 사전조사 | 프리필 | Root | 완료 | — | — | HUD 기능 필요 |" in text, text)
    check("선행은 · 로 잇는다", "| #1001·#1002 |" in text, text)
    check("빈 요약 칸", "| #1002 | HUD | 작업 | #1001 | Frontier | #1001 | — | |" in text, text)
    fresh = MB.MapBlock("목적", "", [], [], [])
    check("빈 지도 왕복", MB.parse(MB.render(fresh)) == fresh, MB.render(fresh))
    check("다이어그램 글자 그대로", MB.parse(text).diagram == b.diagram)


def test_examples_parse():
    body = ORIGINAL + "\n" + _region(
        nodes="| #1001 | 사전조사 | 프리필 | Root | 완료 | — | — | HUD 기능 필요 |\n"
              "| #1002 | HUD | 작업 | #1001 | Frontier | #1001 | — | |",
        diagram="<pre>\n...any text...\n</pre>", fog="- 안개 하나\n\n- 안개 둘", oos="")
    m = MB.parse(body)
    check("예시 파싱 노드 수", len(m.nodes) == 2)
    check("예시 요약 빈칸", m.node(1002).summary == "" and m.node(1002).owner == "")
    check("예시 안개 빈 줄 무시", m.fog == ["안개 하나", "안개 둘"], str(m.fog))
    check("빈 범위 밖", m.out_of_scope == [])
    check("빈 노드 표 유효", MB.parse(_region()).nodes == [])
    check("빈 안개·범위 밖 절", MB.parse(_region()).fog == [] and MB.parse(_region()).out_of_scope == [])
    check("영역 없음 → None", MB.parse(ORIGINAL) is None and MB.parse("") is None and MB.parse(None) is None)
    check("exists", MB.exists(body) and not MB.exists(ORIGINAL))
    crlf = body.replace("\n", "\r\n")
    check("CRLF 본문도 같은 값", MB.parse(crlf) == m)


def test_put():
    b = _sample()
    out = MB.put(ORIGINAL, b)
    check("put 붙이기 — 원문 앞부분 그대로", out.startswith(ORIGINAL.rstrip("\n") + "\n\n<!-- ax:map:begin"), out[:200])
    check("put 붙이기 — 끝 줄바꿈", out.endswith(MB.END_TAG + "\n"))
    check("put 붙인 것 파싱", MB.parse(out) == b)
    check("빈 본문에 put", MB.put("", b) == MB.render(b) + "\n")
    # 영역 교체 — 앞뒤 바이트 그대로
    prefix = "머리말 원문\r\n\r\n| x |\r\n"
    suffix = "\r\n\r\n## 꼬리\r\n끝  \r\n"
    crlf_body = prefix + MB.render(MB.MapBlock("옛 목적", "", [], [], [])).replace("\n", "\r\n") + suffix
    out2 = MB.put(crlf_body, b)
    check("CRLF 교체 — 앞 바이트 그대로", out2.startswith(prefix))
    check("CRLF 교체 — 뒤 바이트 그대로", out2.endswith(suffix))
    mid = out2[len(prefix):len(out2) - len(suffix)]
    check("CRLF 교체 — 영역 안도 CRLF", "\n" not in mid.replace("\r\n", ""), repr(mid[:120]))
    check("CRLF 교체 — 값", MB.parse(out2) == b)
    check("교체는 영역 하나", out2.count("ax:map:begin") == 1 and "옛 목적" not in out2)
    crlf_plain = ORIGINAL.replace("\n", "\r\n")
    out3 = MB.put(crlf_plain, b)
    check("CRLF 붙이기 — 원문 그대로", out3.startswith(crlf_plain.rstrip("\r\n") + "\r\n\r\n"))
    check("CRLF 붙이기 — LF 홀로 없음", "\n" not in out3.replace("\r\n", ""))
    out4 = MB.put(out, MB.MapBlock("새 목적", "", [], [], []))
    check("LF 교체 — 원문 그대로", out4.startswith(ORIGINAL.rstrip("\n")) and MB.parse(out4).destination == "새 목적")
    check("put 실패는 본문을 안 바꾼다(예외)",
          _raises(lambda: MB.put(ORIGINAL, MB.MapBlock("", "", [], [], [])), "목적지"))


def test_tag_rejections():
    r = _region()
    check("시작 태그만", _raises(lambda: MB.parse("<!-- ax:map:begin v=1 -->\n"), "한 쌍"))
    check("끝 태그만", _raises(lambda: MB.parse("x\n<!-- ax:map:end -->"), "한 쌍"))
    check("영역 둘", _raises(lambda: MB.parse(r + "\n" + r), "한 쌍"))
    check("끝이 앞", _raises(lambda: MB.parse("<!-- ax:map:end -->\n<!-- ax:map:begin v=1 -->"), "앞에"))
    check("버전 2 거절", _raises(lambda: MB.parse(_region(begin="<!-- ax:map:begin v=2 -->")), "v=2"))


def test_section_rejections():
    r = _region()
    check("절 누락", _raises(lambda: MB.parse(r.replace("## 안개\n\n\n", "")), "절 제목"))
    check("절 추가", _raises(lambda: MB.parse(r.replace("## 안개", "## 덤\n\n## 안개")), "절 제목"))
    swapped = r.replace("## 안개", "## TMP").replace("## 범위 밖", "## 안개").replace("## TMP", "## 범위 밖")
    check("절 순서 뒤바뀜", _raises(lambda: MB.parse(swapped), "절 제목"))
    check("첫 제목 앞 글", _raises(lambda: MB.parse(r.replace("v=1 -->\n", "v=1 -->\n떠돌이\n")), "앞 글"))
    check("빈 목적지", _raises(lambda: MB.parse(_region(dest="")), "목적지"))
    check("안개에 목록 아닌 줄", _raises(lambda: MB.parse(_region(fog="- 하나\n그냥 줄")), "목록"))
    check("범위 밖에 목록 아닌 줄", _raises(lambda: MB.parse(_region(oos="* 별표")), "목록"))
    check("빈 목록 항목", _raises(lambda: MB.parse(_region(fog="- ")), "빈 항목"))


def _row(nid="#1", title="t", typ="작업", parent="Root", state="대기", deps="—", owner="—", summary=""):
    return f"| {nid} | {title} | {typ} | {parent} | {state} | {deps} | {owner} | {summary} |"


def test_table_rejections():
    P = lambda rows: MB.parse(_region(nodes="\n".join(rows)))  # noqa: E731
    check("정상 행", P([_row()]).nodes[0].id == 1)
    check("머리줄 다름", _raises(lambda: MB.parse(_region().replace("| 요약 |", "| 메모 |")), "머리줄"))
    check("구분줄 없음", _raises(lambda: MB.parse(_region().replace("|---|---|---|---|---|---|---|---|", "")),
                              "머리줄과 구분줄"))
    check("칸 수 다름", _raises(lambda: P(["| #1 | t | 작업 | Root | 대기 | — | — |"]), "칸 수"))
    check("칸에 | 들어감(칸 수로 거절)", _raises(lambda: P([_row(summary="a | b")]), "칸 수"))
    check("노드 id 형식", _raises(lambda: P([_row(nid="1")]), "#<숫자>"))
    check("노드 id 문자", _raises(lambda: P([_row(nid="#a")]), "#<숫자>"))
    check("빈 제목", _raises(lambda: P([_row(title="")]), "제목"))
    check("모르는 타입", _raises(lambda: P([_row(typ="설계")]), "타입"))
    check("모르는 상태", _raises(lambda: P([_row(state="진행")]), "상태"))
    check("부모 형식", _raises(lambda: P([_row(parent="root")]), "부모"))
    check("자기 부모", _raises(lambda: P([_row(parent="#1")]), "자기 자신"))
    check("표 밖 부모", _raises(lambda: P([_row(parent="#9")]), "부모 #9"))
    check("부모 순환", _raises(lambda: P([_row(nid="#1", parent="#2"), _row(nid="#2", parent="#1")]), "순환"))
    check("선행 빈칸", _raises(lambda: P([_row(deps="")]), "선행"))
    check("선행 형식", _raises(lambda: P([_row(nid="#2"), _row(nid="#1", deps="2")]), "선행"))
    check("자기 선행", _raises(lambda: P([_row(deps="#1")]), "자기 자신"))
    check("선행 중복", _raises(lambda: P([_row(nid="#2"), _row(nid="#1", deps="#2·#2")]), "겹친다"))
    check("없는 선행", _raises(lambda: P([_row(deps="#7")]), "없는 선행"))
    check("노드 id 중복", _raises(lambda: P([_row(), _row()]), "겹친다"))
    check("담당 빈칸", _raises(lambda: P([_row(owner="")]), "담당"))
    check("표 줄 아님", _raises(lambda: P(["#1 t 작업"]), "표 줄"))
    ok = P([_row(nid="#2", owner="claude"), _row(nid="#1", parent="#2", deps="#2", summary="요약 글")])
    check("뒤에 나오는 부모·선행도 허용", ok.node(1).parent == 2 and ok.node(1).deps == [2] and ok.node(2).owner == "claude")


def test_render_rejections():
    def R(**kw):
        b = _sample()
        for k, v in kw.items():
            setattr(b, k, v)
        return lambda: MB.render(b)

    def node(**kw):
        n = MB.MapNode(1, "t", "작업", None, "대기", [], "", "")
        for k, v in kw.items():
            setattr(n, k, v)
        return n
    check("쓰기: 칸에 |", _raises(R(nodes=[node(summary="a|b")]), "'|'"))
    check("쓰기: 제목에 |", _raises(R(nodes=[node(title="a|b")]), "'|'"))
    check("쓰기: 담당에 |", _raises(R(nodes=[node(owner="a|b")]), "'|'"))
    check("쓰기: 칸에 줄바꿈", _raises(R(nodes=[node(summary="a\nb")]), "줄바꿈"))
    check("쓰기: 칸 앞뒤 공백", _raises(R(nodes=[node(summary=" a")]), "공백"))
    check("쓰기: 담당 — 모호", _raises(R(nodes=[node(owner="—")]), "담당"))
    check("쓰기: 빈 제목", _raises(R(nodes=[node(title=" ")]), "제목"))
    check("쓰기: 모르는 타입", _raises(R(nodes=[node(type="x")]), "타입"))
    check("쓰기: 모르는 상태", _raises(R(nodes=[node(state="x")]), "상태"))
    check("쓰기: 자기 부모", _raises(R(nodes=[node(parent=1)]), "자기 자신"))
    check("쓰기: 표 밖 부모", _raises(R(nodes=[node(parent=5)]), "부모 #5"))
    check("쓰기: 자기 선행", _raises(R(nodes=[node(deps=[1])]), "자기 자신"))
    check("쓰기: 선행 중복", _raises(R(nodes=[node(id=2), node(deps=[2, 2])]), "겹친다"))
    check("쓰기: 없는 선행", _raises(R(nodes=[node(deps=[3])]), "없는 선행"))
    check("쓰기: id 중복", _raises(R(nodes=[node(), node()]), "겹친다"))
    check("쓰기: 빈 목적지", _raises(R(destination="  "), "목적지"))
    check("쓰기: 목적지에 ## 줄", _raises(R(destination="a\n## 노드"), "절 제목"))
    check("쓰기: 다이어그램에 ## 줄", _raises(R(diagram="## 몰래"), "절 제목"))
    check("쓰기: 다이어그램에 표지", _raises(R(diagram=MB.END_TAG), "표지"))
    check("쓰기: 다이어그램 앞뒤 빈 줄", _raises(R(diagram="\nx\n"), "빈 줄"))
    check("쓰기: CR", _raises(R(destination="a\r\nb"), "CR"))
    check("쓰기: 빈 안개 항목", _raises(R(fog=[""]), "안개"))
    check("쓰기: 안개 줄바꿈", _raises(R(fog=["a\nb"]), "안개"))
    check("쓰기: 범위 밖 앞뒤 공백", _raises(R(out_of_scope=[" a"]), "범위 밖"))


def test_node_marker():
    mk = MB.NodeMarker(1000, "작업")
    check("표지 없음 → None", MB.parse_node(ORIGINAL) is None and MB.parse_node("") is None)
    out = MB.put_node(ORIGINAL, mk)
    check("표지 붙이기 — 원문 그대로", out.startswith(ORIGINAL.rstrip("\n") + "\n\n"))
    check("표지 붙이기 — 한 줄", out.endswith("<!-- ax:node v=1 root=1000 type=작업 -->\n"), repr(out[-60:]))
    check("표지 읽기", MB.parse_node(out) == mk)
    out2 = MB.put_node(out, MB.NodeMarker(2000, "검증"))
    check("표지 교체 — 하나뿐", out2.count("ax:node") == 1 and MB.parse_node(out2) == MB.NodeMarker(2000, "검증"))
    check("표지 교체 — 원문 그대로", out2.startswith(ORIGINAL.rstrip("\n")))
    mid = "위\r\n<!-- ax:node v=1 root=5 type=프리필 -->\r\n아래 원문 \r\n"
    out3 = MB.put_node(mid, MB.NodeMarker(6, "작업"))
    check("CRLF 중간 표지 교체 — 바이트", out3 == "위\r\n<!-- ax:node v=1 root=6 type=작업 -->\r\n아래 원문 \r\n", repr(out3))
    crlf = ORIGINAL.replace("\n", "\r\n")
    out4 = MB.put_node(crlf, mk)
    check("CRLF 붙이기", out4.startswith(crlf.rstrip("\r\n") + "\r\n\r\n") and "\n" not in out4.replace("\r\n", ""))
    check("빈 본문에 표지", MB.put_node("", mk) == "<!-- ax:node v=1 root=1000 type=작업 -->\n")
    two = out + "<!-- ax:node v=1 root=1 type=작업 -->\n"
    check("표지 둘 거절", _raises(lambda: MB.parse_node(two), "2개"))
    check("표지 둘이면 put 도 거절", _raises(lambda: MB.put_node(two, mk), "2개"))
    check("모르는 타입", _raises(lambda: MB.parse_node("<!-- ax:node v=1 root=1 type=설계 -->"), "타입"))
    check("root 숫자 아님", _raises(lambda: MB.parse_node("<!-- ax:node v=1 root=#1 type=작업 -->"), "root"))
    check("버전 2", _raises(lambda: MB.parse_node("<!-- ax:node v=2 root=1 type=작업 -->"), "v=2"))
    check("깨진 표지", _raises(lambda: MB.parse_node("<!-- ax:node root=1 -->"), "형식"))
    check("줄을 혼자 차지 안 함", _raises(lambda: MB.parse_node("앞 <!-- ax:node v=1 root=1 type=작업 -->"), "한 줄"))
    check("쓰기: 모르는 타입", _raises(lambda: MB.put_node("", MB.NodeMarker(1, "x")), "타입"))
    check("쓰기: root 음수", _raises(lambda: MB.put_node("", MB.NodeMarker(-1, "작업")), "root"))
    check("지도 글에 표지 금지", _raises(lambda: MB.render(MB.MapBlock("<!-- ax:node v=1 root=1 type=작업 -->",
                                                                    "", [], [], [])), "표지"))
    check("상수", MB.NO_DEPS == "—" and MB.ROOT == "Root" and MB.NODE_TYPES == ("프리필", "작업", "검증")
          and MB.STATES == ("대기", "Frontier", "작업중", "완료", "차단", "재검증"))


def test_quoted_marker_1027():
    """`#1027` 재현 — 인용(코드 스팬·펜스) 안의 표지 문자열은 표지가 아니다. 그 밖의 깨진 표지는 그대로 거절."""
    M = "<!-- ax:node v=1 root=741 type=작업 -->"
    mk = MB.NodeMarker(1000, "검증")
    tick = f"## 문제\n본문 `{M}` 표지가 붙는다.\n"
    check("#1027 백틱 인용만 → None", MB.parse_node(tick) is None)
    check("#1027 이중 백틱 인용 → None", MB.parse_node(f"설명 `` a `{M}` b `` 끝\n") is None)
    fence = f"## 예\n```\n{M}\n```\n"
    check("#1027 펜스 블록만 → None", MB.parse_node(fence) is None)
    check("#1027 물결 펜스·CRLF → None", MB.parse_node(f"예\r\n~~~~text\r\n{M}\r\n~~~~\r\n") is None)
    check("#1027 닫히지 않은 펜스 → 끝까지 인용", MB.parse_node(f"```\n{M}\n") is None)
    check("#1027 짧은 닫기는 펜스를 닫지 않음",
          MB.parse_node(f"````\n```\n{M}\n````\n") is None)
    both = f"설명 `{M}` 인용\n\n```\n{M}\n```\n\n{M}\n"
    check("#1027 인용 + 진짜 → 진짜만", MB.parse_node(both) == MB.NodeMarker(741, "작업"))
    after_fence = f"```\n예\n```\n{M}\n"
    check("#1027 닫힌 펜스 뒤 진짜 표지", MB.parse_node(after_fence) == MB.NodeMarker(741, "작업"))
    check("#1027 짝 없는 백틱은 인용 아님 → 줄 중간 거절",
          _raises(lambda: MB.parse_node(f"앞 ` {M}\n"), "한 줄"))
    check("#1027 인용 밖 줄 중간 → 거절 유지", _raises(lambda: MB.parse_node(f"앞 {M}\n"), "한 줄"))
    check("#1027 인용 밖 둘 → 거절 유지", _raises(lambda: MB.parse_node(f"{M}\n\n`{M}`\n\n{M}\n"), "2개"))
    check("#1027 인용 밖 형식 깨짐 → 거절 유지",
          _raises(lambda: MB.parse_node("`<!-- ax:node v=1 root=1 type=작업 -->`\n<!-- ax:node root=1 -->\n"), "형식"))
    out = MB.put_node(fence, mk)
    check("#1027 put_node 펜스 인용 보존 + 끝에 표지",
          out == fence + "\n<!-- ax:node v=1 root=1000 type=검증 -->\n", repr(out))
    out = MB.put_node(tick, mk)
    check("#1027 put_node 백틱 인용 보존 + 끝에 표지",
          out.startswith(tick.rstrip("\n")) and MB.parse_node(out) == mk, repr(out))
    out = MB.put_node(both, mk)
    check("#1027 put_node 인용 + 진짜 → 진짜만 교체",
          out == both.replace(f"\n\n{M}\n", "\n\n<!-- ax:node v=1 root=1000 type=검증 -->\n"), repr(out))


def test_planned_keys_1036():
    """`#1036` — 예정 노드(일감 없음)는 지도 키 P<n> 로 표에 있고 #번호와 섞일 수 있다."""
    nodes = [
        MB.MapNode(1032, "현황 실측", "프리필", None, "완료"),
        MB.MapNode("P1", "워커 일감 읽기", "작업", 1032, "Frontier", [1032]),
        MB.MapNode("P2", "일감 발주", "작업", "P1", "차단", ["P1", 1032]),
    ]
    blk = MB.MapBlock("목적지", "", nodes, [], [])
    text = MB.render(blk)
    check("#1036 표에 P 키 그대로", "| P1 | 워커 일감 읽기 |" in text and "| P2 |" in text and "| #1032 |" in text, text)
    check("#1036 부모·선행 칸에 P 키", "| P1 | 차단 | P1·#1032 |" in text, text)
    back = MB.parse(text)
    check("#1036 왕복 — id 형 보존", [n.id for n in back.nodes] == [1032, "P1", "P2"]
          and back.node("P2").parent == "P1" and back.node("P2").deps == ["P1", 1032], str(back.nodes))
    check("#1036 is_planned", MB.is_planned("P1") and not MB.is_planned(1) and not MB.is_planned("Q1")
          and not MB.is_planned("P"))
    check("#1036 label", MB.label(7) == "#7" and MB.label("P3") == "P3")
    check("#1036 id_key 섞인 정렬 — 번호 먼저", sorted(["P10", 5, "P2", 1], key=MB.id_key) == [1, 5, "P2", "P10"])
    bad = text.replace("| P2 |", "| Q2 |")
    check("#1036 모르는 키 거절", _raises(lambda: MB.parse(bad), "P<숫자>"))
    check("#1036 render 도 모르는 키 거절", _raises(lambda: MB.render(MB.MapBlock(
        "목적지", "", [MB.MapNode("X1", "t", "작업", None, "Frontier")], [], [])), "P<숫자>"))
    check("#1036 표 밖 예정 선행 거절", _raises(lambda: MB.render(MB.MapBlock(
        "목적지", "", [MB.MapNode("P1", "t", "작업", None, "차단", ["P9"])], [], [])), "P9"))
    check("#1036 예정 키 중복 거절", _raises(lambda: MB.render(MB.MapBlock(
        "목적지", "", [MB.MapNode("P1", "a", "작업", None, "Frontier"),
                       MB.MapNode("P1", "b", "작업", None, "Frontier")], [], [])), "겹친다"))


def main() -> int:
    for fn in (test_roundtrip, test_examples_parse, test_put, test_tag_rejections, test_section_rejections,
               test_table_rejections, test_render_rejections, test_node_marker, test_quoted_marker_1027,
               test_planned_keys_1036):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_map_block: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
