"""Wayfinder — Root 일감 본문의 지도로 탐색형 작업을 굴린다 (`#982` T4).

    create_map(root_id, destination, nodes, confirm=False)   미리보기 → 동의 뒤 노드 일감·관계·지도 등록
    load(root_id) / check(root_id) / frontier(root_id)       읽기만 한다
    sync(root_id, closed_node=None)                           노드 마감 반영 → 상태 재계산 → 바뀌었을 때만 쓰기
    on_node_closed(issue_id)                                  노드 표지가 있으면 그 Root 로 sync
    propose_node(..., graduates=) → register_node(..., user_answer)
                                                              새 노드 제안(쓰기 0) → 동의 뒤 등록 (안개 졸업 포함, `#1000` T1)
    propose_edit(root_id, op, …) → apply_edit(..., user_answer)
                                                              안개·범위 밖·목적지 편집 제안(쓰기 0) → 동의 뒤 적용 (`#1000` T2)
                                                              노드 → 범위 밖(`node_out`)도 같은 쌍이다 (`#1000` T3)
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
[중요] **안개는 지도 생성 뒤에도 바뀐다** (`#1000`) — 졸업(새 노드로 옮김)·해소·범위 밖 이동·추가와
목적지·범위 밖 편집은 모두 제안(쓰기 0) → 사용자 답 → 적용이다. 결정 근거와 전·후는 **Root 노트에만** 남는다
(지도 형식은 그대로, 사용자 결정 A). 적용은 **지금 지도로 다시 계산한다** — 대상이 사라졌으면 쓰지 않고 거절.
[중요] **노드 → 범위 밖(`node_out`)은 관계를 먼저 지우고 지도를 쓴 뒤 노드를 닫는다** (`#1000` T3).
열린 선행에 막힌 일감은 Redmine 이 닫지 않는다(실측 #982 — #992 가 닫힐 때까지 #993 이 「신규」) — 그래서
그 노드에 걸린 관계를 전부 지운 뒤에 닫는다. 파생 자식이 있는 노드와 이미 완료된 노드는 제안 때 거절한다.
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

# 지도 편집 연산 (`#1000` T2) — 이름 → 노트용 한국어 이름. 계획 함수는 `_EDIT_PLANNERS`.
FOG_ADD = "fog_add"
FOG_RESOLVE = "fog_resolve"
FOG_TO_OUT = "fog_to_out"
DESTINATION = "destination"
OUT_EDIT = "out_edit"
OUT_TO_FOG = "out_to_fog"
NODE_OUT = "node_out"                               # `#1000` T3 — 노드를 표에서 빼 범위 밖으로
EDIT_LABELS = {
    FOG_ADD: "안개 추가",
    FOG_RESOLVE: "안개 해소",
    FOG_TO_OUT: "안개 → 범위 밖",
    DESTINATION: "목적지 변경",
    OUT_EDIT: "범위 밖 수정",
    OUT_TO_FOG: "범위 밖 → 안개",
    NODE_OUT: "노드 → 범위 밖",
}
OUT_SEP = " — "                                     # 범위 밖 줄 「요지 — 이유」


class WayfinderError(ValueError):
    """입력·지도 형식이 계약에 어긋났다 — 사유 문장을 담는다."""


class WayfinderTransportError(WayfinderError):
    """Redmine 읽기·쓰기 실패 — 규칙 거절이 아니다."""


class _Conflict(WayfinderError):
    """지금 지도와 맞지 않는다(대상 없음·중복·변화 없음). 제안에서는 그대로 오르고,
    적용·등록에서는 지도가 그 사이 바뀐 것이므로 규칙 거절(`_refuse`)로 바꾼다."""


class _RuleRefusal(WayfinderError):
    """규칙이 막는다(파생 자식 있음·이미 완료) — 제안·적용 **둘 다** 규칙 거절 dict 로 돌려준다.
    사람이 그 목록을 봐야 하므로 예외로 올리지 않는다. `extra` 는 거절 dict 에 함께 싣는다."""

    def __init__(self, why: str, **extra):
        super().__init__(why)
        self.extra = extra


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


def _node_ref(value, what: str):
    """노드 참조 — 일감 번호(int, 「#12」·「12」도) 또는 예정 키 「P<n>」(`#1036`)."""
    if isinstance(value, str) and MB.is_planned(value.strip()):
        return value.strip()
    return _issue_id(value, what)


def _next_key(block: MB.MapBlock) -> str:
    """새 예정 노드 키 — 지금 지도의 가장 큰 P<n> 다음(`#1036`)."""
    nums = [int(MB.PLANNED_RE.fullmatch(n.id).group(1)) for n in block.nodes if MB.is_planned(n.id)]
    return f"{MB.PLANNED_PREFIX}{max(nums, default=0) + 1}"


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


def _listing(items: list[str]) -> str:
    return " · ".join(f"{i}) {x}" for i, x in enumerate(items, start=1)) or "없음"


def _pick(items: list[str], target, what: str, *, exact: bool = False) -> str:
    """목록 줄 하나를 고른다 — 글 그대로 또는 1부터 센 번호(int·숫자 글). 고른 **글**을 돌려준다.

    `exact=True` 는 글만 받는다(적용·등록의 재확인 — 번호는 지도가 바뀌면 다른 줄을 가리킨다).
    없으면 `_Conflict`(지금 목록을 사유에 싣는다), 형식이 틀리면 `WayfinderError`.
    """
    if target is None or isinstance(target, bool):
        raise WayfinderError(f"{what} 대상이 없다 — 글 또는 1부터 센 번호 (지금 {what}: {_listing(items)})")
    if isinstance(target, str):
        if target in items:
            return target
        s = target.strip()
        if exact or not s.isdigit():
            raise _Conflict(f"{what} 에 없는 줄 {target!r} (지금 {what}: {_listing(items)})")
        idx = int(s)
    elif isinstance(target, int):
        if exact:
            raise WayfinderError(f"{what} 대상은 글이어야 한다: {target!r}")
        idx = target
    else:
        raise WayfinderError(f"{what} 대상은 글 또는 번호다: {target!r}")
    if 1 <= idx <= len(items):
        return items[idx - 1]
    raise _Conflict(f"{what} 에 {idx}번 줄이 없다 (지금 {what}: {_listing(items)})")


def _check_line(text, what: str) -> str:
    """안개·범위 밖·목적지 한 줄 — `_check_text` + 지도 영역이 절 제목으로 읽을 줄 거절."""
    text = _check_text(text, what, required=True)
    if text.startswith("## "):
        raise WayfinderError(f"{what}: '## ' 로 시작하는 줄은 절 제목으로 읽힌다: {text[:80]!r}")
    return text


def _validate_titles(block: MB.MapBlock) -> None:
    for n in block.nodes:
        _check_text(n.title, f"{MB.label(n.id)} 제목", required=True)


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
            raise WayfinderError(f"{MB.label(n.id)}: 표에 없는 선행 " + ", ".join(f"#{d}" for d in missing))
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
            for n in sorted(block.nodes, key=lambda x: MB.id_key(x.id)) if n.state == FRONTIER]


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


