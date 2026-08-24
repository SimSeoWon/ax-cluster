"""태스크 템플릿 레지스트리(`#139`·`#140`) 계약 테스트.

[중요] **이 칸이 층3 RunTests 의 전제다** — 원전 통합 빌드 게이트는 `tdd:true` 인 템플릿의
`test_spec.filter` 만 실제로 돌린다. 그래서 여기서 재는 것 셋:

    ① 왕복      중첩 구조·한글·계약이 우리 yaml_io 로 그대로 돌아오는가
    ② 불변식    검색 채널에 안 섞이는가 (이름으로 스캔하는 구조 레지스트리)
    ③ 게이트    `tdd` 판정 — [중요] **켜 놓고 안 도는 것**을 조용히 넘기지 않는가

실행: .venv/bin/python master/test_task_templates.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.ontology import tasks as T        # noqa: E402
from master.webui import routes               # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


FULL = dict(
    title="미션 태스크 추가",
    summary="에디터뷰 + 데이터 + 실행자 + 등록 4역할",
    related_domains=["MissionRuntime", "MissionEditor"],
    structure=[{"role": "에디터뷰", "class_pattern": "*DetailBase",
                "base": "UUserWidget", "note": "Panel_Empty stub 금지"},
               {"role": "실행자", "class_pattern": "*Executor", "base": "UObject", "note": ""}],
    example={"instance": "MissionTask_Move", "refs": ["Source/A/X.h", "Source/A/X.cpp"]},
    conventions=["SetDetail 은 Renewal 위젯을 활성화한다"],
    contracts={"preconditions": ["데이터가 등록돼 있다"],
               "postconditions": ["Complete() 가 정확히 한 번 불린다"],
               "acceptance": ["다음 단계로 진행한다"]},
    tdd=True,
    test_spec={"filter": "Project.Mission.TaskAddition", "covers": ["postconditions[0]"]},
)


# ── ① 왕복 ────────────────────────────────────────────────────

def test_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        r = T.create(d, "MissionTaskAddition", **FULL)
        check("생성된다", r["status"] == "created", str(r))
        check("역할 수를 돌려준다", r["structure_roles"] == 2, str(r))
        got = T.get(d, "MissionTaskAddition")
        data = got["data"]
        check("한글 title 이 살아남는다", data["title"] == "미션 태스크 추가", data.get("title"))
        check("[중요] 중첩 리스트-of-dict 왕복",
              data["structure"][0]["class_pattern"] == "*DetailBase"
              and data["structure"][1]["role"] == "실행자", str(data["structure"])[:120])
        check("예제 refs 왕복", data["example"]["refs"] == ["Source/A/X.h", "Source/A/X.cpp"],
              str(data["example"]))
        check("계약 3종 왕복",
              data["contracts"]["acceptance"] == ["다음 단계로 진행한다"], str(data["contracts"]))
        check("tdd 와 filter 왕복",
              data["tdd"] is True
              and data["test_spec"]["filter"] == "Project.Mission.TaskAddition", str(data))
        check("원문도 돌려준다", "task_type: MissionTaskAddition" in got["raw"], got["raw"][:80])
        check("[중요] 파일이 도메인 옆 tasks/ 에 있다",
              Path(got["path"]) == Path(d) / "tasks" / "MissionTaskAddition" / "task.yaml",
              got["path"])


def test_name_rules():
    with tempfile.TemporaryDirectory() as d:
        r = T.create(d, "미션추가")
        check("[중요] 비ASCII 이름은 거부된다 (디렉토리·URL·도구 인자에 박힌다)",
              r["status"] == "rejected", str(r))
        check("한글은 title 에 쓰라고 말한다", "title" in r["reason"], r["reason"])
        check("빈 이름도 거부", T.create(d, "  ")["status"] == "error")
        T.create(d, "A")
        check("같은 이름 두 번은 exists", T.create(d, "A")["status"] == "exists")
        check("공백은 안전 문자로 바뀐다", T.safe_task_type("Boss Raid") == "Boss_Raid")


def test_edit_preserves_unsent_fields():
    """[중요] 준 필드만 갱신 — 통째 덮어쓰기면 등록해 둔 계약이 조용히 날아간다."""
    with tempfile.TemporaryDirectory() as d:
        T.create(d, "X", **FULL)
        r = T.edit(d, "X", tdd=False)
        check("바뀐 필드만 보고한다", r["changed"] == ["tdd"], str(r))
        data = T.get(d, "X")["data"]
        check("[중요] 안 준 필드가 보존된다", data["title"] == "미션 태스크 추가"
              and data["contracts"]["acceptance"] == ["다음 단계로 진행한다"], str(data)[:120])
        check("바꾼 필드는 반영된다", data["tdd"] is False)
        check("created 는 유지된다", bool(data.get("created")))
        check("없는 것 편집은 not_found", T.edit(d, "없음", tdd=True)["status"] == "not_found")


# ── ② 불변식: 검색 채널 분리 ──────────────────────────────────

def test_registry_is_not_a_search_channel():
    """[중요] 원전 불변식 — 섞으면 도메인 문서와 경합해 한쪽이 묻힌다 (사용자 지적)."""
    # [주의] **문자열 검색으로 재지 않는다.** 첫 판이 그렇게 했다가 모듈 독스트링이 불변식을
    #    *설명하며* 쓴 `bm25`·`ontology_domains` 를 「호출」로 셌다 — 이름 대조가 양방향으로
    #    틀리는 그 함정이다. [중요] **AST 로 실제 import·호출만 본다.**
    import ast
    src = Path(T.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported: set = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imported |= {a.name.split(".")[-1] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            imported |= {a.name for a in n.names}
            if n.module:
                imported.add(n.module.split(".")[-1])
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    for banned in ("domain_index", "bm25", "index", "sync"):
        check(f"[중요] 색인 모듈을 import 하지 않는다: {banned}", banned not in imported,
              f"import 목록: {sorted(imported)}")
    check("[중요] 색인 동기를 호출하지 않는다", "sync" not in called, f"호출: {sorted(called)}")
    check("실제로 쓰는 것은 우리 yaml_io 뿐", "yaml_io" in imported, str(sorted(imported)))
    check("불변식을 모듈이 스스로 적어 둔다", "검색 채널 분리 불변식" in src)
    with tempfile.TemporaryDirectory() as d:
        T.create(d, "A", title="가")
        T.create(d, "B", title="나")
        lst = T.listing(d)
        check("목록은 디렉토리 스캔이다 (이름순)",
              [t["task_type"] for t in lst["templates"]] == ["A", "B"], str(lst))
        check("목록에 tdd 여부가 보인다", "tdd" in lst["templates"][0])


# ── ③ 층3 게이트 판정 ─────────────────────────────────────────

def test_tdd_gate():
    with tempfile.TemporaryDirectory() as d:
        T.create(d, "On", tdd=True, test_spec={"filter": "F.One"})
        T.create(d, "Off", tdd=False, test_spec={"filter": "F.Never"})
        T.create(d, "Broken", tdd=True)                      # 켜 놓고 filter 없음
        got = T.collect_test_filters(d, ["On", "Off", "Broken", "Missing"])
        check("tdd=true 의 filter 만 모은다", got["filters"] == ["F.One"], str(got))
        check("[중요] tdd=false 는 filter 가 있어도 안 돈다", "F.Never" not in got["filters"], str(got))
        check("꺼진 것은 조용히 건너뛴다 (대부분의 task)", got["skipped"] == ["Off"], str(got))
        check("[중요] 켜 놓고 filter 가 없으면 **말한다**",
              any("tdd=true" in w and "Broken" in w for w in got["warnings"]), str(got["warnings"]))
        check("없는 템플릿도 말한다",
              any("Missing" in w for w in got["warnings"]), str(got["warnings"]))
        check("중복 필터는 한 번만",
              T.collect_test_filters(d, ["On", "On"])["filters"] == ["F.One"])


# ── 웹 표면 (`#140`) ──────────────────────────────────────────

def test_web_surface_has_data_now():
    """`#140` 은 *"라우트는 있고 데이터가 0"* 이었다 — 그 0 을 없앤다."""
    with tempfile.TemporaryDirectory() as d:
        class P:
            ontology = Path(d)
        T.create(d, "MissionTaskAddition", **FULL)
        lst = routes.api_tasks(P())
        check("웹 목록이 실 데이터를 준다", lst["count"] == 1, str(lst))
        check("빈 목록일 때만 안내 문구", "note" not in lst, str(lst.get("note")))
        one = routes.api_task(P(), "MissionTaskAddition")
        check("웹 상세가 붙는다", one and one["data"]["tdd"] is True, str(one)[:80])
        check("[중요] 없는 이름은 None (호출자가 404 로 만든다)",
              routes.api_task(P(), "없는것") is None)
        empty = routes.api_tasks(type("Q", (), {"ontology": Path(d) / "nope"})())
        check("비어 있으면 안내 문구가 붙는다", empty["count"] == 0 and "note" in empty, str(empty))


# ── history 웹 표면 (`#307`) ──────────────────────────────────

def test_history_web_surface_stops_lying():
    """[중요] 종전엔 **하드코딩된 빈 목록 + 「기록이 아직 없다」** 였다. 기록이 생긴 뒤에도
    화면이 「없다」고 말했다 — `#295` 와 같은 부류이고 방향만 반대다."""
    import datetime as _dt
    from master.context_synth import history_gen as HG
    with tempfile.TemporaryDirectory() as d:
        class P:
            root = Path(d)
            ontology = Path(d)
        pp = P()
        (Path(d) / "history").mkdir()
        HG.write(pp, HG.render(title="패드 입력 채택", decision_type="architecture",
                               affected_classes=["UCommonGameViewportClient"],
                               user_quote="사용자가 한 말 — 이건 LAN 에 나가면 안 된다",
                               date=_dt.datetime(2026, 8, 1),
                               body="# 패드 입력 채택\n\n본문 상세"),
                 title="패드 입력 채택", date=_dt.datetime(2026, 8, 1))

        got = routes.api_history(pp, "UCommonGameViewportClient")
        check("[중요] 실물을 돌려준다 (하드코딩 0 이 아니다)", got["count"] == 1, str(got))
        rec = got["records"][0]
        for k in ("source", "date", "decision_type", "summary_head", "path"):
            check(f"프론트 계약 필드 {k}", k in rec, str(rec))
        check("제목이 head 로 간다", rec["summary_head"] == "패드 입력 채택", str(rec))
        check("[중요] 기록이 있으면 「없다」 문구를 안 붙인다", "note" not in got, str(got.get("note")))

        blob = str(got)
        check("🔴 [중요] user_quote 를 LAN 에 내보내지 않는다 (이 포트는 무인증)",
              "이건 LAN 에 나가면 안 된다" not in blob, blob[:200])
        check("🔴 본문도 안 내보낸다", "본문 상세" not in blob, blob[:200])
        check("🔴 절대경로 대신 파일명만", "/" not in rec["path"] and rec["path"].endswith(".md"),
              rec["path"])

        other = routes.api_history(pp, "UNothingToDoWithIt")
        check("[중요] 기록은 있는데 그 클래스가 없으면 **그렇게 말한다**",
              other["count"] == 0 and "1건이 있지만" in other.get("note", ""),
              str(other.get("note")))

        prefixed = routes.api_history(pp, "CommonGameViewportClient")
        check("prefix 관용 매칭 (#158 과 같은 규칙)", prefixed["count"] == 1, str(prefixed["count"]))

    with tempfile.TemporaryDirectory() as d2:
        class Q:
            root = Path(d2)
        empty = routes.api_history(Q(), "UX")
        check("정말 0건이면 그때 안내 문구", empty["count"] == 0 and "note" in empty, str(empty))
        check("[주의] 문구가 「아직 없다」로 사실을 말한다",
              "아직 작업 기록" in empty["note"], empty["note"])


def main() -> int:
    for fn in (test_roundtrip, test_name_rules, test_edit_preserves_unsent_fields,
               test_registry_is_not_a_search_channel, test_tdd_gate,
               test_web_surface_has_data_now,
               test_history_web_surface_stops_lying):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_task_templates: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
