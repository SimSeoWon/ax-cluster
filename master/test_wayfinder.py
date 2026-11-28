"""Wayfinder(`#982` T4) 계약 테스트 — [중요] **제안은 쓰지 않고, 지도와 Redmine 이 어긋나면 거절하고,
재검증은 경로의 조상·각 단계 형제까지만 번지는가.** 실 Redmine·네트워크 없이 메모리 대역으로 돈다.

[중요] 이 파일 전체가 **MCP 없이 모듈 함수를 직접 부른 실증**이다(C8 근거) — 대역 위에서
create_map → claim → sync → propose_node → register_node → mark_verified → close_root 를 끝까지 잇는다.

실행: .venv/bin/python master/test_wayfinder.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import map_block as MB               # noqa: E402
from master import wayfinder as WF               # noqa: E402

PASS = FAIL = 0
ROOT = 500
WRITES = ("update_issue", "create_issue", "create_relation", "delete_relation")


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _raises(fn, needle: str = "", cls=WF.WayfinderError) -> bool:
    try:
        fn()
    except cls as e:
        return needle in str(e)
    return False


class FakeRedmine:
    """메모리 Redmine — `master.redmine` 과 같은 이름·모양의 여섯 함수."""

    def __init__(self):
        self.issues: dict[int, dict] = {}
        self.relations: list[dict] = []
        self.calls: list[tuple] = []
        self.next_id = 1001
        self.next_rel = 1
        self.fail = {}                      # 함수 이름 → 몇 번째 호출부터 실패(1부터)
        self.counts: dict[str, int] = {}

    def add(self, iid, *, description="", status="신규", parent=None, fixed_version="마일스톤 7",
            subject=""):
        self.issues[iid] = {"description": description, "status": status, "parent": parent,
                            "fixed_version": fixed_version, "subject": subject or f"#{iid}",
                            "journals": []}

    def _tick(self, name) -> bool:
        self.counts[name] = self.counts.get(name, 0) + 1
        at = self.fail.get(name)
        return at is not None and self.counts[name] >= at

    def writes(self):
        return [c for c in self.calls if c[0] in WRITES]

    # ── 포트 ──
    def get_issue(self, issue_id, **_):
        self.calls.append(("get_issue", issue_id))
        iss = self.issues.get(int(issue_id))
        if iss is None:
            return {"error": f"#{issue_id} 없음 (404)"}
        return {"id": int(issue_id), **{k: (list(v) if k == "journals" else v) for k, v in iss.items()}}

    def update_issue(self, issue_id, *, notes="", status_name="", done_ratio=None, description="", **_):
        self.calls.append(("update_issue", issue_id, {"notes": notes, "status_name": status_name,
                                                      "done_ratio": done_ratio,
                                                      "description": description}))
        if self._tick("update_issue"):
            return "[주의] 레드마인 갱신 실패 — 대역"
        iss = self.issues[int(issue_id)]
        if description:
            iss["description"] = description
        if notes:
            iss["journals"].append({"notes": notes})
        if status_name:
            # `#982` 실측 — 열린 선행에 막힌 일감은 닫히지 않는다(#993 이 #992 가 닫힐 때까지 「신규」).
            # 실 `redmine.update_issue` 처럼 코멘트는 남고 상태만 미반영 — `[주의]` 로 말한다.
            open_blockers = sorted(r["issue_id"] for r in self.relations
                                   if r["issue_to_id"] == int(issue_id) and r["relation_type"] == "blocks"
                                   and (self.issues.get(r["issue_id"]) or {}).get("status") != "완료")
            if status_name == "완료" and open_blockers:
                return (f"[주의] #{issue_id} 상태 「{status_name}」 반영 안 됨 — 열린 선행 "
                        + ", ".join(f"#{b}" for b in open_blockers))
            iss["status"] = status_name
        return f"#{issue_id} 갱신"

    def create_issue(self, subject, description="", *, fixed_version="", parent_issue_id=None, **kw):
        self.calls.append(("create_issue", subject, {"description": description,
                                                     "fixed_version": fixed_version,
                                                     "parent_issue_id": parent_issue_id, **kw}))
        if self._tick("create_issue"):
            return {"error": "HTTP 500"}
        iid = self.next_id
        self.next_id += 1
        self.add(iid, description=description, parent=parent_issue_id, fixed_version=fixed_version,
                 subject=subject)
        return {"id": iid}

    def create_relation(self, issue_id, issue_to_id, *, relation_type="blocks", **_):
        self.calls.append(("create_relation", issue_id, issue_to_id))
        if self._tick("create_relation"):
            return {"ok": False, "error": "HTTP 422"}
        # `#982` T7 실측 — 실 Redmine 은 조상-후손 사이 관계를 422 로 거절한다. 대역도 같게 한다.
        if self._lineage(issue_id, issue_to_id):
            return {"ok": False, "error": f"관계 생성 실패 #{issue_id}→#{issue_to_id} — HTTP 422 — "
                                          "일감은 하위 일감과 연결할 수 없습니다."}
        rel = {"id": self.next_rel, "issue_id": issue_id, "issue_to_id": issue_to_id,
               "relation_type": relation_type}
        self.next_rel += 1
        self.relations.append(rel)
        return {"ok": True, "relation": dict(rel)}

    def _ancestors(self, iid):
        seen, cur = set(), (self.issues.get(iid) or {}).get("parent")
        while cur and cur not in seen:
            seen.add(cur)
            cur = (self.issues.get(cur) or {}).get("parent")
        return seen

    def _lineage(self, a, b):
        return a in self._ancestors(b) or b in self._ancestors(a)

    def list_relations(self, issue_id, **_):
        self.calls.append(("list_relations", issue_id))
        return {"relations": [dict(r) for r in self.relations
                              if issue_id in (r["issue_id"], r["issue_to_id"])]}

    def delete_relation(self, relation_id, **_):
        self.calls.append(("delete_relation", relation_id))
        self.relations = [r for r in self.relations if r["id"] != relation_id]
        return {"ok": True}


def _quiet():
    lines = []
    return lines, lines.append


SPECS = [
    {"key": "pre", "title": "사전조사 HUD", "type": "프리필", "parent": "Root", "deps": [],
     "summary": "HUD 기능 범위"},
    {"key": "hud", "title": "HUD 위젯", "type": "작업", "parent": "pre", "deps": ["pre"], "summary": ""},
    {"key": "inv", "title": "인벤토리 연결", "type": "작업", "parent": "pre", "deps": ["pre"],
     "summary": ""},
    {"key": "ver", "title": "HUD 인벤토리 결합 검증", "type": "검증", "parent": "Root",
     "deps": ["hud", "inv"], "summary": ""},
]


def _fresh(body="## 요청\n\n원문\n"):
    rm = FakeRedmine()
    rm.add(ROOT, description=body, subject="Root")
    return rm


def _build(rm, destination, specs, *, fog=(), out_of_scope=(), logf=None):
    """`#1028`·`#1036` — 실제 사용 순서: 선행 없는 첫 노드로 맵을 만들고, 나머지는 제안·등록으로 키운다.

    `#1036` 부터 노드는 **예정 키(P<n>)로 지도에만** 오른다 — 돌려주는 `created` 는 key → 예정 키다.
    Redmine 일감은 선점(`claim`) 때 생긴다.
    """
    logf = logf or _quiet()[1]
    first = [x for x in specs if not x.get("deps")]
    out = WF.create_map(ROOT, destination, first, fog=list(fog), out_of_scope=list(out_of_scope), confirm=True,
                        user_answer="좋아 등록해", rm=rm, logf=logf)
    assert out["ok"], out
    c = dict(out["created"])
    for x in specs:
        if not x.get("deps"):
            continue
        parent = MB.ROOT if x.get("parent", MB.ROOT) == MB.ROOT else c[x["parent"]]
        pr = WF.propose_node(ROOT, x["title"], x["type"], parent, deps=[c[d] for d in x["deps"]],
                             summary=x.get("summary", ""), rm=rm, logf=logf)
        reg = WF.register_node(ROOT, pr["proposal"], user_answer="응", rm=rm, logf=logf)
        assert reg["ok"], reg
        c[x["key"]] = reg["id"]
    return c


def _legacy(rm, destination, specs, *, fog=(), out_of_scope=()):
    """`#1036` 이전 모양의 지도 — 모든 노드가 처음부터 Redmine 일감(번호)이다(#741·#1008 같은 기존 맵).

    도구가 더는 이렇게 만들지 않으므로 검사가 직접 깐다 — 이 지도에 기대는 검사들이 곧 **하위 호환 검사**다.
    Root 본문은 대역에 직접 적는다(쓰기 계수에 들어가지 않는다 — 종전 `_made` 뒤 계수와 같은 기준).
    """
    lg = WF._log_of(lambda *_: None)
    order = WF._validate_specs(specs, lg)
    version = rm.issues[ROOT]["fixed_version"]
    ids = {}
    for x in order:
        nid, why = WF._create_node_issue(rm, root_id=ROOT, title=x["title"], type_=x["type"], summary=x["summary"],
                                         parent_id=ROOT, version=version, project="", log=lg)
        assert nid and not why, why
        ids[x["key"]] = nid
    for x in order:
        for d in x["deps"]:
            assert not WF._relate(rm, ids[d], ids[x["key"]], lg)
    block = WF.compute_states(WF._block_from(destination, order, ids, fog, out_of_scope))
    rm.issues[ROOT]["description"] = MB.put(rm.issues[ROOT]["description"], block)
    return ids


FIRST = [x for x in SPECS if not x["deps"]]                       # 첫 노드(선행 없음) — pre 하나
FIRST2 = FIRST + [{"key": "sav", "title": "저장 형식 조사", "type": "프리필", "parent": "Root", "deps": [],
                   "summary": "저장 범위"}]                        # 서로 의존 없는 첫 노드 둘


def _made(rm=None):
    """번호만 있는 기존 모양의 지도(하위 호환) — 노드 4개 · blocks 4개 · 안개 하나."""
    rm = rm or _fresh()
    return rm, _legacy(rm, "HUD 를 붙인다", SPECS, fog=["저장 형식"])


# ── create_map ─────────────────────────────────────────────────────────────

def test_create_map_preview():
    rm = _fresh()
    lines, logf = _quiet()
    out = WF.create_map(ROOT, "HUD 를 붙인다", FIRST2, rm=rm, logf=logf)
    check("미리보기 ok", out["ok"] and out["confirmed"] is False)
    check("미리보기 쓰기 0건", rm.writes() == [], str(rm.writes()))
    check("미리보기 영역 글", out["preview"].startswith("<!-- ax:map:begin v=1 -->")
          and "<pre>" in out["preview"])
    check("#1036 예정 키 P1..Pn", out["temp_ids"] == {"pre": "P1", "sav": "P2"}, str(out["temp_ids"]))
    check("#1036 예정 쓰기 = Root 본문 하나(일감 0)", len(out["writes"]) == 1
          and out["writes"][0].startswith("update_issue") and "P1, P2" in out["writes"][0], str(out["writes"]))
    check("미리보기 로그", any("쓰기 0건" in x for x in lines))
    parsed = MB.parse(out["preview"])
    check("미리보기 왕복", parsed is not None and [n.id for n in parsed.nodes] == ["P1", "P2"])


def test_create_map_confirm():
    """`#1036` — 맵 등록은 Root 본문만 쓴다: 첫 노드는 예정 키로 지도에만, Redmine 일감 0."""
    rm = _fresh()
    lines, logf = _quiet()
    out = WF.create_map(ROOT, "HUD 를 붙인다", FIRST2, fog=["저장 형식"], confirm=True,
                        user_answer="좋아", rm=rm, logf=logf)
    check("등록 ok", out["ok"] and out["confirmed"], str(out))
    check("#1036 created = 예정 키", out["created"] == {"pre": "P1", "sav": "P2"}, str(out["created"]))
    check("#1036 일감 0 · 관계 0", not any(x[0] in ("create_issue", "create_relation") for x in rm.calls)
          and out["relations"] == [], str(rm.calls))
    check("#1036 쓰기는 Root 하나", [x[0] for x in rm.writes()] == ["update_issue"] and rm.writes()[0][1] == ROOT,
          str(rm.writes()))
    check("첫 노드 둘 다 Frontier", sorted(f["id"] for f in out["frontier"]) == ["P1", "P2"], str(out["frontier"]))
    body = rm.issues[ROOT]["description"]
    check("영역 밖 보존", body.startswith("## 요청\n\n원문\n"))
    block = MB.parse(body)
    check("지도 기록", block is not None and [n.id for n in block.nodes] == ["P1", "P2"] and block.fog == ["저장 형식"])
    check("다이어그램", block.diagram.startswith("<pre>") and "P1 사전조사 HUD" in block.diagram)
    check("등록 노트", "Redmine 일감은 선점 때" in rm.issues[ROOT]["journals"][-1]["notes"])
    check("#1036 등록 직후 대조 통과(예정 노드는 일감 대조 안 함)", WF.check(ROOT, rm=rm, logf=_quiet()[1])["ok"])
    # 나머지는 제안·등록으로 자란다 — 역시 일감 0
    rm = _fresh()
    c = _build(rm, "HUD 를 붙인다", SPECS, fog=["저장 형식"])
    check("#1036 키우기도 일감 0", not any(x[0] in ("create_issue", "create_relation") for x in rm.calls))
    check("#1036 등록 키 차례", c == {"pre": "P1", "hud": "P2", "inv": "P3", "ver": "P4"}, str(c))
    block = MB.parse(rm.issues[ROOT]["description"])
    hb = block.node("P2")
    check("파생 부모·선행은 지도 표에(예정 키)", hb.parent == "P1" and hb.deps == ["P1"]
          and block.node("P4").deps == ["P2", "P3"])
    st = {n.id: n.state for n in block.nodes}
    check("초기 상태", st["P1"] == "Frontier" and st["P2"] == "차단" and st["P4"] == "차단", str(st))
    check("Frontier 결과", [f["id"] for f in WF.frontier(ROOT, rm=rm)["frontier"]] == ["P1"])
    check("대조 통과", WF.check(ROOT, rm=rm, logf=_quiet()[1])["ok"])


def test_create_map_refusals():
    rm = _fresh()
    lines, logf = _quiet()
    out = WF.create_map(ROOT, "목적", FIRST, confirm=True, user_answer="  ", rm=rm, logf=logf)
    check("답 없으면 거절", not out["ok"] and out["refused"] and rm.writes() == [])
    check("거절 로그", any(x.startswith("거절") for x in lines))
    rm2, _ = _made()
    n = len(rm2.writes())
    out = WF.create_map(ROOT, "목적", FIRST, confirm=True, user_answer="응", rm=rm2, logf=_quiet()[1])
    check("두 번째 지도 거절", not out["ok"] and "이미" in out["why"] and len(rm2.writes()) == n)
    out = WF.create_map(ROOT, "목적", FIRST, rm=rm2, logf=_quiet()[1])
    check("두 번째 지도는 미리보기도 거절", not out["ok"])
    bad = [dict(SPECS[0], key="a", deps=["b"]), dict(SPECS[1], key="b", parent="Root", deps=["a"])]
    check("선행 순환", _raises(lambda: WF.create_map(ROOT, "목적", bad, rm=_fresh(), logf=_quiet()[1]),
                           "순환"))
    bad = [dict(SPECS[0], key="a", parent="b"), dict(SPECS[1], key="b", parent="a", deps=[])]
    check("부모 순환", _raises(lambda: WF.create_map(ROOT, "목적", bad, rm=_fresh(), logf=_quiet()[1]),
                           "순환"))
    check("모르는 선행", _raises(lambda: WF.create_map(
        ROOT, "목적", [dict(SPECS[0], deps=["x"])], rm=_fresh(), logf=_quiet()[1]), "선행"))
    check("key 중복", _raises(lambda: WF.create_map(
        ROOT, "목적", [SPECS[0], SPECS[0]], rm=_fresh(), logf=_quiet()[1]), "겹친다"))
    check("모르는 타입", _raises(lambda: WF.create_map(
        ROOT, "목적", [dict(SPECS[0], type="설계")], rm=_fresh(), logf=_quiet()[1]), "타입"))
    # Root 쓰기 실패 — 일감이 없으니 남는 것도 없다
    rm3 = _fresh()
    rm3.fail["update_issue"] = 1
    out = WF.create_map(ROOT, "목적", FIRST2, confirm=True, user_answer="응", rm=rm3, logf=_quiet()[1])
    check("#1036 Root 쓰기 실패 보고 · 일감 0", not out["ok"] and out["step"] == "Root 본문" and out["created"] == []
          and not any(x[0] == "create_issue" for x in rm3.calls), str(out))


def test_claim_creates_issue_1036():
    """`#1036` — 예정 노드는 선점 때 일감이 된다: 일감 → 선행 blocks → 키→번호(부모·선행) → 작업중."""
    rm = _fresh()
    c = _build(rm, "HUD 를 붙인다", SPECS, fog=["저장 형식"])
    lines, logf = _quiet()
    before = len(rm.writes())
    out = WF.claim(ROOT, "P2", "codex", rm=rm, logf=logf)
    check("#1036 Frontier 아닌 예정 노드 선점 거절 · 쓰기 0", not out["ok"] and "Frontier 가 아니다" in out["why"]
          and len(rm.writes()) == before, str(out))
    n0 = len(rm.writes())
    out = WF.claim(ROOT, "P1", "codex", rm=rm, logf=logf)
    pre = out["id"]
    check("#1036 선점 → 새 일감 번호 · 옛 키", out["ok"] and isinstance(pre, int) and out["key"] == "P1"
          and out["created"] == [pre], str(out))
    iss = rm.issues[pre]
    mk = MB.parse_node(iss["description"])
    check("#1036 일감: Redmine 부모 Root · 표지 · 요약 · 마일스톤", iss["parent"] == ROOT and mk.root == ROOT
          and mk.type == "프리필" and iss["description"].startswith("HUD 기능 범위")
          and iss["fixed_version"] == "마일스톤 7", str(iss))
    blk = MB.parse(rm.issues[ROOT]["description"])
    check("#1036 지도: 키→번호 · 자식의 부모·선행도", blk.node("P1") is None and blk.node(pre).state == "작업중"
          and blk.node(pre).owner == "codex" and blk.node("P2").parent == pre and blk.node("P2").deps == [pre]
          and blk.node("P3").deps == [pre], str(blk.nodes))
    check("#1036 첫 노드는 관계 0", rm.relations == [])
    check("#1036 선점 노트", "예정 노드 P1 → 일감" in rm.issues[ROOT]["journals"][-1]["notes"])
    check("#1036 선점 뒤 대조 통과", WF.check(ROOT, rm=rm, logf=_quiet()[1])["ok"])
    check("#1036 쓰기 = 일감 생성 + Root", [x[0] for x in rm.writes()[n0:]] == ["create_issue", "update_issue"],
          str(rm.writes()[n0:]))
    # 선행이 끝나면 자식이 Frontier → 선점 때 선행 blocks
    rm.issues[pre]["status"] = "완료"
    check("마감 동기화", WF.on_node_closed(pre, rm=rm, logf=logf)["changed"])
    out = WF.claim(ROOT, "P2", "claude", rm=rm, logf=logf)
    hud = out["id"]
    check("#1036 선행 blocks 를 선점 때 건다", out["ok"] and (pre, hud) in
          {(r["issue_id"], r["issue_to_id"]) for r in rm.relations}, str(rm.relations))
    blk = MB.parse(rm.issues[ROOT]["description"])
    check("#1036 검증 노드 선행 칸이 번호·키 섞임", blk.node("P4").deps == [hud, "P3"], str(blk.node("P4").deps))
    check("#1036 섞인 지도 대조 통과", WF.check(ROOT, rm=rm, logf=_quiet()[1])["ok"])
    check("#1036 번호 노드 선점은 종전대로(일감 안 만듦)",
          WF.claim(ROOT, hud, "x", rm=rm, logf=logf)["ok"] is False)       # 이미 작업중 — Frontier 아님
    # 실패 — 일감 생성 실패면 지도 무변경
    rm2 = _fresh()
    _build(rm2, "목적", FIRST)
    before = rm2.issues[ROOT]["description"]
    rm2.fail["create_issue"] = 1
    out = WF.claim(ROOT, "P1", "codex", rm=rm2, logf=_quiet()[1])
    check("#1036 일감 생성 실패 → 보고 · 지도 무변경", not out["ok"] and "노드 생성" in out["step"]
          and rm2.issues[ROOT]["description"] == before, str(out))
    # 실패 — 관계 실패면 만든 번호를 돌려주고 지도는 그대로
    rm3 = _fresh()
    c3 = _build(rm3, "목적", SPECS)
    p1 = WF.claim(ROOT, "P1", "a", rm=rm3, logf=_quiet()[1])["id"]
    rm3.issues[p1]["status"] = "완료"
    WF.on_node_closed(p1, rm=rm3, logf=_quiet()[1])
    rm3.fail["create_relation"] = 1
    before = rm3.issues[ROOT]["description"]
    out = WF.claim(ROOT, "P2", "b", rm=rm3, logf=_quiet()[1])
    check("#1036 관계 실패 → 만든 번호 보고 · 지도 무변경", not out["ok"] and out["step"].startswith("관계")
          and len(out["created"]) == 1 and rm3.issues[ROOT]["description"] == before, str(out))


def test_prepare_distributed_ticket():
    rm = _fresh()
    _build(rm, "목적", SPECS)
    _, logf = _quiet()
    before = len(rm.writes())
    blocked = WF.claim(ROOT, "P2", prepare_only=True, rm=rm, logf=logf)
    check("분산 준비: 차단 노드는 일감을 만들지 않는다",
          not blocked["ok"] and len(rm.writes()) == before, str(blocked))
    prepared = WF.claim(ROOT, "P1", prepare_only=True, rm=rm, logf=logf)
    issue_id = prepared["id"]
    block = WF.load(ROOT, rm=rm)
    node = block.node(issue_id)
    check("분산 준비: 일감 번호를 받고 노드는 담당 없이 Frontier",
          prepared["created"] == [issue_id] and node.state == "Frontier" and not node.owner, str(prepared))
    before = len(rm.writes())
    again = WF.claim(ROOT, issue_id, prepare_only=True, rm=rm, logf=logf)
    check("분산 준비: 번호가 있는 Frontier는 기존 일감 재사용",
          again["ok"] and again["id"] == issue_id and not again["created"] and len(rm.writes()) == before,
          str(again))
    solo = WF.claim(ROOT, issue_id, "codex", rm=rm, logf=logf)
    check("분산 준비 뒤에도 같은 번호로 단독 선점 가능",
          solo["ok"] and solo["state"] == "작업중" and not solo["created"], str(solo))


def test_planned_node_out_and_drift_1036():
    """`#1036` — 예정 노드를 범위 밖으로 돌리면 지도만 쓴다 · 예정 노드가 착수 뒤 상태면 대조 차이."""
    rm = _fresh()
    _build(rm, "HUD 를 붙인다", SPECS)
    n0 = len(rm.writes())
    p = WF.propose_edit(ROOT, "node_out", target="P4", reason="이번엔 검증 생략", rm=rm, logf=_quiet()[1])
    out = WF.apply_edit(ROOT, p["proposal"], user_answer="응", rm=rm, logf=_quiet()[1])
    check("#1036 예정 node_out ok · 쓰기는 Root 하나", out["ok"] and out["deleted_relations"] == []
          and [x[0] for x in rm.writes()[n0:]] == ["update_issue"] and rm.writes()[n0][1] == ROOT, str(out))
    blk = MB.parse(rm.issues[ROOT]["description"])
    check("#1036 표에서 빠지고 범위 밖에", blk.node("P4") is None
          and any(x.startswith("P4 HUD 인벤토리 결합 검증") for x in blk.out_of_scope), str(blk.out_of_scope))
    blk.node("P2").state = "작업중"                    # 사람이 손으로 고친 흔적 — 일감 없는 작업중
    rm.issues[ROOT]["description"] = MB.put(rm.issues[ROOT]["description"], blk)
    out = WF.check(ROOT, rm=rm, logf=_quiet()[1])
    check("#1036 일감 없는 작업중 → 대조 차이", not out["ok"]
          and any("P2: 예정 노드" in d for d in out["differences"]), str(out))


def test_first_nodes_only_1028():
    """`#1028` 재현 — 맵은 목적지 + 지금 집을 수 있는 첫 노드로 시작한다. 선행 사슬·빈 맵은 처음에 거절."""
    for name, nodes in (("① 선행 사슬 4노드(#741·#1008 꼴)", SPECS), ("② 노드 0개", [])):
        for confirm in (False, True):
            rm = _fresh()
            out = WF.create_map(ROOT, "목적", nodes, confirm=confirm, user_answer="응", rm=rm, logf=_quiet()[1])
            check(f"#1028 {name} 거절(confirm={confirm})", not out["ok"] and out.get("refused")
                  and rm.writes() == [], str(out))
    rm = _fresh()
    out = WF.create_map(ROOT, "목적", SPECS, rm=rm, logf=_quiet()[1])
    check("#1028 거절 사유가 걸린 노드·다음 길을 말한다", all(k in out["why"] for k in ("hud", "inv", "ver"))
          and "register_node" in out["why"], out["why"])
    out = WF.create_map(ROOT, "목적", [], rm=_fresh(), logf=_quiet()[1])
    check("#1028 빈 맵 사유", "첫 노드" in out["why"], out["why"])
    for name, nodes in (("③ 선행 없는 1노드", FIRST), ("④ 선행 없는 2노드", FIRST2)):
        rm = _fresh()
        out = WF.create_map(ROOT, "목적", nodes, confirm=True, user_answer="응", rm=rm, logf=_quiet()[1])
        check(f"#1028 {name} 통과·전부 Frontier", out["ok"] and len(out["frontier"]) == len(nodes), str(out))
    # 형식 오류는 규칙 판정보다 먼저 — 순환·모르는 선행은 종전처럼 WayfinderError
    check("#1028 형식 오류가 먼저", _raises(lambda: WF.create_map(
        ROOT, "목적", [dict(SPECS[0], deps=["x"])], rm=_fresh(), logf=_quiet()[1]), "선행"))


def test_title_validation():
    for bad in ("a|b", "x</pre>", "<!-- y", "두\n줄", " 공백"):
        check(f"제목 거절 {bad!r}", _raises(lambda b=bad: WF.create_map(
            ROOT, "목적", [dict(SPECS[0], title=b)], rm=_fresh(), logf=_quiet()[1]), "제목"))
    blk = MB.MapBlock("목적", "", [MB.MapNode(1, "a</pre>b", "작업", None, "대기")], [], [])
    check("compute_states 제목 거절 — 노드 이름", _raises(lambda: WF.compute_states(blk), "#1 제목"))


# ── 순수 상태 계산 ─────────────────────────────────────────────────────────

def test_compute_states():
    N = MB.MapNode
    blk = MB.MapBlock("목적", "", [
        N(1, "가", "프리필", None, "완료"),
        N(2, "나", "작업", None, "대기", [1]),
        N(3, "다", "작업", None, "Frontier", [2]),
        N(4, "라", "작업", None, "차단", [1], "codex"),
        N(5, "마", "작업", None, "작업중", [2], "x"),
        N(6, "바", "작업", None, "재검증", [1]),
        N(7, "사", "검증", None, "대기", [1, 6]),
        N(8, "아", "작업", None, "차단", []),
    ], [], [])
    out = WF.compute_states(blk)
    st = {n.id: n.state for n in out.nodes}
    check("선행 완료 → Frontier", st[2] == "Frontier" and st[8] == "Frontier")
    check("선행 미완 → 차단", st[3] == "차단")
    check("담당 있으면 대기", st[4] == "대기")
    check("작업중·완료·재검증 그대로", st[5] == "작업중" and st[1] == "완료" and st[6] == "재검증")
    check("재검증 선행은 미완", st[7] == "차단")
    check("다이어그램", out.diagram.startswith("<pre>"))
    check("원본 불변", blk.nodes[1].state == "대기" and blk.diagram == "")


# ── check ──────────────────────────────────────────────────────────────────

def test_check():
    rm, c = _made()
    rm.issues[c["hud"]]["parent"] = c["pre"]
    out = WF.check(ROOT, rm=rm, logf=_quiet()[1])
    check("부모 불일치", not out["ok"] and any(f"#{c['hud']}: Redmine 부모" in d for d in out["differences"]))
    rm, c = _made()
    rm.relations = [r for r in rm.relations if not (r["issue_id"] == c["hud"] and r["issue_to_id"] == c["ver"])]
    rm.create_relation(c["hud"], c["inv"])
    out = WF.check(ROOT, rm=rm, logf=_quiet()[1])
    d = " / ".join(out["differences"])
    check("없는 관계", f"Redmine 에 없는 선행 관계 #{c['hud']}→#{c['ver']}" in d, d)
    check("남는 관계", f"지도에 없는 선행 관계 #{c['hud']}→#{c['inv']}" in d, d)
    rm, c = _made()
    rm.issues[c["ver"]]["description"] = "표지 지움"
    out = WF.check(ROOT, rm=rm, logf=_quiet()[1])
    check("표지 없음", any("표지가 없다" in x for x in out["differences"]))
    rm.issues[c["ver"]]["description"] = MB.put_node("", MB.NodeMarker(ROOT, "작업"))
    out = WF.check(ROOT, rm=rm, logf=_quiet()[1])
    check("표지 타입 불일치", any("type=작업" in x for x in out["differences"]))
    rm, _ = _made()
    n = len(rm.writes())
    WF.check(ROOT, rm=rm, logf=_quiet()[1])
    check("check 는 읽기만", len(rm.writes()) == n)
    check("지도 없음", _raises(lambda: WF.load(ROOT, rm=_fresh()), "지도 영역이 없다"))
    check("읽기 실패", _raises(lambda: WF.load(999, rm=_fresh()), "읽지 못했다", WF.WayfinderTransportError))


# ── sync / on_node_closed ─────────────────────────────────────────────────

def test_sync():
    rm, c = _made()
    lines, logf = _quiet()
    n0 = len(rm.writes())
    out = WF.sync(ROOT, closed_node=c["pre"], rm=rm, logf=logf)
    check("Redmine 미완료면 거절", not out["ok"] and "「신규」" in out["why"] and len(rm.writes()) == n0)
    rm.issues[c["pre"]]["status"] = "완료"
    out = WF.sync(ROOT, closed_node=c["pre"], note="pre 마감", rm=rm, logf=logf)
    check("sync ok · 바뀜", out["ok"] and out["changed"])
    check("의존 노드 Frontier", sorted(f["id"] for f in out["frontier"]) == sorted([c["hud"], c["inv"]]))
    st = {n.id: n.state for n in MB.parse(rm.issues[ROOT]["description"]).nodes}
    check("pre 완료 기록", st[c["pre"]] == "완료" and st[c["ver"]] == "차단")
    check("노트", rm.issues[ROOT]["journals"][-1]["notes"] == "pre 마감")
    n1 = len(rm.writes())
    out = WF.sync(ROOT, rm=rm, logf=logf)
    check("변화 없으면 안 씀", out["ok"] and not out["changed"] and len(rm.writes()) == n1)
    rm.issues[c["inv"]]["parent"] = None
    out = WF.sync(ROOT, rm=rm, logf=logf)
    check("대조 실패면 거절", not out["ok"] and out["differences"] and len(rm.writes()) == n1)
    check("거절 로그", any(x.startswith("거절") for x in lines))


def test_sync_keeps_reverify():
    rm, c = _made()
    blk = MB.parse(rm.issues[ROOT]["description"])
    blk.node(c["pre"]).state = "재검증"
    blk.node(c["hud"]).state = "완료"
    rm.issues[ROOT]["description"] = MB.put(rm.issues[ROOT]["description"], blk)
    rm.issues[c["hud"]]["status"] = "완료"
    rm.issues[c["pre"]]["status"] = "완료"
    out = WF.sync(ROOT, closed_node=c["hud"], rm=rm, logf=_quiet()[1])
    st = {n.id: n.state for n in MB.parse(rm.issues[ROOT]["description"]).nodes}
    check("다른 닫힌 노드의 재검증 유지", out["ok"] and st[c["pre"]] == "재검증")


def test_on_node_closed():
    rm, c = _made()
    rm.add(77, description="표지 없는 일감")
    n = len(rm.writes())
    lines, logf = _quiet()
    out = WF.on_node_closed(77, rm=rm, logf=logf)
    check("표지 없음 → 건너뜀", out == {"ok": True, "skipped": "노드 표지 없음", "log": lines}
          and len(rm.writes()) == n)
    # `#1027` — 본문이 표지 문자열을 인용만 했으면(#1024 마감 거절과 같은 꼴) 표지 없음으로 건너뛴다
    rm.add(78, description="## 문제\n본문 `<!-- ax:node v=1 root=741 type=작업 -->` 표지\n\n"
                           "## 스펙\n`<!-- ax:node v=1 root=741 type=작업 -->`\n")
    out = WF.on_node_closed(78, rm=rm, logf=logf)
    check("#1027 인용만 한 본문 → 표지 없음 건너뜀", out.get("ok") is True and out.get("skipped") == "노드 표지 없음"
          and len(rm.writes()) == n, str(out))
    rm.issues[c["pre"]]["status"] = "완료"
    out = WF.on_node_closed(c["pre"], rm=rm, logf=logf)
    check("표지 있음 → sync", out["ok"] and out["changed"])
    check("마감 노트", rm.issues[ROOT]["journals"][-1]["notes"] == f"노드 #{c['pre']} 마감 — 맵 갱신")


# ── propose / register ────────────────────────────────────────────────────

def _tree():
    """Root ─ A(완료) ─ A1(완료) ─ A1a(완료, 새 노드의 부모)
                    └ A2(완료) ─ A2x(완료)   ← 형제의 자식: 재검증 제외
                    └ A3(대기)
            └ B(완료) ─ Bx(완료)              ← Root 직속 형제의 자식: 제외
    """
    specs = [
        {"key": "A", "title": "전투 시스템 조사", "type": "프리필", "parent": "Root"},
        {"key": "B", "title": "저장 형식 조사", "type": "프리필", "parent": "Root"},
        {"key": "A1", "title": "체력 컴포넌트", "type": "작업", "parent": "A", "deps": ["A"]},
        {"key": "A2", "title": "데미지 계산", "type": "작업", "parent": "A", "deps": ["A"]},
        {"key": "A3", "title": "피격 이펙트", "type": "작업", "parent": "A", "deps": ["A2"]},
        {"key": "A1a", "title": "체력 UI 표시", "type": "작업", "parent": "A1", "deps": ["A1"]},
        {"key": "A2x", "title": "데미지 체력 감소 로그", "type": "작업", "parent": "A2", "deps": ["A2"]},
        {"key": "Bx", "title": "체력 저장", "type": "작업", "parent": "B", "deps": ["B"]},
    ]
    rm = _fresh()
    c = _legacy(rm, "전투", specs)
    blk = MB.parse(rm.issues[ROOT]["description"])
    for k in ("A", "B", "A1", "A2", "A1a", "A2x", "Bx"):
        blk.node(c[k]).state = "완료"
        rm.issues[c[k]]["status"] = "완료"
    rm.issues[ROOT]["description"] = MB.put(rm.issues[ROOT]["description"], WF.compute_states(blk))
    return rm, c


def test_propose_node():
    rm, c = _tree()
    n = len(rm.writes())
    lines, logf = _quiet()
    out = WF.propose_node(ROOT, "체력 회복", "작업", c["A1a"], deps=[c["A1a"]], summary="체력 회복 아이템",
                          rm=rm, logf=logf)
    check("제안 쓰기 0건", out["ok"] and len(rm.writes()) == n)
    check("경로", out["path"] == [c["A1a"], c["A1"], c["A"], ROOT], str(out["path"]))
    want = sorted([c["A1a"], c["A1"], c["A"], c["A2"], c["B"]])
    check("재검증 = 조상 + 각 단계 형제(완료)", out["reverify"] == want, f"{out['reverify']} ≠ {want}")
    check("형제의 자식 제외", c["A2x"] not in out["reverify"] and c["Bx"] not in out["reverify"])
    check("완료 아닌 형제 제외", c["A3"] not in out["reverify"])
    dup = {d["id"]: d for d in out["duplicates"]}
    # 단계 = 형제 묶음의 깊이 — 0 은 새 노드의 형제(A1a 의 자식, 없음), 1 은 A1 의 자식(A1a),
    # 2 는 A 의 자식(A1·A2·A3), 3 은 Root 직속(A·B)
    check("모든 단계 중복 후보", c["A1"] in dup and dup[c["A1"]]["level"] == 2
          and dup[c["A1a"]]["level"] == 1, str(out["duplicates"]))
    check("Root 단계 후보", all(d["level"] <= 3 for d in out["duplicates"]))
    check("하위 나무는 후보 아님", c["A2x"] not in dup and c["Bx"] not in dup)
    check("점수 내림차순", [d["score"] for d in out["duplicates"]]
          == sorted((d["score"] for d in out["duplicates"]), reverse=True))
    check("점수 > 0 만", all(d["score"] > 0 for d in out["duplicates"]))
    check("제안 로그", any("쓰기 0건" in x for x in lines))
    out2 = WF.propose_node(ROOT, "새 축", "프리필", "Root", rm=rm, logf=logf)
    check("Root 직속 제안 경로", out2["path"] == [ROOT]
          and out2["reverify"] == sorted([c["A"], c["B"]]))
    check("모르는 부모", _raises(lambda: WF.propose_node(ROOT, "x", "작업", 9999, rm=rm, logf=logf), "부모"))
    check("제목 검사", _raises(lambda: WF.propose_node(ROOT, "x|y", "작업", "Root", rm=rm, logf=logf), "제목"))


def test_register_node():
    rm, c = _tree()
    p = WF.propose_node(ROOT, "체력 회복", "작업", c["A1a"], deps=[c["A1a"]], rm=rm, logf=_quiet()[1])
    n = len(rm.writes())
    lines, logf = _quiet()
    out = WF.register_node(ROOT, p["proposal"], user_answer="", rm=rm, logf=logf)
    check("답 없으면 거절", not out["ok"] and out["refused"] and len(rm.writes()) == n)
    out = WF.register_node(ROOT, p["proposal"], user_answer="등록해", rm=rm, logf=logf)
    check("등록 ok", out["ok"], str(out))
    new = out["id"]
    check("예정 키 · 등록 시 일감 없음", MB.is_planned(new) and new not in rm.issues)
    check("등록 시 선행 관계 없음", not any(r["issue_to_id"] == new for r in rm.relations))
    nb = MB.parse(rm.issues[ROOT]["description"]).node(new)
    check("파생 부모·선행은 지도 표에", nb.parent == c["A1a"] and nb.deps == [c["A1a"]])
    st = {x.id: x.state for x in MB.parse(rm.issues[ROOT]["description"]).nodes}
    check("재검증 표시", all(st[i] == "재검증" for i in p["reverify"]))
    check("하위 나무 유지", st[c["A2x"]] == "완료" and st[c["Bx"]] == "완료")
    check("새 노드 차단(선행 재검증)", st[new] == "차단")
    notes = {i: [j["notes"] for j in rm.issues[i]["journals"]] for i in p["reverify"]}
    check("재검증 노트", all(f"{new} 추가로 재검증 대상 — 맵 Root #{ROOT}" in v for v in notes.values()))
    check("등록 뒤 대조 통과", WF.check(ROOT, rm=rm, logf=_quiet()[1])["ok"])
    rm.issues[c["A3"]]["parent"] = None
    n = len(rm.writes())
    out = WF.register_node(ROOT, p["proposal"], user_answer="응", rm=rm, logf=logf)
    check("대조 실패면 거절", not out["ok"] and out["differences"] and len(rm.writes()) == n)


# ── claim / mark_verified / close_root ───────────────────────────────────

def test_claim():
    rm, c = _made()
    lines, logf = _quiet()
    out = WF.claim(ROOT, c["hud"], "codex", rm=rm, logf=logf)
    check("Frontier 아니면 거절", not out["ok"] and "Frontier 가 아니다" in out["why"])
    out = WF.claim(ROOT, c["pre"], "codex", rm=rm, logf=logf)
    n = MB.parse(rm.issues[ROOT]["description"]).node(c["pre"])
    check("선점", out["ok"] and n.state == "작업중" and n.owner == "codex")
    check("선점 노트", "Redmine 담당자는 바꾸지 않음" in rm.issues[ROOT]["journals"][-1]["notes"])
    check("Redmine 담당 불변", not any(x[0] == "update_issue" and x[1] == c["pre"] for x in rm.calls))
    check("빈 담당", _raises(lambda: WF.claim(ROOT, c["ver"], "", rm=rm, logf=logf), "담당"))


def test_mark_verified():
    rm, c = _tree()
    p = WF.propose_node(ROOT, "체력 회복", "작업", c["A1a"], deps=[c["A1a"]], rm=rm, logf=_quiet()[1])
    WF.register_node(ROOT, p["proposal"], user_answer="응", rm=rm, logf=_quiet()[1])
    lines, logf = _quiet()
    out = WF.mark_verified(ROOT, c["A1"], "", rm=rm, logf=logf)
    check("근거 없으면 거절", not out["ok"] and "근거" in out["why"])
    out = WF.mark_verified(ROOT, c["A3"], "x", rm=rm, logf=logf)
    check("재검증 아니면 거절", not out["ok"])
    out = WF.mark_verified(ROOT, c["A1"], "체력 테스트 통과", rm=rm, logf=logf)
    st = MB.parse(rm.issues[ROOT]["description"]).node(c["A1"]).state
    check("재검증 → 완료", out["ok"] and st == "완료")
    check("근거 노트", "체력 테스트 통과" in rm.issues[ROOT]["journals"][-1]["notes"])


def test_close_root():
    rm, c = _made()
    lines, logf = _quiet()
    out = WF.close_root(ROOT, rm=rm, logf=logf)
    check("미리보기 막는 것", out["ok"] and not out["confirmed"] and not out["ready"]
          and len(out["blockers"]) == 5)            # 노드 4 + 안개 1
    n = len(rm.writes())
    out = WF.close_root(ROOT, confirm=True, user_answer="닫아", rm=rm, logf=logf)
    check("막는 것 있으면 거절", not out["ok"] and len(rm.writes()) == n and out["blockers"])
    blk = MB.parse(rm.issues[ROOT]["description"])
    for x in blk.nodes:
        x.state = "완료"
    blk.fog = []
    rm.issues[ROOT]["description"] = MB.put(rm.issues[ROOT]["description"], blk)
    out = WF.close_root(ROOT, confirm=True, user_answer="", rm=rm, logf=logf)
    check("답 없으면 거절", not out["ok"] and "user_answer" in out["why"])
    out = WF.close_root(ROOT, confirm=False, rm=rm, logf=logf)
    check("준비됨 미리보기", out["ready"] and len(rm.writes()) == n)
    out = WF.close_root(ROOT, confirm=True, user_answer="닫아", rm=rm, logf=logf)
    last = rm.calls[-1]
    check("마감", out["ok"] and rm.issues[ROOT]["status"] == "완료"
          and last[2]["done_ratio"] == 100 and last[2]["status_name"] == "완료")


def test_logs():
    rm = _fresh()
    seen = []
    WF.create_map(ROOT, "HUD", FIRST2, confirm=True, user_answer="응", rm=rm, logf=seen.append)
    writes = len(rm.writes())
    check("쓰기마다 로그", sum(x.startswith("쓰기 —") for x in seen) == writes, f"{seen}")
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        WF.claim(ROOT, 1999, "x", rm=rm)
    check("기본 로그는 stderr [wayfinder]", buf.getvalue().startswith("[wayfinder] 거절"))


def test_end_to_end_direct():
    """MCP 없이 모듈 함수만으로 한 바퀴 — C8 근거."""
    rm = _fresh()
    log = []
    pv = WF.create_map(ROOT, "HUD", FIRST, rm=rm, logf=log.append)
    ok = pv["ok"] and not rm.writes()
    c = _legacy(rm, "HUD", SPECS, fog=["저장 형식"])
    ok &= WF.claim(ROOT, c["pre"], "claude", rm=rm, logf=log.append)["ok"]
    rm.issues[c["pre"]]["status"] = "완료"
    ok &= WF.on_node_closed(c["pre"], rm=rm, logf=log.append)["changed"]
    for k in ("hud", "inv"):
        rm.issues[c[k]]["status"] = "완료"
        ok &= WF.sync(ROOT, closed_node=c[k], rm=rm, logf=log.append)["ok"]
    ok &= [f["id"] for f in WF.frontier(ROOT, rm=rm)["frontier"]] == [c["ver"]]
    p = WF.propose_node(ROOT, "HUD 애니메이션", "작업", c["pre"], deps=[c["hud"]], rm=rm, logf=log.append)
    reg = WF.register_node(ROOT, p["proposal"], user_answer="응", rm=rm, logf=log.append)
    ok &= reg["ok"] and set(reg["reverify"]) == {c["pre"], c["hud"], c["inv"]}
    for i in reg["reverify"]:
        ok &= WF.mark_verified(ROOT, i, "재확인", rm=rm, logf=log.append)["ok"]
    for k in ("ver",):
        rm.issues[c[k]]["status"] = "완료"
        ok &= WF.sync(ROOT, closed_node=c[k], rm=rm, logf=log.append)["ok"]
    claimed = WF.claim(ROOT, reg["id"], "claude", rm=rm, logf=log.append)
    ok &= claimed["ok"]
    rm.issues[claimed["id"]]["status"] = "완료"
    ok &= WF.on_node_closed(claimed["id"], rm=rm, logf=log.append)["ok"]
    ok &= not WF.close_root(ROOT, confirm=True, user_answer="응", rm=rm, logf=log.append)["ok"]  # 안개
    blk = MB.parse(rm.issues[ROOT]["description"])            # 사람이 안개를 걷었다
    blk.fog = []
    rm.issues[ROOT]["description"] = MB.put(rm.issues[ROOT]["description"], blk)
    st = WF.frontier(ROOT, rm=rm)["states"]
    ok &= st["완료"] == 5
    ok &= WF.close_root(ROOT, confirm=True, user_answer="응", rm=rm, logf=log.append)["ok"]
    check("직접 호출 한 바퀴", ok, "\n".join(log[-10:]))


# ── 안개 졸업 · 지도 편집 (`#1000` T1·T2) ──────────────────────────────────

def _fogged(fog=("저장 형식", "네트워크 동기화", "로컬라이즈"), oos=("멀티플레이 — 이번 범위 아님",)):
    """노드 4개 지도 + 안개 셋 · 범위 밖 하나."""
    rm = _fresh()
    return rm, _legacy(rm, "HUD 를 붙인다", SPECS, fog=fog, out_of_scope=oos)


def _map(rm):
    return MB.parse(rm.issues[ROOT]["description"])


def _last_note(rm):
    return rm.issues[ROOT]["journals"][-1]["notes"]


def test_graduate_propose():
    rm, c = _fogged()
    n = len(rm.writes())
    lines, logf = _quiet()
    out = WF.propose_node(ROOT, "저장 포맷 정하기", "프리필", "Root", graduates="저장 형식", rm=rm, logf=logf)
    check("졸업 제안(글) 쓰기 0건", out["ok"] and out["proposal"]["graduates"] == "저장 형식"
          and len(rm.writes()) == n, str(out.get("proposal")))
    out = WF.propose_node(ROOT, "동기화", "프리필", "Root", graduates=2, rm=rm, logf=logf)
    check("졸업 제안(번호 int)", out["proposal"]["graduates"] == "네트워크 동기화")
    out = WF.propose_node(ROOT, "번역", "프리필", "Root", graduates="3", rm=rm, logf=logf)
    check("졸업 제안(번호 글)", out["proposal"]["graduates"] == "로컬라이즈" and len(rm.writes()) == n)
    out = WF.propose_node(ROOT, "x", "프리필", "Root", rm=rm, logf=logf)
    check("졸업 없음 = None", out["proposal"]["graduates"] is None)
    check("모르는 안개 줄 → 지금 목록과 함께", _raises(lambda: WF.propose_node(
        ROOT, "x", "작업", "Root", graduates="없는 줄", rm=rm, logf=logf), "저장 형식"))
    check("범위 밖 번호", _raises(lambda: WF.propose_node(
        ROOT, "x", "작업", "Root", graduates=9, rm=rm, logf=logf), "9번"))
    check("졸업 제안 로그", any("안개 졸업 저장 형식" in x for x in lines))


def test_graduate_register():
    rm, c = _fogged()
    p = WF.propose_node(ROOT, "저장 포맷 정하기", "프리필", "Root", graduates=1, rm=rm, logf=_quiet()[1])
    n_root = sum(1 for x in rm.writes() if x[0] == "update_issue" and x[1] == ROOT)
    out = WF.register_node(ROOT, p["proposal"], user_answer="졸업시켜", rm=rm, logf=_quiet()[1])
    check("졸업 등록 ok", out["ok"] and out["graduated"] == "저장 형식", str(out))
    root_writes = [x for x in rm.writes() if x[0] == "update_issue" and x[1] == ROOT]
    check("Root 쓰기 한 번", len(root_writes) == n_root + 1)
    blk = _map(rm)
    check("안개에서 걷힘 + 노드 추가", blk.fog == ["네트워크 동기화", "로컬라이즈"]
          and blk.node(out["id"]) is not None, str(blk.fog))
    check("졸업 노트", f"안개 졸업: 저장 형식 → {MB.label(out['id'])}" in _last_note(rm), _last_note(rm))
    # 제안 뒤 그 줄이 사라졌다 → 쓰기 0건 거절
    rm, c = _fogged()
    p = WF.propose_node(ROOT, "동기화", "프리필", "Root", graduates="네트워크 동기화", rm=rm, logf=_quiet()[1])
    e = WF.propose_edit(ROOT, "fog_resolve", target="네트워크 동기화", reason="필요 없다", rm=rm, logf=_quiet()[1])
    WF.apply_edit(ROOT, e["proposal"], user_answer="응", rm=rm, logf=_quiet()[1])
    n = len(rm.writes())
    lines, logf = _quiet()
    out = WF.register_node(ROOT, p["proposal"], user_answer="응", rm=rm, logf=logf)
    check("졸업 줄 사라짐 → 거절 · 쓰기 0건", not out["ok"] and out.get("refused")
          and len(rm.writes()) == n and "네트워크 동기화" in out["why"], str(out))
    check("졸업 거절 로그", any(x.startswith("거절") for x in lines))


def _edit(rm, op, user_answer="응", **kw):
    lines, logf = _quiet()
    n = len(rm.writes())
    p = WF.propose_edit(ROOT, op, rm=rm, logf=logf, **kw)
    zero = len(rm.writes()) == n
    out = WF.apply_edit(ROOT, p["proposal"], user_answer=user_answer, rm=rm, logf=logf)
    return p, out, zero, lines


def test_edit_ops():
    rm, _ = _fogged()
    p, out, zero, lines = _edit(rm, "fog_add", text="세이브 마이그레이션", reason="조사 중 발견")
    check("fog_add 제안 쓰기 0건", zero)
    check("fog_add", out["ok"] and _map(rm).fog[-1] == "세이브 마이그레이션", str(out))
    note = _last_note(rm)
    check("fog_add 노트 전·후·근거·답", "안개 추가" in note and "전: 안개 [저장 형식 · 네트워크 동기화 · 로컬라이즈]" in note
          and "세이브 마이그레이션]" in note and "근거: 조사 중 발견" in note and "사용자 답: 응" in note, note)
    check("편집 로그(제안·쓰기)", any(x.startswith("편집 제안") for x in lines)
          and any(x.startswith("쓰기 —") for x in lines))

    p, out, zero, _ = _edit(rm, "fog_resolve", target=1, reason="JSON 으로 이미 정해짐")
    check("fog_resolve(번호) 쓰기 0건 · 제안 대상은 글", zero and p["proposal"]["target"] == "저장 형식")
    check("fog_resolve", out["ok"] and "저장 형식" not in _map(rm).fog)
    note = _last_note(rm)
    check("fog_resolve 노트 근거", "안개 해소" in note and "근거: JSON 으로 이미 정해짐" in note
          and "전: 안개 [저장 형식 ·" in note, note)

    p, out, zero, _ = _edit(rm, "fog_to_out", target="로컬라이즈", reason="다음 마일스톤")
    blk = _map(rm)
    check("fog_to_out", zero and out["ok"] and "로컬라이즈" not in blk.fog
          and blk.out_of_scope[-1] == "로컬라이즈 — 다음 마일스톤", str(blk.out_of_scope))
    note = _last_note(rm)
    check("fog_to_out 노트 두 절", "안개 → 범위 밖" in note and "범위 밖 [" in note and "근거: 다음 마일스톤" in note, note)

    p, out, zero, _ = _edit(rm, "destination", text="HUD 와 인벤토리를 붙인다", reason="범위 확대")
    check("destination", zero and out["ok"] and _map(rm).destination == "HUD 와 인벤토리를 붙인다")
    note = _last_note(rm)
    check("destination 노트 전→후", "목적지 [HUD 를 붙인다]" in note and "목적지 [HUD 와 인벤토리를 붙인다]" in note, note)

    p, out, zero, _ = _edit(rm, "out_edit", target="1", text="멀티플레이 — 서버 없음")
    check("out_edit(번호 글)", zero and out["ok"] and _map(rm).out_of_scope[0] == "멀티플레이 — 서버 없음")

    p, out, zero, _ = _edit(rm, "out_to_fog", target="로컬라이즈 — 다음 마일스톤")
    blk = _map(rm)
    check("out_to_fog 기본 글 = 꼬리 뗀 것", zero and out["ok"] and blk.fog[-1] == "로컬라이즈"
          and "로컬라이즈 — 다음 마일스톤" not in blk.out_of_scope, str(blk.fog))
    p, out, zero, _ = _edit(rm, "out_to_fog", target=1, text="멀티플레이 재검토")
    check("out_to_fog 글 지정", out["ok"] and _map(rm).fog[-1] == "멀티플레이 재검토" and _map(rm).out_of_scope == [])
    check("편집 뒤 대조 통과", WF.check(ROOT, rm=rm, logf=_quiet()[1])["ok"])


def test_edit_refusals():
    rm, _ = _fogged()
    lg = _quiet()[1]
    n0 = len(rm.writes())
    check("중복 fog_add", _raises(lambda: WF.propose_edit(ROOT, "fog_add", text="저장 형식", rm=rm, logf=lg),
                                "이미 있는"))
    check("fog_resolve 근거 없음", _raises(lambda: WF.propose_edit(
        ROOT, "fog_resolve", target=1, rm=rm, logf=lg), "근거"))
    check("fog_to_out 근거 없음", _raises(lambda: WF.propose_edit(
        ROOT, "fog_to_out", target=1, reason="", rm=rm, logf=lg), "근거"))
    check("모르는 op", _raises(lambda: WF.propose_edit(ROOT, "fog_zap", rm=rm, logf=lg), "fog_add"))
    check("node_out 근거 없음", _raises(lambda: WF.propose_edit(ROOT, "node_out", target=1, rm=rm, logf=lg),
                                      "근거"))
    check("없는 대상", _raises(lambda: WF.propose_edit(
        ROOT, "fog_resolve", target="없음줄", reason="x", rm=rm, logf=lg), "로컬라이즈"))
    for bad in ("a|b", "x</pre>", "<!-- y", "두\n줄", " 공백", "## 제목", ""):
        check(f"글 거절 {bad!r}", _raises(lambda b=bad: WF.propose_edit(
            ROOT, "fog_add", text=b, rm=rm, logf=lg)))
    check("목적지 '## ' 거절", _raises(lambda: WF.propose_edit(
        ROOT, "destination", text="## 목적지", rm=rm, logf=lg), "절 제목"))
    check("목적지 같음 거절", _raises(lambda: WF.propose_edit(
        ROOT, "destination", text="HUD 를 붙인다", rm=rm, logf=lg), "같다"))
    check("근거 '|' 거절", _raises(lambda: WF.propose_edit(
        ROOT, "fog_to_out", target=1, reason="a|b", rm=rm, logf=lg), "근거"))
    check("propose_edit 거절은 아무것도 안 씀", len(rm.writes()) == n0)

    p = WF.propose_edit(ROOT, "fog_resolve", target=2, reason="정해짐", rm=rm, logf=lg)
    n = len(rm.writes())
    lines, logf = _quiet()
    out = WF.apply_edit(ROOT, p["proposal"], user_answer="  ", rm=rm, logf=logf)
    check("답 없으면 거절 · 쓰기 0건", not out["ok"] and out["refused"] and len(rm.writes()) == n)
    check("거절 로그", any(x.startswith("거절") for x in lines))
    # 대상이 사라짐(같은 제안 두 번)
    out = WF.apply_edit(ROOT, p["proposal"], user_answer="응", rm=rm, logf=logf)
    check("첫 적용 ok", out["ok"])
    n = len(rm.writes())
    out = WF.apply_edit(ROOT, p["proposal"], user_answer="응", rm=rm, logf=logf)
    check("낡은 대상 거절 · 쓰기 0건", not out["ok"] and out["refused"] and len(rm.writes()) == n, str(out))
    # 그 사이 안개에 같은 줄이 생김 → 중복 거절
    p = WF.propose_edit(ROOT, "fog_add", text="새 의문", rm=rm, logf=lg)
    WF.apply_edit(ROOT, WF.propose_edit(ROOT, "fog_add", text="새 의문", rm=rm, logf=lg)["proposal"],
                  user_answer="응", rm=rm, logf=lg)
    n = len(rm.writes())
    out = WF.apply_edit(ROOT, p["proposal"], user_answer="응", rm=rm, logf=lg)
    check("적용 때 중복 거절 · 쓰기 0건", not out["ok"] and out["refused"] and len(rm.writes()) == n)
    # 차이 있음 → 거절
    rm2, c = _fogged()
    p = WF.propose_edit(ROOT, "fog_add", text="새 의문", rm=rm2, logf=lg)
    rm2.issues[c["inv"]]["parent"] = None
    n = len(rm2.writes())
    out = WF.apply_edit(ROOT, p["proposal"], user_answer="응", rm=rm2, logf=lg)
    check("대조 차이 → 적용 거절", not out["ok"] and out["differences"] and len(rm2.writes()) == n)
    out = WF.apply_edit(ROOT, dict(p["proposal"], root=ROOT + 1), user_answer="응", rm=rm2, logf=lg)
    check("다른 Root 제안 거절", not out["ok"] and out["refused"])


def test_fog_cleared_close_root():
    """안개를 졸업·해소·범위 밖으로 비운 뒤 노드가 다 끝나면 Root 가 닫힌다 — 대역 위 한 바퀴."""
    rm, c = _fogged()
    lg = _quiet()[1]
    p = WF.propose_node(ROOT, "저장 포맷 정하기", "프리필", "Root", graduates="저장 형식", rm=rm, logf=lg)
    reg = WF.register_node(ROOT, p["proposal"], user_answer="응", rm=rm, logf=lg)
    ok = reg["ok"]
    for op, tgt, why in (("fog_resolve", "네트워크 동기화", "단일 플레이"), ("fog_to_out", 1, "다음 마일스톤")):
        e = WF.propose_edit(ROOT, op, target=tgt, reason=why, rm=rm, logf=lg)
        ok &= WF.apply_edit(ROOT, e["proposal"], user_answer="응", rm=rm, logf=lg)["ok"]
    ok &= _map(rm).fog == []
    for k in ("pre", "hud", "inv", "ver"):
        rm.issues[c[k]]["status"] = "완료"
        ok &= WF.sync(ROOT, closed_node=c[k], rm=rm, logf=lg)["ok"]
    claimed = WF.claim(ROOT, reg["id"], "claude", rm=rm, logf=lg)
    ok &= claimed["ok"]
    rm.issues[claimed["id"]]["status"] = "완료"
    ok &= WF.on_node_closed(claimed["id"], rm=rm, logf=lg)["ok"]
    for n in _map(rm).nodes:                      # 졸업 노드가 Root 직속이라 재검증된 완료 노드를 되돌린다
        if n.state == "재검증":
            ok &= WF.mark_verified(ROOT, n.id, "재확인", rm=rm, logf=lg)["ok"]
    pv = WF.close_root(ROOT, rm=rm, logf=lg)
    out = WF.close_root(ROOT, confirm=True, user_answer="닫아", rm=rm, logf=lg)
    check("안개 비운 뒤 Root 마감", ok and pv["ready"] and out["ok"] and rm.issues[ROOT]["status"] == "완료",
          f"{pv.get('blockers')} {out}")


# ── 노드 → 범위 밖 (`#1000` T3) ────────────────────────────────────────────

def _out_ready():
    """_fogged 지도에서 inv 만 완료(pre 는 열림) — hud 를 빼면 ver 의 남은 선행(inv)이 완료라 Frontier."""
    rm, c = _fogged()
    rm.issues[c["inv"]]["status"] = "완료"
    assert WF.sync(ROOT, closed_node=c["inv"], rm=rm, logf=_quiet()[1])["ok"]
    return rm, c


def test_fake_refuses_blocked_close():
    rm, c = _made()
    out = rm.update_issue(c["hud"], notes="닫기", status_name="완료", done_ratio=100)
    check("대역: 열린 선행이 막으면 닫지 않음", str(out).startswith("[주의]")
          and rm.issues[c["hud"]]["status"] == "신규" and f"#{c['pre']}" in out, str(out))


def test_node_out_propose():
    rm, c = _out_ready()
    n = len(rm.writes())
    lines, logf = _quiet()
    out = WF.propose_edit(ROOT, "node_out", target=str(c["hud"]), reason="HUD 는 다음 마일스톤", rm=rm, logf=logf)
    check("node_out 제안 쓰기 0건", out["ok"] and len(rm.writes()) == n, str(out))
    p = out["proposal"]
    check("제안 노드", p["target"] == c["hud"] and p["node"] == {"id": c["hud"], "title": "HUD 위젯", "state": "차단"},
          str(p.get("node")))
    check("제안 자식 없음", p["children"] == [])
    want_rels = sorted(r["id"] for r in rm.relations if c["hud"] in (r["issue_id"], r["issue_to_id"]))
    check("제안 관계(읽기)", p["relations"] == want_rels and len(want_rels) == 2, str(p["relations"]))
    check("제안 dependents", p["dependents"] == [c["ver"]])
    line = f"#{c['hud']} HUD 위젯 — HUD 는 다음 마일스톤"
    check("후: 범위 밖 줄", p["after"]["out_of_scope"][-1] == line and p["text"] == line, str(p["after"]))
    check("후: 표에서 빠짐", not any(x.startswith(f"#{c['hud']} ") for x in p["after"]["nodes"])
          and any(x.startswith(f"#{c['hud']} ") for x in p["before"]["nodes"]))
    check("후: ver Frontier 미리보기", any(x.startswith(f"#{c['ver']} ") and "Frontier" in x
                                       for x in p["after"]["nodes"]), str(p["after"]["nodes"]))
    check("node_out 제안 로그", any("쓰기 0건" in x and "삭제 예정" in x for x in lines))
    # 파생 자식 → 거절 dict, 목록 포함
    n = len(rm.writes())
    lines, logf = _quiet()
    out = WF.propose_edit(ROOT, "node_out", target=c["pre"], reason="x", rm=rm, logf=logf)
    check("자식 있으면 거절 dict", not out["ok"] and out["refused"]
          and f"#{c['hud']} HUD 위젯" in out["why"] and f"#{c['inv']} 인벤토리 연결" in out["why"]
          and [x["id"] for x in out["children"]] == sorted([c["hud"], c["inv"]]) and len(rm.writes()) == n, str(out))
    check("자식 거절 로그", any(x.startswith("거절") for x in lines))
    out = WF.propose_edit(ROOT, "node_out", target=c["inv"], reason="x", rm=rm, logf=logf)
    check("완료 노드 거절", not out["ok"] and out["refused"] and "이미 완료된 노드" in out["why"]
          and len(rm.writes()) == n, str(out))
    check("모르는 노드", _raises(lambda: WF.propose_edit(ROOT, "node_out", target=9999, reason="x", rm=rm, logf=logf),
                            "노드가 아니다"))
    check("text 거절", _raises(lambda: WF.propose_edit(ROOT, "node_out", target=c["hud"], text="y", reason="x",
                                                      rm=rm, logf=logf), "text"))
    check("node_out 거절들 쓰기 0건", len(rm.writes()) == n)


def test_node_out_apply():
    rm, c = _out_ready()
    p = WF.propose_edit(ROOT, "node_out", target=c["hud"], reason="HUD 는 다음 마일스톤", rm=rm,
                        logf=_quiet()[1])["proposal"]
    n = len(rm.writes())
    lines, logf = _quiet()
    out = WF.apply_edit(ROOT, p, user_answer="", rm=rm, logf=logf)
    check("node_out 답 없으면 거절 · 쓰기 0건", not out["ok"] and out["refused"] and len(rm.writes()) == n)
    start = len(rm.calls)
    out = WF.apply_edit(ROOT, p, user_answer="빼자", rm=rm, logf=logf)
    check("node_out 적용 ok", out["ok"] and out["op"] == "node_out", str(out))
    check("결과 필드", out["node"]["id"] == c["hud"] and out["deleted_relations"] == p["relations"]
          and out["dependents"] == [c["ver"]] and "before" in out and "after" in out)
    w = [x for x in rm.calls[start:] if x[0] in WRITES]
    kinds = [("del" if x[0] == "delete_relation" else "root" if x[1] == ROOT else "node") for x in w]
    check("순서: 관계 삭제 → Root → 닫기", kinds == ["del", "del", "root", "node"], str(kinds))
    check("관계 다 지워짐", not any(c["hud"] in (r["issue_id"], r["issue_to_id"]) for r in rm.relations))
    check("열린 선행이어도 닫힘(관계 먼저 지워서)", rm.issues[c["hud"]]["status"] == "완료"
          and rm.issues[c["pre"]]["status"] == "신규")
    close = w[-1][2]
    check("닫기 노트·100%", close["status_name"] == "완료" and close["done_ratio"] == 100
          and close["notes"] == f"웨이파인더 범위 밖 — HUD 는 다음 마일스톤 (맵 Root #{ROOT})", str(close))
    blk = _map(rm)
    check("표에서 빠짐", blk.node(c["hud"]) is None)
    check("범위 밖 줄", blk.out_of_scope[-1] == f"#{c['hud']} HUD 위젯 — HUD 는 다음 마일스톤", str(blk.out_of_scope))
    check("ver 선행에서 걷힘 · Frontier", blk.node(c["ver"]).deps == [c["inv"]]
          and blk.node(c["ver"]).state == "Frontier")
    note = _last_note(rm)
    check("Root 노트", "노드 → 범위 밖" in note and "근거: HUD 는 다음 마일스톤" in note and "사용자 답: 빼자" in note
          and "전: 노드 [" in note and "삭제한 관계" in note, note)
    check("쓰기 로그 4줄", sum(x.startswith("쓰기 —") for x in lines) == 4, str(lines))
    check("node_out 뒤 대조 통과", WF.check(ROOT, rm=rm, logf=_quiet()[1])["ok"])
    pv = WF.close_root(ROOT, rm=rm, logf=_quiet()[1])
    check("close_root 를 막지 않음", not any(b.startswith(f"#{c['hud']} ") for b in pv["blockers"]), str(pv["blockers"]))
    n = len(rm.writes())
    out = WF.apply_edit(ROOT, p, user_answer="응", rm=rm, logf=_quiet()[1])
    check("두 번째 적용(노드 없음) 거절 · 쓰기 0건", not out["ok"] and out["refused"] and len(rm.writes()) == n, str(out))


def test_node_out_close_fails():
    rm, c = _out_ready()
    p = WF.propose_edit(ROOT, "node_out", target=c["ver"], reason="검증 생략", rm=rm, logf=_quiet()[1])["proposal"]
    rm.fail["update_issue"] = rm.counts.get("update_issue", 0) + 2      # Root 쓰기는 되고 닫기만 실패
    lines, logf = _quiet()
    out = WF.apply_edit(ROOT, p, user_answer="응", rm=rm, logf=logf)
    check("닫기 실패 보고", not out["ok"] and out["step"] == "노드 닫기" and out["map_written"] is True
          and out["why"].startswith("[주의]") and out["deleted_relations"] == p["relations"], str(out))
    check("지도는 이미 범위 밖(되돌리지 않음)", _map(rm).node(c["ver"]) is None
          and rm.issues[c["ver"]]["status"] == "신규")
    check("닫기 실패 로그", any(x.startswith("[주의] 중단 — 노드 닫기") for x in lines))
    rm.fail.clear()
    pv = WF.close_root(ROOT, rm=rm, logf=_quiet()[1])
    check("닫기 실패여도 close_root 막지 않음", not any(b.startswith(f"#{c['ver']} ") for b in pv["blockers"]))


def test_node_out_changed_between():
    # 제안 뒤 파생 자식이 생김 → 거절 · 쓰기 0건
    rm, c = _out_ready()
    p = WF.propose_edit(ROOT, "node_out", target=c["ver"], reason="x", rm=rm, logf=_quiet()[1])["proposal"]
    q = WF.propose_node(ROOT, "결합 검증 보조", "작업", c["ver"], rm=rm, logf=_quiet()[1])
    reg = WF.register_node(ROOT, q["proposal"], user_answer="응", rm=rm, logf=_quiet()[1])
    assert reg["ok"], reg
    n = len(rm.writes())
    out = WF.apply_edit(ROOT, p, user_answer="응", rm=rm, logf=_quiet()[1])
    check("그 사이 자식 생김 → 거절 · 쓰기 0건", not out["ok"] and out["refused"] and len(rm.writes()) == n
          and f"{reg['id']} 결합 검증 보조" in out["why"] and out["children"], str(out))
    # 대조 차이 → 거절
    rm, c = _out_ready()
    p = WF.propose_edit(ROOT, "node_out", target=c["hud"], reason="x", rm=rm, logf=_quiet()[1])["proposal"]
    rm.issues[c["inv"]]["parent"] = None
    n = len(rm.writes())
    out = WF.apply_edit(ROOT, p, user_answer="응", rm=rm, logf=_quiet()[1])
    check("node_out 대조 차이 → 거절 · 쓰기 0건", not out["ok"] and out["differences"] and len(rm.writes()) == n)


def test_distributed_node_display_and_guards():
    from tempfile import TemporaryDirectory
    from master import issue_infra as INF, issue_lock as IL, plan_tools as PT, redmine

    rm, ids = _made()
    n = ids["pre"]
    # 사용자가 범위 밖 편집을 검토한 뒤 노드에 배정이 들어온 경우를 검사한다.
    edit = WF.propose_edit(ROOT, "node_out", target=ids["ver"], reason="검증 보류", rm=rm, logf=_quiet()[1])
    before = len(rm.writes())
    with TemporaryDirectory() as tmp:
        assigned = IL.reserve_node(tmp, n, root_id=ROOT, worker="worker-a")["record"]
        view = WF.frontier(ROOT, rm=rm, lock_root=tmp)
        check("1038 지도에서 서버 워커를 표시하고 Frontier 제외", n not in [x["id"] for x in view["frontier"]]
              and view["assignments"] == [{"id": n, "title": _map(rm).node(n).title,
                                           "worker": "worker-a", "state": "실행 중"}], str(view))
        check("1038 단독 지도 선점 거절", not WF.claim(ROOT, n, "local", rm=rm, lock_root=tmp, logf=_quiet()[1])["ok"])
        refused, _, _ = INF.lock_gate(tmp, n, log=INF.Log("test", n, logf=_quiet()[1]))
        check("1038 단독 시작 거절", refused is not None and refused["step"] == "lock", str(refused))
        check("1038 작업중 전이 잠금 검사에서 거절",
              _raises(lambda: PT._lock_gate(n, tmp), "분산 노드", cls=PT.PlanToolError))
        IL.advance_node_assignment(tmp, n, assignment_id=assigned["assignment_id"], to=IL.NODE_REVIEW,
                                   by="master", why="실행 종료 확인")
        check("1038 지도 검수 상태 표시", WF.frontier(ROOT, rm=rm, lock_root=tmp)["assignments"][0]["state"] == "검수 대기")
        gate = redmine.make_completion_gate(root_fn=lambda: tmp, logf=_quiet()[1])
        check("1038 검수 대기 직접 마감 차단", not gate(n)["ok"] and "분산 노드" in gate(n)["why"])
        IL.reserve_node(tmp, ids["ver"], root_id=ROOT, worker="worker-a")
        result = WF.apply_edit(ROOT, edit["proposal"], user_answer="응", rm=rm, lock_root=tmp, logf=_quiet()[1])
        check("1038 배정 뒤 범위 밖 편집 거절·쓰기 없음", not result["ok"] and len(rm.writes()) == before, str(result))


def test_distributed_dispatch_preflight():
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from types import SimpleNamespace
    from unittest.mock import patch
    from master import auth, issue_infra, issue_lock, plan_block, plan_tools, spec_block
    from master import wayfinder_dispatch as dispatch
    from master.client.bundle import HostFacts
    from master.projects.config import Registry, Workshop
    from master.work import mode

    rm = _fresh()
    keys = _build(rm, "목적", SPECS + FIRST2[-1:])
    _, logf = _quiet()
    issue_id = WF.claim(ROOT, "P1", prepare_only=True, rm=rm, logf=logf)["id"]
    issue = rm.issues[issue_id]
    with TemporaryDirectory() as tmp:
        before = len(rm.writes())
        preview = dispatch.candidates(ROOT, [issue_id, "P2", 99999], rm=rm, lock_root=tmp)
        check("발주 미리보기: 미준비 티켓과 지도에 없는 번호의 대기 사유",
              preview["ok"] and not preview["ready"] and len(preview["waiting"]) == 3
              and len(rm.writes()) == before, str(preview))
        spec = "\n".join(f"## {heading}\n승인된 내용" for heading in
                         ("문제", "분류", "관측", "범위", "완료 조건", "열린 결정"))
        issue["description"] = spec_block.put(issue["description"], spec)
        tasks = [plan_block.IssuePlanTask("T1", "대기", "구현")]
        issue["description"] = plan_block.append(issue["description"], tasks)
        preview = dispatch.candidates(ROOT, [issue_id], rm=rm, lock_root=tmp)
        check("발주 미리보기: 체크리스트 미등록 티켓 대기",
              not preview["ready"] and "체크리스트" in preview["waiting"][0]["why"], str(preview))
        issue["description"] = plan_block.replace(
            issue["description"], tasks, checklist=[plan_block.IssuePlanCheck("C1", "미확인", "검사")])
        preview = dispatch.candidates(ROOT, [issue_id, issue_id], rm=rm, lock_root=tmp)
        check("발주 미리보기: 승인된 플랜 한 건, 중복 입력 제거",
              [row["id"] for row in preview["ready"]] == [issue_id], str(preview))
        workshops = {"a": Workshop("worker-a", driven="ssh", user="sim", path="/repo"),
                     "b": Workshop("requester", driven="ssh", role="requester", user="sim", path="/repo"),
                     "c": Workshop("worker-c", driven="ssh", user="sim", path="/repo")}
        config = SimpleNamespace(workshops=workshops)
        registry = SimpleNamespace(config_of=lambda _: config)
        with patch.object(Registry, "load", return_value=registry), \
                patch.object(mode, "current", return_value=("codex", "test")), \
                patch.object(issue_lock, "default_root", return_value=tmp), \
                patch.object(WF, "_port", return_value=rm):
            dry_run = dispatch.preview(ROOT, [issue_id, "P2"])
            check("드라이런: 대기 사유와 예상 워커를 표시하며 티켓·잠금 파일에 쓰지 않는다",
                  dry_run["dry_run"] and dry_run["worker_candidates"] == [{"id": issue_id, "worker": "worker-a"}]
                  and len(dry_run["waiting"]) == 1 and len(rm.writes()) == before and not list(Path(tmp).iterdir()),
                  str(dry_run))
            second_id = WF.claim(ROOT, keys["sav"], prepare_only=True, rm=rm, logf=logf)["id"]
            second_issue = rm.issues[second_id]
            second_issue["description"] = plan_block.append(
                spec_block.put(second_issue["description"], spec), tasks,
                checklist=[plan_block.IssuePlanCheck("C1", "미확인", "검사")])
            issue_lock.acquire(tmp, 1039, branch="issue/1039", start_rev="a" * 40, logf=logf)
            blocked, _, _ = issue_infra.lock_gate(
                tmp, issue_id, log=issue_infra.Log("dry-run", issue_id, logf=logf))
            check("#1039 활성일 때 다른 노드의 단독 착수·태스크 작업중 전이는 거절",
                  blocked is not None and blocked["holder"] == 1039
                  and _raises(lambda: plan_tools._lock_gate(second_id, tmp), "#1039 작업이 진행 중",
                              cls=plan_tools.PlanToolError))
            old_lock = issue_lock.state_path(tmp).read_bytes()
            writes = len(rm.writes())
            with patch.object(dispatch, "reserve_worker", side_effect=AssertionError("드라이런에서 예약")):
                dry_run = dispatch.preview(ROOT, [issue_id, second_id])
            check("#1039 활성 중 분산 후보 두 건과 예상 워커 두 대, 실제 쓰기 0건",
                  dry_run["worker_candidates"] == [{"id": issue_id, "worker": "worker-a"},
                                                  {"id": second_id, "worker": "worker-c"}]
                  and issue_lock.state_path(tmp).read_bytes() == old_lock and len(rm.writes()) == writes,
                  str(dry_run))
            issue_lock.reserve_node(tmp, 99998, root_id=ROOT, worker="WORKER-A", logf=logf)
            old_lock = issue_lock.state_path(tmp).read_bytes()
            dry_run = dispatch.preview(ROOT, [issue_id])
            check("드라이런: 점유된 등록 워커와 요청자 제외, 배정 장부 그대로",
                  dry_run["worker_candidates"] == [{"id": issue_id, "worker": "worker-c"}]
                  and issue_lock.state_path(tmp).read_bytes() == old_lock, str(dry_run))
            issue_lock.advance_node_assignment(tmp, 99998, assignment_id=issue_lock.node_assignments(tmp)[99998]["assignment_id"],
                                               to=issue_lock.NODE_REVIEW, by="master", why="종료 확인", logf=logf)
        facts = [HostFacts("worker-a", "sim", "/repo", "ssh", codex="codex 1", checkout_ok=True),
                 HostFacts("worker-b", "sim", "/repo", "ssh", codex="codex 1", checkout_ok=True)]
        first = dispatch.reserve_worker(tmp, ROOT, issue_id, facts, mode="codex")
        second = dispatch.reserve_worker(tmp, ROOT, second_id, facts, mode="codex")
        duplicate = dispatch.reserve_worker(tmp, ROOT, issue_id, facts, mode="codex")
        check("발주 예약: 점유 중인 워커를 빼고 두 번째 등록 워커 선택",
              first["ok"] and second["ok"] and first["worker"].host != second["worker"].host)
        check("발주 예약: 같은 노드를 거듭 발주할 수 없다", not duplicate["ok"], str(duplicate))
        check("#1050 발주 예약은 지휘자 모드를 배정의 작성 계열로 남긴다",
              first["record"].get("family") == "codex" and second["record"].get("family") == "codex",
              str(first["record"]))
        test_master_token = "test-master-" + "a" * auth.MIN_TOKEN_LEN

        def run_ticket(worker, ticket, *, assignment_id, grant, mode, on_exit):
            scoped = auth._read_node_ticket_grant(grant, test_master_token)
            check("배정 일감·워커로 서명한 기간 제한 권한을 실행에 전달",
                  scoped is not None and scoped.issue_id == issue_id and scoped.worker == worker.host
                  and scoped.assignment_id == assignment_id
                  and ticket == issue_id and assignment_id == first["record"]["assignment_id"] and mode == "codex")
            on_exit()
            return 0, grant

        with patch.object(auth, "load_token", return_value=test_master_token), \
                patch.object(dispatch.runner, "run_node_ticket", side_effect=run_ticket) as launch:
            result = dispatch.run_assignment(tmp, first["record"], first["worker"], mode="codex")
            wrong = dispatch.run_assignment(tmp, first["record"], second["worker"], mode="codex")
        check("현재 배정만 실행, 실행 결과에 권한값·워커 출력 없음",
              result == {"rc": 0, "termination_confirmed": True, "why": "워커 실행 종료 확인 (rc=0)"}
              and not wrong["termination_confirmed"] and launch.call_count == 1, str(result))

    def simulate_worker(worker, ticket, *, assignment_id, grant, mode, on_exit):
        if ticket == issue_id:
            on_exit()
            return 0, "검증 결과 기록"
        return 255, "연결 끊김"

    with TemporaryDirectory() as tmp, \
            patch.object(auth, "load_token", return_value=test_master_token), \
            patch.object(dispatch.runner, "run_node_ticket", side_effect=simulate_worker) as launch:
        issue_lock.acquire(tmp, 1039, branch="issue/1039", start_rev="a" * 40, logf=logf)
        refused = dispatch.dispatch_cycle(ROOT, [issue_id, second_id], "", rm=rm, lock_root=tmp, workers=facts,
                                           worker_mode="codex")
        check("실제 발주 요청이 없으면 워커 실행 없이 거절", not refused["ok"] and not launch.called, str(refused))
        batch = dispatch.dispatch_cycle(ROOT, [issue_id, second_id], "이번 묶음 발주해", rm=rm, lock_root=tmp,
                                        workers=facts, worker_mode="codex")
        state = issue_lock.node_assignments(tmp)
        check("단독 일감 잠금 유지 중 배정 두 건의 실행과 검수 인계를 대역으로 검증",
              launch.call_count == 2 and issue_lock.current(tmp)["issue_id"] == 1039
              and state[issue_id]["state"] == issue_lock.NODE_REVIEW
              and state[second_id]["state"] == issue_lock.NODE_RUNNING and not batch["ok"], str(batch))
        check("종료가 확인된 일감에만 검사 인계 노트가 생기고 티켓은 열린 상태",
              "검수 대기" in rm.issues[issue_id]["journals"][-1]["notes"]
              and not rm.issues[second_id]["journals"]
              and rm.issues[issue_id]["status"] == rm.issues[second_id]["status"] == "신규")
        old = dict(first, record=state[issue_id])
        issue_lock.advance_node_assignment(tmp, issue_id, assignment_id=old["record"]["assignment_id"],
                                           to=issue_lock.NODE_REWORK, by="master", why="수정 요청", logf=logf)
        again = dispatch.reserve_worker(tmp, ROOT, issue_id, facts, mode="codex")
        with patch.object(dispatch, "run_assignment",
                          return_value={"rc": 0, "termination_confirmed": True, "why": "늦은 종료"}):
            stale = dispatch._run_and_handoff(tmp, rm, old, "codex")
        check("이전 배정의 종료는 새 배정에 영향을 주지 않는다",
              stale.get("reason") == "stale_assignment"
              and issue_lock.node_assignments(tmp)[issue_id] == again["record"], str(stale))


def test_distributed_review_1050():
    """`#1050` T3 — 검수 대기 배정의 통과(마감·맵·해제)와 재작업, 중간 실패 뒤 재시도."""
    from tempfile import TemporaryDirectory
    from master import issue_lock, plan_block, spec_block
    from master import wayfinder_dispatch as dispatch

    rm = _fresh()
    specs = [{"key": "a", "title": "작업 A", "type": "작업", "parent": "Root", "deps": [], "summary": "A"},
             {"key": "b", "title": "작업 B", "type": "작업", "parent": "Root", "deps": [], "summary": "B"},
             {"key": "c", "title": "검증 C", "type": "검증", "parent": "Root", "deps": [], "summary": "C"}]
    _build(rm, "목적", specs)
    _, logf = _quiet()
    spec = "\n".join(f"## {h}\n승인된 내용" for h in ("문제", "분류", "관측", "범위", "완료 조건", "열린 결정"))
    ids = []
    for key in ("P1", "P2", "P3"):
        iid = WF.claim(ROOT, key, prepare_only=True, rm=rm, logf=logf)["id"]
        rm.issues[iid]["description"] = plan_block.append(
            spec_block.put(rm.issues[iid]["description"], spec), [plan_block.IssuePlanTask("T1", "대기", "구현")],
            checklist=[plan_block.IssuePlanCheck("C1", "미확인", "검사")])
        ids.append(iid)
    a, b, c = ids
    with TemporaryDirectory() as tmp:
        recs = {}
        for iid, worker in ((a, "w1"), (b, "w2"), (c, "w3")):
            recs[iid] = issue_lock.reserve_node(tmp, iid, root_id=ROOT, worker=worker, family="codex")["record"]
        rev = "1" * 40
        issue_lock.start_node_work(tmp, a, assignment_id=recs[a]["assignment_id"], worker="w1", start_rev=rev,
                                   branch=f"wayfinder/{ROOT}/n{a}")
        issue_lock.submit_node_result(tmp, a, assignment_id=recs[a]["assignment_id"], worker="w1", end="2" * 40,
                                      hashes=["2" * 40], subjects=["A 구현"], summary="test 3/3")
        review = lambda iid, verdict, **kw: dispatch.review(iid, verdict, kw.pop("why", "검수"), rm=rm,
                                                            lock_root=tmp, **kw)
        check("#1050 실행 중 배정은 검수 거절", not review(a, "pass")["ok"])
        for iid in ids:
            issue_lock.advance_node_assignment(tmp, iid, assignment_id=recs[iid]["assignment_id"],
                                               to=issue_lock.NODE_REVIEW, by="master", why="종료 확인")
        before = len(rm.writes())
        preview = review(a, "pass")
        check("#1050 미리보기: 제출 범위·계열 표시 · 쓰기 0",
              preview["ok"] and preview["dry_run"] and preview["node"]["result"]["hashes"] == ["2" * 40]
              and preview["node"]["family"] == "codex" and len(rm.writes()) == before, str(preview))
        check("#1050 제출 없는 작업 노드는 통과 거절", "제출된 결과" in review(b, "pass")["why"])
        check("#1050 제출 없는 검증 노드는 통과 미리보기 가능", review(c, "pass")["ok"])
        check("#1050 승인 원문 없이 확정 거절",
              not review(a, "pass", confirm=True)["ok"] and len(rm.writes()) == before)

        rm.fail = {"update_issue": rm.counts.get("update_issue", 0) + 1}
        first = review(a, "pass", confirm=True, user_answer="통과시켜")
        state = issue_lock.node_assignments(tmp)[a]["state"]
        check("#1050 마감 실패: step redmine · 배정은 승인됨 유지 · 티켓 열림",
              not first["ok"] and first["step"] == "redmine" and state == issue_lock.NODE_ACCEPTED
              and rm.issues[a]["status"] != WF.DONE, str(first))
        rm.fail = {}
        mapped_fail = review(a, "pass", confirm=True, user_answer="통과시켜",
                             map_hook=lambda iid, rm: {"ok": False, "why": "맵 대역 실패"})
        check("#1050 재시도: 승인 단계 건너뛰고 마감 · 맵 실패면 배정 유지",
              not mapped_fail["ok"] and mapped_fail["steps"] == ["closed"] and mapped_fail["step"] == "map"
              and rm.issues[a]["status"] == WF.DONE and a in issue_lock.node_assignments(tmp), str(mapped_fail))
        notes = [j["notes"] for j in rm.issues[a]["journals"] if "검수 통과" in j["notes"]]
        check("#1050 마감 노트에 범위·작성 계열·근거·승인 원문",
              len(notes) == 1 and "커밋 1건" in notes[0] and "작성 계열 codex" in notes[0]
              and "통과시켜" in notes[0], str(notes))
        done = review(a, "pass", confirm=True, user_answer="통과시켜")
        check("#1050 재시도: 마감 건너뛰고 맵 갱신 → 배정 해제",
              done["ok"] and done["steps"] == ["map", "finished"] and a not in issue_lock.node_assignments(tmp)
              and len([j for j in rm.issues[a]["journals"] if "검수 통과" in j["notes"]]) == 1, str(done))
        check("#1050 해제 뒤 같은 검수 호출은 거절", not review(a, "pass", confirm=True, user_answer="x")["ok"])

        rw = review(b, "rework", why="테스트 누락", confirm=True, user_answer="다시 해")
        check("#1050 재작업: 근거 노트 → 같은 티켓 재작업 상태",
              rw["ok"] and rw["steps"] == ["note", issue_lock.NODE_REWORK]
              and issue_lock.node_assignments(tmp)[b]["state"] == issue_lock.NODE_REWORK
              and "테스트 누락" in rm.issues[b]["journals"][-1]["notes"]
              and rm.issues[b]["status"] != WF.DONE, str(rw))
        again = dispatch.candidates(ROOT, [b], rm=rm, lock_root=tmp)
        check("#1050 재작업 티켓은 다음 발주 후보", [r["id"] for r in again["ready"]] == [b], str(again))
        check("#1050 재작업 상태에서 다시 검수 거절", not review(b, "rework", confirm=True, user_answer="x")["ok"])
        from master import redmine
        gate = redmine.make_completion_gate(root_fn=lambda: tmp)
        check("#1050 검수 도구 밖의 직접 마감은 기존 관문이 계속 막는다", not gate(c)["ok"], str(gate(c)))


def main() -> int:
    for fn in (test_create_map_preview, test_create_map_confirm, test_create_map_refusals,
               test_first_nodes_only_1028, test_claim_creates_issue_1036, test_prepare_distributed_ticket,
               test_planned_node_out_and_drift_1036,
               test_title_validation, test_compute_states, test_check, test_sync,
               test_sync_keeps_reverify, test_on_node_closed, test_propose_node, test_register_node,
               test_claim, test_mark_verified, test_close_root, test_logs, test_end_to_end_direct,
               test_graduate_propose, test_graduate_register, test_edit_ops, test_edit_refusals,
               test_fog_cleared_close_root, test_fake_refuses_blocked_close, test_node_out_propose,
               test_node_out_apply, test_node_out_close_fails, test_node_out_changed_between,
               test_distributed_node_display_and_guards, test_distributed_dispatch_preflight,
               test_distributed_review_1050):
        try:
            fn()
        except Exception as e:                       # noqa: BLE001
            check(f"{fn.__name__} 예외 없음", False, f"{type(e).__name__}: {e}")
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_wayfinder: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