def _relations_of(rm, issue_id: int) -> list[dict]:
    """그 일감에 걸린 Redmine 관계 전부(막는 쪽·막히는 쪽 모두). 읽기 실패는 `WayfinderTransportError`."""
    rels = rm.list_relations(issue_id)
    if not isinstance(rels, dict) or rels.get("error"):
        reason = rels.get("error") if isinstance(rels, dict) else "응답 형식이 아니다"
        raise WayfinderTransportError(f"#{issue_id} 관계를 읽지 못했다 — {reason}")
    return list(rels.get("relations") or [])


def _differences(rm, root_id: int, block: MB.MapBlock) -> list[str]:
    """지도(기록)와 Redmine(사본)의 차이 — 부모 · 선행 관계 · 노드 표지."""
    diffs: list[str] = []
    for n in sorted(block.nodes, key=lambda x: MB.id_key(x.id)):
        if MB.is_planned(n.id):                       # `#1036` — 예정 노드는 일감이 없다: 착수 전 상태만 허용
            if n.state not in RECOMPUTED:
                diffs.append(f"{n.id}: 예정 노드(일감 없음)인데 상태가 {n.state} — 착수 전 상태"
                             f"({'·'.join(RECOMPUTED)})여야 한다")
            continue
        planned_deps = [d for d in n.deps if MB.is_planned(d)]
        if planned_deps:
            diffs.append(f"{MB.label(n.id)}: 일감 있는 노드의 선행에 예정 노드 " + ", ".join(planned_deps))
        iss = _get(rm, n.id)
        want_parent = root_id          # #982 T7 — Redmine 에서는 모든 노드가 Root 직속(파생 트리는 지도에만)
        got_parent = iss.get("parent")
        if got_parent != want_parent:
            diffs.append(f"{MB.label(n.id)}: Redmine 부모 {('#' + str(got_parent)) if got_parent else '없음'}"
                         f" ≠ Root #{want_parent}")
        try:
            marker = MB.parse_node(iss.get("description") or "")
        except MB.MapError as e:
            diffs.append(f"{MB.label(n.id)}: 노드 표지가 깨졌다 — {e}")
            marker = False
        if marker is None:
            diffs.append(f"{MB.label(n.id)}: 노드 표지가 없다")
        elif marker:
            if marker.root != root_id:
                diffs.append(f"{MB.label(n.id)}: 표지 root={marker.root} ≠ 지도 Root #{root_id}")
            if marker.type != n.type:
                diffs.append(f"{MB.label(n.id)}: 표지 type={marker.type} ≠ 지도 타입 {n.type}")
        got = _blocked_by(_relations_of(rm, n.id), n.id)
        want = sorted(d for d in n.deps if not MB.is_planned(d))
        missing = [d for d in want if d not in got]
        extra = [d for d in got if d not in want]
        if missing:
            diffs.append(f"{MB.label(n.id)}: Redmine 에 없는 선행 관계 " + ", ".join(f"#{d}→#{n.id}" for d in missing))
        if extra:
            diffs.append(f"{MB.label(n.id)}: 지도에 없는 선행 관계 " + ", ".join(f"#{d}→#{n.id}" for d in extra))
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
    `#1036` — **Redmine 일감은 만들지 않는다.** 노드는 지도에만 예정 노드(키 P1·P2…, 부모 먼저 순서)로
    올라가고, 일감은 선점(`claim`) 때 생긴다. `confirm=True` 는 `user_answer` 가 있어야 돈다 — 쓰기는
    Root 본문 하나다. `project` 는 받기만 한다(일감은 `claim(project=…)` 이 만든다).
    """
    log, rm = _log_of(logf), _port(rm)
    rid = _issue_id(root_id, "Root")
    order = _validate_specs(nodes, log)
    # `#1028` — 맵은 목적지 + 지금 집을 수 있는 첫 노드에서 시작해 자란다(#982 조사·리포트 206 §2).
    #    처음부터 선행 사슬을 깔면 설계서를 먼저 다 만드는 분산 작업(work) 방식으로 되돌아간다.
    if not order:
        return _refuse(log, "첫 노드가 없다 — 맵은 목적지와 지금 집을 수 있는 노드 하나 이상으로 시작한다")
    chained = [s["key"] for s in order if s["deps"]]
    if chained:
        return _refuse(log, f"선행이 걸린 노드는 처음에 만들지 않는다: {', '.join(chained)} — 처음 노드는 지금 집을 수 "
                            "있어야 하고, 나머지는 앞 노드가 끝난 뒤 제안·등록(propose_node → register_node)으로 붙인다")
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
    tmp = {s["key"]: f"{MB.PLANNED_PREFIX}{i}" for i, s in enumerate(order, start=1)}
    try:
        preview_block = compute_states(_block_from(destination, order, tmp, fog, out_of_scope))
        preview = _map_call(MB.render, preview_block)
    except WayfinderError as e:
        _fail(log, str(e))
    if not confirm:
        writes = [f"update_issue Root #{rid} — 본문에 지도 영역(예정 노드 {', '.join(tmp.values())}) + 노트"]
        log(f"미리보기 Root #{rid} — 예정 노드 {len(order)}개 · 일감 0(선점 때 생긴다) · 실제 쓰기 0건")
        return {"ok": True, "confirmed": False, "preview": preview, "temp_ids": tmp,
                "note": "노드는 예정 키(P<n>)로 지도에만 오른다 — Redmine 일감은 선점(claim) 때 생긴다(#1036)",
                "writes": writes, "log": log.lines}

    log(f"등록 시작 Root #{rid} — 사용자 답: {user_answer}")
    created: dict[str, str] = dict(tmp)
    block = preview_block
    notes = (f"Wayfinder 지도 등록 — 예정 노드 {len(created)}개({', '.join(created.values())}) · "
             f"Redmine 일감은 선점 때 만든다\n사용자 답: {user_answer}")
    try:
        _write_root(rm, rid, body, block, notes, log)
    except WayfinderTransportError as e:
        return _stopped(log, "Root 본문", str(e), [])
    return {"ok": True, "confirmed": True, "created": created, "relations": [],
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

def _proposal(block: MB.MapBlock, rid: int, title, type_, parent, deps, summary,
              graduates=None, *, exact: bool = False) -> dict:
    title = _check_text(title, "제목", required=True)
    grad = None if graduates is None else _pick(block.fog, graduates, "안개", exact=exact)
    summary = _check_text(summary or "", "요약", required=False)
    if type_ not in MB.NODE_TYPES:
        raise WayfinderError(f"모르는 타입 {type_!r} (허용 {', '.join(MB.NODE_TYPES)})")
    if parent in (None, MB.ROOT):
        parent_id = None
    else:
        parent_id = _node_ref(parent, "부모")
        if parent_id == rid:
            parent_id = None
        elif block.node(parent_id) is None:
            raise WayfinderError(f"부모 {MB.label(parent_id)} 가 지도에 없다")
    dep_ids = []
    for d in deps or ():
        did = _node_ref(d, "선행")
        if block.node(did) is None:
            raise WayfinderError(f"선행 {MB.label(did)} 가 지도에 없다")
        if did in dep_ids:
            raise WayfinderError(f"선행이 겹친다 {MB.label(did)}")
        dep_ids.append(did)
    path: list = []                              # 붙는 자리 → Root
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
    duplicates.sort(key=lambda x: (-x["score"], x["level"], MB.id_key(x["id"])))
    return {"proposal": {"root": rid, "title": title, "type": type_, "parent": parent_id,
                         "deps": dep_ids, "summary": summary, "graduates": grad},
            "duplicates": duplicates, "reverify": sorted(reverify, key=MB.id_key), "path": [*path, rid]}


def propose_node(root_id, title, type, parent, *, deps=(), summary="", graduates=None,  # noqa: A002
                 rm=None, logf=None) -> dict:
    """새 노드 제안. **Redmine 쓰기 0건.**

    `graduates` = 이 노드로 **졸업**시킬 안개 한 줄 — 글 그대로 또는 1부터 센 번호(`#1000` T1).
    제안의 `"graduates"` 에는 고른 글이 담긴다(없으면 None). 모르는 줄은 지금 안개 목록과 함께
    `WayfinderError`.

    `parent` = "Root" 또는 노드 번호. 중복 후보는 붙는 자리에서 Root 까지 **모든 단계의 형제**
    (각 조상의 직속 자식, Root 직속 포함)와 비교한 점수(>0)를 높은 순으로 낸다 — 판정하지 않는다.
    `reverify` = 그 경로의 조상과 각 단계 형제 가운데 완료인 것(형제의 하위 나무는 보지 않는다).
    `path` = 붙는 자리부터 Root 까지의 번호.
    """
    log, rm = _log_of(logf), _port(rm)
    rid = _issue_id(root_id, "Root")
    block = compute_states(_load(rm, rid)[1])
    try:
        p = _proposal(block, rid, title, type, parent, deps, summary, graduates)
    except WayfinderError as e:
        _fail(log, str(e))
    grad = p["proposal"]["graduates"]
    log(f"제안 Root #{rid} 「{p['proposal']['title']}」 — 중복 후보 {len(p['duplicates'])}건 · "
        f"재검증 예정 {p['reverify'] or '없음'} · 안개 졸업 {grad if grad is not None else '없음'} · 쓰기 0건")
    return {"ok": True, **p, "log": log.lines}


def register_node(root_id, proposal, *, user_answer, project="", rm=None, logf=None) -> dict:
    """제안을 등록한다. `user_answer` 가 있어야 돈다. 대조에 차이가 있으면 거절.

    `#1036` — **Redmine 일감은 만들지 않는다.** 새 노드는 예정 키(P<n>)로 지도에만 오르고, 선행도 지도에만
    적힌다(일감·blocks 는 선점 `claim` 때). 순서: 재검증 표시 + 상태 재계산 → Root 본문
    → 재검증 대상 노드마다 노트 「#<새> 추가로 재검증 대상 — 맵 Root #<root>」.
    중복 후보·재검증 대상은 **지금 지도로 다시 계산한다**(제안 뒤 지도가 바뀌었을 수 있다).
    `proposal["graduates"]` 가 있으면 지금 안개에서 **글 그대로** 다시 찾는다 — 사라졌으면 쓰기 0건으로
    거절하고, 있으면 노드 줄과 **같은 Root 쓰기**에서 안개에서 걷는다(노트 「안개 졸업: <글> → #<새>」).
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
                      proposal.get("parent"), proposal.get("deps"), proposal.get("summary", ""),
                      proposal.get("graduates"), exact=True)
    except _Conflict as e:
        return _refuse(log, f"Root #{rid} 지도가 제안 뒤 바뀌었다 — 등록하지 않는다 ({e})")
    except WayfinderError as e:
        _fail(log, str(e))
    pr = p["proposal"]
    nid = _next_key(block)
    log(f"예정 노드 {nid} 「{pr['title']}」 — 일감은 선점 때 만든다(#1036)")
    for n in block.nodes:
        if n.id in p["reverify"]:
            log(f"{MB.label(n.id)} 상태 {n.state} → {REVERIFY} ({MB.label(nid)} 추가)")
            n.state = REVERIFY
    block.nodes.append(MB.MapNode(nid, pr["title"], pr["type"], pr["parent"], WAITING,
                                  list(pr["deps"]), "", pr["summary"]))
    if pr["graduates"] is not None:
        block.fog = [x for x in block.fog if x != pr["graduates"]]
        log(f"안개 졸업 「{pr['graduates']}」 → {MB.label(nid)}")
    try:
        new = compute_states(block)
    except WayfinderError as e:
        return _stopped(log, "상태 계산", str(e), [nid])
    rv = "·".join(f"#{i}" for i in p["reverify"]) or "없음"
    grad_note = f"\n안개 졸업: {pr['graduates']} → {MB.label(nid)}" if pr["graduates"] is not None else ""
    notes = (f"예정 노드 {nid} 「{pr['title']}」 추가(일감은 선점 때) — 재검증 대상 {rv}{grad_note}\n"
             f"사용자 답: {user_answer}")
    try:
        _write_root(rm, rid, body, new, notes, log)
    except WayfinderTransportError as e:
        return _stopped(log, "Root 본문", str(e), [nid])
    for i in p["reverify"]:
        out = rm.update_issue(i, notes=f"{MB.label(nid)} 추가로 재검증 대상 — 맵 Root #{rid}")
        if str(out).startswith("[주의]"):
            return _stopped(log, f"재검증 노트 #{i}", str(out), [nid])
        log(f"쓰기 — #{i} 재검증 노트")
    return {"ok": True, "id": nid, "reverify": p["reverify"], "duplicates": p["duplicates"],
            "graduated": pr["graduates"], "frontier": _frontier_list(new), "log": log.lines}


