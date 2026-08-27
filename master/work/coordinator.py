"""2-tier 코디네이터 — 원전 `cluster_coordinator.py` 이식 (Plan v5 C.1/C.2).

    assign_attempt      배정 — durable/attempt 이름을 계산한다 (git 접촉 0)
    push_attempt        ephemeral attempt 에 작업분을 commit·push
    verify_and_merge    [중요] epoch 게이트 → 통과분만 durable 에 merge·push
    cleanup_attempts    ephemeral 정리 — [중요] 기본은 **세기만** 한다 (아래 참조)
    fake_workshop       주입용 가짜 작업장 — 하드웨어·LLM 없이 한 바퀴 돌린다
    run_round           동기 1라운드 (드라이런). 실전은 같은 함수들을 비동기로 조립한다

[중요] **왜 이걸 되살리나.** 마일스톤 3 에서 이 계층을 없앴는데(워커는 추론만 · 통합자가 유일한
쓰기 주체), 리포트 14 §2 가 실측한 대로 **원전에 이미 있던 것**이었다. `verify_and_merge` 의
원전 주석이 *"durable 단일 writer 보존"* 이고 **그 writer 는 서버**다 — 워커는 쓴다, 다만
**ephemeral 에만** 쓴다. 없앤 것은 원칙이 아니라 그 원칙을 지키던 **장치**였다.

## [중요] 원전과 다르게 둔 것 넷 — 이유가 있다

**① `worker` 가 아니라 `workshop`.** 이 저장소에서 `worker/` 는 BC-250 추론 노드다.
브랜치의 그 자리에 오는 것은 파일을 소유한 윈도우 PC = **작업장**이다.
(`branch_names.py` 가 이미 그 개명을 해 뒀다.)

**② `cleanup_attempts(delete=False)` 가 기본.** 원전은 `push --delete` 로 원격 ephemeral 을
지운다(리더의 terminal 결정 시 일괄). 우리는 **08-09 결정**으로 *"attempt 를 성공·실패 무관
push"* 하고 그 목적이 **증거 보존**이라, `work/cleanup.py` 가 이미 *"원격을 없애는 것은 요청자와
사람의 판단"* 이라고 못박아 뒀다. [중요] **기제는 옮기고 정책은 바꾸지 않는다** — 지우려면 호출자가
명시해야 한다. 두 정책 다 일관성이 있고 **시점이 다를 뿐**이다(원전=work 종료 시, 우리=사람).

**③ 드라이런 진입점 이름이 `fake_workshop`.** 원전 `fake_worker` 와 같은 것이다.

**④ `remote` 가 인자다** (기본값은 원전과 같은 `"origin"`). 원전의 인프라 PC 는 `origin` 에
push 할 수 있었지만 **우리 마스터의 정본은 `origin` push 가 봉인돼 있다**
(`DISABLED://마스터는-소스저장소에-push하지-않는다-PLAN.md-2.1`, §2.1). Flow Y(사용자 확정
2026-08-14)가 *"마스터가 diff 를 attempt 에 commit"* 을 요구하므로 별도 쓰기 표면
(`gitea-write`)을 열었고, **이 인자 하나가 그 환경 차이를 전부 흡수한다** — 호출자가 어느
표면으로 쏠지 고르고, 기본값은 원전 동작 그대로다(`selftest` 의 임시 저장소가 그 경로다).
[중요] **봉인을 여는 대신 대체 가드를 뒀다**: 마스터 클론의 `pre-push` 훅이 `attempt/*`·`task/*`
밖의 ref 와 **삭제 전부**를 거부한다(리포트 16 §5 — 네 대가 같은 Gitea 계정이라 서버측
브랜치 보호로는 기계를 구분할 수 없다).

## [주의] `push --force` 가 여기 있는 이유 (지우지 말 것)

`push_attempt` 는 attempt 에 `--force` 로 push 한다. **원전이 근거를 적어 뒀다** — ephemeral 은
`(workshop, ts)` 로 그 작업장 전용 namespace 라 다른 작업장이 절대 안 쓰고, 같은 작업장의
재시도(zombie 포함)가 자기 브랜치를 force 하는 것은 **공유 ref 가 아니므로 안전**하다.

[중요] **durable 은 절대 force 하지 않는다.** `CLAUDE.md` 의 *"never `push --force`"* 는 **대화형
세션**과 **durable** 을 향한 규칙이고(*"Pipeline workers follow different rules"* 가 그 carve-out),
ephemeral 은 그 반대편이다. 대상이 다르면 규칙이 다르다.

## [주의] 이 모듈은 마스터에서 **로컬로** 돈다

`integrate.py` 의 `_git` 은 SSH 로 작업장을 때리지만 여기는 로컬 `repo` 경로를 받는다.
git stdout 은 ref·SHA 라 ASCII 이고 마스터는 UTF-8 이므로 `.2` 콘솔 CP949 문제(리포트 13)가
여기서는 나지 않는다. **본문 텍스트를 읽는 자리가 아니다** — 그건 `source_text.decode` 의 몫.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .branch_names import attempt_branch, attempt_glob, base_branch, durable_branch

GIT_TIMEOUT = 120


class GitError(RuntimeError):
    """git 이 실패했다. **삼키지 않는다** — 여기서 조용히 넘어가면 브랜치 상태를 모른 채
    다음 단계가 돈다(이 저장소가 반복해 물린 *조용히 틀리는* 유형)."""


def _git_cmd(repo: Path, *args: str) -> list:
    """git 명령줄 조립 — [중요] **커밋 신원의 단일 출처.**

    인자로 박는 이유: 마스터의 전역 git 설정에 의존하면 환경마다 달라진다. `_git` 과
    `_git_rc` 가 **같은 이 함수**를 쓴다 — 따로 만들면 신원·서명 설정이 조용히 갈라진다.
    """
    return ["git", "-c", "user.email=cluster@local", "-c", "user.name=ax-cluster",
            "-c", "commit.gpgsign=false", "-C", str(repo), *args]


def _git(repo: Path, *args: str, check: bool = True) -> str:
    """git 한 번. 성공 시 stdout(strip). `check=False` 면 실패도 문자열로 돌려준다."""
    r = subprocess.run(_git_cmd(repo, *args), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT)
    if check and r.returncode != 0:
        raise GitError(f"git {' '.join(args)} → rc={r.returncode}\n{(r.stderr or '').strip()}")
    return (r.stdout or "").strip()


def _git_rc(repo: Path, *args: str, timeout: int = 0) -> tuple:
    """git 한 번 — `(rc, stdout+stderr)`. [중요] **실패가 정상 결과인 자리**에서 쓴다.

    머지 충돌·`ls-remote` 부재처럼 *"실패했다"* 가 곧 답인 연산은 예외로 만들면 흐름이
    끊긴다(원전도 `(rc, out)` 형태를 쓴다).

    [주의] **출력 문구로 판정하지 말 것.** 이 기계는 `ko_KR` 이라 git 메시지가 번역된다 —
    *"nothing to commit"* 대조가 조용히 빗나간 전례가 있다(마일스톤 함정 목록). **rc 로
    판정하고**, 문구는 사람에게 보여 줄 때만 쓴다.
    """
    r = subprocess.run(_git_cmd(repo, *args), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout or GIT_TIMEOUT)
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


def _noop_log(stage: str, msg: str) -> None:
    pass


# ─────────────────────────────────────────────────────────────
# 2-tier git 연산 — 드라이런과 실전이 **같은 함수**를 쓴다
# ─────────────────────────────────────────────────────────────

def assign_attempt(work_id: str, task_id: str, workshop: str, ts: str) -> dict:
    """배정 — 브랜치 **이름을 서버가 정한다**. git 을 건드리지 않는다.

    [중요] `work_id` 가 인자에 들어온 것은 `#319`(계층형) 때문이다 — 조각 durable 이
    `task/<work_id>/<task_id>` 이고, **base 도 같이 돌려준다**. 배정을 받는 쪽이 base 를
    따로 조립하면 그 순간 이름이 두 벌이 된다(`#197` 이 값을 치른 자리).

    [중요] 원전 규약: *"push 모델상 서버가 브랜치명을 배정하므로 작업장은 받은 이름을 쓸 뿐
    (구성하지 않는다)."* 이름을 양쪽이 각자 조립하면 규약이 갈린다.

    `epoch` 는 여기서 만들지 않는다 — 큐(`task_queue/logic_claim.py`)가 배정마다 단조
    증가시키는 것이 **이미 이식돼 있다**. 호출자가 그 값을 `verify_and_merge` 로 넘긴다.
    """
    return {
        "work_id": work_id,
        "task_id": task_id,
        "workshop": workshop,
        "base": base_branch(work_id),
        "durable": durable_branch(work_id, task_id),
        "attempt": attempt_branch(work_id, task_id, workshop, ts),
    }


def push_attempt(repo: Path, attempt: str, base_ref: str, work_fn, target_rel: str,
                 *, message: str, remote: str = "origin", logf=_noop_log) -> str:
    """ephemeral attempt 생성 → `work_fn` 이 작업 → commit·push. head SHA 반환.

    `work_fn(repo, target_rel)` 은 **디스크 워킹트리만 수정한다** — git 은 건드리지 않는다.
    드라이런이면 `fake_workshop`, 실전이면 작업장이 자기 클론에서 수행한다.

    [주의] 변경이 없으면 `commit` 이 rc=1(`nothing to commit`)로 죽는다. 그건 **작업이 아무것도
    안 했다는 사실**이므로 삼키지 않고 `GitError` 로 올린다.
    """
    _git(repo, "checkout", "-q", "-B", attempt, base_ref)
    work_fn(repo, target_rel)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    # ephemeral 은 (workshop, ts) 전용 namespace — 위 「push --force 가 여기 있는 이유」 참조.
    _git(repo, "push", "-q", "--force", remote, attempt)
    head = _git(repo, "rev-parse", "HEAD")
    logf("work", f"{attempt} push (head={head[:8]})")
    return head


def verify_and_merge(repo: Path, attempt: str, durable: str, *,
                     submit_epoch: int, current_epoch: int,
                     remote: str = "origin", logf=_noop_log) -> dict:
    """[중요] epoch 게이트 → 통과분만 durable 에 merge·push. `{ok, merged, reason}`.

    **fencing 이 먼저다** — git 을 건드리기 전에 판정한다. 재배정으로 epoch 이 올라간 뒤
    들어온 이전 작업장(zombie)의 시도는 **부작용 없이** 거부되어야 한다.

    2-tier 가 push 충돌을 이미 구조적으로 없앴으므로(공유 write 타깃 부재) 여기 남는 것은
    *"회수된 줄 모르고 검증을 요청하는"* **권위 문제**뿐이고, 그것을 epoch 이 판정한다.
    → 원전 주석 그대로: **durable 단일 writer 보존.**

    [주의] durable 은 `--force` 하지 않는다. 첫 검증분은 attempt 에서 브랜치를 **만들고**,
    이후는 merge 한다.
    """
    if submit_epoch < current_epoch:
        logf("verify", f"거부 — stale epoch {submit_epoch} < 현재 {current_epoch} (zombie 작업장)")
        return {"ok": False, "merged": False,
                "reason": f"stale_epoch:{submit_epoch}<{current_epoch}"}

    _git(repo, "fetch", "-q", remote, attempt)
    logf("verify", f"{attempt} 검증 (epoch={submit_epoch} OK)")

    remote_durable = _git(repo, "ls-remote", "--heads", remote, durable, check=False)
    if not remote_durable:
        _git(repo, "checkout", "-q", "-B", durable, f"{remote}/{attempt}")
        _git(repo, "push", "-q", remote, durable)
        logf("merge", f"durable {durable} 신규 생성 (첫 검증 통과분)")
        return {"ok": True, "merged": True, "reason": "created_from_first_attempt"}

    _git(repo, "fetch", "-q", remote, durable)
    _git(repo, "checkout", "-q", "-B", durable, f"{remote}/{durable}")
    _git(repo, "merge", "-q", "--no-edit", f"{remote}/{attempt}")
    _git(repo, "push", "-q", remote, durable)
    logf("merge", f"검증 통과 → durable {durable} merge·push")
    return {"ok": True, "merged": True, "reason": "merged"}


def cleanup_attempts(repo: Path, work_id: str, task_id: str, *, delete: bool = False,
                     remote: str = "origin", logf=_noop_log) -> dict:
    """그 task 의 ephemeral 목록. [중요] **기본은 세기만 한다** — durable 은 언제나 보존.

    `delete=True` 를 **호출자가 명시**해야 원격에서 지운다. 위 「원전과 다르게 둔 것 ②」 참조 —
    *"attempt 를 성공·실패 무관 push"* 의 목적이 증거 보존이라, 지우는 시점은 사람이 정한다.
    """
    glob = attempt_glob(work_id, task_id)
    out = _git(repo, "ls-remote", "--heads", remote, glob, check=False)
    refs = [ln.split("refs/heads/")[-1] for ln in out.splitlines() if "refs/heads/" in ln]
    if not delete:
        logf("cleanup", f"ephemeral {len(refs)}건 (glob={glob}) — [중요] 건드리지 않음")
        return {"found": refs, "deleted": []}
    deleted = []
    for ref in refs:
        _git(repo, "push", "-q", remote, "--delete", ref, check=False)
        deleted.append(ref)
    logf("cleanup", f"ephemeral {len(deleted)}건 제거 (glob={glob}), durable 보존")
    return {"found": refs, "deleted": deleted}


# ─────────────────────────────────────────────────────────────
# 드라이런 — [중요] 하드웨어·LLM·원격 PC 없이 2-tier 전체를 돌린다
#
# 원전이 이 자리에 값을 매긴 이유(사용자 발화): *"시킬 일을 억지로 만드는 것도 고역"* —
# 사람이 가짜 일감을 지어낼 필요 없이 서버가 캔드 작업을 주입해 한 바퀴 돌린다.
# `/cluster-selftest`(소 2.3.x)가 이것 위에 선다.
# ─────────────────────────────────────────────────────────────

def fake_workshop(append_line: str):
    """스크립트된 가짜 작업장 — target 파일에 한 줄 append.

    실전에서 이 자리는 작업장의 `claude -p` + 편집이다. 주입으로 갈라 두면 **같은 2-tier
    경로**를 하드웨어 없이 검증할 수 있다.
    """
    def _fn(repo: Path, target_rel: str) -> None:
        p = repo / target_rel
        p.parent.mkdir(parents=True, exist_ok=True)
        prev = p.read_text(encoding="utf-8") if p.exists() else ""
        p.write_text(prev + append_line + "\n", encoding="utf-8")
    return _fn


# [중요] **`run_round`(드라이런 합성)가 여기 있었다 — `#327` 로 걷어냈다** (2026-08-28).
#    `assign → push_attempt → verify_and_merge` 를 한 함수로 묶은 것이었는데, **부르는 곳이
#    테스트뿐**이었다. `selftest` 는 일부러 안 썼다 — 그 파일 주석이 그 이유를 적어 뒀다:
#    *"real 모드는 합성(run_round)을 쓰지 않고 assign(서버) … push_attempt(원격 작업장) …
#    verify_and_merge(서버) 로 비동기 분리하되 같은 함수들을 재사용한다."*
#    즉 실전 형태를 재는 쪽이 합성을 피했고, 합성은 자기 테스트만 갖고 있었다.
#
# [주의] **위 세 함수는 남는다** — `selftest` 드라이런이 그것들을 운송 수단 삼아 매니페스트
#    왕복·`[PSEUDO]` 제거·좀비 epoch 거부를 증명한다. 소비자가 있는 것은 걷지 않는다.
