"""지도 영역의 **다이어그램 절** 그리기 — `#982` T3.

노드 표(`map_block.MapBlock.nodes`)의 선행(deps) 관계로 단계를 나누고, 단계마다 ASCII 상자 하나를
위에서 아래로 쌓는다. 결과는 `<pre>` … `</pre>` 를 포함한 글(LF)이며 `block.diagram` 에 그대로 넣는다.

    <pre>
    +------------------------------+
    | [완료] 1단계                  |
    |  #1001 사전조사 (프리필) [완료] |
    +------------------------------+
                   |
                   v
    …
    </pre>

- 단계 = 선행 깊이. 표 안에 선행이 없으면 1단계, 아니면 1 + max(선행의 단계). 단계 안은 id 순.
- 상자 머리 상태는 단계에서 가장 「볼 만한」 상태다: 작업중 > 재검증 > Frontier > 차단 > 대기 > 완료.
- 단계 사이는 위 상자 가운데에 `|` · `v` 두 줄. 노드별 화살표는 그리지 않는다 — 정확한 간선은
  각 줄 끝 `← #a·#b` 와 Redmine 관계가 보여 준다(합의된 절충).
- 폭은 표시 폭으로 잰다 — 동아시아 넓은 글자(W·F)는 2칸. 그래야 고정폭 `<pre>` 에서 한글 줄이 맞는다.
- 제목은 자르지 않는다(상자가 넓어진다).

[중요] **같은 지도 → 같은 바이트.** 순서는 전부 id·단계로 정하고 입력 순서에 기대지 않는다.
[중요] **선행이 순환하거나 표 밖을 가리키면 그리지 않고 거절한다** (`DiagramError`) — 틀린 그림이
다음 노드 선택을 오도하는 것이 더 비싸다.
"""
from __future__ import annotations

import unicodedata

from master.map_block import MapBlock, MapNode, id_key, label

PRE_OPEN = "<pre>"
PRE_CLOSE = "</pre>"
EMPTY = "(노드 없음)"
DEP_ARROW = " ← "
DEP_SEP = "·"
# 머리 상태 우선순위 — 앞일수록 먼저 눈에 띄어야 한다.
HEAD_PRIORITY = ("작업중", "재검증", "Frontier", "차단", "대기", "완료")


class DiagramError(ValueError):
    """선행 관계로 단계를 정할 수 없다(순환·표 밖 선행·id 중복) — 관련 id 를 담는다."""


def width(text: str) -> int:
    """표시 폭 — 동아시아 넓은 글자(W·F)는 2칸, 나머지는 1칸."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def _level_map(nodes: list[MapNode]) -> dict[int, int]:
    by_id: dict[int, MapNode] = {}
    for n in nodes:
        if n.id in by_id:
            raise DiagramError(f"노드 id 가 겹친다: {label(n.id)}")
        by_id[n.id] = n
    for n in sorted(nodes, key=lambda x: id_key(x.id)):
        missing = sorted((d for d in n.deps if d not in by_id), key=id_key)
        if missing:
            raise DiagramError(f"{label(n.id)}: 표에 없는 선행 " + ", ".join(label(d) for d in missing))

    level: dict[int, int] = {}
    on_path: list[int] = []

    def visit(nid: int) -> int:
        if nid in level:
            return level[nid]
        if nid in on_path:
            cyc = on_path[on_path.index(nid):] + [nid]
            raise DiagramError("선행이 순환한다: " + " → ".join(label(x) for x in cyc))
        on_path.append(nid)
        deps = sorted(by_id[nid].deps, key=id_key)
        lv = 1 + max((visit(d) for d in deps), default=0)
        on_path.pop()
        level[nid] = lv
        return lv

    for nid in sorted(by_id, key=id_key):
        visit(nid)
    return level


def levels(block: MapBlock) -> list[list[int]]:
    """단계별 노드 id(단계 안은 id 순). 노드가 없으면 []. 순환·표 밖 선행은 `DiagramError`."""
    lv = _level_map(block.nodes)
    if not lv:
        return []
    out: list[list[int]] = [[] for _ in range(max(lv.values()))]
    for nid in sorted(lv, key=id_key):
        out[lv[nid] - 1].append(nid)
    return out


def head_state(states: list[str]) -> str:
    """단계 머리 상태 — `HEAD_PRIORITY` 에서 가장 앞에 있는 것."""
    for s in HEAD_PRIORITY:
        if s in states:
            return s
    raise DiagramError(f"모르는 상태뿐이다: {sorted(set(states))}")


def _node_line(n: MapNode) -> str:
    line = f"  {label(n.id)} {n.title} ({n.type}) [{n.state}]"
    if n.deps:
        line += DEP_ARROW + DEP_SEP.join(label(d) for d in sorted(n.deps, key=id_key))
    return line


def _box(lines: list[str]) -> list[str]:
    inner = max(width(x) for x in lines) + 1          # 오른쪽 여백 한 칸
    border = "+" + "-" * inner + "+"
    body = ["|" + x + " " * (inner - width(x)) + "|" for x in lines]
    return [border, *body, border]


def render(block: MapBlock) -> str:
    """`<pre>` · `</pre>` 줄을 포함한 다이어그램 글(LF). 같은 지도면 같은 바이트."""
    groups = levels(block)
    if not groups:
        return f"{PRE_OPEN}\n{EMPTY}\n{PRE_CLOSE}"
    by_id = {n.id: n for n in block.nodes}
    out = [PRE_OPEN]
    prev_width = 0
    for i, ids in enumerate(groups, start=1):
        nodes = [by_id[x] for x in ids]
        box = _box([f" [{head_state([n.state for n in nodes])}] {i}단계",
                    *(_node_line(n) for n in nodes)])
        if i > 1:
            col = prev_width // 2
            out += [" " * col + "|", " " * col + "v"]
        out += box
        prev_width = width(box[0])
    out.append(PRE_CLOSE)
    return "\n".join(out)
