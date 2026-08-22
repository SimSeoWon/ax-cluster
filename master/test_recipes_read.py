"""레시피·안티패턴 **읽기** (`#267`) — 컨벤션 루프의 반대 방향.

합성은 이식돼 있었고(`recipes_synthesizer`, 원전 629줄) **읽는 도구만 없었다** — 그 모듈의
독스트링이 그 구멍을 스스로 적어 뒀다. 원전 주석은 호출 시점까지 못박았다: *"code-writer
에이전트는 **작업 시작 직후에 호출**해 step-by-step 가이드를 컨텍스트로 받는다."*

## [중요] 라이브 런이 잡은 것 — 언어 간극

신호는 한글인데 **합성된 레시피는 전부 영문**이다(원전 규약). 그래서 한글 질의
*"미션 태스크 추가"* 가 `MissionTaskDefinition` 레시피를 **못 찾는다.** 원전 독스트링의 예시
질의도 같은 이유로 안 걸렸을 것이다 — 이식하며 처음 드러났다. 사전을 심는 대신 **있는 것을
목록으로** 준다(부르는 쪽은 에이전트다).

`.venv/bin/python master/test_recipes_read.py`
"""
from __future__ import annotations

import re
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_synth import recipes_read as RR                # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _paths(with_recipes=True):
    tmp = Path(tempfile.mkdtemp())
    if with_recipes:
        (tmp / "recipes").mkdir()
    return types.SimpleNamespace(name="X", root=tmp, recipes=tmp / "recipes")


RECIPE = """---
recipe_name: MissionTaskDefinition
tags: [Mission, Task, Enum]
intent: Adding or modifying definitions and types for mission tasks.
signal_count: 2
---

## Steps
1. Update [Source/ModularStage/Mission/MSMissionTask.h] to define the new task type.
2. Modify [MSMissionTask.cpp] to implement the logic.
"""


def test_empty_states_say_why() -> None:
    """[중요] **「없음」과 「고장」을 구분한다** — 빈 배열만 주면 부르는 쪽이 못 가른다."""
    p = _paths()
    r = RR.find(p, "무엇이든")
    check("레시피 0건이면 사유가 온다", r["ok"] and r["total_recipes"] == 0
          and "아직 없습니다" in r["message"], str(r))
    check("원전 문구를 그대로 쓴다", "신호가 누적되면" in r["message"], r["message"])
    a = RR.anti_patterns(p)
    check("[중요] 카탈로그 부재를 exists=False 로 명시한다", a["exists"] is False, str(a))
    check("그 사유도 온다", "rejected_approaches" in a["message"], a["message"])
    # 디렉토리 자체가 없어도 죽지 않는다
    p2 = _paths(with_recipes=False)
    check("recipes 디렉토리가 없어도 답한다", RR.find(p2, "x")["total_recipes"] == 0)
    check("빈 질의는 거부한다 (무엇을 하려는지가 매칭의 근거다)",
          RR.find(p, "  ")["ok"] is False)


def test_matching_by_english_and_identifier() -> None:
    """영문·식별자 질의는 걸린다 — 그리고 **저자가 붙인 색인(이름·태그)에 가중치**가 있다."""
    p = _paths()
    (p.recipes / "MissionTaskDefinition.md").write_text(RECIPE, encoding="utf-8")
    (p.recipes / "_anti_patterns.md").write_text("---\nunique_patterns: 3\n---\n본문\n",
                                                 encoding="utf-8")
    (p.recipes / "_signals.jsonl").write_text("{}\n", encoding="utf-8")
    r = RR.find(p, "mission task")
    check("영문 질의가 걸린다", [m["recipe_name"] for m in r["matches"]]
          == ["MissionTaskDefinition"], str(r["matches"]))
    check("[주의] 밑줄 파일은 레시피가 아니다 (_anti_patterns·_signals)",
          r["total_recipes"] == 1, str(r["total_recipes"]))
    r2 = RR.find(p, "MSMissionTask enum")
    check("식별자 질의가 걸린다", len(r2["matches"]) == 1, str(r2["matches"]))
    check("태그·이름에 걸리면 점수가 높다",
          RR.find(p, "Mission Task Enum")["matches"][0]["score"]
          > RR.find(p, "logic implement")["matches"][0]["score"])
    check("preview 를 준다 (컨텍스트로 바로 쓴다)", r["matches"][0]["preview"])
    check("파일 이름을 준다", r["matches"][0]["file"] == "MissionTaskDefinition.md")
    check("n_results 를 지킨다", len(RR.find(p, "mission", 1)["matches"]) == 1)


