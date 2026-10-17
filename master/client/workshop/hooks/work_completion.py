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

## CLI 대기 모드 (`#799`) — 훅이 없거나 죽었을 때 대기하는 쪽이 큐를 직접 본다

    py .claude/hooks/work_completion.py --wait <work_id> [--round N]
                                        [--timeout S] [--interval S] [--skip-failures]

훅이 못 덮는 두 자리를 위해서다 (사용자 확인 2026-10-17): ① work 가 훅 제한(`TIMEOUT` 2시간)보다
오래 걸린다 ② 요청자가 Codex CLI 다 — `.33` 의 Codex 에는 훅이 하나도 없다(실측 2026-10-17).
세션이 등재 응답의 `wait` 명령(`client_mcp._wait_command`)을 돌리면 이 모드로 들어온다.

    조회        **1분마다**(`--interval` 기본 60초) 큐를 직접 읽는다 — `wait_for_work` 와 같은
                클라(`pending_works._load_client` → `tool_get_work`)와 같은 판정(`observe`)
    읽기 전용   큐에 쓰지 않는다. 훅의 고지·잠금 파일(`.ax/work-notices`)도 **읽지도 쓰지도
                않는다** — 아래 「중복 억제」
    --round     생략하면 첫 조회의 큐 라운드를 그 대기의 라운드로 고정한다
    --timeout   기본 86400초(24시간). LLM 한도가 아니라 대기 상한이다
    stderr      조회마다 한 줄 `[wait] <work_id> r<N> · 큐 <상태> · 조각 <상태 수> · 남은 mm:ss`
    stdout      끝날 때 결과 한 덩이 — `render_result` 의 사실만 실은 본문(명령형 없음)

    종료 코드   0  ready_for_review
                3  그 밖의 종결·신호 — merged · cancelled · rejected · 실패 조각 신호
                   (failed·needs_revision, 큐는 아직 in_progress 일 수 있다) · 라운드 불일치
                4  타임아웃 — 완료로 처리하지 않는다. 마지막 상태와 조회 오류를 싣는다
                2  사용법 오류 · 연결 준비 실패(`.ax/lib`·config·token 없음)

    --skip-failures   실패 조각 신호로 끝내지 않는다(stderr 에만 찍는다). 실패 고지를 이미
                      받은 뒤 같은 라운드의 종결을 다시 기다릴 때 쓴다 — 없으면 같은 실패를
                      첫 조회에서 다시 보고 곧바로 끝난다.

[중요] **중복 억제를 공유하지 않는다.** 훅의 억제는 `(session, work_id, round)` 키라 세션마다
따로다. CLI 가 그 파일을 쓰면 같은 결과를 훅이 「이미 고지함」으로 삼키고, 훅이 쓴 파일을 CLI 가
읽으면 반대로 CLI 가 침묵한다 — **어느 쪽이 실제로 세션에 닿았는지 모르는 채** 신호 하나를
지운다. 그래서 둘은 독립이고, 같은 사실이 두 번 올 수 있다(훅 + CLI). 중복은 사람이 알아보지만
누락은 아무도 모른다. 로그(`.ax/work_completion.jsonl`)에는 `session="cli-wait"` 로 남기되
**쓰기 실패는 대기를 멈추지 않는다**(Windows 샌드박스의 `.ax` 쓰기 실패 전례, 리포트 89).
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
CLI_INTERVAL = 60          # `#799` — 훅이 없을 때 1분마다 큐를 직접 본다 (사용자 2026-10-17)
CLI_TIMEOUT = 86400        # 대기 상한(24시간) — LLM 토큰 한도가 아니다
CLI_SESSION = "cli-wait"   # 로그의 session 칸. 훅의 고지 키와 섞이지 않는다
TERMINAL = ("ready_for_review", "merged", "cancelled", "rejected")
FAILURE_STATES = ("failed", "needs_revision")
EXIT_READY, EXIT_OTHER, EXIT_TIMEOUT, EXIT_SETUP = 0, 3, 4, 2


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


