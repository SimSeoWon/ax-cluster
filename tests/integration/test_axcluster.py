"""AXCluster 통합 검사: 명시된 검사를 별도 프로세스에서 실행한다."""
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
from master.integration_checks import load_checks, run_check


class AXClusterChecks(unittest.TestCase):
    """실제 실행·통과 증거가 있는 검사만 통합 성공으로 집계한다."""


def _test_for(entry):
    def test(self):
        result = run_check(_ROOT, entry, python=sys.executable)
        print(f"[AXCluster] {entry['path']}: {result['reason']} ({result['count']} checks)")
        detail = result['reason'] + "\n" + result['stdout'][-6000:] + "\n" + result['stderr'][-6000:]
        self.assertTrue(result['ok'], detail)
    return test


# 비어 있거나 깨진 목록은 발견 단계에서 실패한다. 다른 master 테스트를 import하지 않는다.
for _index, _entry in enumerate(load_checks(Path(__file__).with_name('checks.json'), _ROOT), 1):
    _stem = Path(_entry['path']).stem
    setattr(AXClusterChecks, f'test_{_index:02d}_{_stem}', _test_for(_entry))


if __name__ == '__main__':
    unittest.main()