# ── 지도 편집 (`#1000` T2) ────────────────────────────────────────────────

_SECTION_NAMES = {"destination": "목적지", "fog": "안개", "out_of_scope": "범위 밖", "nodes": "노드"}


def _no_text(op: str, text) -> None:
    if text not in (None, ""):
        raise WayfinderError(f"{op}: text 를 받지 않는다 — 대상(target)과 근거(reason)만 쓴다")


def _need_reason(op: str, reason: str) -> str:
    if not reason:
        raise WayfinderError(f"{op}: 결정 근거(reason)가 필요하다 — Root 노트에 남는다")
    return reason


def _no_dup(items: list[str], text: str, what: str) -> None:
    if text in items:
        raise _Conflict(f"{what} 에 이미 있는 줄이다: {text!r}")


def _plan_fog_add(b: MB.MapBlock, target, text, reason, exact) -> dict:
    if target is not None:
        raise WayfinderError(f"{FOG_ADD}: target 을 받지 않는다 — 새 줄은 text 로 준다")
    text = _check_line(text, "안개")
    _no_dup(b.fog, text, "안개")
    b.fog.append(text)
    return {"target": None, "text": text, "sections": ("fog",)}


def _plan_fog_resolve(b, target, text, reason, exact) -> dict:
    _no_text(FOG_RESOLVE, text)
    _need_reason(FOG_RESOLVE, reason)
    line = _pick(b.fog, target, "안개", exact=exact)
    b.fog.remove(line)
    return {"target": line, "text": "", "sections": ("fog",)}


