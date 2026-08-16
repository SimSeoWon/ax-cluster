"""레이어 책임 서술 테스트 — 소 3.1.4. pytest 없이 실행한다.

    .venv/bin/python master/test_descriptions.py

[중요] **LLM 은 주입으로 막는다.** 같은 세션에서 `dry_run` 이 LLM 을 안 막는다는 것을 겪었고
(테스트 하나가 360초를 먹었다), 이 모듈은 아예 호출 함수를 인자로 받게 이식했다.

여기서 고정하는 계약 셋: **비용 가드**(안 불러야 할 때 안 부른다) · **잠금 보존**(사람이
손본 서술을 덮지 않는다) · **환각 제거**(멤버 없는 레이어의 서술은 버린다).
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from master.context_search.paths import ProjectPaths          # noqa: E402
from master.ontology import descriptions as dm, package as pkg, yaml_io as y   # noqa: E402

PASS = FAIL = 0


def check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [완료] {label}")
    else:
        FAIL += 1
        print(f"  [실패] {label}" + (f" — {detail}" if detail else ""))


def _paths(tmp: Path, name: str) -> ProjectPaths:
    return ProjectPaths(name=name, root=tmp / name)


def _domain_md(paths: ProjectPaths, domain: str):
    d = paths.context / "_domains"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{domain}.md").write_text(
        "---\ntags: [미션]\n---\n\n# D\n\n## 시스템 개요\n\n미션 실행 도메인이다.\n"
        "\n## 핵심 책임\n\n- 태스크 실행\n- 상태 전이\n", encoding="utf-8")


def _item(paths, domain, layer, kind, name):
    p = paths.ontology / "domains" / domain / f"L{layer}" / kind / f"{name}.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    y.write(p, {"name": name})


GOOD = """설명을 곁들인 응답입니다.
{"layer_descriptions": {"1": "L1 은 계약을 진다.", "3": "L3 은 구현이 몰려 있다."}}
"""


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ax-desc-"))
    try:
        return _run(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _run(tmp: Path) -> int:
    print("\n[1] 멤버 수집 — 이름만, 본문은 안 읽는다")
    P = _paths(tmp, "M1")
    _domain_md(P, "D")
    _item(P, "D", 1, "objects", "IMissionContract")
    _item(P, "D", 3, "objects", "UMissionTask_Spawn")
    _item(P, "D", 3, "actions", "SpawnActor")
    mem = dm.collect_layer_members(P, "D")
    check("L1 오브젝트를 걷는다", mem[1]["objects"] == ["IMissionContract"], str(mem[1]))
    check("L3 은 종류별로 걷는다",
          mem[3]["objects"] == ["UMissionTask_Spawn"] and mem[3]["actions"] == ["SpawnActor"], str(mem[3]))
    check("멤버 없는 레이어는 빈 목록", not dm.has_content(mem[2]), str(mem[2]))

    print("\n[2] 프롬프트 — 멤버 있는 레이어만, 문구는 원전 그대로")
    p = dm.build_prompt("D", "미션 실행 도메인", ["태스크 실행"], mem)
    check("헤더가 원전 그대로", p.startswith(dm.PROMPT_HEADER), p[:40])
    check("L1 라벨이 들어간다", dm.LAYER_LABELS[1] in p)
    check("[중요] 멤버 없는 L2 는 안 들어간다", dm.LAYER_LABELS[2] not in p)
    check("도메인 요약·책임이 실린다", "미션 실행 도메인" in p and "태스크 실행" in p)
    check("멤버 이름이 실린다", "IMissionContract" in p and "SpawnActor" in p)
    many = {1: {"objects": [f"U{i:02d}" for i in range(40)], "actions": [], "invariants": []},
            2: {"objects": [], "actions": [], "invariants": []},
            3: {"objects": [], "actions": [], "invariants": []}}
    pm = dm.build_prompt("D", "", [], many)
    check("[중요] 상한을 넘으면 자르고 「외 N건」을 적는다", "외 15건" in pm, pm[-300:])

    print("\n[3] 응답 파싱 — 관대하게 읽고, 실패는 값으로")
    got, why = dm.parse_response(GOOD)
    check("JSON 블록만 골라 읽는다", got == {1: "L1 은 계약을 진다.", 3: "L3 은 구현이 몰려 있다."}, str(got))
    check("성공이면 사유가 없다", why == "", why)
    got2, why2 = dm.parse_response('{"layer_descriptions": {"L2": "본문", "9": "범위밖", "3": "  "}}')
    check("키는 L2 형태도 받는다", got2 == {2: "본문"}, str(got2))
    check("범위 밖·빈 서술은 버린다", 9 not in got2 and 3 not in got2, str(got2))
    for bad, tag in ((""              , "응답이 비었다"),
                     ("JSON 없음"      , "JSON 블록"),
                     ('{"x": 1}'      , "layer_descriptions"),
                     ('{"broken": '   , "JSON")):
        g, w = dm.parse_response(bad)
        check(f"[중요] 실패를 값으로 — {tag}", g == {} and tag.split()[0] in w, f"{bad!r} → {w!r}")

    print("\n[4] [중요] 비용 가드 — 부르지 말아야 할 때 안 부른다")
    calls = []
    call = lambda prompt: (calls.append(prompt) or GOOD)
    P2 = _paths(tmp, "M2")
    _domain_md(P2, "D")
    (P2.ontology / "domains" / "D").mkdir(parents=True, exist_ok=True)
    r0 = dm.extract(P2, "D", call=call)
    check("멤버 0이면 LLM 0", r0.llm_calls == 0 and len(calls) == 0, r0.summary)
    check("사유가 남는다", "멤버" in r0.reason, r0.reason)

    print("\n[5] 추출 → 쓰기 → 잠금 보존")
    P3 = _paths(tmp, "M3")
    _domain_md(P3, "D")
    _item(P3, "D", 1, "objects", "IMissionContract")
    _item(P3, "D", 3, "actions", "SpawnActor")
    res = dm.extract(P3, "D", call=call)
    check("LLM 을 한 번만 부른다", res.llm_calls == 1 and len(calls) == 1, str(res.llm_calls))
    check("멤버 있는 레이어의 서술만 남는다", set(res.descriptions) == {1, 3}, str(res.descriptions))
    st = dm.write(P3, "D", res.descriptions)
    check("두 레이어를 쓴다", st.written == 2, st.summary)
    d1 = P3.ontology / "domains" / "D" / "L1" / dm.FILENAME
    check("파일이 생겼다", d1.is_file())
    got = dm.read(d1)
    check("[중요] 자동 초안은 verified_by_user: false", got["verified_by_user"] is False, str(got))
    check("본문이 실렸다", got["body"] == "L1 은 계약을 진다.", str(got["body"]))
    st2 = dm.write(P3, "D", res.descriptions)
    check("같은 본문은 다시 안 쓴다 (mtime 보존)", st2.written == 0 and st2.unchanged == 2, st2.summary)

    # 사람이 손보고 잠근다
    d1.write_text(dm.dump("D", 1, "사람이 고친 서술", verified=True, created="2026-01-01"),
                  encoding="utf-8")
    st3 = dm.write(P3, "D", {1: "기계가 새로 뽑은 것", 3: res.descriptions[3]})
    check(" 검수 잠금을 덮지 않는다", st3.preserved_verified == 1, st3.summary)
    check("본문이 사람 것 그대로", dm.read(d1)["body"] == "사람이 고친 서술")
    calls.clear()
    _item(P3, "D", 1, "objects", "IMore")     # L1 은 잠겼지만 L3 은 안 잠겼다
    r2 = dm.extract(P3, "D", call=call)
    check("일부만 잠기면 여전히 부른다", r2.llm_calls == 1, r2.summary)
    d3 = P3.ontology / "domains" / "D" / "L3" / dm.FILENAME
    d3.write_text(dm.dump("D", 3, "이것도 사람이", verified=True), encoding="utf-8")
    calls.clear()
    r3 = dm.extract(P3, "D", call=call)
    check("[중요] 전부 잠기면 LLM 0", r3.llm_calls == 0 and not calls, r3.summary)
    check("그 사유가 값에 실린다", "잠김" in r3.reason, r3.reason)

    print("\n[6] [중요] 환각 레이어 제거 — 멤버 없는 레이어의 서술은 버린다")
    P4 = _paths(tmp, "M4")
    _domain_md(P4, "D")
    _item(P4, "D", 3, "objects", "UOnlyLeaf")
    r4 = dm.extract(P4, "D", call=lambda p: '{"layer_descriptions": {"1": "없는 L1", "3": "있는 L3"}}')
    check("멤버 있는 것만 남는다", set(r4.descriptions) == {3}, str(r4.descriptions))
    check("버린 것을 센다", r4.dropped_layers == [1], str(r4.dropped_layers))
    check("요약이 그것을 말한다", "환각" in r4.summary, r4.summary)

    print("\n[7] 빈 레이어 drift 정리 — [중요] 잠긴 것은 남긴다")
    P5 = _paths(tmp, "M5")
    _domain_md(P5, "D")
    _item(P5, "D", 3, "objects", "UOnlyLeaf")
    (P5.ontology / "domains" / "D" / "L2").mkdir(parents=True, exist_ok=True)
    (P5.ontology / "domains" / "D" / "L2" / dm.FILENAME).write_text(
        dm.dump("D", 2, "멤버가 사라진 레이어의 서술"), encoding="utf-8")
    (P5.ontology / "domains" / "D" / "L1").mkdir(parents=True, exist_ok=True)
    (P5.ontology / "domains" / "D" / "L1" / dm.FILENAME).write_text(
        dm.dump("D", 1, "사람이 잠근 서술", verified=True), encoding="utf-8")
    st5 = dm.write(P5, "D", {3: "L3 서술"})
    check("멤버 0인 레이어의 비검증 서술은 지운다", st5.removed == 1, st5.summary)
    check("[중요] 잠긴 것은 멤버가 없어도 남는다",
          (P5.ontology / "domains" / "D" / "L1" / dm.FILENAME).is_file())

    print("\n[8] 최초 생성일 보존 · 시간 주입")
    P6 = _paths(tmp, "M6")
    _domain_md(P6, "D")
    _item(P6, "D", 3, "objects", "UX")
    fixed = datetime(2026, 3, 4)
    dm.write(P6, "D", {3: "첫 서술"}, now=fixed)
    p3 = P6.ontology / "domains" / "D" / "L3" / dm.FILENAME
    check("주입한 날짜가 쓰인다", dm.read(p3)["created"] == "2026-03-04", str(dm.read(p3)))
    dm.write(P6, "D", {3: "고친 서술"}, now=datetime(2026, 9, 9))
    check("[중요] 본문을 갱신해도 created 는 보존", dm.read(p3)["created"] == "2026-03-04", str(dm.read(p3)))
    check("본문은 바뀐다", dm.read(p3)["body"] == "고친 서술")

    print("\n[9] [중요] `protected` — 받아온 스냅샷 서술을 우리 초안이 덮지 않는다")
    # 실측 2026-08-15: 트윈에 원전이 만든 description.md 7건이 이미 있고 **전부 미잠금**이다.
    # `verified_by_user` 만 봤으면 35B 초안이 그것을 덮었다 — 리포트 11 §20(우리 합성이
    # 스냅샷보다 얕다)이 겨눈 그 사고다. `package.locked_items` 와 같은 규약으로 맞췄다.
    P8 = _paths(tmp, "M8")
    _domain_md(P8, "D")
    _item(P8, "D", 3, "objects", "UX")
    d3 = P8.ontology / "domains" / "D" / "L3" / dm.FILENAME
    d3.parent.mkdir(parents=True, exist_ok=True)
    d3.write_text(dm.dump("D", 3, "받아온 스냅샷 서술", protected="원전 산출물 — 재생산 불가"),
                  encoding="utf-8")
    meta = dm.read(d3)
    check("protected 를 읽는다", meta["protected"] is True and not meta["verified_by_user"], str(meta))
    check("사유도 읽는다", "재생산 불가" in meta["protected_reason"], meta["protected_reason"])
    check("[중요] is_locked 가 둘을 함께 본다", dm.is_locked(meta))
    st8 = dm.write(P8, "D", {3: "기계가 새로 뽑은 것"})
    check("[중요] 보호된 서술을 덮지 않는다", st8.preserved_verified == 1 and st8.written == 0, st8.summary)
    check("본문이 스냅샷 그대로", dm.read(d3)["body"] == "받아온 스냅샷 서술")
    calls.clear()
    r8 = dm.extract(P8, "D", call=call)
    check("[중요] 전부 보호면 LLM 도 안 부른다", r8.llm_calls == 0 and not calls, r8.summary)

    print("\n[10] [중요] 서술이 실패해도 재합성을 죽이지 않는다 (합성기 배선)")
    from master.ontology import synth as sy
    P7 = _paths(tmp, "M7")
    _domain_md(P7, "D")
    _item(P7, "D", 3, "objects", "UX")
    orig = sy.generate
    sy.generate = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("노드 죽음"))
    try:
        note = sy.describe_domain(P7, "D")
    finally:
        sy.generate = orig
    check("예외를 던지지 않는다", isinstance(note, str), str(type(note)))
    check("[중요] 그리고 조용하지 않다", "노드 죽음" in note, note)

    print(f"\n{'='*46}\n통과 {PASS} · 실패 {FAIL}\n{'='*46}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
