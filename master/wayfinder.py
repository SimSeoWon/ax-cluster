"""Wayfinder — Root 일감 본문의 지도로 탐색형 작업을 굴린다 (`#982` T4).

    create_map(root_id, destination, nodes, confirm=False)   미리보기 → 동의 뒤 노드 일감·관계·지도 등록
    load(root_id) / check(root_id) / frontier(root_id)       읽기만 한다
    sync(root_id, closed_node=None)                           노드 마감 반영 → 상태 재계산 → 바뀌었을 때만 쓰기
    on_node_closed(issue_id)                                  노드 표지가 있으면 그 Root 로 sync
    propose_node(...) → register_node(..., user_answer)       새 노드 제안(쓰기 0) → 동의 뒤 등록
    claim / mark_verified / close_root                        선점 · 재검증 완료 · Root 마감(사람 게이트)

[중요] **지도 영역이 기록이고 Redmine 부모·관계는 그 보이는 사본이다.** 둘이 어긋나면 고쳐 쓰지
않고 차이 목록과 함께 거절한다(`check`). 쓰는 경로(`sync`·`register_node`)는 먼저 대조한다.
🔴 [중요] **Redmine 에서 노드는 모두 Root 의 직속 하위 일감이다 — 파생 트리(「부모」 칸)는 지도에만 있다**
(`#982` T7 실측 2026-11-18, 사용자 결정). 파생 트리를 Redmine 부모-자식으로 옮겼더니 두 번 막혔다:
① 조상-후손 사이 `blocks` 를 422 로 거절(「일감은 하위 일감과 연결할 수 없습니다」, #986→#987) ·
② **열린 하위 일감이 있는 부모는 닫히지 않는다**(#990 「완료」 요청 → 실제 「신규」, 자식 #991). 파생 트리에서는
부모가 먼저 끝나야 하므로 ②가 근본 충돌이다. Redmine 의 부모-자식은 「범위가 품는다」이지 「앞선 일에서 파생됐다」가
아니다. 그래서 Redmine 부모 = Root, 선행은 **전부** 형제 사이 `blocks` 로 건다. 재검증 B·Frontier 는 지도 기준 그대로다.
[중요] **간선 방향** — 지도의 선행 `B.deps = [A]` 는 Redmine 관계 `create_relation(A, B)`(= A 가 B 를
막는다)다. `check` 는 `blocked_by(list_relations(B), B) == sorted(B.deps)` 로 대조한다.
[중요] **제안은 아무것도 쓰지 않는다** — `create_map(confirm=False)`·`propose_node` 는 Redmine 읽기만
한다. 등록·마감은 사용자 답(`user_answer`)이 있어야 돈다.
[중요] **LLM 0** — 중복 후보는 제목+요약의 정규화 토큰 겹침(Jaccard)으로 점수만 낸다. 판정은 사람 몫.
[중요] **모든 쓰기와 거절은 로그 한 줄을 남긴다** — `logf`(기본 stderr `[wayfinder] …`)로 흘리고
결과 dict 의 `"log"` 에도 담는다.

Redmine 접근은 `rm` 포트 하나다(기본 `master.redmine` 모듈). 대역은 `get_issue`·`update_issue`·
`create_issue`·`create_relation`·`list_relations`·`delete_relation` 을 같은 모양으로 구현하면 된다.

규칙 거절은 `{"ok": False, "refused": True, "why": …}` 로 돌려주고, 입력 형식 오류는 `WayfinderError`,
Redmine 읽기 실패는 `WayfinderTransportError` 로 올린다. 쓰기 도중 실패는 되돌리지 않고
`{"ok": False, "step": …, "created": […], "why": …}` 로 이미 생긴 것을 알린다.
[주의] 읽고-고치고-쓰는 사이에 사람이 Root 본문을 고치면 그 수정은 덮인다(Redmine 에 조건부 갱신이
없다) — `plan_tools` 와 같은 전제다.
"""
from __future__ import annotations

import copy
import re
import sys
from collections import deque

from master import map_block as MB
from master import map_diagram as MD

DONE = "완료"
FRONTIER = "Frontier"
WORKING = "작업중"
BLOCKED = "차단"
WAITING = "대기"
REVERIFY = "재검증"
RECOMPUTED = (WAITING, FRONTIER, BLOCKED)          # 이 셋만 다시 계산한다
FORBIDDEN_IN_TEXT = ("|", "</pre>", "<!--")
NOTE_DEFAULT = "맵 갱신"


class WayfinderError(ValueError):
    """입력·지도 형식이 계약에 어긋났다 — 사유 문장을 담는다."""


class WayfinderTransportError(WayfinderError):
    """Redmine 읽기·쓰기 실패 — 규칙 거절이 아니다."""


# ── 포트 · 로그 ───────────────────────────────────────────────────────────

def _port(rm):
    if rm is None:
        from master import redmine
        return redmine
    return rm


def _stderr(msg: str) -> None:
    print(f"[wayfinder] {msg}", file=sys.stderr)


