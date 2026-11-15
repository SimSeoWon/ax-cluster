"""AXCluster 통합 검사: 명시된 검사를 별도 프로세스에서 실행한다.

`#965` — 병렬 개수는 `tests/test-parallel.json` 의 `integration_jobs`(환경변수 `AX_TEST_JOBS` 가
덮어쓴다). 1 이면 종전처럼 테스트마다 그 자리에서 실행한다(`-f` 첫 실패에서 뒤는 실행하지 않는다).
2 이상이면 첫 테스트가 불릴 때 전체를 스레드로 미리 돌리고, 메서드 이름·단정·출력 형식은 그대로다 —
`work/followup.py` 가 `FAIL: test_NN_… (test_axcluster.AXClusterChecks)` 줄을 해석하기 때문이다.
"""
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
from master.integration_checks import load_checks, parallel_jobs, run_check

_ENTRIES = load_checks(Path(__file__).with_name('checks.json'), _ROOT)
_SETTING = parallel_jobs("integration_jobs", _ROOT)
_RESULTS: dict = {}
_LOCK = threading.Lock()
_SLOWEST = 5


def _timed(entry):
    t0 = time.monotonic()
    result = run_check(_ROOT, entry, python=sys.executable)
    result["seconds"] = time.monotonic() - t0
    return result


def _log(msg: str) -> None:
    print(f"[AXCluster] {msg}", file=sys.stderr, flush=True)


def _prefetch() -> None:
    """병렬일 때 한 번만 전체를 미리 돌린다. 결과는 경로로 찾는다."""
    with _LOCK:
        if _RESULTS:
            return
        jobs = _SETTING["jobs"]
        t0 = time.monotonic()
        with ThreadPoolExecutor(max_workers=jobs, thread_name_prefix="ax-check") as pool:
            for entry, result in zip(_ENTRIES, pool.map(_timed, _ENTRIES)):
                _RESULTS[entry['path']] = result
        failed = [p for p, r in _RESULTS.items() if not r['ok']]
        slow = sorted(_RESULTS.items(), key=lambda kv: -kv[1]['seconds'])[:_SLOWEST]
        _log(f"병렬 실행 끝 {time.monotonic() - t0:.1f}초 · 실패 {len(failed)}건"
             + (f" ({', '.join(failed)})" if failed else ""))
        _log("가장 느린 검사: " + " · ".join(f"{p} {r['seconds']:.1f}초" for p, r in slow))


class AXClusterChecks(unittest.TestCase):
    """실제 실행·통과 증거가 있는 검사만 통합 성공으로 집계한다."""

    @classmethod
    def setUpClass(cls):
        if _SETTING["reason"]:
            _log(_SETTING["reason"])
        if _SETTING["jobs"] <= 1:
            _log(f"순차 실행 ({_SETTING['source']}) · 검사 {len(_ENTRIES)}건")
        else:
            _log(f"병렬 {_SETTING['jobs']} ({_SETTING['source']}) · 검사 {len(_ENTRIES)}건 — 첫 테스트에서 전체를 미리 돈다")


def _test_for(entry):
    def test(self):
        if _SETTING["jobs"] > 1:
            _prefetch()
            result = _RESULTS[entry['path']]
        else:
            result = _timed(entry)
        print(f"[AXCluster] {entry['path']}: {result['reason']} ({result['count']} checks)"
              f" {result['seconds']:.1f}s")
        detail = result['reason'] + "\n" + result['stdout'][-6000:] + "\n" + result['stderr'][-6000:]
        self.assertTrue(result['ok'], detail)
    return test


# 비어 있거나 깨진 목록은 발견 단계에서 실패한다. 다른 master 테스트를 import하지 않는다.
for _index, _entry in enumerate(_ENTRIES, 1):
    _stem = Path(_entry['path']).stem
    setattr(AXClusterChecks, f'test_{_index:02d}_{_stem}', _test_for(_entry))


if __name__ == '__main__':
    unittest.main()
