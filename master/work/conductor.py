"""마스터 담당 기록과 워커 모드 조회. 담당 기록은 프로세스 생존 판정이나 잠금이 아니다."""
from __future__ import annotations
import json
import csv
import ntpath
import os
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from . import mode

STATE = Path.home() / ".cache/ax-dispatch/conductor.json"


def _windows_codex_registration(facts, project, read, run_shell):
    """실제 `/IT LIMITED` 런처 등록을 읽는다. Codex 실행 성공 검사는 별도다."""
    from client.init import residency as R

    name = R.conductor_task_name(project)
    # 프로젝트 이름이 SSH cmd.exe 명령으로 해석되는 것을 허용하지 않는다.
    if any(c in name for c in '\"&|<>^%\r\n'):
        return ["예약 작업 이름에 허용되지 않은 문자가 있다"]
    rc, out = run_shell(facts.host, facts.user,
                        f'schtasks /query /tn "{name}" /xml', timeout=30)
    if rc != 0:
        return ["Codex 예약 런처 조회 실패: " + ((out or f"exit {rc}")[-240:])]
    try:
        xml = ET.fromstring((out or "").lstrip('\ufeff').strip())
    except ET.ParseError:
        return ["Codex 예약 런처 XML 형식 오류"]
    if xml.tag.split('}')[-1] != 'Task':
        return ["Codex 예약 런처 XML에 Task가 없다"]
    principals = xml.findall('./{*}Principals/{*}Principal')
    actions = xml.findall('./{*}Actions/*')
    if len(principals) != 1 or len(actions) != 1 or actions[0].tag.split('}')[-1] != 'Exec':
        return ["Codex 예약 런처 principal/Exec 구성이 계약과 다르다"]
    principal, action = principals[0], actions[0]
    value = lambda element, field: (element.findtext('{*}' + field) or '').strip()
    problems = []
    if value(principal, 'LogonType') != 'InteractiveToken':
        problems.append("Codex 예약 런처가 로그인 사용자 세션 전용(InteractiveToken)이 아니다")
    # Task Scheduler는 기본 LeastPrivilege/Enabled=true 요소를 XML에서 생략한다.
    if (value(principal, 'RunLevel') or 'LeastPrivilege') != 'LeastPrivilege':
        problems.append("Codex 예약 런처가 LIMITED(LeastPrivilege)가 아니다")
    context = xml.find('./{*}Actions').get('Context', '')
    if context and context != principal.get('id', ''):
        problems.append("Codex 예약 런처 Actions 실행 주체가 Principal과 다르다")
    enabled = (xml.findtext('./{*}Settings/{*}Enabled') or 'true').strip().lower()
    if enabled != 'true':
        problems.append("Codex 예약 런처가 비활성화됐다")
    # UserId는 SID 또는 DOMAIN\\user다. SSH 계정의 실제 SID와 함께 대조한다.
    rc, identity = run_shell(facts.host, facts.user, 'whoami /user /fo csv /nh', timeout=30)
    try:
        rows = list(csv.reader((identity or '').strip().splitlines(), strict=True))
        account, sid = rows[0] if rc == 0 and len(rows) == 1 else ('', '')
    except (ValueError, csv.Error):
        account, sid = '', ''
    account, sid = account.strip(), sid.strip()
    expected_user = facts.user.casefold()
    account_ok = (account.casefold() == expected_user if '\\' in facts.user else
                  account.rsplit('\\', 1)[-1].casefold() == expected_user)
    registered_user = value(principal, 'UserId').casefold()
    allowed_users = {account.casefold(), sid.casefold(), account.rsplit('\\', 1)[-1].casefold()}
    if not account or not sid.startswith('S-1-') or not account_ok or registered_user not in allowed_users:
        problems.append("Codex 예약 런처 실행 계정이 SSH 워커 계정과 일치하지 않는다")
    command = value(action, 'Command').strip('"')
    if (not ntpath.isabs(command) or not ntpath.splitdrive(command)[0] or
            ntpath.basename(command).casefold() not in ('pythonw.exe', 'python.exe')):
        problems.append("Codex 예약 런처 실행 파일이 절대경로 Python 인터프리터가 아니다")
    script = ntpath.join(facts.path, R.CONDUCTOR_REL.replace('/', '\\'))
    arguments = value(action, 'Arguments')
    if arguments.startswith('"') and arguments.endswith('"'):
        arguments = arguments[1:-1]
    if ntpath.normcase(ntpath.normpath(arguments)) != ntpath.normcase(ntpath.normpath(script)):
        problems.append("Codex 예약 런처 실행 경로가 프로젝트 배달물과 다르다")
    if not (read(facts, script) or '').strip():
        problems.append(f"Codex 예약 런처 파일을 읽지 못했다: {script}")
    return problems


def worker_mode_readiness(selected, project="", *, registry=None, prober=None,
                          reader=None, shell_probe=None):
    """선택한 지휘자의 배달물과 실제 파견 경로 등록을 호스트별로 확인한다.

    파일 존재만으로 통과시키지 않는다. 2026-09-11 `.2`에는 `ax-work`가 있었지만
    Codex command runner가 Session 0에서 죽어 읽지 못했다(`#401`).
    """
    selected = mode._check(selected)
    if selected == "lane":
        return {"ok": True, "mode": selected, "project": project or "", "hosts": []}

    from ..client import bundle, spec
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
        skill = ((ntpath.join(facts.path, spec.project_skill_rel('ax-work').replace('/', '\\'))
                  if facts.windows else f"{facts.path}/{spec.project_skill_rel('ax-work')}")
                 if selected == "codex" else
                 f"{facts.home}\\.claude\\skills\\ax-work\\SKILL.md" if facts.windows else
                 f"{facts.home}/.{selected}/skills/ax-work/SKILL.md")
        if not (read(facts, skill) or "").strip():
            problems.append(f"필수 스킬을 읽지 못했다: {skill}")
        if selected == "codex" and facts.windows and not problems:
            # SSH Session 0에서 Codex를 실행하면 실제 /IT 파견과 다른 경로를 잰다.
            # 조회만 한다. 셸 읽기·apply_patch·결과 회수는 실제 런처에서 별도 검증한다.
            problems.extend(_windows_codex_registration(facts, target, read, run_shell))
        rows.append({"host": host, "ok": not problems, "version": version,
                     "problems": problems})
    if not rows:
        return {"ok": False, "mode": selected, "project": target,
                "reason": "검사할 SSH 워커가 없다", "hosts": []}
    bad = [r for r in rows if not r["ok"]]
    return {"ok": not bad, "mode": selected, "project": target, "hosts": rows,
            **({"note": "배달물·예약 런처 등록 검사다. 로그인 상태와 실제 Codex 셸 읽기·"
                        "apply_patch·결과 회수 성공은 별도 실행 검증이 필요하다"}
               if selected == "codex" else {}),
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
