"""승인 뒤 호출하는 AX 서비스 재시작 CLI (`#647`)."""
from __future__ import annotations

import subprocess
import sys

ALLOWED = (
    "ax-task-queue", "ax-projects", "ax-broker", "ax-indexer",
    "ax-batch", "ax-status", "ax-dispatch", "ax-review-queue",
)
RESIDENT = {"ax-task-queue", "ax-projects", "ax-broker"}
HELPER = "/usr/local/sbin/ax-service-restart-root"


def state(unit: str, *, run=subprocess.run) -> dict:
    r = run(["systemctl", "show", unit, "--property=ExecMainStartTimestampMonotonic,"
             "ExecMainStartTimestamp,ActiveState,SubState,Result,ExecMainStatus"], capture_output=True,
            text=True, timeout=15)
    if r.returncode:
        raise RuntimeError(f"systemctl show 실패 (rc={r.returncode})")
    return dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)


def restart(unit: str, *, run=subprocess.run) -> tuple[dict, dict]:
    if unit not in ALLOWED:
        raise ValueError(f"허용되지 않은 유닛: {unit}")
    before = state(unit, run=run)
    r = run(["sudo", "-n", HELPER, unit], capture_output=True, text=True, timeout=120)
    if r.returncode:
        raise RuntimeError(f"재시작 helper 실패 (rc={r.returncode}): {(r.stderr or '').strip()}")
    after = state(unit, run=run)
    old = before.get("ExecMainStartTimestampMonotonic", "")
    new = after.get("ExecMainStartTimestampMonotonic", "")
    if not old or not new or old == new:
        raise RuntimeError(f"기동 시각이 바뀌지 않았다: {old!r} → {new!r}")
    if unit in RESIDENT:
        good = after.get("ActiveState") == "active" and after.get("SubState") == "running"
    else:
        good = after.get("Result") == "success" and after.get("ExecMainStatus") == "0"
    if not good:
        raise RuntimeError("재시작 뒤 비정상 상태: "
                           f"{after.get('ActiveState')}/{after.get('SubState')} · "
                           f"result={after.get('Result')} status={after.get('ExecMainStatus')}")
    return before, after


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print(f"사용법: {sys.argv[0]} <{'|'.join(ALLOWED)}>", file=sys.stderr)
        return 2
    try:
        before, after = restart(args[0])
    except (ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"[실패] {exc}", file=sys.stderr)
        return 1
    print(f"[완료] {args[0]}: {before.get('ExecMainStartTimestamp')} → "
          f"{after.get('ExecMainStartTimestamp')} · "
          f"{after.get('ActiveState')}/{after.get('SubState')} · result={after.get('Result')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