class _Log:
    """줄을 모으면서 `logf` 로도 흘린다."""

    def __init__(self, logf=None):
        self.lines: list[str] = []
        self._f = logf or _stderr

    def __call__(self, msg: str) -> None:
        self.lines.append(msg)
        self._f(msg)


def _log_of(logf) -> _Log:
    return logf if isinstance(logf, _Log) else _Log(logf)


def _fail(log: _Log, msg: str, cls=WayfinderError):
    log(f"거절 — {msg}")
    raise cls(msg)


def _refuse(log: _Log, why: str, **extra) -> dict:
    log(f"거절 — {why}")
    return {"ok": False, "refused": True, "why": why, **extra, "log": log.lines}


def _stopped(log: _Log, step: str, why: str, created, **extra) -> dict:
    log(f"중단 — {step}: {why} (이미 생긴 것: {created or '없음'}, 되돌리지 않는다)")
    return {"ok": False, "step": step, "created": created, "why": why, **extra, "log": log.lines}


# ── 값 판정 ──────────────────────────────────────────────────────────────

def _issue_id(value, what: str) -> int:
    if isinstance(value, bool):
        raise WayfinderError(f"{what} 는 이슈 번호다: {value!r}")
    if isinstance(value, int):
        if value > 0:
            return value
    elif isinstance(value, str):
        s = value.strip().lstrip("#")
        if s.isdigit() and int(s) > 0:
            return int(s)
    raise WayfinderError(f"{what} 는 양의 이슈 번호다: {value!r}")


def _check_text(text, what: str, *, required: bool) -> str:
    """제목·요약 한 줄 판정 — 표 칸·다이어그램·본문 표지를 깨는 글을 막는다."""
    if not isinstance(text, str):
        raise WayfinderError(f"{what}: 글이 아니다 {text!r}")
    if required and not text.strip():
        raise WayfinderError(f"{what}: 비었다")
    if text != text.strip():
        raise WayfinderError(f"{what}: 앞뒤 공백은 왕복되지 않는다: {text[:80]!r}")
    if "\n" in text or "\r" in text:
        raise WayfinderError(f"{what}: 한 줄이어야 한다: {text[:80]!r}")
    for bad in FORBIDDEN_IN_TEXT:
        if bad in text:
            raise WayfinderError(f"{what}: {bad!r} 를 넣을 수 없다: {text[:80]!r}")
    return text


def _validate_titles(block: MB.MapBlock) -> None:
    for n in block.nodes:
        _check_text(n.title, f"#{n.id} 제목", required=True)


def _map_call(fn, *args):
    try:
        return fn(*args)
    except (MB.MapError, MD.DiagramError) as e:
        raise WayfinderError(str(e)) from e


# ── 순수 계산 ─────────────────────────────────────────────────────────────

def compute_states(block: MB.MapBlock) -> MB.MapBlock:
    """대기·Frontier·차단 노드의 상태를 다시 계산하고 다이어그램을 새로 그린 **사본**을 돌려준다.

    - 선행이 모두 완료 + 담당 없음 → Frontier
    - 선행 중 하나라도 완료가 아님(재검증 포함) → 차단
    - 선행이 모두 완료인데 담당이 있음 → 대기 (선점은 `claim` 이 작업중으로 옮긴다)
    작업중·완료·재검증은 손대지 않는다. 제목이 표·`<pre>`·표지를 깨면 `WayfinderError`.
    """
    out = copy.deepcopy(block)
    _validate_titles(out)
    by_id = {n.id: n for n in out.nodes}
    for n in out.nodes:
        missing = [d for d in n.deps if d not in by_id]
        if missing:
            raise WayfinderError(f"#{n.id}: 표에 없는 선행 " + ", ".join(f"#{d}" for d in missing))
    for n in out.nodes:
        if n.state not in RECOMPUTED:
            continue
        if not all(by_id[d].state == DONE for d in n.deps):
            n.state = BLOCKED
        elif n.owner:
            n.state = WAITING
        else:
            n.state = FRONTIER
    out.diagram = _map_call(MD.render, out)
    return out


def _frontier_list(block: MB.MapBlock) -> list[dict]:
    return [{"id": n.id, "title": n.title, "type": n.type}
            for n in sorted(block.nodes, key=lambda x: x.id) if n.state == FRONTIER]


def _state_counts(block: MB.MapBlock) -> dict:
    counts = {s: 0 for s in MB.STATES}
    for n in block.nodes:
        counts[n.state] = counts.get(n.state, 0) + 1
    return counts


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", (text or "").lower()))


