"""추론 파견 — 워커는 읽고 추론하고 **텍스트로 답한다** (중 1.3 · §4.5 · §8.4).

## 🔴 [중요] 이것은 정본이 아니다 — 정본 ⑸ 는 **워커가 커밋한다**

    이 파일       워커는 추론만 → 응답을 스풀에 → 통합이 적용·커밋      ← 지금 도는 것
    정본 ⑸        워커가 **자기 서브 브랜치에 커밋**하고 다음 작업을 요청  ← `wcommit.py`

사용자 확정 2026-09-02. 종전 라벨 *"사용자 확정 2026-08-11"* 은 **틀렸다**(`settled-decisions.md`
가 mislabeled 로 닫아 뒀다 — `"그래 해"` 를 확정으로 적은 것이다). `runner.py`·`ax-work` 는
**정본 방향의 재료**이므로 지우지 않는다. 워커에는 스킬이 둘 배달돼 있고 **파견 지시가 이름으로
고른다.**

## [중요] 응답은 stdout 이 아니라 **파일로** 받는다

두 번 값을 치른 함정의 반대쪽이다. 마스터→워커는 이미 *"지시는 ASCII, 내용은 파일로"* 인데
(cp949 로 글자가 깨지고 18KB stdin 이 안 닫혀 멈췄다), **워커→마스터도 같은 이유로 같다:**

- `.2` 의 콘솔은 **CP949** 다 — 실측 2026-08-11 에 층3 이 UBT 의 한국어 출력에서 디코딩부터
  죽었다. 응답에 한국어 주석이 섞이면 stdout 은 같은 자리에서 깨진다
- `scp` 는 바이트를 그대로 옮기고 인코딩·줄바꿈을 건드리지 않는다. `_remote_read` 는
  **결과물의 존재**로 성공을 판정하므로 *"모르는 것을 없음으로 접는"* 실패가 없다

즉 stdout 은 **판정 마커와 사람이 읽을 산문**만 나르고, 코드 본문은 파일로 온다.

## [중요] 파견은 큐에 제출하지 않는다 — 태스크는 `claimed` 로 남는다

추론이 끝난 것은 **태스크가 끝난 것이 아니다.** `submit(branch, head_commit)` 은 커밋이
있어야 부를 수 있고, 그 커밋은 **통합자가 빌드를 통과시킨 뒤에** 생긴다(소 1.4.3).

[주의] **그래서 지금은 리스가 붙잡힌 채 끝난다.** 중 1.4 가 없는 동안 리스(1200초)는 만료되고
태스크는 재확보된다 — 숨기지 않고 `Handoff.summary` 가 그렇게 말한다. [중요] **다만 같은 추론을
두 번 사지는 않는다**: 스풀에 **같은 기준 커밋의** 응답이 이미 있으면 파견하지 않고 재사용한다
(소 1.3.3). 스풀이 곧 *"어디까지 진행됐나"* 의 답이다.

## [중요] 병렬을 기본값으로 두지 않는다 (실측 2026-08-09)

워커 2대는 **12% 빠른데 90% 비쌌다** — 캐시 생성이 워커별 고정비라 조각이 작으면 손해다.
반대로 **묶는 것은 확실히 이득**이다(4파일 묶음 파일당 3.2배 쌈). 그래서 동시 파견은 구현하되
`parallel=False` 가 기본이고, 켜는 것은 사람의 선택이다. 분산의 값은 **처리량이 아니라 증분**
이다(사용자 재정의 2026-08-11).
"""
from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..client import bundle
from . import runner
from .skeleton import SkeletonError, parse_files

RESPONSE_NAME = "response.txt"
SPOOL_SUFFIX = ".json"

# [중요] ASCII 만. 한글을 명령줄에 실으면 워커 콘솔에서 깨진다(`runner` 의 § 참조).
#    스킬 이름을 **명시**한다 — 워커에는 `ax-work`(구 토폴로지)도 배달돼 있다.
# 🔴 [중요] **지시서는 파일이 아니라 골조 주석이다** (사용자 확정 · 매니페스트 철거 2026-09-02).
#    체크아웃에 이미 있는 **헤더의 `[DOC]`·`[PSEUDO]` 블록**이 지시서다 — 골조가 전체 구조를
#    알 때 써 넣은 것이고, git 이 관리하는 파일이라 늙지 않는다. 별도 문서·그 배달 배선은 없다.
# [중요] 대상 파일은 **명령줄에 명시**한다 — 워커가 산문에서 우연히 읽지 않게(실측 2026-08-09).
#    판정(`judge(want=...)`)과 지시가 **같은 목록**에서 나와야 어긋나지 않으므로, 둘 다
#    `dispatch_task` 가 큐 레코드에서 만든 하나의 리스트를 쓴다.
INFER_INSTRUCTION = (
    "Follow the ax-infer skill (INFERENCE ONLY, not ax-work). "
    "Implement EXACTLY these files and nothing else: {files}. "
    "Your instructions are the [DOC] comment blocks already present in those files and in "
    "their headers in this checkout - read them first; they state what each function must do, "
    "why, and how this piece connects to the other pieces of this work. "
    "Fill in every [PSEUDO] marker and DELETE that marker line; keep [DOC]/[STATE]/[BIND]/"
    "[REPLICATED] comments verbatim. Do NOT add a completion marker of your own. "
    "Do NOT change any declaration in the headers - they are a frozen contract. "
    "Judge from the source files in this checkout, not from memory. "
    "Do NOT edit source files, do NOT commit, do NOT push, do NOT create branches. "
    "Write the complete new content of every target file to ./{work}/{task}/{resp} as UTF-8, "
    "one block per file, each starting with a line: === FILE: <path> === . "
    "That file must contain ONLY those blocks: do NOT write RESPONSE: or RESULT: into it. "
    "Then PRINT to stdout, as the last two non-empty lines you print and nothing after them: "
    "RESPONSE: <number of files> / RESULT: DONE "
    "(print RESULT: BLOCKED instead if you could not finish, and say why above it)."
)

_RESPONSE_MARK = re.compile(r"^RESPONSE:\s*(\d+)\s*$")
# [중요] 응답 **파일 끝**에 붙은 마커 — 실전 첫 구동에서 나왔다(2026-08-12). 아래 § 참조.
_TRAILING_MARK = re.compile(r"^(RESPONSE:\s*\d+|RESULT:\s*(DONE|BLOCKED).*)$")


class DispatchError(RuntimeError):
    """파견 자체가 불가능하다 — [중요] 태스크를 집은 채로 죽지 않게 호출자가 반납한다."""


