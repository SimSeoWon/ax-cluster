"""골조 생성 레인 A/B — 🔴 **`DEFAULT_MODEL` 을 측정으로 정한다** (소 1.1.1 후속).

## 왜 재는가

`DEFAULT_MODEL = "claude:opus"` 는 **추론으로 정한 값**이다 — 원전이 Opus 를 썼다는 사용자
기억 + *"골조는 1회이고 모든 조각의 계약이라 값을 쓸 자리"* 라는 논리. 🔴 **이 저장소의 규칙은
추측 대신 재는 것**이고(가중치를 눈으로 만지다 한 번 나빠진 전례), 여기도 예외가 아니다.

## 무엇으로 점수를 매기나 — 🔴 **결정적 지표만**

LLM 에게 *"어느 골조가 낫냐"* 를 묻지 않는다. 골조의 좋음은 우리가 이미 코드로 정의해 뒀다:

    동결 선언 수      계약이 될 것이 몇 개인가        많을수록 좋다 (0이면 골조가 아니다)
    [PSEUDO] 수       채울 자리가 있는가              0이면 골조가 아니다
    요청 파일 일치     달라는 파일을 줬는가            빠뜨림·군더더기
    관계 준수         🔴 그래프가 말한 부모를 썼는가   지어낸 부모는 실패다
    태그 보존         [DOC]/[STATE]/[BIND] 를 썼나
    펜스 잔재         마크다운을 섞었나 (감점)
    시간·글자수

🔴 **「관계 준수」가 이 벤치마크의 핵심이다.** 골조가 틀린 부모를 상속하면 N개 조각이 전부
컴파일 실패한다 — 그게 골조에 값을 쓸 이유의 실체이므로, 그것을 직접 잰다.

## 노는 기계를 쓴다 (사용자 지적 2026-08-11)

    claude:opus   마스터의 상용 CLI
    agy           마스터의 Antigravity CLI
    qwen2.5-coder:14b   브로커 → 상주 노드 (RTX 3060 `.2`)
    35B-A3B IQ2_M       브로커 → BC-250 `.43`

⚠️ 실패한 레인도 **기록한다** — *"응답이 없었다"* 와 *"응답이 나빴다"* 는 다른 사실이다.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_search.paths import resolve                 # noqa: E402
from master.work import skeleton as S                            # noqa: E402

LANES = [
    ("claude:opus", "마스터 CLI · Opus"),
    ("agy", "마스터 CLI · Antigravity"),
    ("qwen2.5-coder:14b", "브로커 → 상주 노드"),
    ("hf.co/bartowski/Qwen_Qwen3.5-35B-A3B-GGUF:IQ2_M", "브로커 → BC-250"),
]

# 🔴 실제 코드베이스에 붙는 과제로 잰다 — 신규 클래스 하나 + **실재하는 협력 클래스**.
# 실재 클래스를 끼우는 이유: 그래야 grounding(선언부·관계)이 실제로 재료를 갖는다.
SPEC = S.SkeletonSpec(
    stem="MissionTaskSnapshot",
    files=["Source/ModularStage/Mission/TaskSystem/MissionTaskSnapshot.h",
           "Source/ModularStage/Mission/TaskSystem/MissionTaskSnapshot.cpp"],
    classes=["UMissionTaskSnapshot", "UMissionTaskExecutor"],
    instruction=(
        "UMissionTaskExecutor 의 진행 상태를 저장하고 되돌릴 수 있는 컴포넌트 "
        "UMissionTaskSnapshot 을 만든다. 실행기의 현재 단계를 캡처하고, 저장된 캡처로 "
        "되돌리며, 캡처가 유효한지 검사한다. 저장은 여러 개를 쌓을 수 있어야 한다."
    ),
)

# 관계 준수 채점의 근거 — 그래프가 말한 부모(협력 클래스의 조상)
EXPECT_PARENT_OF = "UMissionTaskExecutor"


def score(paths, sk: S.Skeleton, *, elapsed: float, expect_parents: list) -> dict:
    body = "\n".join(sk.files.values())
    got_files = set(sk.files)
    want = set(SPEC.files)
    # 🔴 지어낸 부모를 잡는다 — 골조가 틀린 부모를 쓰면 N개 조각이 전부 깨진다
    invented_parent = ""
    for line in body.splitlines():
        t = line.strip()
        if t.startswith("class ") and ":" in t:
            bases = [b.strip().replace("public ", "").replace("private ", "")
                     .replace("protected ", "").rstrip("{ ").strip()
                     for b in t.split(":", 1)[1].split(",")]
            for b in bases:
                if b and not b.startswith(("U", "A", "F", "I", "E")):
                    continue
                if b and b not in expect_parents and b not in ("UObject", "UActorComponent",
                                                               "UDataAsset", "USceneComponent"):
                    invented_parent = invented_parent or b
    return {
        "frozen": len(sk.frozen),
        "pseudo": sk.pseudo,
        "depths": sk.depth_set,
        "files_ok": sorted(got_files) == sorted(want),
        "missing_files": sorted(want - got_files),
        "extra_files": sorted(got_files - want),
        "tags_kept": sum(1 for t in S.PERMANENT_TAGS if t in body),
        "fence_left": bool([n for n in sk.notes if "펜스" in n]),
        "invented_parent": invented_parent,
        "chars": len(body),
        "elapsed": round(elapsed, 1),
        "ok": sk.ok,
        "notes": sk.notes,
        "grounding": sk.grounding,
    }


def main(argv) -> int:
    only = [a for a in argv if not a.startswith("-")]
    paths = resolve("")
    from master.graph import class_graph as cg
    expect = [EXPECT_PARENT_OF] + cg.find_ancestors(paths, EXPECT_PARENT_OF)
    print(f"프로젝트 {paths.name} · 대상 {SPEC.stem}")
    print(f"🔴 그래프가 말하는 협력 클래스 조상: {expect}")
    print(f"프롬프트 grounding: 선언부 + 관계 + 규범\n")

    out: dict = {}
    for model, label in LANES:
        if only and not any(o in model for o in only):
            continue
        print(f"=== {label}  [{model}]")
        t0 = time.time()
        try:
            sk = S.build(paths, SPEC, model=model, timeout=1800)
        except Exception as e:                                   # noqa: BLE001
            # ⚠️ 실패도 사실이다 — 조용히 빼면 "그 레인은 안 재봤다" 와 구분이 안 된다
            out[model] = {"error": str(e)[:300], "elapsed": round(time.time() - t0, 1)}
            print(f"  🔴 실패 {out[model]['elapsed']}초 — {str(e)[:160]}\n")
            continue
        s = score(paths, sk, elapsed=time.time() - t0, expect_parents=expect)
        out[model] = s
        mark = "✅" if s["ok"] and not s["invented_parent"] else "🔴"
        print(f"  {mark} 동결 {s['frozen']} · [PSEUDO] {s['pseudo']} · {s['chars']}자 · "
              f"{s['elapsed']}초 · 파일일치 {s['files_ok']}")
        if s["invented_parent"]:
            print(f"     🔴 지어낸 부모: {s['invented_parent']}")
        for n in s["notes"][:3]:
            print(f"     {n}")
        print()

    p = Path("bench_skeleton_result.json")
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"원본 저장: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
