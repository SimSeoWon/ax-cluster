"""워커 러너 — 마스터가 큐에서 집어 **워커의 Claude 에 밀어넣는다** (#21 후속).

## [중요] 워커에는 큐 토큰을 주지 않는다 — 마스터가 중개한다

    claim(마스터) → 매니페스트 파일 배달(scp) → ssh claude -p(워커) → submit(마스터)

실측 2026-08-09: 두 워커 모두 `8101/api/v1/health` 가 **401** 이고 AX MCP 등록은 **0건**이다.
`ax-work` 스킬은 *"MCP 는 등록에 헤더가 박혀 있다"* 를 전제했지만 **사실이 아니었다.** 고르는
길은 둘이었고 — 워커에 토큰을 주거나, 마스터가 중개하거나 — 후자를 택했다. 근거는 넷이고,
**하나라도 뒤집히면 이 파일을 다시 열어야 한다**:

1. §5.5.4 가 *"데몬을 두지 않는다 — SSH 가 열려 있으니 마스터가 밀어넣는다"* 로 이미 정했다.
   큐도 같은 원칙을 받는 것뿐이다.
2. 토큰이 마스터를 떠나지 않는다. 세 서비스는 LAN-only + 베어러인데, 두 대에 더 복사하면
   노출면만 늘고 얻는 게 없다.
3. [중요] **리스 하트비트에는 오래 사는 호출자가 있어야 한다.** 리스 1200초, 재확보 루프 30초
   주기다(`task_queue/server.py:81`). SSH 를 기다리는 마스터는 이미 살아 있다. 반대로 워커의
   Claude 에게 *"작업 도중 하트비트를 잊지 마라"* 를 맡기면 **잊는다** — 잊는 순간 리스가 풀려
   다른 워커가 **같은 태스크를 집는다.**
4. 워커가 실제로 필요한 자격증명은 **git 뿐**이고, 그건 Gitea SSH 키로 이미 된다.

## [중요] 결과는 fail-closed 로 읽는다

워커 stdout 의 마지막 비어 있지 않은 줄이 정확히 `RESULT: DONE` 또는 `RESULT: BLOCKED` 여야
한다. 없거나·깨졌거나·타임아웃이면 **BLOCKED** 다 — 층2 판정과 같은 계약(§9.4.4)이고, 같은
이유다. LLM 의 산문을 성공으로 읽어주는 순간 **큐에 거짓 완료가 쌓이고**, 그 거짓은 다음
태스크의 `depends_on` 을 풀어 버린다.

## [중요] 지시는 ASCII, 내용은 파일로

명령줄로 긴 한글 프롬프트를 밀지 않는다. 두 번 물렸다 — 윈도우 콘솔 cp949 로 **글자가 깨지고**,
stdin 으로 18KB 를 밀었더니 **닫히지 않아 멈췄다**(리포트 11). 그래서 실체는 UTF-8 파일로
`scp` 배달하고(`bundle._remote_write` 가 되읽어 sha256 대조한다), 명령줄에는 **ASCII 한 줄**만
남긴다.

## [주의] 승인은 열려 있다 (사용자 결정 2026-08-09)

*"승인은 뭐든 할 수 있어도 될 것 같아, 깃이니까 언두 해도 되고"* 에 따라
`--dangerously-skip-permissions` 로 파견한다. [중요] **다만 git 이 되돌려 주는 것은 추적 파일까지**
다 — 미추적 파일·저장소 밖·시스템 변경은 git 밖이다. 실질 방어선은 `ax-work` 스킬의 금지
목록(`git clean`·`reset --hard`·브랜치 삭제)이지 승인 프롬프트가 아니다.
"""
from __future__ import annotations

import json
import os
import re
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .. import auth
from ..client import bundle
from ..projects.config import ROLE_WORKER

