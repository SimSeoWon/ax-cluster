"""컨텍스트 MD 합성 테스트 — 중 1.2. pytest 없이 그대로 실행한다.

    .venv/bin/python master/test_context_synth.py

[중요] 지키는 불변식 (전부 원본의 실측 사고에서 나왔다):
   1. **σ.7** — 펜스·자연어 도입부를 벗긴다 (사무실 실측 1,097개 중 477개가 펜스째 저장됨)
   2. **σ.7-B** — 벗긴 뒤에도 형식이 아니면 **저장 거부 + 기존 파일 유지**. 손상 응답이
      정상 문서를 덮어쓰는 것이 진짜 사고였다
   3. **게이트가 스탬프보다 앞** — 원본 사고는 스탬프 함수가 frontmatter 매치 실패를
      그대로 통과시킨 것이었다
   4. **`## 코멘트` 는 개발자 것** — 재생성이 덮지 않고, 해시에도 넣지 않는다
   5. **`source_commit` 은 중 1.3 stale 판정의 한쪽** — 빈 커밋으로 지우지 않는다
   6. **배치 서킷브레이커** — 연속 실패 시 중단. 1,600번 태워 0개 만들지 않는다
   7. **실패를 세서 들고 나온다** — 조용히 건너뛰면 영구 유실이 안 보인다

LLM 은 주입한다 — 실제 호출 없이 규칙을 검증한다.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from master.context_search.paths import ProjectPaths            # noqa: E402
from master.context_synth import md, prompt, synth, verify      # noqa: E402
from master.graph import class_graph as cg, dependency as dep   # noqa: E402

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [완료] {label}")
    else:
        FAIL += 1
        print(f"  [실패] {label}" + (f" — {detail}" if detail else ""))


GOOD = """---
tags: [mission, runtime]
category: Gameplay/Mission/Runtime
related_classes:
  - AMonster: Source/Game/Monster.h
---

## 요약
AMonster는 미션 스포너와 연동해 스폰 트리거를 관리한다.

