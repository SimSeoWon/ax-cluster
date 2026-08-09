"""분산 대 단독 비교 계측 (사용자 요청 2026-08-09).

## 무엇을 재는가 — 그리고 **무엇을 재지 않는가**

    A  요청자 단독      `.33` 이 온톨로지를 받아 스스로 작업
    B  분산 1대         마스터가 워커 한 대에 파견
    C  분산 2대         두 워커에 나눠 파견 (병렬)
    × S1 단일 파일 / S2 다중 파일

🔴 **A 와 B/C 는 같은 모델이다**(셋 다 Claude Code). 그러므로 이 표가 답하는 것은
*"분산이 더 똑똑한가"* 가 **아니라** *"오케스트레이션 비용이 병렬 이득을 넘는가"* 다.
모델 품질 비교는 로컬 LLM 위임을 팔로 넣어야 성립한다.

## 🔴 `.33` 은 worktree 로만 건드린다

사람의 메인 작업 PC 이고 미커밋 `.uasset` 이 있다. 브랜치를 바꾸면 **복구할 수 없다.**
그래서 A 는 별도 worktree 에서 돈다 — 게스트 규칙 그대로다. 그 준비 비용은 A 에 포함해
기록한다(숨기면 비교가 거짓이 된다).

## 🔴 아무것도 push 하지 않는다

비교 대상은 *작업*이지 배관이 아니다. 각 팔은 자기 트리에서 파일을 고치고, 우리는
`git diff` 를 떠서 지표를 낸 뒤 **되돌린다.** 큐도 쓰지 않는다.

## 품질은 결정적으로 잰다

생성된 diff 의 **클래스형 식별자**를 클래스 그래프(1,806개 실측)와 대조한다. 그래프에 없는
이름은 지어낸 것이다 — `verify_facts` 가 호출 관계에 대해 하는 일의 식별자 판이다.
⚠️ **근사다**: 엔진 클래스(`UObject` 등)와 지역 타입은 그래프에 없을 수 있어 오탐이 난다.
그래서 **엔진 접두사 화이트리스트**를 두고, 남은 것을 *의심*으로만 보고한다.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from .client import bundle
from .context_search.paths import ProjectPaths

# UE 엔진 기본형은 프로젝트 그래프에 없다 — 오탐을 줄인다(정확성이 아니라 항법의 문제).
ENGINE_PREFIXES = ("UObject", "AActor", "FString", "FName", "FText", "TArray", "TMap",
                   "TSet", "TSubclassOf", "UClass", "UWorld", "UStruct", "FVector",
                   "FRotator", "FTransform", "UAnimNotify", "AAIController", "UActorComponent",
                   "UUserWidget", "UPrimitiveComponent", "USceneComponent", "FGuid")
_IDENT = re.compile(r"\b([UAFIE][A-Z][A-Za-z0-9_]{2,})\b")


@dataclass
class Cell:
    """한 칸의 실측."""
    arm: str
    size: str
    host: str = ""
    seconds: float = 0.0
    ok: bool = False
    files: int = 0
    added: int = 0
    usage: dict = field(default_factory=dict)
    unknown: list = field(default_factory=list)     # 그래프에 없는 식별자 (의심)
    known: int = 0
    note: str = ""

    @property
    def cost(self) -> float:
        return float(self.usage.get("total_cost_usd") or 0.0)

    @property
    def tok(self) -> tuple:
        u = self.usage.get("usage") or {}
        return (int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0),
                int(u.get("cache_creation_input_tokens") or 0),
                int(u.get("cache_read_input_tokens") or 0))

    @property
    def row(self) -> str:
        i, o, cc, cr = self.tok
        halluc = f"{len(self.unknown)}" if self.ok else "—"
        return (f"| {self.arm} | {self.size} | {self.host or '—'} | "
                f"{'✅' if self.ok else '🔴'} | {self.seconds:.0f}s | "
                f"${self.cost:.3f} | {o:,} | {cc:,} | {cr:,} | "
                f"{self.files}/{self.added} | {self.known} | {halluc} |")


HEADER = ("| 팔 | 크기 | 호스트 | 결과 | 시간 | 비용 | 출력tok | 캐시생성 | 캐시읽기 | "
          "파일/추가줄 | 실재식별자 | 의심 |\n"
          "|---|---|---|---|---|---|---|---|---|---|---|---|")


def graph_classes(paths: ProjectPaths) -> set:
    """클래스 그래프의 이름들. 비면 품질 판정을 **하지 않는다**(0을 성공으로 보지 않는다)."""
    from .graph import db as gdb
    if not gdb.exists(paths):
        return set()
    conn = gdb.connect(paths)
    try:
        return {r["name"] for r in conn.execute("SELECT name FROM classes")}
    finally:
        conn.close()


def judge(diff: str, known: set) -> tuple:
    """`(실재 식별자 수, 의심 목록)`. 🔴 **추가된 줄만** 본다 — 원본 코드를 세면 무의미하다."""
    if not known:
        return 0, []
    hits, unknown = 0, []
    for line in diff.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        for name in _IDENT.findall(line):
            if name in known or name.startswith(ENGINE_PREFIXES):
                hits += 1
            elif name not in unknown:
                unknown.append(name)
    return hits, unknown


def _sh(facts, cmd: str, timeout: int = 120) -> tuple:
    return bundle._ssh(facts.host, facts.user, cmd, timeout=timeout)


def _q(facts, path: str) -> str:
    return f'"{path}"'


def run_one(facts, *, workdir: str, task_id: str, manifest: str, timeout: int = 1800) -> tuple:
    """한 호스트에서 한 번 돌린다. `(Cell 조각, diff)`. **push 하지 않는다.**"""
    # 🔴 **매니페스트는 `workdir` 안에 놓는다** — `facts.path` 가 아니다.
    #
    # 실측 2026-08-09에 이걸 틀려서 한 팔 전체를 버렸다: `.33` 은 worktree 에서 돌았는데
    # 매니페스트는 메인 체크아웃으로 갔다. 에이전트는 없는 파일을 찾아 헤맸고, 그 탐색이
    # **캐시 읽기 620k · 768초**로 잡혀 *"분산이 4배 싸다"* 는 거짓 결론을 낳을 뻔했다.
    # 계측은 **셋업이 맞다는 것을 먼저 증명**한 뒤에만 의미가 있다.
    import dataclasses
    here = dataclasses.replace(facts, path=workdir)
    rel = f"{bundle.WORK_REL}/{task_id}/{MANIFEST_NAME}"
    bundle._remote_write(here, rel, manifest, base="checkout")

    # 🔴 놓았다고 믿지 않는다 — 읽히는지 확인하고, 안 되면 **재지 않는다.**
    sep = "\\" if facts.windows else "/"
    probe = f"{workdir}{sep}{bundle.WORK_REL.replace('/', sep)}{sep}{task_id}{sep}{MANIFEST_NAME}"
    rc, _ = _sh(facts, (f'if exist "{probe}" (exit 0) else (exit 1)') if facts.windows
                else f'test -f "{probe}"')
    if rc != 0:
        raise RuntimeError(f"매니페스트가 실행 위치에 없다: {probe} — 이 상태로 재면 "
                           f"'지시서를 찾아 헤맨 비용'을 작업 비용으로 잘못 읽는다")

    instr = INSTRUCTION.format(work=bundle.WORK_REL, task=task_id)
    cd = f'cd /d "{workdir}"' if facts.windows else f'cd "{workdir}"'
    cmd = f'{cd} && claude -p --output-format json --dangerously-skip-permissions "{instr}"'

    t0 = time.monotonic()
    rc, out = _sh(facts, cmd, timeout=timeout)
    secs = time.monotonic() - t0

    usage = {}
    t = (out or "").strip()
    if t.startswith("{"):
        try:
            d = json.loads(t)
            usage = {k: v for k, v in d.items() if k != "result"}
        except ValueError:
            pass
    rc2, diff = _sh(facts, f'git -C {_q(facts, workdir)} diff -- Source/')
    return secs, rc, usage, (diff if rc2 == 0 else "")


MANIFEST_NAME = "manifest.md"
# 🔴 ASCII — 워커 콘솔 cp949 에서 한글 명령줄은 깨진다(실측).
INSTRUCTION = (
    "Read ./{work}/{task}/manifest.md and do exactly what it says, editing files in place "
    "in this working tree. Judge from the source files here, not from memory. "
    "Do NOT run any git command: no branch, no commit, no push. "
    "Finish with one line: RESULT: DONE (or RESULT: BLOCKED and why)."
)


def revert(facts, workdir: str) -> None:
    """트리를 되돌린다. 🔴 `Source/` 만 — 범위 밖은 우리 것이 아니다."""
    _sh(facts, f'git -C {_q(facts, workdir)} checkout -- Source/')
