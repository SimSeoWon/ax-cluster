#!/usr/bin/env python3
"""ax-bc250-shutdown 스크립트 — BC-250 (.43) 전용 안전 전원 종료 CLI.

    .venv/bin/python master/skills/ax-bc250-shutdown/scripts/shutdown.py --dry-run
    .venv/bin/python master/skills/ax-bc250-shutdown/scripts/shutdown.py --check-only
    .venv/bin/python master/skills/ax-bc250-shutdown/scripts/shutdown.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]  # scripts → ax-bc250-shutdown → skills → master → 저장소 루트
sys.path.insert(0, str(REPO))
os.environ.setdefault("AX_PROJECTS_ROOT", str(REPO))

from master.infra.bc250_shutdown import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
