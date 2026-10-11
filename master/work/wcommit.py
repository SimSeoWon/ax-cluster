"""정본 ⑸-a — **워커가 자기 서브 브랜치에 커밋한다** (사용자 확정 2026-09-02).

사용자 서술 7단계 ⑤: *"작업을 전달받은 워커들은 해당 파일의 서술된 내용을 바탕으로 …
내용물을 코드로 변환하고 **각각 지정된 서브 브랜치에 커밋**하고 작업을 마치고 다음 작업을
요청해"*.

## [중요] 원전을 그대로 옮긴다 — 사이클은 원전 `worker/worker.py` 것이다

    docs/distributed-workers.md § 워커 사이클 (per task)
      claim → git fetch --all --prune → git reset --hard HEAD → git checkout -B <branch> <base_commit>
            → spawn `claude -p` (prompt 에 target_file/스켈레톤/컨텍스트 주입)
            → 디스크 검증: [PSEUDO] 마커 0 · 빈 함수 본문 없음 · 마크다운 펜스 잔재 없음
            → git add <target_files> → git commit → git push --force-with-lease
            → submit_result → 다음 사이클

[중요] **git 은 LLM 이 만지지 않는다.** 원전에서 checkout·add·commit·push 는 데몬의
`git_ops.py` 가 결정적으로 하고, LLM 은 **파일 본문만** 쓴다. 그 분리를 유지한다 — 커밋
경계를 LLM 판단에 맡기면 무엇이 들어갔는지 아무도 모른다.

[주의] **지금은 상주 데몬이 없어 마스터가 SSH 로 그 사이클을 돈다**(⑸-b 가 상주를 되살리면
같은 함수가 워커 로컬에서 돈다 — 그래서 명령 생성과 실행을 갈라 뒀다). `#320` 이 걷은 것이
데몬이고, 사이클 자체는 이 파일이 들고 있다.

## [중요] 검증은 마스터가 한다 — 워커의 선의에 의존하지 않는다

원전은 `worker/validator.py` 가 **제출 전에 워커 안에서** 자기검증했다. 우리는 `layer1` 을
**마스터에서** 돌린다. 근거는 실측이다(`layer1.py` 머리말): *"워커는 실제로 계약을 어겼다 —
마커를 응답 파일에 써 넣었다"*. 그래서 순서가 원전과 한 칸 다르다:

    원전   LLM → (워커가) 검증 → 커밋 → push
    우리   LLM → **되읽어 마스터가 검증** → 통과분만 커밋 → push       ← verify-then-commit

[중요] **그 순서가 계약이다.** 위반이면 **커밋하지 않는다** — 깨진 것이 서브 브랜치에 박히면
⑺ 통합이 그것을 물고, 원전이 정확히 그 사고를 냈다(빌드를 등재 뒤에 둬서 깨진 골조가
`origin` 에 박히고 워커 전원이 그 위에서 작업).

## [주의] `--force-with-lease` 를 그대로 쓴다 — 다만 이유가 좁다

원전 주석: *"직전 attempt 가 reclaim 으로 무효화된 후 같은 host 가 재청구하면 origin 에
남아있는 직전 commit chain 을 덮어써야 함. lease 옵션은 fetch 직후 본 remote tip 과 다르면
거절하므로 진짜 동시성 충돌은 차단됨."* 서브 브랜치는 (work, task) 가 독점하므로 같은 논리가
성립한다. [중요] **`--force` 는 쓰지 않는다** — lease 없는 force 는 남의 커밋을 지운다.
"""
from __future__ import annotations

import os
import re
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from . import branch_names, layer1
from .runner import DispatchError


def _log(msg: str) -> None:
    """파견 로그 한 줄 — `infer._log` 와 **같은 형식**(`[dispatch]` 접두어)이라 journalctl 에서
    한 줄기로 읽힌다. [주의] 테스트는 이 자리를 바꿔 끼운다(`#818`)."""
    print(f"[dispatch] {msg}", flush=True)


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _last_frame(exc: BaseException) -> str:
    """예외의 마지막 프레임 → `파일:줄 in 함수` (`#818`). 저장소 안이면 상대 경로, 밖이면 파일명만.

    [주의] 절대 경로를 큐 기록에 싣지 않는다 — 사유(`c.reason`)는 화면·일감으로 나간다.
    """
    try:
        fr = traceback.extract_tb(exc.__traceback__)[-1]
    except IndexError:
        return "?"
    try:
        name = Path(fr.filename).resolve().relative_to(_REPO_ROOT).as_posix()
    except (ValueError, OSError):
        name = Path(fr.filename).name
    return f"{name}:{fr.lineno} in {fr.name}"