def observe(detail, round_no):
    """큐 응답 한 번 → (work, 이번 라운드 조각, 상태별 수). 훅과 CLI 대기가 **같은 판정**을 쓴다.

    [중요] 라운드가 다르면 완료로 읽지 않는다 — `RuntimeError`. 지난 라운드의 terminal 을
    이번 라운드의 완료로 잘못 고지하는 것을 막는다.
    """
    work = detail.get("work") or {}
    if int(work.get("round") or 0) != round_no:
        raise RuntimeError("요청한 라운드와 서버 라운드가 다릅니다")
    tasks = [t for t in detail.get("tasks", []) if int(t.get("round") or 0) == round_no]
    counts = {}
    for task in tasks:
        status = task.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    return work, tasks, counts


def failure_keys(tasks):
    """실패 신호의 동일성 키 — 같은 실패를 두 번 고지하지 않고, 새 시도는 새 신호로 본다."""
    return [[t.get("task_id"), t.get("status"), t.get("attempt_count"),
             t.get("fail_detail"), t.get("last_feedback"),
             t.get("verdict_feedback"), t.get("fail_reason")]
            for t in tasks if t.get("status") in FAILURE_STATES]


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
            work, tasks, counts = observe(get_work(work_id), round_no)
            status = work.get("merge_status")
            state = (status, sorted(counts.items()))
            if state != previous:
                log(cwd, "state_observed", work_id, round_no, session,
                    status=status, counts=counts, worker_mode=work.get("worker_mode"))
                previous = state
            if status in TERMINAL:
                message = render_result(work, tasks, counts)
                write_state(path, {"event": "signal_emitted", "at": time.time()})
                log(cwd, "signal_emitted", work_id, round_no, session, status=status)
                return message
            failures = failure_keys(tasks)
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