@dataclass
class Response:
    """워커 한 번의 **추론 결과**. [중요] 모르는 값을 성공으로 접지 않는다."""

    task_id: str = ""
    worker: str = ""
    status: str = runner.BLOCKED
    files: dict = field(default_factory=dict)      # {경로: 완성 본문}
    want: list = field(default_factory=list)
    notes: list = field(default_factory=list)      # [중요] 로 시작하는 것은 치명적이다
    reason: str = ""
    tail: str = ""                                 # stdout 꼬리 — 사람이 읽는다
    usage: dict = field(default_factory=dict)
    base_commit: str = ""                          # [중요] 이 응답이 어느 소스를 근거로 하나
    reused: bool = False                           # 스풀에서 되살렸나 (소 1.3.3)
    # 🔴 정본 ⑷ — 이 조각의 **서브 브랜치**(작업 브랜치에서 갈라진 것). 마스터가 배정하고
    #    워커는 받은 이름을 쓴다(원전 `cluster_coordinator.py:11`). ⑸ 에서 워커가 여기에
    #    커밋한다. [주의] 못 만들었으면 사유가 `subbranch_error` 에 남는다 — 빈 문자열을
    #    「없어도 된다」로 읽지 않기 위해 둘을 나눈다.
    subbranch: str = ""
    subbranch_error: str = ""
    # [중요] claim 때 받은 리스 epoch. **통합자가 제출할 때 필요하다**(소 1.4.3) — 없으면 큐의
    #    fencing 이 꺼져 좀비 제출을 못 막는다. 파견과 제출이 다른 프로세스라 스풀에 실어 둔다.
    epoch: object = None

    @property
    def missing(self) -> list:
        return [w for w in self.want if w not in self.files]

    @property
    def fatal(self) -> list:
        """[중요] 로 표시된 메모. `parse_files` 가 이미 그 규약으로 쓴다."""
        return [n for n in self.notes if n.startswith("[중요]")]

    @property
    def ok(self) -> bool:
        """[중요] **fail-closed.** 마커·파일·본문 셋이 다 맞아야 통합자에게 넘긴다."""
        return (self.status == runner.DONE and bool(self.files)
                and not self.missing and not self.fatal)

    @property
    def cost_usd(self) -> float:
        return float(self.usage.get("total_cost_usd") or 0.0)

    @property
    def summary(self) -> str:
        if self.ok:
            n = len(self.files)
            b = sum(len(v) for v in self.files.values())
            s = f"[완료] 파일 {n} · {b:,}자"
            if self.reused:
                s += " ·  스풀 재사용(파견 안 함)"
            elif self.cost_usd:
                s += f" · ${self.cost_usd:.4f}"
            return s
        bits = [f"[중요] {self.status}"]
        if self.reason:
            bits.append(self.reason)
        if self.missing:
            bits.append(f"빠진 파일 {len(self.missing)}: {', '.join(self.missing[:3])}")
        bits += self.fatal[:3]
        return " — ".join(bits)


def infer_command(facts, task_id: str, files=()) -> str:
    """워커에서 실제로 도는 한 줄. [중요] 경로는 레지스트리에서 온 값(`facts.path`)이다.

    [중요] `files` 는 **판정에 쓰는 그 목록**이다 — 지시와 판정이 갈라지지 않게 하나만 돈다.
    비면 지시문에 `(none given)` 이 박혀 워커가 스스로 고르려 들므로 호출부가 막는다.
    """
    shown = ", ".join(str(f) for f in (files or [])) or "(none given)"
    instr = INFER_INSTRUCTION.format(work=bundle.WORK_REL, task=task_id, resp=RESPONSE_NAME,
                                     files=shown)
    cd = f'cd /d "{facts.path}"' if facts.windows else f'cd "{facts.path}"'
    # `--output-format json` — 마커는 `result` 안으로 오고, 대신 토큰·비용을 함께 받는다.
    # 계측 없이 "분산이 이득인가" 를 논할 수 없다(실측이 두 번 결론을 뒤집었다).
    return (f'{cd} && claude -p --output-format json '
            f'--dangerously-skip-permissions "{instr}"')


def response_path(facts, task_id: str) -> str:
    """워커 안의 응답 파일 절대경로."""
    rel = f"{bundle.WORK_REL}/{task_id}/{RESPONSE_NAME}"
    if facts.windows:
        return f"{facts.path}\\" + rel.replace("/", chr(92))
    return f"{facts.path}/{rel}"


def read_response(facts, task_id: str, *, reader=None) -> str:
    """응답 파일을 **scp 로** 가져온다. 없으면 빈 문자열, **못 읽으면 예외.**

    [중요] 셸 경유(`type`·`Get-Content`)를 쓰지 않는다 — `_remote_read` 의 주석에 그 사고가
    두 건 적혀 있고, 둘 다 *"조용히 빈 문자열"* 이었다.
    """
    r = reader or bundle._remote_read
    return r(facts, response_path(facts, task_id))


def strip_trailing_markers(raw: str) -> tuple:
    """응답 파일 **끝**에 붙은 판정 마커를 떼어낸다. `(본문, 뗀 줄 수)`.

    [중요] **실전 첫 구동에서 나온 결함이다** (2026-08-12). 지시문이 *"the last two non-empty lines
    of your output"* 이라 했더니 워커가 **응답 파일의** 마지막 두 줄로 읽고 `RESPONSE: 2` ·
    `RESULT: DONE` 을 파일 끝에 써 넣었다. 마커 검사가 통과했다면 `parse_files` 가 그 두 줄을
    **마지막 파일 본문에 그대로 넣었을** 것이다 — `.cpp` 끝에 `RESULT: DONE` 이 박힌다.

    지시문을 고쳤지만(`stdout` 이라고 못박고, 파일에 쓰지 말라고 했다) 여기서도 막는다 —
    **한 번 일어난 실수는 다시 일어난다.** 다만 [주의] 로 **말하고** 뗀다: 조용히 지우면 지시를
    안 지킨 사실이 사라지고, 통째로 버리면 옳게 만든 본문까지 버려 같은 추론을 다시 산다.

    [주의] **맨 끝의 연속된 마커 줄만** 본다. 파일 중간의 같은 글자는 건드리지 않는다.
    """
    lines = (raw or "").replace("\r", "").split("\n")
    n = 0
    while lines:
        last = lines[-1].strip()
        if not last:
            lines.pop()
            continue
        if _TRAILING_MARK.match(last):
            lines.pop()
            n += 1
            continue
        break
    return ("\n".join(lines) + ("\n" if lines else ""), n)