# 리스 1200초 / 재확보 30초 주기 → 240초면 네 번 놓쳐도 살아남는다
LEASE_SEC = 1200
HEARTBEAT_SEC = 240
DEFAULT_TIMEOUT = 3600          # claude -p 한 번의 상한. 넘으면 BLOCKED (fail-closed)

DONE = "DONE"
BLOCKED = "BLOCKED"

# [중요] **비대칭은 의도다.** 뒤에 사유가 붙은 `RESULT: BLOCKED — …` 는 받아 주고,
# `RESULT: DONE — …` 은 받지 않는다. 관대함을 **안전한 판정 쪽으로만** 연다.
# 실측 2026-08-09: 워커가 사유를 같은 줄에 붙여 쓰는 바람에 "마커 없음" 으로 처리됐고,
# 결론(BLOCKED)은 맞았지만 **진짜 사유(워킹트리 더러움)가 묻혔다.**
_RESULT_STRICT = re.compile(r"^RESULT:\s*(DONE|BLOCKED)\s*$")
_RESULT_LOOSE = re.compile(r"^RESULT:\s*BLOCKED\b(.*)$")
_ATTEMPT = re.compile(r"^ATTEMPT:\s*(\S+)\s*$")
_HEAD = re.compile(r"^HEAD:\s*([0-9a-fA-F]{7,40})\s*$")

MANIFEST_REL = "manifest.md"    # <checkout>/.ax/work/<task_id>/manifest.md

# [중요] ASCII 만. 위 § 참조 — 한글을 명령줄에 실으면 워커 콘솔에서 깨진다.
INSTRUCTION = (
    "Follow the ax-work skill. Read ./{work}/{task}/manifest.md and do exactly what it says. "
    "Judge from the source files in this checkout, not from memory. "
    "The last three non-empty lines of your output must be exactly: "
    "ATTEMPT: <branch you pushed> / HEAD: <commit sha> / RESULT: DONE "
    "(use RESULT: BLOCKED if you could not finish, and say why above it)."
)


class DispatchError(RuntimeError):
    """파견 자체가 불가능하다. [중요] **태스크를 집은 채로 죽지 않게** 호출자가 반납해야 한다."""


@dataclass
class Outcome:
    """워커 한 번의 결과. [중요] **모르는 값을 성공으로 접지 않는다.**"""
    status: str = BLOCKED
    branch: str = ""
    head: str = ""
    reason: str = ""
    tail: str = ""
    # [중요] 실측 계측 — `--output-format json` 이 주는 것. 비어 있으면 **모른다**는 뜻이다.
    usage: dict = field(default_factory=dict)

    @property
    def cost_usd(self) -> float:
        return float(self.usage.get("total_cost_usd") or 0.0)

    @property
    def tokens(self) -> tuple:
        """`(입력, 출력, 캐시생성, 캐시읽기)`. [중요] 캐시가 비용을 지배한다 — 나눠서 본다."""
        u = self.usage.get("usage") or {}
        return (int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0),
                int(u.get("cache_creation_input_tokens") or 0),
                int(u.get("cache_read_input_tokens") or 0))

    @property
    def ok(self) -> bool:
        return self.status == DONE

    @property
    def submittable(self) -> bool:
        """큐에 `submit` 할 수 있나. [중요] 브랜치·커밋이 없으면 성공이라도 제출할 게 없다."""
        return self.ok and bool(self.branch) and bool(self.head)

    @property
    def summary(self) -> str:
        if self.submittable:
            return f"[완료] {self.branch} @ {self.head[:8]}"
        s = f"[중요] {self.status}"
        if self.ok and not self.submittable:
            s = "[중요] DONE 이라 했지만 ATTEMPT/HEAD 가 없다"
        return s + (f" — {self.reason}" if self.reason else "")


