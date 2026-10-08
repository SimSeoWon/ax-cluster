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
from types import SimpleNamespace
from unittest.mock import patch

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


def test_related_resource():
    """관련검색은 한 번 초기화하고 coordinator에서만 검색·해제한다."""
    import contextlib
    import io
    with tempfile.TemporaryDirectory(prefix="ax-synth-related-") as tmp:
        p = _paths(Path(tmp), 5)
        files = [f"pkg/m{k:02d}.py" for k in range(5)]
        coordinator = threading.get_ident()
        opens, searches, closed, groups = [], [], [], []

        class Search:
            def search(self, query, **kw):
                searches.append(threading.get_ident())
                return [SimpleNamespace(file_id="other.md", excerpt="관련 요약")]
            def close(self):
                closed.append(threading.get_ident())

        def factory(paths):
            opens.append(threading.get_ident())
            return Search()

        def fake(paths, key, fs, **kw):
            groups.append((threading.get_ident(), kw["related"]))
            return synth.GroupResult(key=key, files=fs, written=True)

        with patch.object(synth, "_open_related", side_effect=factory), \
                patch.object(synth, "synthesize_group", side_effect=fake):
            st = synth.run(p, changed=files, parallel=2)
        check("실제 작업 여러 묶음에도 초기화·해제 각 1회", opens == [coordinator]
              and closed == [coordinator], str((opens, closed)))
        check("검색 5건은 coordinator에서만 실행", searches == [coordinator] * 5)
        check("병렬 worker는 검색 대신 수집된 요약 사용", st.written == 5
              and all(t != coordinator and related == [("other.md", "관련 요약")]
                      for t, related in groups[:4]))

        groups.clear()
        with patch.object(synth, "_open_related", side_effect=KeyError("bindings")) as opener, \
                patch.object(synth, "synthesize_group", side_effect=fake), \
                contextlib.redirect_stderr(io.StringIO()) as logs:
            st = synth.run(p, changed=files, parallel=2)
        check("초기화 실패는 배치당 한 번만 시도", opener.call_count == 1)
        check("초기화 실패 사유를 남기고 빈 related로 계속", "bindings" in logs.getvalue()
              and "재초기화하지 않는다" in logs.getvalue()
              and st.written == 5 and all(not r for _t, r in groups))

        closed.clear()
        with patch.object(synth, "_open_related", side_effect=factory), \
                patch.object(synth, "synthesize_group", side_effect=RuntimeError("worker fixture")):
            try:
                synth.run(p, changed=files, parallel=2)
            except RuntimeError:
                pass
        check("worker 예외에서도 소유 검색기를 해제", closed == [coordinator])

        for key in synth.group(files):
            out = synth.doc_path(p, key)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("existing", encoding="utf-8")
        with patch.object(synth, "_open_related") as opener:
            st = synth.run(p, changed=files, parallel=2, skip_existing=True)
        check("전부 skip인 배치는 검색기를 열지 않음", not opener.called and st.skipped == 5)

        with patch.object(synth, "_open_related") as opener, \
                patch.object(synth, "synthesize_group", side_effect=fake):
            synth.run(p, changed=files, parallel=2, caller=lambda *_a: "")
        check("주입된 caller는 실제 검색 초기화 없이 격리", not opener.called)
        with patch.object(synth, "_open_related") as opener, \
                patch.object(synth, "_generate", side_effect=synth.GenerateError("fixture")):
            direct = synth.synthesize_group(p, "pkg/m00", files[:1],
                                            caller=lambda *_a: "", dry_run=True)
        check("실제 직접 그룹 합성도 주입 caller의 외부검색을 격리",
              not opener.called and direct.reason.startswith("LLM 실패"))

        closed.clear()
        with patch.object(synth, "_open_related", side_effect=factory):
            related = synth.collect_related(p, "pkg/m00", files[:1], "")
        check("직접 관련검색은 자체 소유 연결을 해제", related == [("other.md", "관련 요약")]
              and closed == [coordinator])
        closed.clear()
        supplied = Search()
        with patch.object(synth, "synthesize_group", side_effect=fake):
            synth.run(p, changed=files, parallel=2, caller=lambda *_a: "", searcher=supplied)
        check("주입 검색기의 해제는 호출자 몫", closed == [])


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ax-synth-par-"))
    real = synth.synthesize_group
    # 기존 worker fake 검사도 실제 Chroma 초기화를 하지 않는다.
    empty_search = SimpleNamespace(search=lambda *_a, **_kw: [], close=lambda: None)
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
        st = synth.run(p, changed=files, parallel=2, searcher=empty_search)
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
        st = synth.run(p, changed=files, parallel=4, limit=3, searcher=empty_search)
        check("[중요] 상한 3 을 넘기지 않는다", st.written == 3, st.summary)
        check("남은 그룹이 사유에 실린다", "상한 3" in st.aborted and "3 그룹" in st.aborted, st.aborted)

        print("③ 연속 실패 차단 — 다음 묶음을 안 띄운다")
        calls = []

        def fake_fail(paths, key, fs, **kw):
            calls.append(key)
            return synth.GroupResult(key=key, files=fs, reason="LLM 실패: 연결 거부")

        synth.synthesize_group = fake_fail
        st = synth.run(p, changed=files, parallel=2, searcher=empty_search)
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

    print("⑤ 검색기 배치 수명·병렬 격리")
    test_related_resource()

    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_synth_parallel: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