def _plan_fog_to_out(b, target, text, reason, exact) -> dict:
    _no_text(FOG_TO_OUT, text)
    _need_reason(FOG_TO_OUT, reason)
    line = _pick(b.fog, target, "안개", exact=exact)
    moved = _check_line(f"{line}{OUT_SEP}{reason}", "범위 밖")
    _no_dup(b.out_of_scope, moved, "범위 밖")
    b.fog.remove(line)
    b.out_of_scope.append(moved)
    return {"target": line, "text": moved, "sections": ("fog", "out_of_scope")}


def _plan_destination(b, target, text, reason, exact) -> dict:
    if target is not None:
        raise WayfinderError(f"{DESTINATION}: target 을 받지 않는다 — 새 목적지는 text 로 준다")
    text = _check_line(text, "목적지")
    if text == b.destination:
        raise _Conflict("목적지가 지금과 같다 — 바뀌는 것이 없다")
    b.destination = text
    return {"target": None, "text": text, "sections": ("destination",)}


def _plan_out_edit(b, target, text, reason, exact) -> dict:
    line = _pick(b.out_of_scope, target, "범위 밖", exact=exact)
    text = _check_line(text, "범위 밖")
    if text == line:
        raise _Conflict("범위 밖 줄이 지금과 같다 — 바뀌는 것이 없다")
    _no_dup(b.out_of_scope, text, "범위 밖")
    b.out_of_scope[b.out_of_scope.index(line)] = text
    return {"target": line, "text": text, "sections": ("out_of_scope",)}