def _unwrap(stdout: str) -> tuple:
    """`(본문, 계측)`. `--output-format json` 이면 `result` 를 꺼내고 나머지를 계측으로 쥔다.

    [중요] **JSON 이 아니어도 실패로 보지 않는다.** 계측이 없는 것과 작업이 실패한 것은 다르다 —
    판정은 어느 쪽이든 **마커**로 읽는다.
    """
    t = (stdout or "").strip()
    if not t.startswith("{"):
        return stdout, {}
    try:
        d = json.loads(t)
    except ValueError:
        return stdout, {}
    if not isinstance(d, dict) or "result" not in d:
        return stdout, {}
    return str(d.get("result") or ""), {k: v for k, v in d.items() if k != "result"}


def parse_result(stdout: str) -> Outcome:
    """워커 출력에서 판정을 읽는다. [중요] **마커가 없으면 BLOCKED.**

    산문에서 "성공했습니다" 를 찾아내지 않는다 — 그 관대함이 층2 의 `syntax_check` 를
    fail-open 으로 만들었고, 이 포팅은 그걸 뒤집기로 이미 정했다(settled).
    """
    body, meta = _unwrap(stdout)
    lines = [ln.strip() for ln in (body or "").replace("\r", "").split("\n")]
    ne = [ln for ln in lines if ln]
    out = Outcome(tail="\n".join(ne[-12:]), usage=meta)
    if not ne:
        out.reason = "출력이 비었다"
        return out

    m = _RESULT_STRICT.match(ne[-1])
    if m:
        out.status = m.group(1)
    else:
        loose = _RESULT_LOOSE.match(ne[-1])
        if loose:
            # BLOCKED 는 이미 안전한 쪽이다 — 사유를 살려 준다
            out.status = BLOCKED
            out.reason = loose.group(1).strip(" —-·:") or "워커가 사유를 적지 않았다"
            return out
        # [중요] 마지막 줄이어야 한다. 중간에 있으면 그 뒤에 무슨 일이 더 있었다는 뜻이다.
        out.reason = f"마지막 줄이 RESULT: 가 아니다 — {ne[-1][:70]!r}"
        return out

    for ln in reversed(ne):
        if not out.branch:
            a = _ATTEMPT.match(ln)
            if a:
                out.branch = a.group(1)
        if not out.head:
            h = _HEAD.match(ln)
            if h:
                out.head = h.group(1)
    if out.status == DONE and not (out.branch and out.head):
        out.reason = "DONE 인데 ATTEMPT/HEAD 를 안 적었다 — 제출할 근거가 없다"
    return out


@dataclass
class Pick:
    """워커 선택 결과. [중요] **왜 떨어졌는지까지 들고 나온다** — 큐가 조용히 굶는 걸 막는다."""
    chosen: object = None
    rejected: list = field(default_factory=list)     # [(host, 사유)]

    @property
    def summary(self) -> str:
        if self.chosen is not None:
            return f"[완료] {self.chosen.host}"
        if not self.rejected:
            return "[중요] 후보 자체가 없다 (레지스트리에 워커가 없나)"
        return "[중요] 파견할 워커가 없다 — " + "; ".join(f"{h}: {r}" for h, r in self.rejected)


def cleanliness(project: str):
    """`host → Cleanliness` 판정기. 없으면 `None` — 호출자가 "확인 못 함" 으로 다룬다."""
    from ..projects.config import Registry
    from ..projects.workshop_check import check_workshop
    ws = Registry.load().config_of(project).workshops
    shops = {w.host: w for w in (ws.values() if isinstance(ws, dict) else ws)}

    def check(f):
        shop = shops.get(f.host)
        return check_workshop(shop) if shop is not None else None
    return check


