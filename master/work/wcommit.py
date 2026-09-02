"""정본 ⑸-a — **워커가 자기 서브 브랜치에 커밋한다** (사용자 확정 2026-09-02).

사용자 서술 7단계 ⑤: *"작업을 전달받은 워커들은 해당 파일의 서술된 내용을 바탕으로 …
내용물을 코드로 변환하고 **각각 지정된 서브 브랜치에 커밋**하고 작업을 마치고 다음 작업을
요청해"*.

## [중요] 원전을 그대로 옮긴다 — 사이클은 원전 `worker/worker.py` 것이다

    docs/distributed-workers.md § 워커 사이클 (per task)
      claim → git fetch --all → git reset --hard HEAD → git checkout -B <branch> <base_commit>
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

import re
from dataclasses import dataclass, field

from . import branch_names, layer1
from .runner import DispatchError

# 원전 커밋 메시지 규약 (`docs/distributed-workers.md` § 워커 사이클)
COMMIT_FMT = "[task:{task_id}] worker={host} target={target}"
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
    stage: str = ""                                 # 어디까지 갔나 (실패 지점)
    reason: str = ""

    @property
    def missing(self) -> list:
        return [w for w in self.want if not (self.files.get(w) or "").strip()]

    @property
    def ok(self) -> bool:
        """[중요] **fail-closed.** 커밋 해시가 있고 층1 위반이 없고 빠진 파일이 없어야 통과다."""
        return (bool(self.head) and not self.reason
                and not self.layer1_violations and not self.missing)

    @property
    def summary(self) -> str:
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
    return (f'{cd} && git fetch --all --quiet && git reset --hard --quiet HEAD && '
            f'git clean -fd && git checkout -q -B "{branch}" "{base_commit}" && '
            f'git rev-parse HEAD')


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
    return (f'{cd} && git add {adds} && git commit -q -m "{msg}" && '
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
        ssh=None, reader=None, baseline=None, branch: str = "") -> Committed:
    """워커 한 대에서 ⑸-a 사이클을 한 바퀴 돈다. **예외를 던지지 않고 사유를 담아 돌려준다.**

    `llm(facts, task_id, files)` — 본문을 쓰게 하는 호출(주입). 반환은 `(rc, stdout)`.
    `ssh(facts, cmd, timeout)` · `reader(facts, abs_path)` — 주입 자리(테스트·오프라인).
    `baseline(path)` — 동결 대조용 원본 본문(층1). 없으면 동결 검사는 **미검사로 기록**된다.
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

    # ② LLM — [중요] **본문만 쓴다.** git 은 만지지 않는다
    c.stage = "본문 작성"
    try:
        rc, out = llm(facts, task_id, c.want)
    except Exception as e:                                   # noqa: BLE001
        c.reason = f"{type(e).__name__}: {e}"
        return c
    if rc != 0:
        c.reason = f"본문 작성이 실패했다 (rc={rc}) — {(out or '').strip()[-300:]}"
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
    if not l1.ok:
        c.layer1_violations = list(l1.problems)
        c.reason = "층1 이 막았다 — 커밋하지 않는다"
        return c

    # ⑤ 커밋 + push
    c.stage = "커밋"
    rc, out = do_ssh(facts, commit_command(facts, c.branch, task_id, c.want), PUSH_TIMEOUT)
    head = _last_sha(out)
    if rc != 0 or not head:
        c.reason = f"커밋·push 가 실패했다 (rc={rc}) — {(out or '').strip()[-300:]}"
        return c
    if head == base:
        # [주의] base 와 같으면 **아무것도 커밋되지 않았다** — 성공으로 읽으면 빈 조각이 통과한다
        c.reason = f"커밋이 생기지 않았다 (HEAD 가 기준 커밋 그대로 {head[:8]})"
        return c
    c.head, c.stage = head, ""
    return c
