#!/usr/bin/env python3
"""Gitea `post-receive` 훅 — 푸시를 이벤트 스풀에 넣는다 (PLAN §5.4.5-a).

**이 파일이 원본이고, `install_hook.py` 가 저장소별 `post-receive.d/` 로 복사한다.**
훅을 저장소 밖에서만 고치면 다음 사람이 원본을 못 찾는다.

    작업장 push → Gitea → 이 훅 → ~/ax-spool/incoming/*.json → 소비자 → 재색인

[중요] **훅은 절대 푸시를 막지 않는다.** `post-receive` 가 0이 아닌 값을 내도 푸시는 이미
끝났지만, 에러를 뱉으면 **사용자 화면에 빨간 글씨가 뜨고 사람이 놀란다.** 색인은 부가
기능이지 푸시의 전제가 아니므로 **무슨 일이 있어도 0으로 끝낸다.** 실패는 stderr 에 한 줄만
남긴다 — 조용히 사라지지도, 사람을 막지도 않게.

[중요] **`gitea` 사용자로 돈다.** 스풀 디렉토리가 `sim:gitea` + setgid(2775)여야 쓸 수 있다.
`install_hook.py` 가 그 권한을 맞춰 준다.

[중요] **셸이 아니라 파이썬인 이유**: 커밋 제목에 따옴표·역슬래시·개행이 들어오면 셸 문자열
조립은 깨진 JSON 을 만든다. 훅은 사람의 커밋 메시지를 그대로 받는 자리라 그 입력을
통제할 수 없다. `json.dumps` 가 그 문제를 없앤다.

**project_id 는 옆 파일에서 읽는다** (`hooks/ax-project-id`). 저장소 경로에서 유추하지
않는 이유는 Gitea 가 표시 이름(`Sim/ModularStage`)과 디스크 이름(`sim/modularstage`)을
따로 쓰기 때문이다(§5.5.4-④) — 유추하면 둘 중 어느 쪽인지가 조용히 어긋난다.

**골조 push 는 파견 신호도 바로 쓴다** (`#785` 갈래 C, 2026-10-10). 종전에는 신호를
소비자(`ax-indexer.service`, oneshot)만 썼는데, 소비자가 앞선 `main` push 재합성으로
~6분 바쁜 동안 `task/<W>/base` push 가 ~3분 기다렸다(실측 2026-10-10). 그래서 이 훅이
색인 이벤트와 **함께** `<디스패치 스풀>/<work_id>.json` 을 원자적으로 쓴다.

    작업장 push(task/<W>/base) → 이 훅 → ~/ax-spool/dispatch/<W>.json → ax-dispatch.path

[주의] 훅은 `master` 를 import 할 수 없다(`gitea` 사용자로 저장소 밖에서 돈다). 그래서
`autodispatch.BASE_REF` 정규식과 tmp→rename 쓰기를 **복제**했고, 레지스트리 이름을 모르므로
`project` 대신 `project_id` 를 싣는다 — 이름 풀이는 `autodispatch._read_triggers` 가 한다.
소비자의 신호 경로는 그대로 둔다(백업). 같은 work 의 신호는 파일 하나라 중복이 멱등이다.
"""
from __future__ import annotations

import json
import os
import re
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
# [주의] `master/work/autodispatch.py` 의 `BASE_REF` 와 **같은 규칙**이어야 한다 — 고칠 때 둘 다.
#    leaf 가 `base` 인 것만 신호다. 조각 브랜치(`task/<W>/<T>`)는 신호가 아니다(무한 루프).
BASE_REF = re.compile(r"^refs/heads/(task/(?P<work>[^/]+)/base)$")


def _dispatch_dir() -> Path:
    """파견 트리거 디렉토리. 소비자(`autodispatch.TRIGGER_DIR`)와 같은 곳이어야 한다.

    `AX_DISPATCH_SPOOL` 이 우선이고, 없으면 **이벤트 스풀 옆** `dispatch/` 다 — 테스트가
    `AX_EVENT_SPOOL` 만 바꿔도 진짜 `~/ax-spool/dispatch` 를 건드리지 않게 하려는 것이다.
    """
    env = (os.environ.get("AX_DISPATCH_SPOOL") or "").strip()
    if env:
        return Path(env)
    return Path(os.environ.get("AX_EVENT_SPOOL") or DEFAULT_SPOOL) / "dispatch"


def _note_dispatch(work_id: str, project_id: str, ref: str) -> bool:
    """골조 push 신호를 원자적으로 쓴다. 실패해도 **예외를 내지 않는다** — 한 줄만 남긴다.

    [주의] tmp 이름은 `.` 으로 시작하고 `.json` 으로 끝나지 않는다 — `ax-dispatch.path` 의
    `*.json` glob 에 반쯤 쓰인 파일이 걸리면 안 된다.
    """
    d = _dispatch_dir()
    body = json.dumps({"work_id": work_id, "project_id": project_id, "ref": ref,
                       "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "source": "hook"}, ensure_ascii=False)
    tmp = d / f".{work_id}.{os.getpid()}.hook.tmp"
    try:
        tmp.write_text(body + "\n", encoding="utf-8")
        os.chmod(tmp, 0o664)            # 파견기(sim)가 읽고 지울 수 있어야 한다
        os.replace(tmp, d / f"{work_id}.json")
    except OSError as e:
        try:
            tmp.unlink()
        except OSError:
            pass
        _log(f"파견 신호를 쓰지 못했다 — {work_id} ({e}) · 푸시는 정상이다. "
             f"소비자 경로·catchup(10분)이 대신 잡는다")
        return False
    _log(f"파견 신호 — {work_id} ({project_id})")
    return True


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

        # 파견 신호는 색인 이벤트와 **독립**이다 — 한쪽이 실패해도 다른 쪽은 간다.
        m = BASE_REF.match(ref.strip())
        if m:
            _note_dispatch(m.group("work"), project_id, ref)

        subject = _subject(new)
        if INDEX_TRAILER in subject:
            # [중요] 재귀 차단은 소비자에도 있지만 여기서도 막는다. 스풀에 안 들어가면
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
            return 0                    # [중요] 푸시를 막지 않는다

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