def pick_worker(facts: list, requires=(), *, clean=None) -> Pick:
    """능력이 맞고 실제로 준비된 워커 하나. **읽기 전용 판정.**

    [중요] `role` 로 먼저 거른다 — `.33` 은 SSH 가 닿지만 `requester` 이고, 사람이 편집 중인
    작업 트리에 파견하면 안 된다(`driven` ≠ `role`).

    [중요] `clean` 을 주면 **워킹트리까지 보고 고른다.** 실측 2026-08-09: `.2` 의 추적 파일이
    더러운 줄 모르고 태스크를 집었고, 워커가 (옳게) 거부해 **집었다 반납하는 왕복**만 남았다.
    거부는 워커의 마지막 방어선이지 **선택 기준**이 아니다 — 못 돌릴 워커에게 주지 않는다.
    """
    need = set(requires or ())
    p = Pick()
    for f in facts:
        if f.role != ROLE_WORKER:
            p.rejected.append((f.host, f"역할이 {f.role} 다 — 파견 대상 아님"))
            continue
        if not f.checkout_ok:
            p.rejected.append((f.host, "체크아웃이 없다"))
            continue
        if not f.claude:
            p.rejected.append((f.host, "claude 가 없다"))
            continue
        missing = need - set(f.capabilities)
        if missing:
            p.rejected.append((f.host, f"능력 부족: {sorted(missing)}"))
            continue
        if clean is not None and p.chosen is None:
            c = clean(f)
            if c is None or not getattr(c, "ok", False):
                p.rejected.append((f.host, "워킹트리 — " +
                                   (getattr(c, "reason", "") or "확인하지 못했다")))
                continue
        if p.chosen is None:
            p.chosen = f
        else:
            p.rejected.append((f.host, "다른 워커를 먼저 골랐다"))
    return p


def deliver_manifest(facts, task_id: str, text: str, *, writer=None) -> str:
    """매니페스트를 워커 체크아웃 안에 놓는다. [중요] **되읽어 sha256 대조까지 `bundle` 이 한다.**"""
    rel = f"{bundle.WORK_REL}/{task_id}/{MANIFEST_REL}"
    w = writer or bundle._remote_write
    try:
        return w(facts, rel, text, base="checkout")
    except bundle.BundleError as e:
        raise DispatchError(f"{facts.host}: 매니페스트를 배달하지 못했다 — {e}") from e


def worker_command(facts, task_id: str) -> str:
    """워커에서 실제로 도는 한 줄. [중요] **경로는 레지스트리에서 온 값**(`facts.path`)이다."""
    instr = INSTRUCTION.format(work=bundle.WORK_REL, task=task_id)
    cd = f'cd /d "{facts.path}"' if facts.windows else f'cd "{facts.path}"'
    # [중요] `--output-format json` — 판정 마커는 `result` 안에 들어오고, 그 대신
    # **토큰·비용·턴 수**를 함께 받는다. 계측 없이 "분산이 이득인가" 를 논할 수 없다.
    return (f'{cd} && claude -p --output-format json '
            f'--dangerously-skip-permissions "{instr}"')


def run_worker(facts, task_id: str, *, runner=None, timeout: int = DEFAULT_TIMEOUT) -> tuple:
    """워커에서 Claude 를 한 번 돌린다. `(rc, stdout)`. **예외를 던지지 않는다.**"""
    cmd = worker_command(facts, task_id)
    if runner is not None:
        return runner(facts, cmd, timeout)
    return bundle._ssh(facts.host, facts.user, cmd, timeout=timeout)


class _Beater:
    """SSH 가 도는 동안 리스를 살려 둔다. [중요] **실패해도 작업을 죽이지 않는다** — 하트비트
    한 번 놓친 것과 워커가 죽은 것은 다르고, 후자만 재확보 루프가 판정할 일이다."""

    def __init__(self, beat, interval: int = HEARTBEAT_SEC):
        self._beat, self._interval = beat, interval
        self._stop = threading.Event()
        self._t = None
        self.beats = 0
        self.errors = []

    def _loop(self):
        while not self._stop.wait(self._interval):
            try:
                self._beat()
                self.beats += 1
            except Exception as e:                       # noqa: BLE001
                self.errors.append(f"{type(e).__name__}: {e}")

    def __enter__(self):
        if self._beat is not None:
            self._t = threading.Thread(target=self._loop, daemon=True)
            self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._t is not None:
            self._t.join(timeout=5)
        return False


