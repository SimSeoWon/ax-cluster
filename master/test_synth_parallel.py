"""합성 병렬 테스트 (`#715`). pytest 없이 그대로 실행한다.

    .venv/bin/python master/test_synth_parallel.py

[중요] 지키는 불변식:
   1. **동시 N 이면 실제로 겹쳐 돈다** — 원전 `MAX_WORKERS` 병렬의 복원
   2. **결과는 그룹 순서대로 센다** — 병렬이어도 `Stats.results` 순서·진행 로그가 직렬과 같다
   3. **상한(`limit`)은 묶기 전에** — N 개를 띄워 상한을 넘기지 않는다
   4. **연속 실패 차단은 다음 묶음을 막는다** — 이미 돈 것은 세고, 새로 띄우지 않는다
   5. **주입된 호출자는 명시하지 않으면 직렬** — 종전 테스트가 바뀌지 않는다
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from master.context_search.paths import ProjectPaths, SourceScope   # noqa: E402
from master.context_synth import synth                               # noqa: E402

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [완료] {label}")
    else:
        FAIL += 1
        print(f"  [실패] {label}" + (f" — {detail}" if detail else ""))


def _paths(tmp: Path, n: int) -> ProjectPaths:
    for k in range(n):
        f = tmp / "repo" / "pkg" / f"m{k:02d}.py"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"x{k} = {k}\n", encoding="utf-8")
    return ProjectPaths(name="PAR", root=tmp, scope=SourceScope(roots=("pkg",), exts=(".py",)))


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ax-synth-par-"))
    real = synth.synthesize_group
    try:
        p = _paths(tmp, 6)
        files = [f"pkg/m{k:02d}.py" for k in range(6)]
        live, peak, lock = [0], [0], threading.Lock()

        def fake_ok(paths, key, fs, **kw):
            with lock:
                live[0] += 1
                peak[0] = max(peak[0], live[0])
            time.sleep(0.15)
            with lock:
                live[0] -= 1
            kw["tally"].add(None)
            return synth.GroupResult(key=key, files=fs, written=True, tokens_in=10, tokens_out=2)

        print("① 동시 N 은 실제로 겹쳐 돈다")
        synth.synthesize_group = fake_ok
        t0 = time.monotonic()
        st = synth.run(p, changed=files, parallel=2)
        el = time.monotonic() - t0
        check("6그룹 모두 통과", st.written == 6, st.summary)
        check("[중요] 최대 동시 2", peak[0] == 2, str(peak[0]))
        check("시간이 직렬의 절반 정도", el < 0.15 * 6 * 0.75, f"{el:.2f}s")
        check("결과는 그룹 순서대로", [r.key for r in st.results] == sorted(r.key for r in st.results))
        check("토큰 합계", (st.tokens_in, st.tokens_out) == (60, 12), str((st.tokens_in, st.tokens_out)))
        check("인코딩 집계가 유실 없이 합쳐진다", st.encodings.unreadable == 6, str(st.encodings.unreadable))
        check("요약에 동시 수가 보인다", "동시 2" in st.summary, st.summary)

        print("② 상한은 묶기 전에")
        peak[0] = 0
        st = synth.run(p, changed=files, parallel=4, limit=3)
        check("[중요] 상한 3 을 넘기지 않는다", st.written == 3, st.summary)
        check("남은 그룹이 사유에 실린다", "상한 3" in st.aborted and "3 그룹" in st.aborted, st.aborted)

        print("③ 연속 실패 차단 — 다음 묶음을 안 띄운다")
        calls = []

        def fake_fail(paths, key, fs, **kw):
            calls.append(key)
            return synth.GroupResult(key=key, files=fs, reason="LLM 실패: 연결 거부")

        synth.synthesize_group = fake_fail
        st = synth.run(p, changed=files, parallel=2)
        check("3연속에서 멈춘다 (2+2 = 4 만 돌았다)", len(calls) == 4 and st.failed == 4, str(calls))
        check("사유에 연속 실패", "연속 실패" in st.aborted, st.aborted)

        print("④ 주입된 호출자는 명시하지 않으면 직렬")
        n, why = synth._workers(None, model="m", broker="http://x", caller=lambda *a: "")
        check("caller 가 있으면 1", (n, why) == (1, "주입된 호출자"), str((n, why)))
        check("지정값은 원전 상한(6)으로 자른다", synth._workers(99, model="m", broker="x", caller=None)[0] == 6)
        n, why = synth._workers(None, model="m", broker="http://127.0.0.1:9", caller=None)
        check("[중요] 브로커를 못 읽으면 직렬(종전)", n == 1 and "못 읽었다" in why, why)
    finally:
        synth.synthesize_group = real
        shutil.rmtree(tmp, ignore_errors=True)

    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_synth_parallel: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
