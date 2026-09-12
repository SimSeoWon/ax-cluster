"""마스터 담당 기록과 워커 모드 조회. 담당 기록은 프로세스 생존 판정이나 잠금이 아니다."""
from __future__ import annotations
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from . import mode

STATE = Path.home() / ".cache/ax-dispatch/conductor.json"


def worker_mode_readiness(selected, project="", *, registry=None, prober=None,
                          reader=None, shell_probe=None):
    """선택한 지휘자가 **실제 SSH 파견 경로에서** 준비됐는지 호스트별로 잰다.

    파일 존재만으로 통과시키지 않는다. 2026-09-11 `.2`에는 `ax-work`가 있었지만
    Codex command runner가 Session 0에서 죽어 읽지 못했다(`#401`).
    """
    selected = mode._check(selected)
    if selected == "lane":
        return {"ok": True, "mode": selected, "project": project or "", "hosts": []}

    from ..client import bundle
    from ..projects.config import Registry

    reg = registry or Registry.load()
    target = project or reg.active
    if not target:
        return {"ok": False, "mode": selected, "project": "",
                "reason": "active 프로젝트가 없어 지휘자 준비 상태를 잴 수 없다", "hosts": []}
    probe = prober or bundle.probe
    read = reader or bundle._remote_read
    run_shell = shell_probe or bundle._ssh
    rows = []
    for host, user, path, driven, role, dispatch in bundle.workshops(target):
        if driven != "ssh" or role != "worker" or dispatch == "never":
            continue
        facts = probe(host, user, path, driven, role, dispatch)
        problems = []
        version = facts.claude if selected == "claude" else facts.codex
        if not version:
            problems.append(f"{selected} 실행 파일/버전을 확인하지 못했다")
        skill = (f"{facts.home}\\.codex\\skills\\ax-work\\SKILL.md" if facts.windows
                 and selected == "codex" else
                 f"{facts.home}\\.claude\\skills\\ax-work\\SKILL.md" if facts.windows else
                 f"{facts.home}/.{selected}/skills/ax-work/SKILL.md")
        if not (read(facts, skill) or "").strip():
            problems.append(f"필수 스킬을 읽지 못했다: {skill}")
        if selected == "codex" and facts.windows and not problems:
            # 🔴 [중요] **`sandbox` 다음은 실행할 명령이다 — 서브커맨드가 아니다** (실측
            #    2026-09-12). 종전 `codex sandbox **windows** cmd /d /c …` 는 `windows` 를
            #    **실행 파일 이름으로** 먹어 `CreateProcessAsUserW failed: 2 (지정된 파일을
            #    찾을 수 없습니다)` 로 죽었다. 그래서 이 probe 는 **환경이 멀쩡해도 늘 실패**
            #    했고, `.2` 를 codex 지휘자에서 빼 둔 판정의 근거가 됐다.
            #    [주의] 같은 기계에서 `codex sandbox cmd.exe /d /c echo …` 는 **세션 0 에서도
            #    통과한다** — 제한 토큰 샌드박스의 단순 경로는 원래 되고, 죽는 것은
            #    `codex exec` 의 셸 도구(unified exec)다(`#401` · 리포트 62·63).
            cmd = 'codex sandbox cmd.exe /d /c echo AX_CODEX_SHELL_READY'
            rc, out = run_shell(host, user, cmd, timeout=30)
            if rc != 0 or "AX_CODEX_SHELL_READY" not in (out or ""):
                problems.append("SSH Session 0 Codex sandbox 셸 probe 실패: "
                                + ((out or f"exit {rc}")[-240:]))
        rows.append({"host": host, "ok": not problems, "version": version,
                     "problems": problems})
    if not rows:
        return {"ok": False, "mode": selected, "project": target,
                "reason": "검사할 SSH 워커가 없다", "hosts": []}
    bad = [r for r in rows if not r["ok"]]
    return {"ok": not bad, "mode": selected, "project": target, "hosts": rows,
            **({"reason": "준비되지 않은 워커: " + ", ".join(r["host"] for r in bad)
                + " — 배달물 누락은 `python -m master.client deliver <프로젝트>`, "
                  "실행 probe 실패는 해당 지휘자 런타임을 복구한 뒤 다시 검사할 것"}
               if bad else {})}

def master_record():
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("agent") not in ("claude", "codex"):
            raise ValueError("담당 기록 형식 오류")
        return data
    except FileNotFoundError:
        return {"agent": "unknown", "note": "담당 기록 없음"}
    except (OSError, ValueError) as exc:
        return {"agent": "unknown", "note": str(exc)}

def record_master(agent, why, by=""):
    if agent not in ("claude", "codex"):
        raise ValueError("마스터 담당은 claude 또는 codex")
    if not isinstance(why, str) or not why.strip():
        raise ValueError("담당 기록 사유가 필요하다")
    if not isinstance(by, str):
        raise ValueError("기록자는 문자열이어야 한다")
    data = {"agent": agent, "why": why.strip(), "by": by.strip(),
            "at": datetime.now().astimezone().isoformat(timespec="seconds")}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".conductor-", dir=STATE.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False)
            out.write("\n")
        os.replace(name, STATE)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return {"ok": True, "master": data}

def snapshot():
    selected, source = mode.current()
    return {"ok": True, "master": master_record(),
            "worker": {"mode": selected, "source": source, "state": mode.read_state()},
            "note": "마스터는 마지막 담당 기록이며 실행 중임을 보증하지 않는다"}

def set_worker(selected, why, by="", *, readiness=None):
    if not isinstance(selected, str) or not isinstance(by, str):
        raise ValueError("모드와 기록자는 문자열이어야 한다")
    if not isinstance(why, str) or not why.strip():
        raise ValueError("워커 모드 변경 사유가 필요하다")
    ready = readiness if readiness is not None else worker_mode_readiness(selected)
    if not ready.get("ok"):
        raise ValueError("지휘자 모드를 바꾸지 않았다 — " + ready.get("reason", "준비 검사 실패"))
    saved = mode.set_mode(selected, why=why, by=by)
    selected_now, source = mode.current()
    return {**snapshot(), "saved": saved, "readiness": ready,
            "mode": selected_now, "source": source, "describe": mode.describe()}