def parse_markers(stdout: str) -> tuple:
    """`(상태, 사유, 꼬리, 계측)`. [중요] **마지막 줄이 `RESULT:` 여야 한다 — 없으면 BLOCKED.**

    `runner.parse_result` 를 그대로 쓰지 않는 이유는 하나다: 그쪽은 `ATTEMPT`/`HEAD` 를
    **요구**하고, 없으면 *"제출할 근거가 없다"* 를 사유로 적는다. 추론 파견에는 브랜치도
    커밋도 **없는 것이 정상**이라 그 사유는 거짓말이 된다 — 사람이 읽는 실패 사유가 틀리면
    엉뚱한 곳을 조사한다. 대신 판정 규약(비대칭 관대함 포함)은 `runner` 의 것을 재사용한다.
    """
    body, meta = runner._unwrap(stdout)
    ne = [ln.strip() for ln in (body or "").replace("\r", "").split("\n") if ln.strip()]
    tail = "\n".join(ne[-12:])
    if not ne:
        return runner.BLOCKED, "출력이 비었다", tail, meta
    m = runner._RESULT_STRICT.match(ne[-1])
    if m:
        return m.group(1), "", tail, meta
    # [중요] 비대칭은 의도다 — 사유가 붙은 `BLOCKED — …` 는 받고 `DONE — …` 은 받지 않는다.
    loose = runner._RESULT_LOOSE.match(ne[-1])
    if loose:
        return (runner.BLOCKED,
                loose.group(1).strip(" —-·:") or "워커가 사유를 적지 않았다", tail, meta)
    return (runner.BLOCKED,
            f"마지막 줄이 RESULT: 가 아니다 — {ne[-1][:70]!r}", tail, meta)


def judge(stdout: str, raw_response: str, *, want: list) -> Response:
    """마커 + 응답 파일을 합쳐 판정한다. **fail-closed.**

    [중요] **두 근거를 다 본다.** 마커만 보면 워커가 `DONE` 이라 말하고 파일을 안 쓴 경우를
    통과시키고, 파일만 보면 반쯤 쓰이다 죽은 것을 통과시킨다.
    """
    status, reason, tail, meta = parse_markers(stdout)
    res = Response(status=status, reason=reason, tail=tail, usage=meta, want=list(want))
    if not want:
        res.status = runner.BLOCKED
        res.reason = ("대상 파일 목록이 비었다 — 큐 레코드의 대상 파일을 못 읽었다. "
                      "무엇을 받아야 하는지 모르면 무엇을 받아도 통과시킬 수 없다")
        return res
    if res.status != runner.DONE:
        return res

    if not (raw_response or "").strip():
        res.status = runner.BLOCKED
        res.reason = (res.reason + " · " if res.reason else "") + \
            f"RESULT: DONE 인데 {RESPONSE_NAME} 이 비었거나 없다 — 제출할 근거가 없다"
        return res
    clean, stripped = strip_trailing_markers(raw_response)
    try:
        files, notes = parse_files(clean, want=list(want))
    except SkeletonError as e:
        res.status = runner.BLOCKED
        res.reason = f"응답을 갈라 읽지 못했다 — {e}"
        return res
    # [중요] 파일 끝 개행을 하나로 맞춘다 (실측 2026-08-12). `parse_files` 는 블록마다 `strip()` 을
    #    하는데(펜스·마커 잔재를 떼려면 필요하다) 그러면 **끝 개행이 통째로 사라진다** — 실전
    #    첫 구동의 `.h` 가 그렇게 마지막 빈 줄을 잃었다. 적용되면 **손대는 파일마다 EOF 잡음
    #    diff** 가 생기고 리뷰와 blame 이 더러워진다.
    #    관례를 재서 골랐다: `Source/ModularStage` 의 `.h`/`.cpp` 160개 중
    #      개행 하나로 끝 **110** · 개행 없이 끝 36 · 끝에 빈 줄 14
    #    → 개행 하나가 지배적(69%)이고 git 관례이기도 하다. [주의] 나머지 50개는 EOF 가 한 줄
    #      바뀐다 — **완전 보존은 불가능**하고(strip 이 정보를 지운다), 이쪽이 잡음이 가장 적다.
    files = {k: (v.rstrip("\n") + "\n") for k, v in files.items()}
    res.files, res.notes = files, list(notes)
    if stripped:
        # [주의] 지시를 안 지킨 사실을 남긴다 — 통과시키되 말한다
        res.notes.append(f"[주의] 응답 파일 끝의 판정 마커 {stripped}줄을 뗐다 — "
                         f"마커는 stdout 에만 낸다(파일에 넣으면 본문에 섞인다)")

    # [중요] 마커가 신고한 개수와 실제가 다르면 **말해 준다** (조용히 넘기지 않는다).
    #    관대함은 안전한 판정 쪽으로만 연다 — 신고 수가 틀렸다고 BLOCKED 로 만들지는 않는다.
    for ln in reversed([x.strip() for x in (res.tail or "").split("\n") if x.strip()]):
        m = _RESPONSE_MARK.match(ln)
        if m:
            said = int(m.group(1))
            if said != len(files):
                res.notes.append(f"[주의] 워커는 {said}개라 했는데 읽힌 것은 {len(files)}개다")
            break
    # [중요] **층1 을 여기서 돌린다** (중 2.1 · 소 2.1.3). 가장 이른 자리다 — 잔재가 있는 응답이
    #    *"통과"* 로 스풀에 쌓이면 통합자가 적용 단계에서야 막고, 같은 결론에 왕복이 더 든다.
    #    [주의] 여기서는 **동결을 대조하지 않는다** — 기준 원본을 아는 것은 통합자 쪽 관심사이고
    #    (`integrate.local_baseline`), 이 함수는 파견 결과만 본다. 잔재 검사는 원본이 필요 없다.
    if res.files:
        from . import layer1 as layer1_mod
        L = layer1_mod.check(res.files)
        if not L.ok:
            res.notes += [f"[중요] {p}" for p in L.problems]

    if not res.ok:
        res.status = runner.BLOCKED
        if not res.reason:
            res.reason = "응답이 계약을 못 맞췄다"
    return res


