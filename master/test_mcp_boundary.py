"""MCP stdio 경계의 인코딩 규약 (소 3.5.4 재범위) — [중요] **우연을 규약으로 못박는다.**

## 왜 이 테스트가 있나

원전은 lone UTF-16 surrogate 가 MCP 결과에 섞이면 `json.dumps(**ensure_ascii=True**)` 가
**에러 없이** `\\udXXX` 를 내보내고 → Claude Code(Node)가 파싱 → Anthropic 요청 직렬화에서
**400 으로 요청 전체 거부 = 세션 사망**하는 것을 겪었다(2026-06-06). 그래서 `server.py` 의
`json.dumps` 64곳을 `safe_dumps`(surrogate → U+FFFD)로 일괄 교체했다.

[중요] **우리에게는 그 실패 모드가 없다** — 실측 2026-08-14:

    원전 방식 ensure_ascii=True   dumps OK · encode OK  → **조용히 나간다** (세션 사망 경로)
    우리 방식 ensure_ascii=False  dumps OK · encode **실패(loud)** → 그 호출만 실패

[주의] **그래서 치환(`safe_dumps`)을 이식하지 않았다.** 치환은 loud 실패를 조용한 U+FFFD 로 바꾸는데,
우리에게 그것은 **퇴행**이다 — 원전이 치환을 택한 이유는 대안이 세션 사망이었기 때문이고 우리는
이미 loud 하다. 이 저장소는 *"조용히 틀리는 것"* 을 가장 경계한다.

[중요] **그러나 그 보호는 우연이다.** 누가 원전 코드를 베끼거나 "ASCII 가 안전하다" 고 생각해
`ensure_ascii=True` 로 바꾸면 **보호가 조용히 사라진다.** 이 테스트가 그 자리를 지킨다.

`.venv/bin/python master/test_mcp_boundary.py`
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PASS = FAIL = 0
BOUNDARY = ("projects/mcp_server.py", "task_queue/mcp_server.py")
LONE = "\ud800"          # lone high surrogate


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def test_failure_mode_is_loud():
    """[중요] 우리 방식은 **loud** 하고 원전 방식은 **조용하다** — 이 차이가 이식을 안 한 근거다."""
    ours = json.dumps({"a": LONE}, ensure_ascii=False)
    try:
        ours.encode("utf-8")
        check("우리 방식은 encode 에서 실패한다(loud)", False, "조용히 나갔다 — 보호가 사라졌다")
    except UnicodeEncodeError:
        check("우리 방식은 encode 에서 실패한다(loud)", True)

    theirs = json.dumps({"a": LONE}, ensure_ascii=True)
    try:
        theirs.encode("utf-8")
        check("원전 방식은 조용히 나간다 (그래서 위험했다)", True)
    except UnicodeEncodeError:
        check("원전 방식은 조용히 나간다 (그래서 위험했다)", False, "여기서 막힌다면 전제가 바뀐 것")
    check("원전 방식은 \\udXXX 이스케이프를 만든다", "\\ud800" in theirs, theirs)


def test_boundary_never_uses_ensure_ascii_true():
    """[중요] MCP 경계에서 `ensure_ascii=True`(또는 생략=기본 True)를 쓰지 않는다."""
    root = Path(__file__).resolve().parent
    bad = []
    for rel in BOUNDARY:
        p = root / rel
        if not p.exists():
            check(f"{rel} 존재", False, "경계 파일이 사라졌다 — 이 테스트를 갱신할 것")
            continue
        for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            st = ln.strip()
            if st.startswith("#") or "json.dumps" not in st:
                continue
            if "ensure_ascii=True" in st:
                bad.append(f"{rel}:{i} ensure_ascii=True")
    check("경계에 ensure_ascii=True 가 없다", not bad, "; ".join(bad))


def test_boundary_dumps_are_explicit():
    """[주의] `json.dumps` 를 부르면서 `ensure_ascii` 를 **생략하면 기본이 True** 라 보호가 사라진다.

    여러 줄에 걸친 호출도 있으므로 파일 전체에서 `json.dumps(` 개수와
    `ensure_ascii=False` 개수를 비교한다 — 같아야 한다.
    """
    root = Path(__file__).resolve().parent
    for rel in BOUNDARY:
        p = root / rel
        if not p.exists():
            continue
        t = p.read_text(encoding="utf-8")
        # 주석 줄은 뺀다
        body = "\n".join(l for l in t.splitlines() if not l.strip().startswith("#"))
        n_dumps = len(re.findall(r"json\.dumps\(", body))
        n_safe = body.count("ensure_ascii=False")
        check(f"{rel}: dumps {n_dumps}건 전부 ensure_ascii=False ({n_safe}건)",
              n_dumps > 0 and n_safe >= n_dumps, f"dumps={n_dumps} safe={n_safe}")


def test_no_silent_replacement_crept_in():
    """[주의] 나중에 누가 `errors='replace'` 로 경계를 조용하게 만들지 않았는지."""
    root = Path(__file__).resolve().parent
    bad = []
    for rel in BOUNDARY:
        p = root / rel
        if not p.exists():
            continue
        for i, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            st = ln.strip()
            if st.startswith("#"):
                continue
            if "errors=" in st and ("replace" in st or "ignore" in st):
                bad.append(f"{rel}:{i}")
    check("경계에서 조용한 치환(errors=replace/ignore)을 쓰지 않는다", not bad, "; ".join(bad))


def main() -> int:
    for fn in (test_failure_mode_is_loud, test_boundary_never_uses_ensure_ascii_true,
               test_boundary_dumps_are_explicit, test_no_silent_replacement_crept_in):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_mcp_boundary: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