def _plan_out_to_fog(b, target, text, reason, exact) -> dict:
    line = _pick(b.out_of_scope, target, "범위 밖", exact=exact)
    if text in (None, ""):
        text = line.rsplit(OUT_SEP, 1)[0] if OUT_SEP in line else line
    text = _check_line(text, "안개")
    _no_dup(b.fog, text, "안개")
    b.out_of_scope.remove(line)
    b.fog.append(text)
    return {"target": line, "text": text, "sections": ("fog", "out_of_scope")}


def _node_row(n: MB.MapNode) -> str:
    """노드 표 한 줄의 요지 — 노트·미리보기용(`#번호 제목 — 상태 (선행 …)`)."""
    deps = f" (선행 {'·'.join(MB.label(d) for d in n.deps)})" if n.deps else ""
    return f"{MB.label(n.id)} {n.title} — {n.state}{deps}"


def _plan_node_out(b, target, text, reason, exact) -> dict:
    """노드를 표에서 빼고 범위 밖에 「#<번호> <제목> — <근거>」를 붙인다(`#1000` T3).

    다른 노드의 선행에서도 걷고 상태를 다시 계산한다(그 노드만 기다리던 노드는 Frontier 가 될 수 있다).
    파생 자식이 있으면(사용자 결정 A)·이미 완료면 `_RuleRefusal`, 지도에 없으면 `_Conflict`.
    """
    _no_text(NODE_OUT, text)
    _need_reason(NODE_OUT, reason)
    nid = _node_ref(target, "노드")
    n = b.node(nid)
    if n is None:
        now = " · ".join(f"{MB.label(x.id)} {x.title}" for x in sorted(b.nodes, key=lambda x: MB.id_key(x.id))) or "없음"
        raise _Conflict(f"{MB.label(nid)} 는 지도의 노드가 아니다 (지금 노드: {now})")
    node = {"id": n.id, "title": n.title, "state": n.state}
    if n.state == DONE:
        raise _RuleRefusal(f"{MB.label(nid)} — 이미 완료된 노드는 범위 밖으로 돌리지 않는다 — 결과가 이미 적용됐다",
                           node=node)
    children = sorted((x for x in b.nodes if x.parent == nid), key=lambda x: MB.id_key(x.id))
    if children:
        listed = " · ".join(f"{MB.label(x.id)} {x.title}" for x in children)
        raise _RuleRefusal(f"{MB.label(nid)} 에 파생 자식이 있다 — 자식부터 정리해야 범위 밖으로 돌린다: {listed}",
                           node=node, children=[{"id": x.id, "title": x.title} for x in children])
    line = _check_line(f"{MB.label(nid)} {n.title}{OUT_SEP}{reason}", "범위 밖")
    _no_dup(b.out_of_scope, line, "범위 밖")
    dependents = sorted((x.id for x in b.nodes if nid in x.deps), key=MB.id_key)
    b.nodes = [x for x in b.nodes if x.id != nid]
    for x in b.nodes:
        if nid in x.deps:
            x.deps = [d for d in x.deps if d != nid]
    b.out_of_scope.append(line)
    computed = compute_states(b)                      # 미리보기에도 바뀐 상태(Frontier)를 보인다
    b.nodes, b.diagram = computed.nodes, computed.diagram
    return {"target": nid, "text": line, "sections": ("nodes", "out_of_scope"),
            "extra": {"node": node, "children": [], "dependents": dependents}}


_EDIT_PLANNERS = {
    FOG_ADD: _plan_fog_add,
    FOG_RESOLVE: _plan_fog_resolve,
    FOG_TO_OUT: _plan_fog_to_out,
    DESTINATION: _plan_destination,
    OUT_EDIT: _plan_out_edit,
    OUT_TO_FOG: _plan_out_to_fog,
    NODE_OUT: _plan_node_out,
}