# 원전 커밋 메시지 규약 (`docs/distributed-workers.md` § 워커 사이클)
COMMIT_FMT = "[task:{task_id}] worker={host} target={target}"
# 🔴 [중요] 사이클이 끝나면 **`main` 으로 돌아오고 그 작업의 흔적을 전부 지운다**
# (사용자 2026-09-04: *"작업 워커는 그냥 임시 저장소로 쓰는거야. 거기 뭘 남길 필요가 없어"*).
# 지우는 것: 조각 브랜치 · 원격추적 캐시 · `.ax/work/<task_id>`. 커밋은 push 된 순간
# 원격에 있고, 통과 못 한 본문은 마스터 스풀에 원문이 남는다.
#    실측 2026-09-03: 이 단계가 없어서 `.2` 가 조각 브랜치에 체크아웃된 채 남았고, 그러면
#    **정리기가 그 브랜치를 영영 못 지운다**(체크아웃된 브랜치는 삭제 대상에서 빠진다).
#    작업물은 이미 원격에 있으므로 돌아와도 잃는 것이 없다.
HOME_BRANCH = "main"
PUSH_TIMEOUT = 300
GIT_TIMEOUT = 180


@dataclass
class Committed:
    task_id: str = ""
    branch: str = ""
    head: str = ""                                  # 워커가 만든 커밋
    files: dict = field(default_factory=dict)       # 되읽은 본문 {경로: 내용}
    want: list = field(default_factory=list)
    layer1_violations: list = field(default_factory=list)
    layer2_findings: list = field(default_factory=list)
    layer2_failure: str = ""
    notes: list = field(default_factory=list)       # [주의] 로 시작하는 것은 비치명 경고다
    stage: str = ""                                 # 어디까지 갔나 (실패 지점)
    reason: str = ""
    # 🔴 **할 일이 없던 조각** (원전 `worker/validator.py:547` = `ok_no_op`).
    #    골조에 `[PSEUDO]` 가 하나도 없으면 그것은 **완성된 파일**이고(`skeleton.py` 머리말),
    #    워커가 그대로 돌려준 것이 정답이다. 그때 커밋은 생기지 않는다 — **실패가 아니다.**
    no_op: bool = False
    # 🔴 **파견 계측** (`#387`) — 본문 작성 호출이 쓴 것. `runner.Outcome.usage` 와 **같은 모양**.
    #    [중요] **rc≠0 일 때도 채운다** — 실패한 실행도 토큰은 태웠다(사용자 지적 2026-09-08).
    #    비어 있으면 **모른다**는 뜻이고, 0 이 아니다.
    usage: dict = field(default_factory=dict)
    seconds: float = 0.0                            # 본문 작성에 걸린 시간

    @property
    def missing(self) -> list:
        return [w for w in self.want if not (self.files.get(w) or "").strip()]

    @property
    def ok(self) -> bool:
        """[중요] **fail-closed.** 커밋 해시가 있고 층1 위반이 없고 빠진 파일이 없어야 통과다.

        [주의] 예외는 `no_op` 하나다 — 골조에 `[PSEUDO]` 가 없어 **채울 것이 없던** 조각이고,
        원전이 `ok_no_op` 으로 통과시키는 그 경우다. 커밋 해시가 없는 것이 정상이다.
        """
        if self.no_op:
            return not self.layer1_violations and not self.missing
        return (bool(self.head) and not self.reason
                and not self.layer1_violations and not self.missing)

    @property
    def summary(self) -> str:
        if self.no_op:
            return (f"[완료] 할 일이 없는 조각이었다 — 골조에 `[PSEUDO]` 가 0개다 "
                    f"({self.branch} · 파일 {len(self.files)}). 커밋 없음이 정상이다")
        if self.ok:
            return f"[완료] {self.branch} ← {self.head[:8]} · 파일 {len(self.files)}"
        bits = [f"[중요] {self.stage or '미상'}"]
        if self.reason:
            bits.append(self.reason)
        if self.layer1_violations:
            bits.append(f"층1 위반 {len(self.layer1_violations)}: "
                        + "; ".join(self.layer1_violations[:2]))
        if self.missing:
            bits.append(f"빠진 파일 {len(self.missing)}: {', '.join(self.missing[:3])}")
        return " — ".join(bits)


def _q(path: str, windows: bool) -> str:
    return path.replace("/", "\\") if windows else path


