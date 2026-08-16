"""소 2.1.1~2.1.3 도메인 색인 — 페이로드 · 지문 · [중요] 노이즈 3중 차단.

**무거운 임베딩을 부르지 않는다.** 벡터 채널은 별도 컬렉션이라 없으면 그냥 0건이 되고,
여기서 지켜야 하는 계약은 **BM25 가 0건이면 도메인이 끼어들지 않는다** 쪽이다.

`python3 master/test_domain_index.py`
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_search import domain_index as di        # noqa: E402
from master.context_search.paths import ProjectPaths        # noqa: E402
from master.ontology import yaml_io                          # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _project(tmp: Path) -> ProjectPaths:
    """도메인 패키지 2개를 가진 최소 프로젝트."""
    paths = ProjectPaths(name="T", root=tmp)
    root = tmp / "ontology" / "domains"

    d = root / "MissionRuntime"
    yaml_io.write(d / "domain.yaml", {
        "domain": "MissionRuntime", "tier": 3,
        "summary": "미션의 생명주기와 실행을 관리한다",
        "tags": ["mission", "task"],
        "core_responsibilities": ["태스크 순차 실행"],
        "objects": ["L3/objects/UMissionTaskExecutor.yaml",
                    "L1/objects/UMissionTaskBase.yaml"],
        "actions": ["L3/actions/RunTask.yaml"],
        "invariants_files": ["L3/invariants/ServerOnly.yaml"],
        "collaborates_with": ["GlobalEventSystem"],
    })
    yaml_io.write(d / "L3/actions/RunTask.yaml", {
        "name": "RunTask", "kind": "Action",
        "description": "태스크 한 건을 실행한다",
        "implementation": {"primary": "UMissionTaskExecutor::Run"},
        "flow": [{"step": 1, "actor": "UMissionTaskExecutor",
                  "operation": "실행", "target": "UMissionTaskBase"}],
        "triggers_events": ["OnTaskCompleted"], "evidence": "X.cpp:1",
    })
    yaml_io.write(d / "L3/invariants/ServerOnly.yaml", {
        "name": "ServerOnly", "text": "서버 권한에서만 등록된다",
        "evidence": "X.cpp:9", "source_signal": "algorithm",
    })

    g = root / "GlobalEventSystem"
    yaml_io.write(g / "domain.yaml", {
        "domain": "GlobalEventSystem", "tier": 2,
        "summary": "전역 이벤트 디스패치",
        "tags": ["event"], "objects": ["L1/objects/FGlobalEventSystem.yaml"],
    })
    return paths


def test_payload() -> None:
    with tempfile.TemporaryDirectory() as t:
        paths = _project(Path(t))
        ms = di.manifests(paths)
        check("manifest 만 색인 대상", len(ms) == 2 and all(m.name == "domain.yaml" for m in ms),
              str([str(m) for m in ms]))

        pl = di.payload(paths.ontology / "domains" / "MissionRuntime" / "domain.yaml")
        check("도메인명이 file_id", pl["file_id"] == "MissionRuntime")
        check("[중요] 도메인명이 태그 채널에 들어간다", "MissionRuntime" in pl["tags"], str(pl["tags"]))
        check("objects 경로 → 클래스명(stem)",
              set(pl["related_classes"]) == {"UMissionTaskExecutor", "UMissionTaskBase"},
              str(pl["related_classes"]))
        # [중요] 이게 이 모듈의 핵심 — 항목 본문이 안 녹으면 액션·invariant 로 검색이 안 된다
        check("[중요] 액션 본문이 body 에 녹는다", "태스크 한 건을 실행한다" in pl["body"])
        check("[중요] invariant 본문이 body 에 녹는다", "서버 권한에서만 등록된다" in pl["body"])
        check("flow 의 actor/operation 도 녹는다", "UMissionTaskExecutor 실행" in pl["body"])
        check("발행 이벤트도 녹는다", "OnTaskCompleted" in pl["body"])
        check("collaborates_with 는 메타로만", pl["collaborates_with"] == ["GlobalEventSystem"])
        check("tier 보존", pl["tier"] == 3)

        bad = Path(t) / "none.yaml"
        check("없는 파일은 None", di.payload(bad) is None)


def test_fingerprint_and_sync() -> None:
    with tempfile.TemporaryDirectory() as t:
        paths = _project(Path(t))
        fp1 = di.fingerprint(paths)
        check("지문이 나온다", bool(fp1))
        check("같은 상태면 같은 지문", fp1 == di.fingerprint(paths))

        # [중요] manifest 가 아니라 **항목** 을 바꿔도 지문이 바뀌어야 한다
        p = paths.ontology / "domains" / "MissionRuntime" / "L3/actions/RunTask.yaml"
        d = yaml_io.read(p)
        d["description"] = "바뀐 설명"
        p.write_text(yaml_io.dump(d) + "\n" + " " * 0, encoding="utf-8")
        check("[중요] 항목 파일이 바뀌면 지문이 바뀐다", di.fingerprint(paths) != fp1)

        st = di.sync(paths, force=True)
        check("색인 2건", st.synced == 2, st.summary)
        check("BM25 행이 생긴다", st.bm25_count == 2, st.summary)
        check("DB 파일이 생긴다", paths.bm25_domains_db.is_file())
        check("지문 스탬프가 남는다", bool(di.stored_fingerprint(paths)))

        again = di.sync(paths)
        check("[중요] 안 바뀌면 건너뛴다", again.skipped_unchanged, again.summary)
        check("[중요] 건너뛸 때 0 을 보고하지 않는다", again.synced == 2, again.summary)


def test_empty_is_an_error() -> None:
    with tempfile.TemporaryDirectory() as t:
        paths = ProjectPaths(name="T", root=Path(t))
        try:
            di.sync(paths)
            check("[중요] 대상 0이면 예외", False, "예외가 안 났다")
        except di.DomainIndexError:
            check("[중요] 빈 색인을 성공으로 보고하지 않는다", True)


def test_noise_gate() -> None:
    """[중요] 이 절이 소 2.1.2 다 — 빼면 조용히 나빠진다."""
    with tempfile.TemporaryDirectory() as t:
        paths = _project(Path(t))
        di.sync(paths, force=True)

        hits = di.search_norms(paths, "미션 태스크")
        check("관련 질의는 잡힌다", bool(hits), str(hits))
        if hits:
            check("도메인 이름이 온다", hits[0]["domain"] in {"MissionRuntime", "GlobalEventSystem"})
            check("경로를 준다(본문은 호출자가 읽는다)", hits[0]["path"].endswith("domain.yaml"))
            check("source 라벨", hits[0]["source"] in {"bm25", "vector", "vector+bm25"})

        check("[중요] ① 무관 질의는 0건 (BM25 0건 가드)",
              di.search_norms(paths, "김치찌개 끓이는 법") == [], "무관 질의가 잡혔다")
        check("[중요] ① 무관 영문도 0건",
              di.search_norms(paths, "quantum blockchain") == [])
        check("빈 질의도 0건", di.search_norms(paths, "") == [])

        # ③ 개수 상한
        many = di.search_norms(paths, "미션 이벤트 태스크 전역", top_k=1)
        check("[중요] ③ 개수 상한이 걸린다", len(many) <= 1, str(len(many)))

        # 액션 본문으로도 도메인이 잡혀야 한다 (payload 에 녹인 이유)
        check("[중요] 액션 이름으로 도메인이 잡힌다",
              any(h["domain"] == "MissionRuntime" for h in di.search_norms(paths, "RunTask")),
              str(di.search_norms(paths, "RunTask")))



def test_alias_lifts_to_tags() -> None:
    """[중요] 중 1.4.5 — 사람이 등록한 별칭이 **가중치 3.0 채널**에 올라가는가.

    실측 근거: 도메인 태그 118토큰 중 한글 4개(3%)뿐인데 본문엔 도메인마다 한글 887~1,740자.
    한글 질의가 최고 가중치 채널을 통째로 놓친다.
    """
    with tempfile.TemporaryDirectory() as t:
        paths = ProjectPaths(name="T", root=Path(t))
        d = paths.ontology / "domains" / "D"
        (d / "L1" / "objects").mkdir(parents=True)
        yaml_io.write(d / "L1/objects/AMonster.yaml",
                      {"name": "AMonster", "aliases": ["몬스터", "몹"]})
        yaml_io.write(d / "L1/objects/ABoss.yaml",
                      {"name": "ABoss", "aliases": ["보스", "몬스터"]})   # 중복 별칭
        yaml_io.write(d / "domain.yaml", {
            "domain": "D", "tags": ["UI"],
            "objects": ["L1/objects/AMonster.yaml", "L1/objects/ABoss.yaml"]})

        p = di.payload(d / "domain.yaml")
        tags = p["tags"]
        check("[중요] 별칭이 tags 채널에 올라간다", "몬스터" in tags and "보스" in tags, str(tags))
        check("기존 태그를 밀어내지 않는다", "UI" in tags and "D" in tags, str(tags))
        check("[중요] 중복은 한 번만", tags.count("몬스터") == 1, str(tags))
        # [중요] 별칭은 related_classes 가 아니라 tags 여야 한다 — 가중치가 다르다(2.5 vs 3.0)
        check("[중요] related 로 새지 않는다", "몬스터" not in p["related_classes"],
              str(p["related_classes"]))

        # 별칭이 없으면 예전과 똑같아야 한다 (하위호환)
        yaml_io.write(d / "L1/objects/AMonster.yaml", {"name": "AMonster"})
        yaml_io.write(d / "L1/objects/ABoss.yaml", {"name": "ABoss"})
        check("별칭이 없으면 태그가 늘지 않는다",
              di.payload(d / "domain.yaml")["tags"] == ["UI", "D"],
              str(di.payload(d / "domain.yaml")["tags"]))


def test_fingerprint_sees_aliases() -> None:
    """[중요] 중 1.4.3 — 별칭을 등록하면 지문이 바뀌어야 재색인이 걸린다."""
    with tempfile.TemporaryDirectory() as t:
        paths = ProjectPaths(name="T", root=Path(t))
        d = paths.ontology / "domains" / "D"
        (d / "L1" / "objects").mkdir(parents=True)
        obj = d / "L1/objects/AMonster.yaml"
        yaml_io.write(obj, {"name": "AMonster"})
        yaml_io.write(d / "domain.yaml",
                      {"domain": "D", "objects": ["L1/objects/AMonster.yaml"]})
        before = di.fingerprint(paths)
        yaml_io.write(obj, {"name": "AMonster", "aliases": ["몬스터"]})
        check("[중요] 항목에 별칭이 붙으면 지문이 바뀐다", di.fingerprint(paths) != before,
              f"{before} → {di.fingerprint(paths)}")



def test_norm_search_uses_expansion() -> None:
    """[중요] 규범 검색도 시소러스 확장을 써야 한다 (실측 2026-08-10).

    확장을 `ContextSearch.search()` 에만 붙였더니 「다이얼로그 매니저」가 엉뚱한 도메인을
    1위로 냈다(AlphaCoreGameFramework 1.500 → 확장하면 MissionSystemTools 5.233).
    **매니페스트의 규범 채널이 이 함수를 쓰므로, 빠지면 코드 생성이 틀린 규범을 받는다.**
    """
    src = (Path(__file__).resolve().parent / "context_search" / "domain_index.py").read_text("utf-8")
    i_expand = src.find("expand_for")
    i_bm25 = src.find("_bm25_hits(paths, query")
    check("[중요] search_norms 가 확장을 부른다", i_expand > 0, "expand_for 호출 없음")
    check("[중요] BM25 **전에** 확장한다", 0 < i_expand < i_bm25, f"{i_expand} vs {i_bm25}")


def main() -> int:
    for fn in (test_payload, test_fingerprint_and_sync, test_empty_is_an_error, test_noise_gate,
               test_alias_lifts_to_tags, test_fingerprint_sees_aliases,
               test_norm_search_uses_expansion):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_domain_index: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
