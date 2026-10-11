"""층1 — **결정적 자기검증** (중 2.1 · §4.3). 무료 · 즉시 · LLM 0.

## [중요] 어디에 박히나 — 실제 호출자 (실측 2026-10-11, grep)

    ① 커밋 직전    `wcommit` ④ 층1   워커 체크아웃을 **되읽은 디스크 내용**으로    ← 실전 경로
                   (`baseline` = 기준 커밋의 골조 — 동결·스텁·pyflakes 기존분 대조)
    ② 응답 수락    `infer.judge`      `ax-infer` 응답을 받는 자리 (`baseline` 없음 — 잔재·구문·pyflakes 만)
    ③ 측정         `bench_lane_codex` 레인 비교 판정 (`baseline` = 골조)

①이 verify-then-commit 이다 — 위반이면 커밋하지 않고 그 조각은 재시도로 간다. ②는 `infer_task`
경로가 응답을 「통과」로 돌려주기 전에 본다. 검사가 무료라서 여러 자리에서 돌려도 잃는 것이 없다.
[주의] 종전 서술의 「적용 직전 `integrate.apply_one`」은 통합자와 함께 지워졌다
(`master/test_no_integrator.py` 가 부활을 막는다).

[주의] 옛 구조에서 이 칸은 *"워커가 제출 전에 자기검증한다"* 였다(원전 `worker/validator.py`).
쓰는 주체가 하나가 된 뒤로는 **마스터가 받는 자리**가 곧 제출 경로다 — 워커의 선의에 의존하지
않는 편이 낫고, 실측에서 워커는 실제로 계약을 어겼다(마커를 응답 파일에 써 넣었다).

## 무엇을 보나

    동결 인터페이스 위반   추가는 허용, **변경·삭제는 위반**            (소 2.1.1)
    휘발 태그 잔재         `[PSEUDO]`·`[PSEUDO:N]`·`[IMPL]`            (소 2.1.2)
    `[FEEDBACK]` 잔재      [중요] 아래 § 참조                              (소 2.1.2)
    재시도 피드백 블록     `AUTO-VERIFY FEEDBACK` 여는 줄(C·`#` 둘 다)        (`#806`)
    마크다운 펜스 잔재     14b 의 알려진 유일 결함                      (소 2.1.2)
                           기준 원본에 이미 있던 개수만큼은 기존이다 — 프롬프트 문자열 속
                           정상 펜스를 워커가 지워 통과하던 결함        (`#819`)
    `.py` 정의 안 된 이름  pyflakes `undefined name`(`__all__` 포함) — ⑦ 과 같은 차단 집합,
                           기준 원본에 이미 있던 개수만큼은 기존이다      (`#815`)

[중요] **보존 태그는 건드리지 않는다** — `[DOC]`·`[STATE]`·`[BIND]`·`[REPLICATED]` 와 무태그 주석은
남아 있어야 정상이다. 태그가 두 종류라는 것이 소 1.1.1 의 실제 계약이다.

## [중요] `[FEEDBACK]` 이 소스에 남아 있으면 위반이다 — 값을 치른 교훈

원전에 *"모든 주석을 보존하라"* 는 지시가 있었고, 그것이 `[FEEDBACK]` 블록 **삭제를 막아
검증이 무한 실패**했다(리포트 11 §30). 우리는 두 방향으로 막는다 — 통합자는 `[FEEDBACK]` 을
**소스에 넣지 않고** 큐로만 나르고(소 1.4.4), 층1 은 소스에 남은 `[FEEDBACK]` 을 **위반으로
잡는다.** 한쪽만 하면 사람이 손으로 붙인 경우가 새어 나간다.

## [중요] fail-closed 의 방향

- 검사를 **안 돌린 것**은 통과가 아니다 (`checked=False`)
- 기준 원본이 없으면 동결은 **미검사**다 — 통과라고 적지 않는다
- [주의] 다만 **없는 위반을 만들지는 않는다.** 인코딩이 유실된 사본으로 대조하면 치환된 글자가
  선언 키를 바꿔 정상 작업이 막힌다. *정상 작업을 막는 게이트가 통과시키는 게이트보다 나쁘다*
  — 그런 파일은 미검사로 넘긴다(판정은 층2·층3 이 이어받는다).
- [주의] pyflakes 를 돌리지 못하면(미설치·예외) **막지 않고 `unchecked` 에 미검사로 적는다**
  (사용자 결정, `#815`). 같은 결함은 ⑦ 의 `pystatic` 이 fail-closed 로 다시 본다 — 구멍이 아니다.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from . import pyskel, skeleton
from .pystatic import BLOCKING_FLAKES
from .revise import FEEDBACK_OPEN, PY_FEEDBACK_OPEN


def _is_py(path: str) -> bool:
    return str(path or "").lower().endswith(".py")

# [중요] 소스에 남아 있으면 안 되는 것들. 보존 태그(`skeleton.PERMANENT_TAGS`)는 여기 없다.
FEEDBACK_TAG = "[FEEDBACK]"
# 🔴 [중요] **마커와 「인용」을 가른다** (실측 2026-09-05 — 오탐으로 조각 하나가 죽었다).
#    골조의 `[DOC]` 문장이 태그를 **언급**한 것뿐인데 위반으로 잡혔다:
#
#        * EvaluateInteractor 의 후보 판정에 이 가드가 추가된다(아래 [PSEUDO] 참고).
#
#    워커는 본문을 다 쓰고 실제 마커도 전부 지웠는데(`.cpp` 0개 · `.h` 는 이 문장 하나),
#    문자열 포함 판정이라 커밋이 막혔다. 추론값을 통째로 버렸다.
#
# 마커의 실제 모양은 **주석의 시작**이다 — `// [PSEUDO]` · `/* [PSEUDO]` · `* [PSEUDO]`
# (블록 주석 이어지는 줄) · `# [PSEUDO]`. 문장 **중간**에 나오는 것은 인용이다.
# [주의] 느슨하게 푸는 것이 아니다 — 채워야 할 자리는 언제나 「주석 한 줄이 통째로 지시」이고,
#    그 형태만 본다. 실제 마커를 놓치면 미완성이 `main` 으로 가므로 형태를 좁게 잡는다.
_VOLATILE = re.compile(
    r"(?m)^[ \t]*(?://+|/\*+|\*|#)[ \t]*(?:"
    + "|".join(re.escape(t.rstrip("]")) + r"(?::\d+)?\]" for t in skeleton.VOLATILE_TAGS)
    + ")")
# 🔴 `#806` — 재시도 피드백 블록(`revise.build_block`)이 남으면 위반이다. 원전도 *"블록이
#    남아 있으면 검증 실패"* 다(`worker/validator.py`). 종전에는 `.py` 에서 C 주석이 구문을
#    깨뜨려 **우연히** 잡혔다 — `#` 모양으로 바뀌면 그 우연이 사라진다.
# [주의] 인용과 가른다 — **줄 머리**(공백 허용)의 여는 줄만 본다. 문자열 안 언급은 아니다.
_FEEDBACK_BLOCK = re.compile(
    r"(?m)^[ \t]*(?:" + re.escape(FEEDBACK_OPEN) + "|" + re.escape(PY_FEEDBACK_OPEN) + ")")
# 위반 문구에 태그 이름을 싣기 위한 보조 — 어떤 태그였나만 뽑는다
_VOLATILE_NAME = re.compile(
    "|".join(re.escape(t.rstrip("]")) + r"(?::\d+)?\]" for t in skeleton.VOLATILE_TAGS))


@dataclass
class Layer1:
    """적용/수락 직전 자기검증. [중요] `ok` 가 아니면 **넘기지 않는다.**"""

    checked: bool = False
    problems: list = field(default_factory=list)
    skipped: list = field(default_factory=list)     # 기준 원본이 없어 동결을 못 본 파일
    unchecked: list = field(default_factory=list)   # pyflakes 를 돌리지 못한 사유 (`#815`)

    @property
    def ok(self) -> bool:
        # [중요] fail-closed — 검사를 못 돌렸으면 통과가 아니다
        return bool(self.checked and not self.problems)

    @property
    def summary(self) -> str:
        if not self.checked:
            return "[주의] 층1 미확인"
        un = (" · pyflakes 미검사 — " + "; ".join(self.unchecked[:2])) if self.unchecked else ""
        if self.problems:
            return f"[중요] 층1 위반 {len(self.problems)}: " + "; ".join(self.problems[:3]) + un
        s = "[완료] 층1 통과"
        if self.skipped:
            s += f" (기준 원본 없어 동결 미검사 {len(self.skipped)})"
        return s + un


class _FlakesUnavailable(Exception):
    """pyflakes 를 돌리지 못했다 — 「결함 0」도 「위반」도 아니다(미검사)."""


def _flakes(path: str, text: str) -> list:
    """pyflakes 의 **차단** 발견 `[(종류, 줄, 문구)]` — 분류는 ⑦(`pystatic`)과 같은 `BLOCKING_FLAKES`.

    프로세스 안에서 부른다(파견 프로세스는 오래 살고, 조각마다 해석기를 띄울 이유가 없다).
    구문 오류는 여기서 세지 않는다 — 호출자가 `pyskel.parse` 로 이미 본다(중복 문구 방지).
    돌지 못하면 `_FlakesUnavailable`.
    """
    try:
        from pyflakes import api as _api, reporter as _rep
    except Exception as e:                                   # noqa: BLE001
        raise _FlakesUnavailable(f"{type(e).__name__}: {e}") from None
    found, broken = [], []

    class _R(_rep.Reporter):
        def __init__(self):                                  # noqa: D401 — 출력 스트림 없음
            pass

        def unexpectedError(self, filename, msg):
            broken.append(str(msg))

        def syntaxError(self, filename, msg, lineno, offset, text):
            pass

        def flake(self, m):
            if type(m).__name__ in BLOCKING_FLAKES:
                found.append((type(m).__name__, m.lineno, m.message % m.message_args))

    try:
        _api.check(text, path, _R())
    except Exception as e:                                   # noqa: BLE001
        raise _FlakesUnavailable(f"{path}: {type(e).__name__}: {e}") from None
    if broken:
        raise _FlakesUnavailable(f"{path}: {broken[0]}")
    return found


def _fence_problem(path: str, text: str, baseline) -> str:
    """마크다운 펜스 잔재 문구 — 없으면 `""`.

    🔴 `#819` (실측 2026-10-11, work `#817`) — 원본 문자열(`DRAFT_PROMPT` 의 ```` ```diff ````)에
    정상으로 든 펜스를 잔재로 잡아, 재시도 워커가 **프롬프트의 펜스를 지워** 통과했다(범위 밖 변경).
    [중요] 기준 원본에 이미 있던 펜스는 그 **개수만큼** 기존이다 — pyflakes(`#815`)와 같은 개수 규칙.
    기준이 없거나(`baseline` 미지정) 신규 파일(`None`)이면 종전대로 펜스 하나도 위반이다.
    [주의] 셈은 `_FENCE_ANY`(MULTILINE `^\\s*```) 의 일치 수 = 펜스로 **시작하는 줄** 수다.
    """
    new = len(skeleton._FENCE_ANY.findall(text))
    if not new:
        return ""
    old_text = baseline(path) if baseline is not None else None
    if old_text is None:
        return f"{path}: 마크다운 펜스가 남아 있다"
    old = len(skeleton._FENCE_ANY.findall(old_text))
    if new <= old:
        return ""                            # 원본의 펜스를 지키거나 줄였다 — 잔재가 아니다
    return f"{path}: 마크다운 펜스가 남아 있다 (새로 생김 {new - old} · 원본 {old})"


def check(files: dict, *, baseline=None) -> Layer1:
    """동결 위반 · 휘발 태그 · `[FEEDBACK]` · 펜스 잔재 · `.py` 의 정의 안 된 이름을 본다. **무료 · LLM 0.**

    `baseline(path) -> str|None` — 그 파일의 **변경 전** 내용. `None` 이면 신규 파일이라
    동결 대조 대상이 없다(정상). [중요] 함수 자체를 주지 않으면 **동결을 검사하지 않은 것**이다.
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
            # [중요] 휘발 태그는 *"여기를 채워라"* 는 표시다 — 남아 있으면 본문이 안 채워졌다
            _n = _VOLATILE_NAME.search(m.group(0))
            L.problems.append(f"{path}: 휘발 태그 `{_n.group(0) if _n else m.group(0)}` 가 "
                              f"남아 있다")
        if FEEDBACK_TAG in text:
            # [중요] 소스에 남으면 다음 라운드가 그것을 또 읽는다 (리포트 11 §30 의 무한 실패)
            L.problems.append(f"{path}: `{FEEDBACK_TAG}` 가 소스에 남아 있다")
        if _FEEDBACK_BLOCK.search(text):
            L.problems.append(f"{path}: 재시도 피드백 블록(AUTO-VERIFY FEEDBACK)이 남아 있다")
        _fence = _fence_problem(path, text, baseline)
        if _fence:
            L.problems.append(_fence)

        # 🔴 `#695` P3 — `.py` 는 선언과 정의가 한 몸이다. 구문은 **원본 없이도** 본다.
        if _is_py(path):
            _tree, _why = pyskel.parse(text)
            if _tree is None:
                L.problems.append(f"{path}: 구문 오류 — {_why}")
                continue
            # 🔴 `#815` — ⑦ 에서야 보이던 `undefined name` 을 조각 단위로 당긴다(즉시 재시도).
            #    [중요] 기준 원본(골조)에 이미 있던 (종류, 문구)는 그 **개수만큼** 기존이다 — ⑦ 과 같은 규칙
            try:
                head = _flakes(path, text)
                if head and baseline is not None:
                    old = baseline(path)
                    if old is not None:
                        base_cnt = Counter((k, m) for k, _ln, m in _flakes(path, old))
                        new = []
                        for k, ln, m in head:
                            if base_cnt[(k, m)] > 0:
                                base_cnt[(k, m)] -= 1
                            else:
                                new.append((k, ln, m))
                        head = new
                for _k, ln, m in head:
                    L.problems.append(f"{path}:{ln}: 정의되지 않은 이름 — {m}")
            except _FlakesUnavailable as e:
                if str(e) not in L.unchecked:
                    L.unchecked.append(str(e))
        if baseline is None:
            continue
        if not (skeleton.is_header(path) or _is_py(path)):
            continue                        # 동결은 **선언**의 문제다 — `.cpp` 는 대상 아님
        old = baseline(path)
        if old is None:
            continue                        # 신규 파일 — 동결할 원본이 없다
        if _is_py(path):
            why = pyskel.violation(old, text)
            if why:
                L.problems.append(f"{path}: 동결 위반 — {why}")
            # [중요] 마커 주석만 지우고 스텁을 남긴 경우 — 마커 검사는 주석만 본다
            left = pyskel.unfilled(old, text)
            if left:
                L.problems.append(f"{path}: 본문이 안 채워졌다 (스텁 그대로) — "
                                  + ", ".join(left[:5]))
            continue
        why = skeleton.violation(old, text)
        if why:
            L.problems.append(f"{path}: 동결 위반 — {why}")

    # 🔴 [중요] **동결을 못 본 파일은 `.py` 도 여기 든다** (`#695` P3 — 종전에는 헤더만 들어서
    #    `.py` 는 동결을 안 보고도 요약이 「통과」라고만 말했다. 조용한 통과였다).
    if baseline is None:
        L.skipped = sorted(files)
    else:
        L.skipped = sorted(p for p in files
                           if (skeleton.is_header(p) or _is_py(p)) and baseline(p) is None)
    return L