def checkout_command(facts, branch: str, base_commit: str) -> str:
    """원전 `git_ops.checkout_base` 의 한 줄판.

    [중요] **`clean -fd` 에 `-x` 를 붙이지 않는다** (원전 주석 그대로): `.gitignore` 대상
    (`.ax/` · UE `Intermediate`/`Saved`/`Binaries`)까지 지우면 인프라·캐시가 날아간다.
    [주의] `reset --hard` 는 미커밋 변경을 지운다 — 워커 클론은 **파이프라인 소유**라서
    성립하는 것이고, `.33`(사람 기계)에 이 명령을 절대 돌리지 않는다.
    """
    cd = f'cd /d "{facts.path}"' if facts.windows else f'cd "{facts.path}"'
    return (f'{cd} && git fetch --all --prune --quiet && git reset --hard --quiet HEAD && '
            f'git clean -fd && git checkout -q -B "{branch}" "{base_commit}" && '
            f'{delegation_dirs_command(facts)} && '
            f'git rev-parse HEAD')


def delegation_dirs_command(facts) -> str:
    """`.agy-work/in`·`out` 을 **비운 채로 세운다** (`#764`, 사용자 결정 2026-10-09 ① · 위치는 같은 날 `.ax` 밖으로).

    🔴 실측 2026-10-09 `.2` 세션1: 지휘자가 `rg --files … .ax/work/agy-out` 으로 경로를 확인하다
    폴더가 없어 rc=1 이 나자 *"저장소의 실패 시 중단 규칙에 따라 멈췄습니다"* 로 `BLOCKED` 했다
    (AXCluster 체크아웃의 대화형 규칙을 워커가 따랐다). **폴더가 늘 있으면 그 갈림길이 없다** —
    지휘자의 판단에 기대지 않고 막힌 원인을 없앤다. 비우는 이유: 죽은 지난 사이클의 응답을 이번
    조각으로 회수하지 않기 위해서다. 실패해도 체크아웃을 실패로 만들지 않는다(관용).
    """
    root = _agy_dir(facts)
    if facts.windows:
        mk = " & ".join(f'mkdir "{_agy_dir(facts, n)}"' for n in (AGY_IN, AGY_OUT))
        return f'((if exist "{root}" rmdir /s /q "{root}") & {mk} || ver >nul)'
    ds = " ".join(f'"{_agy_dir(facts, n)}"' for n in (AGY_IN, AGY_OUT))
    return f'(rm -rf "{root}" && mkdir -p {ds} || true)'



def return_home_command(facts, home: str = HOME_BRANCH, branch: str = "",
                        task_id: str = "") -> str:
    """사이클 종료 자세 — `main` 으로 복귀하고 **그 조각 브랜치를 지운다.**

    🔴 [중요] **워커는 임시 저장소다 — 거기 남길 것이 없다** (사용자 2026-09-04:
    *"작업 워커는 그냥 임시 저장소로 쓰는거야. 거기 뭘 남길 필요가 없어"*).
    커밋은 push 된 순간 원격(gitea)에 있고, 통과 못 한 본문은 마스터 스풀에 원문이 남는다.
    로컬 브랜치를 남겨 둘 이유가 없다.

    [주의] **종전에는 복귀만 하고 브랜치를 남겼다.** 지우는 판정을 `cleanup.py` 가
    「팁이 `origin/main` 에서 도달 가능한가」로 했는데, 전진분은 `main` 이 아니라 작업
    브랜치로 들어가므로 그 기준으로는 **영원히 「도달 불가 = 보존」** 이었다. 실측
    2026-09-04: 라운드 하나에 `.2`·`.43`·`.33` 세 기계 모두에 조각 브랜치가 쌓였고
    사람이 손으로 걷어냈다. 그 「보존」 규칙은 사용자 결정이 아니라 내가 붙인 것이다.

    [중요] **원전이 이 단계를 갖고 있고 이유가 정리다**: 체크아웃된 브랜치는 `git branch -d`
    대상에서 빠지므로, 조각 브랜치에 서 있는 채로 끝나면 병합 뒤에도 지워지지 않는다.
    실측 2026-09-03 에 `.2` 가 정확히 그 상태로 남았다.
    [주의] 실패해도 커밋을 되돌리지 않는다 — 산출물은 이미 원격에 있다. 사유만 남긴다.
    """
    cd = f'cd /d "{facts.path}"' if facts.windows else f'cd "{facts.path}"'
    # [중요] **먼저 트리를 정리한다.** 실측 2026-09-03: 층1 에서 막힌 조각의 미커밋 본문이
    #    남아 `git checkout main` 이 *"local changes would be overwritten"* 로 거부됐고,
    #    그래서 워커가 조각 브랜치에 남았다. 테스트가 잡은 자리다.
    # [주의] **버리는 것이 안전한 이유**: ⑴ 이 트리는 파이프라인 소유다(사람 트리가 아니다 —
    #    `.33` 에 이 명령을 절대 돌리지 않는다) ⑵ 통과한 본문은 이미 커밋·push 됐고,
    #    막힌 본문은 **스풀에 원문이 남는다**(`Response.files`) — 증거를 잃지 않는다
    #    ⑶ 다음 사이클의 `checkout_base` 가 어차피 `reset --hard` 로 시작한다.
    # [주의] 브랜치 삭제는 **복귀 뒤**다 — 체크아웃돼 있으면 `-D` 가 거부된다.
    #    전부 `|| true`(윈도우 `|| ver >nul`)로 관용한다: 이미 없어도 사이클을 실패로 만들지
    #    않는다. 판정은 마지막 `rev-parse` 가 `main` 을 찍는가 하나다.
    tolerate = "ver >nul" if facts.windows else "true"
    steps = [f'git checkout -q "{home}"']
    if branch:
        steps.append(f'(git branch -D "{branch}" -q || {tolerate})')
    # 원격추적 캐시도 남기지 않는다 — 원격에서 지워도 prune 전까지 남는다(실측 2026-09-01)
    steps.append(f'(git remote prune origin -q || {tolerate})')
    if task_id:
        art = (f'{facts.path}\\.ax\\work\\{task_id}' if facts.windows
               else f'{facts.path}/.ax/work/{task_id}')
        steps.append(f'(rmdir /s /q "{art}" || {tolerate})' if facts.windows
                     else f'(rm -rf "{art}" || {tolerate})')
        # `#764` — 위임 폴더도 지운다(회수는 복귀 **전에** `collect_delegations` 가 했다)
        agy = _agy_dir(facts)
        # [주의] 바깥 괄호가 필요하다 — cmd 에서 `&` 는 `&&` 보다 약해, 없으면 앞 단계 실패와 무관하게 뒤가 돈다
        steps.append(f'((if exist "{agy}" rmdir /s /q "{agy}") & ver >nul)' if facts.windows
                     else f'(rm -rf "{agy}" || {tolerate})')
    steps.append('git rev-parse --abbrev-ref HEAD')
    return f'{cd} && git reset --hard -q HEAD && git clean -fdq && ' + " && ".join(steps)