## 개선 필요 사항
없음
"""

HEADER = 'class AMonster : public AActor { void Tick(float d); };\n'


def make_project(root: Path) -> ProjectPaths:
    p = ProjectPaths(name="C", root=root / "C")
    (p.source / "Game").mkdir(parents=True, exist_ok=True)
    (p.source / "Game" / "Monster.h").write_text(HEADER, encoding="utf-8")
    (p.source / "Game" / "Monster.cpp").write_text(
        '#include "Monster.h"\nvoid AMonster::Tick(float d) {}\n', encoding="utf-8")
    p.context.mkdir(parents=True, exist_ok=True)
    return p


def llm(*responses):
    """주입 LLM. 응답을 순서대로 돌려주고, 소진되면 마지막 것을 반복한다."""
    box = list(responses)

    def caller(url, payload):
        return box.pop(0) if len(box) > 1 else box[0]
    return caller


def honest_llm(url, payload):
    """프롬프트의 [실측] 클래스를 그대로 쓰는 정직한 모델.

    [중요] 이 픽스처가 필요한 이유: 앞선 판은 모든 파일에 같은 `AMonster` 문서를 돌려줬는데
    **사실 게이트가 그것을 "다른 파일을 서술한 문서" 로 정확히 거부했다.** 게이트가 맞다.
    """
    import re as _re
    m = _re.search(r"\[실측 — 이 파일이 정의하는 클래스[^\]]*\]\n((?:  - \w+\n?)+)",
                   payload["prompt"])
    names = _re.findall(r"- (\w+)", m.group(1)) if m else ["AMonster"]
    first = names[0]
    return (f"---\ntags: [x]\ncategory: a/b/c\nrelated_classes:\n"
            f"  - {first}: Source/Game/X.h\n---\n\n## 요약\n"
            f"{first} 은 게임 런타임에서 해당 기능을 담당한다. "
            f"{'다른 클래스로는 ' + ', '.join(names[1:4]) + ' 가 있다. ' if len(names) > 1 else ''}"
            f"검색 친화적으로 짧게 서술한다.\n\n## 개선 필요 사항\n없음\n")


def boom(url, payload):
    from master.work.generate import GenerateError
    raise GenerateError("브로커에 닿지 않는다: refused")


def test_attempt_records(tmp):
    """가짜 LLM의 실제 원문·판정 연결, 원자적 파일·병렬 고유성을 확인한다."""
    import contextlib
    import io
    import json
    from concurrent.futures import ThreadPoolExecutor
    from unittest.mock import patch

    files = ["Source/Game/Monster.h", "Source/Game/Monster.cpp"]
    key = "Source/Game/Monster"
    p = make_project(tmp / "attempt-success")
    seen = []
    raw = "```markdown\n" + GOOD + "```\n"
    def caller(_url, payload):
        seen.append(payload["prompt"])
        return raw
    real_finalize = md.finalize
    before_finalize = []
    def finalize(response, **kwargs):
        rows = [json.loads(f.read_text(encoding="utf-8"))
                for f in (p.root / "synth_attempts").glob("*.json")]
        before_finalize.append(rows[0]["raw"] == response and rows[0]["status"] == "received")
        return real_finalize(response, **kwargs)
    with patch.object(md, "finalize", side_effect=finalize):
        r = synth.synthesize_group(p, key, files, caller=caller, commit="capture123")
    rows = [json.loads(f.read_text(encoding="utf-8"))
            for f in (p.root / "synth_attempts").glob("*.json")]
    row = rows[0]
    check("응답 원문은 finalize 이전에 이미 기록", before_finalize == [True])
    check("성공 기록의 prompt/raw는 실제 호출과 글자 그대로 동일",
          r.written and row["prompt"] == seen[0] and row["raw"] == raw)
    check("사실 검증 대상 정규화 문서도 원문과 구별해 보존",
          row["normalized_doc"] == real_finalize(raw, commit="capture123")[0]
          and row["normalized_doc"] != raw)
    check("형식·사실·쓰기 결과가 동일 시도에 연결",
          len(rows) == 1 and row["format"]["ok"] and row["facts"]["ok"]
          and row["status"] == "written" and row["commit"] == "capture123"
          and row["group"] == key and "AMonster" in row["declared"])
    check("합성 결과에서 실제 기록 파일을 찾을 수 있음", len(r.attempt_records) == 1
          and Path(r.attempt_records[0]).is_file())
    check("기록은 인증헤더·브로커봉투를 저장하지 않음",
          "headers" not in row and "Authorization" not in row and "broker" not in row)
    check("임시 파일이 남지 않고 원문 기록 권한은 0600",
          not list((p.root / "synth_attempts").glob("*.tmp"))
          and next((p.root / "synth_attempts").glob("*.json")).stat().st_mode & 0o777 == 0o600)

    p = make_project(tmp / "attempt-facts")
    r = synth.synthesize_group(p, key, files, caller=llm(GOOD.replace("AMonster", "AOther")))
    row = json.loads(next((p.root / "synth_attempts").glob("*.json")).read_text(encoding="utf-8"))
    check("사실 거부에도 원문·거부근거 보존", not r.written
          and row["status"] == "facts_rejected" and row["format"]["ok"]
          and not row["facts"]["ok"] and row["facts"]["reason"])

    p = make_project(tmp / "attempt-chain")
    bad = "형식 없는 응답 그대로\n" * 10
    r = synth.synthesize_group(p, key, files, caller=llm(bad, GOOD),
                               chain=(synth.LOCAL_MODEL, synth.FALLBACK_MODEL))
    rows = [json.loads(f.read_text(encoding="utf-8"))
            for f in (p.root / "synth_attempts").glob("*.json")]
    by_model = {row["model"]: row for row in rows}
    check("형식 거부·대체 통과를 모델별 독립 원문으로 기록", r.written and len(rows) == 2
          and by_model[synth.LOCAL_MODEL]["raw"] == bad
          and by_model[synth.LOCAL_MODEL]["status"] == "format_rejected"
          and by_model[synth.LOCAL_MODEL]["facts"] is None
          and by_model[synth.FALLBACK_MODEL]["status"] == "written")

    p = make_project(tmp / "attempt-error")
    r = synth.synthesize_group(p, key, files, caller=boom)
    row = json.loads(next((p.root / "synth_attempts").glob("*.json")).read_text(encoding="utf-8"))
    check("생성 오류는 원문 없음과 transport_error를 명시", not r.written
          and row["status"] == "transport_error" and row["raw"] is None
          and not row["raw_received"] and "refused" in row["error"])
    check("실패 종료시각을 기록", row["finished_at"] >= row["started_at"])

    p = make_project(tmp / "attempt-dry")
    before = sorted(str(f.relative_to(p.root)) for f in p.root.rglob("*") if f.is_file())
    r = synth.synthesize_group(p, key, files, caller=llm(GOOD), dry_run=True)
    after = sorted(str(f.relative_to(p.root)) for f in p.root.rglob("*") if f.is_file())
    check("dry-run은 기록 디렉토리·파일도 쓰지 않음",
          r.dry_ok and before == after and not (p.root / "synth_attempts").exists())

    p = make_project(tmp / "attempt-parallel")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda n: synth.synthesize_group(
            p, f"Source/Game/parallel{n}", files, caller=llm(GOOD)), range(4)))
    rows = [json.loads(f.read_text(encoding="utf-8"))
            for f in (p.root / "synth_attempts").glob("*.json")]
    check("병렬 시도도 고유파일로 서로 덮지 않음", all(r.written for r in results)
          and len(rows) == 4 and len({row["attempt_id"] for row in rows}) == 4)

    p = make_project(tmp / "attempt-write-error")
    (p.root / "synth_attempts").write_text("cannot create directory", encoding="utf-8")
    with contextlib.redirect_stderr(io.StringIO()) as logs:
        r = synth.synthesize_group(p, key, files, caller=llm(GOOD))
    check("기록 실패는 로그에 남고 합성 판정은 유지",
          r.written and "[attempt] 기록 실패" in logs.getvalue())


def test_gemini_primary(tmp):
    """기본 제미나이 1차와 호출·형식·사실 실패의 로컬 대체를 실제 게이트로 잰다."""
    import json
    files = ["Source/Game/Monster.h", "Source/Game/Monster.cpp"]
    key = "Source/Game/Monster"
    for name, primary in (("ok", GOOD), ("transport", None),
                          ("format", "깨진 응답"),
                          ("facts", GOOD.replace("AMonster", "AOther"))):
        p = make_project(tmp / f"gemini-{name}")
        called = []
        def cli(lane, prompt, timeout):
            called.append(lane)
            return primary
        def local(_url, payload):
            called.append(payload["model"])
            return GOOD
        r = synth.synthesize_group(p, key, files, caller=local, cli=cli)
        expected = ["agy"] if name == "ok" else ["agy", synth.LOCAL_MODEL]
        check(f"제미나이 {name}: 지정 순서·동일 게이트로 통과",
              r.written and called == expected
              and r.model == ("agy" if name == "ok" else synth.LOCAL_MODEL), str(called))
        rows = {row["model"]: row for row in (
            json.loads(f.read_text(encoding="utf-8"))
            for f in (p.root / "synth_attempts").glob("*.json"))}
        check(f"제미나이 {name}: 모델마다 원문·판정 기록 연결",
              len(rows) == len(expected) and rows[r.model]["facts"]["ok"])
        if name == "facts":
            check("제미나이 사실 거부가 로컬 통과 기록으로 덮이지 않음",
                  rows["agy"]["status"] == "facts_rejected"
                  and not rows["agy"]["facts"]["ok"])
    p = make_project(tmp / "gemini-manual")
    calls = []
    r = synth.synthesize_group(p, key, files, model="agy", caller=llm(GOOD),
                               cli=lambda lane, *_a: calls.append(lane))
    check("명시 agy 호출 실패는 단독 실행이라 다른 모델을 부르지 않음",
          not r.passed and calls == ["agy"] and len(r.attempt_records) == 1)
    r = synth.synthesize_group(p, key, files, caller=llm(GOOD), dry_run=True)
    check("기본 제미나이도 fake caller만 있으면 실제 상용을 부르지 않음",
          r.passed and "agy 건너뜀(주입된 호출자)" in r.attempts
          and r.model == synth.LOCAL_MODEL)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ax-synth-test-"))
    FILES = ["Source/Game/Monster.h", "Source/Game/Monster.cpp"]

    print("\n[1] 그룹핑 — .h/.cpp 가 한 문서를 공유한다")
    g = synth.group(FILES + ["Source/Game/Boss.h"])
    check("stem 단위로 묶는다", set(g) == {"Source/Game/Monster", "Source/Game/Boss"}, str(g))
    check("[중요] 헤더가 먼저 (인터페이스 → 구현)",
          g["Source/Game/Monster"][0].endswith(".h"), str(g["Source/Game/Monster"]))
    check("다른 디렉토리의 같은 stem 은 다른 그룹",
          len(synth.group(["A/X.h", "B/X.h"])) == 2)

    print("\n[2] [중요] σ.7 — 펜스와 도입부를 벗긴다 (실측 43% 손상)")
    check("```markdown 펜스 제거",
          md.strip_wrapper("```markdown\n" + GOOD.strip() + "\n```").startswith("---"))
    check("언어 없는 펜스도 제거",
          md.strip_wrapper("```\n" + GOOD.strip() + "\n```").startswith("---"))
    check("자연어 도입부 제거",
          md.strip_wrapper("아래에 MD 를 작성했습니다.\n\n" + GOOD).startswith("---"))
    check("정상 문서는 그대로", md.strip_wrapper(GOOD).startswith("---"))

    print("\n[3] [중요] σ.7-B — 저장 전 게이트. 거부는 실패가 아니라 보류다")
    check("너무 짧으면 거부", not md.check("---\ntags: []\n---\n").ok)
    check("  사유가 남는다", "짧다" in md.check("---\n").reason)
    c = md.check("설명만 있고 frontmatter 가 없다. " * 5)
    check("frontmatter 없으면 거부", not c.ok and "frontmatter" in c.reason, c.reason)
    check("  preview 를 남긴다 (원인 추적용)", len(c.preview) > 10, c.preview)
    check("닫히지 않은 frontmatter 도 거부",
          not md.check("---\ntags: [a]\ncategory: x/y/z\n" + "본문 " * 20).ok)
    check("정상은 통과", md.check(GOOD).ok)

    print("\n[3-1] [중요] 닫는 `---` 누락은 결정적으로 복구한다 (14b 실측 실패)")
    UNCLOSED = GOOD.replace("---\n\n## 요약", "\n## 요약", 1)
    check("  재현: 닫는 줄이 없으면 게이트가 거부", not md.check(UNCLOSED).ok)
    fixed = md.repair_frontmatter(UNCLOSED)
    check("복구된다", md.check(fixed).ok, md.check(fixed).reason)
    check("  필드가 보존된다", "tags: [mission, runtime]" in fixed and "AMonster" in fixed)
    check("  본문이 보존된다", "## 요약" in fixed and "스폰 트리거" in fixed)
    check("이미 닫힌 문서는 건드리지 않는다", md.repair_frontmatter(GOOD) == GOOD.strip())
    check("[중요] `##` 제목이 없으면 손대지 않는다 (경계를 모른다)",
          md.repair_frontmatter("---\ntags: [a]\n본문뿐") == "---\ntags: [a]\n본문뿐")
    check("[중요] `---` 로 시작 안 하면 손대지 않는다",
          md.repair_frontmatter("본문\n## 요약\nx") == "본문\n## 요약\nx")
    check("strip_wrapper 가 복구까지 한다", md.check(md.strip_wrapper(UNCLOSED)).ok)
    doc_u, v_u = md.finalize(UNCLOSED, commit="zz99")
    check("finalize 도 통과시키고 스탬프한다",
          v_u.ok and "source_commit: zz99" in doc_u, v_u.reason)

    print("\n[3-2] #666 — 여는 구분선·양쪽 구분선 누락은 필드를 지키며 복구한다")
    existing_comments = GOOD + "\n## 코멘트\n- 사람이 남긴 설계 근거\n"
    reference, reference_v = md.finalize(GOOD, existing=existing_comments, commit="c666")
    for label, raw in (("여는 줄만 누락", GOOD.removeprefix("---\n")),
                       ("양쪽 줄 누락", UNCLOSED.removeprefix("---\n"))):
        check(f"{label}: 원문은 게이트 거부", not md.check(raw).ok)
        repaired = md.repair_frontmatter(raw)
        check(f"{label}: 메타데이터·본문 전체 보존",
              repaired == GOOD.strip(), repaired)
        document, verdict = md.finalize(raw, existing=existing_comments, commit="c666")
        check(f"{label}: 저장 가능한 정상 문서와 동일",
              reference_v.ok and verdict.ok and document == reference, verdict.reason)
        check(f"{label}: 해시·리비전·개발자 코멘트 보존",
              md.content_hash(document) == md.content_hash(reference)
              and md.read_source_commit(document) == "c666"
              and "사람이 남긴 설계 근거" in document)
        fenced, fenced_verdict = md.finalize("```markdown\n" + raw.strip() + "\n```",
                                             existing=existing_comments, commit="c666")
        check(f"{label}: 펜스 응답도 필드 유실 없이 복구",
              fenced_verdict.ok and fenced == reference)

    MISSING_OPEN = GOOD.removeprefix("---\n")
    for label, raw in (
            ("깨진 태그 배열", MISSING_OPEN.replace("[mission, runtime]", "[mission, runtime")),
            ("깨진 태그 따옴표", MISSING_OPEN.replace("[mission, runtime]", "['mission, runtime]")),
            ("메타데이터 사이 설명", MISSING_OPEN.replace("category:", "여기는 설명이다.\ncategory:")),
            ("중복 필드", MISSING_OPEN.replace("category:", "tags: [other]\ncategory:")),
            ("경계 제목 없음", MISSING_OPEN.split("## 요약")[0] + "설명 본문 " * 10),
            ("메타데이터처럼 보이는 설명", "tags: 설명\ncategory: 예시\n\n## 요약\n" + "설명 " * 30),
            ("중간 구분선", MISSING_OPEN.replace("category:", "---\ncategory:"))):
        refused_doc, refused_verdict = md.finalize(raw, existing=existing_comments, commit="c666")
        check(f"{label}: 손상을 정상으로 위장하지 않는다",
              refused_doc == "" and not refused_verdict.ok, refused_verdict.reason)

    check("정상 문서와 자연어 도입부는 기존 결과 유지",
          md.strip_wrapper(GOOD) == GOOD.strip()
          and md.strip_wrapper("아래에 MD 를 작성했습니다.\n\n" + GOOD) == GOOD.strip())

    print("\n[4] [중요] 게이트가 스탬프보다 앞 (원본 사고의 핵심)")
    doc, v = md.finalize("```markdown\n" + GOOD.strip() + "\n```", commit="abc123")
    check("펜스 벗기고 통과", v.ok and doc.startswith("---"))
    check("  content_hash 가 새겨진다", "content_hash: " in doc, doc[:200])
    check("  source_commit 이 새겨진다", "source_commit: abc123" in doc)
    bad_doc, bad_v = md.finalize("망가진 응답", commit="abc123")
    check("게이트 실패면 빈 문서 + 사유", bad_doc == "" and not bad_v.ok, bad_v.reason)

    print("\n[5] [중요] `## 코멘트` 는 개발자 것이다")
    existing = GOOD + "\n## 코멘트\n- 이건 의도된 설계다 (개발자)\n"
    doc2, _ = md.finalize(GOOD, existing=existing, commit="c1")
    check("재생성이 코멘트를 지우지 않는다", "의도된 설계다" in doc2, doc2[-120:])
    doc3, _ = md.finalize(GOOD.replace("없음", "없음") + "\n## 코멘트\n- LLM 이 지어낸 것\n",
                          existing=existing, commit="c1")
    check("[중요] LLM 이 만든 코멘트는 버리고 기존 것을 쓴다",
          "지어낸" not in doc3 and "의도된 설계다" in doc3, doc3[-160:])
    h1 = md.content_hash(doc2)
    h2 = md.content_hash(doc2.replace("의도된 설계다", "코멘트를 고쳤다"))
    check("[중요] 코멘트 변경이 해시를 바꾸지 않는다 (재색인 유발 금지)", h1 == h2)
    check("  본문 변경은 해시를 바꾼다",
          md.content_hash(doc2.replace("스폰 트리거", "다른 내용")) != h1)

    print("\n[6] [중요] source_commit — 중 1.3 stale 판정의 한쪽")
    check("없으면 -1 (첫 배포 전체 재합성 폭주 방지)", md.read_source_commit(GOOD) == "-1")
    stamped = md.stamp(GOOD, commit="deadbeef")
    check("읽어낸다", md.read_source_commit(stamped) == "deadbeef")
    check("[중요] 빈 커밋은 기존 값을 지우지 않는다",
          md.read_source_commit(md.stamp(stamped, commit="")) == "deadbeef")
    check("갱신은 교체한다", md.read_source_commit(md.stamp(stamped, commit="f00d")) == "f00d")

    print("\n[7] 근거 조립 — 없는 것은 없다고 적는다")
    gr = prompt.Grounding(declared_classes=["AMonster"],
                          ancestors={"AMonster": ["AActor", "UObject"]},
                          dependents=["Source/Game/Boss.h"])
    r = gr.render()
    check("실측 클래스를 적는다", "AMonster" in r)
    check("상속 사슬을 주고 추측을 금지한다", "AActor → UObject" in r and "추측하지 말고" in r)
    check("역방향 근사 경고를 붙인다", "근사" in r)
    check("[중요] 도메인 규범이 없다고 명시한다", "_없음 — 마일스톤 2 의 중 1.3" in r)
    p_txt = prompt.build(files=FILES, bodies={f: "code" for f in FILES}, grounding=gr)
    check("프롬프트에 형식 지시가 있다", "tags: [영문태그1" in p_txt)
    check("[중요] 한글 태그 병기를 지시한다 (사용자 지시 2026-08-17)",
          "한글 개념 태그 2~4개를 병기" in p_txt)
    check("범용어 태그 금지를 지시한다", "범용어는 태그가 아니다" in p_txt)
    check("[중요] 펜스로 감싸지 말라고 지시한다", "펜스로" in p_txt)
    check("코멘트를 만들지 말라고 지시한다", "## 코멘트\" 섹션은 절대 생성하지 마" in p_txt)
    check("🔴 #637 「개선 필요 사항」 절을 요구하지 않는다", "개선 필요 사항" not in p_txt)
    for name, src, role in (
        ("mat", "struct mat { double v[9]; };", "회전 행렬을 담는다"),
        ("loaded", "struct loaded { void *ctx; };", "로드한 컨텍스트를 보관한다"),
        ("error", "struct error { float max_abs; double relative_l2; };", "오차 지표를 담는다"),
    ):
        path = f"vendor/{name}.cpp"
        p_decl = prompt.build(files=[path], bodies={path: src},
                              grounding=prompt.Grounding(declared_classes=[name]))
        check(f"{name}: 실측 소문자 선언과 요약의 이름·역할 지시를 함께 제공",
              f"  - {name}" in p_decl and "최소 하나의 실제 이름과 역할" in p_decl
              and "`## 요약`에 명시" in p_decl and "소문자 보조 구조체" in p_decl)
        doc = f"## 요약\n{name} 구조체는 {role}.\n"
        check(f"{name}: 지시를 따른 실제 선언 요약은 기존 게이트 통과",
              verify.verify(doc, sources={path: src}, declared=[name]).ok)
        check(f"{name}: 역할만 설명하고 선언을 빠뜨린 요약은 기존 게이트 거부",
              not verify.verify(f"## 요약\n구조체는 {role}.\n",
                                sources={path: src}, declared=[name]).ok)
    check("선언 없는 근거에는 선언 언급 지시를 붙이지 않음",
          "[요약 작성 지시]" not in prompt.Grounding().render())
    p_dev = prompt.build(files=FILES, bodies={f: "code" for f in FILES}, grounding=gr,
                         existing="## 요약\nx\n\n## 코멘트\n사람이 쓴 메모\n")
    check("#637 개발자 코멘트 안내에도 그 절이 없다",
          "사람이 쓴 메모" in p_dev and "개선 필요 사항" not in p_dev)
    check("본문 상한을 적용한다",
          len(prompt.build(files=FILES, bodies={FILES[0]: "x" * 20000}, grounding=gr,
                           limit=100)) < 12000)
    try:
        prompt.build(files=[], bodies={}, grounding=gr)
        check("파일 0개면 예외", False, "예외 없음")
    except ValueError:
        check("파일 0개면 예외", True)

    print("\n[8] 합성 — 한 그룹")
    p1 = make_project(tmp)
    r1 = synth.synthesize_group(p1, "Source/Game/Monster", FILES,
                                commit="aa11", caller=llm(GOOD))
    check("문서를 쓴다", r1.written, r1.reason)
    out = synth.doc_path(p1, "Source/Game/Monster")
    check("경로가 stem 규칙과 맞는다", out.is_file(), str(out))
    body = out.read_text(encoding="utf-8")
    check("스탬프가 들어있다", "content_hash: " in body and "source_commit: aa11" in body)

    print("\n[9] [중요] 게이트 거부는 기존 문서를 지키고, 실패로 센다")
    before = out.read_text(encoding="utf-8")
    r2 = synth.synthesize_group(p1, "Source/Game/Monster", FILES,
                                commit="bb22", caller=llm("망가진 응답"))
    check("쓰지 않는다", not r2.written)
    check("[중요] 기존 문서가 그대로다", out.read_text(encoding="utf-8") == before)
    check("사유와 preview 를 들고 나온다", "게이트" in r2.reason and "preview" in r2.reason,
          r2.reason)
    check("[중요] 영구 유실로 표시된다", r2.lost)

    print("\n[10] LLM 실패도 결과로 (예외로 배치를 멈추지 않는다)")
    r3 = synth.synthesize_group(p1, "Source/Game/Monster", FILES, caller=boom)
    check("결과로 돌아온다", not r3.written and r3.reason.startswith("LLM 실패"), r3.reason)
    check("[중요] 기존 문서 유지", out.read_text(encoding="utf-8") == before)

    print("\n[11] 배치 — 통계가 분모를 들고 있다")
    p2 = make_project(tmp / "batch")
    for i in range(4):
        (p2.source / "Game" / f"F{i}.h").write_text(f"class AF{i} {{}};\n", encoding="utf-8")
    allf = FILES + [f"Source/Game/F{i}.h" for i in range(4)]
    st = synth.run(p2, changed=allf, commit="c9", caller=honest_llm)
    check("그룹 수", st.groups == 5, str(st.groups))
    check("전부 작성", st.written == 5, st.summary)
    check("유실 0", st.lost == 0, st.summary)
    check("요약에 분모가 있다", "그룹 5 → 통과 5" in st.summary, st.summary)
    check("통과율을 낼 수 있다", st.pass_rate == "5/5", st.pass_rate)

    print("\n[12] [중요] 서킷브레이커 — 연속 실패 시 중단한다")
    p3 = make_project(tmp / "circuit")
    for i in range(10):
        (p3.source / "Game" / f"G{i}.h").write_text(f"class AG{i} {{}};\n", encoding="utf-8")
    many = [f"Source/Game/G{i}.h" for i in range(10)]
    st2 = synth.run(p3, changed=many, caller=boom)
    check(f"임계값 {synth.CIRCUIT_THRESHOLD} 에서 끊는다",
          st2.failed == synth.CIRCUIT_THRESHOLD, str(st2.failed))
    check("[중요] 남은 그룹을 태우지 않는다", st2.failed < st2.groups, st2.summary)
    check("중단 사유를 남긴다", "연속 실패" in st2.aborted, st2.aborted)
    check("마지막 사유도 붙는다", "브로커" in st2.aborted, st2.aborted)

    print("\n[13] 게이트 거부는 서킷을 열지 않는다 (모델은 살아 있다)")
    st3 = synth.run(p3, changed=many, caller=llm("망가짐"))
    check("전부 시도한다", st3.refused == st3.groups, st3.summary)
    check("중단하지 않는다", not st3.aborted, st3.aborted)

    print("\n[14] skip_existing · limit — 감추지 않고 적는다")
    st4 = synth.run(p2, changed=allf, skip_existing=True, caller=honest_llm)
    check("이미 있으면 건너뛴다", st4.skipped == 5 and st4.written == 0, st4.summary)
    st5 = synth.run(p2, changed=allf, limit=2, caller=honest_llm)
    check("상한이 먹는다", st5.written == 2, st5.summary)
    check("[중요] 남긴 것을 적는다", "상한" in st5.aborted and "미처리" in st5.aborted, st5.aborted)

    print("\n[14-1] [중요] 주기적 모델 회수 — num_ctx 만으로는 부족하다 (실측)")
    st_u = synth.run(p2, changed=allf, caller=honest_llm, unload_every=2)
    check("주입 caller 일 때는 회수하지 않는다 (실제 노드가 아니다)",
          st_u.unloads == 0, str(st_u.unloads))
    check("  그래도 전부 처리된다", st_u.written == 5, st_u.summary)
    calls = []
    real_unload = synth.unload_model
    real_call = synth.call_broker
    synth.unload_model = lambda m, **kw: calls.append(m)
    synth.call_broker = lambda pr, **kw: honest_llm("", {"prompt": pr})
    try:
        st_u2 = synth.run(p2, changed=allf, unload_every=2, model=synth.LOCAL_MODEL)
        check("[중요] 노드 경로에서는 주기마다 회수한다", len(calls) == 2, str(len(calls)))
        check("  통계에 회수 횟수가 남는다", st_u2.unloads == 2, st_u2.summary)
        check("  요약에 나타난다", "모델 회수 2회" in st_u2.summary, st_u2.summary)
        calls.clear()
        st_u3 = synth.run(p2, changed=allf, unload_every=0, model=synth.LOCAL_MODEL)
        check("unload_every=0 이면 회수하지 않는다 (전용 VRAM 노드)",
              not calls and st_u3.unloads == 0)

        def _boom_unload(m, **kw):
            raise synth.GenerateError("회수 실패")

        synth.unload_model = _boom_unload
        st_u4 = synth.run(p2, changed=allf, unload_every=2, model=synth.LOCAL_MODEL)
        check("[중요] 회수 실패가 배치를 죽이지 않는다", st_u4.written == 5, st_u4.summary)
    finally:
        synth.unload_model = real_unload
        synth.call_broker = real_call

    print("\n[15] [중요] 소스 0건은 예외 (빈 배치를 성공으로 보고하지 않는다)")
    for label, kwargs in (("빈 변경 목록", {"changed": []}),
                          ("전부 삭제됨", {"changed": ["Source/없는파일.h"]})):
        try:
            synth.run(p2, caller=honest_llm, **kwargs)
            check(f"{label} → 예외", False, "예외 없음")
        except synth.SynthError:
            check(f"{label} → 예외", True)

    print("\n[16] CP949 소스 — 44% 가 그렇다")
    p4 = make_project(tmp / "cp949")
    kr = "// 몬스터 스폰을 관리한다\nclass AKr : public AActor {};\n"
    (p4.source / "Game" / "Kr.h").write_bytes(kr.encode("cp949"))
    seen = {}

    def capture(url, payload):
        seen["prompt"] = payload["prompt"]
        return honest_llm(url, payload)

    st6 = synth.run(p4, changed=["Source/Game/Kr.h"], caller=capture)
    check("합성이 된다", st6.written == 1, st6.summary)
    check("[중요] 한글 주석이 프롬프트에 살아서 들어간다",
          "몬스터 스폰을 관리한다" in seen["prompt"], seen["prompt"][:120])
    check("인코딩 분포를 보고한다", st6.encodings.cp949 == 1, st6.encodings.summary)

    print("\n[16-1] [중요] 사실 게이트 — 주석에만 있는 것을 특정한다 (결정적, LLM 0)")
    SRC = """
