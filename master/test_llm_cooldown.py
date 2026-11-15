"""생성 체인 파일 쿨다운(`#964` T1) 계약 테스트 — [중요] **한도에 걸린 백엔드를 새 프로세스에서도 다시 두드리지 않는가.**

실행: .venv/bin/python master/test_llm_cooldown.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from master import layer2_verify as L2                 # noqa: E402
from master import llm_cooldown as CD                  # noqa: E402
from master.context_synth import review_gen as RG      # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def test_classify_and_file():
    check("한도 표지 → 1시간", CD.classify("rc=1 — You've hit your usage limit") == ("quota", 3600))
    check("429 → 1시간", CD.classify("HTTP 429 Too Many Requests")[1] == 3600)
    check("그 밖 → 600초", CD.classify("timeout 240s") == ("other", 600))
    with tempfile.TemporaryDirectory() as t:
        f = Path(t) / "cd.json"
        check("없는 파일 → 0", CD.remaining("codex", path=f) == 0)
        e = CD.mark("codex", "quota exceeded", path=f, now=1000.0)
        check("기록", e["kind"] == "quota" and CD.remaining("codex", path=f, now=1000.0) == 3600)
        check("시간이 지나면 0", CD.remaining("codex", path=f, now=1000.0 + 3601) == 0)
        check("관측 state", "codex" in CD.state(path=f, now=1001.0) and CD.state(path=f, now=9999.0) == {})
        check("해제", CD.clear("codex", path=f) and CD.remaining("codex", path=f, now=1000.0) == 0)
        check("없는 것 해제는 False", CD.clear("agy", path=f) is False)
        f.write_text("{깨짐")
        check("깨진 파일 → 쿨다운 없음(막지 않는다)", CD.remaining("codex", path=f) == 0)


def _run_chain(f: Path, log: Path) -> str:
    code = f'''
import sys; sys.path.insert(0, {str(ROOT)!r})
from master import layer2_verify as L2
from master.context_synth import review_gen as RG
from pathlib import Path
def codex(p, timeout=0, **k):
    open({str(log)!r}, "a").write("codex\\n"); return None, "rc=1 — You've hit your usage limit"
def agy(p, timeout=0, **k):
    open({str(log)!r}, "a").write("agy\\n"); return "ok", ""
L2.WHY_BACKENDS = [("codex", codex), ("agy", agy)]
for _ in range(3): RG.commercial_chat("x", cooldown_path=Path({str(f)!r}))
'''
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stderr


def test_cooldown_survives_new_process():
    """재현 ③ — 고친 뒤: 한도 실패 codex 는 첫 호출 1회뿐, 이후 항목·새 프로세스는 건너뛴다."""
    with tempfile.TemporaryDirectory() as t:
        f, log = Path(t) / "cd.json", Path(t) / "calls"
        err1 = _run_chain(f, log)
        _run_chain(f, log)
        calls = log.read_text().split()
        check("codex 1회 · agy 6회", calls.count("codex") == 1 and calls.count("agy") == 6, str(calls))
        check("쿨다운 로그 줄", "[cooldown] codex 쿨다운 3600초(quota)" in err1, err1)


def test_success_clears_and_all_cooled_reports():
    with tempfile.TemporaryDirectory() as t:
        f = Path(t) / "cd.json"
        saved = L2.WHY_BACKENDS
        try:
            CD.mark("codex", "quota", path=f)
            L2.WHY_BACKENDS = [("codex", lambda p, timeout=0, **k: ("응답", ""))]
            try:
                RG.commercial_chat("x", cooldown_path=f)
                ok = False
            except RG.ReviewChatError as e:
                ok = "쿨다운" in str(e) and "건너뜀" in str(e)
            check("전부 쿨다운 → 「건너뜀」 사유로 실패", ok)
            CD.mark("codex", "quota", path=f, now=0.0)        # 이미 만료
            check("만료 뒤 호출 · 성공하면 해제", RG.commercial_chat("x", cooldown_path=f) == "응답"
                  and CD._read(f) == {})
        finally:
            L2.WHY_BACKENDS = saved


def test_fakes_never_touch_machine_file():
    """[중요] 가짜 백엔드 + cooldown_path 없음 → 기본 파일을 읽지도 쓰지도 않는다."""
    with tempfile.TemporaryDirectory() as t:
        import os
        f = Path(t) / "machine.json"
        os.environ["AX_LLM_COOLDOWN_FILE"] = str(f)
        saved = L2.WHY_BACKENDS
        try:
            L2.WHY_BACKENDS = [("codex", lambda p, timeout=0, **k: (None, "usage limit")),
                               ("agy", lambda p, timeout=0, **k: ("ok", ""))]
            RG.commercial_chat("x")
            check("가짜 실패가 기계 파일을 만들지 않는다", not f.exists())
            check("진짜 함수 판별 — 기본 체인은 진짜 (#966 agy 1순위)", saved[0][1] is L2.call_agy_why)
        finally:
            L2.WHY_BACKENDS = saved
            os.environ.pop("AX_LLM_COOLDOWN_FILE", None)


def main() -> int:
    for fn in (test_classify_and_file, test_cooldown_survives_new_process, test_success_clears_and_all_cooled_reports,
               test_fakes_never_touch_machine_file):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_llm_cooldown: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
