"""`#647` allowlist와 전후 판정 회귀."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import service_restart as S


class R:
    def __init__(self, code=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


def main() -> int:
    calls = []
    shows = iter((
        "ExecMainStartTimestampMonotonic=1\nExecMainStartTimestamp=old\nActiveState=active\nSubState=running\nResult=success\nExecMainStatus=0\n",
        "ExecMainStartTimestampMonotonic=2\nExecMainStartTimestamp=new\nActiveState=active\nSubState=running\nResult=success\nExecMainStatus=0\n",
    ))
    def run(cmd, **kwargs):
        calls.append(cmd)
        return R(out=next(shows)) if cmd[:2] == ["systemctl", "show"] else R()
    before, after = S.restart("ax-projects", run=run)
    assert before["ExecMainStartTimestampMonotonic"] == "1"
    assert after["ExecMainStartTimestampMonotonic"] == "2"
    assert calls[1] == ["sudo", "-n", S.HELPER, "ax-projects"]
    shows = iter((
        "ExecMainStartTimestampMonotonic=1\nActiveState=inactive\nSubState=dead\nResult=success\nExecMainStatus=0\n",
        "ExecMainStartTimestampMonotonic=2\nActiveState=inactive\nSubState=dead\nResult=success\nExecMainStatus=0\n",
    ))
    S.restart("ax-status", run=run)
    try:
        S.restart("ssh", run=run)
    except ValueError:
        pass
    else:
        raise AssertionError("미허용 유닛을 받았다")
    assert S.main(["ax-projects", "extra"]) == 2
    print("통과 6 · 실패 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
