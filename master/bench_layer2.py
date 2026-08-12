"""층2 모델 선정 벤치 — 🔴 **실측으로 고른다** (소 2.2.1).

## 왜 하네스를 새로 쓰나

마일스톤 문서가 *"`bench_quality2.py` 하네스 재활용"* 이라 적어 뒀지만 그 파일은 원전(AgentTest)
쪽이고 이 저장소에 없다. 그리고 재는 것이 다르다 — 그쪽은 **작성 품질**을 재고, 여기는
**검출력**을 잰다. 같은 하네스로 될 일이 아니다.

## 🔴 표본은 지어내지 않는다 — 이 프로젝트에서 **실제로 났던 실패**다

    P1 없는 반환값      error C4716 값을 반환해야 합니다        리포트 12 §6.3 ②
    P2 괄호/세미콜론     layer2_verify 의 자체 표본
    P3 없는 열거값       error C2065 'None' 선언되지 않은 식별자  리포트 12 §6.3 ③
    P4 매크로 오용       GENERATED_BODY/UPROPERTY 오용
    N1 정상 `.cpp`      실제 소스 그대로 (통과해야 한다)
    N2 정상 헤더        한국어 주석 포함 (통과해야 한다)

🔴 **음성 표본이 있어야 의미가 있다.** 전부 막는 검증기는 검출력 100% 인데 쓸 수 없다 —
*정상 작업을 막는 게이트가 통과시키는 게이트보다 나쁘다.*

## 🔴 채점은 결정적이다

`verdict.parse_verdict` 의 판정(APPROVE / REQUEST_CHANGES / 계약 위반)만 본다. **LLM 에게
우열을 묻지 않는다** — 골조 A/B 에서 쓴 것과 같은 규율이다.

## 🔴 P3 은 grounding 없이는 잡을 수 없다 (설계상)

`EMissionType::None` 이 틀렸다는 것은 **그 열거형의 정의를 봐야** 안다. 파일만 주면 어떤 모델도
추측할 뿐이다. 그래서 P3 은 **선언부를 함께 주는 변형**(`P3g`)을 따로 둔다 — 층2 프롬프트에
grounding 을 실을지 말지를 이 차이로 결정한다.

사용:
    .venv/bin/python master/bench_layer2.py            # 후보 전부
    .venv/bin/python master/bench_layer2.py agy claude  # 골라서
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import layer2_verify as L2        # noqa: E402
from master.verdict import parse_verdict      # noqa: E402

# ── 표본 ────────────────────────────────────────────────────────────────────────

P1 = ("Source/ModularStage/Mission/MSSnapshot.cpp", """#include "MSSnapshot.h"

bool UMSSnapshot::IsSnapshotValid() const
{
\t// 스냅샷이 유효한지 확인한다
}

void UMSSnapshot::Clear()
{
\tSteps.Empty();
}
""")

P2 = ("Source/ModularStage/Combat/Foo.cpp", """#include "Foo.h"

