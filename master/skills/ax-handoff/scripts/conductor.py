#!/usr/bin/env python3
"""ax-handoff 의 정적 동작 — 지휘 상태 조회·마스터 담당 기록 (`#890` — 인라인 `python -c` 를 대신한다).

MCP(`ax-projects:get_orchestration_tool` · `record_master_conductor_tool`)가 안 붙어 있을 때만 쓴다.
결과는 정본 `master.work.conductor` 의 반환을 JSON 한 줄로 찍는다.

    .venv/bin/python master/skills/ax-handoff/scripts/conductor.py snapshot
    .venv/bin/python master/skills/ax-handoff/scripts/conductor.py record-master codex --why "사유" --by codex
"""
import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]          # scripts → ax-handoff → skills → master → 저장소 루트
sys.path.insert(0, str(REPO))
os.environ.setdefault("AX_PROJECTS_ROOT", str(REPO))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="conductor.py", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("snapshot", help="마스터 담당·워커 모드 조회 (읽기)")
    rec = sub.add_parser("record-master", help="마스터 담당 기록 — 사용자 지시로 실제 인수한 뒤에만")
    rec.add_argument("agent", choices=("claude", "codex", "antigravity", "agy"))
    rec.add_argument("--why", required=True)
    rec.add_argument("--by", default="")
    a = ap.parse_args(argv)
    from master.work import conductor as c
    out = c.snapshot() if a.cmd == "snapshot" else c.record_master(a.agent, why=a.why, by=a.by)
    print(json.dumps(out, ensure_ascii=False))
    return 0 if not (isinstance(out, dict) and out.get("ok") is False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
