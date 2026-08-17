"""#169 로그 태깅 — 사이드카 CRUD·invariant 첨부·후보 리포트 계약 (원전 η.12.3 이식).

지키는 계약:
① upsert 는 tag 기준, 마지막 삭제는 파일째 (원전 그대로)
② 매치 없음 = `log_tags` 필드 **부재** (null 아님) — 실증 불가와 미확인의 구분
③ 리포트는 제안형 — 사이드카를 절대 쓰지 않고, 확정 등록분은 버리지 않고 표기한다
④ evidence 파서는 원전 정규식 그대로 — 서술형 evidence 는 빈 집합

실행: .venv/bin/python master/test_log_tags.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_search.paths import ProjectPaths  # noqa: E402
from master.ontology import log_candidates as lc  # noqa: E402
from master.ontology import log_tags as lt  # noqa: E402


def _twin(tmp: Path, domain: str = "MissionRuntime") -> ProjectPaths:
    paths = ProjectPaths(name="P", root=tmp)
    (paths.context / "_domains").mkdir(parents=True)
    (paths.context / "_domains" / f"{domain}.md").write_text(
        "---\nstatus: active\n---\n\n# " + domain + "\n\n## 시스템 개요\n\nx\n",
        encoding="utf-8")
    inv = paths.ontology / "domains" / domain / "L3" / "invariants"
    inv.mkdir(parents=True)
    (paths.ontology / "domains" / domain / "domain.yaml").write_text(
        f"domain: {domain}\n", encoding="utf-8")   # 뷰어 로더는 manifest 없으면 None
    (inv / "ExecutorStateConsistency.yaml").write_text(
        "name: ExecutorStateConsistency\n"
        "text: '상태 일관성'\n"
        "evidence: 'UMissionExecutor.cpp:142, MissionTypes.h:10'\n"
        "layer: 3\n", encoding="utf-8")
    (inv / "NarrativeOnly.yaml").write_text(
        "name: NarrativeOnly\n"
        "text: '서술형'\n"
        "evidence: 'Tick() 의 lock_guard 패턴'\n"
        "layer: 3\n", encoding="utf-8")
    return paths


def test_crud_roundtrip_and_last_delete_removes_file():
    with tempfile.TemporaryDirectory() as tmp:
        paths = _twin(Path(tmp))
        r = lt.set_impl(paths, "MissionRuntime", "LogMissionExec", "mission.LogExec.Enable",
                        related_invariants=["ExecutorStateConsistency"])
        assert r["status"] == "created", r
        r = lt.set_impl(paths, "MissionRuntime", "LogMissionExec", "mission.LogExec2.Enable")
        assert r["status"] == "updated" and r["entry_count"] == 1
        got = lt.list_impl(paths, "MissionRuntime")
        assert got["count"] == 1 and got["entries"][0]["cvar"] == "mission.LogExec2.Enable"
        # [중요] cvar 만 갱신해도 related_invariants 는 보존된다 (원전 upsert 계약)
        assert got["entries"][0]["related_invariants"] == ["ExecutorStateConsistency"]
        r = lt.remove_impl(paths, "MissionRuntime", "LogMissionExec")
        assert r["status"] == "deleted" and r["entry_count"] == 0
        p = lt.sidecar_path(paths.ontology / "domains" / "MissionRuntime")
        assert not p.exists(), "마지막 삭제는 파일째 지운다 (원전 그대로)"


def test_missing_domain_package_is_not_found():
    with tempfile.TemporaryDirectory() as tmp:
        paths = _twin(Path(tmp))
        assert lt.set_impl(paths, "없는도메인", "T", "c.v")["status"] == "not_found"
        assert lt.list_impl(paths, "없는도메인")["status"] == "not_found"


def test_empty_tag_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        paths = _twin(Path(tmp))
        assert lt.set_impl(paths, "MissionRuntime", "  ", "c.v")["status"] == "error"


def test_tags_for_invariant_absence_semantics():
    entries = [{"tag": "LogA", "cvar": "a.v", "related_invariants": ["Inv1"]}]
    assert lt.tags_for_invariant(entries, "Inv1") == [{"tag": "LogA", "cvar": "a.v"}]
    assert lt.tags_for_invariant(entries, "Inv2") == []      # 부재 — 호출자가 필드를 생략


def test_evidence_parser_matches_origin():
    assert lc.parse_evidence_classes("UMissionExecutor.cpp:142, MissionTypes.h:10") \
        == {"UMissionExecutor", "MissionTypes"}
    assert lc.parse_evidence_classes("Tick() 의 lock_guard 패턴") == set()
    assert lc.parse_evidence_classes("") == set()


def test_candidates_report_is_proposal_only():
    with tempfile.TemporaryDirectory() as tmp:
        paths = _twin(Path(tmp))
        lt.set_impl(paths, "MissionRuntime", "LogDone", "m.LogDone.Enable",
                    related_invariants=["ExecutorStateConsistency"])
        before = lt.sidecar_path(paths.ontology / "domains" / "MissionRuntime") \
            .read_text(encoding="utf-8")
        got = lc.generate(paths)
        # 서술형 evidence(클래스 0)는 후보가 아니다 — 원전 계약
        assert got["total"] == 1 and got["domains"] == 1, got
        # [중요] 확정 등록분은 버리지 않고 표기한다 (원전은 파서 한계로 dedup 못 함 —
        #    우리는 표기로 그 대조를 대신한다)
        assert got["registered"] == 1
        md = Path(got["path"]).read_text(encoding="utf-8")
        assert "[확정 등록됨]" in md and "ExecutorStateConsistency" in md
        assert "LogMissionRuntimeExecutorStateConsistency" in md      # 권장 tag 컨벤션
        assert "missionruntime.Log" in md                             # 권장 cvar 컨벤션
        # [중요] 리포트는 사이드카를 절대 쓰지 않는다 (제안형)
        after = lt.sidecar_path(paths.ontology / "domains" / "MissionRuntime") \
            .read_text(encoding="utf-8")
        assert before == after


def test_viewer_attaches_log_tags_field():
    with tempfile.TemporaryDirectory() as tmp:
        paths = _twin(Path(tmp))
        lt.set_impl(paths, "MissionRuntime", "LogExec", "m.LogExec.Enable",
                    related_invariants=["ExecutorStateConsistency"])
        from master.webui import loaders
        d = loaders.load_domain_package(paths.root, "MissionRuntime")
        by_name = {i.get("name"): i for i in d["invariants"]}
        assert by_name["ExecutorStateConsistency"]["log_tags"] == \
            [{"tag": "LogExec", "cvar": "m.LogExec.Enable"}]
        # [중요] 매치 없는 invariant 는 필드 자체가 없다 (null 아님)
        assert "log_tags" not in by_name["NarrativeOnly"]


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} 통과")
    sys.exit(1 if failed else 0)