def infer_task(facts, task_id: str, *, want, beat=None, runner_=None,
               reader=None, timeout: int = runner.DEFAULT_TIMEOUT) -> Response:
    """파견 한 건: 추론(하트비트 유지) → 응답 되읽기 → 판정.

    [중요] **배달 인자가 없다** (2026-09-02): 지시서는 base 커밋의 헤더 `[DOC]` 이고
    git 이 나른다. `want` 는 이제 **필수**다 — 큐 레코드에서 오고, 그것이 지시와 판정의
    같은 하나다(종전에는 매니페스트 본문에서 되읽었다).

    [중요] **큐를 만지지 않고, 응답을 적용하지도 않는다.** 이 함수는 *워커가 무엇을 답했는가* 만
    돌려준다 — 적용·빌드·커밋은 통합자(중 1.4)의 일이다.
    """
    files_wanted = list(want or [])
    # [중요] **fail-closed** — 대상 파일을 모르면 파견하지 않는다. 빈 목록으로 보내면 워커가
    #    스스로 할 일을 고르고, 그것이 가장 비싼 실패다.
    if not files_wanted:
        raise DispatchError(f"대상 파일이 비었다 (task={task_id}) — 지시와 판정의 근거가 "
                            f"없으므로 파견하지 않는다")
    # [중요] **아무것도 배달하지 않는다.** 지시서는 배정된 브랜치의 헤더 `[DOC]` 이고
    #    base 커밋에 이미 있다 — 나를 것이 없다 (매니페스트 배선 철거 2026-09-02).
    with runner._Beater(beat) as b:
        rc, out = (runner_ or (lambda f_, t_, to_: _default_runner(f_, t_, to_,
                                                                   files_wanted)))(
            facts, task_id, timeout)
    try:
        raw = read_response(facts, task_id, reader=reader)
    except bundle.BundleError as e:
        # [중요] "못 읽었다" 를 "없다" 로 접지 않는다 — 그게 `_remote_read` 가 배운 교훈이다
        raw = ""
        res = judge(out, "", want=files_wanted)
        res.reason = (res.reason + " · " if res.reason else "") + f"응답 파일 읽기 실패 — {e}"
        res.status = runner.BLOCKED
        res.task_id, res.worker = task_id, facts.host
        return res
    res = judge(out, raw, want=files_wanted)
    res.task_id, res.worker = task_id, facts.host
    if rc != 0 and res.status == runner.DONE:
        # [중요] 워커는 DONE 이라는데 껍데기가 실패했다 — 성공으로 접지 않는다
        res.status = runner.BLOCKED
        res.reason = f"RESULT: DONE 이지만 ssh rc={rc} 다"
    elif rc != 0:
        res.reason = (res.reason + " · " if res.reason else "") + f"ssh rc={rc}"
    if b.errors:
        res.reason = (res.reason + " · " if res.reason else "") + \
            f"하트비트 실패 {len(b.errors)}회"
    return res


def _default_runner(facts, task_id: str, timeout: int, files=()) -> tuple:
    return bundle._ssh(facts.host, facts.user, infer_command(facts, task_id, files),
                       timeout=timeout)


# ── 스풀 — [중요] **돈을 낸 출력이고, 진행 상황의 유일한 사본이다** (소 1.3.2·1.3.3) ──────

def spool_dir(paths, work_id: str = ""):
    d = paths.responses / (work_id or "loose")
    return d


def spool_path(paths, task_id: str, work_id: str = ""):
    return spool_dir(paths, work_id) / f"{task_id}{SPOOL_SUFFIX}"


def spool(paths, res: Response, *, work_id: str = "", order: int = 0) -> str:
    """응답을 스풀에 **원자적으로** 쓴다. 통합자가 이걸 읽어 순서대로 적용한다.

    [중요] **실패도 쓴다.** 무엇을 시도했고 어디서 막혔는지가 사라지면 피드백을 줄 근거가 없다
    (§8.4 「실패도 커밋한다」와 같은 논지 — 다만 우리는 커밋이 아니라 스풀에 남긴다).
    """
    d = spool_dir(paths, work_id)
    d.mkdir(parents=True, exist_ok=True)
    p = spool_path(paths, res.task_id, work_id)
    rec = {
        "task_id": res.task_id, "work_id": work_id, "order": order,
        "worker": res.worker, "status": res.status, "reason": res.reason,
        "base_commit": res.base_commit, "epoch": res.epoch,
        # 🔴 정본 ⑷ — 조각의 서브 브랜치. [중요] **스풀에 실어야 통합·검수가 안다** (파견과
        #    통합은 다른 프로세스다 — `epoch` 를 여기 실은 것과 같은 이유).
        "subbranch": res.subbranch, "subbranch_error": res.subbranch_error,
        "want": res.want, "files": res.files,
        "notes": res.notes, "usage": res.usage, "tail": res.tail[-4000:],
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)                      # [중요] 통합자가 반쯤 쓰인 응답을 읽으면 안 된다
    return str(p)


def unspool(paths, task_id: str, work_id: str = "") -> Response | None:
    """스풀에서 되살린다. 없으면 `None`. **못 읽으면 `None` 이 아니라 예외다.**"""
    p = spool_path(paths, task_id, work_id)
    if not p.is_file():
        return None
    rec = json.loads(p.read_text(encoding="utf-8"))
    return Response(
        task_id=rec.get("task_id", ""), worker=rec.get("worker", ""),
        status=rec.get("status", runner.BLOCKED), files=dict(rec.get("files") or {}),
        want=list(rec.get("want") or []), notes=list(rec.get("notes") or []),
        reason=rec.get("reason", ""), tail=rec.get("tail", ""),
        usage=dict(rec.get("usage") or {}), base_commit=rec.get("base_commit", ""),
        epoch=rec.get("epoch"), reused=True,
        subbranch=rec.get("subbranch", ""), subbranch_error=rec.get("subbranch_error", ""))


def reusable(paths, task_id: str, *, base_commit: str, work_id: str = "") -> Response | None:
    """[중요] **같은 기준 커밋의 통과한 응답이 이미 있으면 다시 사지 않는다** (소 1.3.3).

    리스 만료·중단·재실행 뒤에 같은 태스크가 다시 집히는 것은 **정상 흐름**이다(제출은
    통합자가 하므로 그때까지 태스크는 `claimed` 로 남는다). 그때 추론을 다시 돌리면 돈만
    두 번 낸다 — 스풀이 그것을 막는 자리다.

    [주의] **기준 커밋이 다르면 재사용하지 않는다.** 트윈이 움직였으면 근거가 달라진 것이고,
    낡은 응답을 적용하면 통합자의 빌드가 남의 실패로 깨진다.
    """
    old = unspool(paths, task_id, work_id)
    if old is None or not old.ok:
        return None
    if (old.base_commit or "") != (base_commit or ""):
        return None
    return old


# ── 인계 — [중요] 순서가 계약이다 (소 1.3.2) ────────────────────────────────────────