// class ULegacyLoader : public UObject {};    <- 주석 처리됨
/* struct FOldPayload { int32 Count; }; */
class UActiveThing : public UObject {
    void DoWork();
    const char* note = "// not a comment /* nor this */";
};
"""
    live, dead = verify.strip_comments(SRC)
    check("주석을 걷어낸다", "ULegacyLoader" not in live and "FOldPayload" not in live)
    check("살아 있는 코드는 남는다", "UActiveThing" in live and "DoWork" in live)
    check("[중요] 문자열 안의 `//` 를 주석으로 보지 않는다",
          "not a comment" in live, live[-90:])
    only = verify.comment_only(SRC)
    check("주석 전용 식별자를 특정한다", {"ULegacyLoader", "FOldPayload"} <= only, str(sorted(only)))
    check("[중요] 살아 있는 것은 포함하지 않는다", "UActiveThing" not in only and "DoWork" not in only)
    check("언어 키워드·UE 매크로는 노이즈로 제외", "class" not in only and "struct" not in only)

    GHOST = """---
tags: [x]
category: a/b/c
related_classes:
  - UActiveThing: Source/Game/T.h
---

## 요약
UActiveThing 은 ULegacyLoader 를 통해 FOldPayload 를 비동기로 관리한다.

## 개선 필요 사항
없음
"""
    rep = verify.verify(GHOST, sources={"T.h": SRC}, declared=["UActiveThing"])
    check("[중요] 유령 식별자를 잡는다", not rep.ok and "ULegacyLoader" in rep.ghosts, str(rep.ghosts))
    check("  사유에 이름이 들어간다", "ULegacyLoader" in rep.reason, rep.reason)
    HONEST = GHOST.replace(
        "UActiveThing 은 ULegacyLoader 를 통해 FOldPayload 를 비동기로 관리한다.",
        "UActiveThing 은 DoWork 로 작업을 수행한다. 파일 상단에는 주석 처리된 흔적이 있다.")
    check("정직한 문서는 통과", verify.verify(HONEST, sources={"T.h": SRC},
                                        declared=["UActiveThing"]).ok)
    check("[중요] 「개선 필요 사항」에서 주석을 언급하는 것은 위반이 아니다",
          verify.verify(HONEST.replace("없음", "ULegacyLoader 는 주석 처리되어 있다"),
                        sources={"T.h": SRC}, declared=["UActiveThing"]).ok)
    check("엔진 클래스는 오탐이 아니다 (소스에 없다)",
          verify.verify(HONEST.replace("DoWork 로", "UObject·AActor 기반으로 DoWork 로"),
                        sources={"T.h": SRC}, declared=["UActiveThing"]).ok)
    other = verify.verify(HONEST.replace("UActiveThing", "USomethingElse"),
                          sources={"T.h": SRC}, declared=["UActiveThing"])
    check("실측 클래스를 하나도 안 쓰면 거부", not other.ok and not other.mentioned_declared)
    check("declared 가 비면 그 검사는 건너뛴다",
          verify.verify(HONEST, sources={"T.h": SRC}, declared=[]).ok)

    # 🔴 `#693` — 비UE 소문자 선언(`struct mat`)은 모양 규칙에 안 걸려 언급으로 안 세졌다
    LOWER_SRC = "struct mat { double v[9]; };\nmat mul(const mat&a){return a;}\n"
    LOWER = "## 요약\n3x3 회전 행렬 mat 구조체로 시퀀스를 디코딩한다.\n"
    check("🔴 소문자 선언 이름을 요약에 쓰면 언급으로 센다 (Kimodo `mat`)",
          verify.verify(LOWER, sources={"s.cpp": LOWER_SRC}, declared=["mat"]).ok)
    check("  한국어 조사가 붙어도 센다",
          verify.verify(LOWER.replace("mat 구조체로", "mat로"),
                        sources={"s.cpp": LOWER_SRC}, declared=["mat"]).ok)
    check("  다른 낱말의 일부는 세지 않는다 (format ≠ mat)",
          not verify.verify(LOWER.replace("mat 구조체로", "format 으로"),
                            sources={"s.cpp": LOWER_SRC}, declared=["mat"]).ok)
    FUNC = "## 요약\n`condition_row` 함수가 골격 조건을 계산한다.\n"
    FUNC_SRC = LOWER_SRC + "float condition_row(const float*r){return r[0];}\n"
    check("🔴 index_only: 파일의 살아 있는 함수를 서술하면 통과 (Kimodo `sequence`)",
          verify.verify(FUNC, sources={"s.cpp": FUNC_SRC}, declared=["mat"],
                        live_counts=True).ok)
    check("  unreal(기본): 같은 문서는 종전대로 거부",
          not verify.verify(FUNC, sources={"s.cpp": FUNC_SRC}, declared=["mat"]).ok)
    check("  index_only 라도 파일에 없는 이름만 쓰면 거부",
          not verify.verify(FUNC.replace("condition_row", "other_func"),
                            sources={"s.cpp": FUNC_SRC}, declared=["mat"],
                            live_counts=True).ok)
    check("  요약 밖에만 있으면 세지 않는다",
          not verify.verify("## 요약\n행렬로 디코딩한다.\n\n## 개선 필요 사항\nmat 이름이 짧다\n",
                            sources={"s.cpp": LOWER_SRC}, declared=["mat"]).ok)

    print("\n[16-2] 사실 게이트가 합성에 물려 있다")
    p6 = make_project(tmp / "factual")
    (p6.source / "Game" / "T.h").write_text(SRC, encoding="utf-8")
    r6 = synth.synthesize_group(p6, "Source/Game/T", ["Source/Game/T.h"], caller=llm(GHOST))
    check("[중요] 유령 문서를 저장하지 않는다", not r6.written, r6.reason)
    check("  사유가 사실 게이트라고 말한다", "사실 게이트" in r6.reason, r6.reason)
    check("  영구 유실로 센다", r6.lost)
    st7 = synth.run(p6, changed=["Source/Game/T.h"], caller=llm(GHOST))
    check("통계가 사실 거부를 따로 센다", st7.unfactual == 1 and st7.refused == 0, st7.summary)
    check("  요약에 나타난다", "사실 거부" in st7.summary, st7.summary)
    check("[중요] 사실 거부는 서킷을 열지 않는다 (모델은 살아 있다)", not st7.aborted)

    print("\n[17] 근거 수집 — 그래프가 있으면 실측값이 들어간다")
    p5 = make_project(tmp / "grounded")
    (p5.source / "Game" / "Boss.h").write_text(
        '#include "Monster.h"\nclass ABoss : public AMonster {};\n', encoding="utf-8")

    def fake_git(repo, *args):
        return 0, "\n".join(FILES + ["Source/Game/Boss.h"])

    cg.build_full(p5, git=fake_git)
    dep.build_full(p5, git=fake_git)
    gr2 = synth.collect_grounding(p5, ["Source/Game/Monster.h"])
    check("정의 클래스를 실측한다", "AMonster" in gr2.declared_classes,
          str(gr2.declared_classes))
    check("상속 사슬이 들어간다", gr2.ancestors.get("AMonster") == ["AActor"],
          str(gr2.ancestors))
    check("이 파일을 참조하는 쪽이 들어간다",
          "Source/Game/Boss.h" in gr2.dependents, str(gr2.dependents))
    check("근거가 비어 있지 않다", not gr2.empty)
    check("그래프가 없으면 빈 근거 (예외 아님)",
          synth.collect_grounding(make_project(tmp / "nograph"),
                                  ["Source/Game/Monster.h"]).dependents == [])

    print("\n[live] 🔴 실재 심볼은 프로젝트 전체의 살아 있는 코드에서도 온다 (실측 2026-09-13 NS)")
    pl = make_project(tmp / "live")
    (pl.source / "Game" / "PC.h").write_text(
        "// 세력 판정\n"
        "class APC : public APlayerController, public IGenericTeamAgentInterface {\n"
        "  int CurrentVulnerableState = 0;\n};\n", encoding="utf-8")
    (pl.source / "Game" / "Ctrl.h").write_text(
        "// IGenericTeamAgentInterface 는 AAIController 가 이미 구현한다\n"
        "// CurrentVulnerableState 는 캐릭터가 들고 있다\n"
        "// UNSGhostOnly 는 주석에만 있다\n"
        "class ACtrl : public AAIController { void Run(); };\n", encoding="utf-8")
    known = synth.project_symbols(pl)                   # 그래프 없음 — 살아 있는 코드만 근거
    check("다른 파일 코드의 엔진 인터페이스를 안다", "IGenericTeamAgentInterface" in known)
    check("다른 파일 코드의 멤버 변수를 안다", "CurrentVulnerableState" in known)
    check("[중요] 프로젝트 어디에도 코드로 없는 이름은 모른다 (게이트가 무뎌지지 않았다)",
          "UNSGhostOnly" not in known)
    ctrl_src = {"Source/Game/Ctrl.h": (pl.source / "Game" / "Ctrl.h").read_text(encoding="utf-8")}
    ok_doc = ("## 요약\n\nACtrl 은 IGenericTeamAgentInterface 로 세력을 답하고 "
              "CurrentVulnerableState 를 본다\n\n## 끝\n")
    r_ok = verify.verify(ok_doc, sources=ctrl_src, declared=["ACtrl"], known=known)
    check("🔴 실재하는 두 이름을 서술한 문서가 통과한다 (NS 에서 운에 따라 거부되던 것)",
          r_ok.ok, str(r_ok.ghosts))
    ghost_doc = "## 요약\n\nACtrl 은 UNSGhostOnly 를 쓴다\n\n## 끝\n"
    r_gh = verify.verify(ghost_doc, sources=ctrl_src, declared=["ACtrl"], known=known)
    check("[중요] 주석에만 있는 이름은 여전히 거부한다",
          not r_gh.ok and "UNSGhostOnly" in r_gh.ghosts, str(r_gh.ghosts))
    (pl.source / "Game" / "PC.h").write_text("// 비웠다\nclass APC {};\n", encoding="utf-8")
    check("  파일이 바뀌면 캐시를 쓰지 않는다",
          "CurrentVulnerableState" not in synth.project_symbols(pl))

    print("\n[#727-1] e4b 실측 모양 — 펜스 · 여는/닫는 줄 누락 · 공백 든 category 를 복구한다")
    REVIEW_GEN_RAW = (
        "```markdown\n"
        "tags: [코드리뷰생성, 코드분석, 컨벤션검증, 커밋리포트]\n"
        "category: Context Synthesis/Review Generation/Code Review\n\n"
        "## 요약\nAMonster 는 리뷰를 만든다.\n\n## 개선 필요 사항\n- 없음\n"
        "```")
    check("  재현: 종전 게이트는 이 원문을 거부했다(벗긴 뒤에도 `---` 없음)",
          not md.check(md._FENCE_RE.match(REVIEW_GEN_RAW).group(1)).ok)
    d727, v727 = md.finalize(REVIEW_GEN_RAW, commit="93dea06")
    check("복구된 문서가 **바뀌지 않은 게이트**를 통과한다", v727.ok and md.check(d727).ok,
          v727.reason)
    check("  category 의 공백이 보존된다",
          "category: Context Synthesis/Review Generation/Code Review" in d727, d727[:200])
    check("  스탬프가 들어간다", md.read_source_commit(d727) == "93dea06")
    REL_PATHS = ("tags: [a, b]\ncategory: X Y/Z\nrelated_classes:\n"
                 "  - context_synth/synth.py: master/context_synth/synth.py\n\n## 요약\n" + "본문 " * 20)
    check("related_classes 이름 자리의 경로 모양도 복구한다",
          md.finalize(REL_PATHS, commit="c1")[1].ok)
    for label, raw in (
            ("category 에 콜론", REVIEW_GEN_RAW.replace("Code Review", "Code: Review")),
            ("category 가 YAML 목록", REVIEW_GEN_RAW.replace(
                "Context Synthesis/Review Generation/Code Review", "[a, b]")),
            ("category 가 비었다", REVIEW_GEN_RAW.replace(
                "Context Synthesis/Review Generation/Code Review", "")),
            ("related 항목이 문장", REL_PATHS.replace(
                "context_synth/synth.py: master", "이건 설명: master"))):
        dd, vv = md.finalize(raw, commit="c1")
        check(f"{label}: 여전히 거부한다(게이트를 무디게 하지 않았다)", dd == "" and not vv.ok,
              dd[:120])

    print("\n[기본 사슬] agy → e4b → codex → 12b, claude 는 없다")
    check("사슬이 상수 한 곳이다 — agy → e4b → codex → 12b",
          synth.SYNTH_CHAIN == ("agy", synth.LOCAL_MODEL, "codex", synth.FALLBACK_MODEL),
          str(synth.SYNTH_CHAIN))
    check("[중요] claude 는 사슬에 없다", not any(m.startswith("claude") for m in synth.SYNTH_CHAIN))
    check("첫 모델은 제미나이 agy", synth.SYNTH_MODEL == "agy"
          and synth._chain_for(None, None)[0] == "agy")
    check("기본 사슬은 상수 순서 그대로다 (로컬을 앞으로 모으지 않는다)",
          synth._chain_for(None, None)
          == ["agy", "gemma4:e4b", "codex", "gemma3:12b"],
          str(synth._chain_for(None, None)))
    check("claude 를 넣어도 뺀다 · 받은 순서를 지킨다",
          synth._chain_for(synth.SYNTH_MODEL, ("gemma4:e4b", "agy", "claude:opus", "codex",
                                               "gemma3:12b"))
          == ["gemma4:e4b", "agy", "codex", "gemma3:12b"])
    check("명시한 사슬의 상용 첫 순서도 그대로 유지한다",
          synth._chain_for(synth.SYNTH_MODEL, ("codex", "claude:opus", "gemma4:e4b", "agy"))
          == ["codex", "gemma4:e4b", "agy"])
    check("명시 --model agy는 그 하나만", synth._chain_for("agy", None) == ["agy"])
    check("명시한 다른 모델은 그 하나만 (수동 경로 종전 그대로)",
          synth._chain_for("gemma3:12b", None) == ["gemma3:12b"])
    BAD = "설명만 있고 frontmatter 가 없다. " * 6

    def routed(table, seen):
        def caller(url, payload):
            seen.append(payload["model"])
            v = table[payload["model"]]
            return v(url, payload) if callable(v) else v
        return caller

    def cli_rec(table, seen):
        def cli(lane, prompt, timeout):
            seen.append(lane)
            v = table.get(lane)
            return v(None, {"prompt": prompt}) if callable(v) else v
        return cli

    pc = make_project(tmp / "chain")
    K = "Source/Game/Monster"
    old_chain = (synth.LOCAL_MODEL, "agy", "codex", synth.FALLBACK_MODEL)
    seen, cseen = [], []
    r = synth.synthesize_group(pc, K, FILES, commit="c727", dry_run=True, chain=old_chain,
                               caller=routed({"gemma4:e4b": BAD, "gemma3:12b": honest_llm}, seen),
                               cli=cli_rec({"agy": honest_llm, "codex": honest_llm}, cseen))
    check("e4b 형식 거부 → agy 통과", r.passed and r.model == "agy", r.reason)
    check("  codex·12b 는 부르지 않았다", cseen == ["agy"] and seen == ["gemma4:e4b"],
          f"{seen} {cseen}")
    check("  시도 기록이 남는다", r.attempts == ["gemma4:e4b 형식 거부", "agy 형식 통과"],
          str(r.attempts))

    seen, cseen = [], []
    r = synth.synthesize_group(pc, K, FILES, commit="c727", dry_run=True, chain=old_chain,
                               caller=routed({"gemma4:e4b": BAD, "gemma3:12b": honest_llm}, seen),
                               cli=cli_rec({"agy": BAD, "codex": honest_llm,
                                            "claude": honest_llm}, cseen))
    check("e4b·agy 거부 → codex 통과", r.passed and r.model == "codex", r.reason)
    check("  12b·claude 는 부르지 않았다", cseen == ["agy", "codex"] and seen == ["gemma4:e4b"],
          f"{seen} {cseen}")

    seen, cseen = [], []
    r = synth.synthesize_group(pc, K, FILES, commit="c727", dry_run=True, chain=old_chain,
                               caller=routed({"gemma4:e4b": BAD, "gemma3:12b": honest_llm}, seen),
                               cli=cli_rec({"agy": BAD, "codex": BAD}, cseen))
    check("e4b·agy·codex 거부 → 12b 통과 (최후)", r.passed and r.model == "gemma3:12b", r.reason)
    check("  순서대로 한 번씩", cseen == ["agy", "codex"] and seen == ["gemma4:e4b", "gemma3:12b"],
          f"{seen} {cseen}")
    check("  시도 기록이 남는다", r.attempts == ["gemma4:e4b 형식 거부", "agy 형식 거부",
                                         "codex 형식 거부", "gemma3:12b 형식 통과"],
          str(r.attempts))

    seen, cseen = [], []
    pc2 = make_project(tmp / "chain2")
    synth.doc_path(pc2, K).parent.mkdir(parents=True, exist_ok=True)
    synth.doc_path(pc2, K).write_text(GOOD, encoding="utf-8")
    r = synth.synthesize_group(pc2, K, FILES, commit="c727", chain=old_chain,
                               caller=routed({"gemma4:e4b": BAD, "gemma3:12b": BAD}, seen),
                               cli=cli_rec({"codex": BAD, "agy": None}, cseen))
    check("전부 실패 → 쓰지 않는다 · 유실로 남는다", not r.written and r.lost, r.reason)
    check("  [중요] 형식 거부로 센다 (서킷 사유가 아니다)", r.reason.startswith("형식 게이트"),
          r.reason[:80])
    check("  사유에 사슬이 실린다", "사슬:" in r.reason and "agy LLM 실패" in r.reason, r.reason)
    check("  레인마다 한 번 · claude 없음", cseen == ["agy", "codex"]
          and seen == ["gemma4:e4b", "gemma3:12b"], f"{seen} {cseen}")
    check("  기존 문서를 지킨다", synth.doc_path(pc2, K).read_text(encoding="utf-8") == GOOD)
    from master.context_synth import pending as pending_mod
    check("  보류로 남는다 (다음 실행이 다시 시도)", any(k == K for k, _ in pending_mod.due(pc2))
          or K in (pending_mod.summary(pc2) or ""), pending_mod.summary(pc2))

    seen, cseen = [], []
    r = synth.synthesize_group(pc, K, FILES, dry_run=True, chain=old_chain,
                               caller=routed({"gemma4:e4b": boom, "gemma3:12b": honest_llm}, seen),
                               cli=cli_rec({"agy": honest_llm, "codex": honest_llm}, cseen))
    check("첫 모델 호출 실패도 다음 모델로 대체한다",
          r.passed and r.model == "agy" and seen == ["gemma4:e4b"]
          and cseen == ["agy"], f"{r.reason} {seen} {cseen}")

    seen = []
    r = synth.synthesize_group(pc, K, FILES, dry_run=True,
                               caller=routed({"gemma4:e4b": BAD, "gemma3:12b": BAD}, seen))
    check("주입된 브로커 호출자뿐이면 진짜 상용 CLI 를 부르지 않는다",
          not r.passed and "agy 건너뜀(주입된 호출자)" in r.attempts
          and "codex 건너뜀(주입된 호출자)" in r.attempts
          and seen == ["gemma4:e4b", "gemma3:12b"], f"{r.attempts} {seen}")

    seen, cseen = [], []
    stc = synth.run(pc, changed=FILES, commit="c727", dry_run=True,
                    model=synth.LOCAL_MODEL, chain=old_chain,
                    caller=routed({"gemma4:e4b": BAD, "gemma3:12b": honest_llm}, seen),
                    cli=cli_rec({"agy": honest_llm}, cseen))
    check("배치 통계가 대체 통과를 센다", stc.fallback_passed == 1
          and "대체 모델 통과 1" in stc.summary, stc.summary)

    print("\n[#727-3] 사용량 — 로컬·상용 시도가 트윈 usage_log 에 `synth` 로 남는다")
    import json as _json
    import urllib.request as _ur
    from master import layer2_verify as _l2
    import importlib as _il
    _gen = _il.import_module("master.work.generate")

    class _Resp:
        def __init__(self, body):
            self._b = body

        def read(self):
            return self._b

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=0):
        return _Resp(_json.dumps({"response": BAD, "prompt_eval_count": 11,
                                  "eval_count": 7}).encode("utf-8"))

    good_txt = honest_llm(None, {"prompt": ""})
    ev = _json.dumps({"type": "turn.completed",
                      "usage": {"input_tokens": 100, "output_tokens": 20}})

    def agy_env(text):
        # agy 1.2.16 봉투 (`usage.parse_agy_json`) — 진짜 agy 는 부르지 않는다
        return _json.dumps({"status": "SUCCESS", "response": text,
                            "usage": {"input_tokens": 50, "output_tokens": 9}})

    def usage_run(name, agy_text):
        saved = (_ur.urlopen, _gen.auth_headers, _l2._codex_run, _l2._run_rc, _l2.shutil.which)
        pu = make_project(tmp / name)
        real_which = _l2.shutil.which
        try:
            _ur.urlopen = fake_urlopen
            _gen.auth_headers = lambda t=None: {}
            _l2._codex_run = lambda prompt, *, timeout, reasoning: (good_txt, ev, "", 0, True)
            _l2._run_rc = lambda cmd, *, timeout: (agy_env(agy_text), "", 0)
            _l2.shutil.which = lambda n, *a, **k: "/usr/bin/agy" if n == "agy" \
                else real_which(n, *a, **k)
            rr = synth.synthesize_group(pu, K, FILES, commit="c727", dry_run=True, chain=old_chain)
        finally:
            (_ur.urlopen, _gen.auth_headers, _l2._codex_run, _l2._run_rc,
             _l2.shutil.which) = saved
        rws = [_json.loads(x) for x in pu.usage_log.read_text(encoding="utf-8").splitlines()] \
            if pu.usage_log.is_file() else []
        return rr, rws

    logged, real_log = [], synth._log
    synth._log = lambda m: (logged.append(m), real_log(m))
    try:
        r, rows = usage_run("usage", good_txt)
    finally:
        synth._log = real_log
    check("agy 가 통과시킨다 (주입 없이 실제 진입점)", r.passed and r.model == "agy", r.reason)
    check("🔴 #751 상용 레인 로그 줄에 실제 토큰이 찍힌다 (「미상」 아님)",
          any("— agy · 토큰 입력 50 · 출력 9" in m for m in logged),
          str([m for m in logged if "agy ·" in m]))
    check("사용량 2행 — e4b · agy", [x["lane"] for x in rows]
          == ["local:gemma4:e4b", "agy"], str([x.get("lane") for x in rows]))
    check("  전부 source=synth · task_id=그룹", rows and all(
        x["source"] == "synth" and x["task_id"] == K for x in rows), str(rows)[:300])
    check("  토큰이 실린다", rows and rows[0]["input_tokens"] == 11
          and rows[-1]["input_tokens"] == 50, str(rows)[:300])
    check("  GroupResult 는 로컬 토큰 합을 든다", r.tokens_in == 11 and r.tokens_out == 7,
          f"{r.tokens_in}/{r.tokens_out}")

    r, rows = usage_run("usage2", BAD)
    check("agy 형식 거부 → codex 통과", r.passed and r.model == "codex", r.reason)
    check("사용량 3행 — e4b · agy · codex", [x["lane"] for x in rows]
          == ["local:gemma4:e4b", "agy", "codex"], str([x.get("lane") for x in rows]))
    check("  전부 source=synth", rows and all(x["source"] == "synth" for x in rows),
          str(rows)[:300])

    print("\n[원문기록] 실제 프롬프트·모델 응답·게이트 결과")
    test_attempt_records(tmp)
    print("\n[제미나이 1차] 호출·형식·사실 실패는 로컬 LLM 대체")
    test_gemini_primary(tmp)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'='*46}\n통과 {PASS} · 실패 {FAIL}\n{'='*46}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