def test_korean_query_gets_a_catalog_not_a_dead_end() -> None:
    """[중요] **라이브 런이 잡은 언어 간극** — 신호는 한글, 레시피는 영문이다.

    사전을 심지 않는다(이 저장소엔 시소러스·`resolve_terms` 가 이미 있고, 두 벌은 갈라진다).
    대신 **있는 것을 목록으로** 준다.
    """
    p = _paths()
    (p.recipes / "MissionTaskDefinition.md").write_text(RECIPE, encoding="utf-8")
    r = RR.find(p, "미션 태스크 추가")
    check("한글 질의는 못 걸린다 (사실이다)", r["matches"] == [], str(r["matches"]))
    check("[중요] 그래도 막다른 답이 아니다 — 목록이 온다", len(r.get("catalog") or []) == 1,
          str(r.get("catalog")))
    check("목록에 이름과 의도가 있다",
          r["catalog"][0]["recipe_name"] == "MissionTaskDefinition"
          and "mission tasks" in r["catalog"][0]["intent"], str(r["catalog"]))
    check("[중요] 왜 못 걸렸는지 말한다 (영문 합성)", "영문으로 합성된다" in r["message"],
          r["message"])
    check("무엇을 하면 되는지도 말한다", "식별자" in r["message"], r["message"])
    check("[주의] 레시피가 0건일 때와 문구가 다르다",
          "아직 없습니다" not in r["message"], r["message"])


def test_frontmatter_parsing_is_narrow_on_purpose() -> None:
    """[주의] YAML 파서를 쓰지 않는다 — 원전도 그렇고, 실패 모드를 늘리지 않는다."""
    meta, body = RR._frontmatter("---\ntags: [a, b]\nname: 'q'\n---\n본문\n")
    check("인라인 리스트를 읽는다", meta["tags"] == ["a", "b"], str(meta))
    check("인용을 벗긴다", meta["name"] == "q", str(meta))
    check("본문을 가른다", body.strip() == "본문")
    m2, b2 = RR._frontmatter("프론트매터 없는 문서")
    check("프론트매터가 없으면 전부 본문", m2 == {} and b2.startswith("프론트매터"))
    m3, b3 = RR._frontmatter("---\n닫히지 않은\n본문")
    check("닫히지 않으면 전부 본문 (죽지 않는다)", m3 == {})
    src = (Path(__file__).resolve().parent / "context_synth" / "recipes_read.py").read_text(
        encoding="utf-8")
    check("[주의] yaml 을 import 하지 않는다",
          not re.search(r"^\s*import yaml", src, re.M))


def test_read_failure_is_not_absence() -> None:
    """[중요] 읽기 실패를 「없음」으로 접지 않는다 — 고장과 부재는 다른 사고다."""
    p = _paths()
    cat = p.recipes / "_anti_patterns.md"
    cat.write_text("---\nunique_patterns: 3\n---\n본문\n", encoding="utf-8")
    ok = RR.anti_patterns(p)
    check("있으면 내용을 준다", ok["exists"] and ok["content"] == "본문", str(ok))
    check("메타를 함께 준다", ok["unique_patterns"] == "3", str(ok))
    src = (Path(__file__).resolve().parent / "context_synth" / "recipes_read.py").read_text(
        encoding="utf-8")
    i = src.index("def anti_patterns")
    body = src[i:]
    check("[중요] OSError 를 exists=True + error 로 낸다",
          '"exists": True, "error"' in body, "실패가 부재로 접힌다")