@dataclass
class Handoff:
    """통합자에게 넘기는 것. [중요] **적용 순서대로**이고, 통과분만 들어간다.

    적용 순서는 분해(`decompose`)가 정한 의존 순서다 — A 가 B 를 `#include` 하면 B 가 먼저다.
    파견은 병렬일 수 있어도 **적용은 순차**다(§4.5).
    """

    work_id: str = ""
    items: list = field(default_factory=list)       # [(순서, Response)] — 파견 순서 그대로
    skipped: list = field(default_factory=list)     # [(task_id, 사유)] — 파견조차 안 한 것
    note: str = ""

    def ordered(self) -> list:
        """[중요] **통과분만**, 적용 순서대로. 실패는 통합자에게 넘기지 않는다."""
        return [r for _, r in sorted(self.items, key=lambda kv: kv[0]) if r.ok]

    @property
    def failed(self) -> list:
        return [r for _, r in sorted(self.items, key=lambda kv: kv[0]) if not r.ok]

    @property
    def cost_usd(self) -> float:
        return sum(r.cost_usd for _, r in self.items)

    def summary(self) -> str:
        ok = self.ordered()
        out = [f"추론 파견 — 통과 {len(ok)} / 파견 {len(self.items)}"
               + (f" · 건너뜀 {len(self.skipped)}" if self.skipped else "")
               + (f" · ${self.cost_usd:.4f}" if self.cost_usd else "")]
        for i, r in sorted(self.items, key=lambda kv: kv[0]):
            out.append(f"  [{i}] {r.task_id} → {r.worker or '-'}: {r.summary}")
        for tid, why in self.skipped:
            out.append(f"  [–] {tid}: [중요] 파견하지 않았다 — {why}")
        if ok:
            out.append("")
            out.append("적용 순서 (통합자가 이 순서로 순차 적용한다):")
            for n, r in enumerate(ok, 1):
                out.append(f"  {n}. {r.task_id} — " + ", ".join(sorted(r.files)))
        # [주의] 없는 것을 있는 척하지 않는다 — 중 1.4 가 아직 없다는 사실이 결과에 실린다
        out.append("")
        out.append("[주의] **적용은 아직 아무도 하지 않는다** — 통합자(중 1.4)가 비어 있다. "
                   "응답은 스풀에 남았고, 태스크는 `claimed` 로 남아 리스(1200초) 만료 뒤 "
                   "재확보된다. [중요] 그때도 같은 추론을 다시 사지는 않는다(스풀 재사용).")
        if self.note:
            out.append(self.note)
        return "\n".join(out)


# ── 다건 파견 (소 1.3.1) ────────────────────────────────────────────────────────

def _free_workers(facts, *, clean=None) -> tuple:
    """파견 가능한 워커 **전부**. `(고른 것들, [(host, 사유)])`.

    `pick_worker` 는 하나만 고른다 — 다건 파견은 **여러 대를 동시에** 봐야 하므로 같은 판정을
    전부에 적용해 목록으로 받는다. [중요] 판정 규칙은 하나뿐이어야 하니 `pick_worker` 를 재사용한다.
    """
    chosen: list = []
    rejected: list = []
    pool = list(facts)
    while pool:
        pick = runner.pick_worker(pool, clean=clean)
        if pick.chosen is None:
            rejected += [(h, r) for h, r in pick.rejected if "다른 워커를 먼저" not in r]
            break
        chosen.append(pick.chosen)
        pool = [f for f in pool if f is not pick.chosen]
    return chosen, rejected


def _skeleton_contract_reason(paths, base: str, want) -> str:
    """base 커밋의 실물 골조가 태그 계약을 지켰나. 통과면 `""`, 아니면 **막을 사유**.

    [주의] **읽지 못하면 막지 않는다** — 미러에 커밋이 없거나 git 이 없는 환경(테스트·
    오프라인)에서 「못 읽었다」를 「위반」으로 접으면 정상 파견이 죽는다. 대신 사유를 로그에
    남긴다. [중요] 반대로 **읽었는데 위반이면 막는다** — 그것이 이 게이트의 전부다.
    """
    try:
        from . import skeleton_gate as SG
        from .declarations import _mirror_git, ensure_commit
        ensure_commit(paths, base)
        files = {}
        for rel in want:
            txt = _mirror_git(paths, "show", f"{base}:{rel}", check=False)
            if (txt or "").strip():
                files[rel] = txt
        if not files:
            _log(f"[골조] base {base[:8]} 에서 대상 파일을 못 읽었다 — 계약 미확인")
            return ""
        return SG.check_tags(files)
    except Exception as e:                                   # noqa: BLE001
        _log(f"[골조] 계약을 재지 못했다 ({type(e).__name__}: {e}) — 미확인으로 진행한다")
        return ""


def _log(msg: str) -> None:
    """[중요] **파견 로그는 `[dispatch]` 접두어 하나로 모인다** — 「걸었는지」와 「왜 안 걸었는지」를
    둘 다 찍어야 침묵이 배선 사망과 구별된다(그 침묵이 2026-08-29~31 이틀을 태웠다).
    `autodispatch._log` 와 같은 형식을 쓰는 것이 요점이다 — journalctl 에서 한 줄기로 읽힌다.
    """
    print(f"[dispatch] {msg}", flush=True)


