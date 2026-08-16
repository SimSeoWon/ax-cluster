"""σ 감사 — **조용히 틀리는 자리**를 찾는다 (소 4.2.1).

원전 `.claude/reviews/_silent_failure/audit_matrix.md` **99줄** 이식. 그 문서는 우리 저장소에서
**인용 0회**였고, 그 안에 이 저장소가 반복해 물린 실패의 **체계적 탐지법**이 있었다.

## [중요] 원전이 그 문서를 만든 계기가 이 방법론의 요점이다

> *"본 산출물은 plan v4.5.1 에 σ.1·σ.2 모두 `[x] 2026-05-21 완료` 로 마킹되어 있었으나,
> **2026-05-22 세션의 검증에서 디렉토리 자체 부재 + 산출물 미생성 확인**. plan 의 `[x]` 가
> 실 작업 완료를 의미하지 않은 한 가지 사례. 본 파일은 그 백필."*

즉 **「완료」 표시와 실물이 어긋나는 것**이 1차 표적이고, 그 대조로 silent failure **4건**을 찾았다.

## 두 축

    σ.1  발동 매트릭스   「완료」 주장 ↔ ① 실 코드 ② 실 산출물 ③ 카나리 로그  — **셋을 독립으로** 본다
    σ.2  정적 검사       전 함수/큰 블록을 감싼 `try` + `except` + **silent return/pass** + **로그 부재**

[중요] **σ.2 의 위험도는 「주기 호출인가」가 정한다** (원전 표기 /). 매 폴링에서 조용히 실패하는
것은 영구 유실로 누적되고, 이벤트 트리거는 사람이 다시 부른다.

## [중요] 모든 silent fallback 이 결함은 아니다 — 그게 이 감사의 핵심 절제다

원전이 6건 중 **4건을 「유지」로 판정**했다: `parse_file → return []`(tree-sitter 미설치 대응) ·
`get_commit_diff → return ""` · `is_trivial_diff → return False`(*"over-review > under-review"*) ·
`_read_source_snippet → return ""`. 조치는 *"docstring 으로 의도 명시"* 였다.

→ 그래서 이 스캐너는 **판정을 내리지 않는다.** *"silent fallback 인데 **의도가 적혀 있지 않다**"* 를
찾아 줄 뿐이다. 의도가 적혀 있으면 그것은 **설계**다. [주의] 자동으로 «결함» 딱지를 붙이면
[[feedback_analytics_restraint]] 를 어기고 노이즈가 된다 — 원전이 except ~33개 중 **딱 2개만**
카나리로 승격한 것과 같은 절제다.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

# 핸들러 안에서 이것이 보이면 «조용하지 않다» 로 본다.
_LOUD = re.compile(r"\b(log|logf|print|warn|error|canary|append|chk|raise|degraded|note)\b")

# 함수 독스트링/주석에 이런 말이 있으면 «의도가 적혀 있다» 로 본다.
_INTENT = re.compile(
    r"(폴백|fallback|기본값|삼키지 않|조용|정상 동작|의도|없으면|실패도|베스트에포트|"
    r"best.?effort|막지 않는다|죽지 않)", re.IGNORECASE)


@dataclass
class Finding:
    file: str
    line: int
    func: str
    swallow: str            # 핸들러가 하는 것 (`pass` · `return ""` …)
    exc: str                # 잡는 예외
    intent_documented: bool
    periodic: bool          #  주기 호출 경로인가 (모듈로 추정)
    broad: bool = True      # [중요] `except Exception`/bare 인가 (좁은 것은 의도적)
    covers_most: bool = False  # `try` 가 함수 큰 블록을 감싸나

    def line_str(self) -> str:
        star = "" if self.periodic else ""
        doc = "의도 적힘" if self.intent_documented else "[중요] 의도 없음"
        big = " · 함수 대부분을 감쌈" if self.covers_most else ""
        return (f"{star} {self.file}:{self.line} {self.func}() "
                f"— except {self.exc} → {self.swallow} · {doc}{big}")


@dataclass
class Report:
    scanned: int = 0
    findings: list = field(default_factory=list)
    parse_failed: list = field(default_factory=list)

    @property
    def undocumented(self) -> list:
        """[중요] **이것만 사람이 봐야 한다** — silent 인데 의도가 안 적힌 자리."""
        return [f for f in self.findings if not f.intent_documented]

    def summary(self) -> str:
        u = self.undocumented
        star = sum(1 for f in u if f.periodic)
        s = (f"σ.2 정적 검사 — 파일 {self.scanned}개 · silent fallback {len(self.findings)}건 "
             f"· [중요] 의도 없음 {len(u)}건 (그중 주기 {star}건)")
        if self.parse_failed:
            s += f" · [주의] 파싱 실패 {len(self.parse_failed)}건"
        return s


# 주기 호출 경로 — 색인기·타이머·큐가 반복해서 부르는 모듈.
# [주의] **정적으로는 알 수 없다.** 원전도 사람이 / 를 달았다. 여기서는 모듈로 **추정**하고,
#    추정이라는 사실을 이름(`periodic`)과 이 주석에 남긴다.
_PERIODIC_HINTS = ("events/", "context_search/", "graph/", "task_queue/", "status.py",
                   "ontology/", "context_synth/")


def _is_periodic(rel: str) -> bool:
    return any(h in rel for h in _PERIODIC_HINTS)


def _swallow_kind(handler: ast.ExceptHandler) -> str:
    """핸들러가 «조용히» 무엇을 하는가. 조용하지 않으면 빈 문자열.

    [중요] **조용함의 정의는 「호출자가 실패를 알 수 없다」다.** 그래서 둘은 조용하지 않다:

        ① 핸들러가 로그·카나리·raise 를 한다                    → `_LOUD`
        ② [중요] **바인딩한 예외를 값으로 돌려준다** (`except E as e: return _fail(e)`)
           → 실패가 **데이터로 전파**된다. 우리 MCP 도구 24개가 전부 이 형태다.

    [주의] ②를 안 넣었을 때 54건이 나왔고 그중 상당수가 `mcp_server.py` 의 `_fail(e)` 래퍼였다 —
    **원전 패턴을 글자로만 옮기면 우리 관례를 결함으로 센다.** 원전의 사람 검토자가 암묵적으로
    하던 판단이 이것이다.
    """
    src = ast.dump(handler)
    if _LOUD.search(src):
        return ""
    # ② 예외를 값으로 돌려주면 조용하지 않다.
    if handler.name:
        for n in ast.walk(handler):
            if isinstance(n, ast.Name) and n.id == handler.name:
                return ""
    body = handler.body
    if len(body) == 1 and isinstance(body[0], ast.Pass):
        return "pass"
    if len(body) == 1 and isinstance(body[0], ast.Return):
        v = body[0].value
        if v is None:
            return "return None"
        if isinstance(v, ast.Constant):
            return f"return {v.value!r}"
        if isinstance(v, (ast.List, ast.Dict, ast.Tuple, ast.Set)) and not getattr(v, "elts", getattr(v, "keys", [1])):
            return f"return {type(v).__name__.lower()}()"
        return "return <값>"
    if len(body) == 1 and isinstance(body[0], ast.Continue):
        return "continue"
    return ""


# [중요] **넓은 핸들러만 본다.** 원전 패턴 원문: *"전 함수 또는 큰 블록을 감싸는 `try` +
# **`except Exception` (또는 bare except)** + silent return / pass + 로그 부재"*.
#
# [주의] 첫 이식에서 이 조건을 빠뜨려 **114건**이 나왔다(원전은 6건). `sqlite3.OperationalError` ·
# `TypeError, ValueError` · `KeyError` 처럼 **좁게 잡은 것은 의도적**이다 — 무엇이 날아오는지
# 알고 그것만 받는다. 조용히 틀리는 것이 숨는 자리는 **아무거나 받는** 핸들러다.
_BROAD = {"Exception", "BaseException", "(bare)"}


BARE = "(bare)"


def _is_broad(name: str) -> bool:
    """[중요] `except Exception` · `except BaseException` · **bare `except:`**.

    [주의] 첫 판은 `strip("()")` 로 `"(bare)"` 를 벗겨 놓고 원래 문자열과 비교해서 **bare 를 못
    잡았다** — 가장 위험한 형태를 놓치는 버그였고 `test_sigma_audit` 가 잡았다(2026-08-14).
    """
    n = (name or "").strip()
    if n == BARE:
        return True
    return n.split(".")[-1] in {"Exception", "BaseException"}


def _covers_most(fn, node: ast.Try) -> bool:
    """`try` 가 함수 «큰 블록» 을 감싸나 — 원전 패턴의 첫 조건.

    함수 최상위 문장이 그 `try` 하나뿐이거나, `try` 본문이 함수 문장의 절반 이상이면 그렇다.
    [주의] 근사다 — 원전도 사람이 봤다. 좁히는 신호로만 쓰고 단독 판정에 쓰지 않는다.
    """
    top = [x for x in fn.body if not isinstance(x, ast.Expr)]      # 독스트링 제외
    if len(top) == 1 and top[0] is node:
        return True
    return len(node.body) * 2 >= max(1, len(top))


def _exc_name(handler: ast.ExceptHandler) -> str:
    t = handler.type
    if t is None:
        return "(bare)"
    try:
        return ast.unparse(t)
    except Exception:                                   # noqa: BLE001
        return "?"


def _handler_intent(lines: list, h: ast.ExceptHandler) -> bool:
    """[중요] **핸들러 블록의 원문 줄**에서 의도를 찾는다 (주석 포함).

    [주의] 첫 판은 `ast.unparse` + 독스트링만 봤는데 **주석이 소실**된다. 그래서 의도를 주석에
    적어 둔 자리(`ontology/stale.py:104`)를 *"의도 없음"* 으로 계속 잡았다 — 내가 그 한계를
    모듈 주석에 적어 놓고 **해결하지 않은** 것이다(σ.2 를 자기 자신에게 돌려 발견, 2026-08-14).

    [중요] 핸들러별 의도는 **주석이 자연스러운 자리**다 — 함수에 핸들러가 셋이면 독스트링 하나로는
    어느 것을 말하는지 알 수 없다. 그래서 독스트링이 아니라 **그 블록**을 본다.
    """
    a = max(0, h.lineno - 1)
    b = getattr(h, "end_lineno", h.lineno) or h.lineno
    return bool(_INTENT.search("\n".join(lines[a:b])))


def scan_file(path: Path, *, rel: str = "") -> tuple:
    """한 파일. `(findings, parse_error)`."""
    rel = rel or path.name
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(raw)
    except SyntaxError as e:
        return [], f"{rel}: {e}"
    lines = raw.splitlines()

    out = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        doc = ast.get_docstring(fn) or ""
        try:
            body_src = ast.unparse(fn)
        except Exception:                               # noqa: BLE001
            body_src = ""
        # 주석은 unparse 에 안 남으므로 독스트링 + 원문 라인 범위를 함께 본다.
        doc_intent = bool(_INTENT.search(doc)) or bool(_INTENT.search(body_src))
        for node in ast.walk(fn):
            if not isinstance(node, ast.Try):
                continue
            for h in node.handlers:
                kind = _swallow_kind(h)
                if not kind:
                    continue
                exc = _exc_name(h)
                if not _is_broad(exc):
                    continue          # [중요] 좁은 예외는 의도적이다 (위 _BROAD 주석)
                out.append(Finding(file=rel, line=h.lineno, func=fn.name,
                                   swallow=kind, exc=exc,
                                   intent_documented=(doc_intent
                                                      or _handler_intent(lines, h)),
                                   periodic=_is_periodic(rel),
                                   broad=True, covers_most=_covers_most(fn, node)))
    return out, ""


def scan(root: Path, *, skip_tests: bool = True) -> Report:
    """저장소를 훑는다. [중요] 테스트는 뺀다 — 테스트의 `except` 는 검사 대상이 아니다."""
    r = Report()
    for p in sorted(root.rglob("*.py")):
        rel = str(p.relative_to(root))
        if "__pycache__" in rel or ".venv" in rel:
            continue
        if skip_tests and Path(rel).name.startswith("test_"):
            continue
        r.scanned += 1
        found, err = scan_file(p, rel=rel)
        if err:
            r.parse_failed.append(err)
        r.findings.extend(found)
    return r


# ─────────────────────────────────────────────────────────────
# σ.1 — 발동 매트릭스
#
# [중요] **이쪽은 자동화하지 않는다.** 원전도 사람이 표를 만들었고, 그 값은 **세 축을 독립으로
# 확인하는 절차** 자체에 있다. 코드로 만들면 «주장된 산출물 경로를 파싱» 하는 취약한 것이 되고,
# 그건 감사가 아니라 또 하나의 조용히 틀리는 자리가 된다.
#
#     ① 실 코드      그 기능의 코드가 실제로 있나          (grep/import)
#     ② 실 산출물    그것이 만든다는 파일·행·표가 있나     (ls/SELECT COUNT)
#     ③ 카나리 로그  돌았다는 것을 로그가 말하나           (journalctl)
#
# [중요] 셋이 **서로를 대신하지 못한다** — 원전 실측: 코드는  인데 산출물이 [실패] 였던 것이
# *"도메인 자동 승급"*(회사 환경 수개월), 산출물이 [실패] 인 것을 아무도 몰랐던 이유가 카나리 부재다.
#
# 절차는 `docs/` 가 아니라 이 주석에 둔다 — **감사를 돌리는 사람이 코드 옆에서 읽어야** 한다.
# ─────────────────────────────────────────────────────────────

SIGMA1_AXES = ("실 코드", "실 산출물", "카나리 로그")


def main(argv=None) -> int:
    import sys
    root = Path(__file__).resolve().parent
    r = scan(root)
    print(r.summary())
    u = r.undocumented
    if u:
        print("\n[중요] 의도가 적혀 있지 않은 silent fallback (=주기 호출 추정):")
        for f in sorted(u, key=lambda x: (not x.periodic, x.file, x.line)):
            print("  " + f.line_str())
    for e in r.parse_failed:
        print(f"  [주의] {e}")
    print("\n[주의] 이 목록은 «결함» 이 아니다 — *의도가 안 적힌 자리*다. 원전은 6건 중 4건을 "
          "「정상 fallback 이라 유지」로 판정하고 docstring 으로 의도를 적었다.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
