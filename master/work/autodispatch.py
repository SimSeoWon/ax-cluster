"""자동 파견 — 골조가 올라오면 마스터가 끝까지 배당한다 (`#340`).

## 왜 이것이 없었나

원전은 **워커 데몬이 30초마다 `claim`** 했다(`worker/worker.py`: poll → claim → LLM →
commit·push → submit → 다시 claim). 그 루프가 배당 엔진이었다. `#320`(2026-08-27)이 상주를
철거하면서 **그 엔진이 사라졌는데, 대체를 만들지 않았다** — `#320` 의 완료 조건은
*"빌드가 SSH 로 도는가"* 뿐이었고 파견을 라이브로 확인하지 않았다.

3일간 안 드러난 이유는 그 뒤 실제 분산 작업이 **파견 단계까지 간 적이 없어서**다. 2026-08-30
첫 완주 시도에서 골조가 올라오자 그제서야 「아무도 안 집는다」가 보였다. 사용자:
*"워커 데몬 안쓴다고 자동으로 등록된 모든 일 처리해야 된다는 말이잖아 —
작업완료되었다면 다음 일 할당시키라고"*.

## [중요] 파견 다음 칸(통합)까지 이 모듈이 잇는다 — 실측 2026-09-01

`#340` 은 *"워커 데몬이 배당 엔진이었다"* 로 **배당만** 복구했다. 그런데 원전 루프는
`poll → claim → LLM → commit·push → **submit** → 다시 claim` 이고, `submit` 은 통합자 안에
있다(`integrate.py:888`). 그래서 배당만 되살린 뒤 첫 완주에서 **4/4 추론 성공 · 조각 전부
`claimed` · `submitted_at=None`** 이 나왔다 — 고친 것과 **같은 종류의 침묵**이 한 칸 뒤에.
당시 `integrate.run` 의 프로덕션 호출부는 **0곳**(주석 두 줄이 전부)이었다.

[주의] 사람 게이트를 여기 만들지 않는다 — `~/CLAUDE.md` 파이프라인에서 `[사람 승인]` 표식이
붙은 곳은 **finalize(`main` 머지) 한 곳뿐**이다.

## [중요] 「끝나면 다음 배당」은 이미 있다

`infer.run_many` 가 **워커가 빌 때마다 다음 태스크를 집는** 루프다(`while True` + 빈 워커
판정). 여기서 만드는 것은 그 루프를 **시작시키는 자리** 하나뿐이다 — 새 배당 엔진이 아니다.

## 트리거는 골조 push 다 — 등재가 아니다

등재 시점에는 골조가 아직 없다(`#317` ① 순서: 0 등재 → 1 브랜치 → 2 골조 → 3 태스크).
`task/<work_id>/base` 가 원격에 **나타나는 것**이 「요청자가 자기 몫을 끝냈다」는 유일한
관측 가능한 신호다. 그것은 이미 스풀에 이벤트로 들어온다(`post-receive` → `Event.ref`).

## 🔴 [중요] 트리거를 소비자 **안**에서 돌리면 안 된다 — 실측 2026-08-31

배선을 두 번 놓쳤다. 첫 번째는 `on_push` 를 만들고 **호출부를 안 만든 것**(전 저장소 인용 0),
두 번째는 「소비자 안 어딘가에 넣으면 된다」는 오독이다. 후자가 왜 틀린지:

    23:08:24  [중요] 색인 일시 중지 — 진행 중 분산 작업 1건 (20260831_2301_work_0edff5f3)
                    · 이벤트 1건 넘김

그 1건이 골조 push 이벤트였다. `events/consumer.py` 의 게이트는 `claim_batch` 로 이벤트를
claim 하고 `done()` 으로 **버린 뒤 `return`** 한다. 그리고 **골조 push 는 정의상 항상 그
게이트가 켜진 상태에서 일어난다**(`#317` ① 순서: 0 등재 → 1 브랜치 → 2 골조 push). 그래서
게이트 뒤에 있는 코드는 **영원히 안 불린다.**

두 번째 함정도 실측으로 확인했다 — `coalesce()` 는 `project_id` 당 **최신 하나만** 남기므로,
골조 push 뒤에 같은 프로젝트의 다른 push 가 한 배치에 들어오면 `batch.events` 에서 골조 ref 가
**조용히 사라진다**(실측: base+main 두 건을 넣으면 남는 것은 `refs/heads/main` 뿐). 그래서
`_note_dispatch_triggers` 는 `batch.events` 가 아니라 **배치 디렉토리를 직접 읽는다.**

⇒ 소비자는 **신호 파일만** 쓰고(`note_trigger`), 파견은 전용 유닛이 한다(`drain`).

## [주의] 가드 넷 — 돈이 나가는 자리다

    멱등     pending 태스크가 있는 work 만. 이미 파견 중이면 물러난다
    base     `twin_base.resolve().exists` 가 참일 때만 (`#331` 과 같은 판정)
    동시성    파일 잠금 — 같은 work 을 두 프로세스가 밀지 않는다
    보고     걸었는지·왜 안 걸었는지를 **둘 다** 저널에 남긴다

[중요] **안 건 이유도 찍는다.** 오늘 `[register]` 로그가 없었으면 등재 실패를 못 찾았다 —
파견은 그보다 조용한 자리라 「안 걸렸다」가 안 보이면 사람이 영원히 기다린다.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

LOCK_DIR = Path.home() / ".cache" / "ax-dispatch"
# `#340` 트리거 스풀. 색인 스풀(`~/ax-spool/incoming`)과 **다른 디렉토리**다 —
# 소비자는 색인 게이트에 걸리면 자기 스풀을 비우므로(아래 `note_trigger` 주석) 같은 곳에
# 두면 파견 신호도 같이 사라진다.
TRIGGER_DIR = Path(os.environ.get("AX_DISPATCH_SPOOL")
                   or Path.home() / "ax-spool" / "dispatch")
# `refs/heads/task/<work_id>/base` — `#319` 계층형 이름. leaf 가 `base` 인 것만 신호다.
BASE_REF = re.compile(r"^refs/heads/(task/(?P<work>[^/]+)/base)$")


def work_id_from_ref(ref: str) -> str:
    """골조 push 인가. 아니면 빈 문자열.

    [주의] 조각 durable(`task/<W>/<T>`)은 신호가 아니다 — 그것은 통합자가 미는 것이고,
    그때 파견을 다시 걸면 무한 루프다.
    """
    m = BASE_REF.match((ref or "").strip())
    return m.group("work") if m else ""


# [중요] **세션 한도는 실패가 아니라 「지금은 못 한다」다** (사용자 결정 2026-09-01 · 실측 01:03).
#    `.2` 의 `claude` 가 한도에 걸려 4조각 중 3이 죽었다. 사유 문장에 **리셋 시각이 들어 있다** —
#    그것을 읽어 그때까지 **안 두드린다.** 10분 타이머가 그냥 재시도하면 리셋까지 `attempt_count`
#    만 태우고(실측 기준 ~15회) 조각이 소진 처리될 수 있다.
SESSION_LIMIT_RE = re.compile(
    r"session limit.*?resets\s+(?P<h>\d{1,2}):(?P<m>\d{2})\s*(?P<ap>am|pm)", re.I)
HOLD_FILE = LOCK_DIR / "hold.json"
HOLD_FALLBACK_SEC = 3600      # 리셋 시각을 못 읽었을 때 — 두드리는 것보다 낫다


def _next_local(hour: int, minute: int) -> float:
    """다음번 그 시각(로컬)의 epoch. 이미 지났으면 내일."""
    import datetime as _dt
    now = _dt.datetime.now()
    t = now.replace(hour=hour % 24, minute=minute, second=0, microsecond=0)
    if t <= now:
        t += _dt.timedelta(days=1)
    return t.timestamp()


def session_limit_until(reasons) -> tuple:
    """실패 사유들에서 세션 한도를 읽는다. `(epoch|0, 원문)`."""
    for why in reasons:
        m = SESSION_LIMIT_RE.search(str(why or ""))
        if not m:
            continue
        h, mi = int(m.group("h")), int(m.group("m"))
        if m.group("ap").lower() == "pm" and h != 12:
            h += 12
        if m.group("ap").lower() == "am" and h == 12:
            h = 0
        return _next_local(h, mi), str(why)
        # [주의] 못 읽으면 아래 폴백 — 사유는 남긴다
    for why in reasons:
        if "session limit" in str(why or "").lower():
            return time.time() + HOLD_FALLBACK_SEC, str(why)
    return 0.0, ""


def _write_hold(d: dict) -> None:
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    HOLD_FILE.write_text(json.dumps(d, ensure_ascii=False) + "\n", encoding="utf-8")


def set_hold(until: float, reason: str, *, work_id: str = "", project: str = "") -> None:
    """[중요] 파일로 남긴다 — **재부팅을 넘어야** 한다. 타이머는 부팅 5분 뒤에도 뜬다."""
    _write_hold({"state": "held", "until": until,
                 "until_str": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(until)),
                 "reason": reason[:500], "work_id": work_id, "project": project,
                 "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})


def clear_hold() -> bool:
    """보류를 지운다. `--resume` 만 부른다 — [중요] **시간이 지났다는 사실로는 안 지운다.**"""
    try:
        HOLD_FILE.unlink()
        return True
    except OSError:
        return False


def hold_state() -> dict:
    """보류 파일 원문(없으면 빈 dict). 큐의 상태 표면이 이것을 실어 요청자에게 보낸다."""
    try:
        d = json.loads(HOLD_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def hold_active() -> tuple:
    """`(막을까, 사유문장)`.

    [중요] **시각이 지나도 자동으로 풀지 않는다** (사용자 결정 2026-09-01):
    *"공지하고 내가 작업 시작 지시하면 이어서 진행해야 해"*. 그래서 만료는 「해제」가 아니라
    **`awaiting_resume` 로의 전이**이고, 그 뒤로도 계속 막는다. 푸는 것은 `--resume` 뿐이다.
    [주의] 종전에는 만료 시 파일을 지워 **다음 타이머가 자동으로 재파견**했다 — 사람이 모르는
    사이에 돈이 나가는 자리였고, 사용자가 그것을 사람 게이트로 바꾸라고 지시했다.
    """
    d = hold_state()
    if not d:
        return False, ""
    until = float(d.get("until") or 0)
    wid = str(d.get("work_id") or "")
    if until > time.time():
        left = int(until - time.time())
        return True, (f"세션 한도로 보류 중 — {d.get('until_str')} 까지 "
                      f"(남은 {left // 60}분) · {str(d.get('reason'))[:120]}")
    if str(d.get("state") or "") != "awaiting_resume":
        d["state"] = "awaiting_resume"
        d["expired_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        _write_hold(d)
    proj = str(d.get("project") or "<프로젝트>")
    return True, (f"[재개 대기] 세션 한도가 풀렸다({d.get('until_str')}) — "
                  f"**사람이 지시해야 이어간다.** "
                  f"재개: python -m master.work.autodispatch --resume {proj} {wid}".rstrip())


def _log(msg: str) -> None:
    print(f"[dispatch] {msg}", flush=True)


class _Lock:
    """work 하나당 잠금. **같은 work 을 두 번 밀지 않는다.**

    [주의] 소비자의 flock 과 같은 결이다 — 잡히면 **기다리지 않고 물러난다.** 파견은 분 단위라
    줄 세우면 뒤엣것이 리스 만료를 본다.
    """

    def __init__(self, work_id: str):
        LOCK_DIR.mkdir(parents=True, exist_ok=True)
        self.path = LOCK_DIR / f"{work_id}.lock"
        self.fd = None

    def __enter__(self):
        import fcntl
        self.fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(self.fd)
            self.fd = None
            return None
        os.write(self.fd, f"{os.getpid()} {time.time():.0f}\n".encode())
        return self

    def __exit__(self, *exc):
        if self.fd is not None:
            import fcntl
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)


def pending_tasks(work_id: str, *, api=None) -> list:
    """아직 아무도 안 집은 태스크. [중요] **이것이 비면 파견하지 않는다** (멱등)."""
    from . import runner
    call = api or runner._api
    got = call("GET", f"/api/v1/works/{work_id}")
    tasks = (got or {}).get("tasks") or []
    return [t for t in tasks if str(t.get("status") or "") == "pending"]


def should_dispatch(paths, work_id: str, *, api=None) -> tuple:
    """`(걸까, 사유)`. **안 거는 이유도 문장으로 낸다** — 조용히 넘기지 않는다."""
    from . import runner, twin_base
    # [중요] **보류가 최우선이다.** 한도 중에 파견하면 조각의 attempt 만 태운다.
    held, why_hold = hold_active()
    if held:
        return False, why_hold
    call = api or runner._api
    try:
        got = call("GET", f"/api/v1/works/{work_id}")
    except Exception as e:                                   # noqa: BLE001
        return False, f"work 조회 실패 — {type(e).__name__}: {e}"
    work = (got or {}).get("work") or {}
    if not work:
        return False, f"큐에 없는 work 이다 ({work_id})"
    status = str(work.get("merge_status") or "")
    if status not in ("in_progress", ""):
        return False, f"merge_status={status!r} — 진행 중인 work 만 민다"

    pend = [t for t in (got.get("tasks") or []) if str(t.get("status") or "") == "pending"]
    if not pend:
        return False, "pending 태스크가 없다 — 이미 파견됐거나 끝났다 (멱등)"

    # [중요] `#331` 과 같은 판정 — base 가 없으면 조각이 갈라질 자리가 없다
    b = twin_base.resolve(paths, work_id)
    if not b.checked:
        return False, f"base 확인 실패 — {b.error} (확인 실패는 통과가 아니다)"
    if not b.exists:
        return False, f"base 가 원격에 없다 — {b.branch}. 요청자가 먼저 올려야 한다"
    return True, f"pending {len(pend)}건 · base {b.commit[:8]}"


def needs_integration(paths, work_id: str, *, api=None) -> tuple:
    """추론은 끝났는데 통합이 안 된 work 인가. `(그런가, 사유)`.

    [중요] **이 자리가 비면 아무도 못 꺼낸다.** `dispatch()` 는 `pending > 0` 일 때만 시작하므로,
    추론이 다 끝난 뒤 통합이 안 걸린 work 은 **파견 경로로 영원히 다시 안 잡힌다**
    (실측 2026-09-01: 4/4 추론 성공 · pending 0 · `submitted_at=None` 인 work 이 그렇게 떴다).
    `ax-indexer.timer` 가 게이트로 넘긴 분을 되찾는 것과 **같은 역할**이다.
    """
    from . import runner
    # [중요] **보류가 여기에도 걸려야 한다** (실측 2026-09-01 01:13 — 내가 낸 구멍).
    #    `should_dispatch` 만 막았더니 catchup 의 **회수 경로가 한도를 무시하고** 부분 통합을
    #    돌렸다. 한도는 「지금은 못 한다」이므로 통합도 미룬다 — 층2 도 같은 `claude` 를 쓴다.
    held, why_hold = hold_active()
    if held:
        return False, why_hold
    call = api or runner._api
    try:
        got = call("GET", f"/api/v1/works/{work_id}")
    except Exception as e:                                       # noqa: BLE001
        return False, f"work 조회 실패 — {type(e).__name__}: {e}"
    work = (got or {}).get("work") or {}
    if str(work.get("merge_status") or "") not in ("in_progress", ""):
        return False, f"merge_status={work.get('merge_status')!r}"
    tasks = got.get("tasks") or []
    if not tasks:
        return False, "태스크가 없다"
    if any(str(t.get("status") or "") == "pending" for t in tasks):
        return False, "pending 이 남았다 — 파견이 먼저다"
    # 🔴 [중요] 정본 ⑸ 이후 `submitted` 의 뜻이 바뀌었다 (2026-09-02): **워커가 자기 서브
    #    브랜치에 커밋하고 제출한 것**이다(종전에는 통합자가 제출했다). 그래서 여기서 멈추는
    #    것이 옳고, 다음 칸은 **⑺ 사람 승인**이다 — 자동 통합이 아니다.
    # [주의] **사유 문구가 거짓말을 하지 않게 한다** — 종전 문구는 *"이미 통합이 손을 댔다"*
    #    였는데 통합은 손댄 적이 없다. 그 종류의 오문구가 2026-08-29~31 이틀을 태웠다.
    done = [t for t in tasks if str(t.get("status") or "") in ("submitted", "verified")]
    if done:
        return False, (f"워커 커밋 완료 {len(done)}/{len(tasks)}건 — **⑺ 사람 승인 대기**"
                       f" (정본 7단계: 통합 여부는 `.33` 이 묻는다)")
    if any(str(t.get("status") or "") == "failed" for t in tasks):
        return False, "실패한 조각이 있다 — 재적용하지 않는다 (사람이 판단한다)"
    stuck = [t for t in tasks if str(t.get("status") or "") == "claimed"]
    if not stuck:
        return False, "claimed 인 조각이 없다"
    # 스풀에 실물 응답이 있어야 적용할 것이 있다.
    try:
        import json as _json

        from .infer import spool_dir          # [주의] 정의는 infer 다 (integrate 는 재수출)
        d = spool_dir(paths, work_id)
        files = sorted(d.glob("*.json")) if d.is_dir() else []
        n = len(files)
        # [중요] **실패 응답을 「완료」로 세지 않는다** (실측 2026-09-01 01:13 — 세션 한도로 3건이
        #    죽었는데 `스풀 응답 4/4건` 이라고 찍었다). 적용되는 것은 `DONE` 뿐이므로
        #    (`load_handoff` 가 `r.ok` 로 거른다) 그 수를 따로 세서 문장에 싣는다.
        n_ok = 0
        for f in files:
            try:
                if str(_json.loads(f.read_text(encoding="utf-8")).get("status") or "") == "DONE":
                    n_ok += 1
            except (OSError, ValueError):
                continue
    except Exception as e:                                       # noqa: BLE001
        return False, f"스풀 확인 실패 — {type(e).__name__}: {e}"
    if not n_ok:
        return False, (f"통과한 응답이 0건이다 (스풀 {n}건 전부 실패) — 적용할 것이 없다")
    # [중요] **`pending 0` 은 「추론 완료」가 아니다** (실측 2026-09-01 01:03). 추론이 실패하면
    #    조각은 `pending` 으로 돌아가지 않고 **`claimed` 로 남는다**(리스 만료까지). 그래서
    #    세션 한도로 3/4 가 실패한 work 이 「pending 0」을 만족해 **1/4 만 들고** 통합에 들어갔다.
    #    판정 기준은 상태가 아니라 **응답이 조각 수만큼 스풀에 있는가**다.
    if n < len(tasks):
        return False, (f"응답 {n}/{len(tasks)}건 — 추론이 덜 끝났다 "
                       f"(전량 재적용을 피한다. 남은 조각이 들어온 뒤 통합한다)")
    # 조각마다 응답은 왔다. 통과분만 적용되므로 그 수를 **문장에 그대로 싣는다** —
    # 「4/4 응답 · 통과 1」과 「4/4 응답 · 통과 4」는 사람이 다르게 판단할 상태다.
    return True, (f"claimed {len(stuck)}건 · 응답 {n}/{len(tasks)}건 · "
                  f"통과 {n_ok}건{' [주의] 나머지는 실패라 적용되지 않는다' if n_ok < n else ''}")


def dispatch(paths, work_id: str, *, limit: int = 0, api=None, runner_many=None) -> dict:
    """한 work 을 **끝까지** 민다. `run_many` 가 워커가 빌 때마다 다음 조각을 집는다.

    [중요] 여기서 배당 루프를 새로 짜지 않는다 — `infer.run_many` 가 이미 그것이고,
    *"워커가 빌 때만 집는다"* 는 실측된 규칙(집어놓고 못 돌리면 리스가 1200초 묶인다)이다.
    """
    ok, why = should_dispatch(paths, work_id, api=api)
    if not ok:
        _log(f"{work_id} 안 건다 — {why}")
        return {"dispatched": False, "reason": why}

    with _Lock(work_id) as lk:
        if lk is None:
            _log(f"{work_id} 안 건다 — 이미 파견이 돌고 있다 (잠금)")
            return {"dispatched": False, "reason": "이미 파견 중"}
        n = limit or len(pending_tasks(work_id, api=api))
        _log(f"{work_id} 파견 시작 — {why} · limit={n}")
        fn = runner_many
        if fn is None:
            from .infer import run_many as fn                # noqa: PLC0415
        # 🔴 [중요] **병렬을 명시로 넘긴다** (사용자 확정 2026-09-03). 종전에는 넘기지 않아
        #    `run_many` 의 옛 기본값(`False`)이 그대로 먹었고, **자동 파견 경로에는 병렬을
        #    켤 자리가 아예 없었다.** 기본값에 의존하면 그 기본값이 바뀐 줄도 모른다.
        hand = fn(paths, limit=n, project=paths.name, work_id=work_id, parallel=True)
        # [중요] **필드 이름을 확인하고 읽는다** (`#342`, 실측 2026-08-30). 처음에
        #    `hand.responses` 를 읽어 **성공을 「응답 0건」으로 보고**했다 — 실제로는
        #    `Handoff.items` 다(`[(order, Response), …]`). 만들고 확인하지 않은 자리다.
        note = getattr(hand, "note", "") or ""
        items = list(getattr(hand, "items", []) or [])
        skipped = list(getattr(hand, "skipped", []) or [])
        ok = [r for _o, r in items if str(getattr(r, "status", "")) == "DONE"]
        bad = [r for _o, r in items if str(getattr(r, "status", "")) != "DONE"]
        _log(f"{work_id} 파견 끝 — 성공 {len(ok)} · 실패 {len(bad)} · 건너뜀 {len(skipped)}"
             + (f" · {note}" if note else ""))
        # [중요] **실패·건너뜀은 한 줄씩 찍는다** — 수를 세는 것만으로는 왜 멈췄는지 모른다.
        for r in bad:
            _log(f"  [실패] {getattr(r,'task_id','?')} @ {getattr(r,'worker','?')} — "
                 f"{str(getattr(r,'reason',''))[:200]}")
        for tid, why in skipped:
            _log(f"  [건너뜀] {tid} — {why}")
        out = {"dispatched": True, "ok": len(ok), "failed": len(bad),
               "skipped": len(skipped), "note": note}

        # ── [중요] 세션 한도면 **여기서 멈춘다** (사용자 결정 2026-09-01) ──
        #
        # 한도는 조각의 결함이 아니라 계정의 상태다. 부분 통합을 하면 나머지가 3:40am 뒤에
        # 들어올 때 스풀 전량이 다시 적용되고(`load_handoff` 는 제출 여부를 안 본다), 층2 도
        # 같은 `claude` 를 쓰므로 어차피 같은 한도에 걸린다. **보류하고 통째로 다시 한다.**
        until, why_lim = session_limit_until(
            [getattr(r, "reason", "") for r in bad] + [note])
        if until:
            set_hold(until, why_lim, work_id=work_id, project=paths.name)
            _log(f"[중요] {work_id} 세션 한도 — "
                 f"{time.strftime('%m-%d %H:%M', time.localtime(until))} 까지 보류한다. "
                 f"통합하지 않는다 (부분 적용은 재적용을 만든다)")
            _log(f"  [중요] 재개는 자동이 아니다 (사용자 결정 2026-09-01) — 시각이 지나면 "
                 f"「재개 대기」로 바뀌고 사람의 지시를 기다린다. "
                 f"`.33` 세션 시작 훅이 그 사실을 고지한다")
            _log(f"  재개: python -m master.work.autodispatch --resume {paths.name} {work_id}")
            out["held_until"] = until
            return out

        # ── [중요] 다음 칸을 이어 붙인다 — 통합 (`#340` 의 한 칸 뒤, 실측 2026-09-01) ──
        #
        # 종전에는 여기서 끝났다. 추론이 4/4 성공해도 조각은 `claimed` · `submitted_at=None`
        # 으로 남고 **아무도 안 집었다.** `#320` 이 걷은 원전 워커 루프는
        # `poll → claim → LLM → commit·push → submit → 다시 claim` 이었고, `#340` 은 그
        # **앞쪽 절반(배당)만** 대체했다. `submit` 은 통합자 안에 있다(`integrate.py:888`).
        #
        # [주의] 사람 게이트는 여기가 아니다 — `~/CLAUDE.md` 파이프라인에서 `[사람 승인]` 은
        # **finalize(main 머지) 한 곳뿐**이다. 통합까지는 자동이 설계다.
        #
        # [중요] **추론이 다 끝났을 때만 한 번 부른다.** `load_handoff` 는 스풀의 통과분을
        # **전량** 싣고(이미 제출된 것을 걸러내지 않는다), `one_base` 는 기준 커밋이 섞이면
        # 거절한다 — 조각이 남은 채로 부르면 다음 회차에 같은 것을 다시 적용하거나 기준이
        # 섞여 통합이 통째로 막힌다. 그래서 조건은 「pending 0」이다.
        # [중요] 판정을 **한 함수로 모은다** — `needs_integration` 이 「응답이 조각 수만큼
        #    스풀에 있는가」로 본다. 종전에 여기만 `pending 0` 으로 봤다가, 실패가 `claimed` 로
        #    남는 경로에서 1/4 만 들고 통합에 들어갔다(실측 2026-09-01 01:03).
        # [중요] **마스터는 여기서 끝난다** (사용자 확정 2026-09-03). 종전에는 이 자리에서
        #    「통합자」를 골라 적용·빌드·커밋까지 했는데, 정본 ⑺ 은 **모든 서브태스크가 끝나면
        #    요청자(`.33`)에 완료를 공지하고, 통합 여부는 거기서 사람이 정하는 것**이다.
        #    공지는 큐가 낸다 — 조각이 전부 terminal 이 되면 `merge_status` 가
        #    `ready_for_review` 로 뒤집히고 `logic_cleanup` 이 Redmine [리뷰 요청] 이슈를 만든다.
        need, why_i = needs_integration(paths, work_id, api=api)
        out["all_pieces_done"] = bool(need)
        _log(f"{work_id} " + ("조각 전부 완료 — 요청자(.33) 공지 대기 (통합은 .33 에서)"
                              if need else f"아직 안 끝났다 — {why_i}"))
        return out


def on_push(paths_for, ref: str, *, api=None) -> dict:
    """스풀 이벤트 하나를 본다. 골조 push 가 아니면 아무것도 안 한다.

    `paths_for(work_id)` 는 프로젝트 경로 해석기 — 호출부가 준다(이벤트가 프로젝트를 안다).
    """
    work_id = work_id_from_ref(ref)
    if not work_id:
        return {"dispatched": False, "reason": "골조 push 가 아니다"}
    return dispatch(paths_for(work_id), work_id, api=api)


def note_trigger(work_id: str, project: str, ref: str = "") -> Path:
    """골조 push 를 봤다는 **신호만** 파일로 남긴다. [중요] 여기서 파견하지 않는다.

    `#340` 갈래 ⓑ. 파견은 **분 단위**인데 이것을 부르는 `master.events.consumer` 는
    `ax-indexer.service`(oneshot) 안에서 돈다 — 거기서 동기로 파견하면 색인이 그만큼 막힌다
    (갈래 ⓒ 가 안 되는 이유). 그래서 신호만 쓰고 실제 파견은 `ax-dispatch.service` 가 한다.

    [주의] **원자적으로 쓴다** — `ax-dispatch.path` 가 inotify 로 이 디렉토리를 보고 있어서,
    반쯤 쓰인 파일을 읽힐 수 있다(`spool.enqueue` 가 tmp→rename 을 쓰는 것과 같은 이유).
    """
    TRIGGER_DIR.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"work_id": work_id, "project": project, "ref": ref,
                       "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")},
                      ensure_ascii=False)
    final = TRIGGER_DIR / f"{work_id}.json"
    tmp = TRIGGER_DIR / f".{work_id}.{os.getpid()}.tmp"
    tmp.write_text(body + "\n", encoding="utf-8")
    os.replace(tmp, final)
    return final


def _read_triggers() -> list:
    """`(work_id, project, path)` 목록. 못 읽는 파일은 **지우지 않고** 사유만 찍는다."""
    out = []
    if not TRIGGER_DIR.is_dir():
        return out
    for f in sorted(TRIGGER_DIR.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            wid, proj = str(d.get("work_id") or ""), str(d.get("project") or "")
        except (OSError, ValueError) as e:                   # noqa: PERF203
            _log(f"[주의] 트리거를 못 읽었다 — {f.name}: {type(e).__name__}: {e}")
            continue
        if not (wid and proj):
            _log(f"[주의] 트리거에 work_id·project 가 없다 — {f.name}")
            continue
        out.append((wid, proj, f))
    return out


def drain(*, catchup: bool = False, api=None) -> dict:
    """트리거를 소비해 파견한다. `ax-dispatch.service` 의 본문.

    [중요] **파견 전에 트리거 파일을 지운다.** 남겨 두면 실패가 이어질 때 `ax-dispatch.path`
    가 같은 파일을 보고 무한 재기동한다 — 색인기 주석이 경고한 그 함정이고, 여기서는 **돈이
    나가는 자리**라 더 나쁘다. 지워도 상태는 안 잃는다: 무엇을 파견할지는 `should_dispatch`
    가 **큐를 읽어** 정하고, 놓친 것은 `ax-dispatch.timer` 의 `catchup` 이 되찾는다.

    [주의] `catchup` 은 **열린 work 전부**를 훑는다 — 멱등 가드(pending 있을 때만)가 유일한
    방어선이므로 그 가드를 약화시키면 안 된다.
    """
    from ..context_search.paths import resolve
    # [중요] **보류 중이면 그 사실을 먼저 찍는다** — 「아무것도 안 했다」와 「막혀 있다」는
    #    다른 상태이고, 그 둘을 구분 못 해서 이틀을 잃었다.
    held, why_hold = hold_active()
    if held:
        _log(f"[중요] {why_hold}")
    res = {"triggers": 0, "dispatched": 0, "skipped": 0, "errors": 0}
    seen: set = set()

    for wid, proj, f in _read_triggers():
        res["triggers"] += 1
        try:
            f.unlink()
        except OSError:
            pass
        seen.add((proj, wid))
        try:
            r = dispatch(resolve(proj), wid, api=api)
        except Exception as e:                               # noqa: BLE001
            res["errors"] += 1
            _log(f"[중요] {proj}/{wid} 파견 중 예외 — {type(e).__name__}: {e}")
            continue
        res["dispatched" if r.get("dispatched") else "skipped"] += 1

    if catchup:
        from ..projects.config import Registry
        from . import runner
        call = api or runner._api
        for name in Registry.load().names:
            try:
                works = call("GET", f"/api/v1/works?project={name}")
            except Exception as e:                           # noqa: BLE001
                res["errors"] += 1
                _log(f"[주의] {name}: 열린 work 조회 실패 — {type(e).__name__}: {e}")
                continue
            rows = works if isinstance(works, list) else []
            for w in rows:
                wid = str(w.get("work_id") or "")
                if not wid or (name, wid) in seen:
                    continue
                if str(w.get("merge_status") or "") not in ("in_progress", ""):
                    continue
                paths_ = resolve(name)
                try:
                    r = dispatch(paths_, wid, api=api)
                except Exception as e:                       # noqa: BLE001
                    res["errors"] += 1
                    _log(f"[중요] {name}/{wid} 파견 중 예외 — {type(e).__name__}: {e}")
                    continue
                res["dispatched" if r.get("dispatched") else "skipped"] += 1
                # [중요] **추론과 통합 사이에 낀 work 을 여기서 꺼낸다.** 파견은 pending 이
                #    있을 때만 시작하므로, 추론이 끝난 뒤 통합이 안 걸린 work 은 파견 경로로
                #    다시 안 잡힌다 — 그것을 되찾는 것이 따라잡기의 일이다.
                if not r.get("dispatched"):
                    need, why2 = needs_integration(paths_, wid, api=api)
                    if need:
                        # [중요] 통합하지 않는다 — `.33` 의 자리다. 여기서는 고지만 한다.
                        _log(f"{name}/{wid} 조각 전부 완료 — 요청자(.33) 처리 대기 ({why2})")
                        res.setdefault("recovered", 0)
                        res["recovered"] += 1

    # [중요] **한 줄은 반드시 남긴다** — 「아무것도 안 했다」와 「안 돌았다」는 다른 상태이고,
    #    그 둘을 구분 못 해서 2026-08-29~31 이틀을 잃었다(`#340` 노트).
    _log(f"드레인 끝 — 트리거 {res['triggers']}건 · 파견 {res['dispatched']}건 · "
         f"안 걸림 {res['skipped']}건 · 예외 {res['errors']}건"
         + (" · catchup" if catchup else ""))
    return res


def main(argv) -> int:
    """`python -m master.work.autodispatch <프로젝트> [work_id]`

    work_id 를 안 주면 그 프로젝트의 **열린 work 전부**를 훑는다 — 트리거를 놓쳤을 때의
    따라잡기다(`ax-indexer.timer` 가 같은 이유로 있다).
    """
    from ..context_search.paths import resolve
    from . import runner
    if argv and argv[0] in ("--resume", "resume"):
        # [중요] **사람이 이어가라고 말하는 자리.** 보류를 지우고 그 자리에서 한 번 민다.
        st = hold_state()
        if not st:
            print("[주의] 보류가 없다 — 막혀 있지 않다. 그냥 `--drain` 이면 된다")
        else:
            print(f"보류 해제 — state={st.get('state')} · until={st.get('until_str')} · "
                  f"work={st.get('work_id')}")
            clear_hold()
        proj = argv[1] if len(argv) > 1 else str(st.get("project") or "")
        wid = argv[2] if len(argv) > 2 else str(st.get("work_id") or "")
        if not proj:
            print("[중요] 프로젝트를 모른다 — `--resume <프로젝트> [work_id]`")
            return 2
        paths = resolve(proj)
        if wid:
            r = dispatch(paths, wid)
            if not r.get("dispatched"):
                # 파견할 것이 없으면 통합이 남았을 수 있다 — 회수 경로를 그 자리에서 본다.
                need, why = needs_integration(paths, wid)
                _log(f"{wid} " + ("조각 전부 완료 — 통합은 `.33` 에서 한다"
                                  if need else f"이어갈 것이 없다 — {why}"))
            return 0
        r = drain(catchup=True)
        return 1 if r["errors"] else 0
    if argv and argv[0] in ("--drain", "drain"):
        # `ax-dispatch.service` 가 부르는 자리. `--catchup` 은 타이머용.
        r = drain(catchup="--catchup" in argv[1:])
        return 1 if r["errors"] else 0
    if not argv:
        print(__doc__)
        return 2
    paths = resolve(argv[0])
    if len(argv) > 1:
        r = dispatch(paths, argv[1])
        return 0 if r.get("dispatched") else 1
    works = runner._api("GET", f"/api/v1/works?project={paths.name}")
    open_ids = [w["work_id"] for w in (works if isinstance(works, list) else [])
                if str(w.get("merge_status") or "") in ("in_progress", "")]
    if not open_ids:
        _log(f"{paths.name}: 열린 work 없음")
        return 0
    for wid in open_ids:
        dispatch(paths, wid)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