void AFoo::Tick(float Dt)
{
\tSuper::Tick(Dt)
\tif (IsValid(Target) {
\t\tTarget->Ping();
\t}
""")

_P3_BODY = """#include "MSMissionTask.h"
#include "ModularStage/Table/TableEnum.h"

void UMSMissionTask::Reset()
{
\tMissionType = EMissionType::None;
\tStepIndex = 0;
}
"""
P3 = ("Source/ModularStage/Mission/MSMissionTask.cpp", _P3_BODY)

# 🔴 같은 파일에 **선언부를 함께** 준 변형 — grounding 의 효과를 재려는 것이다
P3G_DECLS = """
=== DECLARATIONS FROM INCLUDED HEADERS (authoritative) ===
--- ModularStage/Table/TableEnum.h ---
UENUM(BlueprintType)
enum class EMissionType : uint8
{
\tMain,
\tSub,
};

UENUM(BlueprintType)
enum class EMissionExecutorState : uint8
{
\tNone,
\tRunning,
\tComplete,
};
=== END DECLARATIONS ===
"""

P4 = ("Source/ModularStage/UI/MSWidget.h", """#pragma once

#include "CoreMinimal.h"
#include "MSWidget.generated.h"

UCLASS()
class MODULARSTAGE_API UMSWidget : public UUserWidget
{
\tGENERATED_BODY;

public:
\tUPROPERTY
\tint32 Count;

\tUFUNCTION(BlueprintCallable)
\tvoid Refresh()
};
""")

N1 = ("Source/ModularStage/Mission/TaskSystem/MissionTask_SetCamera.cpp", """#include "MissionTask_SetCamera.h"
#include "ModularStage/Table/MissionTaskTable.h"

UMissionTask_SetCamera::UMissionTask_SetCamera()
{
}

void UMissionTask_SetCamera::SetData(const FMissionTaskInfo& InTaskInfo)
{
\tSuper::SetData(InTaskInfo);

\tTileIndex = InTaskInfo.IntValue;
}

ETaskExecutorResult UMissionTask_SetCamera::DoAction()
{
\treturn ETaskExecutorResult::Complete;
}

void UMissionTask_SetCamera::Clear()
{
\tSuper::Clear();
}
""")

N2 = ("Source/ModularStage/Mission/MissionPropsBase.h", """#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "MissionPropsBase.generated.h"

UCLASS()
class MODULARSTAGE_API AMissionPropsBase : public AActor
{
\tGENERATED_BODY()

public:
\tAMissionPropsBase();

\t// [DOC] 미션 소품의 공통 기반 — 미션이 시작될 때 배치되고 끝나면 회수된다.
\tvirtual void OnMissionStart();

\t// 미션이 끝났을 때 정리한다. 상태는 남기지 않는다.
\tvirtual void OnMissionEnd();

protected:
\tUPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Mission")
\tint32 PropsId = -1;
};
""")


@dataclass
class Sample:
    key: str
    files: list
    should_block: bool
    what: str
    extra: str = ""          # grounding 등 프롬프트에 덧붙일 것


SAMPLES = [
    Sample("P1", [P1], True, "없는 반환값 (C4716) — 실측"),
    Sample("P2", [P2], True, "괄호/세미콜론"),
    Sample("P3", [P3], True, "없는 열거값 (C2065) — grounding 없음"),
    Sample("P3g", [P3], True, "없는 열거값 — 🔴 선언부 제공", extra=P3G_DECLS),
    Sample("P4", [P4], True, "UE 매크로 오용"),
    Sample("N1", [N1], False, "🔴 정상 `.cpp` (막으면 안 된다)"),
    Sample("N2", [N2], False, "🔴 정상 헤더 · 한국어 주석 (막으면 안 된다)"),
]


# ── 후보 백엔드 ─────────────────────────────────────────────────────────────────
#
# 🔴 로컬도 후보다. 모토는 *"검증에만 상용 토큰"* 이지만 **로컬이 잡으면 그게 더 낫다** —
#    재 보고 정한다. 브로커 레인은 `synth.generate` 규약을 그대로 쓴다.

def _broker(model: str, num_ctx: int = 16384):
    """브로커 레인. `ontology.synth.generate` 가 모델 이름으로 백엔드를 고른다(같은 규약).

    ⚠️ `num_ctx` 를 넉넉히 준다 — 표본 + 계약 + grounding 이 8K 를 넘으면 **앞이 잘려**
    판정이 아니라 절단을 재게 된다.
    """
    def call(prompt: str, *, timeout: int = L2.TIMEOUT_SEC):
        from master.ontology import synth
        from master.work.generate import DEFAULT_BROKER
        try:
            return synth.generate(prompt, model, broker=DEFAULT_BROKER,
                                  num_ctx=num_ctx, timeout=timeout)
        except Exception:                                # noqa: BLE001
            return None
    return call


CANDIDATES = {
    "agy": L2.call_agy,
    "claude:sonnet": lambda p, *, timeout=L2.TIMEOUT_SEC: L2.call_claude(
        p, timeout=timeout, model="sonnet"),
    "claude:opus": lambda p, *, timeout=L2.TIMEOUT_SEC: L2.call_claude(
        p, timeout=timeout, model="opus"),
    "qwen2.5-coder:14b": _broker("qwen2.5-coder:14b"),
    "35b": _broker("hf.co/bartowski/Qwen_Qwen3.5-35B-A3B-GGUF:IQ2_M"),
}


@dataclass
class Row:
    backend: str
    hits: int = 0            # 양성을 맞게 막았다
    misses: int = 0          # 🔴 양성을 통과시켰다 (가장 나쁘다)
    false_alarms: int = 0    # 🔴 음성을 막았다 (정상 작업 차단 — 이것도 나쁘다)
    correct_pass: int = 0
    broken: int = 0          # 계약 위반 (판정을 못 냈다) → fail-closed 로 차단됨
    seconds: float = 0.0
    detail: list = field(default_factory=list)

    @property
    def score(self) -> str:
        return f"검출 {self.hits}/{self.hits + self.misses} · 오탐 {self.false_alarms}"


def run_one(name: str, call, sample: Sample, *, timeout: int) -> tuple:
    """`(막았나, 계약위반, 초)`. 🔴 판정은 `verdict` 계약으로만 읽는다."""
    prompt = L2.build_prompt(sample.files)
    if sample.extra:
        prompt += "\n" + sample.extra
    t0 = time.time()
    raw = call(prompt, timeout=timeout)
    el = time.time() - t0
    if raw is None:
        return None, True, el                # 백엔드 미가용/실패 → fail-closed
    v = parse_verdict(raw, backend=name)
    return (not v.approved), bool(v.failure), el


def bench(names: list, *, timeout: int = 300) -> list:
    rows = []
    for name in names:
        call = CANDIDATES[name]
        r = Row(backend=name)
        for s in SAMPLES:
            blocked, broken, el = run_one(name, call, s, timeout=timeout)
            r.seconds += el
            if blocked is None:
                r.broken += 1
                r.detail.append(f"{s.key}: 🔴 응답 없음")
                continue
            if broken:
                r.broken += 1
            mark = "?"
            if s.should_block:
                if blocked:
                    r.hits += 1
                    mark = "✅ 막음"
                else:
                    r.misses += 1
                    mark = "🔴 놓침"
            else:
                if blocked:
                    r.false_alarms += 1
                    mark = "🔴 오탐"
                else:
                    r.correct_pass += 1
                    mark = "✅ 통과"
            r.detail.append(f"{s.key}: {mark} ({el:.0f}초)")
            print(f"  {name:18} {s.key:4} {mark:8} {el:5.0f}초  {s.what}")
        rows.append(r)
    return rows


def main(argv) -> int:
    names = [a for a in argv if a in CANDIDATES] or list(CANDIDATES)
    bad = [a for a in argv if a not in CANDIDATES]
    if bad:
        print(f"🔴 모르는 후보: {bad} — 가능한 것: {list(CANDIDATES)}")
        return 2
    print(f"층2 후보 {len(names)} × 표본 {len(SAMPLES)} "
          f"(양성 {sum(1 for s in SAMPLES if s.should_block)} · "
          f"음성 {sum(1 for s in SAMPLES if not s.should_block)})\n")
    rows = bench(names)
    print("\n=== 결과 ===")
    print(f"{'백엔드':20} {'검출':>8} {'놓침':>6} {'오탐':>6} {'정상통과':>8} "
          f"{'계약위반':>8} {'초':>7}")
    for r in rows:
        print(f"{r.backend:20} {r.hits:>8} {r.misses:>6} {r.false_alarms:>6} "
              f"{r.correct_pass:>8} {r.broken:>8} {r.seconds:>7.0f}")
    print("\n🔴 고르는 기준: **놓침 0 을 먼저** 보고(층2 의 존재 이유), 그 다음 **오탐 0**"
          "(정상 작업을 막으면 게이트가 못 쓰이게 된다), 마지막에 속도·비용.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