def dispatch_task(paths, facts, task, *, api=runner._api, work_id: str = "", order: int = 0,
                 runner_=None, reader=None, ssh=None,
                 timeout: int = runner.DEFAULT_TIMEOUT) -> Response:
    """집어 둔 태스크 하나를 워커에서 추론시키고 **스풀에 남긴다.**

    [중요] **큐에 제출하지 않는다** (§ 모듈 머리말). 대신 하트비트로 리스를 살려 두고, 응답을
    스풀에 원자적으로 쓴다 — 통합자가 없어도 산출물이 사라지지 않게.
    """
    task_id = str(task.get("task_id") or task.get("id") or "")
    if not task_id:
        raise DispatchError(f"claim 응답에 task_id 가 없다 — {str(task)[:160]}")

    # [중요] `#319` — 계층형 브랜치 이름은 work_id 없이는 만들 수 없다. 인자로 받은 값이
    #    없으면 태스크가 실어 온 값을 쓰고, 그래도 없으면 **막는다**(옛 평평한 이름으로
    #    조용히 접으면 조각이 골조 없는 base 에서 난다).
    work_id = (work_id or "").strip() or str(task.get("work_id") or "")
    if not work_id:
        raise DispatchError(f"work_id 가 없다 — 작업 브랜치를 못 정한다 (task={task_id})")

    # [중요] **읽을 지시서 문서가 없다** (매니페스트 철거 2026-09-02). 종전에는 등재 시점
    #    문서를 되읽어 기준 절만 다시 풀었다. 그 문서는 등재 시점(골조 없음)에 조립돼
    #    **자기 안에서 모순됐고**(실측 2026-09-01: 상단 "브랜치가 원격에 있다" / 하단
    #    "원격에 없다"), 관례도 `main` 실측으로 계약과 반대로 실었다. 지시서는 골조 주석이다.
    # [중요] 대상 파일은 **큐 레코드**에서 만든다 — 등재가 만든 그 목록이고, 판정(`want=`)과
    #    워커 지시가 **같은 하나**에서 나온다(그 등가성이 실측 2026-08-09 의 요구였다).
    want = [str(f) for f in (task.get("target_file"), task.get("header_file")) if f]
    if not want:
        raise DispatchError(f"큐 레코드에 target_file·header_file 이 없다 (task={task_id}) — "
                            f"무엇을 만들지 모르므로 파견하지 않는다")
    body = ""
    base = ""
    try:
        from . import twin_base
        base = twin_base.resolve(paths, work_id).commit or ""
    except Exception:                                    # noqa: BLE001
        # [주의] 기준 커밋을 모르면 **재사용 판정을 못 한다** — 그래도 파견은 막지 않는다.
        #    결손은 `Response.subbranch_error` 와 `[dispatch]` 로그에 남는다.
        base = ""

    # 🔴 **정본 ⑷ — 조각의 서브 브랜치를 작업 브랜치에서 갈라 둔다** (사용자 확정 2026-09-02).
    #    사용자 서술: *"작업 브랜치에서 갈라진 각각의 서브 브랜치를 만들고 워커들에게 브랜치와
    #    작업할 클래스를 전달해"*. 이름을 배정하는 것은 서버다(원전 `cluster_coordinator.py:11`
    #    *"서버가 브랜치명을 배정하므로 워커는 받은 이름을 쓸 뿐"*).
    # 🔴 [중요] **골조 태그 계약을 파견 직전에 잰다** (실측 2026-09-03). base 커밋의 **실물**
    #    을 읽는다 — 워커가 받는 것이 그것이고, 등재 시점에는 아직 push 되지 않아 볼 수 없다.
    # [중요] **워커 토큰이 나가기 직전이 마지막 싼 자리다.** 이 검사가 없어서 골조가 본문까지
    #    써 버린 채 파견됐고(13/13 실코드), 층2 도 층3 도 아니라 **층1** 이 막았다 —
    #    즉 워커 한 대의 추론값을 통째로 버린 뒤에 드러났다.
    if base:
        why_tags = _skeleton_contract_reason(paths, base, want)
        if why_tags:
            _log(f"[골조] {task_id} 파견 안 한다 — {why_tags}")
            res = Response(task_id=task_id, worker=facts.host, want=want,
                           base_commit=base, epoch=task.get("epoch"),
                           reason=f"골조 계약 위반 — {why_tags}")
            res.notes.append(f"[중요] {why_tags}")
            spool(paths, res, work_id=work_id, order=order)
            try:
                runner.submit_fail(task_id, runner.BLOCKED, why_tags,
                                   epoch=task.get("epoch"), worker_id=facts.host, api=api)
            except Exception as e:                           # noqa: BLE001
                res.notes.append(f"[주의] 반납도 실패했다 — {type(e).__name__}: {e}")
            return res

    # 🔴 [중요] **여기는 fail-closed 다** — ⑸ 가 이 브랜치에 커밋하므로 없으면 진행이 불가하다.
    #    (⑷ 를 만들 때는 비차단이었다. ⑸ 가 배선된 지금 그 유예가 끝났다.)
    sub_name = sub_err = ""
    if base:
        try:
            from . import subbranch as _sb
            _c = _sb.create(paths, work_id, task_id, base_commit=base, logf=_log)
            sub_name, sub_err = (_c.branch if _c.ok else ""), _c.error
        except Exception as e:                               # noqa: BLE001
            sub_name, sub_err = "", f"{type(e).__name__}: {e}"
    else:
        sub_err = "기준 커밋을 몰라 서브 브랜치를 만들지 않았다 (작업 브랜치 미확인)"
    if sub_err:
        _log(f"[subbranch] {task_id} 실패 — {sub_err}")

    if base:
        old = reusable(paths, task_id, base_commit=base, work_id=work_id)
        if old is not None:
            old.worker = old.worker or "(스풀)"
            # [중요] epoch 은 **이번 claim 의 것으로 갱신한다.** 재확보되면 epoch 가 올라가고,
            #    낡은 epoch 로 제출하면 큐가 stale 로 거부한다(fencing 은 그러라고 있다).
            old.epoch = task.get("epoch")
            old.subbranch, old.subbranch_error = sub_name, sub_err
            spool(paths, old, work_id=work_id, order=order)
            return old

    # 🔴 **정본 ⑸ — 워커가 자기 서브 브랜치에 커밋한다** (사용자 확정 2026-09-02).
    #    [중요] 서브 브랜치가 없으면 **여기서 멈춘다** — 커밋할 자리가 없다.
    if not sub_name:
        res = Response(task_id=task_id, worker=facts.host, want=want,
                       base_commit=base, epoch=task.get("epoch"),
                       subbranch="", subbranch_error=sub_err,
                       reason=f"서브 브랜치가 없어 파견하지 않는다 — {sub_err}")
        spool(paths, res, work_id=work_id, order=order)
        return res

    res = commit_task(paths, facts, task, work_id=work_id, base=base, want=want,
                      branch=sub_name, api=api, runner_=runner_, reader=reader, ssh=ssh,
                      timeout=timeout)
    res.subbranch, res.subbranch_error = sub_name, sub_err
    spool(paths, res, work_id=work_id, order=order)
    return res


