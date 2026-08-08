#!/usr/bin/env python3
"""Gitea `post-receive` 훅 — 푸시를 이벤트 스풀에 넣는다 (PLAN §5.4.5-a).

**이 파일이 원본이고, `install_hook.py` 가 저장소별 `post-receive.d/` 로 복사한다.**
훅을 저장소 밖에서만 고치면 다음 사람이 원본을 못 찾는다.

    작업장 push → Gitea → 이 훅 → ~/ax-spool/incoming/*.json → 소비자 → 재색인

🔴 **훅은 절대 푸시를 막지 않는다.** `post-receive` 가 0이 아닌 값을 내도 푸시는 이미
끝났지만, 에러를 뱉으면 **사용자 화면에 빨간 글씨가 뜨고 사람이 놀란다.** 색인은 부가
기능이지 푸시의 전제가 아니므로 **무슨 일이 있어도 0으로 끝낸다.** 실패는 stderr 에 한 줄만
남긴다 — 조용히 사라지지도, 사람을 막지도 않게.

🔴 **`gitea` 사용자로 돈다.** 스풀 디렉토리가 `sim:gitea` + setgid(2775)여야 쓸 수 있다.
`install_hook.py` 가 그 권한을 맞춰 준다.

🔴 **셸이 아니라 파이썬인 이유**: 커밋 제목에 따옴표·역슬래시·개행이 들어오면 셸 문자열
조립은 깨진 JSON 을 만든다. 훅은 사람의 커밋 메시지를 그대로 받는 자리라 그 입력을
통제할 수 없다. `json.dumps` 가 그 문제를 없앤다.

**project_id 는 옆 파일에서 읽는다** (`hooks/ax-project-id`). 저장소 경로에서 유추하지
않는 이유는 Gitea 가 표시 이름(`Sim/ModularStage`)과 디스크 이름(`sim/modularstage`)을
따로 쓰기 때문이다(§5.5.4-④) — 유추하면 둘 중 어느 쪽인지가 조용히 어긋난다.
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ZERO = "0" * 40
DEFAULT_SPOOL = "/home/sim/ax-spool"
# 색인기가 만든 커밋을 다시 색인하지 않기 위한 표식 (§5.5.3-d ⓑ).
INDEX_TRAILER = "[ax-index]"


def _log(msg: str) -> None:
    # stderr 는 푸시한 사람 화면에 보인다. 조용한 실패보다 낫지만 시끄러우면 안 된다.
    sys.stderr.write(f"[ax-hook] {msg}\n")


def _project_id(hook_dir: Path) -> str:
    for p in (hook_dir / "ax-project-id", hook_dir.parent / "ax-project-id"):
        try:
            v = p.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if v:
            return v
    return ""


def _subject(sha: str) -> str:
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%s", sha],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:                                  # noqa: BLE001
        return ""


def main() -> int:
    hook_dir = Path(__file__).resolve().parent
    project_id = _project_id(hook_dir)
    if not project_id:
        # project_id 없이 넣으면 스풀이 거부한다(§5.5.3-⑤). 여기서 멈추는 편이 낫다.
        _log("ax-project-id 파일이 없다 — 색인 이벤트를 넣지 않는다")
        return 0

    spool = Path(os.environ.get("AX_EVENT_SPOOL") or DEFAULT_SPOOL)
    tmp_dir, inc_dir = spool / "tmp", spool / "incoming"

    n = 0
    for line in sys.stdin:
        parts = line.split()
        if len(parts) < 3:
            continue
        old, new, ref = parts[0], parts[1], parts[2]
        if new == ZERO:
            continue                    # 브랜치 삭제 — 색인할 새 상태가 없다

        subject = _subject(new)
        if INDEX_TRAILER in subject:
            # 🔴 재귀 차단은 소비자에도 있지만 여기서도 막는다. 스풀에 안 들어가면
            #    합치기·claim 비용 자체가 발생하지 않는다.
            continue

        ev = {
            "project_id": project_id,
            "ref": ref,
            "old": old,
            "new": new,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "subject": subject,
        }
        name = f"{time.time_ns()}-{secrets.token_hex(4)}.json"
        try:
            tmp = tmp_dir / name
            tmp.write_text(json.dumps(ev, ensure_ascii=False), encoding="utf-8")
            os.chmod(tmp, 0o664)        # 소비자(sim)가 읽고 지울 수 있어야 한다
            os.replace(tmp, inc_dir / name)     # 같은 FS — 원자적
            n += 1
        except OSError as e:
            _log(f"스풀에 쓰지 못했다 ({e}) — 푸시는 정상이다. 재색인은 수동으로")
            return 0                    # 🔴 푸시를 막지 않는다

    if n:
        _log(f"색인 이벤트 {n}건 큐잉 ({project_id})")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:                             # noqa: BLE001
        # 어떤 예외도 푸시를 실패로 만들지 않는다.
        _log(f"예외 — 무시하고 통과 ({type(e).__name__}: {e})")
        sys.exit(0)
