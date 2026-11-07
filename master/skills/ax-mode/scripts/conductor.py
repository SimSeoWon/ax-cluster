#!/usr/bin/env python3
"""ax-mode 의 정적 동작 — 워커 지휘자 모드 조회·변경 (`#890` — 인라인 `python -c` 를 대신한다).

MCP(`ax-projects:get_orchestration_tool` · `set_worker_mode_tool`)가 안 붙어 있을 때만 쓴다.
변경은 정본 `master.work.conductor` 가 준비 검사(readiness)를 거친다. 결과는 JSON 한 줄.

    .venv/bin/python master/skills/ax-mode/scripts/conductor.py snapshot
    .venv/bin/python master/skills/ax-mode/scripts/conductor.py set-worker codex --why "사유" --by "현재 지휘자"
    .venv/bin/python master/skills/ax-mode/scripts/conductor.py set-work-mode <work_id> claude --why "사유" --by "현재 지휘자"
"""
import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]          # scripts → ax-mode → skills → master → 저장소 루트
sys.path.insert(0, str(REPO))
os.environ.setdefault("AX_PROJECTS_ROOT", str(REPO))

MODES = ("lane", "claude", "codex")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="conductor.py", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("snapshot", help="마스터 담당·워커 모드 조회 (읽기)")
    sw = sub.add_parser("set-worker", help="전역 워커 모드 변경 — 사용자가 고른 경우만")
    sw.add_argument("mode", choices=MODES)
    sw.add_argument("--why", required=True)
    sw.add_argument("--by", default="")
    sm = sub.add_parser("set-work-mode", help="진행 중 work 하나의 지휘자 스탬프 변경 — 다음 파견부터")
    sm.add_argument("work_id")
    sm.add_argument("mode", choices=MODES)
    sm.add_argument("--why", required=True)
    sm.add_argument("--by", default="")
    a = ap.parse_args(argv)
    from master.work import conductor as c
    if a.cmd == "snapshot":
        out = c.snapshot()
    elif a.cmd == "set-worker":
        out = c.set_worker(a.mode, why=a.why, by=a.by)
    else:
        out = c.set_work_worker_mode(a.work_id, a.mode, why=a.why, by=a.by)
    print(json.dumps(out, ensure_ascii=False))
    return 0 if not (isinstance(out, dict) and out.get("ok") is False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
