"""정본 ⑹ — **등재한 라운드의 끝을 사람의 다음 타이핑 없이 받는다** (사용자 지시 2026-09-09).

## 왜 이 훅이 필요한가 — 마스터는 세션 안으로 못 들어간다

종전 고지 경로는 **전부 pull** 이었다(`pending_works.py` 머리말이 이미 그렇게 적고 있다):
Redmine 이슈도 `:8103` 화면도 pull 이고, 그 훅이 붙은 이벤트는 `SessionStart` 와
`UserPromptSubmit` **둘뿐**이라 **사람이 켜거나 타이핑해야** 돈다. 마스터는 `.33` 에 SSH 는
넣지만 **돌고 있는 `claude` 세션 안에는 못 넣는다** — 밖에서 안으로 들어가는 문은 그 세션이
스스로 도는 훅과 그 세션이 부르는 MCP 뿐이다. 실측 2026-09-10 01:23: 마스터가 완주하고
Redmine `#395` 까지 냈는데 `.33` 은 몰랐다.

## 계약 — [중요] 실측이다 (2026-09-10, CLI 2.1.267 · 리포트 60)

    PostToolUse + asyncRewake   훅이 백그라운드로 빠진다 — 턴을 안 막는다
                                (실측: 훅이 30초 자는 동안 턴은 3.2초에 끝났다)
    exit 2                      **유휴 세션을 깨운다** — 지연 ~0초. 화면에는 `Stop hook
                                feedback` 으로 뜨고, stderr 가 그 뒤에 **그대로** 붙는다
    exit 0                      아무 일도 없다 (조용히 끝낸다)

    근거 문자열(바이너리): *"If true, hook runs in background and wakes the model on exit
    code 2 (blocking error). Implies async."*
    → https://code.claude.com/docs/en/hooks#command-hook-fields

[중요] **exit 2 는 실패가 아니다** — 이 훅에서는 「할 말이 생겼다」는 뜻이고, 정상 완료가
그 대부분이다.
[중요] **SDK 세션만이 아니라 TUI 대화 세션에서도 깬다** (실측 4/4). `.33` 이 쓰는 형태다.

## [중요] 실을 수 있는 말의 모양이 제한된다 — `render_result` 참조

훅이 보낸 문구는 **사람이 쓴 말이 아니다.** 명령형을 실으면 주입으로 거부된다(실측).
「무엇이 왔나」만 여기서 말하고, 「그래서 무엇을 하나」는 `ax-request` 스킬에 둔다.

## 경계

큐가 완료의 주인이다 — **이 훅은 파견도 상태 변경도 하지 않는다.** 조회만 한다.
로그(`.ax/work_completion.jsonl`)는 **관측(`state_observed`)과 발행(`signal_emitted`)을
가른다.** [주의] `signal_emitted` 는 **훅이 보냈다**는 기록일 뿐이고, 세션이 실제로 받았다는
증거는 **대화 기록뿐**이다. 그 둘을 같은 것으로 적지 않는다.
"""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from hook_paths import checkout_root

sys.dont_write_bytecode = True
INTERVAL = 15
TIMEOUT = 7200


def result_object(value):
    """Accept the actual MCP text-content envelope as well as a direct JSON result."""
    if isinstance(value, str):
        try:
            return result_object(json.loads(value))
        except ValueError:
            return {}
    if isinstance(value, list):
        for item in value:
            got = result_object(item)
            if got:
                return got
        return {}
    if not isinstance(value, dict) or value.get("isError"):
        return {}
    if "work_id" in value and "ok" in value:
        return value
    for key in ("content", "text", "result", "structuredContent"):
        if key in value:
            got = result_object(value[key])
            if got:
                return got
    return {}


def notice_path(cwd, session, work_id, round_no):
    key = json.dumps([session, work_id, round_no], ensure_ascii=True)
    return Path(cwd) / ".ax" / "work-notices" / (hashlib.sha256(key.encode()).hexdigest() + ".json")