def commit_task(paths, facts, task, *, work_id: str, base: str, want, branch: str,
                api=runner._api, runner_=None, reader=None, ssh=None,
                timeout: int = runner.DEFAULT_TIMEOUT) -> Response:
    """정본 ⑸ 한 바퀴: 워커가 본문을 쓰고 **마스터가 검증해 그 브랜치에 커밋**한다.

    사이클 자체는 `wcommit.py` 에 있다(원전 `worker/worker.py` 이식). 이 함수가 하는 것은
    **큐와의 연결**이다 — 하트비트로 리스를 살리고, 커밋이 생기면 **제출한다.**

    [중요] **제출이 여기 있다** (원전과 같은 자리): 원전 사이클은
    `... commit·push → submit_result → 다시 claim` 이고, 커밋이 생긴 시점이 곧 그 태스크가
    끝난 시점이다. 종전 구조는 제출을 통합자에 뒀는데, 그 때문에 리스가 붙잡힌 채 만료되고
    **같은 추론을 다시 사는** 자리가 됐다(실측 2026-09-01 `f0c13582` reclaims=1).

    [주의] 실패도 **반납한다**(`submit_fail`) — 집은 채로 죽으면 리스 1200초를 태운다.
    """
    from . import wcommit

    task_id = str(task.get("task_id") or task.get("id") or "")
    epoch = task.get("epoch")

    def llm(f, tid, files):
        """워커의 `ax-work` 를 한 번 돌린다. [중요] **본문만 쓴다** — git 은 안 만진다."""
        with runner._Beater(lambda: runner.heartbeat(tid, f.host, api=api)):
            return (runner_ or (lambda f_, t_, to_: runner.run_worker(
                f_, t_, files=files, runner=None, timeout=to_)))(f, tid, timeout)

    # 동결 대조 원본 — 마스터의 색인 클론이 같은 커밋이면 그것을 쓴다(왕복 0).
    # [주의] 없으면 `None` 이라 층1 이 **동결 미검사로 기록**한다 — 통과로 접지 않는다.
    try:
        from .integrate import local_baseline
        baseline = local_baseline(paths, base)
    except Exception as e:                                   # noqa: BLE001
        _log(f"[wcommit] {task_id} 동결 원본을 못 잡았다 — {type(e).__name__}: {e}")
        baseline = None

    c = wcommit.run(facts, task, work_id=work_id, base_commit=base, want=want,
                    llm=llm, ssh=ssh, reader=reader, baseline=baseline, branch=branch)

    res = Response(task_id=task_id, worker=facts.host, want=list(c.want),
                   files=dict(c.files), base_commit=base, epoch=epoch)
    if c.ok:
        res.status = runner.DONE
        _log(f"[wcommit] {task_id} {c.summary}")
        # [중요] **커밋이 생겼으므로 제출한다** (원전 `submit_result` 자리)
        out = runner.Outcome(status=runner.DONE, branch=c.branch, head=c.head,
                             tail=(c.reason or "")[-2000:])
        try:
            runner.submit(task_id, out, epoch=epoch, worker_id=facts.host, api=api)
        except Exception as e:                               # noqa: BLE001
            # [주의] 제출 실패는 **커밋을 되돌리지 않는다** — 코드는 브랜치에 안전하게 있다.
            #    사유만 남긴다(사람이 재제출한다). 조용히 성공으로 접지 않는다.
            res.notes.append(f"[중요] 커밋은 됐는데 큐 제출이 실패했다 — {type(e).__name__}: {e}")
            _log(f"[wcommit] {task_id} 제출 실패 — {e}")
    else:
        res.status = runner.BLOCKED
        res.reason = c.summary
        res.notes.extend(f"[중요] {v}" for v in c.layer1_violations[:5])
        _log(f"[wcommit] {task_id} {c.summary}")
        try:
            runner.submit_fail(task_id, runner.BLOCKED, c.summary,
                               epoch=epoch, worker_id=facts.host, api=api)
        except Exception as e:                               # noqa: BLE001
            res.notes.append(f"[주의] 반납도 실패했다 — {type(e).__name__}: {e}")
    return res


def run_many(paths, *, limit: int = 4, facts=None, project: str = "", api=runner._api,
             clean=runner.AUTO, parallel: bool = False, work_id: str = "",
             runner_=None, reader=None, ssh=None,
             timeout: int = runner.DEFAULT_TIMEOUT) -> Handoff:
    """큐에서 최대 `limit` 건을 집어 추론시키고, **인계 묶음**을 돌려준다 (소 1.3.1).

    [중요] **워커가 빌 때만 집는다.** 집어놓고 못 돌리는 것이 가장 나쁘다 — `run_once` 가 이미
    같은 규칙이다(리스가 1200초 붙잡히고 사람은 *"왜 아무것도 안 도나"* 를 본다).

    [중요] **병렬은 기본값이 아니다** (실측: 워커 2대 = 12% 빠르고 90% 비쌌다). `parallel=True` 는
    사람이 켜는 것이고, 조각이 클 때만 이득이다.

    [중요] **실패한 태스크의 후속(`depends_on`)은 파견하지 않는다.** 큐는 `failed` 를 의존 해소로
    **센다**(`logic_claim.py`: *"failed 도 dependents 차단 X — 영원 block 방지"*). 그 선택은
    큐 입장에서 맞지만, 뎁스 분할(`X.d1`→`X.d2`)에서는 앞 단계 없이 뒷 단계를 추론하면
    **헛일이 확실하다.** 이번 실행에서 실패한 것을 마스터가 기억해 막는다.
    """
    if facts is None:
        facts = [bundle.probe(h, u, p, d, r, dp)
                 for h, u, p, d, r, dp in bundle.workshops(project or paths.name)]
    if clean == runner.AUTO:
        clean = runner.cleanliness(project or paths.name)

    workers, rejected = _free_workers(facts, clean=clean)
    hand = Handoff(work_id=work_id)
    # [중요] `#318` 완료 조건 5 — 회수돼 돌아온 태스크를 **집었다는 사실**을 보고에 남긴다.
    #    claim 이 그것을 집으면서 `worker_id` 를 갱신하고 `epoch` 를 올린다(= 재파견이다).
    #    말하지 않으면 「처음 파견」과 「재파견」이 구분되지 않는다.
    try:
        _w = runner.waiting_summary(project or paths.name, api=api)
        if _w["reclaimed"]:
            hand.note = (f"[주의] 회수된 태스크 {_w['reclaimed']}건이 대기 중이다 — "
                         f"이번 파견이 그것을 다시 민다")
    except Exception:                                        # noqa: BLE001
        pass
    if not workers:
        hand.note = ("[중요] 파견할 워커가 없어 claim 조차 하지 않았다 — "
                     + ("; ".join(f"{h}: {r}" for h, r in rejected) or "후보 자체가 없다"))
        return hand
    if not parallel:
        workers = workers[:1]
        hand.note = ("[주의] 직렬로 돌렸다 (기본값) — 워커 2대는 실측에서 12% 빠르고 90% 비쌌다. "
                     "조각이 클 때만 `parallel=True` 를 켠다.")

    lock = threading.Lock()
    state = {"taken": 0, "failed": set(), "stop": False,
             # [중요] `#342` — 빈손인 워커를 센다. 전원이 빈손일 때만 「큐가 비었다」다.
             "idle": set(), "workers": len(workers)}

    def loop(f):
        while True:
            with lock:
                if state["stop"] or state["taken"] >= limit:
                    return
                state["taken"] += 1
                order = state["taken"]
            task = runner.claim(f.host, f.capabilities, api=api)
            if not task:
                # [중요] **빈 claim 은 「큐가 비었다」가 아니다** (`#342`, 실측 2026-08-30).
                #    능력 라우팅이 있으면 *"나에게 줄 게 없다"* 일 수 있다. 실측: `.43`(ue5 없음)
                #    이 `requires=[ue5]` 태스크 4건 앞에서 즉시 빈 값을 받았고, 그것을 「큐가
                #    비었다」로 읽어 **`.2` 까지 세웠다** — 첫 조각만 돌고 나머지 3건이 남았다.
                #    그래서 **자기 루프만** 끝내고, 모두가 빈손일 때만 전체를 세운다.
                with lock:
                    state["taken"] -= 1
                    state["idle"].add(f.host)
                    if len(state["idle"]) >= state["workers"]:
                        state["stop"] = True    # 전원이 빈손 — 그때가 「큐가 비었다」
                return
            task_id = str(task.get("task_id") or task.get("id") or "")
            deps = list(task.get("depends_on") or [])
            with lock:
                blocked = [d for d in deps if d in state["failed"]]
            if blocked:
                # [중요] 앞 단계가 이번에 실패했다. 추론해도 헛일이므로 **파견하지 않고 반납한다.**
                why = f"선행 {', '.join(blocked)} 이 이번 실행에서 실패했다"
                try:
                    # [중요] `#318` — 반납도 신원·epoch 게이트를 통과해야 한다. 이 태스크는
                    #    방금 `f.host` 로 claim 했으므로 그것이 소유자다.
                    runner.submit_fail(task_id, "선행 실패", why, api=api,
                                       epoch=task.get("epoch"), worker_id=f.host)
                except runner.QueueError as e:
                    why += f" · [중요] 반납 실패({e}) — 리스 만료까지 붙잡힌다"
                with lock:
                    hand.skipped.append((task_id, why))
                    state["failed"].add(task_id)
                continue
            try:
                res = dispatch_task(paths, f, task, api=api, work_id=work_id, order=order,
                                   runner_=runner_, reader=reader, ssh=ssh,
                                   timeout=timeout)
            except Exception as e:                       # noqa: BLE001
                # [중요] 집은 태스크를 붙잡은 채 죽지 않는다. 반납이 실패해도 사유를 남긴다.
                res = Response(task_id=task_id, worker=f.host,
                               reason=f"{type(e).__name__}: {e}")
                try:
                    runner.submit_fail(task_id, "파견 실패", res.reason, api=api,
                                       epoch=task.get("epoch"), worker_id=f.host)
                except Exception as e2:                  # noqa: BLE001
                    res.reason += f" · [중요] 반납 실패({e2}) — 리스 만료까지 붙잡힌다"
            with lock:
                hand.items.append((order, res))
                if not res.ok:
                    state["failed"].add(task_id)

    if len(workers) == 1:
        loop(workers[0])
    else:
        threads = [threading.Thread(target=loop, args=(f,), daemon=True) for f in workers]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    return hand


