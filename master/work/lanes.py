"""본문 작성 **레인** — 🔴 정본 ⑸ *"제미나이·로컬 LLM 까지 써서"* (사용자 확정 2026-09-02).

## [중요] 왜 필요했나 — 한도 하나로 라운드가 죽었다

`infer_command` 가 `claude -p` **하드코딩**이었다(`#346`). 실측 2026-09-04 00:16: 워커 계정이
`429 You've hit your session limit` 을 맞자 **4조각 중 3이 동시에 죽고** 라운드가 02:30 까지
보류됐다. 배달되는 작업장 문서는 *"대량 생성은 로컬 LLM/`agy` 에 위임하고 너는 검증한다"*
(`client/bundle.py:721`)고 지시하는데 **코드는 그 위임을 못 했다** — `#297` 부류다.

## [중요] 레인 규약은 새로 만들지 않았다 — `ontology/synth.generate` 가 이미 그것이다

    `claude[:모델]` · `agy`  →  마스터의 상용 CLI (`layer2_verify.call_*`)
    그 밖(모델 이름)          →  브로커(8102) → 그 모델을 상주한 노드

## 순서 (사용자 지시 2026-09-04 · codex 추가 2026-09-05): **agy → codex → 로컬**
   `claude` 는 여전히 체인 밖이다 — 한도가 이 세션과 **공용 자원**이라 429 하나로
   조각 여럿이 함께 죽는다(2026-09-04 실측: 4조각 중 3).

실측(같은 골조 · 같은 프롬프트 · 같은 판정 = 층1):

    agy (제미나이)            58.5초   파일 2/2   `[PSEUDO]` 0   층1 통과
    로컬 qwen2.5-coder:14b   117.6초   파일 2/2   `[PSEUDO]` 0   층1 통과  (`.43`)
    claude (워커)          90~154초   파일 2/2        —          오늘 429 로 3조각 사망

[중요] **`claude` 를 체인 끝으로 미룬 것은 사용자 결정이다** — 품질 판정이 아니다.
한도가 공용 자원이라 먼저 쓰면 라운드 전체가 그 한도에 묶인다.

## [중요] 구조가 하나 바뀐다 — 마스터가 쓰고, 워커로 써 넣는다

    종전   워커의 `claude -p` 가 **자기 체크아웃 파일을 직접 읽고 고친다**
    레인   `agy`·브로커는 **마스터에서** 돌고 텍스트를 돌려준다
           → 결과를 워커 파일로 **써 넣는 단계**가 필요하다 (`bundle._remote_write`,
             scp + sha256 대조 — 조용한 배달 사고를 두 번 잡은 그 함수)

그 뒤는 `wcommit` 의 기존 경로가 그대로 돈다: **되읽기 → 층1 → 커밋 → 조각 종결.**
[중요] 즉 게이트는 하나도 안 줄었다 — 되읽기가 디스크 상태로 판정하므로, 누가 썼든 같은
검사를 받는다.

## [주의] 실측으로 드러난 프롬프트 함정

로컬 모델은 지시에 *"Output BOTH files"* 가 **없으면 `.h` 를 빼먹는다**(`.2` 실측: 파일 1/2).
그 줄이 있는 판(`.43`)은 2/2 였다. 그래서 지시문에 고정한다. 마크다운 펜스도 로컬 14b 의
알려진 결함이라(`skeleton.py` 머리말) `strip_fence` 로 걷는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..client import bundle

# 🔴 사용자 지시 2026-09-04 — **agy 먼저, 그다음 로컬. `claude` 는 나중에.**
#    [주의] `.43` 에는 `agy` 가 없다(실측: `command -v agy` → NO). 그 대는 로컬부터 걸린다 —
#    체인이 레인 실패를 다음으로 넘기므로 배선을 나눌 필요가 없다.
# 🔴 **codex 가 2순위다** (사용자 결정 2026-09-05, 실측 근거 아래).
#    A/B 실측 2026-09-05 — 같은 골조(동결 20 · `[PSEUDO]` 6)로 본문 작성:
#
#        agy     32.9초   층1 통과   `[PSEUDO]` 잔재 0   `.h` 4,501자 · `.cpp` 3,303자
#        codex   98.6초   층1 통과   `[PSEUDO]` 잔재 0   `.h` 4,501자 · `.cpp` 3,397자
#        로컬     117.6초  층1 통과  (2026-09-04 측정)
#
#    [중요] **두 레인의 헤더가 바이트 단위로 동일했다** — 동결이 실제로 지켜진다는 뜻이다.
#    품질이 같고 로컬보다 빠르므로 **폴백 자리를 로컬에서 codex 로 올린다**. 로컬은 그 뒤다
#    (codex 도 구독이라 한도가 있고, 그때 마지막으로 남는 것이 로컬이다).
#    [주의] codex 는 **`.33` 원격 CLI** 다 — `.33` 이 꺼져 있으면 이 레인이 죽고 로컬로 넘어간다.
DEFAULT_LANES = ("agy", "codex", "qwen2.5-coder:14b")

# `claude` 를 쓰려면 **명시**해야 한다 (`AX_LANES=claude:opus` 또는 인자)
LANE_CLAUDE = "claude"

INSTRUCTION = (
    "You are implementing UE5 C++ from a skeleton. The skeleton comments are your spec.\n"
    "\n"
    "RULES:\n"
    "- Fill in every [PSEUDO] marker and DELETE that marker line.\n"
    "- Keep [DOC]/[STATE]/[BIND]/[REPLICATED] comments verbatim.\n"
    "- Do NOT change any declaration in the header - it is a frozen contract.\n"
    "- Do NOT leave empty function bodies. Non-void functions must return something.\n"
    "- Output EVERY file listed below, each block starting with a line: === FILE: <path> ===\n"
    "- Output nothing else. No prose, no markdown fences.\n"
)


class LaneError(RuntimeError):
    """레인 자체가 불가능하다 — 다음 레인으로 넘긴다."""


@dataclass
class LaneRun:
    """한 레인 시도의 결과. [중요] **모르는 것을 성공으로 접지 않는다.**"""
    lane: str = ""
    ok: bool = False
    seconds: float = 0.0
    chars: int = 0
    files: dict = field(default_factory=dict)     # {경로: 본문}
    missing: list = field(default_factory=list)
    reason: str = ""
    # 🔴 **토큰 계측** (사용자 결정 2026-09-05) — 「위임하면 클로드 토큰이 주는가」는
    #    추정으로 답할 수 없다. 레인마다 실제로 쓴 것을 남긴다.
    #    [중요] 못 읽으면 **None** 이다 — 0 으로 적으면 「안 썼다」로 읽힌다.
    usage: object = None

    @property
    def summary(self) -> str:
        if self.ok:
            base = (f"[완료] {self.lane} · {self.seconds:.0f}초 · 파일 {len(self.files)}"
                    f" · {self.chars:,}자")
        else:
            base = f"[중요] {self.lane}"
            if self.reason:
                base += f" — {self.reason}"
            if self.missing:
                base += f" · 빠진 파일 {len(self.missing)}: {', '.join(self.missing[:3])}"
        # 🔴 **토큰을 요약에 싣는다** — 이 줄이 곧 계측 기록이다(파견 로그가 정본).
        #    [중요] 미상은 **미상이라고 적는다** — 안 적으면 0 처럼 읽힌다.
        if self.usage is not None:
            if getattr(self.usage, "known", False):
                base += " · " + self.usage.summary()
            elif getattr(self.usage, "note", ""):
                base += f" · [주의] 토큰 미상({self.usage.note})"
        return base


def build_prompt(skeleton: dict) -> str:
    """`{경로: 골조 본문}` → 프롬프트. [중요] 골조 주석이 지시서다(매니페스트 없음)."""
    if not skeleton:
        raise LaneError("골조가 비었다 — 무엇을 채울지 모른다")
    parts = [INSTRUCTION, "Files to implement: " + ", ".join(sorted(skeleton)), ""]
    for rel in sorted(skeleton):
        parts += [f"=== FILE: {rel} ===", skeleton[rel], ""]
    return "\n".join(parts)


def parse_blocks(out: str, want) -> tuple:
    """`=== FILE: … ===` 블록을 가른다. `(파일, 빠진 것)`. **펜스는 걷는다.**"""
    from .generate import strip_fence

    want = list(want or [])
    files, cur, buf = {}, None, []
    for ln in (out or "").splitlines():
        s = ln.strip()
        if s.startswith("=== FILE:") and s.endswith("==="):
            if cur:
                files[cur] = "\n".join(buf)
            cur, buf = s[len("=== FILE:"):-3].strip(), []
        elif cur is not None:
            buf.append(ln)
    if cur:
        files[cur] = "\n".join(buf)
    got = {}
    for k, v in files.items():
        if k in want:
            code, _ = strip_fence(v.strip())
            code = code.strip()
            if code:
                got[k] = code + "\n"
    return got, [w for w in want if w not in got]


def run_one(skeleton: dict, lane: str, *, broker: str = "", num_ctx: int = 16384,
            timeout: int = 900, generator=None) -> LaneRun:
    """레인 하나로 본문을 받는다. **파일을 쓰지 않는다** — 텍스트만 돌려준다.

    `generator` 는 테스트 주입 자리다(`(prompt, lane) -> str`). 기본은 `synth.generate` —
    **레인 규약을 두 벌 두지 않는다**(그렇게 갈린 자리가 이 저장소에 이미 있었다).
    """
    import time

    r = LaneRun(lane=lane)
    try:
        prompt = build_prompt(skeleton)
    except LaneError as e:
        r.reason = str(e)
        return r
    t0 = time.time()
    try:
        if generator is not None:
            out = generator(prompt, lane)
        else:
            # 🔴 **CLI 레인은 계측 경로로 부른다** — 같은 호출에서 본문과 토큰이 함께 온다
            #    (`claude`/`agy` 는 `--output-format json`, `codex` 는 출력의 `tokens used`).
            #    [주의] 로컬 모델은 브로커가 답하므로 종전 경로 그대로다 — 그쪽 토큰은 미상이다.
            from . import usage as U
            if U.is_cli_lane(lane):
                call = U.call(lane, prompt, timeout=timeout)
                if call.error:
                    raise LaneError(call.error)
                out, r.usage = call.text, call.usage
            else:
                from ..ontology import synth
                from .generate import DEFAULT_BROKER
                out = synth.generate(prompt, lane, broker=broker or DEFAULT_BROKER,
                                     num_ctx=num_ctx, timeout=timeout)
    except Exception as e:                                   # noqa: BLE001
        r.seconds = time.time() - t0
        r.reason = f"{type(e).__name__}: {e}"
        return r
    r.seconds = time.time() - t0
    r.chars = len(out or "")
    r.files, r.missing = parse_blocks(out, skeleton.keys())
    if not r.files:
        r.reason = "`=== FILE:` 블록을 못 읽었다 (형식 미준수)"
        return r
    if r.missing:
        r.reason = "일부 파일이 안 왔다"
        return r
    r.ok = True
    return r


def write_back(facts, files: dict, *, writer=None) -> list:
    """받은 본문을 **워커 체크아웃에** 쓴다. `[사유]` — 비면 전부 성공.

    [중요] `bundle._remote_write` 를 쓴다 — **되읽어 sha256 대조**한다. 그 검증이 조용한
    배달 사고를 두 번 잡았다(BOM/CRLF · stdin 미종료).
    [주의] 여기서 쓴 뒤 `wcommit` 이 **다시 되읽어** 층1 을 돌린다 — 우리가 쓴 것을 그대로
    믿지 않는다. 게이트는 하나도 줄지 않는다.
    """
    w = writer or bundle._remote_write
    bad: list = []
    for rel, body in files.items():
        try:
            w(facts, rel, body, base="checkout")
        except Exception as e:                               # noqa: BLE001
            bad.append(f"{rel}: {type(e).__name__}: {e}")
    return bad


def run_chain(facts, skeleton: dict, *, lanes=DEFAULT_LANES, broker: str = "",
              num_ctx: int = 16384, timeout: int = 900, generator=None, writer=None,
              logf=None) -> tuple:
    """레인을 **순서대로** 시도해 첫 성공분을 워커에 써 넣는다. `(성공한 LaneRun|None, 시도들)`.

    [중요] **fail-forward 다** — 한 레인이 죽으면 다음으로 넘어간다. 그것이 이 배선의 목적이고,
    오늘 429 하나로 3조각이 함께 죽은 것을 막는다.
    [주의] **써 넣기가 실패하면 그 레인은 성공이 아니다** — 텍스트를 받은 것과 워커 디스크에
    올라간 것은 다르다. 조용히 넘기지 않는다.
    """
    log = logf or (lambda m: None)
    tried: list = []
    for lane in lanes:
        r = run_one(skeleton, lane, broker=broker, num_ctx=num_ctx, timeout=timeout,
                    generator=generator)
        tried.append(r)
        if not r.ok:
            log(f"[lane] {r.summary} → 다음 레인")
            continue
        bad = write_back(facts, r.files, writer=writer)
        if bad:
            r.ok = False
            r.reason = "워커에 써 넣지 못했다 — " + "; ".join(bad[:2])
            log(f"[lane] {r.summary} → 다음 레인")
            continue
        log(f"[lane] {r.summary} · 워커에 기록")
        return r, tried
    return None, tried
