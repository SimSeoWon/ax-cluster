"""층1 — **결정적 자기검증** (중 2.1 · §4.3). 무료 · 즉시 · LLM 0.

## 🔴 어디에 박히나 — **두 곳이고, 둘 다 fail-closed 다**

    ① 응답 수락    `infer.judge`      워커 응답이 스풀에 **들어오기 전**    ← 가장 이른 자리
    ② 적용 직전    `integrate.apply_one`  파일을 쓰기 **전**                ← 마지막 방어선

①이 없으면 잔재가 있는 응답이 *"통과"* 로 스풀에 쌓이고, 통합자가 적용 단계에서야 막는다 —
같은 결론에 왕복이 하나 더 든다. ②가 없으면 스풀을 손으로 만지거나 재사용하는 경로에서 검사가
빠진다. **둘 다 둔다.** 검사가 무료라서 두 번 돌려도 잃는 것이 없다.

⚠️ 옛 구조에서 이 칸은 *"워커가 제출 전에 자기검증한다"* 였다(원전 `worker/validator.py`).
쓰는 주체가 하나가 된 뒤로는 **마스터가 받는 자리**가 곧 제출 경로다 — 워커의 선의에 의존하지
않는 편이 낫고, 실측에서 워커는 실제로 계약을 어겼다(마커를 응답 파일에 써 넣었다).

## 무엇을 보나

    동결 인터페이스 위반   추가는 허용, **변경·삭제는 위반**            (소 2.1.1)
    휘발 태그 잔재         `[PSEUDO]`·`[PSEUDO:N]`·`[IMPL]`            (소 2.1.2)
    `[FEEDBACK]` 잔재      🔴 아래 § 참조                              (소 2.1.2)
    마크다운 펜스 잔재     14b 의 알려진 유일 결함                      (소 2.1.2)

🔴 **보존 태그는 건드리지 않는다** — `[DOC]`·`[STATE]`·`[BIND]`·`[REPLICATED]` 와 무태그 주석은
남아 있어야 정상이다. 태그가 두 종류라는 것이 소 1.1.1 의 실제 계약이다.

## 🔴 `[FEEDBACK]` 이 소스에 남아 있으면 위반이다 — 값을 치른 교훈

원전에 *"모든 주석을 보존하라"* 는 지시가 있었고, 그것이 `[FEEDBACK]` 블록 **삭제를 막아
검증이 무한 실패**했다(리포트 11 §30). 우리는 두 방향으로 막는다 — 통합자는 `[FEEDBACK]` 을
**소스에 넣지 않고** 큐로만 나르고(소 1.4.4), 층1 은 소스에 남은 `[FEEDBACK]` 을 **위반으로
잡는다.** 한쪽만 하면 사람이 손으로 붙인 경우가 새어 나간다.

## 🔴 fail-closed 의 방향

- 검사를 **안 돌린 것**은 통과가 아니다 (`checked=False`)
- 기준 원본이 없으면 동결은 **미검사**다 — 통과라고 적지 않는다
- ⚠️ 다만 **없는 위반을 만들지는 않는다.** 인코딩이 유실된 사본으로 대조하면 치환된 글자가
  선언 키를 바꿔 정상 작업이 막힌다. *정상 작업을 막는 게이트가 통과시키는 게이트보다 나쁘다*
  — 그런 파일은 미검사로 넘긴다(판정은 층2·층3 이 이어받는다).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import skeleton

# 🔴 소스에 남아 있으면 안 되는 것들. 보존 태그(`skeleton.PERMANENT_TAGS`)는 여기 없다.
FEEDBACK_TAG = "[FEEDBACK]"
_VOLATILE = re.compile(
    "|".join(re.escape(t.rstrip("]")) + r"(?::\d+)?\]" for t in skeleton.VOLATILE_TAGS))


@dataclass
class Layer1:
    """적용/수락 직전 자기검증. 🔴 `ok` 가 아니면 **넘기지 않는다.**"""

    checked: bool = False
    problems: list = field(default_factory=list)
    skipped: list = field(default_factory=list)     # 기준 원본이 없어 동결을 못 본 파일

    @property
    def ok(self) -> bool:
        # 🔴 fail-closed — 검사를 못 돌렸으면 통과가 아니다
        return bool(self.checked and not self.problems)

    @property
    def summary(self) -> str:
        if not self.checked:
            return "⚠️ 층1 미확인"
        if self.problems:
            return f"🔴 층1 위반 {len(self.problems)}: " + "; ".join(self.problems[:3])
        s = "✅ 층1 통과"
        if self.skipped:
            s += f" (기준 원본 없어 동결 미검사 {len(self.skipped)})"
        return s


def check(files: dict, *, baseline=None) -> Layer1:
    """동결 위반 · 휘발 태그 · `[FEEDBACK]` · 펜스 잔재를 본다. **무료 · LLM 0.**

    `baseline(path) -> str|None` — 그 파일의 **변경 전** 내용. `None` 이면 신규 파일이라
    동결 대조 대상이 없다(정상). 🔴 함수 자체를 주지 않으면 **동결을 검사하지 않은 것**이다.
    """
    L = Layer1()
    if not files:
        L.problems.append("검사할 파일이 없다")
        return L
    L.checked = True
    for path in sorted(files):
        text = files[path] or ""
        m = _VOLATILE.search(text)
        if m:
            # 🔴 휘발 태그는 *"여기를 채워라"* 는 표시다 — 남아 있으면 본문이 안 채워졌다
            L.problems.append(f"{path}: 휘발 태그 `{m.group(0)}` 가 남아 있다")
        if FEEDBACK_TAG in text:
            # 🔴 소스에 남으면 다음 라운드가 그것을 또 읽는다 (리포트 11 §30 의 무한 실패)
            L.problems.append(f"{path}: `{FEEDBACK_TAG}` 가 소스에 남아 있다")
        if skeleton._FENCE_ANY.search(text):
            L.problems.append(f"{path}: 마크다운 펜스가 남아 있다")

        if baseline is None:
            continue
        if not skeleton.is_header(path):
            continue                        # 동결은 **선언**의 문제다 — `.cpp` 는 대상 아님
        old = baseline(path)
        if old is None:
            continue                        # 신규 파일 — 동결할 원본이 없다
        why = skeleton.violation(old, text)
        if why:
            L.problems.append(f"{path}: 동결 위반 — {why}")

    if baseline is None:
        L.skipped = sorted(files)
    else:
        L.skipped = sorted(p for p in files
                           if skeleton.is_header(p) and baseline(p) is None)
    return L