def run_task(facts, task_id: str, manifest_text: str, *, beat=None, runner=None,
             writer=None, deliver=None, timeout: int = DEFAULT_TIMEOUT) -> Outcome:
    """파견 한 건: 배달 → 실행(하트비트 유지) → 판정.

    [중요] **큐에 제출하지 않는다.** 제출은 호출자(마스터)의 일이다 — 이 함수는 *워커가 무엇을
    했는가* 만 돌려준다. 판정과 제출을 한 곳에 섞으면 실패 경로에서 리스를 반납하지 못한다.
    """
    if deliver is not None:
        # git-carried (#185 판정 2026-08-17) — scp 자리의 대체. 주입이 없으면 기존 scp.
        deliver(facts, task_id, manifest_text)
    else:
        deliver_manifest(facts, task_id, manifest_text, writer=writer)
    with _Beater(beat) as b:
        rc, out = run_worker(facts, task_id, runner=runner, timeout=timeout)
    res = parse_result(out)
    if rc != 0 and not res.ok:
        res.reason = (res.reason + " · " if res.reason else "") + f"ssh rc={rc}"
    elif rc != 0:
        # [중요] 워커는 DONE 이라는데 껍데기는 실패했다 — 성공으로 접지 않는다
        res.status, res.reason = BLOCKED, f"RESULT: DONE 이지만 ssh rc={rc} 다"
    if b.errors:
        res.reason = (res.reason + " · " if res.reason else "") + f"하트비트 실패 {len(b.errors)}회"
    return res


# ── 큐 배선 — [중요] 집었으면 반드시 놓는다 ──────────────────────────────────────
#
# [중요] claim 과 submit 사이에서 예외가 나면 태스크는 **리스가 만료될 때까지(1200초) 붙잡힌
# 채로 남는다.** 그동안 다른 워커는 그 태스크를 못 집고, 사람은 "왜 아무것도 안 도나" 를
# 본다. 그래서 아래 `run_once` 는 claim 이후 **전 구간을 try/finally 로 감싸고**, 어떤 경로로
# 빠져나가든 submit 또는 submit-fail 중 하나를 반드시 부른다.

QUEUE_URL = os.environ.get("AX_QUEUE_URL", "http://127.0.0.1:8101")
HTTP_TIMEOUT = 20


class QueueError(RuntimeError):
    """큐와 말이 통하지 않는다."""


def _api(method: str, path: str, payload=None, *, timeout: int = HTTP_TIMEOUT):
    """큐 호출 한 번. [중요] **토큰은 마스터에만 있다** — 이 함수가 워커로 건너가면 안 된다."""
    url = QUEUE_URL.rstrip("/") + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in auth.auth_headers().items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace").strip()
            if r.status == 204 or not body:
                return None
            return json.loads(body)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:200]
        if e.code == 204:                       # 집을 게 없다 — 오류가 아니다
            return None
        raise QueueError(f"{method} {path} → {e.code} {detail}") from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise QueueError(f"{method} {path} → {type(e).__name__}: {e}") from e


def claim(worker_id: str, capabilities, *, api=_api):
    """태스크 하나를 집는다. 없으면 `None`. [중요] **능력은 실측값**(`facts.capabilities`)이다."""
    return api("POST", "/api/v1/tasks/claim",
               {"worker_id": worker_id, "capabilities": list(capabilities)})


def heartbeat(task_id: str, worker_id: str, *, api=_api):
    return api("POST", f"/api/v1/tasks/{task_id}/heartbeat", {"worker_id": worker_id})


def submit(task_id: str, out: Outcome, *, epoch=None, api=_api):
    """성공 제출. [중요] `submittable` 이 아닌 것을 여기로 보내지 않는다 — 근거가 없다."""
    if not out.submittable:
        raise QueueError(f"제출 불가한 결과를 submit 하려 했다 — {out.summary}")
    return api("POST", f"/api/v1/tasks/{task_id}/submit", {
        "branch": out.branch, "head_commit": out.head,
        "self_check": {"worker_report": out.tail[-2000:], "gates": "worker-side only"},
        "epoch": epoch,
    })