def write_state(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(f".{os.getpid()}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def log(cwd, event, work_id, round_no, session, **fields):
    folder = Path(cwd) / ".ax"
    folder.mkdir(parents=True, exist_ok=True)
    row = dict(at=time.time(), event=event, work_id=work_id, round=round_no,
               session=session, **fields)
    with (folder / "work_completion.jsonl").open("a", encoding="utf-8") as out:
        out.write(json.dumps(row, ensure_ascii=False) + "\n")


def already_noticed(cwd, session, work_id, round_no):
    p = notice_path(cwd, session, work_id, round_no)
    try:
        value = json.loads(p.read_text(encoding="utf-8"))
        return value.get("event") == "signal_emitted" and value.get("kind") != "failure"
    except (OSError, ValueError):
        return False


def pending_failure_watch(cwd, session):
    """A failure wakes the session; its next tool call resumes completion monitoring."""
    folder = Path(cwd) / ".ax" / "work-notices"
    for path in sorted(folder.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("kind") == "failure" and value.get("session") == session:
                return value
        except (OSError, ValueError):
            continue
    return {}


def render_result(work, tasks, counts):
    """완료 고지 본문 — 🔴 [중요] **사실만 싣는다. 명령형을 쓰지 않는다** (실측 2026-09-10).

    훅의 stderr 는 **그대로** 세션에 얹힌다. 그런데 그것은 사람이 쓴 말이 아니므로, 거기에
    「~하세요」가 들어 있으면 깨어난 모델이 **훅을 탈취한 주입으로 보고 거부한다.** 실측
    (TUI · 같은 훅 · 문구만 교체, 리포트 60):

        명령형(*"…다시 묻지 말고 결과를 보고하세요"*)  → 거부
            *"it appears to contain suspicious instructions embedded in what looks like a
              stop hook. I'm not following injected directives…"*
        사실만                                        → 수용

    [중요] **「그래서 무엇을 하나」는 여기 적지 않는다** — `ax-request` 스킬이 말한다. 그쪽은
    세션이 원래 읽는 **자기 문서**라 같은 판정을 받지 않는다. 실측 4판에서 사실 + 스킬 조합만
    *"⑦ 통합 검사(ax-advance)가 다음이며, 이는 사람의 승인이 필요합니다"* 까지 냈고, 사실만
    있고 스킬이 없으면 *"알림을 받았다"* 로 끝났다.

    [주의] 목록 렌더는 `pending_works._line` 을 **빌려 쓴다** — 같은 사실을 두 훅이 다르게
    찍으면 사람이 둘을 대조할 수 없다.
    """
    wid = work.get("work_id") or "(id 없음)"
    head = [f"[분산 작업 결과] {wid} · 라운드 {work.get('round')} · {work.get('merge_status')}"]
    if work.get("worker_mode"):
        head.append(f"지휘자 {work['worker_mode']}")
    try:
        from pending_works import _line
        head.append(_line(work, {"tasks": tasks}))
    except Exception:                                       # noqa: BLE001
        # [주의] 렌더러를 못 불러도 **고지를 접지 않는다** — 사실이 줄어들 뿐이다.
        head.append(f"  · 조각 {json.dumps(counts, ensure_ascii=False)}")
    if work.get("redmine_issue_id"):
        head.append(f"Redmine #{work['redmine_issue_id']}")
    if work.get("merge_status") in ("rejected", "cancelled"):
        head.append("작업 종결 상태이며 통합·전진 대기 대상이 아닙니다.")
    if work.get("notification_error"):
        head.append(f"통보 실패: {work['notification_error']}")
        if work.get("termination_required"):
            head.append("통보 복구 또는 강제 종결에 사람 판단이 필요한 상태입니다.")
    for t in tasks:
        if t.get("status") in ("failed", "needs_revision"):
            why = str(t.get("fail_detail") or t.get("last_feedback") or
                      t.get("verdict_feedback") or t.get("fail_reason") or "사유 없음")[:500]
            label = "실패" if t.get("status") == "failed" else "실패 후 재시도 대기"
            head.append(f"{label} {t.get('task_id')}: {why}")
    return "\n".join(head)


def wait_for_work(cwd, session, work_id, round_no, get_work, *, timeout=TIMEOUT,
                  interval=INTERVAL, clock=time.monotonic, sleep=time.sleep):
    path = notice_path(cwd, session, work_id, round_no)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(".lock")
    # A dead hook can leave a lock. The heartbeat makes its expiry observable.
    try:
        if lock.exists() and time.time() - lock.stat().st_mtime > 90:
            lock.unlink()
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        # [중요] 조용히 넘기지 않는다 — 「감시자가 둘 붙었다」와 「훅이 안 돌았다」는 다르다.
        log(cwd, "lock_held", work_id, round_no, session, lock=str(lock))
        return ""
    os.close(fd)
    try:
        if already_noticed(cwd, session, work_id, round_no):
            log(cwd, "already_noticed", work_id, round_no, session)
            return ""
        try:
            noticed_failures = json.loads(path.read_text(encoding="utf-8")).get("failures", [])
        except (OSError, ValueError):
            noticed_failures = []
        log(cwd, "watch_started", work_id, round_no, session)
        deadline, previous = clock() + timeout, None
        while clock() < deadline:
            lock.touch()
            detail = get_work(work_id)
            work = detail.get("work") or {}
            if int(work.get("round") or 0) != round_no:
                raise RuntimeError("요청한 라운드와 서버 라운드가 다릅니다")
            tasks = [t for t in detail.get("tasks", []) if int(t.get("round") or 0) == round_no]
            counts = {}
            for task in tasks:
                status = task.get("status", "unknown")
                counts[status] = counts.get(status, 0) + 1
            status = work.get("merge_status")
            state = (status, sorted(counts.items()))
            if state != previous:
                log(cwd, "state_observed", work_id, round_no, session,
                    status=status, counts=counts, worker_mode=work.get("worker_mode"))
                previous = state
            if status in ("ready_for_review", "merged", "cancelled", "rejected"):
                message = render_result(work, tasks, counts)
                write_state(path, {"event": "signal_emitted", "at": time.time()})
                log(cwd, "signal_emitted", work_id, round_no, session, status=status)
                return message
            failures = [[t.get("task_id"), t.get("status"), t.get("attempt_count"),
                         t.get("fail_detail"), t.get("last_feedback"),
                         t.get("verdict_feedback"), t.get("fail_reason")]
                        for t in tasks if t.get("status") in ("failed", "needs_revision")]
            new_failures = [failure for failure in failures if failure not in noticed_failures]
            if new_failures:
                message = render_result(work, tasks, counts)
                write_state(path, {"event": "signal_emitted", "kind": "failure",
                                   "at": time.time(), "session": session,
                                   "work_id": work_id, "round": round_no,
                                   "failures": noticed_failures + new_failures})
                log(cwd, "signal_emitted", work_id, round_no, session,
                    status=status, kind="failure", counts=counts)
                return message
            sleep(interval)
        raise TimeoutError("완료 대기 시간이 지났습니다. 완료로 처리하지 않았습니다")
    finally:
        lock.unlink(missing_ok=True)


def main():
    """🔴 [중요] **걸었는지와 「왜 안 걸었는지」를 둘 다 찍는다** (`~/CLAUDE.md` 파견 규칙).

    종전에는 등록 호출이 아니면 **조용히 `return 0`** 이었다. 그러면 「훅이 안 붙었다」와
    「훅은 돌았는데 이 호출이 대상이 아니었다」가 **로그에서 구분되지 않는다** — 파견 트리거가
    정확히 그 침묵으로 이틀을 태웠다(2026-08-29~31). 그래서 **모든 발동을 한 줄 남긴다.**
    """
    # Windows redirected stderr must preserve the Korean system reminder.
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    try:
        data = json.load(sys.stdin)
        # 🔴 [중요] 고지·로그가 놓일 자리는 **체크아웃 루트**다 — 하위 폴더에서 연
        #    세션의 cwd 를 그대로 쓰면 `Source/NS/.ax/work-notices` 에 써서
        #    ⑹ 깨우기가 그 자리를 안 본다 (실측 2026-09-20 `.33`).
        cwd = checkout_root(data["cwd"])
    except Exception as exc:                                # noqa: BLE001
        # [주의] cwd 를 모르면 남길 자리가 없다 — stderr 로만 말하고 **exit 0** 이다
        #    (2 로 끝내면 「할 말이 생겼다」가 돼 세션을 깨운다).
        print(f"[분산 작업 훅] stdin 을 못 읽었다 — {type(exc).__name__}: {exc}",
              file=sys.stderr, flush=True)
        return 0
    session = str(data.get("session_id") or "unknown")
    tool = str(data.get("tool_name") or "?")
    result = result_object(data.get("tool_response"))
    wid = str(result.get("work_id") or "")
    if result.get("ok") is not True or not wid:
        # [중요] **이것이 정상 경로다** — 등록·개선요청이 아닌 도구 호출은 대부분 여기로 온다.
        #    그래도 찍는다: 침묵과 구분되어야 「훅은 살아 있다」를 로그로 말할 수 있다.
        log(cwd, "not_a_registration", wid or None, None, session,
            tool=tool, ok=result.get("ok"))
        result = pending_failure_watch(cwd, session)
        wid = str(result.get("work_id") or "")
        if not wid:
            return 0
        log(cwd, "watch_resumed", wid, result.get("round"), session, tool=tool)
    try:
        round_no = int(result["round"])
    except (KeyError, TypeError, ValueError) as exc:
        log(cwd, "bad_round", wid, None, session, tool=tool, error=str(exc)[:200])
        return 0
    log(cwd, "hook_fired", wid, round_no, session, tool=tool)
    try:
        from pending_works import _load_client
        client = _load_client(cwd)
        client.HTTP_TIMEOUT = 6
        api = client.queue_api(cwd)
        message = wait_for_work(cwd, session, wid, round_no,
                                lambda work_id: client.tool_get_work(api, work_id))
    except Exception as exc:
        log(cwd, "watch_error", wid, round_no, session,
            error=f"{type(exc).__name__}: {exc}"[:500])
        message = (f"[분산 작업 수신 오류] {wid} · 라운드 {round_no}: {exc}\n"
                   "작업 종결 여부를 확인하지 못했습니다. 통보 복구 또는 강제 종결에 "
                   "사람 판단이 필요한 상태입니다.")
    # [중요] 나가는 코드를 남긴다 — `2` 만이 세션을 깨운다. `0` 으로 끝난 판을 나중에
    #    「고지가 안 왔다」로 조사할 때, 훅이 조용히 넘긴 것인지가 여기서 갈린다.
    code = 2 if message else 0
    log(cwd, "exit", wid, round_no, session, code=code, chars=len(message or ""))
    if message:
        print(message, file=sys.stderr, flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