def test_wiring_keeps_the_query_out_of_the_url() -> None:
    """[중요] **URL 에 한글을 넣지 않는다** (사용자 지적 2026-08-23).

    이 저장소 관례가 이미 본문이다(`POST /api/v1/search/combined`). 퍼센트 인코딩된 URL 은
    저널에 못 읽는 문자열로 남고, 손으로 curl 하면 그냥 깨진다(실측: raw 한글 GET →
    `Invalid HTTP request`).
    """
    from master.task_queue import tagging as T
    check("라우트가 POST 다", "POST /api/v1/recipes/search" in T.POLICY)
    check("[주의] GET 라우트를 남겨 두지 않았다", "GET /api/v1/recipes" not in T.POLICY)
    check("[중요] 정책은 MOUNT — 남의 프로젝트 레시피를 돌려주지 않는다",
          T.POLICY["POST /api/v1/recipes/search"] == T.MOUNT)
    check("안티패턴 읽기도 MOUNT", T.POLICY["GET /api/v1/anti_patterns"] == T.MOUNT)
    check("[주의] 태그를 요구하지는 않는다 (없으면 마운트가 정답이다)",
          "POST /api/v1/recipes/search" not in T.REQUIRE_TAG)

    cmcp = (Path(__file__).resolve().parent.parent / "client" / "runtime"
            / "client_mcp.py").read_text(encoding="utf-8")
    check("[중요] 클라가 본문으로 보낸다",
          '"/api/v1/recipes/search", {"query"' in cmcp, "URL 에 질의를 붙인다")
    check("quote 로 URL 에 붙이지 않는다", "recipes?query=" not in cmcp)

    # 완료 조건 1 — **도구 목록에 두 이름이 보인다**
    from client.runtime import client_mcp as C
    names = [t["name"] for t in C.TOOLS]
    for n in ("find_recipes", "get_anti_patterns"):
        check(f"[중요] 도구 목록에 {n} 이 있다", n in names, str(names[-4:]))
    decl = next(t for t in C.TOOLS if t["name"] == "find_recipes")
    check("query 가 필수다", decl["inputSchema"]["required"] == ["query"])
    check("[중요] 설명이 **호출 시점**을 말한다 (원전 규약)",
          "작업을 시작하기 직전" in decl["description"], decl["description"][:60])
    check("빈 목록과 고장을 구분한다고 설명한다", "고장" in decl["description"])

    # 완료 조건 2 — **클라가 레시피 디렉토리를 직접 읽지 않는다**
    # [주의] **언급 금지가 아니라 접근 금지다** — 라우트 문자열(`/api/v1/recipes/search`)에
    #    `recipes` 가 들어 있다. 파일 접근 흔적으로 잰다(이번 세션 네 번째로 걸린 구분이다).
    check("[중요] 클라가 recipes 디렉토리를 열지 않는다",
          "recipes_dir" not in cmcp
          and not re.search(r"(rglob|glob|open|read_text)\([^)]*recipe", cmcp),
          "요청자 기계엔 그 디렉토리가 없다")
    check("대행 구조를 쓴다 (큐 API 를 부른다)", 'api("POST", "/api/v1/recipes/search"' in cmcp)


if __name__ == "__main__":
    for fn in (test_empty_states_say_why, test_matching_by_english_and_identifier,
               test_korean_query_gets_a_catalog_not_a_dead_end,
               test_frontmatter_parsing_is_narrow_on_purpose,
               test_read_failure_is_not_absence,
               test_wiring_keeps_the_query_out_of_the_url):
        fn()
    print(f"{'OK' if not FAIL else 'FAIL'} test_recipes_read: {PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