def commit_command(facts, branch: str, task_id: str, targets, message: str = "") -> str:
    """원전 `git_ops.commit_and_push` 의 한 줄판. **명시 add — `add -A` 는 쓰지 않는다.**

    [중요] 전수 add 를 금지하는 이유는 원전과 같다 — 사람의 WIP 를 삼킨다. 대상은 큐 레코드가
    준 목록뿐이고, 그 목록은 판정(`want`)과 **같은 하나**에서 나온다.
    """
    if not targets:
        raise DispatchError(f"{task_id}: 커밋할 대상 파일이 없다 — 빈 커밋을 만들지 않는다")
    cd = f'cd /d "{facts.path}"' if facts.windows else f'cd "{facts.path}"'
    msg = message or COMMIT_FMT.format(task_id=task_id, host=facts.host,
                                       target=targets[0])
    adds = " ".join(f'"{_q(t, facts.windows)}"' for t in targets)
    # [주의] `--force-with-lease` — 이유는 머리말 § 참조. `--force` 아님.
    # 🔴 [중요] **빈 커밋을 관용한다** (원전 `git_ops.py:149` — `"nothing to commit"` 은 에러가
    #    아니다). 종전에는 `&&` 사슬이라 커밋이 실패하면 `rev-parse` 까지 안 갔고, 그래서
    #    호출자가 **git 의 지역화된 메시지를 읽어야** 했다. 실측 2026-09-03: 이 저장소의 git 은
    #    한국어로 답한다 — *"커밋할 사항 없음, 작업 폴더 깨끗함"*. 영어 문구만 보면 못 잡는다.
    #    관용하고 `rev-parse` 를 항상 돌리면 판정이 **`HEAD == base` 하나**로 끝난다(지역화 무관).
    tolerate = "ver >nul" if facts.windows else "true"
    return (f'{cd} && git add {adds} && (git commit -q -m "{msg}" || {tolerate}) && '
            f'git push --quiet --force-with-lease -u origin "{branch}" && '
            f'git rev-parse HEAD')


_SHA = re.compile(r"^[0-9a-f]{40}$")


def _last_sha(out: str) -> str:
    for ln in reversed((out or "").splitlines()):
        s = ln.strip()
        if _SHA.match(s):
            return s
    return ""