def _sections_of(b: MB.MapBlock, keys) -> dict:
    out = {}
    for k in keys:
        if k == "nodes":                              # 표는 줄 요지 글로 — 노트·제안에 그대로 싣는다
            out[k] = [_node_row(n) for n in sorted(b.nodes, key=lambda x: MB.id_key(x.id))]
        else:
            out[k] = copy.deepcopy(getattr(b, k))
    return out


def _plan_edit(block: MB.MapBlock, op, target, text, reason, *, exact: bool = False) -> dict:
    """편집 하나를 지도 **사본**에 적용한다 → {"block", "target", "text", "reason", "before", "after", "extra"}.

    대상·텍스트 판정과 `MB.render` 판정까지 여기서 끝낸다 — 쓰기 때가 아니라 제안 때 실패하도록.
    `exact=True`(적용 때)는 대상을 글로만 다시 찾는다.
    """
    if op not in _EDIT_PLANNERS:
        raise WayfinderError(f"모르는 편집 {op!r} (허용 {', '.join(_EDIT_PLANNERS)})")
    reason = _check_text(reason if reason is not None else "", "근거", required=False)
    if text is not None and not isinstance(text, str):
        raise WayfinderError(f"text 는 글이다: {text!r}")
    b = copy.deepcopy(block)
    got = _EDIT_PLANNERS[op](b, target, text if text is not None else "", reason, exact)
    _map_call(MB.render, b)
    keys = got["sections"]
    return {"block": b, "target": got["target"], "text": got["text"], "reason": reason,
            "before": _sections_of(block, keys), "after": _sections_of(b, keys),
            "extra": got.get("extra", {})}


def _fmt_sections(sec: dict) -> str:
    parts = []
    for k, v in sec.items():
        shown = (" · ".join(v) or "없음") if isinstance(v, list) else v
        parts.append(f"{_SECTION_NAMES.get(k, k)} [{shown}]")
    return " / ".join(parts)


def propose_edit(root_id, op, *, target=None, text="", reason="", rm=None, logf=None) -> dict:
    """지도 편집 제안 — **Redmine 쓰기 0건** (`#1000` T2).

    `op` 는 `EDIT_LABELS` 의 이름이다:
      fog_add      text(새 안개 줄) — 이미 있는 줄이면 거절
      fog_resolve  target(안개 줄) + reason(결정 근거, 필수) — 줄을 걷는다. 근거는 Root 노트에만 남는다
      fog_to_out   target(안개 줄) + reason(필수) — 범위 밖에 「<줄> — <근거>」로 옮긴다
      destination  text(새 목적지)
      out_edit     target(범위 밖 줄) + text(바꿀 글)
      out_to_fog   target(범위 밖 줄) + text(선택 — 비우면 「 — 이유」 꼬리를 뗀 글)
      node_out     target(노드 번호) + reason(필수) — 표에서 빼고 범위 밖에 「#<번호> <제목> — <근거>」.
                   제안에 `node`(번호·제목·상태) · `children`(지도 파생 자식) · `relations`(그 일감에 걸린
                   Redmine 관계 번호, 읽기만) · `dependents`(그 노드를 선행으로 둔 노드 — 선행을 잃는다)를 싣는다.
                   파생 자식이 있거나 이미 완료면 **규칙 거절 dict**(`refused`)로 돌려준다 — 목록을 봐야 하므로.
    target 은 글 그대로 또는 1부터 센 번호다(node_out 은 노드 번호). 제안의 `target` 에는 **고른 글**이 담긴다.
    """
    log, rm = _log_of(logf), _port(rm)
    rid = _issue_id(root_id, "Root")
    block = _load(rm, rid)[1]
    try:
        plan = _plan_edit(block, op, target, text, reason)
    except _RuleRefusal as e:
        return _refuse(log, f"Root #{rid} {EDIT_LABELS.get(op, op)} 거절 — {e} · 쓰기 0건", **e.extra)
    except WayfinderError as e:
        _fail(log, str(e))
    label = EDIT_LABELS[op]
    proposal = {"root": rid, "op": op, "target": plan["target"], "text": plan["text"],
                "reason": plan["reason"], "before": plan["before"], "after": plan["after"]}
    extra = ""
    if op == NODE_OUT:
        rels = _relations_of(rm, plan["target"])
        proposal.update(plan["extra"], relations=sorted(r["id"] for r in rels))
        extra = (f" · 관계 {proposal['relations'] or '없음'} 삭제 예정"
                 f" · 선행을 잃는 노드 {proposal['dependents'] or '없음'}")
    log(f"편집 제안 Root #{rid} {label} — 전 {_fmt_sections(plan['before'])} → "
        f"후 {_fmt_sections(plan['after'])}{extra} · 쓰기 0건")
    return {"ok": True, "proposal": proposal, "log": log.lines}