def _mmss(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _counts_text(counts):
    return " · ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "없음"


def _log_quiet(cwd, event, work_id, round_no, **fields):
    """CLI 대기의 로그 — [주의] 쓰기 실패가 대기를 멈추지 않는다(stderr 줄이 주 관측이다)."""
    try:
        log(cwd, event, work_id, round_no, CLI_SESSION, **fields)
    except OSError:
        pass


def cli_wait(cwd, work_id, get_work, *, round_no=None, timeout=CLI_TIMEOUT,
             interval=CLI_INTERVAL, skip_failures=False, clock=time.monotonic,
             sleep=time.sleep, err=None):
    """`#799` — 큐를 **직접, 1분마다** 읽으며 이 work·라운드의 끝을 기다린다. 읽기만 한다.

    반환 `(종료 코드, stdout 본문)`. 코드의 뜻은 머리말 「CLI 대기 모드」 표.
    [중요] 훅의 고지·잠금 파일을 쓰지도 읽지도 않는다 — 신호를 서로 지우지 않게(머리말).
    [주의] 조회 실패는 그 자리에서 끝내지 않는다 — 한 줄 찍고 다음 조회로 간다. 끝까지
    실패하면 타임아웃(4)이 마지막 오류를 싣는다.
    """
    err = err or sys.stderr
    deadline = clock() + timeout
    last_work, last_tasks, last_counts, last_error = {}, [], {}, ""
    noticed, previous, polls = [], None, 0
    _log_quiet(cwd, "cli_wait_started", work_id, round_no, timeout=timeout, interval=interval)

    def say(line):
        print(line, file=err, flush=True)

    def finish(code, outcome, text):
        _log_quiet(cwd, "cli_wait_exit", work_id, round_no, code=code, outcome=outcome,
                   polls=polls)
        return code, text

    while True:
        polls += 1
        remain = deadline - clock()
        try:
            detail = get_work(work_id)
            if round_no is None:
                # 생략이면 첫 조회의 큐 라운드에 고정한다 — 도중에 개선요청이 와도 따라가지 않는다
                round_no = int((detail.get("work") or {}).get("round") or 0)
                if round_no < 1:
                    raise RuntimeError("큐 응답에 라운드가 없습니다")
            try:
                work, tasks, counts = observe(detail, round_no)
            except RuntimeError:
                server = (detail.get("work") or {}).get("round")
                say(f"[wait] {work_id} r{round_no} · 큐 라운드 r{server} · 남은 {_mmss(remain)}")
                return finish(EXIT_OTHER, "round_mismatch",
                              f"[분산 작업 대기 종료] {work_id} · 요청 라운드 {round_no} · "
                              f"큐 라운드 {server}\n요청한 라운드와 큐의 라운드가 다릅니다. "
                              "이 라운드의 완료로 처리하지 않았습니다.")
            last_work, last_tasks, last_counts, last_error = work, tasks, counts, ""
            status = work.get("merge_status")
            say(f"[wait] {work_id} r{round_no} · 큐 {status or '?'} · 조각 "
                f"{_counts_text(counts)} · 남은 {_mmss(remain)}")
            state = (status, sorted(counts.items()))
            if state != previous:
                _log_quiet(cwd, "state_observed", work_id, round_no, status=status,
                           counts=counts, worker_mode=work.get("worker_mode"))
                previous = state
            if status in TERMINAL:
                code = EXIT_READY if status == "ready_for_review" else EXIT_OTHER
                return finish(code, status, render_result(work, tasks, counts))
            failures = failure_keys(tasks)
            if failures and [f for f in failures if f not in noticed]:
                if not skip_failures:
                    return finish(EXIT_OTHER, "failure", render_result(work, tasks, counts))
                say(f"[wait] {work_id} r{round_no} · 실패 조각 {len(failures)}건 — "
                    "--skip-failures 로 종결까지 계속 대기")
                noticed = failures
        except Exception as exc:                            # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"[:300]
            say(f"[wait] {work_id} r{round_no if round_no is not None else '?'} · 조회 오류 "
                f"{last_error} · 남은 {_mmss(remain)}")
        left = deadline - clock()
        if left <= 0:
            break
        sleep(min(interval, left))         # 마지막 조회는 상한 시각에 한 번 더 한다
    lines = [f"[분산 작업 대기 시간 초과] {work_id} · 라운드 "
             f"{round_no if round_no is not None else '?'} · 조회 {polls}회",
             "완료로 처리하지 않았습니다."]
    if last_work:
        lines.append(render_result(last_work, last_tasks, last_counts))
    if last_error:
        lines.append(f"마지막 조회 오류: {last_error}")
    return finish(EXIT_TIMEOUT, "timeout", "\n".join(lines))


def cli_main(argv):
    """`--wait` 진입. 훅(stdin) 경로와 섞이지 않는다 — 인자가 있을 때만 여기로 온다."""
    import argparse
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="work_completion.py",
                                 description="분산 작업 완료를 큐에서 직접 읽으며 기다린다 (#799)")
    ap.add_argument("--wait", metavar="WORK_ID", required=True)
    ap.add_argument("--round", type=int, default=None, help="생략하면 큐의 현재 라운드")
    ap.add_argument("--timeout", type=float, default=CLI_TIMEOUT, help="최대 대기(초)")
    ap.add_argument("--interval", type=float, default=CLI_INTERVAL, help="조회 간격(초, 기본 60)")
    ap.add_argument("--skip-failures", action="store_true",
                    help="실패 조각 신호로 끝내지 않고 종결까지 기다린다")
    ap.add_argument("--root", default="", help="체크아웃 루트 (기본: 이 파일의 체크아웃)")
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return EXIT_SETUP if exc.code else 0
    work_id = args.wait.strip()
    if not work_id or args.interval <= 0 or args.timeout <= 0 or \
            (args.round is not None and args.round < 1):
        print("[wait] 사용법 오류 — work_id 비어 있음 · interval/timeout 0 이하 · round 1 미만 "
              "중 하나", file=sys.stderr, flush=True)
        return EXIT_SETUP
    cwd = Path(args.root) if args.root else checkout_root(Path.cwd())
    try:
        from pending_works import _load_client
        client = _load_client(cwd)
        client.HTTP_TIMEOUT = 20
        api = client.queue_api(cwd)
    except Exception as exc:                                # noqa: BLE001
        print(f"[wait] 연결 준비 실패 — {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        _log_quiet(cwd, "cli_wait_setup_error", work_id, args.round,
                   error=f"{type(exc).__name__}: {exc}"[:500])
        return EXIT_SETUP
    code, text = cli_wait(cwd, work_id, lambda wid: client.tool_get_work(api, wid),
                          round_no=args.round, timeout=args.timeout, interval=args.interval,
                          skip_failures=args.skip_failures)
    print(text, flush=True)
    return code


if __name__ == "__main__":
    sys.exit(cli_main(sys.argv[1:]) if len(sys.argv) > 1 else main())