def run(facts, task, *, work_id: str, base_commit: str, want, llm,
        ssh=None, reader=None, baseline=None, branch: str = "", verifier=None) -> Committed:
    """워커 한 대에서 ⑸-a 사이클을 한 바퀴 돈다. **예외를 던지지 않고 사유를 담아 돌려준다.**

    `llm(facts, task_id, files)` — 본문을 쓰게 하는 호출(주입). 반환은 `(rc, stdout)`.
    `ssh(facts, cmd, timeout)` · `reader(facts, abs_path)` — 주입 자리(테스트·오프라인).
    `baseline(path)` — 동결 대조용 원본 본문(층1). 없으면 동결 검사는 **미검사로 기록**된다.
    `verifier(files)` — 층2 Verdict. 누락·예외·승인되지 않은 판정이면 커밋하지 않는다.
    """
    task_id = str(task.get("task_id") or task.get("id") or "")
    c = Committed(task_id=task_id, want=[str(w) for w in (want or [])])
    if not task_id:
        c.stage, c.reason = "입력", "claim 응답에 task_id 가 없다"
        return c
    if not c.want:
        c.stage, c.reason = "입력", "대상 파일이 비었다 — 무엇을 만들지 모르므로 돌리지 않는다"
        return c
    base = (base_commit or "").strip()
    if not base:
        c.stage, c.reason = "입력", "기준 커밋이 비었다 — 어느 골조 위에서 작업할지 모른다"
        return c
    try:
        c.branch = branch or branch_names.durable_branch(work_id, task_id)
    except branch_names.BranchNameError as e:
        c.stage, c.reason = "입력", str(e)
        return c

    from ..client import bundle
    do_ssh = ssh or (lambda f, cmd, t: bundle._ssh(f.host, f.user, cmd, timeout=t))
    do_read = reader or (lambda f, p: bundle._remote_read(f, p))

    # ① 체크아웃 — 서브 브랜치를 골조 커밋 위에 세우고 잔재를 지운다
    c.stage = "체크아웃"
    rc, out = do_ssh(facts, checkout_command(facts, c.branch, base), GIT_TIMEOUT)
    if rc != 0 or _last_sha(out) != base:
        c.reason = (f"서브 브랜치를 세우지 못했다 (rc={rc}) — {(out or '').strip()[-300:]}")
        return c

    # ⑥ [중요] **복귀는 `finally` 다** — 실측 2026-09-03: 성공 경로에만 붙였더니 층1 에서
    #    막힌 조각이 브랜치에 체크아웃된 채 남았고, 테스트가 그것을 잡았다. **잔재가 남는
    #    것은 성공/실패와 무관하다** — 체크아웃을 옮긴 쪽이 되돌릴 책임을 진다.
    try:
        return _cycle(facts, task_id, c, base, llm, do_ssh, do_read, baseline, verifier)
    finally:
        collect_delegations(facts, do_ssh, do_read, c, work_id)    # `#764` — 복귀가 지우기 전에
        _return_home(facts, do_ssh, c)


