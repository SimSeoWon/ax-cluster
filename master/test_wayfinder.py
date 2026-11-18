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
        if status_name:
            iss["status"] = status_name
        if notes:
            iss["journals"].append({"notes": notes})
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
        rel = {"id": self.next_rel, "issue_id": issue_id, "issue_to_id": issue_to_id,
               "relation_type": relation_type}
        self.next_rel += 1
        self.relations.append(rel)
        return {"ok": True, "relation": dict(rel)}

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


def _made(rm=None):
    rm = rm or _fresh()
    lines, logf = _quiet()
    out = WF.create_map(ROOT, "HUD 를 붙인다", SPECS, fog=["저장 형식"], confirm=True,
                        user_answer="좋아 등록해", rm=rm, logf=logf)
    assert out["ok"], out
    return rm, out["created"]


# ── create_map ─────────────────────────────────────────────────────────────

def test_create_map_preview():
    rm = _fresh()
    lines, logf = _quiet()
    out = WF.create_map(ROOT, "HUD 를 붙인다", SPECS, rm=rm, logf=logf)
    check("미리보기 ok", out["ok"] and out["confirmed"] is False)
    check("미리보기 쓰기 0건", rm.writes() == [], str(rm.writes()))
    check("미리보기 영역 글", out["preview"].startswith("<!-- ax:map:begin v=1 -->")
          and "<pre>" in out["preview"])
    check("임시 번호 1..n", sorted(out["temp_ids"].values()) == [1, 2, 3, 4])
    check("예정 쓰기 목록", sum(w.startswith("create_issue") for w in out["writes"]) == 4
          and sum(w.startswith("create_relation") for w in out["writes"]) == 4
          and out["writes"][-1].startswith("update_issue"))
    check("미리보기 로그", any("쓰기 0건" in x for x in lines))
    parsed = MB.parse(out["preview"])
    check("미리보기 왕복", parsed is not None and len(parsed.nodes) == 4)


def test_create_map_confirm():
    rm = _fresh()
    lines, logf = _quiet()
    out = WF.create_map(ROOT, "HUD 를 붙인다", SPECS, fog=["저장 형식"], confirm=True,
                        user_answer="좋아", rm=rm, logf=logf)
    check("등록 ok", out["ok"] and out["confirmed"], str(out))
    c = out["created"]
    creates = [x for x in rm.calls if x[0] == "create_issue"]
    order = [x[1] for x in creates]
    check("부모 먼저", order.index("사전조사 HUD") < order.index("HUD 위젯")
          and order.index("사전조사 HUD") < order.index("인벤토리 연결"))
    check("부모 번호", rm.issues[c["hud"]]["parent"] == c["pre"] and rm.issues[c["pre"]]["parent"] == ROOT
          and rm.issues[c["ver"]]["parent"] == ROOT)
    check("마일스톤 = Root", all(x[2]["fixed_version"] == "마일스톤 7" for x in creates))
    mk = MB.parse_node(rm.issues[c["hud"]]["description"])
    check("노드 표지", mk is not None and mk.root == ROOT and mk.type == "작업")
    check("요약 + 표지", rm.issues[c["pre"]]["description"].startswith("HUD 기능 범위"))
    rels = {(r["issue_id"], r["issue_to_id"]) for r in rm.relations}
    check("관계 방향 (선행 blocks 노드)", rels == {(c["pre"], c["hud"]), (c["pre"], c["inv"]),
                                             (c["hud"], c["ver"]), (c["inv"], c["ver"])}, str(rels))
    first_rel = next(i for i, x in enumerate(rm.calls) if x[0] == "create_relation")
    last_create = max(i for i, x in enumerate(rm.calls) if x[0] == "create_issue")
    check("관계는 노드 뒤", first_rel > last_create)
    body = rm.issues[ROOT]["description"]
    check("영역 밖 보존", body.startswith("## 요청\n\n원문\n"))
    block = MB.parse(body)
    check("지도 기록", block is not None and len(block.nodes) == 4 and block.fog == ["저장 형식"])
    check("다이어그램", block.diagram.startswith("<pre>") and block.diagram.endswith("</pre>"))
    st = {n.id: n.state for n in block.nodes}
    check("초기 상태", st[c["pre"]] == "Frontier" and st[c["hud"]] == "차단" and st[c["ver"]] == "차단")
    check("Frontier 결과", [f["id"] for f in out["frontier"]] == [c["pre"]])
    check("쓰기 로그", sum(x.startswith("쓰기 —") for x in lines) == 4 + 4 + 1)
    check("등록 직후 대조 통과", WF.check(ROOT, rm=rm, logf=_quiet()[1])["ok"])


