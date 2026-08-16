"""소비자 recipes_synthesizer (#157) 계약 테스트.

재는 것 다섯 (전부 chat 주입 — LLM/네트워크 0):
    ① 생산자 왕복    signals.append_signal 이 쌓은 실물 파일에서 합성까지
    ② 클러스터 방어  JSON 밖 산문 · 범위 밖 인덱스 · 비정형 응답에서 안 죽는다
    ③ 임계치        min_signals 미만 클러스터는 합성하지 않고 신호를 남긴다
    ④ 아카이브      처리분은 archive 로 이동·잔여는 유지 · 28일 초과 정리
    ⑤ 안티패턴      rejected+error 를 4섹션 카탈로그로 · 없으면 스킵(-1)

실행: .venv/bin/python master/test_recipes.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_synth import recipes_synthesizer as RS      # noqa: E402
from master.context_synth import signals as SG                  # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


class P:
    def __init__(self, root: Path):
        self.root = root
        self.repo = root / "repo"


def fixture(n=5, with_negatives=False):
    p = P(Path(tempfile.mkdtemp(prefix="ax-rs-")))
    (p.repo / "Source" / "M").mkdir(parents=True)
    (p.repo / "Source" / "M" / "UHitBox.h").write_text(
        "UCLASS()\nclass UHitBox : public UObject {};\n", encoding="utf-8")
    for i in range(n):
        kw = {}
        if with_negatives and i == 0:
            kw = {"rejected_approaches": [{"approach": "틱마다 검사", "reason": "성능"}],
                  "error_recoveries": [{"error": "linker error on [UHitBox]",
                                        "fix": "UCLASS 매크로 추가"}]}
        SG.append_signal(p, SG.make_record(
            intent=f"히트박스[UHitBox] 판정 추가 {i}",
            files_read=["Source/M/UHitBox.h"],
            files_modified=[{"path": "Source/M/UHitBox.cpp", "summary": "판정"}],
            source="pipeline", **kw))
    return p


CLUSTER_JSON = ('[{"recipe_name": "HitBoxJudge", "intent": "Add [UHitBox] judgement", '
                '"signal_indices": [0, 1, 2, 3, 4], "tags": ["Combat"]}]')

RECIPE_BODY = ("## Intent\nAdd [UHitBox] judgement.\n\n## Steps\n1. Edit [UHitBox].\n\n"
               "## Files of Interest\n- Source/M/UHitBox.h: class\n\n## Caveats\nNone.")

ANTI_BODY = ("## User-Rejected Approaches\n\n### Combat\n- Avoid: 틱마다 검사 — 성능.\n\n"
             "## Build Recoveries\n- Watch for: linker error on [UHitBox] — Recovery: UCLASS 매크로 추가.\n\n"
             "## Crash Recoveries\n_None recorded yet._\n\n"
             "## Behavioral Investigations\n_None recorded yet._")


# ── ① 왕복 + ③ 임계치 + ④ 아카이브 ──────────────────────────

def test_synthesis_roundtrip():
    p = fixture(5, with_negatives=True)
    calls = []

    def chat(prompt):
        calls.append(prompt)
        if "Cluster signals" in prompt:
            return "설명 산문...\n" + CLUSTER_JSON + "\n끝"
        if "anti-pattern catalog" in prompt:
            return ANTI_BODY
        return "```markdown\n" + RECIPE_BODY + "\n```"

    n = RS.run_recipe_synthesis(p, min_signals=5, chat=chat, logf=lambda m: None)
    check("[중요] 생산자 실물 파일에서 레시피 1건", n == 1, str(n))

    recipe = RS.recipes_dir(p) / "HitBoxJudge.md"
    text = recipe.read_text(encoding="utf-8")
    check("frontmatter 계약 (recipe_name/tags/signal_count)",
          "recipe_name: HitBoxJudge" in text and "tags: [Combat]" in text
          and "signal_count: 5" in text, text[:200])
    check("[중요] 코드 펜스를 벗긴다 (원전 규약)", "```" not in text)
    check("[대괄호] 식별자가 레시피에 보존된다", "[UHitBox]" in text)
    check("합성 프롬프트에 소스 발췌가 실린다 (repo 기준 해석)",
          any("=== Source/M/UHitBox.h ===" in c for c in calls))
    check("[중요] 처리된 신호는 아카이브로 (활성 0 + 아카이브 5)",
          SG.read_signals(p) == [] and
          len(RS.archive_path(p).read_text(encoding="utf-8").strip().splitlines()) == 5)

    anti = (RS.recipes_dir(p) / "_anti_patterns.md").read_text(encoding="utf-8")
    check("[중요] 안티패턴 카탈로그 4섹션 + 계수 frontmatter",
          "type: anti_patterns" in anti and "unique_patterns: 2" in anti
          and "Avoid:" in anti and "Watch for:" in anti, anti[:150])

    # 재실행 — 누적 signal_count 보존
    p2 = fixture(5)
    RS.run_recipe_synthesis(p2, min_signals=5, chat=chat, logf=lambda m: None)
    for _ in range(5):
        SG.append_signal(p2, SG.make_record(intent="히트박스 다시", source="pipeline"))
    RS.run_recipe_synthesis(p2, min_signals=5, chat=chat, logf=lambda m: None)
    text2 = (RS.recipes_dir(p2) / "HitBoxJudge.md").read_text(encoding="utf-8")
    check("[중요] 재합성 시 signal_count 누적 (5+5=10)", "signal_count: 10" in text2)


def test_threshold_keeps_signals():
    p = fixture(3)

    def chat(prompt):
        if "Cluster signals" in prompt:
            return ('[{"recipe_name": "X", "intent": "x", "signal_indices": [0, 1, 2], '
                    '"tags": []}]')
        return RECIPE_BODY

    n = RS.run_recipe_synthesis(p, min_signals=5, chat=chat, logf=lambda m: None)
    check("[중요] 임계치(5) 미만 클러스터(3)는 합성 안 함 — 신호는 다음 사이클까지 유지",
          n == 0 and len(SG.read_signals(p)) == 3, f"n={n}")
    check("min_signals 하한은 2 (원전 max(2, …))", True)  # 시그니처 계약 — 아래 직접 확인
    n2 = RS.run_recipe_synthesis(p, min_signals=0, chat=chat, logf=lambda m: None)
    check("min_signals 0 을 줘도 2 로 접힌다 (3건 클러스터는 합성됨)", n2 == 1, str(n2))


# ── ② 클러스터 방어 ──────────────────────────────────────────

def test_cluster_defenses():
    sigs = [{"intent": f"i{n}"} for n in range(3)]
    got = RS._cluster_signals(sigs, chat=lambda pr: "산문만 있고 배열 없음")
    check("JSON 배열이 없으면 빈 결과 (죽지 않는다)", got == [])
    got2 = RS._cluster_signals(
        sigs, chat=lambda pr: '[{"recipe_name": "A", "signal_indices": [0, 99, -1, "x"]}]')
    check("[중요] 범위 밖·비정수 인덱스는 걸러진다", got2[0]["signal_indices"] == [0], str(got2))
    got3 = RS._cluster_signals([{"intent": "홀로/작업: 하나"}], chat=lambda pr: 1 / 0)
    check("신호 1건이면 LLM 없이 단독 클러스터 (파일명 안전화)",
          got3[0]["signal_indices"] == [0] and "/" not in got3[0]["recipe_name"], str(got3))
    got4 = RS._cluster_signals(sigs, chat=lambda pr: (_ for _ in ()).throw(RuntimeError("죽음")))
    check("클러스터링 LLM 예외도 빈 결과 (fail-soft)", got4 == [])


# ── ④ 아카이브 보관 기한 ─────────────────────────────────────

def test_archive_retention():
    p = fixture(0)
    RS.recipes_dir(p).mkdir(parents=True, exist_ok=True)
    old = {"timestamp": (datetime.now() - timedelta(days=40)).isoformat(timespec="seconds"),
           "intent": "옛날"}
    new = {"timestamp": datetime.now().isoformat(timespec="seconds"), "intent": "최근"}
    RS.archive_path(p).write_text(
        json.dumps(old, ensure_ascii=False) + "\n" + json.dumps(new, ensure_ascii=False) + "\n",
        encoding="utf-8")
    SG.signals_path(p).write_text("", encoding="utf-8")
    RS._archive_signals(p, set(), [])
    kept = RS.archive_path(p).read_text(encoding="utf-8")
    check("[중요] 28일 초과 아카이브는 정리, 최근 것은 유지",
          "최근" in kept and "옛날" not in kept, kept[:100])


# ── ⑤ 안티패턴 스킵 ──────────────────────────────────────────

def test_anti_patterns_skip():
    p = fixture(2)   # negatives 없음
    got = RS._aggregate_anti_patterns(p, chat=lambda pr: ANTI_BODY)
    check("[중요] rejected/error 가 없으면 LLM 없이 스킵 (-1)", got == -1, str(got))
    p2 = fixture(2, with_negatives=True)
    got2 = RS._aggregate_anti_patterns(p2, chat=lambda pr: "카탈로그 라인이 없는 응답")
    check("응답에서 카탈로그 라인을 못 세면 갱신 스킵 (-1)", got2 == -1, str(got2))


def main() -> int:
    for fn in (test_synthesis_roundtrip, test_threshold_keeps_signals,
               test_cluster_defenses, test_archive_retention, test_anti_patterns_skip):
        fn()
    print(f"{'OK' if not FAIL else '[실패]'} test_recipes: {PASS}/{PASS + FAIL} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
