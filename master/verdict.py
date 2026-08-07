"""층2 검증의 판정 계약 — fail-closed.

gajae-code 의 `extragoal` 리뷰어 계약(`docs/extragoal-skill-template.md`)을 가져왔다.
런타임(gjc)은 도입하지 않고 **계약의 형태만** 쓴다 — PLAN.md §9.4.3.

계약:
  · 응답의 **마지막 비어 있지 않은 줄**이 정확히 `VERDICT: APPROVE` 또는 `VERDICT: REQUEST_CHANGES`
  · 누락·형식오류·타임아웃·백엔드 부재는 **절대 APPROVE 로 매핑하지 않는다**

왜 바꾸나 — 기존 `syntax_check`(AgentTest `worker/claude_spawn.py:739`)는 **fail-open** 이었다:
docstring 이 "checked=False = 양쪽 다 불가 → 호출자는 통과로 간주" 라 명시하고,
`_parse_syntax_verdict` 도 파싱 실패 시 `None` 을 돌려 호출자가 통과로 처리했다.
검증기가 죽거나 헛소리를 하면 **조용히 통과**한다는 뜻이고, 이는 PLAN.md §8.3
("완료 신호를 믿지 말 것")과 정면으로 어긋난다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

APPROVE = "VERDICT: APPROVE"
REQUEST_CHANGES = "VERDICT: REQUEST_CHANGES"

# 판정 줄에 모델이 흔히 덧붙이는 장식. 벗겨내고 비교하되 벗겨냈다는 사실은 기록한다.
_DECORATION = re.compile(r"^[\s>*_`#-]+|[\s*_`.]+$")


@dataclass
class Verdict:
    """층2 판정 결과. `approved` 만 보고 분기하면 된다 — fail-closed 가 이미 반영돼 있다."""

    approved: bool
    failure: str | None          # None = 모델이 실제로 판정을 냈다. 그 외 = 계약 위반 사유
    findings: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_tail: str = ""           # 진단용 — 마지막 비어 있지 않은 줄 원문

    @property
    def blocked(self) -> bool:
        """승인되지 않음. 지적 때문인지 계약 위반 때문인지는 `failure` 로 구분한다."""
        return not self.approved

    def summary(self) -> str:
        if self.approved:
            return "APPROVE"
        if self.failure:
            return f"BLOCKED(계약 위반: {self.failure})"
        return f"REQUEST_CHANGES({len(self.findings)}건)"


def contract_text() -> str:
    """리뷰어 프롬프트 끝에 붙일 계약 지시문. 프롬프트 본문(무엇을 볼지)과 분리해 재사용한다."""
    return (
        "OUTPUT CONTRACT — obey exactly:\n"
        "First list your findings, one per line, each starting with '- '.\n"
        "If there are no findings, write nothing there.\n"
        f"Then the LAST non-empty line of your response must be exactly one of:\n"
        f"{APPROVE}\n"
        f"{REQUEST_CHANGES}\n"
        "Nothing may follow that line. Do not wrap it in quotes, code fences, or markdown emphasis.\n"
        "Emit REQUEST_CHANGES if you found anything that would break compilation or violate the spec."
    )


def parse_verdict(raw: str | None, *, backend: str = "") -> Verdict:
    """모델 응답 → `Verdict`. **모든 실패 경로는 승인되지 않음으로 떨어진다.**

    `raw=None` 은 백엔드 부재·타임아웃·예외를 뜻한다(호출자가 그렇게 넘겨줄 것).
    """
    if raw is None:
        return Verdict(approved=False, failure="no_output",
                       warnings=[f"백엔드 응답 없음{f' ({backend})' if backend else ''}"])

    lines = [ln for ln in raw.splitlines() if ln.strip()]
    if not lines:
        return Verdict(approved=False, failure="empty", raw_tail="")

    last = lines[-1].strip()
    normalized = _DECORATION.sub("", last)
    warnings: list[str] = []
    if normalized != last:
        warnings.append(f"판정 줄에 장식이 붙어 있었다: {last!r}")

    if normalized == APPROVE:
        approved, failure = True, None
    elif normalized == REQUEST_CHANGES:
        approved, failure = False, None
    else:
        # 계약 위반 — 판정을 못 읽었으므로 통과시키지 않는다.
        return Verdict(approved=False, failure="malformed", raw_tail=last,
                       findings=_extract_findings(lines[:-1]), warnings=warnings)

    # 판정 토큰이 앞쪽에도 나오면 기록만 한다. 권위는 마지막 줄에 있다(계약 원문: "the LAST
    # non-empty line"). 모델이 지시문을 되읊는 것은 흔한 행동이라 그걸로 막으면 헛차단이 는다.
    body = lines[:-1]
    if any(_DECORATION.sub("", ln.strip()) in (APPROVE, REQUEST_CHANGES) for ln in body):
        warnings.append("판정 토큰이 본문에도 나타났다 — 마지막 줄을 권위로 삼았다")

    findings = _extract_findings(body)
    if not approved and not findings:
        warnings.append("REQUEST_CHANGES 인데 지적 항목이 없다")

    return Verdict(approved=approved, failure=failure, findings=findings,
                   warnings=warnings, raw_tail=last)


def _extract_findings(body: list[str]) -> list[str]:
    """본문에서 '- ' 로 시작하는 지적 항목만 뽑는다. 없으면 빈 목록."""
    out = []
    for ln in body:
        s = ln.strip()
        if s.startswith(("- ", "* ")):
            item = s[2:].strip()
            if item:
                out.append(item)
    return out[:20]