def test_create_map_refusals():
    rm = _fresh()
    lines, logf = _quiet()
    out = WF.create_map(ROOT, "목적", SPECS, confirm=True, user_answer="  ", rm=rm, logf=logf)
    check("답 없으면 거절", not out["ok"] and out["refused"] and rm.writes() == [])
    check("거절 로그", any(x.startswith("거절") for x in lines))
    rm2, _ = _made()
    n = len(rm2.writes())
    out = WF.create_map(ROOT, "목적", SPECS, confirm=True, user_answer="응", rm=rm2, logf=_quiet()[1])
    check("두 번째 지도 거절", not out["ok"] and "이미" in out["why"] and len(rm2.writes()) == n)
    out = WF.create_map(ROOT, "목적", SPECS, rm=rm2, logf=_quiet()[1])
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
    # 도중 실패 — 되돌리지 않고 보고
    rm3 = _fresh()
    rm3.fail["create_issue"] = 3
    out = WF.create_map(ROOT, "목적", SPECS, confirm=True, user_answer="응", rm=rm3, logf=_quiet()[1])
    check("도중 실패 보고", not out["ok"] and out["created"] == [1001, 1002] and "노드 생성" in out["step"],
          str(out))
    check("도중 실패 뒤 Root 안 씀", not any(x[0] == "update_issue" for x in rm3.calls))
    rm4 = _fresh()
    rm4.fail["create_relation"] = 2
    out = WF.create_map(ROOT, "목적", SPECS, confirm=True, user_answer="응", rm=rm4, logf=_quiet()[1])
    check("관계 실패 보고", not out["ok"] and len(out["created"]) == 4 and out["step"].startswith("관계"))


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
    rm.issues[c["hud"]]["parent"] = ROOT
    out = WF.check(ROOT, rm=rm, logf=_quiet()[1])
    check("부모 불일치", not out["ok"] and any(f"#{c['hud']}: Redmine 부모" in d for d in out["differences"]))
    rm, c = _made()
    rm.relations = [r for r in rm.relations if not (r["issue_id"] == c["pre"] and r["issue_to_id"] == c["inv"])]
    rm.create_relation(c["hud"], c["inv"])
    out = WF.check(ROOT, rm=rm, logf=_quiet()[1])
    d = " / ".join(out["differences"])
    check("없는 관계", f"Redmine 에 없는 선행 관계 #{c['pre']}→#{c['inv']}" in d, d)
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
    out = WF.create_map(ROOT, "전투", specs, confirm=True, user_answer="응", rm=rm, logf=_quiet()[1])
    c = out["created"]
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
    check("부모·표지", rm.issues[new]["parent"] == c["A1a"]
          and MB.parse_node(rm.issues[new]["description"]).root == ROOT)
    check("선행 관계", any(r["issue_id"] == c["A1a"] and r["issue_to_id"] == new for r in rm.relations))
    st = {x.id: x.state for x in MB.parse(rm.issues[ROOT]["description"]).nodes}
    check("재검증 표시", all(st[i] == "재검증" for i in p["reverify"]))
    check("하위 나무 유지", st[c["A2x"]] == "완료" and st[c["Bx"]] == "완료")
    check("새 노드 차단(선행 재검증)", st[new] == "차단")
    notes = {i: [j["notes"] for j in rm.issues[i]["journals"]] for i in p["reverify"]}
    check("재검증 노트", all(f"#{new} 추가로 재검증 대상 — 맵 Root #{ROOT}" in v for v in notes.values()))
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
    WF.create_map(ROOT, "HUD", SPECS, confirm=True, user_answer="응", rm=rm, logf=seen.append)
    writes = len(rm.writes())
    check("쓰기마다 로그", sum(x.startswith("쓰기 —") for x in seen) == writes, f"{seen}")
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        WF.claim(ROOT, 1002, "x", rm=rm)
    check("기본 로그는 stderr [wayfinder]", buf.getvalue().startswith("[wayfinder] 거절"))


def test_end_to_end_direct():
    """MCP 없이 모듈 함수만으로 한 바퀴 — C8 근거."""
    rm = _fresh()
    log = []
    pv = WF.create_map(ROOT, "HUD", SPECS, rm=rm, logf=log.append)
    ok = pv["ok"] and not rm.writes()
    c = WF.create_map(ROOT, "HUD", SPECS, fog=["저장 형식"], confirm=True, user_answer="응", rm=rm,
                      logf=log.append)["created"]
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
    rm.issues[reg["id"]]["status"] = "완료"
    ok &= WF.on_node_closed(reg["id"], rm=rm, logf=log.append)["ok"]
    ok &= not WF.close_root(ROOT, confirm=True, user_answer="응", rm=rm, logf=log.append)["ok"]  # 안개
    blk = MB.parse(rm.issues[ROOT]["description"])            # 사람이 안개를 걷었다
    blk.fog = []
    rm.issues[ROOT]["description"] = MB.put(rm.issues[ROOT]["description"], blk)
    st = WF.frontier(ROOT, rm=rm)["states"]
    ok &= st["완료"] == 5
    ok &= WF.close_root(ROOT, confirm=True, user_answer="응", rm=rm, logf=log.append)["ok"]
    check("직접 호출 한 바퀴", ok, "\n".join(log[-10:]))


def main() -> int:
    for fn in (test_create_map_preview, test_create_map_confirm, test_create_map_refusals,
               test_title_validation, test_compute_states, test_check, test_sync,
               test_sync_keeps_reverify, test_on_node_closed, test_propose_node, test_register_node,
               test_claim, test_mark_verified, test_close_root, test_logs, test_end_to_end_direct):
        try:
            fn()
        except Exception as e:                       # noqa: BLE001
            check(f"{fn.__name__} 예외 없음", False, f"{type(e).__name__}: {e}")
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_wayfinder: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