def apply_edit(root_id, proposal, *, user_answer, rm=None, logf=None) -> dict:
    """편집 제안을 적용한다. `user_answer` 가 있어야 돈다. 대조에 차이가 있으면 거절.

    제안의 op·target·text·reason 으로 **지금 지도에서 다시 계산한다** — 대상이 사라졌거나 중복·변화
    없음이면 쓰기 0건으로 거절. Root 는 한 번 쓰고, 노트에 편집 이름 · 전 → 후 · 근거 · 사용자 답을 남긴다.

    node_out 은 쓰기가 셋이고 이 순서다: ① 그 노드에 걸린 관계 전부 삭제(지금 다시 읽은 목록) → ② Root
    지도(행 제거 · 다른 노드 선행에서 제거 · 범위 밖 줄 · 상태 재계산) → ③ 노드 일감 「완료」(100%) +
    노트. ①②에서 멈추면 `_stopped`(되돌리지 않는다). ③이 실패하면 지도는 이미 범위 밖이라 되돌리지 않고
    `{"ok": False, "step": "노드 닫기", "map_written": True, …}` 로 크게 알린다.
    """
    log, rm = _log_of(logf), _port(rm)
    rid = _issue_id(root_id, "Root")
    if not str(user_answer or "").strip():
        return _refuse(log, "사용자 답(user_answer)이 없다 — 지도를 고치지 않는다")
    if not isinstance(proposal, dict):
        _fail(log, "proposal 은 propose_edit 결과의 proposal dict 다")
    if proposal.get("root") not in (None, rid):
        return _refuse(log, f"제안의 Root #{proposal.get('root')} ≠ #{rid}")
    op = proposal.get("op")
    body, block = _load(rm, rid)
    diffs = _differences(rm, rid, block)
    if diffs:
        return _refuse(log, f"Root #{rid} 지도와 Redmine 이 어긋난다 — 고치지 않는다 ({len(diffs)}건)",
                       differences=diffs)
    # fog_resolve·fog_to_out·node_out 의 제안 text 는 결과 표시일 뿐 입력이 아니다(out_to_fog 는 제안 때 정한 글 그대로)
    text = "" if op in (FOG_RESOLVE, FOG_TO_OUT, NODE_OUT) else proposal.get("text", "")
    try:
        plan = _plan_edit(block, op, proposal.get("target"), text, proposal.get("reason", ""),
                          exact=True)
    except _RuleRefusal as e:
        return _refuse(log, f"Root #{rid} 지도가 제안 뒤 바뀌었다 — 고치지 않는다 ({e})", **e.extra)
    except _Conflict as e:
        return _refuse(log, f"Root #{rid} 지도가 제안 뒤 바뀌었다 — 고치지 않는다 ({e})")
    except WayfinderError as e:
        _fail(log, str(e))
    label = EDIT_LABELS[op]
    try:
        new = compute_states(plan["block"])
    except WayfinderError as e:
        _fail(log, str(e))
    notes = (f"Wayfinder 맵 편집 — {label}\n"
             f"전: {_fmt_sections(plan['before'])}\n"
             f"후: {_fmt_sections(plan['after'])}\n"
             f"근거: {plan['reason'] or '없음'}\n"
             f"사용자 답: {user_answer}")
    log(f"편집 적용 Root #{rid} {label} — 사용자 답: {user_answer}")
    if op == NODE_OUT:
        return _apply_node_out(rm, rid, body, new, plan, notes, log)
    try:
        _write_root(rm, rid, body, new, notes, log)
    except WayfinderTransportError as e:
        return _stopped(log, "Root 본문", str(e), [])
    return {"ok": True, "op": op, "before": plan["before"], "after": plan["after"], "log": log.lines}


def _apply_node_out(rm, rid: int, body: str, new: MB.MapBlock, plan: dict, notes: str, log: _Log) -> dict:
    """node_out 쓰기 셋 — 관계 삭제 → Root 지도 → 노드 닫기 (`#1000` T3)."""
    nid, ex = plan["target"], plan["extra"]
    result = {"op": NODE_OUT, "node": ex["node"], "dependents": ex["dependents"],
              "before": plan["before"], "after": plan["after"]}
    deleted: list[int] = []
    if MB.is_planned(nid):                            # `#1036` — 예정 노드는 일감·관계가 없다: 지도만 쓴다
        result["deleted_relations"] = deleted
        try:
            _write_root(rm, rid, body, new, notes + "\n예정 노드(일감 없음) — 관계 삭제·노드 닫기 없음", log)
        except WayfinderTransportError as e:
            return _stopped(log, "Root 본문", str(e), [], **result)
        return {"ok": True, **result, "log": log.lines}
    # ① 관계 — 열린 선행에 막힌 일감은 Redmine 이 닫지 않는다(#982 실측), 선행을 잃는 노드의 관계도 지도와 맞춘다
    for r in sorted(_relations_of(rm, nid), key=lambda x: x["id"]):
        got = rm.delete_relation(r["id"])
        if not isinstance(got, dict) or not got.get("ok"):
            why = (got.get("error") if isinstance(got, dict) else "응답 형식이 아니다") or "실패"
            return _stopped(log, f"관계 삭제 {r['id']}", why, [], **result, deleted_relations=deleted)
        deleted.append(r["id"])
        log(f"쓰기 — 관계 {r['id']} 삭제 (#{r.get('issue_id')} {r.get('relation_type', 'blocks')} "
            f"#{r.get('issue_to_id')})")
    result["deleted_relations"] = deleted
    # ② Root 지도
    try:
        _write_root(rm, rid, body, new, notes + f"\n삭제한 관계: {deleted or '없음'}", log)
    except WayfinderTransportError as e:
        return _stopped(log, "Root 본문", str(e), [], **result)
    # ③ 노드 닫기 — 실패해도 되돌리지 않는다(지도는 이미 범위 밖이라 close_root 를 막지 않는다)
    try:
        out = rm.update_issue(nid, notes=f"웨이파인더 범위 밖 — {plan['reason']} (맵 Root #{rid})",
                              status_name=DONE, done_ratio=100)
    except Exception as e:                            # noqa: BLE001 — 지도는 이미 썼다, 크게 알리고 끝낸다
        out = f"[주의] 노드 닫기 예외 — {type(e).__name__}: {e}"
    if str(out).startswith("[주의]"):
        log(f"[주의] 중단 — 노드 닫기 #{nid}: {out} (지도는 이미 범위 밖 · 관계 삭제 {deleted or '없음'} · "
            f"되돌리지 않는다 — 노드 일감을 사람이 닫아야 한다)")
        return {"ok": False, "step": "노드 닫기", "why": str(out), "map_written": True, **result,
                "log": log.lines}
    log(f"쓰기 — 노드 #{nid} 「{DONE}」 마감 (범위 밖)")
    return {"ok": True, **result, "log": log.lines}


