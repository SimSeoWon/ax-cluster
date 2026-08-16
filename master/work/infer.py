"""추론 파견 — 워커는 읽고 추론하고 **텍스트로 답한다** (중 1.3 · §4.5 · §8.4).

## [중요] 무엇이 `runner.py` 와 다른가 — 쓰는 주체가 하나다

    runner.py    (구 토폴로지) 워커가 고치고 커밋하고 attempt push → 마커로 판정
    infer.py     (현 토폴로지) [중요] 워커는 **추론만** → 응답을 모아 **통합자에게 순서대로 넘긴다**

사용자 확정 2026-08-11. `runner.py` 를 **지우지 않는다** — N-writer 기계장치는 측정으로
뒤집힐 여지가 있는 동안 되돌릴 수 있게 둔다(§8.4 [주의]). 워커에는 스킬이 둘 배달돼 있고
(`ax-work`·`ax-infer`), **파견 지시가 이름으로 고른다.**

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
INFER_INSTRUCTION = (
    "Follow the ax-infer skill (INFERENCE ONLY, not ax-work). "
    "Read ./{work}/{task}/manifest.md and do exactly what it says. "
    "Judge from the source files in this checkout, not from memory. "
    "Do NOT edit source files, do NOT commit, do NOT push, do NOT create branches. "
    "Write the complete new content of every target file to ./{work}/{task}/{resp} as UTF-8, "
    "one block per file, each starting with a line: === FILE: <path from the manifest> === . "
    "That file must contain ONLY those blocks: do NOT write RESPONSE: or RESULT: into it. "
    "Then PRINT to stdout, as the last two non-empty lines you print and nothing after them: "
    "RESPONSE: <number of files> / RESULT: DONE "
    "(print RESULT: BLOCKED instead if you could not finish, and say why above it)."
)

_RESPONSE_MARK = re.compile(r"^RESPONSE:\s*(\d+)\s*$")
# [중요] 응답 **파일 끝**에 붙은 마커 — 실전 첫 구동에서 나왔다(2026-08-12). 아래 § 참조.
_TRAILING_MARK = re.compile(r"^(RESPONSE:\s*\d+|RESULT:\s*(DONE|BLOCKED).*)$")
# 매니페스트의 「대상 파일」 절 — 마스터가 자기가 쓴 형식을 되읽는다(`manifest.build`)
_TARGET_HEADING = "## 대상 파일"
_BULLET = re.compile(r"^-\s*`([^`]+)`\s*$")


class DispatchError(RuntimeError):
    """파견 자체가 불가능하다 — [중요] 태스크를 집은 채로 죽지 않게 호출자가 반납한다."""


# ── 대상 파일 — [중요] 마스터가 **말한 것**만 받는다 ────────────────────────────────

def target_files_from(manifest_text: str) -> list:
    """매니페스트의 「대상 파일」 절을 되읽는다. **LLM 0 · 결정적.**

    [중요] **큐 레코드가 아니라 매니페스트에서 읽는 이유**: 워커가 본 것이 이것이다. 큐의
    `target_file` 은 단수이고(여러 개면 첫 번째만), 실측 2026-08-09 에 *"워커는 어느 파일을
    고칠지를 `contracts` 산문에서 우연히 읽고 있었다"* 가 나온 그 자리다. **판정 기준과 지시가
    같은 문서에서 나와야** 어긋나지 않는다.
    """
    want: list = []
    inside = False
    for line in (manifest_text or "").replace("\r", "").split("\n"):
        s = line.strip()
        if s.startswith("## "):
            inside = s.startswith(_TARGET_HEADING)
            continue
        if not inside:
            continue
        m = _BULLET.match(s)
        if m:
            f = m.group(1).strip()
            if f and f not in want:
                want.append(f)
    return want


# ── 판정 ────────────────────────────────────────────────────────────────────────

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


def infer_command(facts, task_id: str) -> str:
    """워커에서 실제로 도는 한 줄. [중요] 경로는 레지스트리에서 온 값(`facts.path`)이다."""
    instr = INFER_INSTRUCTION.format(work=bundle.WORK_REL, task=task_id, resp=RESPONSE_NAME)
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
        res.reason = ("대상 파일 목록이 비었다 — 매니페스트의 「대상 파일」 절을 못 읽었다. "
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


def infer_task(facts, task_id: str, manifest_text: str, *, want=None, beat=None, runner_=None,
               deliver=None,
          writer=None, reader=None, timeout: int = runner.DEFAULT_TIMEOUT) -> Response:
    """파견 한 건: 배달 → 추론(하트비트 유지) → 응답 되읽기 → 판정.

    [중요] **큐를 만지지 않고, 응답을 적용하지도 않는다.** 이 함수는 *워커가 무엇을 답했는가* 만
    돌려준다 — 적용·빌드·커밋은 통합자(중 1.4)의 일이다.
    """
    files_wanted = list(want) if want is not None else target_files_from(manifest_text)
    # [중요] 배달 주입 자리 — 실전은 git-carried(carry.deliverer, #185 판정 2026-08-17),
    #    writer 주입(테스트·레거시)은 scp 그대로. 조용한 폴백은 없다 — 어느 경로로 돌았는지
    #    모르게 되는 것이 최악이다.
    if deliver is not None:
        deliver(facts, task_id, manifest_text)
    else:
        runner.deliver_manifest(facts, task_id, manifest_text, writer=writer)
    with runner._Beater(beat) as b:
        rc, out = (runner_ or _default_runner)(facts, task_id, timeout)
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


def _default_runner(facts, task_id: str, timeout: int) -> tuple:
    return bundle._ssh(facts.host, facts.user, infer_command(facts, task_id), timeout=timeout)


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
        epoch=rec.get("epoch"), reused=True)


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


def dispatch_task(paths, facts, task, *, api=runner._api, work_id: str = "", order: int = 0,
                 runner_=None, writer=None, reader=None, deliver=None,
                 timeout: int = runner.DEFAULT_TIMEOUT) -> Response:
    """집어 둔 태스크 하나를 워커에서 추론시키고 **스풀에 남긴다.**

    [중요] **큐에 제출하지 않는다** (§ 모듈 머리말). 대신 하트비트로 리스를 살려 두고, 응답을
    스풀에 원자적으로 쓴다 — 통합자가 없어도 산출물이 사라지지 않게.
    """
    task_id = str(task.get("task_id") or task.get("id") or "")
    if not task_id:
        raise DispatchError(f"claim 응답에 task_id 가 없다 — {str(task)[:160]}")

    body = runner.refresh_base(runner._manifest_for(paths, task_id), paths, task_id)
    want = target_files_from(body)
    base = ""
    try:
        from . import twin_base
        base = twin_base.resolve(paths, task_id).commit or ""
    except Exception:                                    # noqa: BLE001
        # [주의] 기준 커밋을 모르면 **재사용 판정을 못 한다** — 그래도 파견은 막지 않는다.
        #    매니페스트 자체가 이미 그 결손을 적어서 워커에게 간다.
        base = ""

    if base:
        old = reusable(paths, task_id, base_commit=base, work_id=work_id)
        if old is not None:
            old.worker = old.worker or "(스풀)"
            # [중요] epoch 은 **이번 claim 의 것으로 갱신한다.** 재확보되면 epoch 가 올라가고,
            #    낡은 epoch 로 제출하면 큐가 stale 로 거부한다(fencing 은 그러라고 있다).
            old.epoch = task.get("epoch")
            spool(paths, old, work_id=work_id, order=order)
            return old

    # [중요] 실전 배달 = git-carried (#185 판정). writer/deliver 주입이 없을 때만 켠다 —
    #    테스트는 writer 로 scp 자리를 그대로 잰다.
    if deliver is None and writer is None:
        from . import carry
        _d = carry.deliverer(paths)
        deliver = lambda f_, t_, txt: _d(f_, t_, txt)     # noqa: E731

    res = infer_task(facts, task_id, body, want=want,
                beat=lambda: runner.heartbeat(task_id, facts.host, api=api),
                runner_=runner_, writer=writer, reader=reader, deliver=deliver,
                timeout=timeout)
    res.base_commit = base
    res.epoch = task.get("epoch")
    spool(paths, res, work_id=work_id, order=order)
    return res


def run_many(paths, *, limit: int = 4, facts=None, project: str = "", api=runner._api,
             clean=runner.AUTO, parallel: bool = False, work_id: str = "",
             runner_=None, writer=None, reader=None,
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
        facts = [bundle.probe(h, u, p, d, r)
                 for h, u, p, d, r in bundle.workshops(project or paths.name)]
    if clean == runner.AUTO:
        clean = runner.cleanliness(project or paths.name)

    workers, rejected = _free_workers(facts, clean=clean)
    hand = Handoff(work_id=work_id)
    if not workers:
        hand.note = ("[중요] 파견할 워커가 없어 claim 조차 하지 않았다 — "
                     + ("; ".join(f"{h}: {r}" for h, r in rejected) or "후보 자체가 없다"))
        return hand
    if not parallel:
        workers = workers[:1]
        hand.note = ("[주의] 직렬로 돌렸다 (기본값) — 워커 2대는 실측에서 12% 빠르고 90% 비쌌다. "
                     "조각이 클 때만 `parallel=True` 를 켠다.")

    lock = threading.Lock()
    state = {"taken": 0, "failed": set(), "stop": False}

    def loop(f):
        while True:
            with lock:
                if state["stop"] or state["taken"] >= limit:
                    return
                state["taken"] += 1
                order = state["taken"]
            task = runner.claim(f.host, f.capabilities, api=api)
            if not task:
                with lock:
                    state["taken"] -= 1
                    state["stop"] = True        # 큐가 비었다 — 다른 워커도 그만둔다
                return
            task_id = str(task.get("task_id") or task.get("id") or "")
            deps = list(task.get("depends_on") or [])
            with lock:
                blocked = [d for d in deps if d in state["failed"]]
            if blocked:
                # [중요] 앞 단계가 이번에 실패했다. 추론해도 헛일이므로 **파견하지 않고 반납한다.**
                why = f"선행 {', '.join(blocked)} 이 이번 실행에서 실패했다"
                try:
                    runner.submit_fail(task_id, "선행 실패", why, api=api)
                except runner.QueueError as e:
                    why += f" · [중요] 반납 실패({e}) — 리스 만료까지 붙잡힌다"
                with lock:
                    hand.skipped.append((task_id, why))
                    state["failed"].add(task_id)
                continue
            try:
                res = dispatch_task(paths, f, task, api=api, work_id=work_id, order=order,
                                   runner_=runner_, writer=writer, reader=reader,
                                   timeout=timeout)
            except Exception as e:                       # noqa: BLE001
                # [중요] 집은 태스크를 붙잡은 채 죽지 않는다. 반납이 실패해도 사유를 남긴다.
                res = Response(task_id=task_id, worker=f.host,
                               reason=f"{type(e).__name__}: {e}")
                try:
                    runner.submit_fail(task_id, "파견 실패", res.reason, api=api)
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


# ── CLI ──────────────────────────────────────────────────────────────────────────
#
#   python -m master.work.infer probe  [프로젝트]         누가 파견 가능한가 (큐 무접촉)
#   python -m master.work.infer run    [프로젝트] [N]     최대 N건 추론 (직렬)
#   python -m master.work.infer run-p  [프로젝트] [N]     [중요] 병렬 — 사람이 켠다
#   python -m master.work.infer spool  [프로젝트] [work]  스풀에 무엇이 있나
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

    facts = [bundle.probe(h, u, p, d, r) for h, u, p, d, r in bundle.workshops(paths.name)]
    if cmd == "probe":
        workers, rejected = _free_workers(facts, clean=runner.cleanliness(paths.name))
        print(f"프로젝트 {paths.name}")
        for f in facts:
            print("  " + f.summary)
        print(f"추론 가능: {', '.join(f.host for f in workers) or '[중요] 없다'}")
        for h, r in rejected:
            print(f"  제외 {h}: {r}")
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