def _cycle(facts, task_id: str, c: "Committed", base: str, llm, do_ssh, do_read,
           baseline, verifier) -> "Committed":
    """체크아웃이 선 뒤의 사이클 — 본문 → 되읽기 → 층1 → 층2 → 커밋·push."""
    # ② LLM — [중요] **본문만 쓴다.** git 은 만지지 않는다
    c.stage = "본문 작성"
    _t0 = time.time()
    try:
        rc, out = llm(facts, task_id, c.want)
    except Exception as e:                                   # noqa: BLE001
        c.seconds = time.time() - _t0
        c.reason = f"{type(e).__name__}: {e}"
        return c
    c.seconds = time.time() - _t0
    # 🔴 **계측을 여기서 받는다** (`#387`). 종전에는 `out` 을 rc≠0 일 때 **사유 문자열로만**
    #    쓰고 버렸다 — 성공해도 계측이 사라졌다. `_unwrap` 이 claude JSON·codex JSONL·레인
    #    봉투를 **한 경로로** 푼다(형식 지식은 `usage` 모듈이 갖는다).
    #    [주의] 계측 파싱이 실패해도 본문 작성 판정을 바꾸지 않는다 — 모르면 빈 dict 다.
    try:
        from .runner import _unwrap                          # noqa: PLC0415
        _body, c.usage = _unwrap(out or "")
    except Exception as e:                                   # noqa: BLE001
        c.notes.append(f"[주의] 계측을 못 읽었다 — {type(e).__name__}: {e}")
        _body = out
    # Codex 실패 이벤트는 본문과 별개다. 분류 원문은 요약과 분리해 보존한다.
    # rc=0 복구/성공 판정은 디스크 검증을 따르는 기존 계약을 유지한다 (#720).
    c.notes.extend(f"[지휘자] 오류: {error}" for error in c.usage.get("errors", []))
    # 🔴 **워커가 UE5 빌드를 돌렸으면 조각 기록에 남긴다** (실측 2026-09-13). 저널만으로는 `.33` 이
    #    못 본다(`#391` 과 같은 결). 판정은 바꾸지 않는다 — 빌드 판정은 요청자의 통합 빌드다.
    try:
        from .runner import build_attempts as _ba             # noqa: PLC0415
        c.notes.extend(f"[주의] [지휘자] 워커가 UE5 빌드를 돌렸다(지시문 위반) — {b}"
                       for b in _ba(out or ""))
    except Exception as e:                                   # noqa: BLE001
        c.notes.append(f"[주의] 빌드 흔적을 못 읽었다 — {type(e).__name__}: {e}")
    # 🔴 **위임했는지 남긴다** (`#764` 3a) — codex 모드는 명령 이벤트로 세고, claude 모드는 「미상」.
    try:
        from .runner import delegation_notes as _dn          # noqa: PLC0415
        c.notes.extend(_dn(out or ""))
    except Exception as e:                                   # noqa: BLE001
        c.notes.append(f"[주의] 위임 흔적을 못 읽었다 — {type(e).__name__}: {e}")
    if rc != 0:
        # [중요] 실패 사유는 **푼 본문**으로 적는다 — 봉투 JSON 을 그대로 보이면 못 읽는다.
        errors = c.usage.get("errors", [])
        detail = errors[0][:300] if errors else (_body or '').strip()[-300:]
        c.reason = f"본문 작성이 실패했다 (rc={rc}) — {detail}"
        return c

    # ③ 되읽기 — [중요] **판정은 디스크 상태로 한다** (원전 `_validate_disk_after_agent` 와 같은 논지)
    c.stage = "되읽기"
    sep = "\\" if facts.windows else "/"
    for w in c.want:
        try:
            c.files[w] = do_read(facts, f"{facts.path}{sep}{_q(w, facts.windows)}")
        except Exception as e:                               # noqa: BLE001
            # [중요] **못 읽은 것을 「없음」으로 접지 않는다** — `_remote_read` 가 그러라고 예외를 던진다
            c.reason = f"{w} 를 되읽지 못했다 — {type(e).__name__}: {e}"
            return c
    if c.missing:
        c.reason = "본문이 비어 있다 — 커밋하지 않는다"
        return c

    # ④ 층1 — [중요] **verify-then-commit.** 위반이면 커밋하지 않는다
    c.stage = "층1"
    l1 = layer1.check(c.files, baseline=baseline)
    # 🔴 [중요] **통과도 기록한다** (`#695` P3) — 종전에는 위반만 남아서, 동결을 못 본 통과가
    #    「통과」와 구분되지 않았다(파견 로그에 층1 통과·동결 미검사 0건 — 안 본 것이 안 보였다).
    c.notes.append(f"[층1] {l1.summary}"
                   + (f" — 동결 미검사: {', '.join(l1.skipped[:5])}" if l1.skipped else ""))
    if not l1.ok:
        c.layer1_violations = list(l1.problems)
        c.reason = "층1 이 막았다 — 커밋하지 않는다"
        # 🔴 [중요] **층1 이 막았을 때가 지휘자의 말이 가장 필요한 순간이다** (`#391`).
        #    「`[PSEUDO]` 가 남아 있다」는 **증상**이고, 왜 안 채웠는지는 지휘자만 안다.
        #    실측 2026-09-09: codex 가 *"파일 쓰기 도구가 실패했다"* 고 말했는데 그 말이
        #    어디에도 안 남아, 환경 실패가 **코드 실패로 위장**됐다(재시도 3회 낭비).
        #    [주의] 기록(task md)에 남긴다 — 저널만으로는 `.33` 이 못 본다.
        try:
            from . import runner as _R                       # noqa: PLC0415
            c.notes.extend(f"[지휘자] {ln}" for ln in _R.agent_report(out, rc=rc))
        except Exception as e:                                # noqa: BLE001
            c.notes.append(f"[주의] 지휘자 출력을 못 뽑았다 — {type(e).__name__}: {e}")
        return c

    # 층2도 커밋 전에 마스터가 판정한다. 미가용·예외·계약 오류는 승인되지 않는다.
    c.stage = "층2"
    if verifier is None:
        c.layer2_failure = "no_verifier"
        c.reason = "층2 검증기가 없다 — 커밋하지 않는다"
        return c
    try:
        from ..verdict import Verdict
        verdict = verifier(c.files)
        if not isinstance(verdict, Verdict):
            raise TypeError("층2 검증 결과가 Verdict 계약이 아니다")
        c.layer2_findings = list(verdict.findings)
        c.layer2_failure = verdict.failure or ""
        c.notes.append(f"[층2] {verdict.summary()}")
        c.notes.extend(f"[층2] {s}" for s in verdict.warnings)
        c.notes.extend(f"[층2 지적] {s}" for s in verdict.findings)
        if verdict.raw_tail:
            c.notes.append(f"[층2 판정 원문] {verdict.raw_tail}")
        if not verdict.approved or verdict.failure is not None:
            c.reason = f"층2 이 막았다 — {verdict.summary()} — 커밋하지 않는다"
            return c
    except Exception as e:                                   # noqa: BLE001
        c.layer2_failure = "verifier_exception"
        # 🔴 **추적을 버리지 않는다** (`#818`, 실측 2026-10-11 20:48). 병렬 9조각 중 하나의 층2 가
        #    마스터에서 `RuntimeError: dictionary changed size during iteration` 으로 죽었는데,
        #    종전에는 예외 한 줄만 남아 **경합 자리를 알 수 없었다.**
        #    [중요] 전체 추적은 **파견 로그(저널)** 로 — 줄마다 태스크 id 를 붙여 섞여도 가른다.
        #    사유(`c.reason`)는 큐 `fail_detail` 에서 잘리므로 짧게 두고 **마지막 프레임만** 싣는다.
        where = _last_frame(e)
        for ln in traceback.format_exc().rstrip().splitlines():
            _log(f"[wcommit] {task_id} 층2 예외 추적: {ln}")
        c.reason = f"층2 검증 실패 — {type(e).__name__}: {e} @ {where} — 커밋하지 않는다"
        return c

    # ⑤ 커밋 + push
    c.stage = "커밋"
    rc, out = do_ssh(facts, commit_command(facts, c.branch, task_id, c.want), PUSH_TIMEOUT)
    head = _last_sha(out)
    text = (out or "")
    # 🔴 **원전 계약 이식** (`worker/git_ops.py:149` · `worker/validator.py:547`).
    #
    #     git_ops    `if rc != 0 and "nothing to commit" not in out:`  ← 그 문구는 에러가 아니다
    #     validator  양쪽 다 변화 없음 → 원본에 `[PSEUDO]` 가 없었으면 **`ok_no_op`(정상)**,
    #                있었으면 `no_changes_but_pseudo_present`(진짜 실패)
    #
    # [중요] **이 이식이 빠져서 정상 조각이 두 라운드 연속 죽었다** (실측 2026-09-03):
    # `NSInteractionPromptWidget` 의 골조가 *"UpdatePrompt 는 BlueprintImplementableEvent 라
    # C++ 기본 구현이 없다 — 이 클래스에는 C++ 로직을 추가하지 않는다"* 라고 적어 놨고
    # `[PSEUDO]` 가 0개였다. 워커는 골조를 **바이트 동일**하게 돌려줬고(그것이 정답이다)
    # 커밋 단계가 `nothing to commit` → rc=1 → BLOCKED 로 읽었다. 조각당 $0.66~$1.08 을
    # 두 번 태우고 실패로 기록했다.
    #
    # [주의] 판정 근거는 **되읽은 본문의 `[PSEUDO]` 유무**다. 변화가 없었으므로 되읽은 것이
    # 곧 원본이고, 원전이 `original_target` 으로 보는 것과 같은 값이다.
    # [중요] 판정은 **`HEAD == base`** 다 — 지역화된 메시지를 읽지 않는다(위 § 참조).
    #    문구 검사는 `rev-parse` 가 못 돈 경우의 **보조 신호**로만 남긴다.
    from .skeleton import pseudo_count
    had_pseudo = any(pseudo_count(v) for v in c.files.values())
    nothing = ("nothing to commit" in text) or ("커밋할 사항 없음" in text)
    unchanged = bool(head and head == base) or (not head and nothing)
    if unchanged:
        if had_pseudo:
            # 채울 것이 있었는데 아무것도 안 바뀌었다 — 진짜 실패다(원전과 같은 판정)
            c.reason = ("변경이 없는데 골조에 `[PSEUDO]` 가 남아 있다 — 워커가 본문을 "
                        f"쓰지 않았다 (마커 {sum(pseudo_count(v) for v in c.files.values())}개)")
            return c
        # [중요] HEAD 는 **base 그대로**다 — 서브 브랜치가 base 에서 갈라진 뒤 아무것도
        #    안 얹혔으니 그 팁이 base 다. 원전도 `commit_and_push` 가 `rev-parse HEAD`
        #    (= base)를 돌려주고 그 값으로 제출한다. 사실을 그대로 싣는다.
        c.no_op, c.head, c.stage = True, (head or base), ""
        return c
    if rc != 0 or not head:
        c.reason = f"커밋·push 가 실패했다 (rc={rc}) — {text.strip()[-300:]}"
        return c
    c.head, c.stage = head, ""
    return c