# ── 선점 · 재검증 완료 · Root 마감 ────────────────────────────────────────

def claim(root_id, node_id, owner, *, project="", rm=None, logf=None) -> dict:
    """Frontier 노드를 선점한다 — 담당을 적고 작업중으로. Redmine 담당자(assigned_to)는 바꾸지 않는다.

    `#1036` — **예정 노드(P<n>)면 이때 Redmine 일감을 만든다.** 순서: 노드 일감(부모 Root · Root 마일스톤 ·
    본문 = 요약 + 노드 표지) → 선행마다 blocks(선점은 Frontier 만 받으므로 선행은 모두 완료 = 일감 있음) →
    지도의 키를 #번호로 바꾸고 그 키를 가리키는 부모·선행도 바꾼다 → 작업중 → Root 본문. 응답의 `id` 가
    새 일감 번호, `key` 가 옛 예정 키다. 도중 실패는 되돌리지 않고 이미 만든 번호를 돌려준다.
    이미 번호가 있는 노드는 종전처럼 지도만 바꾼다."""
    log, rm = _log_of(logf), _port(rm)
    rid = _issue_id(root_id, "Root")
    nid = _node_ref(node_id, "노드")
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
        return _refuse(log, f"{MB.label(nid)} 는 Root #{rid} 지도의 노드가 아니다")
    if n.state != FRONTIER:
        return _refuse(log, f"{MB.label(nid)} 는 Frontier 가 아니다 (지금 {n.state}) — 선점하지 않는다")
    key, created = None, []
    if MB.is_planned(nid):
        planned_deps = [d for d in n.deps if MB.is_planned(d)]
        if planned_deps:                              # Frontier 면 선행은 완료 — 예정 노드는 완료일 수 없다
            return _refuse(log, f"{nid} 의 선행에 아직 일감이 없는 예정 노드가 있다: {', '.join(planned_deps)}")
        root = _get(rm, rid)
        new_id, why = _create_node_issue(rm, root_id=rid, title=n.title, type_=n.type, summary=n.summary,
                                         parent_id=rid, version=root.get("fixed_version") or "",
                                         project=project, log=log)
        if new_id is not None:
            created.append(new_id)
        if why:
            return _stopped(log, f"노드 생성 {nid}", why, created)
        for d in n.deps:
            why = _relate(rm, d, new_id, log)
            if why:
                return _stopped(log, f"관계 #{d}→#{new_id}", why, created)
        key = nid
        for x in block.nodes:                         # 키 → 번호 (자기 자신 · 부모 · 선행)
            if x.id == key:
                x.id = new_id
            if x.parent == key:
                x.parent = new_id
            x.deps = [new_id if d == key else d for d in x.deps]
        n, nid = block.node(new_id), new_id
        log(f"예정 노드 {key} → 일감 #{new_id}")
    n.owner, n.state = owner, WORKING
    new = compute_states(block)
    made = f"예정 노드 {key} → 일감 #{nid} 생성 · " if key else ""
    try:
        _write_root(rm, rid, body, new,
                    f"#{nid} 선점 — {made}담당 {owner} (Redmine 담당자는 바꾸지 않음)", log)
    except WayfinderTransportError as e:
        return _stopped(log, "Root 본문", str(e), created)
    return {"ok": True, "id": nid, "key": key, "created": created, "owner": owner, "state": WORKING,
            "log": log.lines}


def mark_verified(root_id, node_id, evidence, *, rm=None, logf=None) -> dict:
    """재검증 노드를 근거와 함께 완료로 되돌린다. 근거가 없으면 거절."""
    log, rm = _log_of(logf), _port(rm)
    rid = _issue_id(root_id, "Root")
    nid = _node_ref(node_id, "노드")
    if not str(evidence or "").strip():
        return _refuse(log, f"{MB.label(nid)} 재검증 근거(evidence)가 없다")
    body, block = _load(rm, rid)
    n = block.node(nid)
    if n is None:
        return _refuse(log, f"{MB.label(nid)} 는 Root #{rid} 지도의 노드가 아니다")
    if n.state != REVERIFY:
        return _refuse(log, f"{MB.label(nid)} 는 재검증 상태가 아니다 (지금 {n.state})")
    n.state = DONE
    new = compute_states(block)
    try:
        _write_root(rm, rid, body, new, f"{MB.label(nid)} 재검증 완료 — 근거: {evidence}", log)
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
    blockers = [f"{MB.label(n.id)} {n.title} — {n.state}" for n in sorted(block.nodes, key=lambda x: MB.id_key(x.id))
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
