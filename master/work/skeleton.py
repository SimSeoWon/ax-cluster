"""골조 생성 + **인터페이스 동결** (중 1.1 — §4.5 의 빈 첫 칸).

## 왜 이것이 병렬의 전제인가

클래스 단위 분할은 ***파일*** 충돌만 막는다. ***인터페이스*** 충돌은 못 막는다 — A 를 짠
모델과 B 를 짠 모델이 서로의 시그니처를 다르게 가정하면 **컴파일에서야 드러난다.** 그래서
원전은 이것을 *"강제"* 로 못박았다(사용자 2026-06-21): **클래스 관계·인터페이스는 골조에서
1회 확정, 워커는 본문만 채우고 변경 불가.**

그 동결이 drift 의 원천을 없애기 때문에, 원전이 검토했던 크로스-task 해시 박제나
`interface_revision.jsonl` 카나리가 **불필요해졌다.** 값싼 결정적 검사 하나가 그것들을 대체한다.

## [중요] 마스터는 골조를 파일로 쓰지 않는다

원전 `generate_skeletons_impl` 은 `repo_path` 에 **직접 write** 한다. 우리 경계는 다르다 —
*"파일은 윈도우를 떠나지 않는다 · 마스터는 인프라지 작업장이 아니다"*(§2.1). 그래서 이 모듈은
**텍스트만 돌려준다.** 파일로 쓰는 것은 작업장이고, 운반은 매니페스트다(`manifest.py`,
§4.7 ④ — `task_data` 는 전송 수단이 아니다).

## [중요] 동결은 결정적이다 — LLM 0

골조를 만드는 것은 LLM 이지만, **무엇이 동결됐는지 읽어내는 것은 정규식**이다. 여기에 LLM 을
쓰면 *"결정적 게이트가 LLM 판단보다 위"* 라는 규칙이 첫 칸에서부터 깨진다. 추출기는 원전
`worker/validator._frozen_decls` 를 그대로 이식했다 — 이미 prod 에서 굴러 본 것이다.

키는 본문 `{` 나 `;` **앞까지** + 공백 정규화다. 그래서 인라인 `[PSEUDO]` 본문을 채우면서
`;` 가 `{…}` 로 바뀌어도 **같은 키**로 남는다(선언과 정의가 한 키). 반대로 시그니처를 고치면
키가 달라져 즉시 잡힌다.

## 태그 계약 — 지우는 것과 남기는 것 (원전 §스켈레톤 주석 태그)

    [PSEUDO] · [PSEUDO:N] · [IMPL]              워커가 **구현 후 그 줄을 지운다**
    [DOC] · [STATE] · [BIND] · [REPLICATED]     [중요] **절대 보존** — 삭제·수정 금지
    태그 없는 주석                                보존 (임의 판단으로 제거 금지)

## [중요] **「무엇을 왜」는 `[DOC]`, 「여기를 채워라」만 `[PSEUDO]`** (사용자 결정 2026-08-27)

종전에는 작업 지시가 통째로 `[PSEUDO]` 에 들어가서 **구현과 함께 사라졌다.** 그래서 나중에
`main` 에서 그 함수를 읽는 사람에게 *"왜 이렇게 생겼나"* 가 남지 않았다. 둘을 가른다:

    // [DOC] N 이 0 이하이면 0 을 돌려준다 — 호출부가 음수를 거르지 않는다   ← 보존, main 까지 산다
    // [PSEUDO] 위 규칙대로 합을 계산한다                                    ← 휘발, 구현하면 지운다

[주의] **「작업 완료」 마킹은 만들지 않는다.** 그것은 **워커의 자기 신고**이고, 이 저장소가
`RESULT: DONE` 을 판정 근거로 안 쓰기로 한 것과 같은 부류다(`layer1.py` 의 실측: *"워커는 실제로
계약을 어겼다 — 마커를 응답 파일에 써 넣었다"*). **`[PSEUDO]` 가 사라진 것이 곧 완료 표시**이고,
그것은 층1이 **결정적으로** 검사한다 — 위조하면 통과가 안 된다.
[중요] 머지 시점의 판단 근거는 주석이 아니라 **git** 이다: 골조 원본이 작업 브랜치
`task/<work_id>/base` 에 영구 보존되므로 `diff base...tip` 이 「지시 vs 구현」을 사실로 낸다
(`#319`).

[주의] **getter/setter 에는 주석을 달지 않는다** — 시그니처로 충분하고, 불필요한 주석은 워커
프롬프트의 노이즈가 된다.

## [중요] 골조는 "본문 없음" 이 아니라 **"컴파일되는 최소 본문"** 이다 (실측 2026-08-11)

소 1.1.5 게이트를 처음 실전 구동했을 때 **골조가 빌드에서 떨어졌다**:

    error C4716: 'UMissionTaskSnapshot::IsSnapshotValid': 값을 반환해야 합니다

본문을 `// [PSEUDO] …` 주석 하나로만 두면 **반환값 있는 함수는 컴파일되지 않는다.** 이건
모델의 실패가 아니라 **계약의 구멍**이었다 — 원전도 골조를 빌드해 통과시켰으니(Step 6) 같은
전제를 암묵적으로 갖고 있었다. 그래서 프롬프트가 못박는다: **non-void 는 `[PSEUDO]` 주석
바로 뒤에 최소 반환**(`return false;` · `return {};` · `return nullptr;`)을 둔다.

[중요] **게이트가 없었으면 이 구멍은 첫 분산 작업에서 N개 조각을 헛일로 만들고서야 드러났을 것이다.**

## [중요] 골조가 아니면 골조라고 하지 않는다 (fail-closed)

`[PSEUDO]` 가 하나도 없으면 그것은 **완성된 파일**이지 골조가 아니다. 원전은 그 경우 워커
태스크 등재를 **skip** 한다(글루 파일이 워커에게 배정되던 버그를 그렇게 고쳤다). 동결할 선언이
0개인 것도 같다 — 계약을 만들 수 없으면 병렬로 나눠도 안전하지 않다. **둘 다 거부한다.**
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..context_search.paths import ProjectPaths

# 뎁스 없는 `[PSEUDO]` 는 단일 태스크(하위 호환), `[PSEUDO:N]` 은 파일 내 순차 분할(소 1.2.4)
_PSEUDO = re.compile(r"\[PSEUDO(?::(\d+))?\]")
VOLATILE_TAGS = ("[PSEUDO]", "[IMPL]")
PERMANENT_TAGS = ("[DOC]", "[STATE]", "[BIND]", "[REPLICATED]")

# ── 동결 선언 추출 (원전 worker/validator.py 이식 + 실측으로 메운 구멍) ───────────
#
# [중요] **원전 목록에 구멍이 있었다** (실측 2026-08-11, 이 프로젝트 헤더 857개):
#
#     GENERATED_USTRUCT_BODY          97회   ← 원전 목록에 없다
#     DECLARE_LOG_CATEGORY_EXTERN     25회   ← 없다
#     DECLARE_DYNAMIC_MULTICAST_…     19회   ← 없다
#     UE_DECLARE_GAMEPLAY_TAG_EXTERN         ← 없다 (그래서 태그 헤더의 동결이 0개였다)
#
# 그래서 `GENERATED_*BODY` 와 `DECLARE_`/`UE_DECLARE_` 계열을 접두어로 받는다.
#
# [주의] **대문자 매크로를 통째로 받지는 않는다.** 같은 실측에서 `UE_LOG` 가 헤더의 **인라인 본문에
# 23회** 나왔다 — 그것까지 동결하면 워커가 로그 문구만 고쳐도 위반이 뜬다. *정상 작업을 막는
# 게이트가 통과시키는 게이트보다 나쁘다*(사실 게이트에서 이미 내린 판단). 프로젝트 고유
# 매크로(`PODS_SAFE_CALL` 130회 등)도 선언인지 문장인지 모르므로 넣지 않는다.
_DECL_MACRO = re.compile(
    r"^(GENERATED_\w*BODY|(UE_)?DECLARE_\w+|UPROPERTY|UFUNCTION|UCLASS|USTRUCT"
    r"|UENUM|UINTERFACE|UDELEGATE)\b")
_CLASS_DECL = re.compile(r"^(class|struct)\s+\w")
# `<반환타입…> <이름>(` — 타입 토큰 + 공백 + 이름 + `(`. 베어 호출 `Foo();` 는 안 걸린다.
_FUNC_SIG = re.compile(r"^[A-Za-z_][\w:<>,\*&\s~]*\s[~\w:]+\s*\(")
# 본문 문장 키워드 — `return Foo();` 가 선언으로 오인되지 않게
_STMT_KW = re.compile(r"^(return|if|else|for|while|switch|do|case|throw|delete|new"
                      r"|co_return|co_await|using|typedef)\b")

_FENCE_WRAP = re.compile(r"\A\s*```[a-zA-Z+]*\s*\n(.*?)\n?\s*```\s*\Z", re.DOTALL)
_FENCE_ANY = re.compile(r"^\s*```", re.MULTILINE)

HEADER_SUFFIXES = (".h", ".hpp")

# [중요] **골조는 상용 모델로 만든다** (사용자 2026-08-11: 원전이 *"클로드 오푸스 모델을 이용해
# 처리"* 했다). 모토(*작성은 무료 로컬*)와 충돌하지 않는다 — 그 모토는 **본문 대량 생산**
# 이야기이고, 골조는 **작업 하나당 1회**이면서 **모든 병렬 조각의 계약**이 된다. 틀린 골조는
# N개 조각을 전부 오염시키므로, 배칭 실측이 말한 것과 같은 논리로 여기가 값을 쓸 자리다.
# 레인 문법은 `synth.generate` 와 같다 — `claude:opus` · `claude` · `agy` · 그 밖은 브로커.
DEFAULT_MODEL = "claude:opus"


class SkeletonError(RuntimeError):
    """골조를 만들 수 없다. [중요] 삼키면 빈 골조가 계약처럼 보인다."""


def strip_comments(text: str) -> str:
    """`//` 줄과 `/* */` 블록을 지운다 — 태그가 선언 키에 섞이지 않게."""
    text = re.sub(r"/\*.*?\*/", " ", text or "", flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", text)


def frozen_decls(header: str) -> set:
    """헤더의 **동결 대상 선언 키 집합.** [중요] 결정적 — LLM 0.

    포함: UE 매크로 · `class`/`struct` 선언 · 함수 시그니처(선언이든 인라인 정의든).
    [주의] 생성자·단독 멤버변수 rename 은 커버하지 않는다(원전과 같은 한계) — 백스톱은
    층2 재점검과 통합 빌드다.

    [주의] **키를 줄 단위로 뽑는다** — 그래서 `class A { void f(int); };` 처럼 **한 줄에 몰아 쓴**
    선언은 `class A` 하나로만 잡히고 그 안의 함수는 동결되지 않는다(실측 2026-08-12, 소 1.4.2
    를 배선하다 확인). 이 프로젝트의 헤더는 UE 관례대로 줄을 나눠 쓰므로 실사용에서는 문제가
    없었지만(857개 회귀에서 동결 12,719개), **생성 코드가 한 줄로 뭉치면 조용히 헐거워진다.**
    """
    out: set = set()
    for raw in strip_comments(header).splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line:
            continue
        if _DECL_MACRO.match(line) or _CLASS_DECL.match(line):
            out.add(re.split(r"[{;]", line, 1)[0].strip())
        elif "(" in line and not _STMT_KW.match(line) and _FUNC_SIG.match(line):
            # [중요] `;`(선언)와 `{`(정의)가 같은 키가 된다 — 본문을 채워도 동결이 안 깨진다
            out.add(re.split(r"[{;]", line, 1)[0].strip())
    return out


def violation(original: str, new: str) -> str:
    """동결 위반 사유, 없으면 `""`. **추가는 허용** — `original ⊆ new` 만 본다 (소 2.1.1).

    [중요] 방향이 중요하다. 워커가 멤버를 *더하는* 것은 정상이고(구현하다 보면 헬퍼가 생긴다),
    **기존 선언을 바꾸거나 지우는 것**만 병렬을 깨뜨린다.
    """
    missing = frozen_decls(original) - frozen_decls(new)
    if not missing:
        return ""
    shown = sorted(missing)[:3]
    more = f" (외 {len(missing) - 3}개)" if len(missing) > 3 else ""
    return "동결 인터페이스 변경/삭제: " + " | ".join(shown) + more


def depths(text: str) -> list:
    """`[PSEUDO:N]` 의 N 들. 뎁스 없는 `[PSEUDO]` 만 있으면 빈 리스트(단일 태스크)."""
    return sorted({int(m.group(1)) for m in _PSEUDO.finditer(text or "") if m.group(1)})


def pseudo_count(text: str) -> int:
    return len(_PSEUDO.findall(text or ""))


def is_header(path: str) -> bool:
    return str(path or "").lower().endswith(HEADER_SUFFIXES)


def relations(paths: ProjectPaths, classes: list, *, max_each: int = 8) -> str:
    """대상 클래스의 **관계**를 프롬프트 블록으로. [중요] LLM 0 — 그래프에서 읽는다.

    사용자가 원전 흐름을 이렇게 기억했다(2026-08-11): *"각 클래스별 관계(부모/자식, 포함관계
    등)와 호출하는 인터페이스등 기본 골조를 만들고"*. 관계가 **골조의 재료**라는 뜻이다 —
    부모가 무엇인지 모르면 `: public X` 를 지어내고, include 를 모르면 헤더를 잘못 문다.

    [중요] 우리는 이 그래프를 중 1.1 에서 이미 만들어 뒀는데(상속 + `#include`, LLM 0) **골조
    프롬프트가 그것을 안 쓰고 있었다.** 규범·선언부만 싣고 관계를 뺀 것이 실제 누락이었다.
    """
    from ..graph import class_graph as cg, dependency as dep

    names = [c for c in (classes or []) if c and c.strip()]
    if not names:
        return ""
    lines: list = []
    for cls in names:
        bits: list = []
        try:
            anc = cg.find_ancestors(paths, cls)
            if anc:
                # 가까운 조상이 먼저다 — `: public <직계부모>` 가 골조에 그대로 쓰인다
                bits.append(f"parents: {' <- '.join(anc[:max_each])}")
        except Exception:                                   # noqa: BLE001
            pass
        try:
            subs = cg.find_subclasses(paths, cls, max_depth=1)
            if subs:
                # [중요] 자식이 있으면 virtual 계약이 있다는 뜻이다 — 시그니처를 함부로 못 바꾼다
                bits.append(f"children ({len(subs)}): {', '.join(subs[:max_each])}")
        except Exception:                                   # noqa: BLE001
            pass
        if bits:
            lines.append(f"- {cls}: " + " · ".join(bits))
    inc: list = []
    for f in _class_files(paths, names):
        try:
            deps = dep.dependencies(paths, f, depth=1)
        except Exception:                                   # noqa: BLE001
            continue
        if deps:
            inc.append(f"- {f} includes: {', '.join(deps[:max_each])}")
    if not lines and not inc:
        return ""
    out = ["=== RELATIONS (measured from the source graph, not guessed) ==="]
    if lines:
        out += ["Inheritance:", *lines]
    if inc:
        out += ["Includes:", *inc]
    out += ["[중요] Derive the skeleton's base class, virtual overrides and #include list from "
            "these facts. Do not invent a parent that is not listed.",
            "=== END RELATIONS ==="]
    return "\n".join(out)


def include_decls(paths: ProjectPaths, classes: list, *, budget: int = 4000) -> str:
    """[중요] **관계가 이름만 댄 헤더의 내용을 싣는다** (실측 2026-08-11).

    골조 게이트 첫 실전에서 잡힌 것:

        error C2065: 'None': 선언되지 않은 식별자입니다
        EMissionType MissionType = EMissionType::None;

    `EMissionType` 은 실재하고(`Main`/`Sub`) `None` 은 **다른 열거형**(`EMissionExecutorState`)의
    멤버다 — 모델이 둘을 섞었다. `declarations.py` 가 고치려던 *"한 글자 차이"* 와 같은 부류다.

    [중요] **왜 안 잡혔나**: 선언부는 `spec.classes` 만 싣는데, 그 열거형은 **관계 블록이 include
    로 이름만 댄 헤더**(`Table/TableEnum.h`)에 있었다. *"이 헤더를 문다"* 고만 말하고 **내용은
    안 준** 것이다. 이름을 댔으면 내용도 줘야 한다 — 안 주면 모델은 기억에서 꺼낸다.
    """
    from ..ontology import contexts
    from ..graph import dependency as dep

    seen: set = set()
    blocks: list = []
    used = 0
    for f in _class_files(paths, [c for c in (classes or []) if c]):
        try:
            deps = dep.dependencies(paths, f, depth=1)
        except Exception:                                   # noqa: BLE001
            continue
        for d in deps:
            if d in seen or used >= budget:
                continue
            seen.add(d)
            text = contexts.excerpt_header(paths, d, limit=min(1200, budget - used))
            if not (text or "").strip():
                continue
            blocks.append(f"--- {d} ---\n{text.strip()}")
            used += len(text)
    if not blocks:
        return ""
    return ("=== TYPES FROM INCLUDED HEADERS — COPY ENUM/STRUCT MEMBERS EXACTLY ===\n"
            "[중요] The relations block above says these headers are included. Their real "
            "contents are below. Do NOT invent enum values or members that are not here.\n\n"
            + "\n\n".join(blocks)
            + "\n=== END TYPES ===")


def _class_files(paths: ProjectPaths, classes: list) -> list:
    from ..graph import db as gdb
    if not gdb.exists(paths):
        return []
    conn = gdb.connect(paths)
    try:
        want = set(classes)
        return sorted({r["file"] for r in conn.execute("SELECT name, file FROM classes")
                       if r["name"] in want and r["file"]})
    finally:
        conn.close()


@dataclass
class SkeletonSpec:
    """무엇의 골조를 만들 것인가. **이미 분해된 조각 하나**가 들어온다 (§4.5)."""

    stem: str
    files: list = field(default_factory=list)      # 이 조각이 맡는 경로 (`.h` 먼저)
    classes: list = field(default_factory=list)
    instruction: str = ""                          # 무엇을 만들라는 것인지 (사람의 말)
    source_files: list = field(default_factory=list)  # 포팅 원본 (소 1.3.5) — **읽기 전용**
    # [중요] 이번 작업에만 적용되는 사람의 답(`scope=once`). 적립되지 않고 이 골조에만 실린다 —
    #    재생성 때 앞 라운드의 질문에 답한 것을 넣는 자리다.
    answers: list = field(default_factory=list)

    def validate(self) -> None:
        if not (self.stem or "").strip():
            raise SkeletonError("stem 이 비었다 — 조각을 식별할 수 없다")
        if not self.files:
            raise SkeletonError(f"{self.stem}: 만들 파일 경로가 없다")
        if not (self.instruction or "").strip():
            raise SkeletonError(f"{self.stem}: 무엇을 만들지가 비었다")

    @property
    def headers(self) -> list:
        return [f for f in self.files if is_header(f)]


@dataclass
class Skeleton:
    """골조 한 벌. [중요] **텍스트다** — 파일로 쓰는 것은 작업장 몫이다."""

    stem: str
    files: dict = field(default_factory=dict)      # 경로 → 본문
    frozen: set = field(default_factory=set)       # 동결 선언 키 (헤더에서 뽑은 것)
    depth_set: list = field(default_factory=list)  # `[PSEUDO:N]` → 소 1.2.4 가 소비
    pseudo: int = 0
    model: str = ""
    grounding: list = field(default_factory=list)  # 무엇으로 grounding 했나 (근거 기록)
    # [중요] 모델이 "여기서 추측했다" 고 말한 것 (소 1.1.6). **이것 자체는 휴리스틱이 아니다** —
    #    사람이 답해야 적립된다. 자동 승급을 껐던 것과 같은 이유.
    questions: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    prompt_chars: int = 0

    @property
    def ok(self) -> bool:
        # [중요] fail-closed — 채울 자리가 없거나 동결할 것이 없으면 골조가 아니다
        return bool(self.files) and self.pseudo > 0 and bool(self.frozen)

    @property
    def header_text(self) -> str:
        return "\n".join(t for p, t in sorted(self.files.items()) if is_header(p))

    def contracts(self) -> str:
        """`TaskSpec.contracts` 로 실릴 계약 텍스트. 워커가 읽는 것은 이것이다."""
        if not self.frozen:
            return ""
        out = ["=== FROZEN INTERFACE — DO NOT CHANGE OR REMOVE ===",
               "These declarations were fixed once when the skeleton was made. Adding new "
               "members is allowed; changing or deleting any line below is not.",
               "[중요] A worker that alters these is rejected deterministically before review.",
               ""]
        out += sorted(self.frozen)
        out += ["", "Tags: [PSEUDO]/[PSEUDO:N]/[IMPL] — delete the marker line once "
                "implemented. [DOC]/[STATE]/[BIND]/[REPLICATED] and untagged comments — "
                "[중요] keep verbatim. The requirement lives in [DOC] and MUST survive; "
                "[PSEUDO] only marks where to write. [중요] Do NOT add a 'done' marker of "
                "your own — the absence of [PSEUDO] is the completion signal and it is "
                "checked deterministically.",
                "=== END FROZEN INTERFACE ==="]
        return "\n".join(out)

    @property
    def summary(self) -> str:
        bits = [f"파일 {len(self.files)}", f"[PSEUDO] {self.pseudo}",
                f"동결 {len(self.frozen)}"]
        if self.questions:
            bits.append(f"[중요] 물음 {len(self.questions)}")
        if self.depth_set:
            bits.append(f"뎁스 {self.depth_set}")
        if self.model:
            bits.append(self.model)
        s = f"{self.stem}: " + " · ".join(bits)
        if not self.ok:
            s = "[중요] " + s + " — 골조가 아니다"
        return s


# ── 프롬프트 (소 1.1.2 grounding) ────────────────────────────────────────────────

def build_prompt(spec: SkeletonSpec, *, declarations: str = "", norms: str = "",
                 relations_text: str = "", conventions: str = "",
                 heuristics_text: str = "", failures_text: str = "") -> str:
    """골조 생성 프롬프트.

    [중요] **grounding 은 이미 있는 것을 쓴다** — 헤더 선언(`declarations.py`, #26)과 도메인
    규범(`norms.py`, 소 2.3.1). 원전은 이 둘이 없어 골조가 **LLM 자유 생성**이었고, 그래서
    *동결의 원천이 LLM 출력*이었다. 우리는 실측된 이름과 규범 위에 세운다.

    [중요] **선언부를 지시 바로 앞에 둔다** — 베껴야 할 텍스트가 지시에서 멀수록 모델은 기억에서
    꺼낸다(#26 실측: `CurrentStep` vs 실제 `Step`).
    """
    spec.validate()
    parts = [
        "You are writing the SKELETON of Unreal Engine 5 C++ files for an existing project.",
        "A skeleton fixes the interface and leaves the bodies unwritten, so that several "
        "workers can fill different files in parallel without colliding.",
        "",
        "RULES — violating any of these makes the output unusable:",
        "1. Write COMPLETE, COMPILABLE declarations: includes, UCLASS/USTRUCT/UENUM macros, "
        "GENERATED_BODY(), member declarations, method signatures.",
        "2. Do NOT write real logic. Each function body carries TWO comment lines: "
        "`// [DOC] <what this must do and why>` which STAYS FOREVER, then "
        "`// [PSEUDO] <fill this in>` which the worker deletes once implemented. "
        "[중요] The requirement lives in [DOC]; [PSEUDO] only marks the spot. "
        "[중요] THE SKELETON MUST STILL COMPILE. A non-void function therefore ends "
        "with a minimal placeholder return on its own line (`return false;`, `return {};`, "
        "`return nullptr;`) directly after the [PSEUDO] comment. A void function has the "
        "comment alone.",
        "3. Use `// [PSEUDO:1]`, `// [PSEUDO:2]` … instead of `[PSEUDO]` ONLY when this file "
        "is large enough that one pass cannot implement it: depth 1 = foundational logic, "
        "depth 2 = builds on depth 1, depth 3+ = integration. Otherwise use plain [PSEUDO].",
        "4. Mark durable comments so they survive implementation: `[DOC]` the requirement "
        "itself (see 2 — that is where intent lives) and design notes, "
        "`[STATE]` what a member is for, `[BIND]` Blueprint/event wiring, `[REPLICATED]` "
        "network replication. [중요] Do NOT put any comment on getters/setters.",
        "5. Output the file contents, each preceded by a line `=== FILE: <path> ===`. "
        "No markdown fences.",
        "6. [중요] AFTER the files, output a `=== QUESTIONS ===` block: every place where you "
        "had to GUESS, and every structure you think would be better than what the task "
        "asked for. One per line, phrased as a question with the alternatives "
        "(`Should X be a component or a subsystem?`). Write `(none)` only if you truly had "
        "no choice to make. [중요] Do NOT change the files because of these — the owner decides, "
        "not you.",
        "7. Follow the conventions of the existing codebase shown below — this is not "
        "greenfield code.",
        "",
    ]
    # [중요] 휴리스틱이 맨 앞이다 — *이미 내려진 사람의 결정*이라 나머지 재료보다 위다
    if heuristics_text.strip():
        parts += [heuristics_text.strip(), ""]
    # [중요] 실패 카탈로그가 그 다음이다 (소 2.3.4) — **기계가 결정적 게이트에서 모은 것**이라
    #    사람의 결정 아래, 나머지 재료 위다. 이 고리가 없으면 같은 컴파일 오류를 매번 다시 낸다.
    if failures_text.strip():
        parts += [failures_text.strip(), ""]
    if norms.strip():
        parts += [norms.strip(), ""]
    # [중요] 관계는 규범 뒤·선언부 앞이다. 규범은 *무엇을 지킬지*, 관계는 *어디에 붙을지*,
    #    선언부는 *정확한 철자*다 — 뒤로 갈수록 베껴야 하는 것이라 지시에 가깝게 둔다.
    if relations_text.strip():
        parts += [relations_text.strip(), ""]
    if conventions.strip():
        parts += ["=== CONVENTIONS ===", conventions.strip(), "=== END CONVENTIONS ===", ""]
    if spec.source_files:
        # [중요] 포팅 참조의 원칙 — 원전이 못박은 그대로 (소 1.3.5)
        parts += [
            "=== PREVIOUS IMPLEMENTATION (reference only) ===",
            "[중요] This code is NOT the answer — it ran in a different engine version and "
            "project. Read it to understand INTENT only. Do not copy it, and never edit it.",
            *spec.source_files,
            "=== END PREVIOUS IMPLEMENTATION ===",
            "",
        ]
    if declarations.strip():
        parts += [declarations.strip(), ""]
    parts += [
        "FILES TO WRITE (exactly these, in this order):",
        *[f"  {f}" for f in spec.files],
        "",
        "TASK:",
        spec.instruction.strip(),
        "",
    ]
    return "\n".join(parts)


# ── 응답 읽기 ────────────────────────────────────────────────────────────────────

_FILE_MARK = re.compile(r"^===\s*FILE:\s*(.+?)\s*===\s*$", re.MULTILINE)


def parse_files(raw: str, *, want: list) -> tuple:
    """`=== FILE: path ===` 로 갈라 `{경로: 본문}`. `(파일들, 메모)`.

    [중요] **요청하지 않은 경로는 버린다.** 모델이 없던 파일을 끼워 넣으면 그것을 워커가 쓰게
    되는데, 분해 계획에 없던 파일은 **다른 조각과 충돌할 수 있다**(`check_disjoint` 의 전제가
    깨진다).
    """
    # [중요] `=== QUESTIONS ===` 블록은 파일이 아니다 — 파일 파싱 전에 떼어낸다(소 1.1.6).
    #    안 떼면 마지막 파일의 본문에 질문이 섞여 그대로 워커에게 배달된다.
    #    [주의] **마지막 것 기준으로 자른다** — 실측 2026-08-11: 첫 것 기준으로 잘랐더니 모델이
    #    본문 중간에 흘린 낱말에 걸려 **`.cpp` 를 통째로 잃었다**(파일 1개만 남았다).
    from .heuristics import _last_q_start
    _i = _last_q_start(raw or "")
    raw = (raw or "")[:_i] if _i >= 0 else (raw or "")
    text, _ = _strip_wrap(raw)
    notes: list = []
    marks = list(_FILE_MARK.finditer(text))
    files: dict = {}
    if not marks:
        # 파일이 하나뿐이면 마커 없이 본문만 줄 수 있다 — 그때만 관대하게 받는다
        if len(want) == 1 and text.strip():
            files[want[0]] = text.strip()
            notes.append("FILE 마커 없음 — 대상이 하나라 본문 전체로 받았다")
            return files, notes
        raise SkeletonError("응답에 `=== FILE: path ===` 마커가 없다 — 어느 파일인지 모른다")

    norm = {_norm(w): w for w in want}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        got = m.group(1).strip()
        body = text[m.end():end].strip()
        key = norm.get(_norm(got))
        if key is None:
            notes.append(f"[중요] 요청하지 않은 경로를 버렸다: {got}")
            continue
        if not body:
            notes.append(f"[중요] 본문이 비었다: {key}")
            continue
        if _FENCE_ANY.search(body):
            # [중요] 중간 펜스는 모델이 설명을 섞었다는 뜻이다 — 조용히 지우지 않는다
            notes.append(f"[중요] 본문에 마크다운 펜스가 남았다: {key}")
        files[key] = body
    for w in want:
        if w not in files:
            notes.append(f"[중요] 빠진 파일: {w}")
    return files, notes


def _norm(p: str) -> str:
    return str(p or "").replace("\\", "/").strip().lstrip("./").lower()


def _strip_wrap(text: str) -> tuple:
    m = _FENCE_WRAP.match(text or "")
    return (m.group(1), True) if m else ((text or "").strip(), False)


# ── 생성 (소 1.1.1) ──────────────────────────────────────────────────────────────

def build(paths: ProjectPaths, spec: SkeletonSpec, *, model: str = DEFAULT_MODEL,
          broker: str = "", num_ctx: int = 8192, timeout: int = 900,
          ground: bool = True) -> Skeleton:
    """골조를 **텍스트로** 만든다. [중요] 파일을 쓰지 않는다.

    레인은 `synth.generate` 와 같은 규약이다 — `claude[:모델]`/`agy` 는 마스터의 상용 CLI,
    그 밖은 브로커(8102)를 통해 모델을 상주한 노드로 간다. **기본값은 `claude:opus`** — 왜
    그런지는 `DEFAULT_MODEL` 주석에 있다.
    """
    # [중요] `from . import generate` 는 **함수가 서브모듈을 가린다** — `__init__` 이 같은 이름의
    #    함수를 내보내기 때문이다(master/README.md 에 적힌 함정, 여기서 실제로 밟았다).
    #    서브모듈을 **직접** 임포트한다.
    from .generate import DEFAULT_BROKER
    from ..ontology import synth

    spec.validate()
    model = model or DEFAULT_MODEL
    sk = Skeleton(stem=spec.stem, model=model)

    decl = norms_text = ""
    if ground:
        # [중요] 이미 있는 것을 쓴다 — 새로 만들지 않는다
        try:
            from . import declarations as dcl
            d = dcl.collect(paths, spec.classes)
            decl = d.render()
            if decl:
                sk.grounding.append(f"선언부 {d.summary}")
        except Exception as e:                              # noqa: BLE001
            sk.notes.append(f"[주의] 선언부 수집 실패 — 없이 진행한다: {e}")
        try:
            from . import norms as nm
            n = nm.attach(paths, classes=spec.classes, stem=spec.stem)
            # [중요] `render()` 는 매니페스트용 마크다운 **줄 목록**이다. 비어도 *왜 비었는지*를
            #    돌려주므로(`degraded`) 그대로 싣는다 — 규범이 없다는 사실도 grounding 이다.
            lines = n.render()
            norms_text = ("=== DOMAIN NORMS ===\n" + "\n".join(lines)
                          + "\n=== END DOMAIN NORMS ===") if lines else ""
            d, inv, act = n.counts
            sk.grounding.append(f"규범 도메인 {d} · invariant {inv} · action {act}"
                                + (" [중요] " + "; ".join(n.degraded) if n.degraded else ""))
        except Exception as e:                              # noqa: BLE001
            sk.notes.append(f"[주의] 규범 수집 실패 — 없이 진행한다: {e}")

    rel = inc = ""
    if ground:
        try:
            inc = include_decls(paths, spec.classes)
            if inc:
                sk.grounding.append("include 헤더 타입")
        except Exception as e:                              # noqa: BLE001
            sk.notes.append(f"[주의] include 타입 수집 실패 — 없이 진행한다: {e}")
        try:
            rel = relations(paths, spec.classes)
            if rel:
                sk.grounding.append("관계 그래프(상속·include)")
            else:
                sk.notes.append("[주의] 관계를 못 찾았다 — 신규 클래스이거나 그래프가 비었다")
        except Exception as e:                              # noqa: BLE001
            sk.notes.append(f"[주의] 관계 수집 실패 — 없이 진행한다: {e}")

    # [중요] include 타입은 **선언부와 한 덩어리**로 붙인다 — 둘 다 "정확한 철자" 채널이다
    heur = ""
    if ground:
        try:
            from . import heuristics as H
            # [중요] **이 작업의 도메인으로 거른다** — 안 거르면 남의 작업의 결정이 실린다
            #    (사용자 지적 2026-08-11). 도메인은 결정적 추론으로 뽑는다(소 2.2.2).
            doms: list = []
            try:
                from ..context_search import infer as _infer
                doms = list(_infer.infer_for(
                    paths, " ".join(spec.classes) + " " + spec.instruction).domains)
            except Exception:                               # noqa: BLE001
                pass
            items = H.load(paths)
            heur = H.render(items, domains=doms, extra=spec.answers)
            kept = [h for h in items if h.applies_to(doms)]
            if items or spec.answers:
                sk.grounding.append(
                    f"휴리스틱 {len(kept)}/{len(items)}건"
                    + (f" (도메인 {', '.join(doms)})" if doms else " (도메인 미상 — project 만)")
                    + (f" + 이번만 {len(spec.answers)}" if spec.answers else ""))
        except Exception as e:                              # noqa: BLE001
            sk.notes.append(f"[주의] 휴리스틱 로드 실패 — 없이 진행한다: {e}")

    fails = ""
    if ground:
        try:
            from . import failures as F
            fails = F.attach(paths)
            n = len(F.load(paths))
            if n:
                sk.grounding.append(f"실패 카탈로그 {n}건")
        except Exception as e:                              # noqa: BLE001
            sk.notes.append(f"[주의] 실패 카탈로그 로드 실패 — 없이 진행한다: {e}")

    prompt = build_prompt(spec, declarations="\n\n".join(x for x in (inc, decl) if x),
                          norms=norms_text, relations_text=rel, heuristics_text=heur,
                          failures_text=fails)
    sk.prompt_chars = len(prompt)

    raw = synth.generate(prompt, model, broker=broker or DEFAULT_BROKER,
                         num_ctx=num_ctx, timeout=timeout)
    sk.files, notes = parse_files(raw, want=spec.files)
    sk.notes += notes
    try:
        from . import heuristics as H
        sk.questions = H.parse_questions(raw)
        if not sk.questions:
            # [주의] 물음이 0개인 것은 *애매함이 없었다* 는 뜻일 수도, 모델이 규칙을 어긴 것일
            #    수도 있다. 구분이 안 되므로 **말은 해 둔다.**
            sk.notes.append("[주의] 골조가 물음을 하나도 내지 않았다 — 애매함이 없었거나 "
                            "지시를 어겼거나다. 큰 작업이면 의심할 것")
    except Exception as e:                                  # noqa: BLE001
        sk.notes.append(f"[주의] 물음 파싱 실패: {e}")

    body = "\n".join(sk.files.values())
    sk.pseudo = pseudo_count(body)
    sk.depth_set = depths(body)
    # [중요] 동결의 원천은 **헤더**다. `.cpp` 의 인라인 정의는 계약이 아니다.
    head = sk.header_text or body
    sk.frozen = frozen_decls(head)
    if not sk.header_text and spec.headers:
        sk.notes.append("[중요] 헤더가 안 나왔다 — 동결을 `.cpp` 에서 뽑았다(약한 계약)")
    if sk.pseudo == 0:
        sk.notes.append("[중요] `[PSEUDO]` 가 0개 — 골조가 아니라 완성 파일이다. 태스크로 "
                        "등재하면 워커가 할 일이 없다(원전은 이 경우 등재를 skip 한다)")
    if not sk.frozen:
        sk.notes.append("[중요] 동결할 선언이 0개 — 계약을 만들 수 없어 병렬로 나눌 수 없다")
    return sk