# 🔴 **위임 결과를 마스터로 회수한다** (`#764`, 사용자 결정 2026-10-09). 지휘자는 agy 응답 봉투를
#    `.agy-work/out/<번호>.json` 에 남기고(지시문·`ax-work` §4), 마스터가 **복귀 전에** 가져와
#    `~/ax-state/delegations/<work_id>/<task_id>/` 에 둔다. 워커는 임시 저장소라 복귀가 그 폴더를 지운다 —
#    회수가 없으면 「agy 가 무엇을 답했나」는 그 워커 홈의 agy 대화 기록에만 남는다.
# [주의] 지휘자는 task_id 를 모른다(지시문은 대상 파일만 싣는다) — 그래서 **고정 폴더**다. 한 체크아웃은
#    한 번에 한 조각만 돌고, 복귀가 매번 지우므로 조각끼리 섞이지 않는다.
# [주의] 판정을 바꾸지 않는다 — 회수 실패는 `[주의]` 노트다.
# 🔴 **`.ax` 밖, 체크아웃 루트의 `.agy-work/` 다** (사용자 결정 2026-10-09 — 저장소 작업 영역에서 처리).
#    실측 `.2` 세션1: `.ax` 아래는 샌드박스 쓰기가 전부 거부됐고(루트의 샌드박스 SID ACE 가 그 아래에
#    없다), 루트 바로 아래 새 폴더는 상속으로 써졌다. git 은 `spec.GIT_EXCLUDES` 의 `/.agy-work/` 가 가린다.
AGY_ROOT, AGY_IN, AGY_OUT = ".agy-work", "in", "out"