# [중요] **pull 회수 절(`#204` 2단계)은 걷었다** (2026-09-02). 판정 기준이 매니페스트 blob
#    sha 였고 그 문서가 없어졌으며, `#320` 이 상주를 걷은 뒤로는 **쓰는 주체가 없어 언제나
#    「결과 미도착」**이었다. 정본 ⑸ 는 워커가 커밋하므로 회수 자리가 `wcommit` 이다.


# ── CLI ──────────────────────────────────────────────────────────────────────────
#
#   python -m master.work.infer probe   [프로젝트]         누가 파견 가능한가 (큐 무접촉)
#   python -m master.work.infer run     [프로젝트] [N]     최대 N건 추론 (직렬)
#   python -m master.work.infer run-p   [프로젝트] [N]     [중요] 병렬 — 사람이 켠다
#   python -m master.work.infer spool   [프로젝트] [work]  스풀에 무엇이 있나
#
# [중요] 데몬으로 만들지 않는다(§5.5.4). 상주가 필요하면 systemd timer 로 `run` 을 부른다.

def _cli_spool(paths, work_id: str) -> int:
    d = spool_dir(paths, work_id)
    if not d.is_dir():
        print(f"스풀이 없다: {d}")
        return 0
    recs = sorted(d.glob(f"*{SPOOL_SUFFIX}"))
    print(f"스풀 {d} — {len(recs)}건")
    for p in recs:
        rec = json.loads(p.read_text(encoding="utf-8"))
        n = len(rec.get("files") or {})
        mark = "[완료]" if rec.get("status") == runner.DONE and n else "[중요]"
        print(f"  {mark} [{rec.get('order', 0)}] {rec.get('task_id')} · 파일 {n} · "
              f"기준 {(rec.get('base_commit') or '?')[:8]} · {rec.get('at', '')}"
              + (f" · {rec.get('reason')}" if rec.get("reason") else ""))
    return 0


def main(argv) -> int:
    from ..context_search.paths import resolve
    cmd = (argv[0] if argv else "probe").strip()
    project = argv[1] if len(argv) > 1 else ""
    paths = resolve(project)

    if cmd == "spool":
        return _cli_spool(paths, argv[2] if len(argv) > 2 else "")

    facts = [bundle.probe(h, u, p, d, r, dp) for h, u, p, d, r, dp in bundle.workshops(paths.name)]
    if cmd == "probe":
        workers, rejected = _free_workers(facts, clean=runner.cleanliness(paths.name))
        print(f"프로젝트 {paths.name}")
        for f in facts:
            print("  " + f.summary)
        print(f"추론 가능: {', '.join(f.host for f in workers) or '[중요] 없다'}")
        for h, r in rejected:
            print(f"  제외 {h}: {r}")
        # [중요] `#318` 완료 조건 5 — **집히기를 기다리는 것을 보여 준다.** `reclaim` 이 되돌린
        #    태스크는 push 모델에서 **집을 주체가 없어** 마스터가 다시 밀어야 하고, 상주가
        #    철거된 지금(`#320`) 그 루프는 사람이 시작한다. 안 보이면 조용히 멈춘다.
        w = runner.waiting_summary(paths.name)
        if w["pending"] or w["stuck"]:
            print(f"\n대기: pending {w['pending']} · stuck {w['stuck']}"
                  + (f" · [주의] 회수된 것 {w['reclaimed']}건 — `infer run` 이 다시 민다"
                     if w["reclaimed"] else ""))
            for ln in w["lines"][:10]:
                print("  " + ln)
            if w["stuck"]:
                print("  [중요] `stuck` 은 재파견 대상이 아니다 — 회수 3회 초과로 큐가 손들었다. "
                      "사람이 볼 것")
        else:
            for ln in w["lines"]:
                print("  " + ln)
        return 0
    if cmd in ("run", "run-p"):
        n = int(argv[2]) if len(argv) > 2 else 4
        hand = run_many(paths, limit=n, facts=facts, parallel=(cmd == "run-p"))
        print(hand.summary())
        return 0
    print(__doc__.split("## ")[0])
    print("  probe | run | run-p | spool")
    return 2


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
