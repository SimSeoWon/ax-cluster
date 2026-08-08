"""컨텍스트 MD 합성 테스트 — 중 1.2. pytest 없이 그대로 실행한다.

    .venv/bin/python master/test_context_synth.py

🔴 지키는 불변식 (전부 원본의 실측 사고에서 나왔다):
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
from master.context_synth import md, prompt, synth              # noqa: E402
from master.graph import class_graph as cg, dependency as dep   # noqa: E402

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label}" + (f" — {detail}" if detail else ""))


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


def boom(url, payload):
    from master.work.generate import GenerateError
    raise GenerateError("브로커에 닿지 않는다: refused")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ax-synth-test-"))
    FILES = ["Source/Game/Monster.h", "Source/Game/Monster.cpp"]

    print("\n[1] 그룹핑 — .h/.cpp 가 한 문서를 공유한다")
    g = synth.group(FILES + ["Source/Game/Boss.h"])
    check("stem 단위로 묶는다", set(g) == {"Source/Game/Monster", "Source/Game/Boss"}, str(g))
    check("🔴 헤더가 먼저 (인터페이스 → 구현)",
          g["Source/Game/Monster"][0].endswith(".h"), str(g["Source/Game/Monster"]))
    check("다른 디렉토리의 같은 stem 은 다른 그룹",
          len(synth.group(["A/X.h", "B/X.h"])) == 2)

    print("\n[2] 🔴 σ.7 — 펜스와 도입부를 벗긴다 (실측 43% 손상)")
    check("```markdown 펜스 제거",
          md.strip_wrapper("```markdown\n" + GOOD.strip() + "\n```").startswith("---"))
    check("언어 없는 펜스도 제거",
          md.strip_wrapper("```\n" + GOOD.strip() + "\n```").startswith("---"))
    check("자연어 도입부 제거",
          md.strip_wrapper("아래에 MD 를 작성했습니다.\n\n" + GOOD).startswith("---"))
    check("정상 문서는 그대로", md.strip_wrapper(GOOD).startswith("---"))

    print("\n[3] 🔴 σ.7-B — 저장 전 게이트. 거부는 실패가 아니라 보류다")
    check("너무 짧으면 거부", not md.check("---\ntags: []\n---\n").ok)
    check("  사유가 남는다", "짧다" in md.check("---\n").reason)
    c = md.check("설명만 있고 frontmatter 가 없다. " * 5)
    check("frontmatter 없으면 거부", not c.ok and "frontmatter" in c.reason, c.reason)
    check("  preview 를 남긴다 (원인 추적용)", len(c.preview) > 10, c.preview)
    check("닫히지 않은 frontmatter 도 거부",
          not md.check("---\ntags: [a]\ncategory: x/y/z\n" + "본문 " * 20).ok)
    check("정상은 통과", md.check(GOOD).ok)

    print("\n[4] 🔴 게이트가 스탬프보다 앞 (원본 사고의 핵심)")
    doc, v = md.finalize("```markdown\n" + GOOD.strip() + "\n```", commit="abc123")
    check("펜스 벗기고 통과", v.ok and doc.startswith("---"))
    check("  content_hash 가 새겨진다", "content_hash: " in doc, doc[:200])
    check("  source_commit 이 새겨진다", "source_commit: abc123" in doc)
    bad_doc, bad_v = md.finalize("망가진 응답", commit="abc123")
    check("게이트 실패면 빈 문서 + 사유", bad_doc == "" and not bad_v.ok, bad_v.reason)

    print("\n[5] 🔴 `## 코멘트` 는 개발자 것이다")
    existing = GOOD + "\n## 코멘트\n- 이건 의도된 설계다 (개발자)\n"
    doc2, _ = md.finalize(GOOD, existing=existing, commit="c1")
    check("재생성이 코멘트를 지우지 않는다", "의도된 설계다" in doc2, doc2[-120:])
    doc3, _ = md.finalize(GOOD.replace("없음", "없음") + "\n## 코멘트\n- LLM 이 지어낸 것\n",
                          existing=existing, commit="c1")
    check("🔴 LLM 이 만든 코멘트는 버리고 기존 것을 쓴다",
          "지어낸" not in doc3 and "의도된 설계다" in doc3, doc3[-160:])
    h1 = md.content_hash(doc2)
    h2 = md.content_hash(doc2.replace("의도된 설계다", "코멘트를 고쳤다"))
    check("🔴 코멘트 변경이 해시를 바꾸지 않는다 (재색인 유발 금지)", h1 == h2)
    check("  본문 변경은 해시를 바꾼다",
          md.content_hash(doc2.replace("스폰 트리거", "다른 내용")) != h1)

    print("\n[6] 🔴 source_commit — 중 1.3 stale 판정의 한쪽")
    check("없으면 -1 (첫 배포 전체 재합성 폭주 방지)", md.read_source_commit(GOOD) == "-1")
    stamped = md.stamp(GOOD, commit="deadbeef")
    check("읽어낸다", md.read_source_commit(stamped) == "deadbeef")
    check("🔴 빈 커밋은 기존 값을 지우지 않는다",
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
    check("🔴 도메인 규범이 없다고 명시한다", "_없음 — 마일스톤 2 의 중 1.3" in r)
    p_txt = prompt.build(files=FILES, bodies={f: "code" for f in FILES}, grounding=gr)
    check("프롬프트에 형식 지시가 있다", "tags: [태그1" in p_txt)
    check("🔴 펜스로 감싸지 말라고 지시한다", "펜스로" in p_txt)
    check("코멘트를 만들지 말라고 지시한다", "## 코멘트\" 섹션은 절대 생성하지 마" in p_txt)
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

    print("\n[9] 🔴 게이트 거부는 기존 문서를 지키고, 실패로 센다")
    before = out.read_text(encoding="utf-8")
    r2 = synth.synthesize_group(p1, "Source/Game/Monster", FILES,
                                commit="bb22", caller=llm("망가진 응답"))
    check("쓰지 않는다", not r2.written)
    check("🔴 기존 문서가 그대로다", out.read_text(encoding="utf-8") == before)
    check("사유와 preview 를 들고 나온다", "게이트" in r2.reason and "preview" in r2.reason,
          r2.reason)
    check("🔴 영구 유실로 표시된다", r2.lost)

    print("\n[10] LLM 실패도 결과로 (예외로 배치를 멈추지 않는다)")
    r3 = synth.synthesize_group(p1, "Source/Game/Monster", FILES, caller=boom)
    check("결과로 돌아온다", not r3.written and r3.reason.startswith("LLM 실패"), r3.reason)
    check("🔴 기존 문서 유지", out.read_text(encoding="utf-8") == before)

    print("\n[11] 배치 — 통계가 분모를 들고 있다")
    p2 = make_project(tmp / "batch")
    for i in range(4):
        (p2.source / "Game" / f"F{i}.h").write_text(f"class AF{i} {{}};\n", encoding="utf-8")
    allf = FILES + [f"Source/Game/F{i}.h" for i in range(4)]
    st = synth.run(p2, changed=allf, commit="c9", caller=llm(GOOD))
    check("그룹 수", st.groups == 5, str(st.groups))
    check("전부 작성", st.written == 5, st.summary)
    check("유실 0", st.lost == 0, st.summary)
    check("요약에 분모가 있다", "그룹 5 → 작성 5" in st.summary, st.summary)

    print("\n[12] 🔴 서킷브레이커 — 연속 실패 시 중단한다")
    p3 = make_project(tmp / "circuit")
    for i in range(10):
        (p3.source / "Game" / f"G{i}.h").write_text(f"class AG{i} {{}};\n", encoding="utf-8")
    many = [f"Source/Game/G{i}.h" for i in range(10)]
    st2 = synth.run(p3, changed=many, caller=boom)
    check(f"임계값 {synth.CIRCUIT_THRESHOLD} 에서 끊는다",
          st2.failed == synth.CIRCUIT_THRESHOLD, str(st2.failed))
    check("🔴 남은 그룹을 태우지 않는다", st2.failed < st2.groups, st2.summary)
    check("중단 사유를 남긴다", "연속 실패" in st2.aborted, st2.aborted)
    check("마지막 사유도 붙는다", "브로커" in st2.aborted, st2.aborted)

    print("\n[13] 게이트 거부는 서킷을 열지 않는다 (모델은 살아 있다)")
    st3 = synth.run(p3, changed=many, caller=llm("망가짐"))
    check("전부 시도한다", st3.refused == st3.groups, st3.summary)
    check("중단하지 않는다", not st3.aborted, st3.aborted)

    print("\n[14] skip_existing · limit — 감추지 않고 적는다")
    st4 = synth.run(p2, changed=allf, skip_existing=True, caller=llm(GOOD))
    check("이미 있으면 건너뛴다", st4.skipped == 5 and st4.written == 0, st4.summary)
    st5 = synth.run(p2, changed=allf, limit=2, caller=llm(GOOD))
    check("상한이 먹는다", st5.written == 2, st5.summary)
    check("🔴 남긴 것을 적는다", "상한" in st5.aborted and "미처리" in st5.aborted, st5.aborted)

    print("\n[15] 🔴 소스 0건은 예외 (빈 배치를 성공으로 보고하지 않는다)")
    for label, kwargs in (("빈 변경 목록", {"changed": []}),
                          ("전부 삭제됨", {"changed": ["Source/없는파일.h"]})):
        try:
            synth.run(p2, caller=llm(GOOD), **kwargs)
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
        return GOOD

    st6 = synth.run(p4, changed=["Source/Game/Kr.h"], caller=capture)
    check("합성이 된다", st6.written == 1, st6.summary)
    check("🔴 한글 주석이 프롬프트에 살아서 들어간다",
          "몬스터 스폰을 관리한다" in seen["prompt"], seen["prompt"][:120])
    check("인코딩 분포를 보고한다", st6.encodings.cp949 == 1, st6.encodings.summary)

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

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'='*46}\n통과 {PASS} · 실패 {FAIL}\n{'='*46}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