def _agy_dir(facts, sub: str = "") -> str:
    sep = "\\" if facts.windows else "/"
    return f"{facts.path}{sep}{AGY_ROOT}" + (f"{sep}{sub}" if sub else "")
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,80}\.json$")
MAX_COLLECT = 50


def delegations_root() -> Path:
    return Path(os.environ.get("AX_DELEGATIONS_ROOT") or (Path.home() / "ax-state" / "delegations"))


def collect_delegations(facts, do_ssh, do_read, c: Committed, work_id: str) -> None:
    """워커의 `.agy-work/out/*.json` → `delegations_root()/<work_id>/<task_id>/`. 예외를 던지지 않는다."""
    try:
        sep = "\\" if facts.windows else "/"
        src = _agy_dir(facts, AGY_OUT)
        cmd = (f'(dir /b "{src}\\*.json" 2>nul || ver >nul)' if facts.windows
               else f'(ls -1 "{src}" 2>/dev/null || true)')
        rc, out = do_ssh(facts, cmd, GIT_TIMEOUT)
        names = [n.strip() for n in (out or "").splitlines() if _SAFE_NAME.match(n.strip())]
        if not names:
            c.notes.append(f"[지휘자] 위임 결과 파일 0개 ({AGY_ROOT}/{AGY_OUT}/)")
            return
        dest = delegations_root() / (work_id or "_no_work") / c.task_id
        dest.mkdir(parents=True, exist_ok=True)
        got = 0
        for n in sorted(names)[:MAX_COLLECT]:
            text = do_read(facts, f"{src}{sep}{n}")
            (dest / n).write_text(text, encoding="utf-8")
            got += 1
        more = f" · {len(names) - MAX_COLLECT}개는 상한 초과로 버렸다" if len(names) > MAX_COLLECT else ""
        c.notes.append(f"[지휘자] 위임 결과 {got}개 회수 → {dest}{more}")
    except Exception as e:                                   # noqa: BLE001
        c.notes.append(f"[주의] 위임 결과를 회수하지 못했다 — {type(e).__name__}: {e}")


def _return_home(facts, do_ssh, c: Committed) -> None:
    """`main` 복귀. [주의] **실패를 치명으로 보지 않는다** — 커밋은 이미 원격에 있다."""
    try:
        rc, out = do_ssh(facts, return_home_command(facts, branch=c.branch,
                                                    task_id=c.task_id), GIT_TIMEOUT)
        if rc != 0 or HOME_BRANCH not in (out or ""):
            c.notes.append(f"[주의] 워커 정리 실패 (rc={rc}) — 임시 저장소에 그 작업이 "
                           f"남았다: {(out or '').strip()[-160:]}")
    except Exception as e:                                   # noqa: BLE001
        c.notes.append(f"[주의] `{HOME_BRANCH}` 복귀를 시도하지 못했다 — {type(e).__name__}: {e}")
