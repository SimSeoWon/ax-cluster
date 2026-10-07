"""워커 러너 — 마스터가 큐에서 집어 **워커의 Claude 에 밀어넣는다** (#21 후속).

## [중요] 워커에는 큐 토큰을 주지 않는다 — 마스터가 중개한다

    claim(마스터) → ssh claude -p(워커) → submit(마스터)
    [중요] **배달 단계가 없다** (2026-09-02) — 지시서는 배정된 브랜치의 골조 주석이고
    git 이 나른다. 매니페스트 파일과 그 scp/carry 배선은 걷었다.

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

# [중요] ASCII 만. 위 § 참조 — 한글을 명령줄에 실으면 워커 콘솔에서 깨진다.
# 🔴 정본 ⑸ (사용자 확정 2026-09-02) — **지시서는 파일이 아니라 골조 주석이다.**
#    매니페스트 파일은 걷었다(2026-09-02): 컨텍스트·작업 지시는 배정된 브랜치의 `.h`/`.cpp`
#    헤더 주석(`[DOC]`·`[PSEUDO]`)에 실려 있고, git 이 그것을 나른다.
# [중요] **git 은 워커의 LLM 이 만지지 않는다** — checkout·commit·push 는 `wcommit` 이
#    결정적으로 한다(원전도 데몬의 `git_ops.py` 가 했다). 그래서 이 지시서는 push 를
#    요구하지 않고 `ATTEMPT`/`HEAD` 도 요구하지 않는다.
INSTRUCTION = (
    "Follow the ax-work skill. You are on the assigned branch already. "
    "This message is dispatched work from the AX master, not a human chat: the plan was already approved when the task was registered. "
    "Do not ask for approval, do not propose a plan for review, do not wait for confirmation - implement the bodies now. "
    "Read the [DOC] and [PSEUDO] comments in these files and write their bodies: {files}. "
    "Judge from the source files in this checkout, not from memory. "
    "Do not run any git command. Do not commit or push. "
    "Do not run UE5 builds, UnrealBuildTool, UnrealEditor or automation tests, "
    "and for Python files do not start servers, run the program or run tests - "
    "verification is done later by the requester, not on this worker. "
    "The last non-empty line of your output must be exactly RESULT: DONE "
    "(use RESULT: BLOCKED if you could not finish, and say why above it)."
)

# 🔴 **워커는 UE5 빌드를 돌리지 않는다** (실측 2026-09-13 · 원전 대조).
# 🔴 `#695` P4 — **Python 조각도 같은 원칙이다**: 서버 기동·프로그램 실행·테스트 금지를
#    같은 문장에 넣었다(언어별로 두 벌을 두면 `.2` 세션 1 사본도 두 벌이 된다). Kimodo 는
#    WebUI 서버를 띄우는 프로젝트라 금지가 없으면 워커가 「확인」하러 서버를 띄운다.
#
# [중요] 원전 워커는 빌드하지 않는다 — `worker/` 에 `Build.bat` 이 없고 조각 검증은 정적 검사다.
#    빌드는 마스터 게이트와 `.33` 의 ⑺ 통합에서 한 번이다. 그런데 `.2` 의 codex 지휘자가 본문을
#    채운 직후 **스스로** `Build.bat NSEditor …` 를 돌렸고, 샌드박스 안에서 UnrealBuildTool 이
#    시작하자마자 두 번 죽어(`0xe0434352`) 오류 창이 프로세스를 붙잡았다 — 사람이 창을 닫기까지
#    7분 · 입력 113만 토큰(`.43` 은 19만). 명시 지시는 없었고, 배달 블록의 「할 수 있는 것: UE5
#    C++ 빌드」와 스킬의 「너는 검증한다」가 그렇게 읽혔다.
# [주의] 지시문으로 막아도 **실제로 안 돌렸는지는 따로 잰다** — `build_attempts` 가 그 로그다.
# [중요] **실행 모양만** 표식으로 쓴다 — `UnrealBuildTool` 낱말만으로는 오탐이다. 실측 출력에서
#    `…\UnrealBuildTool\Log.txt` 를 **읽는** 명령과 `Get-Process -match 'UnrealBuildTool'` 가
#    같이 걸렸다. 실제 빌드 실행은 `Build.bat` 이었다.
_BUILD_MARKS = ("Build.bat", "RunUAT", "UnrealEditor-Cmd", "UnrealBuildTool.exe",
                "UnrealBuildTool.dll", "UnrealEditor.exe")


def build_attempts(stdout: str) -> list:
    """지휘자 출력에서 **실제로 실행된 UE5 빌드·에디터 명령**을 뽑는다. 없으면 빈 목록.

    [중요] **명령 실행 이벤트만 본다**(codex JSONL 의 `item.type == "command_execution"`) — 지휘자가
    말로 *"UnrealBuildTool 최종 문구까지 확인하겠다"* 고 쓴 것까지 세면 오탐이다(실측 문구).
    [주의] 같은 명령이 `item.started`(in_progress)와 `item.completed` 로 두 번 온다 — **명령당 한 줄**,
    마지막 상태로 적는다. 판정을 바꾸지 않는다 — 기록용이다. 예외를 던지지 않는다.
    """
    found: dict = {}
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{") or not any(m in line for m in _BUILD_MARKS):
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        item = d.get("item") if isinstance(d, dict) else None
        if not isinstance(item, dict) or item.get("type") != "command_execution":
            continue
        cmd = " ".join(str(item.get("command") or "").split())
        if any(m in cmd for m in _BUILD_MARKS):
            found[cmd] = (item.get("status") or "?", item.get("exit_code"))
    return [f"{c[:200]} (상태 {s} · 종료 코드 {code})" for c, (s, code) in found.items()]


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
    def cost_known(self) -> bool:
        """비용을 **아는가**. 🔴 [중요] codex 는 usage 를 주면서 **비용만 안 준다** —
        `cost_usd` 의 0.0 을 「공짜」로 읽으면 안 된다. 집계는 이 값으로 미상을 따로 센다."""
        return bool(self.usage) and not self.usage.get("cost_unknown")

    @property
    def cost_usd(self) -> float:
        """[주의] 모르면 0.0 이다 — **아는 0 과 구분하려면 `cost_known` 을 함께 본다.**"""
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


def _codex(stdout: str):
    """codex 이벤트면 `(본문, 계측)`, 아니면 `None`. 형식 지식은 `usage` 모듈이 갖는다."""
    try:
        from .usage import parse_codex_jsonl
    except ImportError:                                          # noqa: BLE001
        return None
    return parse_codex_jsonl(stdout)


def _unwrap(stdout: str) -> tuple:
    """`(본문, 계측)`. `--output-format json` 이면 `result` 를 꺼내고 나머지를 계측으로 쥔다.

    [중요] **JSON 이 아니어도 실패로 보지 않는다.** 계측이 없는 것과 작업이 실패한 것은 다르다 —
    판정은 어느 쪽이든 **마커**로 읽는다.
    """
    t = (stdout or "").strip()
    if not t.startswith("{"):
        # [중요] `codex exec --json` 은 **JSONL 이벤트**라 첫 글자가 `{` 여도 단일 JSON 이
        #    아니고, 앞에 다른 줄이 붙기도 한다. 형식 지식은 `usage` 가 갖는다.
        got = _codex(stdout)
        return got if got is not None else (stdout, {})
    try:
        d = json.loads(t)
    except ValueError:
        got = _codex(stdout)
        return got if got is not None else (stdout, {})
    if not isinstance(d, dict) or "result" not in d:
        got = _codex(stdout)
        return got if got is not None else (stdout, {})
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

    [중요] 그 다음이 **`dispatch`** 다 (`#321`) — `role` 은 *자격*, `dispatch` 는 *지금 보낼까*.
    점검 중이거나 자원이 모자란 워커를 **잠시 빼는** 자리다. [주의] **좁히기 전용**이라
    요청자는 이 값으로 켜지지 않는다 — 위 role 검사가 먼저 걸러 낸다.

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
        if not f.dispatchable:
            p.rejected.append((f.host, f"dispatch={f.dispatch!r} — 파견에서 빠져 있다 (`#321`)"))
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


def agent_command(facts, path: str, instr: str, *, mode: str) -> str:
    """워커에서 도는 **지휘자** 한 줄 (`#385`). `mode` 는 `claude` 또는 `codex`.

    [중요] 지시문은 **갈래를 만들지 않는다** — 실측 2026-09-08(리포트 56 ⓒ): codex 가
    `.claude/skills/ax-work/SKILL.md` 를 찾아 읽고, config 가 없자 그 스킬의 한글 규칙을
    인용하며 `RESULT: BLOCKED` 로 멈췄다. 설정을 주니 층1 기준(`[PSEUDO]` 0 · `[DOC]` 보존 ·
    선언 동결)을 만족하며 구현했다. 같은 계약이 양쪽에 선다.
    [주의] 다만 **자동 로드가 아니라 탐색**이다 — 스킬 파일이 체크아웃에 있어야 한다.

    [완료] **권한 범위를 좁혔다** (실측 2026-09-08, `#385` 완료 조건 3). `.43` 에서 같은 작업을
    샌드박스만 바꿔 재봤다 — 판정은 브로커(8102) `curl` 의 rc 다:

        -s workspace-write                            파일 수정 O · 네트워크 **X** (curl rc=7)
        -s workspace-write + network_access=true      파일 수정 O · 네트워크 **O** (HTTP 401)
        -s danger-full-access                         둘 다 O — 그러나 **디스크 전체가 열린다**
        --dangerously-bypass-approvals-and-sandbox    둘 다 O — 샌드박스 자체가 없다

    🔴 [중요] **네트워크가 필요한 이유는 위임이다.** `ax-work` §0④ 가 *"대량 생성은
    `codex`→`agy`→로컬에 위임하고 너는 검증한다"* 고 지시하고, 로컬 위임은 브로커 HTTP 다.
    네트워크를 막으면 지휘자가 그 지시를 못 따른다. 그래서 **쓰기는 작업공간으로 묶고
    네트워크만 여는** 가운데 값을 쓴다 — 디스크 전체를 열 이유가 없다.
    [주의] `401` 은 서버가 죽은 것이 아니라 **인증 거절**이다(리포트 55 와 같은 판정).
    """
    cd = f'cd /d "{path}"' if facts.windows else f'cd "{path}"'
    if mode == "claude":
        # `--output-format json` — 판정 마커는 `result` 안에 들어오고, 그 대신
        # **토큰·비용·턴 수**를 함께 받는다. 계측 없이 "분산이 이득인가" 를 논할 수 없다.
        return (f'{cd} && claude -p --output-format json '
                f'--dangerously-skip-permissions "{instr}"')
    if mode == "codex":
        # [중요] `--json` 은 **JSONL 이벤트**다 — 단일 JSON 이 아니다. `usage.parse_codex_jsonl`
        #    이 본문과 토큰을 뽑는다. **비용은 codex 가 주지 않는다**(0 이 아니라 미상).
        # [주의] stdin 을 막지 않으면 *"Reading additional input from stdin"* 으로 멈춘다
        #    (실측 2026-09-07 — SSH 는 tty 가 아니다).
        nul = "NUL" if facts.windows else "/dev/null"
        # 🔴 [중요] **Windows 워커는 샌드박스를 `unelevated` 로 못 박는다** (실측 2026-09-09).
        #    `.2` 의 `~/.codex/config.toml` 은 **데스크톱 앱이 관리**해서 `[windows]
        #    sandbox = "elevated"` 가 들어 있는데, 그 러너는 세션 9(대화형 데스크톱)의 네이티브
        #    파이프를 쓴다. SSH 는 세션 0 이라 파이프가 안 닿고 **파일 쓰기 도구가 통째로 죽는다** —
        #    그런데 `codex exec` 는 **rc=0 으로 정상 종료한다**:
        #
        #        exec_command failed: CreateProcess { message: "Rejected(\"Failed to create
        #            unified exec process: timed out after 15000ms connecting runner pipe-in\")" }
        #        agent_message: "Unable to create probe.txt because the file-writing tools failed."
        #
        #    그래서 마스터에는 「골조가 그대로」로만 보이고 층1 이 `[PSEUDO]` 로 막는다. 라이브
        #    2026-09-09 에 `.2` 조각 2건이 이렇게 죽었다(재시도 3회 포함) — 같은 파견에서 `.43` 은
        #    2/2 성공했다. **모델이 아니라 실행 환경이 원인이다.**
        #
        #    [중요] **앱이 관리하는 파일을 고치지 않는다** — 앱이 언제든 다시 쓴다. 명령줄로
        #    못 박는다(`network_access` 를 같은 이유로 같은 자리에서 준다).
        #    [주의] 값은 `elevated`/`unelevated` **둘뿐**이고 다른 값이면 codex 가 **설정 로드
        #    단계에서 거절**한다(실측). Linux 도 같은 스키마로 파싱하지만 **쓰지는 않으므로**
        #    Windows 일 때만 싣는다 — 안 쓰는 손잡이를 보낼 이유가 없다.
        win = '-c windows.sandbox="unelevated" ' if facts.windows else ""
        # 🔴 [중요] **MCP 도구는 승인 없이는 안 불린다** (`#402`, 실측 2026-09-12).
        #    비대화형은 `approval: never` 라 호출이 이렇게 거절된다:
        #
        #        MCP tool call requires approval, but approval policy is never
        #
        #    🔴 **서버 단위 키는 안 먹는다** — `-c mcp_servers.<서버>.approval_mode` 로는 그대로
        #    거절당했고, `tools.<도구>.approval_mode` 만 통과했다(실측). 그래서 도구마다 하나씩
        #    싣는다. 목록은 `bundle.client_tool_names()` 가 **클라 MCP 의 `TOOLS` 에서** 읽는다 —
        #    여기 이름을 베껴 두면 도구가 늘 때 조용히 낡는다.
        #    [주의] **`--approve-for-me` 를 쓰지 않는다** — 승인 경로에 LLM 자동 검토가 들어간다.
        #    결정론 게이트가 LLM 판단보다 앞선다는 원칙과 어긋난다.
        #    [주의] 파일이 아니라 **명령줄**인 것은 바로 위 `windows.sandbox` 와 같은 근거다
        #    (*"앱이 관리하는 파일을 고치지 않는다"*) — `codex mcp add` 로는 쓸 수도 없다.
        appr = bundle.codex_approval_flags()
        return (f'{cd} && codex exec --json -s workspace-write '
                f'-c sandbox_workspace_write.network_access=true '
                f'{win}'
                f'{appr} '
                f'-C "{path}" "{instr}" < {nul}')
    raise ValueError(f"모르는 지휘자 모드: {mode!r}")


# ── 🔴 지휘자가 **자기 입으로 한 말**을 남긴다 (`#391`, 실측 2026-09-09·09-10) ───────
#
# [중요] **버린 것이 이틀을 태웠다.** `.2` 의 codex 가 파일 쓰기 도구 실패로 아무것도 못 썼는데,
# 자기 출력에는 정확히 말하고 있었다:
#
#     exec_command failed: CreateProcess { message: "Rejected(\"Failed to create unified exec
#         process: timed out after 15000ms connecting runner pipe-in\")" }
#     agent_message: "Unable to create probe.txt because the file-writing tools failed."
#
# 그런데 `run_worker` 의 `(rc, stdout)` 중 **stdout 은 rc==0 경로에서 아무 데도 안 남았고**,
# 마스터 기록에는 층1 의 `[PSEUDO]` 한 줄만 남았다 ⇒ **「codex 가 코드를 덜 썼다」로 보였다.**
# 그 오독으로 재시도 3회를 태웠고(환경 실패엔 재시도가 무의미하다), 원인은 사람이 워커에
# 직접 프로브를 쏘고 나서야 나왔다.
#
# 🔴 [중요] **이것은 `#385` 가 낸 회귀다 — 없던 기능이 아니라 잃은 기능이다** (사용자 지적
# 2026-09-10: *"기존 lane 모드에서는 근데 받았잖아"*). 레인 경로는 처음부터 시도마다 남긴다:
#
#     lanes.run_chain(..., logf=_log)  →  [lane] [완료] codex · 98초 · 파일 2 · 3,397자 · 토큰 …
#                                         [lane] [중요] agy — 429 session limit → 다음 레인
#
# 생성이 마스터에서 돌아 출력이 손안에 있었기 때문이다. 워커 지휘자 경로는 그 출력이 **SSH 저편**
# 이라 `(rc, stdout)` 으로 돌아오는데, `#385` 는 그것을 **받아만 놓고 아무 데도 안 썼다.**
# 새 경로를 낼 때 **옛 경로가 이미 하던 일**을 확인하지 않은 자리다.
#
# [중요] **추론하지 말고 남긴다.** 이 저장소가 이미 두 번 적은 규칙이다 — 사용자:
# *"이거 보려고 로그 심는거잖아"* (리포트 48 §7).
#
# [주의] 전문을 찍지 않는다 — codex 는 JSONL 이라 수백 줄이다. **사람이 판단에 쓰는 것만**:
# 지휘자의 마지막 말 · 실패한 명령 · 오류 줄. 형식 지식은 `usage` 가 갖는다(파서를 또 만들지
# 않는다 — `#385` 검증 ⓒ 와 같은 규칙).

_ERR_MARKS = ("ERROR", "error=", "Rejected(", "failed:", "Traceback", "Permission denied",
              "AX_CLAUDE_AUTH_FAILED",
              "Failed to authenticate: OAuth session expired and could not be refreshed")
AGENT_LOG_MAX = 3          # 오류 줄은 최대 3개까지만 (로그가 본문이 되면 안 읽힌다)
AGENT_TEXT_MAX = 400       # 지휘자의 말 한 토막


def agent_report(stdout: str, *, rc: int = 0) -> list:
    """지휘자 출력에서 **사람이 읽을 몇 줄**을 뽑는다. 못 뽑으면 그 사실을 말한다.

    [중요] **빈 목록을 돌려주지 않는다** — 침묵은 「문제 없음」으로 읽힌다. 뽑을 것이 없으면
    「출력이 없었다」고 말하는 것이 정보다(그 자체가 이상 신호다).
    """
    out = (stdout or "").strip()
    if not out:
        return [f"출력이 없다 (rc={rc}) — [주의] 지휘자가 아무 말도 안 했다"]

    lines: list = []
    text = ""
    event_errors = []
    event_error_lines = set()
    try:                                                     # codex JSONL
        from .usage import parse_codex_jsonl                 # noqa: PLC0415
        got = parse_codex_jsonl(out, error_lines=event_error_lines)
        if got:
            text = str(got[0] or "")
            event_errors = got[1].get("errors", [])
    except Exception:                                        # noqa: BLE001
        pass
    if not text:                                             # claude --output-format json
        try:
            import json as _json                             # noqa: PLC0415
            d = _json.loads(out)
            if isinstance(d, dict):
                text = str(d.get("result") or "")
        except Exception:                                    # noqa: BLE001
            pass
    if text:
        one = " ".join(text.split())[:AGENT_TEXT_MAX]
        lines.append(f"말: {one}")

    # [중요] 실패한 도구 호출과 오류 줄 — **원인은 거의 항상 여기 있다.**
    # 구조화 오류를 먼저 요약하며 일반 오류 줄과 합쳐 최대 3개만 보인다.
    # 판정 원문은 wcommit이 meta.errors에서 따로 보존한다 (#720).
    errs = [" ".join(e.split())[:AGENT_TEXT_MAX] for e in event_errors[:AGENT_LOG_MAX]]
    for ln in out.splitlines():
        ln = ln.strip()
        if not ln or ln in event_error_lines or len(errs) >= AGENT_LOG_MAX:
            continue
        if any(m in ln for m in _ERR_MARKS) or '"status":"failed"' in ln.replace(" ", ""):
            errs.append(" ".join(ln.split())[:AGENT_TEXT_MAX])
    lines.extend(f"오류: {e}" for e in errs)

    if not lines:
        lines.append(f"뽑을 것이 없다 (rc={rc} · {len(out)}자) — 원문은 이 로그에 없다")
    return lines


def worker_command(facts, task_id: str, files=(), *, mode: str = "claude") -> str:
    """워커에서 실제로 도는 한 줄. [중요] **경로는 레지스트리에서 온 값**(`facts.path`)이다.

    [중요] `files` 는 **판정에 쓰는 그 목록**이다 (`infer_command` 와 같은 계약) — 지시와
    판정이 갈라지지 않게 하나만 돈다. 비면 지시문에 `(none given)` 이 박혀 워커가 스스로
    고르려 들므로 호출부가 막는다.
    """
    shown = ", ".join(str(f) for f in (files or [])) or "(none given)"
    instr = INSTRUCTION.format(files=shown)
    return agent_command(facts, facts.path, instr, mode=mode)


def uses_session1(facts, mode: str) -> bool:
    """이 파견이 **세션 1 경유**여야 하나 (`#401`).

    🔴 [중요] **Windows + codex 조합 하나다.** SSH 는 세션 0 이고 거기서는 codex 의 제한 토큰
    샌드박스 자식이 `0xC0000142` 로 죽는다 — 실측 2026-09-12 에 조각 2건이 `ax-work` SKILL.md
    조차 못 읽고 죽었다. `/IT` 로 등록된 작업을 `schtasks /run` 으로 부르면 스케줄러가
    프로세스를 **세션 1** 에 만들고 거기서는 산다.
    [주의] 리눅스는 이 문제가 **없다**(`.43` 은 SSH 로 4조각을 완주했다) · `claude` 모드도
    이 경로를 안 탄다(셸 도구를 그렇게 쓰지 않는다). **좁게 건다.**
    """
    return bool(getattr(facts, "windows", False)) and mode == "codex"


def run_worker(facts, task_id: str, *, files=(), runner=None, mode: str = "claude",
               timeout: int = DEFAULT_TIMEOUT) -> tuple:
    """워커에서 **지휘자**를 한 번 돌린다. `(rc, stdout)`. **예외를 던지지 않는다.**

    [중요] Windows+codex 는 **세션 1 경유**다(`uses_session1`) — 전송만 다르고 판정·커밋
    흐름은 그대로다.
    """
    if runner is None and uses_session1(facts, mode):
        return run_worker_session1(facts, task_id, files=files, timeout=timeout)
    cmd = worker_command(facts, task_id, files, mode=mode)
    if runner is not None:
        return runner(facts, cmd, timeout)
    if mode == "claude":
        from .conductor_auth import check_claude_auth, invalidate_claude_auth
        from .revise import authentication_failure
        checked = check_claude_auth(facts)
        if not checked["ok"]:
            return 1, f"AX_CLAUDE_AUTH_FAILED: {checked['reason']}\nRESULT: BLOCKED"
        # bundle._ssh 회수 대상은 stdout뿐이다. Claude의 인증 stderr도 회수한다.
        rc, out = bundle._ssh(facts.host, facts.user, cmd + " 2>&1", timeout=timeout)
        json_failed = False
        try:
            payload = json.loads(out)
            json_failed = isinstance(payload, dict) and payload.get("is_error") is True
        except (ValueError, TypeError):
            pass
        if (rc != 0 or json_failed) and authentication_failure([out]):
            invalidated = invalidate_claude_auth(facts)
            detail = "Claude OAuth session expired; claude auth login 후 강제 재검사 필요"
            if invalidated.get("failure_type") == "storage":
                detail += "; 인증 캐시 저장 실패"
            # wcommit은 rc 실패의 마지막 300자를 보관하므로 원문 길이와 무관하게 남긴다.
            return rc or 1, f"AX_CLAUDE_AUTH_FAILED: {detail}\nRESULT: BLOCKED"
        return rc, out
    return bundle._ssh(facts.host, facts.user, cmd, timeout=timeout)


SESSION1_POLL_SEC = 10
# 🔴 **기다리는 동안에도 찍는다** (실측 2026-09-13). 끝나야 찍히는 로그는 멈춤을 못 보여 준다 —
#    실증 7분(18:54~19:02) 동안 저널이 비어 있었고, 그사이 워커에서 UnrealBuildTool 이 두 번
#    죽어 오류 창이 떴다는 것을 사람이 SSH 로 들어가서야 찾았다.
SESSION1_NOTE_SEC = 120
SESSION1_LAUNCHER_LOG = "launcher.log"
SESSION1_LAUNCHER_TAIL = 20             # 저널로 옮기는 런처 로그 줄 수 (최근 것부터)


def _s1_log(msg: str) -> None:
    """세션 1 경로 로그. [중요] `infer._log`·`autodispatch._log` 와 같은 `[dispatch]` 줄기다 —
    journalctl 에서 한 흐름으로 읽혀야 한다."""
    print(f"[dispatch] [세션1] {msg}", flush=True)


def _popup_events(facts, since: str, *, ssh=None) -> list:
    """🔴 워커에 뜬 **오류 창** — System 로그 `Application Popup`(ID 26), `since` 이후.

    [중요] 실측 2026-09-13: `dotnet.exe - 응용 프로그램 오류 : 알 수 없는 소프트웨어 예외
    (0xe0434352)` 가 18:55·19:00 두 번 떴는데 **Application 로그에는 없고 System 로그 ID 26
    에만** 있었다. 창이 뜨면 프로세스가 매달리므로 이것이 「왜 멈췄나」의 직접 증거다.
    [주의] `since` 는 워커 **로컬 시각** 문자열이다 — 마스터와 워커 시계가 같은 시간대라는
    전제(실측 일치)이고, 호출자가 여유를 두고 앞당긴다. 윈도우가 아니면 빈 목록이다.
    [주의] 실패해도 예외를 던지지 않는다 — 판정 보조이지 판정이 아니다.
    """
    if not getattr(facts, "windows", False):
        return []
    import base64 as _b64
    ps = ("$ProgressPreference='SilentlyContinue';"
          "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
          f"Get-WinEvent -FilterHashtable @{{LogName='System';Id=26;StartTime=[datetime]'{since}'}}"
          " -ErrorAction SilentlyContinue | Sort-Object TimeCreated | ForEach-Object "
          "{ '{0:HH:mm:ss} {1}' -f $_.TimeCreated, ($_.Message -replace '\\s+',' ') }")
    enc = _b64.b64encode(ps.encode("utf-16-le")).decode("ascii")
    try:
        rc, out = (ssh or bundle._ssh)(facts.host, facts.user,
                                       f"powershell -NoProfile -EncodedCommand {enc}")
    except Exception:                                        # noqa: BLE001
        return []
    if rc != 0:
        return []
    return [ln.strip() for ln in (out or "").splitlines()
            if ln.strip() and not ln.lstrip().startswith(("#<", "<Objs"))]


def _session1_after(facts, task_id: str, base: str, sep: str, since: str, out: str, *,
                    log, popup) -> str:
    """결과를 받은 뒤(또는 시간 초과 뒤) **런처 로그와 오류 창**을 저널로 가져온다.

    [중요] 오류 창은 **결과 문자열에도 붙인다** — `ERROR` 로 시작하므로 `agent_report` 가 오류 줄로
    뽑아 조각 기록(`c.notes`)까지 간다. 저널에만 있으면 `.33` 이 못 본다(`#391` 과 같은 결).
    """
    from ..client import bundle as _b
    try:
        ll = _b._remote_read(facts, f"{base}{sep}{SESSION1_LAUNCHER_LOG}") or ""
    except Exception as e:                                   # noqa: BLE001
        ll = ""
        log(f"{task_id} [주의] launcher.log 를 못 읽었다 — {type(e).__name__}: {e} "
            f"(런처가 옛 배달본이거나 job 을 집지 않았다)")
    else:
        if not ll.strip():
            log(f"{task_id} [주의] launcher.log 가 비었다 — 런처가 job 을 집지 않았을 수 있다")
    for ln in ll.strip().splitlines()[-SESSION1_LAUNCHER_TAIL:]:
        if ln.strip():
            log(f"{task_id} 런처: {ln.strip()[:300]}")
    try:
        pops = (popup or _popup_events)(facts, since)
    except Exception as e:                                   # noqa: BLE001
        pops = []
        log(f"{task_id} [주의] 오류 창 기록을 못 읽었다 — {type(e).__name__}: {e}")
    for p in pops:
        log(f"{task_id} @{facts.host} 🔴 오류 창 감지 — {p[:300]}")
    if pops:
        out = (out or "") + "\n" + "\n".join(
            f"ERROR [세션1] 오류 창 감지 — {p[:300]}" for p in pops)
    return out


def run_worker_session1(facts, task_id: str, *, files=(), timeout: int = DEFAULT_TIMEOUT,
                        sleeper=None, logf=None, now=None, popup=None) -> tuple:
    """세션 1 런처를 거쳐 지휘자를 돌린다. `(rc, stdout)` (`#401`).

    🔴 [중요] **마스터가 보내는 것은 데이터뿐이다** — `job.json` 의 `task_id`·`files`.
    실행 파일과 플래그는 **워커의 런처가 소유한다**(`clientside/session1_conductor.py`).
    2026-09-12 에 「마스터가 임의 셸 문자열을 파일로 떨구는」 구조를 만들었다가 폐기했다 —
    인증도 계약도 없는 **로컬 원격실행 면**이었다. 그 차이가 이 함수의 요점이다.

    [중요] 완료 판정은 **`done.flag`** 다 — 런처가 그것을 맨 마지막에 쓰므로 반쯤 쓰인
    `out.txt` 를 읽지 않는다.
    [주의] 실패해도 예외를 던지지 않는다 — `(rc, stdout)` 계약은 그대로다.
    """
    import json as _json
    import time as _t
    import uuid as _uuid
    from ..client import bundle as _b
    from client.init import residency as _R

    nap = sleeper or _t.sleep
    clock = now or _t.time
    log = logf or _s1_log
    t0 = clock()
    # [주의] 오류 창 조회 기준 — 워커 로컬 시각 · 1분 여유를 두고 앞당긴다(`_popup_events` 참조)
    since = _t.strftime("%Y-%m-%d %H:%M:%S", _t.localtime(t0 - 60))
    who = f"{task_id} @{facts.host}"
    # #695: results belong to one invocation, not merely to the task being retried.
    # Keep old attempts for audit; a fresh directory cannot contain their done.flag.
    request_id = _uuid.uuid4().hex
    rel = f".ax/session1/{task_id}/{request_id}"
    job = _json.dumps({"task_id": task_id, "files": [str(f) for f in (files or [])],
                       "request_id": request_id,
                       "approvals": _approval_overrides(), "timeout": timeout},
                      ensure_ascii=False)
    try:
        _b._remote_write(facts, f"{rel}/job.json", job + "\n", base="checkout")
    except Exception as e:                                   # noqa: BLE001
        log(f"{who} 🔴 job 전송 실패 — {type(e).__name__}: {e}")
        return 1, f"[세션1] job 을 못 보냈다 — {type(e).__name__}: {e}"
    log(f"{who} job 전송 — 파일 {len(files or [])} · 제한 {timeout}초")

    task_name = _R.conductor_task_name(_project_of(facts))
    rc0, out0 = bundle._ssh(facts.host, facts.user,
                            _R.conductor_run_command(_project_of(facts), facts))
    if rc0 != 0:
        log(f"{who} 🔴 런처를 못 깨웠다 (rc={rc0}) — {(out0 or '').strip()[:200]}")
        return 1, (f"[세션1] 런처를 못 깨웠다 (rc={rc0}) — {(out0 or '')[:200]}\n"
                   f"[중요] `{task_name}` 작업이 등록돼 "
                   f"있는지 본다(`master.client deliver` 가 등록한다)")
    log(f"{who} 런처를 깨웠다 (`{task_name}`) — done.flag 를 기다린다")

    sep = chr(92) if facts.windows else "/"
    base = f"{facts.path}{sep}{rel.replace('/', sep)}"
    waited = 0
    next_note = SESSION1_NOTE_SEC
    while waited < timeout:
        rc, _o = bundle._ssh(facts.host, facts.user,
                             (f'if exist "{base}{sep}done.flag" (echo DONE) else (echo WAIT)'
                              if facts.windows
                              else f'test -e "{base}/done.flag" && echo DONE || echo WAIT'))
        if "DONE" in (_o or ""):
            marker = (_b._remote_read(facts, f"{base}{sep}done.flag") or "").strip()
            if marker != request_id:
                log(f"{who} 🔴 결과 시도 불일치 — 현재 job 의 결과가 아니다")
                return 1, "[세션1] 결과 request_id가 현재 job과 다르다 — 옛 결과 회수 거부"
            out = _b._remote_read(facts, f"{base}{sep}out.txt") or ""
            rct = (_b._remote_read(facts, f"{base}{sep}rc.txt") or "1").strip()
            try:
                rc_i = int(rct)
            except ValueError:
                rc_i = 1
            log(f"{who} 결과 회수 — rc={rc_i} · {int(clock() - t0)}초 · 출력 {len(out)}자")
            out = _session1_after(facts, task_id, base, sep, since, out, log=log, popup=popup)
            return rc_i, out
        if waited >= next_note:
            log(f"{who} {waited}초째 대기 — 아직 결과 없음 (done.flag 없음)")
            next_note += SESSION1_NOTE_SEC
        nap(SESSION1_POLL_SEC)
        waited += SESSION1_POLL_SEC
    log(f"{who} 🔴 {timeout}초 시간 초과 — 결과를 못 받았다")
    msg = (f"[세션1] {timeout}초 안에 끝나지 않았다 — 런처가 돌지 않았을 수 있다"
           f"(로그온 세션이 없으면 `/IT` 작업은 뜨지 않는다)")
    return 1, _session1_after(facts, task_id, base, sep, since, msg, log=log, popup=popup)


def _project_of(facts) -> str:
    """이 체크아웃의 프로젝트 태그. [중요] 경로가 아니라 **배달된 config** 에서 읽는다."""
    try:
        from ..client import bundle as _b
        return (_b.stored_project(facts) or {}).get("project") or ""
    except Exception:                                        # noqa: BLE001
        return ""


def _approval_overrides() -> list:
    """MCP 도구별 승인 `-c` 값들 (`#402`). 런처가 그대로 codex 에 싣는다."""
    try:
        from ..client import bundle as _b
        return [f'mcp_servers.{_b.MCP_SERVER_NAME}.tools.{t}.approval_mode="approve"'
                for t in _b.client_tool_names()]
    except Exception:                                        # noqa: BLE001
        return []


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


def run_task(facts, task_id: str, *, files=(), beat=None, runner=None,
             timeout: int = DEFAULT_TIMEOUT) -> Outcome:
    """파견 한 건: 실행(하트비트 유지) → 판정.

    [중요] **배달 단계가 없다** (2026-09-02): 지시서는 배정된 브랜치의 골조 주석이고
    git 이 나른다 — 파일을 밀어 넣을 것이 남아 있지 않다.

    [중요] **큐에 제출하지 않는다.** 제출은 호출자(마스터)의 일이다 — 이 함수는 *워커가 무엇을
    했는가* 만 돌려준다. 판정과 제출을 한 곳에 섞으면 실패 경로에서 리스를 반납하지 못한다.
    """
    with _Beater(beat) as b:
        rc, out = run_worker(facts, task_id, files=files, runner=runner, timeout=timeout)
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


def _tag(method: str, path: str, payload):
    """[중요] **태그가 필수인 표면에만** 마운트를 실어 준다 (`#258`).

    [주의] 전부에 붙이면 안 된다 — `STAMP` 표면(submit·verify·PATCH)은 **그 work 의 스탬프**로
    풀린다(`#210`). 마운트를 붙이면 미종결 work 를 둔 채 활성을 바꿨을 때 `project_mismatch` 가
    나고, 그것은 `#210` 이 지키려던 바로 그 흐름을 깨는 것이다. 그래서 축을 나눈다.
    """
    if not isinstance(payload, dict) or str(payload.get("project") or "").strip():
        return payload
    try:
        from ..task_queue import tagging
        if not tagging.requires_tag(method, path):
            return payload
        from ..projects.config import Registry
        active = (Registry.load().active or "").strip()
    except Exception:                                    # noqa: BLE001
        return payload                                   # 태그를 못 정하면 서버가 거절한다
    return {**payload, "project": active} if active else payload


def _api(method: str, path: str, payload=None, *, timeout: int = HTTP_TIMEOUT):
    """큐 호출 한 번. [중요] **토큰은 마스터에만 있다** — 이 함수가 워커로 건너가면 안 된다."""
    url = QUEUE_URL.rstrip("/") + path
    payload = _tag(method, path, payload)
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


def claim(worker_id: str, capabilities, *, work_id: str = "", api=_api):
    """태스크 하나를 집는다. 없으면 `None`. [중요] **능력은 실측값**(`facts.capabilities`)이다."""
    payload = {"worker_id": worker_id, "capabilities": list(capabilities)}
    if work_id:
        payload["work_id"] = work_id
    return api("POST", "/api/v1/tasks/claim", payload)


def waiting_summary(project: str = "", *, api=_api) -> dict:
    """지금 **집히기를 기다리는** 태스크. `{pending, stuck, reclaimed, lines}` (`#318` 완료 조건 5).

    [중요] **이 함수가 있는 이유**: `reclaim` 이 만기 리스를 회수해 `pending` 으로 되돌리는데,
    pull 에서는 다른 워커가 알아서 집었지만 **push 에서는 집을 주체가 없다.** 마스터가 파견
    루프를 다시 돌려야 하고(그것이 곧 재파견이다 — `claim` 이 pending 을 집으면서 `worker_id`
    를 갱신하고 `epoch` 를 올린다), 상주가 철거된 지금(`#320`) 그 루프는 **사람이 시작한다.**
    그래서 「기다리는 것이 있다」가 **보여야** 한다 — 안 보이면 조용히 멈춘다.

    [주의] `stuck` 은 재파견 대상이 아니다 — `reclaim_count > 3` 으로 큐가 손든 것이라
    사람이 봐야 한다. 세되 pending 과 **섞지 않는다.**
    """
    out = {"pending": 0, "stuck": 0, "reclaimed": 0, "lines": []}
    try:
        tasks = api("GET", f"/api/v1/tasks?limit=500"
                          + (f"&project={project}" if project else ""), None)
    except Exception as e:                                   # noqa: BLE001
        out["lines"].append(f"[주의] 대기 목록을 읽지 못했다 ({e}) — 없다는 뜻이 아니다")
        return out
    for t in tasks or []:
        st = t.get("status")
        if st not in ("pending", "stuck"):
            continue
        out[st] = out.get(st, 0) + 1
        n = int(t.get("reclaim_count", 0) or 0)
        if n:
            out["reclaimed"] += 1
        out["lines"].append(
            f"{str(t.get('task_id'))[:8]} · {st}"
            + (f" · [주의] 회수 {n}회" if n else "")
            + f" · {t.get('stem') or t.get('work_id') or ''}")
    return out


def heartbeat(task_id: str, worker_id: str, *, api=_api):
    return api("POST", f"/api/v1/tasks/{task_id}/heartbeat", {"worker_id": worker_id})


def submit(task_id: str, out: Outcome, *, epoch=None, worker_id: str = "", api=_api):
    """성공 제출. [중요] `submittable` 이 아닌 것을 여기로 보내지 않는다 — 근거가 없다.

    [중요] `worker_id` 는 **큐가 신원을 대조하는 값**이다 (`#318`). 빈 값을 보내면 거부된다 —
    그것이 설계다(미확인은 통과가 아니다).
    """
    if not out.submittable:
        raise QueueError(f"제출 불가한 결과를 submit 하려 했다 — {out.summary}")
    return api("POST", f"/api/v1/tasks/{task_id}/submit", {
        "branch": out.branch, "head_commit": out.head,
        "self_check": {"worker_report": out.tail[-2000:], "gates": "worker-side only"},
        "epoch": epoch, "worker_id": worker_id,
    })


def verify(task_id: str, *, passed: bool = True, feedback: str = "", api=_api):
    """조각을 **종결**한다 — [중요] 「검증했다」가 아니라 **「그 조각 작업이 끝났다」**이다.

    [중요] **조각 단위로 통과 도장을 찍지 않는다** (사용자 지적 2026-09-03): 미시적인 한
    부분씩 검사해 봐야 값이 없다. 실제 검사는 `.33` 이 **서브 브랜치를 전부 머지한 뒤
    한 곳에서 한 번** 한다 — 교차 파일 정합성은 모아 놔야 드러나기 때문이다.
    이 호출은 큐에 *"이 조각은 더 이상 진행할 것이 없다"* 를 알리는 것뿐이고,
    `verified` 라는 상태 이름은 큐의 어휘일 뿐 판정의 주장이 아니다.

    [중요] **submit 만으로는 태스크가 끝나지 않는다.**

    큐의 `terminal = verified + failed + cancelled` 이고, `terminal >= total` 일 때만
    work 이 `ready_for_review` 로 뒤집히며 **거기에 `.33` 완료 공지(Redmine [리뷰 요청]
    이슈)가 달려 있다**(`task_queue/logic_cleanup.py`).

    [중요] **이것이 없어서 교착이었다** (실측 2026-09-03): 조각 4/4 가 커밋에 성공해도 전부
    `submitted` 에 남아 terminal 0/4 → 공지 없음 → `.33` 은 끝난 줄 모름. 그런데 종전 코드는
    verify 를 「통합자」 안에 두었고 통합은 사람 승인을 기다렸으므로, **승인하라는 공지가
    통합 뒤에 나오는** 순환이 됐다. 정본대로 조각의 끝은 **워커 커밋**이므로 판정도 거기서 낸다.

    [주의] `verify_epoch` 는 보내지 않는다 — 원전 규약상 `None` 은 재배정 fencing 대상이
    아닌 주체(서버측 verify)를 뜻한다.
    """
    return api("POST", f"/api/v1/tasks/{task_id}/verify", {
        "passed": bool(passed), "result": "pass" if passed else "reject",
        "feedback": feedback[:600],
    })


def cancel(task_id: str, *, reason: str = "", no_work: bool = False, api=_api):
    """조각을 **종결**한다 — 소유권 게이트가 없는 유일한 종결 경로다.

    🔴 [중요] `no_work=True` 는 *"골조에 `[PSEUDO]` 가 0개 = 채울 본문이 없다"* 다.
    실패도 취소도 아니고, **원전이 등재 자체를 skip 하는** 그 조각이다.

    [중요] **`submit`+`verify` 로 종결하지 않는다** (실측 2026-09-04 21:32): 그 두 경로는
    `#318` 신원 게이트가 있어 *"고지자 '(none)' 가 소유자 '192.168.0.2' 가 아니다"* 로
    **409** 를 냈고, 조각 2건이 `claimed` 로 남아 `terminal 2/4` 교착이 됐다. 파견하지 않은
    조각을 워커 이름으로 제출하는 것도 사실이 아니다 — 그 워커는 아무것도 안 했다.
    """
    return api("POST", f"/api/v1/tasks/{task_id}/cancel",
               {"reason": reason[:300], "no_work": bool(no_work)})


def submit_fail(task_id: str, reason: str, detail: str = "", *, epoch=None,
                worker_id: str = "", result: str = "", new_base_commit: str = "",
                api=_api):
    """실패 고지. [중요] **submit 과 같은 두 게이트**를 통과해야 한다 (`#318`).

    🔴 `result="revise"` 면 terminal `failed` 이 아니라 **`needs_revision`** 으로 간다
    (`#388` · 원전 `_classify_verify_issues` 이식). 그때 `new_base_commit` 은 **피드백
    주석이 박힌 커밋**이고, 다음 시도가 거기서 출발한다.

    [중요] **분류는 여기서 하지 않는다** — 호출자가 `work/revise.classify` 로 정한다.
    """
    return api("POST", f"/api/v1/tasks/{task_id}/submit-fail",
               {"reason": reason[:200], "detail": detail[-2000:],
                "epoch": epoch, "worker_id": worker_id,
                "result": result, "new_base_commit": new_base_commit})


AUTO = "auto"          # [중요] 기본은 **재는 것**이다. 끄려면 호출자가 명시적으로 None 을 준다.


def run_once(paths, *, facts=None, project: str = "", api=_api, runner=None, writer=None,
             clean=AUTO, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """큐에서 하나 집어 워커에서 돌리고 결과를 제출한다. **한 건.**

    반환은 사람이 읽을 요약 dict — `{"picked":…, "task":…, "outcome":…, "submitted":…}`.
    집을 게 없으면 `{"task": None}`.
    """
    if facts is None:
        facts = [bundle.probe(h, u, p, d, r, dp)
                 for h, u, p, d, r, dp in bundle.workshops(project or paths.name)]
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

    work_id = str(task.get("work_id") or "")
    res = {"picked": pick.summary, "task": task_id, "worker": f.host, "epoch": epoch,
           "work": work_id}
    if not work_id:
        # [중요] `#319` — work_id 없이는 작업 브랜치도 조각 durable 도 이름을 못 만든다.
        #    조용히 옛 평평한 이름으로 접지 않는다(그러면 골조 없는 base 에서 난다).
        raise QueueError(f"claim 응답에 work_id 가 없다 — 계층형 브랜치를 만들 수 없다 "
                         f"(task={task_id})")
    try:
        # [중요] 대상 파일은 **큐 레코드**에서 온다 — 지시와 판정이 같은 하나에서 나온다
        #    (`infer.dispatch_task` 와 같은 계약).
        want = [str(x) for x in (task.get("target_file"), task.get("header_file")) if x]
        if not want:
            raise QueueError(f"큐 레코드에 target_file·header_file 이 없다 (task={task_id}) — "
                             f"무엇을 만들지 모르므로 파견하지 않는다")
        out = run_task(f, task_id, files=want,
                       beat=lambda: heartbeat(task_id, worker_id, api=api),
                       runner=runner, timeout=timeout)
        res["outcome"] = out.summary
        res["tail"] = out.tail
        if out.submittable:
            submit(task_id, out, epoch=epoch, worker_id=worker_id, api=api)
            res["submitted"] = "submit"
        else:
            submit_fail(task_id, out.status, out.reason + "\n" + out.tail,
                        epoch=epoch, worker_id=worker_id, api=api)
            res["submitted"] = "submit-fail"
    except Exception as e:                                   # noqa: BLE001
        # [중요] 집은 태스크를 붙잡은 채 죽지 않는다. 반납이 실패해도 사유를 남긴다.
        res["error"] = f"{type(e).__name__}: {e}"
        try:
            submit_fail(task_id, "파견 실패", res["error"],
                        epoch=epoch, worker_id=worker_id, api=api)
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
    facts = [bundle.probe(h, u, p, d, r, dp) for h, u, p, d, r, dp in bundle.workshops(paths.name)]

    if cmd == "probe":
        pick = pick_worker(facts, clean=cleanliness(paths.name))
        print(f"프로젝트 {paths.name}")
        for f in facts:
            print("  " + f.summary)
        print("선택: " + pick.summary)
        return 0
    if cmd == "once":
        r = run_once(paths, facts=facts)
        print(_summary(r))
        if r.get("task"):
            # [중요] 파견은 상태가 실제로 바뀐 순간이다 — 스냅샷 갱신을 던진다 (#216).
            #    백그라운드·무해·120초 가드 통과 시에만 실제 수집 (status.refresh_after_event)
            from ..status import refresh_after_event
            print("  " + refresh_after_event("파견", project=paths.name))
        return 0
    if cmd == "loop":
        n = int(argv[2]) if len(argv) > 2 else 5
        did = False
        for i in range(n):
            r = run_once(paths, facts=facts)
            print(f"[{i+1}/{n}]")
            print(_summary(r))
            did = did or bool(r.get("task"))
            if not r.get("task"):
                break
        if did:
            from ..status import refresh_after_event
            print("  " + refresh_after_event("파견 루프", project=paths.name))
        return 0
    print(__doc__.split("## ")[0])
    print("  probe | once | loop")
    return 2


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