def submit_fail(task_id: str, reason: str, detail: str = "", *, api=_api):
    return api("POST", f"/api/v1/tasks/{task_id}/submit-fail",
               {"reason": reason[:200], "detail": detail[-2000:]})


def _manifest_for(paths, task_id: str) -> str:
    """등록 때 마스터가 써 둔 매니페스트. [중요] **없으면 파견하지 않는다.**

    빈 지시서로 보내면 워커의 Claude 가 *스스로 할 일을 지어낸다* — 그게 가장 비싼 실패다.
    """
    from . import manifest as manifest_mod
    body = manifest_mod.read(paths, task_id)
    if not body or not body.strip():
        raise DispatchError(
            f"매니페스트가 없다 ({manifest_mod.manifest_path(paths, task_id)}). 등록 단계에서 "
            f"조립되지 않았다 — 빈 지시서로 파견하면 워커가 할 일을 지어낸다")
    return body


BASE_HEADING = "## 기준 (커밋·브랜치)"


def refresh_base(body: str, paths, task_id: str, *, resolver=None) -> str:
    """[중요] 기준 절을 **파견 시점에 다시 푼다.**

    등록 시점에 푼 값은 **정상 흐름에서 반드시 낡는다** — durable `task/<id>` 는 설계상
    *등록 이후에* 요청자가 만들기 때문이다(§2.1: 마스터는 push 할 수 없다). 실측 2026-08-09:
    브랜치를 만든 뒤에도 매니페스트는 *"원격에 아직 없다 — 요청자가 먼저 만들어야 한다"* 로
    남아 있었다. 그대로 보내면 워커가 **있는 브랜치를 없다고 믿고 BLOCKED** 를 낸다.

    풀지 못하면 **옛 절을 지우지 않고 경고만 덧붙인다** — 모르는 것을 지어내지 않는다.
    """
    from . import twin_base
    try:
        base = (resolver or twin_base.resolve)(paths, task_id)
        fresh = "\n".join([BASE_HEADING, ""] + twin_base.manifest_section(base))
    except Exception as e:                                   # noqa: BLE001
        return body.replace(
            BASE_HEADING,
            f"{BASE_HEADING}\n\n[주의] 파견 시점에 기준을 다시 풀지 못했다 ({e}) — 아래는 "
            f"**등록 시점의 값**이라 낡았을 수 있다. `git ls-remote` 로 직접 확인할 것.", 1)

    if BASE_HEADING not in body:
        return fresh + "\n\n" + body
    head, _, rest = body.partition(BASE_HEADING)
    tail = ""
    idx = rest.find("\n## ")
    if idx >= 0:
        tail = rest[idx:]
    return head + fresh + tail


AUTO = "auto"          # [중요] 기본은 **재는 것**이다. 끄려면 호출자가 명시적으로 None 을 준다.


