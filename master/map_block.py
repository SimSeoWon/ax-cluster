"""Redmine 이슈 본문 안의 **지도 영역**(Wayfinder map) 읽기/쓰기 — `#982` T2.

Root 일감 본문에 지도 영역을 두고, 노드 일감 본문에는 한 줄 노드 표지를 둔다:

    <!-- ax:map:begin v=1 -->
    ## 목적지
    HUD 를 붙인다

    ## 다이어그램
    <pre>
    …다른 모듈이 만든 글 — 글자 그대로 둔다…
    </pre>

    ## 노드
    | 노드 | 제목 | 타입 | 부모 | 상태 | 선행 | 담당 | 요약 |
    |---|---|---|---|---|---|---|---|
    | #1001 | 사전조사 | 프리필 | Root | 완료 | — | — | HUD 기능 필요 |
    | #1002 | HUD | 작업 | #1001 | Frontier | #1001 | — | |

    ## 안개
    - 아직 모르는 것

    ## 범위 밖
    - 요지 — 이유
    <!-- ax:map:end -->

    <!-- ax:node v=1 root=1000 type=작업 -->        ← 노드 일감 본문의 표지

[중요] **이 모듈은 형식만 안다.** 그래프 판단(어느 노드가 Frontier 인가)·Redmine 호출·다이어그램 그리기는
여기 없다. 영역 밖 본문은 바이트 그대로 돌려준다 — `plan_block`·`spec_block` 과 같은 규율이다.
Redmine 이 본문을 CRLF 로 저장하므로 새로 쓰는 줄도 본문의 줄바꿈 방식을 따른다.

[중요] **형식이 어긋나면 고쳐 읽지 않고 거절한다** (`MapError`). 제목 순서가 다르거나, 칸 수가 다르거나,
모르는 타입·상태이거나, 부모·선행이 표 밖을 가리키면 추측으로 잇지 않는다 — 사람이 본문을 직접 고친
흔적일 수 있고, 잘못 읽은 지도로 다음 노드를 고르는 것이 더 비싸다.

- 절 안 글은 앞뒤 빈 줄만 걷고 읽는다. 다이어그램 절은 그 밖에는 글자 그대로다.
- 영역 안에서 `## ` 로 시작하는 줄은 모두 절 제목이다 — 그래서 목적지·다이어그램 글에 그런 줄을 넣으면
  쓰기(`render`)가 거절한다(왕복이 깨지므로).
- 부모 사슬은 Root 에 닿아야 한다(표 안에서 닫힌 나무) — 순환도 거절한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

FORMAT_VERSION = 1
BEGIN_RE = re.compile(r"<!-- ax:map:begin v=(\d+) -->")
END_TAG = "<!-- ax:map:end -->"
SECTIONS = ("목적지", "다이어그램", "노드", "안개", "범위 밖")
COLUMNS = ("노드", "제목", "타입", "부모", "상태", "선행", "담당", "요약")
NODE_TYPES = ("프리필", "작업", "검증")
STATES = ("대기", "Frontier", "작업중", "완료", "차단", "재검증")
NO_DEPS = "—"
ROOT = "Root"
DEP_SEP = "·"

NODE_VERSION = 1
NODE_PREFIX_RE = re.compile(r"<!-- ax:node\b")
NODE_RE = re.compile(r"<!-- ax:node v=(\d+) root=(\S+) type=(\S+) -->")

_ID_RE = re.compile(r"#(\d+)")


class MapError(ValueError):
    """지도 영역·노드 표지의 형식이 어긋났다 — 사유 문장을 담는다."""


@dataclass
class MapNode:
    """노드 표 한 줄. `parent` 가 None 이면 Root, `owner` 가 "" 이면 담당 없음(—)."""
    id: int
    title: str
    type: str
    parent: int | None
    state: str
    deps: list[int] = field(default_factory=list)
    owner: str = ""
    summary: str = ""


@dataclass
class MapBlock:
    """지도 영역 전체."""
    destination: str
    diagram: str
    nodes: list[MapNode] = field(default_factory=list)
    fog: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)

    def node(self, node_id: int) -> MapNode | None:
        return next((n for n in self.nodes if n.id == node_id), None)


@dataclass
class NodeMarker:
    """노드 일감 본문의 표지 — 어느 Root 의 어떤 타입 노드인가."""
    root: int
    type: str


# ── 영역 찾기 ──────────────────────────────────────────────────────────────

def _region(body: str) -> tuple[int, int, int, int] | None:
    """(시작 태그 시작, 영역 안 시작, 영역 안 끝, 끝 태그 끝). 태그가 없으면 None."""
    begins = list(BEGIN_RE.finditer(body))
    ends = [m.start() for m in re.finditer(re.escape(END_TAG), body)]
    if not begins and not ends:
        return None
    if len(begins) != 1 or len(ends) != 1:
        raise MapError(f"지도 태그가 한 쌍이 아니다 — 시작 {len(begins)}개 · 끝 {len(ends)}개")
    begin = begins[0]
    if ends[0] < begin.end():
        raise MapError("지도 끝 태그가 시작 태그보다 앞에 있다")
    if int(begin.group(1)) != FORMAT_VERSION:
        raise MapError(f"모르는 지도 형식 v={begin.group(1)} (이 코드는 v{FORMAT_VERSION})")
    return begin.start(), begin.end(), ends[0], ends[0] + len(END_TAG)


# ── 칸 · 값 ───────────────────────────────────────────────────────────────

def _cells(line: str) -> list[str]:
    s = line.strip()
    if not (s.startswith("|") and s.endswith("|")) or len(s) < 2:
        raise MapError(f"표 줄이 아니다: {s[:80]!r}")
    return [p.strip() for p in s[1:-1].split("|")]


def _node_id(text: str, what: str) -> int:
    m = _ID_RE.fullmatch(text)
    if not m:
        raise MapError(f"{what} 는 #<숫자> 다: {text!r}")
    return int(m.group(1))


def _deps(text: str, nid: int) -> list[int]:
    if text == NO_DEPS:
        return []
    out: list[int] = []
    for part in text.split(DEP_SEP):
        d = _node_id(part.strip(), f"#{nid} 선행")
        if d == nid:
            raise MapError(f"#{nid}: 자기 자신을 선행으로 둘 수 없다")
        if d in out:
            raise MapError(f"#{nid}: 선행이 겹친다 #{d}")
        out.append(d)
    return out


def _check_node(n: MapNode) -> None:
    """한 노드의 값 판정(표 전체를 보는 판정은 `_check_tree`)."""
    if not isinstance(n.id, int) or isinstance(n.id, bool) or n.id < 0:
        raise MapError(f"노드 id 는 음이 아닌 정수다: {n.id!r}")
    if not n.title.strip():
        raise MapError(f"#{n.id}: 제목이 비었다")
    if n.type not in NODE_TYPES:
        raise MapError(f"#{n.id}: 모르는 타입 {n.type!r} (허용 {', '.join(NODE_TYPES)})")
    if n.state not in STATES:
        raise MapError(f"#{n.id}: 모르는 상태 {n.state!r} (허용 {', '.join(STATES)})")
    if n.parent is not None and n.parent == n.id:
        raise MapError(f"#{n.id}: 자기 자신을 부모로 둘 수 없다")
    if n.id in n.deps:
        raise MapError(f"#{n.id}: 자기 자신을 선행으로 둘 수 없다")
    if len(set(n.deps)) != len(n.deps):
        raise MapError(f"#{n.id}: 선행이 겹친다")


def _check_tree(nodes: list[MapNode]) -> None:
    """id 중복 · 표 밖 부모/선행 · 부모 순환을 거절한다."""
    seen: set[int] = set()
    for n in nodes:
        if n.id in seen:
            raise MapError(f"노드 id 가 겹친다: #{n.id}")
        seen.add(n.id)
    by_id = {n.id: n for n in nodes}
    for n in nodes:
        if n.parent is not None and n.parent not in by_id:
            raise MapError(f"#{n.id}: 부모 #{n.parent} 가 표에 없다 (표 밖 부모는 Root 만)")
        missing = [d for d in n.deps if d not in by_id]
        if missing:
            raise MapError(f"#{n.id}: 없는 선행 " + ", ".join(f"#{d}" for d in missing))
    for n in nodes:
        walked = {n.id}
        cur = n
        while cur.parent is not None:
            if cur.parent in walked:
                raise MapError(f"#{n.id}: 부모 사슬이 순환한다 — Root 에 닿지 않는다")
            walked.add(cur.parent)
            cur = by_id[cur.parent]


# ── 절 나누기 ─────────────────────────────────────────────────────────────

def _trim(lines: list[str]) -> list[str]:
    """앞뒤 빈 줄(공백뿐인 줄 포함)만 걷는다."""
    a, b = 0, len(lines)
    while a < b and not lines[a].strip():
        a += 1
    while b > a and not lines[b - 1].strip():
        b -= 1
    return lines[a:b]


def _sections(inner: str) -> dict[str, list[str]]:
    lines = inner.splitlines()
    heads = [i for i, ln in enumerate(lines) if ln.startswith("## ")]
    if any(ln.strip() for ln in lines[:heads[0] if heads else len(lines)]):
        raise MapError("지도 영역에 첫 제목(## 목적지) 앞 글이 있다")
    names = [lines[i][3:].strip() for i in heads]
    if tuple(names) != SECTIONS:
        raise MapError(f"지도 절 제목이 다르다: {names} (필요 {list(SECTIONS)})")
    out: dict[str, list[str]] = {}
    for k, i in enumerate(heads):
        stop = heads[k + 1] if k + 1 < len(heads) else len(lines)
        out[names[k]] = _trim(lines[i + 1:stop])
    return out


def _bullets(lines: list[str], what: str) -> list[str]:
    out = []
    for ln in lines:
        if not ln.strip():
            continue
        if not ln.startswith("- "):
            raise MapError(f"{what} 절은 '- ' 목록만 쓴다: {ln.strip()[:80]!r}")
        item = ln[2:].strip()
        if not item:
            raise MapError(f"{what} 절에 빈 항목이 있다")
        out.append(item)
    return out


def _parse_nodes(lines: list[str]) -> list[MapNode]:
    rows = [ln for ln in lines if ln.strip()]
    if len(rows) < 2:
        raise MapError("노드 표에 머리줄과 구분줄이 없다")
    if tuple(_cells(rows[0])) != COLUMNS:
        raise MapError(f"노드 표 머리줄이 다르다: {_cells(rows[0])}")
    sep = _cells(rows[1])
    if len(sep) != len(COLUMNS) or not all(re.fullmatch(r":?-{3,}:?", c) for c in sep):
        raise MapError("노드 표 구분줄이 아니다")
    nodes: list[MapNode] = []
    for ln in rows[2:]:
        c = _cells(ln)
        if len(c) != len(COLUMNS):
            raise MapError(f"칸 수가 {len(c)}개다 (필요 {len(COLUMNS)}): {ln.strip()[:80]!r}")
        nid_s, title, typ, parent_s, state, deps_s, owner, summary = c
        nid = _node_id(nid_s, "노드")
        parent = None if parent_s == ROOT else _node_id(parent_s, f"#{nid} 부모")
        n = MapNode(nid, title, typ, parent, state, _deps(deps_s, nid),
                    "" if owner == NO_DEPS else owner, summary)
        if not owner:
            raise MapError(f"#{nid}: 담당 칸이 비었다 — 없으면 {NO_DEPS}")
        _check_node(n)
        nodes.append(n)
    _check_tree(nodes)
    return nodes


# ── 읽기 ──────────────────────────────────────────────────────────────────

def parse(body: str) -> MapBlock | None:
    """본문에서 지도를 읽는다. 영역이 없으면 None, 형식이 어긋나면 `MapError`."""
    body = body or ""
    r = _region(body)
    if r is None:
        return None
    sec = _sections(body[r[1]:r[2]])
    destination = "\n".join(sec["목적지"])
    if not destination.strip():
        raise MapError("목적지가 비었다")
    return MapBlock(
        destination=destination,
        diagram="\n".join(sec["다이어그램"]),
        nodes=_parse_nodes(sec["노드"]),
        fog=_bullets(sec["안개"], "안개"),
        out_of_scope=_bullets(sec["범위 밖"], "범위 밖"),
    )


def exists(body: str) -> bool:
    """지도 영역이 있는가. 깨진 영역은 `MapError`."""
    return parse(body) is not None


# ── 쓰기 ──────────────────────────────────────────────────────────────────

def _cell(text: str, what: str) -> str:
    if "|" in text:
        raise MapError(f"{what}: 칸에 '|' 를 넣을 수 없다: {text[:80]!r}")
    if "\n" in text or "\r" in text:
        raise MapError(f"{what}: 칸에 줄바꿈을 넣을 수 없다: {text[:80]!r}")
    if text != text.strip():
        raise MapError(f"{what}: 칸 앞뒤 공백은 왕복되지 않는다: {text[:80]!r}")
    return text


def _text(text: str, what: str, *, required: bool) -> str:
    if "\r" in text:
        raise MapError(f"{what}: CR 을 넣을 수 없다 — 줄바꿈은 LF 로 준다")
    if BEGIN_RE.search(text) or END_TAG in text or NODE_PREFIX_RE.search(text):
        raise MapError(f"{what}: 지도·노드 표지를 넣을 수 없다")
    lines = text.split("\n")
    if any(ln.startswith("## ") for ln in lines):
        raise MapError(f"{what}: '## ' 로 시작하는 줄은 절 제목으로 읽힌다")
    if text and _trim(lines) != lines:
        raise MapError(f"{what}: 앞뒤 빈 줄은 왕복되지 않는다")
    if required and not text.strip():
        raise MapError(f"{what}: 비었다")
    return text


def _item(text: str, what: str) -> str:
    if not text.strip() or text != text.strip() or "\n" in text or "\r" in text:
        raise MapError(f"{what}: 항목은 앞뒤 공백 없는 한 줄이다: {text[:80]!r}")
    if BEGIN_RE.search(text) or END_TAG in text or NODE_PREFIX_RE.search(text):
        raise MapError(f"{what}: 지도·노드 표지를 넣을 수 없다")
    return text


def render(block: MapBlock) -> str:
    """태그를 포함한 영역 글(LF). 읽기와 같은 규칙으로 판정해 어긋나면 `MapError`."""
    dest = _text(block.destination, "목적지", required=True)
    diagram = _text(block.diagram, "다이어그램", required=False)
    for n in block.nodes:
        _check_node(n)
        if n.owner == NO_DEPS:
            raise MapError(f"#{n.id}: 담당 {NO_DEPS!r} 는 '담당 없음' 과 겹친다 — 없으면 \"\"")
    _check_tree(block.nodes)
    rows = ["| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    for n in block.nodes:
        cells = (f"#{n.id}", _cell(n.title, f"#{n.id} 제목"), n.type,
                 ROOT if n.parent is None else f"#{n.parent}", n.state,
                 DEP_SEP.join(f"#{d}" for d in n.deps) if n.deps else NO_DEPS,
                 _cell(n.owner, f"#{n.id} 담당") or NO_DEPS,
                 _cell(n.summary, f"#{n.id} 요약"))
        rows.append("|" + "".join(f" {x} |" if x else " |" for x in cells))
    fog = ["- " + _item(x, "안개") for x in block.fog]
    oos = ["- " + _item(x, "범위 밖") for x in block.out_of_scope]

    parts = [f"<!-- ax:map:begin v={FORMAT_VERSION} -->"]
    for name, body in ((SECTIONS[0], [dest]), (SECTIONS[1], [diagram] if diagram else []),
                       (SECTIONS[2], rows), (SECTIONS[3], fog), (SECTIONS[4], oos)):
        if len(parts) > 1:
            parts.append("")
        parts.append(f"## {name}")
        parts.extend(body)
    parts.append(END_TAG)
    return "\n".join(parts)


def put(body: str, block: MapBlock) -> str:
    """영역이 있으면 통째로 바꾸고, 없으면 본문 끝에 빈 줄 하나를 두고 붙인다. 영역 밖은 바이트 그대로."""
    body = body or ""
    nl = "\r\n" if "\r\n" in body else "\n"
    text = render(block).replace("\n", nl)
    r = _region(body)
    if r is not None:
        return body[:r[0]] + text + body[r[3]:]
    base = body.rstrip("\r\n")
    return (base + nl + nl if base else "") + text + nl


# ── 노드 표지 ─────────────────────────────────────────────────────────────

def _marker_span(body: str) -> tuple[int, int, NodeMarker] | None:
    """(줄 안 표지 시작, 표지 끝, 표지). 없으면 None. 둘 이상이거나 값이 어긋나면 `MapError`."""
    hits = list(NODE_PREFIX_RE.finditer(body))
    if not hits:
        return None
    if len(hits) != 1:
        raise MapError(f"노드 표지가 {len(hits)}개다 — 하나만 둔다")
    m = NODE_RE.match(body, hits[0].start())
    if not m:
        raise MapError("노드 표지 형식이 아니다 — <!-- ax:node v=1 root=<숫자> type=<타입> -->")
    line_start = body.rfind("\n", 0, m.start()) + 1
    line_end = body.find("\n", m.end())
    line_end = len(body) if line_end == -1 else line_end
    if body[line_start:m.start()].strip() or body[m.end():line_end].strip():
        raise MapError("노드 표지는 한 줄을 혼자 차지해야 한다")
    if int(m.group(1)) != NODE_VERSION:
        raise MapError(f"모르는 노드 표지 형식 v={m.group(1)} (이 코드는 v{NODE_VERSION})")
    if not m.group(2).isdigit():
        raise MapError(f"노드 표지 root 는 숫자다: {m.group(2)!r}")
    if m.group(3) not in NODE_TYPES:
        raise MapError(f"노드 표지의 모르는 타입 {m.group(3)!r} (허용 {', '.join(NODE_TYPES)})")
    return m.start(), m.end(), NodeMarker(int(m.group(2)), m.group(3))


def _marker_text(marker: NodeMarker) -> str:
    if not isinstance(marker.root, int) or isinstance(marker.root, bool) or marker.root < 0:
        raise MapError(f"노드 표지 root 는 음이 아닌 정수다: {marker.root!r}")
    if marker.type not in NODE_TYPES:
        raise MapError(f"노드 표지의 모르는 타입 {marker.type!r} (허용 {', '.join(NODE_TYPES)})")
    return f"<!-- ax:node v={NODE_VERSION} root={marker.root} type={marker.type} -->"


def parse_node(body: str) -> NodeMarker | None:
    """노드 일감 본문의 표지. 없으면 None, 둘 이상이거나 값이 어긋나면 `MapError`."""
    span = _marker_span(body or "")
    return None if span is None else span[2]


def put_node(body: str, marker: NodeMarker) -> str:
    """표지를 바꾸거나 본문 끝에 붙인다. 표지 밖 바이트는 그대로, 새 줄은 본문의 줄바꿈 방식."""
    body = body or ""
    text = _marker_text(marker)
    span = _marker_span(body)
    if span is not None:
        return body[:span[0]] + text + body[span[1]:]
    nl = "\r\n" if "\r\n" in body else "\n"
    base = body.rstrip("\r\n")
    return (base + nl + nl if base else "") + text + nl