def _score(a: str, b: str) -> float:
    """정규화 토큰 겹침(Jaccard) — 0~1, 소수 셋째 자리."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return round(len(ta & tb) / len(ta | tb), 3)


# ── 읽기 ──────────────────────────────────────────────────────────────────

def _get(rm, iid: int) -> dict:
    got = rm.get_issue(iid)
    if not isinstance(got, dict) or got.get("error"):
        reason = got.get("error") if isinstance(got, dict) else "응답 형식이 아니다"
        raise WayfinderTransportError(f"#{iid} 를 읽지 못했다 — {reason}")
    return got


def _parse_map(body: str, root_id: int) -> MB.MapBlock:
    try:
        block = MB.parse(body)
    except MB.MapError as e:
        raise WayfinderError(f"Root #{root_id} 지도 영역이 깨졌다 — {e}") from e
    if block is None:
        raise WayfinderError(f"Root #{root_id} 에 지도 영역이 없다")
    return block


def _load(rm, root_id: int) -> tuple[str, MB.MapBlock]:
    root = _get(rm, root_id)
    body = root.get("description") or ""
    return body, _parse_map(body, root_id)


def load(root_id, *, rm=None) -> MB.MapBlock:
    """Root 본문의 지도. 읽기 실패는 `WayfinderTransportError`, 영역 없음·깨짐은 `WayfinderError`."""
    return _load(_port(rm), _issue_id(root_id, "Root"))[1]


def _blocked_by(relations, issue_id: int) -> list[int]:
    from master.redmine import blocked_by
    return blocked_by(relations, issue_id)


def _differences(rm, root_id: int, block: MB.MapBlock) -> list[str]:
    """지도(기록)와 Redmine(사본)의 차이 — 부모 · 선행 관계 · 노드 표지."""
    diffs: list[str] = []
    for n in sorted(block.nodes, key=lambda x: x.id):
        iss = _get(rm, n.id)
        want_parent = root_id          # #982 T7 — Redmine 에서는 모든 노드가 Root 직속(파생 트리는 지도에만)
        got_parent = iss.get("parent")
        if got_parent != want_parent:
            diffs.append(f"#{n.id}: Redmine 부모 {('#' + str(got_parent)) if got_parent else '없음'}"
                         f" ≠ Root #{want_parent}")
        try:
            marker = MB.parse_node(iss.get("description") or "")
        except MB.MapError as e:
            diffs.append(f"#{n.id}: 노드 표지가 깨졌다 — {e}")
            marker = False
        if marker is None:
            diffs.append(f"#{n.id}: 노드 표지가 없다")
        elif marker:
            if marker.root != root_id:
                diffs.append(f"#{n.id}: 표지 root={marker.root} ≠ 지도 Root #{root_id}")
            if marker.type != n.type:
                diffs.append(f"#{n.id}: 표지 type={marker.type} ≠ 지도 타입 {n.type}")
        rels = rm.list_relations(n.id)
        if not isinstance(rels, dict) or rels.get("error"):
            reason = rels.get("error") if isinstance(rels, dict) else "응답 형식이 아니다"
            raise WayfinderTransportError(f"#{n.id} 관계를 읽지 못했다 — {reason}")
        got = _blocked_by(rels.get("relations") or [], n.id)
        want = sorted(n.deps)
        missing = [d for d in want if d not in got]
        extra = [d for d in got if d not in want]
        if missing:
            diffs.append(f"#{n.id}: Redmine 에 없는 선행 관계 " + ", ".join(f"#{d}→#{n.id}" for d in missing))
        if extra:
            diffs.append(f"#{n.id}: 지도에 없는 선행 관계 " + ", ".join(f"#{d}→#{n.id}" for d in extra))
    return diffs


def check(root_id, *, rm=None, logf=None) -> dict:
    """지도와 Redmine 부모·`blocks` 관계·노드 표지를 대조한다. 읽기만 한다."""
    log, rm = _log_of(logf), _port(rm)
    rid = _issue_id(root_id, "Root")
    _, block = _load(rm, rid)
    diffs = _differences(rm, rid, block)
    log(f"대조 Root #{rid} — 노드 {len(block.nodes)}개 · 차이 {len(diffs)}건")
    return {"ok": not diffs, "differences": diffs, "log": log.lines}


def frontier(root_id, *, rm=None) -> dict:
    """지금 집을 수 있는 노드와 상태별 개수. 상태는 메모리에서 다시 계산한 값이다(쓰지 않는다)."""
    block = compute_states(load(root_id, rm=rm))
    return {"frontier": _frontier_list(block), "states": _state_counts(block)}


# ── 쓰기 공통 ────────────────────────────────────────────────────────────

def _write_root(rm, root_id: int, old_body: str, block: MB.MapBlock, notes: str, log: _Log) -> str:
    new_body = _map_call(MB.put, old_body, block)
    out = rm.update_issue(root_id, description=new_body, notes=notes)
    if str(out).startswith("[주의]"):
        raise WayfinderTransportError(str(out))
    log(f"쓰기 — Root #{root_id} 지도 영역 갱신 (노트: {notes.splitlines()[0] if notes else ''})")
    return new_body


def _created_id(got) -> tuple[int | None, str, list[str]]:
    """create_issue 응답 → (id, 실패 사유, 생략 사유)."""
    if not isinstance(got, dict):
        return None, "응답 형식이 아니다", []
    if got.get("error"):
        return None, str(got["error"]), []
    try:
        return int(got["id"]), "", list(got.get("skipped") or [])
    except (KeyError, TypeError, ValueError):
        return None, f"응답에 id 가 없다: {got!r}", []


def _create_node_issue(rm, *, root_id: int, title: str, type_: str, summary: str,
                       parent_id: int, version: str, project: str, log: _Log):
    """노드 일감 하나를 만든다 → (id, 사유). 부모가 안 붙으면 실패로 본다(지도와 어긋나므로)."""
    desc = _map_call(MB.put_node, summary, MB.NodeMarker(root_id, type_))
    kwargs = {"fixed_version": version, "parent_issue_id": parent_id}
    if project:
        kwargs["project"] = project
    nid, why, skipped = _created_id(rm.create_issue(title, desc, **kwargs))
    if nid is None:
        return None, why
    log(f"쓰기 — 노드 일감 #{nid} 「{title}」 생성 (부모 #{parent_id} · 타입 {type_} · "
        f"마일스톤 {version or '없음'})")
    for s in skipped:
        log(f"[주의] #{nid} 생성에서 생략: {s}")
    if any("부모" in s for s in skipped):
        return nid, "부모가 붙지 않았다 — " + "; ".join(skipped)
    return nid, ""


def _relate(rm, dep: int, node: int, log: _Log) -> str:
    got = rm.create_relation(dep, node)
    if not isinstance(got, dict) or not got.get("ok"):
        return (got.get("error") if isinstance(got, dict) else "응답 형식이 아니다") or "실패"
    log(f"쓰기 — 관계 #{dep} blocks #{node}")
    return ""


# ── create_map ───────────────────────────────────────────────────────────

def _validate_specs(nodes, log: _Log) -> list[dict]:
    """노드 명세를 판정하고 **부모 먼저** 순서로 돌려준다."""
    if not isinstance(nodes, (list, tuple)):
        _fail(log, "nodes 는 목록이다")
    specs: list[dict] = []
    keys: set[str] = set()
    for i, raw in enumerate(nodes):
        if not isinstance(raw, dict):
            _fail(log, f"nodes[{i}] 가 dict 가 아니다")
        key = str(raw.get("key", "")).strip()
        if not key or key == MB.ROOT:
            _fail(log, f"nodes[{i}]: key 가 비었거나 예약어 {MB.ROOT!r} 다")
        if key in keys:
            _fail(log, f"key 가 겹친다: {key!r}")
        keys.add(key)
        try:
            title = _check_text(raw.get("title", ""), f"{key} 제목", required=True)
            summary = _check_text(raw.get("summary", "") or "", f"{key} 요약", required=False)
        except WayfinderError as e:
            _fail(log, str(e))
        typ = raw.get("type", "")
        if typ not in MB.NODE_TYPES:
            _fail(log, f"{key}: 모르는 타입 {typ!r} (허용 {', '.join(MB.NODE_TYPES)})")
        parent = str(raw.get("parent", MB.ROOT) or MB.ROOT).strip()
        deps = [str(d).strip() for d in (raw.get("deps") or [])]
        specs.append({"key": key, "title": title, "type": typ, "parent": parent,
                      "deps": deps, "summary": summary})
    for s in specs:
        if s["parent"] != MB.ROOT and s["parent"] not in keys:
            _fail(log, f"{s['key']}: 모르는 부모 {s['parent']!r}")
        if s["parent"] == s["key"]:
            _fail(log, f"{s['key']}: 자기 자신을 부모로 둘 수 없다")
        if len(set(s["deps"])) != len(s["deps"]):
            _fail(log, f"{s['key']}: 선행이 겹친다")
        for d in s["deps"]:
            if d == s["key"]:
                _fail(log, f"{s['key']}: 자기 자신을 선행으로 둘 수 없다")
            if d not in keys:
                _fail(log, f"{s['key']}: 모르는 선행 {d!r}")
    by_key = {s["key"]: s for s in specs}
    for s in specs:                                   # 부모 순환
        seen, cur = {s["key"]}, s
        while cur["parent"] != MB.ROOT:
            if cur["parent"] in seen:
                _fail(log, f"{s['key']}: 부모 사슬이 순환한다 — Root 에 닿지 않는다")
            seen.add(cur["parent"])
            cur = by_key[cur["parent"]]
    state: dict[str, int] = {}                        # 선행 순환 (0 방문중 · 1 끝)

    def visit(k: str, path: list[str]) -> None:
        if state.get(k) == 1:
            return
        if state.get(k) == 0:
            cyc = path[path.index(k):] + [k]
            _fail(log, "선행이 순환한다: " + " → ".join(cyc))
        state[k] = 0
        for d in by_key[k]["deps"]:
            visit(d, path + [k])
        state[k] = 1

    for s in specs:
        visit(s["key"], [])
    order: list[dict] = []
    queue = deque(s for s in specs if s["parent"] == MB.ROOT)
    while queue:
        s = queue.popleft()
        order.append(s)
        queue.extend(c for c in specs if c["parent"] == s["key"])
    return order


def _block_from(destination: str, order: list[dict], ids: dict, fog, oos) -> MB.MapBlock:
    nodes = [MB.MapNode(ids[s["key"]], s["title"], s["type"],
                        None if s["parent"] == MB.ROOT else ids[s["parent"]], WAITING,
                        [ids[d] for d in s["deps"]], "", s["summary"]) for s in order]
    return MB.MapBlock(destination=destination, diagram="", nodes=nodes,
                       fog=[str(x) for x in (fog or ())],
                       out_of_scope=[str(x) for x in (oos or ())])


def create_map(root_id, destination, nodes, *, fog=(), out_of_scope=(), confirm=False,
               user_answer="", project="", rm=None, logf=None) -> dict:
    """Root 에 지도를 만든다. `confirm=False` 는 미리보기뿐 — Redmine 쓰기 0건.

    `nodes` = `[{"key", "title", "type", "parent": "Root"|<key>, "deps": [keys], "summary"}]`.
    미리보기의 노드 번호는 **임시 번호 1..n**(부모 먼저 순서)이다 — 실제 번호는 등록 때 정해진다.
    `confirm=True` 는 `user_answer` 가 있어야 돈다. 순서: 노드 일감(부모 먼저, Root 와 같은 마일스톤,
    본문 = 요약 + 노드 표지) → 선행 관계(`create_relation(선행, 노드)`) → 상태 계산 → Root 본문.
    `project` 는 노드 일감의 Redmine 프로젝트다 — 비우면 `redmine.create_issue` 기본값.
    도중 실패는 되돌리지 않고 이미 만든 번호를 돌려준다.
    """
    log, rm = _log_of(logf), _port(rm)
    rid = _issue_id(root_id, "Root")
    order = _validate_specs(nodes, log)
    if confirm and not str(user_answer or "").strip():
        return _refuse(log, "confirm=True 인데 사용자 답(user_answer)이 없다 — 등록하지 않는다")
    root = _get(rm, rid)
    body = root.get("description") or ""
    try:
        existing = MB.parse(body)
    except MB.MapError as e:
        return _refuse(log, f"Root #{rid} 에 깨진 지도 영역이 이미 있다 — {e}")
    if existing is not None:
        return _refuse(log, f"Root #{rid} 에 지도 영역이 이미 있다 — 두 번째 지도는 만들지 않는다")
    version = root.get("fixed_version") or ""

    tmp = {s["key"]: i for i, s in enumerate(order, start=1)}
    try:
        preview_block = compute_states(_block_from(destination, order, tmp, fog, out_of_scope))
        preview = _map_call(MB.render, preview_block)
    except WayfinderError as e:
        _fail(log, str(e))
    if not confirm:
        writes = []
        for s in order:
            parent = f"Root #{rid}" if s["parent"] == MB.ROOT else \
                f"Root #{rid} (지도 파생 부모 {s['parent']} 임시 #{tmp[s['parent']]})"
            writes.append(f"create_issue 「{s['title']}」 타입 {s['type']} · Redmine 부모 {parent} · "
                          f"마일스톤 {version or '없음'} · 본문 = 요약 + 노드 표지")
        for s in order:
            for d in s["deps"]:
                writes.append(f"create_relation {d}(임시 #{tmp[d]}) blocks {s['key']}(임시 #{tmp[s['key']]})")
        writes.append(f"update_issue Root #{rid} — 본문에 지도 영역 + 노트")
        log(f"미리보기 Root #{rid} — 노드 {len(order)}개 · 예정 쓰기 {len(writes)}건 · 실제 쓰기 0건")
        return {"ok": True, "confirmed": False, "preview": preview, "temp_ids": tmp,
                "note": "미리보기의 노드 번호는 임시 번호 1..n 이다", "writes": writes,
                "log": log.lines}

    log(f"등록 시작 Root #{rid} — 사용자 답: {user_answer}")
    created: dict[str, int] = {}
    for s in order:
        parent_id = rid                # #982 T7 — Redmine 부모는 늘 Root, 파생 부모는 지도 「부모」 칸
        nid, why = _create_node_issue(rm, root_id=rid, title=s["title"], type_=s["type"],
                                      summary=s["summary"], parent_id=parent_id, version=version,
                                      project=project, log=log)
        if nid is not None:
            created[s["key"]] = nid
        if why:
            return _stopped(log, f"노드 생성 {s['key']}", why, list(created.values()))
    relations = []
    for s in order:
        for d in s["deps"]:
            why = _relate(rm, created[d], created[s["key"]], log)
            if why:
                return _stopped(log, f"관계 {d}→{s['key']}", why, list(created.values()),
                                relations=relations)
            relations.append([created[d], created[s["key"]]])
    block = compute_states(_block_from(destination, order, created, fog, out_of_scope))
    notes = (f"Wayfinder 지도 등록 — 노드 {len(created)}개 · 관계 {len(relations)}개\n"
             f"사용자 답: {user_answer}")
    try:
        _write_root(rm, rid, body, block, notes, log)
    except WayfinderTransportError as e:
        return _stopped(log, "Root 본문", str(e), list(created.values()), relations=relations)
    return {"ok": True, "confirmed": True, "created": created, "relations": relations,
            "frontier": _frontier_list(block), "log": log.lines}


# ── sync ─────────────────────────────────────────────────────────────────

def _sync(rid: int, closed_node, note: str, rm, log: _Log) -> dict:
    body, block = _load(rm, rid)
    diffs = _differences(rm, rid, block)
    if diffs:
        return _refuse(log, f"Root #{rid} 지도와 Redmine 이 어긋난다 — 고치지 않는다 ({len(diffs)}건)",
                       differences=diffs)
    if closed_node is not None:
        cid = _issue_id(closed_node, "마감 노드")
        n = block.node(cid)
        if n is None:
            return _refuse(log, f"#{cid} 는 Root #{rid} 지도의 노드가 아니다")
        status = _get(rm, cid).get("status")
        if status != DONE:
            return _refuse(log, f"#{cid} 의 Redmine 상태가 「{status}」다 — 「{DONE}」일 때만 완료로 옮긴다")
        if n.state != DONE:
            log(f"#{cid} 상태 {n.state} → {DONE}")
            n.state = DONE
    new = compute_states(block)
    new_body = _map_call(MB.put, body, new)
    changed = new_body != body
    if changed:
        try:
            _write_root(rm, rid, body, new, note or NOTE_DEFAULT, log)
        except WayfinderTransportError as e:
            return _stopped(log, "Root 본문", str(e), [])
    else:
        log(f"Root #{rid} 지도 변화 없음 — 쓰지 않는다")
    return {"ok": True, "changed": changed, "frontier": _frontier_list(new), "log": log.lines}


def sync(root_id, *, closed_node=None, note="", rm=None, logf=None) -> dict:
    """대조 → (마감 노드를 완료로) → 상태 재계산 → **바뀌었을 때만** Root 본문을 쓴다.

    대조에 차이가 있으면 아무것도 쓰지 않고 차이 목록으로 거절한다. `closed_node` 는 Redmine 상태가
    「완료」일 때만 완료로 옮긴다. 다른 노드의 재검증은 완료로 되돌리지 않는다(`mark_verified` 몫).
    """
    log, rm = _log_of(logf), _port(rm)
    return _sync(_issue_id(root_id, "Root"), closed_node, note, rm, log)


def on_node_closed(issue_id, *, rm=None, logf=None) -> dict:
    """닫힌 일감에 노드 표지가 있으면 그 Root 를 sync 한다. 표지가 없으면 아무것도 쓰지 않는다."""
    log, rm = _log_of(logf), _port(rm)
    iid = _issue_id(issue_id, "일감")
    iss = _get(rm, iid)
    try:
        marker = MB.parse_node(iss.get("description") or "")
    except MB.MapError as e:
        return _refuse(log, f"#{iid} 노드 표지가 깨졌다 — {e}")
    if marker is None:
        log(f"#{iid} 노드 표지 없음 — 건너뜀")
        return {"ok": True, "skipped": "노드 표지 없음", "log": log.lines}
    return _sync(marker.root, iid, f"노드 #{iid} 마감 — 맵 갱신", rm, log)


# ── 새 노드 ──────────────────────────────────────────────────────────────

def _proposal(block: MB.MapBlock, rid: int, title, type_, parent, deps, summary) -> dict:
    title = _check_text(title, "제목", required=True)
    summary = _check_text(summary or "", "요약", required=False)
    if type_ not in MB.NODE_TYPES:
        raise WayfinderError(f"모르는 타입 {type_!r} (허용 {', '.join(MB.NODE_TYPES)})")
    if parent in (None, MB.ROOT):
        parent_id = None
    else:
        parent_id = _issue_id(parent, "부모")
        if parent_id == rid:
            parent_id = None
        elif block.node(parent_id) is None:
            raise WayfinderError(f"부모 #{parent_id} 가 지도에 없다")
    dep_ids = []
    for d in deps or ():
        did = _issue_id(d, "선행")
        if block.node(did) is None:
            raise WayfinderError(f"선행 #{did} 가 지도에 없다")
        if did in dep_ids:
            raise WayfinderError(f"선행이 겹친다 #{did}")
        dep_ids.append(did)
    path: list[int] = []                              # 붙는 자리 → Root
    cur = parent_id
    while cur is not None:
        path.append(cur)
        cur = block.node(cur).parent
    containers: list[int | None] = [*path, None]      # 각 단계의 형제 묶음(부모) — 마지막은 Root
    me = f"{title} {summary}"
    duplicates, reverify = [], set(i for i in path if block.node(i).state == DONE)
    for level, cont in enumerate(containers):
        for n in block.nodes:
            if n.parent != cont:
                continue
            score = _score(me, f"{n.title} {n.summary}")
            if score > 0:
                duplicates.append({"id": n.id, "title": n.title, "level": level, "score": score})
            if n.state == DONE:
                reverify.add(n.id)
    duplicates.sort(key=lambda x: (-x["score"], x["level"], x["id"]))
    return {"proposal": {"root": rid, "title": title, "type": type_, "parent": parent_id,
                         "deps": dep_ids, "summary": summary},
            "duplicates": duplicates, "reverify": sorted(reverify), "path": [*path, rid]}


def propose_node(root_id, title, type, parent, *, deps=(), summary="", rm=None, logf=None) -> dict:  # noqa: A002
    """새 노드 제안. **Redmine 쓰기 0건.**

    `parent` = "Root" 또는 노드 번호. 중복 후보는 붙는 자리에서 Root 까지 **모든 단계의 형제**
    (각 조상의 직속 자식, Root 직속 포함)와 비교한 점수(>0)를 높은 순으로 낸다 — 판정하지 않는다.
    `reverify` = 그 경로의 조상과 각 단계 형제 가운데 완료인 것(형제의 하위 나무는 보지 않는다).
    `path` = 붙는 자리부터 Root 까지의 번호.
    """
    log, rm = _log_of(logf), _port(rm)
    rid = _issue_id(root_id, "Root")
    block = compute_states(_load(rm, rid)[1])
    try:
        p = _proposal(block, rid, title, type, parent, deps, summary)
    except WayfinderError as e:
        _fail(log, str(e))
    log(f"제안 Root #{rid} 「{p['proposal']['title']}」 — 중복 후보 {len(p['duplicates'])}건 · "
        f"재검증 예정 {p['reverify'] or '없음'} · 쓰기 0건")
    return {"ok": True, **p, "log": log.lines}


def register_node(root_id, proposal, *, user_answer, project="", rm=None, logf=None) -> dict:
    """제안을 등록한다. `user_answer` 가 있어야 돈다. 대조에 차이가 있으면 거절.

    순서: 노드 일감(부모·Root 의 마일스톤·표지) → 선행 관계 → 재검증 표시 + 상태 재계산 → Root 본문
    → 재검증 대상 노드마다 노트 「#<새> 추가로 재검증 대상 — 맵 Root #<root>」.
    중복 후보·재검증 대상은 **지금 지도로 다시 계산한다**(제안 뒤 지도가 바뀌었을 수 있다).
    """
    log, rm = _log_of(logf), _port(rm)
    rid = _issue_id(root_id, "Root")
    if not str(user_answer or "").strip():
        return _refuse(log, "사용자 답(user_answer)이 없다 — 노드를 등록하지 않는다")
    if not isinstance(proposal, dict):
        _fail(log, "proposal 은 propose_node 결과의 proposal dict 다")
    if proposal.get("root") not in (None, rid):
        return _refuse(log, f"제안의 Root #{proposal.get('root')} ≠ #{rid}")
    root = _get(rm, rid)
    body = root.get("description") or ""
    block = _parse_map(body, rid)
    diffs = _differences(rm, rid, block)
    if diffs:
        return _refuse(log, f"Root #{rid} 지도와 Redmine 이 어긋난다 — 등록하지 않는다 ({len(diffs)}건)",
                       differences=diffs)
    try:
        p = _proposal(compute_states(block), rid, proposal.get("title"), proposal.get("type"),
                      proposal.get("parent"), proposal.get("deps"), proposal.get("summary", ""))
    except WayfinderError as e:
        _fail(log, str(e))
    pr = p["proposal"]
    nid, why = _create_node_issue(rm, root_id=rid, title=pr["title"], type_=pr["type"],
                                  summary=pr["summary"], parent_id=rid,
                                  version=root.get("fixed_version") or "", project=project, log=log)
    if why:
        return _stopped(log, "노드 생성", why, [nid] if nid else [])
    for d in pr["deps"]:
        why = _relate(rm, d, nid, log)
        if why:
            return _stopped(log, f"관계 #{d}→#{nid}", why, [nid])
    for n in block.nodes:
        if n.id in p["reverify"]:
            log(f"#{n.id} 상태 {n.state} → {REVERIFY} (#{nid} 추가)")
            n.state = REVERIFY
    block.nodes.append(MB.MapNode(nid, pr["title"], pr["type"], pr["parent"], WAITING,
                                  list(pr["deps"]), "", pr["summary"]))
    try:
        new = compute_states(block)
    except WayfinderError as e:
        return _stopped(log, "상태 계산", str(e), [nid])
    rv = "·".join(f"#{i}" for i in p["reverify"]) or "없음"
    notes = f"노드 #{nid} 「{pr['title']}」 추가 — 재검증 대상 {rv}\n사용자 답: {user_answer}"
    try:
        _write_root(rm, rid, body, new, notes, log)
    except WayfinderTransportError as e:
        return _stopped(log, "Root 본문", str(e), [nid])
    for i in p["reverify"]:
        out = rm.update_issue(i, notes=f"#{nid} 추가로 재검증 대상 — 맵 Root #{rid}")
        if str(out).startswith("[주의]"):
            return _stopped(log, f"재검증 노트 #{i}", str(out), [nid])
        log(f"쓰기 — #{i} 재검증 노트")
    return {"ok": True, "id": nid, "reverify": p["reverify"], "duplicates": p["duplicates"],
            "frontier": _frontier_list(new), "log": log.lines}


# ── 선점 · 재검증 완료 · Root 마감 ────────────────────────────────────────

def claim(root_id, node_id, owner, *, rm=None, logf=None) -> dict:
    """Frontier 노드를 선점한다 — 담당을 적고 작업중으로. **지도만 바꾼다**: Redmine 담당자
    (assigned_to)는 바꾸지 않는다."""
    log, rm = _log_of(logf), _port(rm)
    rid = _issue_id(root_id, "Root")
    nid = _issue_id(node_id, "노드")
    try:
        owner = _check_text(owner if isinstance(owner, str) else "", "담당", required=True)
    except WayfinderError as e:
        _fail(log, str(e))
    if owner == MB.NO_DEPS:
        _fail(log, f"담당 {MB.NO_DEPS!r} 는 '담당 없음' 과 겹친다")
    body, block = _load(rm, rid)
    block = compute_states(block)
    n = block.node(nid)
    if n is None:
        return _refuse(log, f"#{nid} 는 Root #{rid} 지도의 노드가 아니다")
    if n.state != FRONTIER:
        return _refuse(log, f"#{nid} 는 Frontier 가 아니다 (지금 {n.state}) — 선점하지 않는다")
    n.owner, n.state = owner, WORKING
    new = compute_states(block)
    try:
        _write_root(rm, rid, body, new,
                    f"#{nid} 선점 — 담당 {owner} (지도만, Redmine 담당자는 바꾸지 않음)", log)
    except WayfinderTransportError as e:
        return _stopped(log, "Root 본문", str(e), [])
    return {"ok": True, "id": nid, "owner": owner, "state": WORKING, "log": log.lines}


def mark_verified(root_id, node_id, evidence, *, rm=None, logf=None) -> dict:
    """재검증 노드를 근거와 함께 완료로 되돌린다. 근거가 없으면 거절."""
    log, rm = _log_of(logf), _port(rm)
    rid = _issue_id(root_id, "Root")
    nid = _issue_id(node_id, "노드")
    if not str(evidence or "").strip():
        return _refuse(log, f"#{nid} 재검증 근거(evidence)가 없다")
    body, block = _load(rm, rid)
    n = block.node(nid)
    if n is None:
        return _refuse(log, f"#{nid} 는 Root #{rid} 지도의 노드가 아니다")
    if n.state != REVERIFY:
        return _refuse(log, f"#{nid} 는 재검증 상태가 아니다 (지금 {n.state})")
    n.state = DONE
    new = compute_states(block)
    try:
        _write_root(rm, rid, body, new, f"#{nid} 재검증 완료 — 근거: {evidence}", log)
    except WayfinderTransportError as e:
        return _stopped(log, "Root 본문", str(e), [])
    return {"ok": True, "id": nid, "state": DONE, "frontier": _frontier_list(new), "log": log.lines}


def close_root(root_id, *, confirm=False, user_answer="", rm=None, logf=None) -> dict:
    """Root 마감 — 사람 게이트. 미리보기는 막는 것(완료 아닌 노드·안개)을 보여 준다.

    `confirm=True` + `user_answer` + 막는 것 0 일 때만 Root 를 「완료」(100%)로 닫는다. 아니면 거절.
    """
    log, rm = _log_of(logf), _port(rm)
    rid = _issue_id(root_id, "Root")
    block = compute_states(_load(rm, rid)[1])
    blockers = [f"#{n.id} {n.title} — {n.state}" for n in sorted(block.nodes, key=lambda x: x.id)
                if n.state != DONE]
    blockers += [f"안개: {x}" for x in block.fog]
    if not confirm:
        log(f"Root #{rid} 마감 미리보기 — 막는 것 {len(blockers)}건 · 쓰기 0건")
        return {"ok": True, "confirmed": False, "ready": not blockers, "blockers": blockers,
                "log": log.lines}
    reasons = []
    if not str(user_answer or "").strip():
        reasons.append("사용자 답(user_answer)이 없다")
    if blockers:
        reasons.append(f"막는 것 {len(blockers)}건")
    if reasons:
        return _refuse(log, f"Root #{rid} 를 닫지 않는다 — " + " · ".join(reasons), blockers=blockers)
    out = rm.update_issue(rid, status_name=DONE, done_ratio=100,
                          notes=f"Wayfinder Root 마감 — 노드 {len(block.nodes)}개 전부 완료 · 안개 없음\n"
                                f"사용자 답: {user_answer}")
    if str(out).startswith("[주의]"):
        return _stopped(log, "Root 마감", str(out), [])
    log(f"쓰기 — Root #{rid} 「{DONE}」 마감")
    return {"ok": True, "confirmed": True, "closed": rid, "log": log.lines}
