"""생성 프롬프트에 **선언부를 싣는다** (레드마인 #26).

## 왜 — 규범으로는 안 잡히는 실패가 실측됐다

같은 지시·같은 모델로 매니페스트만 바꿔 재봤을 때(리포트 11 §14):

    규범 없음  →  **없는 멤버**를 지어냈다
    규범 있음  →  실재 멤버 4/4 + invariant 준수 … **그런데 철자가 한 글자 틀렸다**
                  `CurrentStep`(실제 `Step`) · `EMissionTaskExecutorState`(실제 `EMissionExecutorState`)

규범은 *무엇을 지킬지*를 준다. **정확한 철자는 헤더에만 있다.** 그래서 헤더 선언을 프롬프트에
직접 싣는다 — 모델이 기억에서 꺼내지 않고 **눈앞의 텍스트를 베끼게** 한다.

🔴 **워커의 Claude 에게는 이 문제가 없다** — 소스를 직접 읽기 때문이다(실측: 첫 파견에서
실재 멤버만 썼다). 이 모듈이 필요한 자리는 **로컬 LLM 에 본문 생성을 위임할 때**다.

## 🔴 못 찾은 것을 조용히 빼지 않는다

헤더를 못 찾은 클래스를 말없이 생략하면 모델은 *"선언부에 없으니 내가 지어내도 되겠다"* 로
읽는다 — 고치려던 실패가 그대로 돌아온다. 그래서 **없으면 없다고 프롬프트에 쓴다.**

## 예산

실측(리포트 11 §14): 규범까지 실은 프롬프트가 **2,824 tok**, `num_ctx` 8192 에서 출력 여유가
**5,368 tok** 남았다. 그 여유 안에서 쓴다 — 2.79~2.85자/tok 이므로 6,000자면 ~2,100 tok 이다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..context_search.paths import ProjectPaths

PER_CLASS = 1500        # 클래스당 헤더 발췌
TOTAL = 6000            # 전체 상한 (≈2,100 tok — 실측 여유 5,368 안)


@dataclass
class Declarations:
    blocks: list = field(default_factory=list)      # [(클래스, 파일, 발췌)]
    missing: list = field(default_factory=list)     # 헤더를 못 찾은 클래스
    truncated: list = field(default_factory=list)   # 예산에 잘린 클래스
    dropped: list = field(default_factory=list)     # 예산이 다 차 아예 못 실은 클래스

    @property
    def ok(self) -> bool:
        return bool(self.blocks)

    @property
    def summary(self) -> str:
        s = f"선언부 {len(self.blocks)}개"
        for label, xs in (("헤더 없음", self.missing), ("잘림", self.truncated),
                          ("예산 초과", self.dropped)):
            if xs:
                s += f" · 🔴 {label} {len(xs)}"
        return s

    def render(self) -> str:
        """프롬프트에 넣을 블록. 🔴 **결손을 본문에 적는다.**"""
        if not self.blocks and not (self.missing or self.dropped):
            return ""
        out = ["=== DECLARATIONS — COPY THESE NAMES EXACTLY ===",
               "These are the real headers from this codebase. Member, method and enum "
               "names below are the ONLY spellings that compile.",
               "🔴 If a name you need is not here, do NOT invent it — say so in a comment "
               "instead of guessing.", ""]
        for cls, file, text in self.blocks:
            out += [f"--- {cls}  ({file}) ---", text.strip(), ""]
        # 🔴 빠진 것을 숨기지 않는다 — 숨기면 모델이 "없으니 지어내도 된다" 로 읽는다
        for label, xs in (("NOT AVAILABLE (header not found)", self.missing),
                          ("TRUNCATED (excerpt cut by budget)", self.truncated),
                          ("OMITTED (budget exhausted)", self.dropped)):
            if xs:
                out.append(f"🔴 {label}: {', '.join(xs)}")
        out.append("=== END DECLARATIONS ===")
        return "\n".join(out)


def _files_for(paths: ProjectPaths, classes: list) -> dict:
    """`{클래스: 헤더 경로}`. 클래스 그래프가 근거다 — **소스 실측**이라 가장 신선하다."""
    from ..graph import db as gdb
    if not gdb.exists(paths):
        return {}
    conn = gdb.connect(paths)
    try:
        want = {c for c in classes if c}
        return {r["name"]: (r["file"] or "") for r in conn.execute("SELECT name, file FROM classes")
                if r["name"] in want}
    finally:
        conn.close()


def collect(paths: ProjectPaths, classes: list, *, per_class: int = PER_CLASS,
            total: int = TOTAL) -> Declarations:
    """대상 클래스들의 헤더 선언을 모은다. **읽기 전용.**"""
    from ..ontology import contexts

    d = Declarations()
    names = [c for c in (classes or []) if c and c.strip()]
    if not names:
        return d
    files = _files_for(paths, names)
    used = 0
    for cls in names:
        f = files.get(cls, "")
        if not f:
            d.missing.append(cls)
            continue
        if used >= total:
            d.dropped.append(cls)                   # 🔴 조용히 빼지 않는다
            continue
        room = min(per_class, total - used)
        text = contexts.excerpt_header(paths, f, limit=room)
        if not (text or "").strip():
            d.missing.append(cls)
            continue
        if len(text) >= room:
            d.truncated.append(cls)
        d.blocks.append((cls, f, text))
        used += len(text)
    return d
