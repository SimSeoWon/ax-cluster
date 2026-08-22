"""온톨로지 YAML 읽기·쓰기 테스트 — 소 1.3.4. pytest 없이 실행한다.

    .venv/bin/python master/test_ontology.py

[중요] 이 모듈의 **유일한 계약은 왕복 보존**이다 — `dump` 한 것을 `load` 하면 값이 같아야 한다.
예쁜 YAML 을 만드는 것이 목적이 아니다. PyYAML 을 안 쓰는 이유(우리가 쓴 것만 우리가 읽는
닫힌 회로)가 그래서 성립한다.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from master.context_search.paths import ProjectPaths   # noqa: E402
from master.ontology import (collect as col, hierarchy as hx, layers as ly,  # noqa: E402
                             package as pkg, stale as st_mod,
                             verify_facts as vf, yaml_io as y)

PASS = FAIL = 0


def check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [완료] {label}")
    else:
        FAIL += 1
        print(f"  [실패] {label}" + (f" — {detail}" if detail else ""))


def roundtrip(label, value):
    got = y.load(y.dump(value))
    check(label, got == value, f"{value!r} → {got!r}")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ax-onto-"))

    print("\n[1] [중요] 왕복 보존 — 이 모듈의 유일한 계약")
    roundtrip("빈 매핑", {})
    roundtrip("스칼라 매핑", {"name": "AMonster", "tier": 2, "confidence": 0.85})
    roundtrip("불리언·null", {"verified_by_user": True, "locked": False, "parent": None})
    roundtrip("빈 리스트/매핑", {"aliases": [], "meta": {}})
    roundtrip("문자열 리스트", {"aliases": ["몬스터", "몹", "괴물"]})
    roundtrip("매핑 리스트", {"objects": [{"name": "AMonster", "tier": 1},
                                          {"name": "ABoss", "tier": 2}]})
    roundtrip("중첩 매핑", {"trigger": {"type": "event", "source": "EventBus"}})
    roundtrip("멀티라인", {"description": "첫 줄\n둘째 줄\n셋째 줄"})
    roundtrip("깊은 중첩", {"flow": [{"step": 1, "actor": "AMonster",
                                      "note": "여러\n줄"}]})

    print("\n[2] [중요] 따옴표가 필요한 값 (원본 규칙 그대로)")
    for label, v in (("콜론 포함", "Gameplay: Mission"), ("한글", "미션 시스템"),
                     ("예약어 문자열", "null"), ("예약어 true", "yes"),
                     ("대괄호", "[Identifier]"), ("작은따옴표", "it's"),
                     ("앞 공백", " lead"), ("빈 문자열", ""), ("해시", "a#b")):
        roundtrip(f"  {label}", {"v": v})
    check("예약어는 따옴표로 감싼다", y.scalar("null") == "'null'", y.scalar("null"))
    check("안전한 식별자는 그대로", y.scalar("AMonster") == "AMonster")
    check("경로도 그대로", y.scalar("Source/Game/A.h") == "Source/Game/A.h")

    print("\n[3] 실제 산출물 모양 (도메인 manifest·object)")
    manifest = {
        "name": "MissionRuntime", "tier": 2, "status": "active",
        "summary": "미션 실행을 담당한다.\n런타임에서 태스크를 진행한다.",
        "objects": ["L1/objects/AMonster.yaml", "L2/objects/UMissionTask.yaml"],
        "invariants": [], "actions": ["L2/actions/SpawnMonster.yaml"],
    }
    roundtrip("도메인 manifest", manifest)
    obj = {"name": "AMonster", "kind": "Object", "tier": 1, "layer": 1,
           "file": "Source/Game/Monster.h", "confidence": 0.9,
           "verified_by_user": False, "source_commit": "bc4b38f4",
           "aliases": ["몬스터", "몹"],
           "evidence": [{"file": "Source/Game/Monster.h", "line": 12}]}
    roundtrip("object yaml", obj)

    print("\n[4] [중요] 안 바뀌면 안 쓴다 (dirty 판정이 자기 자신을 트리거하지 않게)")
    f = tmp / "d" / "domain.yaml"
    check("첫 쓰기는 True", y.write(f, manifest) is True)
    before = f.stat().st_mtime_ns
    check("같은 내용이면 False", y.write(f, manifest) is False)
    check("  mtime 도 그대로", f.stat().st_mtime_ns == before)
    m2 = dict(manifest, tier=3)
    check("바뀌면 True", y.write(f, m2) is True)
    check("읽어서 확인", y.read(f) == m2)
    check("임시 파일이 안 남는다", not list(f.parent.glob("*.tmp")))

    print("\n[5] 없는 파일은 None (빈 dict 로 위장하지 않는다)")
    check("read → None", y.read(tmp / "없음.yaml") is None)
    check("빈 텍스트 → {}", y.load("") == {})
    check("주석만 → {}", y.load("# 설명\n# 더\n") == {})
    check("주석이 섞여도 값은 읽는다", y.load("# c\nname: A\n") == {"name": "A"})

    print("\n[6] [중요] 실제 온톨로지 파일을 읽는다 (받아온 247개)")
    real = sorted((_ROOT / "ModularStage" / "ontology" / "domains").glob("*/domain.yaml"))
    if not real:
        check("도메인 manifest 발견", False, "없음 — 스킵")
    else:
        # [중요] manifest 의 이름 키는 `name` 이 아니라 **`domain`** 이다 (object yaml 만 `name`).
        # 첫 판 테스트가 `name` 을 단언해 7개 전부 실패했다 — 코드가 아니라 단언이 틀렸다.
        ok = sum(1 for p in real
                 if isinstance(y.read(p), dict) and (y.read(p) or {}).get("domain"))
        check(f"manifest {len(real)}개를 읽고 domain 을 얻는다", ok == len(real), f"{ok}/{len(real)}")
        d0 = y.read(real[0])
        check("  중첩 매핑(layer_counts)도 읽는다", isinstance(d0.get("layer_counts"), dict),
              str(d0.get("layer_counts")))
        check("  리스트(objects)도 읽는다", len(d0.get("objects") or []) > 0)
        s0 = d0.get("summary") or ""
        check("  따옴표 안의 백틱·한글 요약이 온전하다",
              "`" in s0 and any("가" <= c <= "힣" for c in s0) and len(s0) > 80, s0[:50])
        objs = sorted((_ROOT / "ModularStage" / "ontology" / "domains").glob("*/L*/objects/*.yaml"))
        got = [y.read(p) for p in objs[:40]]
        named = sum(1 for d in got if isinstance(d, dict) and d.get("name"))
        check(f"object yaml 40개 중 name 을 얻는다", named >= 38, f"{named}/40")

    print("\n[7] [중요] stale 판정 — 워터마크 두 개 비교 (소 1.3.8)")
    P = ProjectPaths(name="S", root=tmp / "S")
    (P.ontology / "domains" / "D" / "L1" / "objects").mkdir(parents=True, exist_ok=True)
    y.write(P.ontology / "domains" / "D" / "domain.yaml",
            {"domain": "D", "objects": ["L1/objects/AMonster.yaml"]})
    y.write(P.ontology / "domains" / "D" / "L1" / "objects" / "AMonster.yaml",
            {"name": "AMonster", "file": "Source/Game/Monster.h"})

    def put_doc(commit):
        d = P.context / "Source" / "Game"
        d.mkdir(parents=True, exist_ok=True)
        body = "---\ntags: [x]\n---\n\n## 요약\n본문"
        if commit:
            body = body.replace("tags: [x]", f"tags: [x]\nsource_commit: {commit}")
        (d / "Monster.md").write_text(body, encoding="utf-8")

    check("활성 도메인을 찾는다 (status 키가 없으면 active)",
          st_mod.active_domains(P) == ["D"], str(st_mod.active_domains(P)))
    put_doc(None)
    # [중요] **계약이 바뀌었다** (`#275`, 2026-08-23). 종전엔 양쪽 `-1` 이면 결과에 **안 나왔다**
    #    — 그것이 「첫 배포 폭주 방지」의 방법이었지만, 동시에 **82%를 조용히 통과**시켰다
    #    (실측: 도메인 멤버 112건 중 92건). 지금은 **나오되 재합성을 부르지 않는다.**
    #    의도(폭주 방지)는 그대로이고, 침묵만 없앴다.
    _r0 = st_mod.compute(P)
    check("[중요] 둘 다 -1 이면 **판정 불가로 드러난다** (침묵 아님)",
          len(_r0) == 1 and _r0[0].undecidable and _r0[0].unknown == 1,
          st_mod.summary(_r0))
    check("[중요] 그래도 stale 이 아니다 — 첫 배포 폭주 방지는 그대로",
          not _r0[0].stale, st_mod.summary(_r0))
    check("요약이 「최신」으로 말하지 않는다",
          "알 수 없다" in st_mod.summary(_r0), st_mod.summary(_r0))
    put_doc("bc4b38f4")
    r = st_mod.compute(P)
    check("문서에 커밋이 찍히면 stale", len(r) == 1 and r[0].stale, st_mod.summary(r))
    check("  사유에 분모가 있다", r and r[0].reason == "stale=1/1", r[0].reason if r else "")
    check("  어느 클래스가 왜인지 남긴다",
          r and r[0].members == [("AMonster", "-1", "bc4b38f4")], str(r[0].members if r else ""))
    check("요약이 사람이 읽을 수 있다", "D(stale=1/1)" in st_mod.summary(r), st_mod.summary(r))
    check("stale 이 없으면 그렇게 말한다", "없다" in st_mod.summary([]))
    check("컨텍스트 문서 경로가 합성기 그룹 규칙과 같다",
          st_mod.context_doc_for(P, "Source/Game/Monster.cpp").name == "Monster.md")
    check("문서가 없으면 -1", st_mod.latest_commit(P, "Source/없는/X.h") == "-1")
    check("빈 소스 경로도 -1", st_mod.latest_commit(P, "") == "-1")
    check("멤버 없는 도메인은 건너뛴다", st_mod.compute(P, ["없는도메인"]) == [])

    print("\n[8] [중요] 레이어 추정 — 구조 우선, git 은 강등만 (소 1.3.5, LLM 0)")
    #  ABase ← AMid ← ALeaf1/ALeaf2   ·  AOrphan(고립)
    members = {"ABase": "", "AMid": "ABase", "ALeaf1": "AMid", "ALeaf2": "AMid",
               "AOrphan": ""}
    es = {e.name: e for e in ly.estimate_domain(members)}
    check("루트(자손 있음, 깊이 0) → L1", es["ABase"].layer == 1, es["ABase"].summary)
    check("  자손 3 이상이면 확신이 높다", es["ABase"].confidence == 0.8, str(es["ABase"].confidence))
    check("중간 기반(부모도 자식도) → L2", es["AMid"].layer == 2, es["AMid"].summary)
    check("리프 → L3", es["ALeaf1"].layer == 3 and es["ALeaf2"].layer == 3)
    check("[중요] 고립 클래스도 L3 (리프다)", es["AOrphan"].layer == 3, es["AOrphan"].summary)
    d = ly.distribution(list(es.values()))
    check("[중요] L3 가 0 이 아니다 (동등 투표 평균의 실패 재발 감지)", d[3] >= 2, str(d))
    check("분포가 합계와 맞는다", d[1] + d[2] + d[3] + d["locked"] == len(members), str(d))

    check("도메인 밖 부모는 잇지 않는다 (엔진 클래스 오염 방지)",
          ly.build_member_graph({"A": "AActor"})[0] == {}, "")
    check("자손 수를 센다", ly.descendant_count("ABase", ly.build_member_graph(members)[1]) == 3)
    check("깊이를 센다", ly.internal_depth("ALeaf1", ly.build_member_graph(members)[0]) == 2)

    cyc = {"A": "B", "B": "A"}
    pm, cm = ly.build_member_graph(cyc)
    check("[중요] 순환에서 멈춘다 (상속 그래프를 DAG 로 믿지 않는다)",
          ly.internal_depth("A", pm) >= 0 and ly.descendant_count("A", cm) >= 0)

    print("\n[8-1] git 보정 — 하향만, 상향 없음")
    calls = []
    real = ly.count_commits
    ly.count_commits = lambda repo, file, **kw: calls.append(file) or 99
    try:
        e2 = {e.name: e for e in ly.estimate_domain(
            members, files={n: f"Source/{n}.h" for n in members}, repo=Path("."))}
        check("[중요] 고churn L2 는 L3 로 강등", e2["AMid"].layer == 3, e2["AMid"].summary)
        check("  강등 표시가 남는다", e2["AMid"].signals["git_demoted"] is True)
        check("[중요] 리프를 L2 로 올리지 않는다 (git=0 과 '진짜 안정' 을 구분 못 한다)",
              e2["ALeaf1"].layer == 3)
        check("  루트는 강등 대상이 아니다", e2["ABase"].layer == 1)
    finally:
        ly.count_commits = real
    check("repo 가 없으면 git 을 안 부른다",
          ly.estimate("X", parent_map={}, children_map={}).signals["commits_90d"] == 0)

    print("\n[8-2] [중요] 검수 잠금은 추정하지 않는다")
    lk = {e.name: e for e in ly.estimate_domain(members, locked={"AMid"})}
    check("잠긴 멤버는 건너뛴다", lk["AMid"].locked and lk["AMid"].layer == 0, lk["AMid"].summary)
    check("  나머지는 그대로 추정", lk["ABase"].layer == 1)
    check("  분포가 잠금을 따로 센다", ly.distribution(list(lk.values()))["locked"] == 1)

    print("\n[9] [중요] 관계 수집 — 자동 확장이 아니라 제안 (중 1.3 입력)")
    from master.graph import class_graph as cg2

    G = ProjectPaths(name="G2", root=tmp / "G2")
    (G.source / "Game").mkdir(parents=True, exist_ok=True)
    (G.source / "Game" / "Base.h").write_text(
        "class ABase {};\nclass AMid : public ABase {};\n", encoding="utf-8")
    (G.source / "Game" / "Leaf.h").write_text(
        '#include "Base.h"\nclass ALeaf : public AMid {};\n', encoding="utf-8")
    (G.source / "Game" / "Helper.h").write_text(
        '#include "Leaf.h"\nclass AHelper {};\n', encoding="utf-8")
    FILES = ["Source/Game/Base.h", "Source/Game/Leaf.h", "Source/Game/Helper.h"]

    def gl(repo, *a):
        return (0, "\n".join(FILES)) if a[0] == "ls-files" else (0, "")

    cg2.build_full(G, git=gl)
    from master.graph import dependency as dep2
    dep2.build_full(G, git=gl)

    # [중요] 멤버 파일 기준 **1홉** 이웃만 본다 — AHelper 는 Leaf.h 를 include 하므로
    # 멤버에 ALeaf(Leaf.h)가 있어야 이웃으로 잡힌다. 첫 판 테스트가 2홉을 기대해 틀렸다.
    pr = col.propose(G, "D", {"AMid": "Source/Game/Base.h", "ALeaf": "Source/Game/Leaf.h"})
    names = {c.name: c for c in pr.candidates}
    check("조상을 후보로 낸다", "ABase" in names, str(sorted(names)))
    check("  근거를 붙인다", "조상" in names["ABase"].why, names["ABase"].why)
    check("  어느 멤버를 통해 왔는지 남긴다", names["ABase"].via in ("AMid", "ALeaf"),
          names["ABase"].via)
    check("[중요] 이미 멤버인 것은 후보에 없다", "AMid" not in names and "ALeaf" not in names)
    pr2 = col.propose(G, "D", {"AMid": "Source/Game/Base.h"})
    n2 = {c.name: c for c in pr2.candidates}
    check("자식을 후보로 낸다", "ALeaf" in n2 and "자식" in n2["ALeaf"].why,
          n2["ALeaf"].why if "ALeaf" in n2 else "없음")
    check("#include 이웃도 본다", "AHelper" in names, str(sorted(names)))

    print("\n[9-1] [중요] 제안이지 자동 추가가 아니다")
    check("멤버를 바꾸지 않는다", pr.members == ["ALeaf", "AMid"], str(pr.members))
    q = pr.question
    check("물어볼 문장을 만든다", "포함할까" in q, q[:80])
    check("  근거별로 묶는다", "조상" in q or "이웃" in q, q[:120])
    check("  넣지 않을 자유를 명시한다", "그대로 두면" in q)
    empty = col.Proposal(domain="E", members=["A"])
    check("후보가 없으면 없다고 말한다 (채우지 않는다)",
          "찾지 못했다" in empty.question, empty.question[:60])
    check("  empty 판정", empty.empty)
    check("요약에 분모가 있다", "멤버 2" in pr.summary and "후보" in pr.summary, pr.summary)

    print("\n[9-2] 그래프가 없어도 죽지 않는다")
    NG = ProjectPaths(name="NG", root=tmp / "NG")
    p2 = col.propose(NG, "D", {"X": "Source/X.h"})
    check("빈 제안을 돌려준다", p2.empty and p2.members == ["X"], p2.summary)
    check("  물어볼 것도 없다고 말한다", "찾지 못했다" in p2.question)

    print("\n[10] [중요] 개념 계층 — 하위 문서를 object 로 (소 1.3.10)")
    H = ProjectPaths(name="H", root=tmp / "H")
    for d in ("Top", "Mid", "Leaf"):
        y.write(H.ontology / "domains" / d / "domain.yaml", {"domain": d, "objects": []})
    y.write(H.ontology / "domains" / "Leaf" / "L1" / "objects" / "AThing.yaml",
            {"name": "AThing", "file": "Source/T.h"})
    y.write(H.ontology / "domains" / "Leaf" / "domain.yaml",
            {"domain": "Leaf", "objects": ["L1/objects/AThing.yaml"]})

    r = hx.add_child(H, "Top", "Mid")
    check("하위 문서를 건다", r.ok and r.status == "added", r.note)
    check("  직계 하위로 보인다", hx.children(H, "Top") == ["Mid"], str(hx.children(H, "Top")))
    check("  하위에도 부모가 적힌다",
          (y.read(H.ontology / "domains" / "Mid" / "domain.yaml") or {}).get("parent_domain") == "Top")
    check("같은 것을 또 걸면 noop", hx.add_child(H, "Top", "Mid").status == "noop")
    hx.add_child(H, "Mid", "Leaf")
    check("전이적 하위를 찾는다", set(hx.descendants(H, "Top")) == {"Mid", "Leaf"},
          str(hx.descendants(H, "Top")))

    print("\n[10-1] [중요] 순환을 막는다 (문서 참조는 새 축이다)")
    c = hx.add_child(H, "Leaf", "Top")
    check("순환이 되는 연결을 거부한다", c.status == "cycle", c.note)
    check("  사유를 말한다", "순환" in c.note, c.note)
    check("자기 자신도 거부", hx.add_child(H, "Top", "Top").status == "cycle")
    check("없는 도메인은 not_found", hx.add_child(H, "Top", "없음").status == "not_found")

    print("\n[10-2] [중요] 하위 문서 참조는 클래스가 아니다")
    check("kind 로 구분한다", hx.is_domain_ref({"name": "Mid", "kind": "domain"}))
    check("  kind 가 없으면 클래스 (기존 파일 호환)", not hx.is_domain_ref({"name": "AThing"}))
    check("class_members 는 문서 참조를 뺀다", hx.class_members(H, "Top") == {},
          str(hx.class_members(H, "Top")))
    check("  recursive 면 하위의 클래스를 합친다",
          "AThing" in hx.class_members(H, "Top", recursive=True),
          str(hx.class_members(H, "Top", recursive=True)))
    check("[중요] stale 도 문서 참조를 클래스로 세지 않는다",
          st_mod._members(H, "Top") == {}, str(st_mod._members(H, "Top")))
    check("트리를 낸다", hx.tree(H)["Top"] == ["Mid"], str(hx.tree(H)))
    check("루트를 찾는다", hx.roots(H) == ["Top"], str(hx.roots(H)))

    print("\n[11] [중요] 온톨로지 사실 게이트 — 호출 관계를 실측과 대조 (1.3.3 선행)")
    V = ProjectPaths(name="V", root=tmp / "V")
    (V.source / "G").mkdir(parents=True, exist_ok=True)
    (V.source / "G" / "M.h").write_text(
        "class UManager : public UObject { void RunTask(); };\n"
        "class UWorker : public UObject { void Step(); };\n", encoding="utf-8")
    from master.graph import class_graph as cg3

    def gl2(repo, *a):
        return (0, "Source/G/M.h") if a[0] == "ls-files" else (0, "")

    cg3.build_full(V, git=gl2)

    r = vf.verify_object(V, {"name": "UManager", "file": "Source/G/M.h"})
    check("실재하는 클래스는 통과", r.ok, r.reason)
    r = vf.verify_object(V, {"name": "UGhost", "file": "x.h"})
    check("[중요] 없는 클래스를 잡는다", not r.ok and r.findings[0].kind == "ghost_class", r.reason)
    r = vf.verify_object(V, {"name": "UManager", "file": "Source/틀린/M.h"})
    check("[중요] 파일 경로가 다르면 잡는다", not r.ok and r.findings[0].kind == "wrong_file", r.reason)
    check("하위 문서 참조는 검사하지 않는다",
          vf.verify_object(V, {"name": "Mid", "kind": "domain"}).ok)

    print("\n[11-1] [중요] 호출 관계")
    ok_a = {"name": "RunMission", "objects_affected": ["UManager"],
            "implementation": {"primary": "UManager::RunTask()"}}
    check("실재하는 호출은 통과", vf.verify_action(V, ok_a).ok, vf.verify_action(V, ok_a).reason)
    bad = {"name": "X", "implementation": {"primary": "UManager::NoSuchMethod()"}}
    r = vf.verify_action(V, bad)
    check("[중요] 없는 메서드 호출을 잡는다",
          not r.ok and r.findings[0].kind == "ghost_method", r.reason)
    r = vf.verify_action(V, {"name": "X", "objects_affected": ["UGhost"]})
    check("[중요] 없는 클래스를 objects_affected 에서 잡는다",
          not r.ok and r.findings[0].kind == "ghost_class", r.reason)
    eng = {"name": "X", "implementation": {"primary": "AActor::Tick()"}}
    check("[중요] 엔진 클래스는 봐준다 (모르는 것을 틀렸다고 하지 않는다)",
          vf.verify_action(V, eng).ok, vf.verify_action(V, eng).reason)
    r = vf.verify_action(V, {"name": "X", "flow": [{"step": 1, "target": "UWorker::Step()"}]})
    check("flow 의 target 도 본다", r.ok, r.reason)
    amb = {"name": "X", "implementation": {"primary": "UManager::SomeMember"}}
    check("[중요] 괄호 없는 표기는 봐준다 (enum 값·UPROPERTY 오탐 방지 — 실측)",
          vf.verify_action(V, amb).ok, vf.verify_action(V, amb).reason)
    r = vf.verify_action(V, {"name": "X", "flow": [{"step": 1, "target": "UWorker::Nope()"}]})
    check("  거기서도 잡는다", not r.ok, r.reason)

    print("\n[11-2] [중요] 게이트가 닫혀 있으면 검사하지 않는다")
    E = ProjectPaths(name="E2", root=tmp / "E2")
    r = vf.verify_action(E, ok_a)
    check("그래프가 없으면 검사 안 함", r.ok and "비었다" in r.skipped_reason, r.reason)
    check("  사유를 말한다", "검사 못 함" in r.reason, r.reason)
    real = cg3.methods_ready
    cg3.methods_ready = lambda p: False
    try:
        r = vf.verify_action(V, bad)
        check("[중요] methods 가 비면 검사 안 함 (전수 거짓양성 방지)",
              r.ok and "전수 거짓양성" in r.skipped_reason, r.reason)
    finally:
        cg3.methods_ready = real

    print("\n[12] [중요] 패키지 쓰기 — 검수 잠금은 덮지 않는다 (소 1.3.3 의 LLM 0 부분)")
    W = ProjectPaths(name="W", root=tmp / "W")
    objs = [{"name": "AAlpha", "layer": 1, "file": "a.h"},
            {"name": "ABeta", "layer": 3, "file": "b.h"}]
    s1 = pkg.write(W, "D", objects=objs, actions=[], invariants=[])
    root = W.ontology / "domains" / "D"
    check("레이어 디렉토리로 나눈다", (root / "L1/objects/AAlpha.yaml").is_file()
          and (root / "L3/objects/ABeta.yaml").is_file(), s1.summary)
    man = y.read(root / "domain.yaml") or {}
    check("manifest 가 경로를 갖는다",
          "L1/objects/AAlpha.yaml" in (man.get("objects") or []), str(man.get("objects")))
    check("레이어가 없으면 L3 (보수적)",
          pkg._layer_of({}) == "L3" and pkg._layer_of({"layer": 2}) == "L2")
    s2 = pkg.write(W, "D", objects=objs, actions=[], invariants=[])
    check("[중요] 안 바뀌면 안 쓴다", s2.written == 0 and s2.unchanged >= 3, s2.summary)

    print("\n[12-1] [중요] verified_by_user 는 재합성이 덮지 않는다")
    lockf = root / "L1" / "objects" / "AAlpha.yaml"
    y.write(lockf, {"name": "AAlpha", "layer": 1, "file": "a.h",
                    "verified_by_user": True, "note": "사람이 손봤다"})
    s3 = pkg.write(W, "D", objects=[{"name": "AAlpha", "layer": 1, "file": "덮어쓰기.h"}],
                   actions=[], invariants=[])
    got = y.read(lockf) or {}
    check("[중요] 잠긴 항목이 그대로다",
          got.get("note") == "사람이 손봤다" and got.get("file") == "a.h", str(got))
    check("  통계가 잠금 보존을 센다", s3.locked_kept == 1, s3.summary)
    m = pkg.merge_preserve_locked([{"name": "A", "v": 1}], {"A": {"name": "A", "v": 9}})
    check("merge — 잠긴 이름은 하나만 남고", [i["name"] for i in m] == ["A"], str(m))
    check("  값은 잠긴 쪽", m[0]["v"] == 9)

    print("\n[12-2] prune — 사라진 항목은 지우되 잠긴 것은 남긴다")
    pkg.write(W, "D", objects=[{"name": "ABeta", "layer": 3, "file": "b.h"}],
              actions=[], invariants=[])
    check("[중요] 잠긴 파일은 안 지운다", lockf.is_file(), "지워졌다")
    pkg.write(W, "D", objects=[], actions=[], invariants=[])
    check("전부 비워도 잠긴 것은 남는다", lockf.is_file())

    print("\n[12-3] 안 준 종류는 건드리지 않는다")
    before = list((y.read(root / "domain.yaml") or {}).get("objects") or [])
    pkg.write(W, "D", actions=[{"name": "DoIt", "layer": 2}])
    after = y.read(root / "domain.yaml") or {}
    check("[중요] objects 를 안 주면 기존 목록이 남는다",
          list(after.get("objects") or []) == before, f"{before} → {after.get('objects')}")
    check("actions 는 새로 들어간다",
          "L2/actions/DoIt.yaml" in (after.get("actions") or []), str(after.get("actions")))
    check("invariants 키는 스냅샷 이름", pkg._manifest_key("invariants") == "invariants_files")
    check("파일명 금지문자를 바꾼다", pkg._safe("A/B:C") == "A_B_C")

    print("\n[12-4] [중요] 사람이 넣은 별칭은 재합성이 지우지 않는다 (중 1.4.2)")
    # [중요] 실측 2026-08-09로 재현한 결함이다: register() 가 aliases 를 쓴 뒤 재합성하면
    #    합성기가 오브젝트를 {name,file,layer} 로만 다시 만들어 별칭이 사라졌다.
    A = ProjectPaths(name="A", root=tmp / "A")
    aroot = A.ontology / "domains" / "D"
    pkg.write(A, "D", objects=[{"name": "AMonster", "layer": 1, "file": "m.h"}])
    mf = aroot / "L1/objects/AMonster.yaml"
    item = y.read(mf); item["aliases"] = ["몬스터", "몹"]; y.write(mf, item)

    pkg.write(A, "D", objects=[{"name": "AMonster", "layer": 1, "file": "m.h"}])
    check("[중요] 재합성해도 별칭이 남는다",
          (y.read(mf) or {}).get("aliases") == ["몬스터", "몹"], str(y.read(mf)))
    # [중요] 항목 잠금(verified_by_user)으로 막지 않는다 — 그러면 내용이 영영 개선되지 않는다
    check("[중요] 잠금을 걸지 않는다 (필드 단위 이월이다)",
          (y.read(mf) or {}).get("verified_by_user") is not True, str(y.read(mf)))
    check("합성이 준 값은 그대로 반영된다", (y.read(mf) or {}).get("file") == "m.h")

    # 계층이 바뀌어 파일 경로가 달라져도 따라가야 한다
    pkg.write(A, "D", objects=[{"name": "AMonster", "layer": 2, "file": "m.h"}])
    moved = aroot / "L2/objects/AMonster.yaml"
    check("[중요] 계층이 바뀌어도 별칭을 따라간다",
          (y.read(moved) or {}).get("aliases") == ["몬스터", "몹"], str(y.read(moved)))

    # 새 값이 있으면 덮지 않는다
    pkg.write(A, "D", objects=[{"name": "AMonster", "layer": 2, "file": "m.h",
                                "aliases": ["새것"]}])
    check("새 값이 있으면 이월하지 않는다",
          (y.read(moved) or {}).get("aliases") == ["새것"], str(y.read(moved)))

    shutil.rmtree(tmp, ignore_errors=True)
    print("\n[11-3] [중요] `이름 (주석)` 은 호출이 아니다 (실측 2026-08-10)")
    # 실측: target: "FGlobalEventSystem::PrivateHandler (ListenerMap)" 를 호출로 읽어
    #   정상 문서 9건을 유령으로 신고했다. PrivateHandler 는 소스에서 static TSharedPtr 멤버다.
    #   [중요] 저장소 원칙 — 정상 문서를 막는 게이트가 통과시키는 게이트보다 나쁘다.
    calls = lambda t: vf._CALL.findall(t)
    check("[중요] 공백 뒤 괄호는 호출이 아니다", calls("FGlobalEventSystem::PrivateHandler (ListenerMap)") == [])
    check("붙은 괄호는 호출이다", calls("FGlobalEventSystem::Init()") == [("FGlobalEventSystem", "Init")])
    check("인자가 있어도 호출", calls("UManager_Mission::RunTask(task)") == [("UManager_Mission", "RunTask")])
    check("괄호 없는 멤버는 여전히 무시", calls("EMissionType::Wait") == [])

    print("\n[12-5] [중요] MD 태그가 domain.yaml 로 전파된다 — 합치되 덮지 않는다 (#53)")
    import types
    M = ProjectPaths(name="M", root=tmp / "M")
    pkg.write(M, "D", objects=[{"name": "UFoo", "layer": 1, "file": "f.h"}])
    mroot = M.ontology / "domains" / "D"
    man = y.read(mroot / "domain.yaml"); man["tags"] = ["기존", "Shared"]; y.write(mroot / "domain.yaml", man)
    doc = types.SimpleNamespace(summary="개요", tags=["한글태그", "shared", "새것"])
    from master.ontology import synth as sy
    extra = sy._manifest_extra(M, "D", doc)
    check("MD 태그를 싣는다", "한글태그" in (extra.get("tags") or []), str(extra))
    # [중요] 사람이 yaml 에 직접 넣은 것을 잃으면 안 된다 — package.write 는 얕게 덮는다
    check("[중요] 기존 태그를 지우지 않는다", "기존" in extra["tags"], str(extra["tags"]))
    check("기존 것이 앞선다", extra["tags"][0] == "기존", str(extra["tags"]))
    check("대소문자 중복은 한 번만", sum(1 for t in extra["tags"] if t.lower() == "shared") == 1,
          str(extra["tags"]))
    check("요약도 함께", extra.get("summary") == "개요")
    check("MD 태그가 없으면 tags 키를 안 만든다",
          "tags" not in (sy._manifest_extra(M, "D", types.SimpleNamespace(summary="s", tags=[])) or {}))

    print(f"\n{'='*46}\n통과 {PASS} · 실패 {FAIL}\n{'='*46}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
