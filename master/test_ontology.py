"""온톨로지 YAML 읽기·쓰기 테스트 — 소 1.3.4. pytest 없이 실행한다.

    .venv/bin/python master/test_ontology.py

🔴 이 모듈의 **유일한 계약은 왕복 보존**이다 — `dump` 한 것을 `load` 하면 값이 같아야 한다.
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
from master.ontology import stale as st_mod, yaml_io as y   # noqa: E402

PASS = FAIL = 0


def check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label}" + (f" — {detail}" if detail else ""))


def roundtrip(label, value):
    got = y.load(y.dump(value))
    check(label, got == value, f"{value!r} → {got!r}")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ax-onto-"))

    print("\n[1] 🔴 왕복 보존 — 이 모듈의 유일한 계약")
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

    print("\n[2] 🔴 따옴표가 필요한 값 (원본 규칙 그대로)")
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

    print("\n[4] 🔴 안 바뀌면 안 쓴다 (dirty 판정이 자기 자신을 트리거하지 않게)")
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

    print("\n[6] 🔴 실제 온톨로지 파일을 읽는다 (받아온 247개)")
    real = sorted((_ROOT / "ModularStage" / "ontology" / "domains").glob("*/domain.yaml"))
    if not real:
        check("도메인 manifest 발견", False, "없음 — 스킵")
    else:
        # 🔴 manifest 의 이름 키는 `name` 이 아니라 **`domain`** 이다 (object yaml 만 `name`).
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

    print("\n[7] 🔴 stale 판정 — 워터마크 두 개 비교 (소 1.3.8)")
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
    check("🔴 둘 다 -1 이면 stale 아니다 (첫 배포 폭주 방지)",
          st_mod.compute(P) == [], st_mod.summary(st_mod.compute(P)))
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

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'='*46}\n통과 {PASS} · 실패 {FAIL}\n{'='*46}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