def run_once(paths, *, facts=None, project: str = "", api=_api, runner=None, writer=None,
             clean=AUTO, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """큐에서 하나 집어 워커에서 돌리고 결과를 제출한다. **한 건.**

    반환은 사람이 읽을 요약 dict — `{"picked":…, "task":…, "outcome":…, "submitted":…}`.
    집을 게 없으면 `{"task": None}`.
    """
    if facts is None:
        facts = [bundle.probe(h, u, p, d, r)
                 for h, u, p, d, r in bundle.workshops(project or paths.name)]
    if clean == AUTO:
        clean = cleanliness(project or paths.name)
    pick = pick_worker(facts, clean=clean)
    if pick.chosen is None:
        return {"picked": pick.summary, "task": None,
                "note": "[중요] 워커가 없어 claim 조차 하지 않았다 — 집어놓고 못 돌리는 게 더 나쁘다"}

    f = pick.chosen
    worker_id = f.host
    task = claim(worker_id, f.capabilities, api=api)
    if not task:
        return {"picked": pick.summary, "task": None, "note": "집을 태스크가 없다"}

    task_id = str(task.get("task_id") or task.get("id") or "")
    epoch = task.get("epoch")
    if not task_id:
        raise QueueError(f"claim 응답에 task_id 가 없다 — {str(task)[:160]}")

    res = {"picked": pick.summary, "task": task_id, "worker": f.host, "epoch": epoch}
    try:
        body = refresh_base(_manifest_for(paths, task_id), paths, task_id)
        deliver = None
        if writer is None:
            # [중요] 실전 배달 = git-carried (#185 판정 2026-08-17). writer 주입(테스트)은
            #    scp 자리를 그대로 잰다.
            from . import carry
            _d = carry.deliverer(paths)
            deliver = lambda f_, t_, txt: _d(f_, t_, txt)  # noqa: E731
        out = run_task(f, task_id, body,
                       beat=lambda: heartbeat(task_id, worker_id, api=api),
                       runner=runner, writer=writer, deliver=deliver, timeout=timeout)
        res["outcome"] = out.summary
        res["tail"] = out.tail
        if out.submittable:
            submit(task_id, out, epoch=epoch, api=api)
            res["submitted"] = "submit"
        else:
            submit_fail(task_id, out.status, out.reason + "\n" + out.tail, api=api)
            res["submitted"] = "submit-fail"
    except Exception as e:                                   # noqa: BLE001
        # [중요] 집은 태스크를 붙잡은 채 죽지 않는다. 반납이 실패해도 사유를 남긴다.
        res["error"] = f"{type(e).__name__}: {e}"
        try:
            submit_fail(task_id, "파견 실패", res["error"], api=api)
            res["submitted"] = "submit-fail(예외)"
        except Exception as e2:                              # noqa: BLE001
            res["submitted"] = f"[중요] 반납 실패 — 리스 만료까지 {LEASE_SEC}s 붙잡힌다 ({e2})"
        raise
    return res


# ── CLI ──────────────────────────────────────────────────────────────────────
#
#   python -m master.work.runner probe [프로젝트]     누가 파견 가능한가 (큐를 건드리지 않는다)
#   python -m master.work.runner once  [프로젝트]     한 건 집어 돌린다
#   python -m master.work.runner loop  [프로젝트] [N] 빌 때까지 최대 N건 (기본 5)
#
# [중요] 데몬으로 만들지 않는다(§5.5.4). 상주가 필요하면 systemd timer 로 `once` 를 부른다 —
# 큐가 비면 즉시 끝나므로 빈 호출이 싸다.

def _summary(r: dict) -> str:
    if not r.get("task"):
        return f"  {r.get('note', '집을 게 없다')}"
    return (f"  태스크 {r['task']} → {r.get('worker', '?')}\n"
            f"  결과 {r.get('outcome', '?')}\n"
            f"  큐   {r.get('submitted', '?')}")


def main(argv) -> int:
    from ..context_search.paths import resolve
    cmd = (argv[0] if argv else "probe").strip()
    project = argv[1] if len(argv) > 1 else ""
    paths = resolve(project)
    facts = [bundle.probe(h, u, p, d, r) for h, u, p, d, r in bundle.workshops(paths.name)]

    if cmd == "probe":
        pick = pick_worker(facts, clean=cleanliness(paths.name))
        print(f"프로젝트 {paths.name}")
        for f in facts:
            print("  " + f.summary)
        print("선택: " + pick.summary)
        return 0
    if cmd == "once":
        print(_summary(run_once(paths, facts=facts)))
        return 0
    if cmd == "loop":
        n = int(argv[2]) if len(argv) > 2 else 5
        for i in range(n):
            r = run_once(paths, facts=facts)
            print(f"[{i+1}/{n}]")
            print(_summary(r))
            if not r.get("task"):
                break
        return 0
    print(__doc__.split("## ")[0])
    print("  probe | once | loop")
    return 2


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
