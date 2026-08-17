"""워커 찌꺼기 정리 — [중요] **워커는 스스로 못 지운다. 마스터가 치운다** (레드마인 #27).

## 왜 마스터인가

`ax-work` 스킬의 git 금지 목록에 **브랜치 삭제**가 있고 그건 의도된 설계다 — 워커가 브랜치를
지우는 것이 가장 위험한 경우다. 그래서 파견을 반복하면 워커에 이렇게 쌓인다(사용자 지적
2026-08-09): 요청자가 `main` 에 병합하고 원격·로컬을 정리해도

    로컬 attempt/<task>/<workshop>/<ts>   파견 1회당 1개
    로컬 task/<id>                        병합 후 무의미
    원격추적 origin/attempt/*             원격에서 지워도 prune 전까지 남는다
    <checkout>/.ax/work/<task_id>/        부산물 디렉토리

## [중요] 지우는 기준은 단 하나 — **커밋이 다른 곳에 살아 있는가**

    로컬 브랜치 삭제  ⇔  그 팁이 origin/<기본브랜치> 에서 **도달 가능**하다
                        (= 정말 병합됐다 = 지워도 잃는 것이 없다)

도달 불가면 **지우지 않고 보고한다.** *"항상 attempt 를 push 한다"* 는 증거 보존이 목적이므로,
증거가 어딘가에 살아 있는지 **확인하기 전에는** 로컬을 없애지 않는다. 판정 자체를 못 하면
(fetch 실패·ancestor 확인 실패) 역시 **남긴다** — fail-closed 의 방향이 여기서는 "보존" 이다.

## [중요] 원격 브랜치 — 병합 확인분만, `remote` 서브커맨드로 (사용자 결정 2026-08-18)

옛 규칙(*"원격은 사람"*)을 사용자가 좁혔다: **팁이 기준 브랜치에서 도달 가능한**(=정말
병합된) 원격 attempt/task 는 마스터가 지운다 — 원전 `cleanup_attempts` 로의 회귀이고,
지우려는 순간 pre-push 훅(#125: main 도달 가능한 ref 만 삭제 허용)이 **두 번째 가드**로
같은 판정을 한 번 더 한다. [중요] **도달 불가는 여전히 사람 몫** — 병합 안 된 것을 지우는
결정은 자동화하지 않는다 (미병합 프로브·실패 증거가 그 부류다). 워커 로컬을 훑는
plan/apply 와 달리 이건 **마스터 정본 저장소에서** 돈다.

## [중요] 부산물은 성공한 것만 지운다

`.ax/work/<id>/` 는 태스크가 `verified`·`cancelled` 일 때만 지운다. **`failed` 는 남긴다** —
그게 왜 실패했는지 볼 유일한 기록이다. 큐를 못 읽으면 아무것도 지우지 않는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..client import bundle

GIT_TIMEOUT = 90

# 우리가 만든 것만 건드린다. 사람이 만든 브랜치는 이름이 다르므로 애초에 후보가 아니다.
_OURS = re.compile(r"^(attempt|task)/")
_TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")   # 경로 조작 차단

KEEP_STATUSES = ("failed",)                  # [중요] 증거로 남긴다
DROP_STATUSES = ("verified", "cancelled")


class CleanupError(RuntimeError):
    """정리를 계획조차 할 수 없다."""


@dataclass
class HostPlan:
    """워커 한 대의 계획. [중요] **지울 것과 남길 것을 둘 다 들고 있다.**"""
    host: str
    path: str = ""
    current: str = ""                                    # 지금 체크아웃된 브랜치
    delete: list = field(default_factory=list)           # [(브랜치, 팁)]
    keep: list = field(default_factory=list)             # [(브랜치, 사유)]
    drop_dirs: list = field(default_factory=list)        # [(task_id, 상태)]
    keep_dirs: list = field(default_factory=list)        # [(task_id, 사유)]
    remote_attempts: int = 0                             # [중요] 세기만 한다
    park: str = ""                                       # main 으로 되돌릴 것인가
    errors: list = field(default_factory=list)

    @property
    def summary(self) -> str:
        s = (f"{self.host}: 브랜치 삭제 {len(self.delete)} · 보존 {len(self.keep)}"
             f" · 부산물 삭제 {len(self.drop_dirs)} · 보존 {len(self.keep_dirs)}")
        if self.park:
            s += f" · {self.current} → {self.park} 복귀"
        if self.remote_attempts:
            s += f" · 원격 attempt {self.remote_attempts}건(건드리지 않음)"
        if self.errors:
            s += " · [주의] " + "; ".join(self.errors[:2])
        return s


def fmt_arg(facts, spec: str) -> str:
    """`--format=` 인자. [중요] **반드시 따옴표로 감싼다.**

    `%(refname:short)` 의 **괄호는 POSIX 셸의 문법**이라 안 감싸면 `.43` 에서 통째로 실패한다.
    윈도우 cmd 는 괄호를 그냥 넘겨 **한쪽만 조용히 깨졌다**(실측 2026-08-09: `.2` 는 되고
    `.43` 만 "브랜치 목록 실패"). 셸이 다르면 따옴표도 다르다 — cmd 는 작은따옴표를 모른다.
    """
    q = '"' if facts.windows else "'"
    return f"--format={q}{spec}{q}"


def _git(facts, args: str, *, runner=None) -> tuple:
    cmd = f'git -C "{facts.path}" {args}'
    if runner is not None:
        return runner(facts, cmd)
    return bundle._ssh(facts.host, facts.user, cmd, timeout=GIT_TIMEOUT)


def survey(facts, *, base_branch: str = "main", closed=None, runner=None) -> HostPlan:
    """워커 한 대를 **읽기만 해서** 계획을 세운다.

    `closed` 는 `{task_id: status}` — 큐에서 온 종료 상태. `None` 이면 부산물은 손대지 않는다.
    """
    p = HostPlan(host=facts.host, path=facts.path)

    # ① prune 은 원격추적 ref 만 건드린다 — 커밋도 로컬 브랜치도 잃지 않는다
    rc, out = _git(facts, "fetch --prune origin", runner=runner)
    if rc != 0:
        # [중요] fetch 를 못 했으면 origin/<base> 가 낡았을 수 있다 → 아무것도 지우지 않는다
        p.errors.append(f"fetch 실패 — 지우지 않는다 ({out.strip()[:80]})")
        return p

    rc, out = _git(facts, "branch --show-current", runner=runner)
    p.current = out.strip() if rc == 0 else ""

    # [중요] **형식 문자열에 공백을 넣지 않는다.** 원격 셸이 쪼개서 git 이 뒷부분을 *패턴*으로
    # 읽는다 — 실측 2026-08-09: 두 워커 모두 브랜치가 0건으로 나왔고 한쪽은 조용히 빈 목록,
    # 다른 쪽은 rc≠0 이었다. `:` 는 refname 에 **쓸 수 없는 문자**라 구분자로 안전하다.
    rc, out = _git(facts, "for-each-ref "
                   + fmt_arg(facts, "%(refname:short):%(objectname)") + " refs/heads/",
                   runner=runner)
    if rc != 0:
        p.errors.append(f"브랜치 목록 실패 ({out.strip()[:80]})")
        return p

    for line in out.splitlines():
        if ":" not in line:
            continue
        name, tip = line.strip().rsplit(":", 1)      # sha 는 항상 마지막 조각이다
        if not name or not tip:
            continue
        if not _OURS.match(name):
            continue                                     # 사람의 브랜치는 후보가 아니다
        if name == p.current:
            p.keep.append((name, "지금 체크아웃되어 있다"))
            continue
        rc2, out2 = _git(facts, f"merge-base --is-ancestor {tip} origin/{base_branch}",
                         runner=runner)
        if rc2 == 0:
            p.delete.append((name, tip))
        elif rc2 == 1:
            # [중요] 병합되지 않았다 = 이 커밋이 여기에만 있을 수 있다
            p.keep.append((name, f"origin/{base_branch} 에 병합되지 않았다 — 증거일 수 있다"))
        else:
            p.keep.append((name, f"도달 여부를 확인하지 못했다 ({out2.strip()[:60]})"))

    rc, out = _git(facts, "for-each-ref " + fmt_arg(facts, "%(refname:short)")
                   + " refs/remotes/origin/attempt", runner=runner)
    p.remote_attempts = len([x for x in out.splitlines() if x.strip()]) if rc == 0 else 0

    # [중요] 우리 브랜치 위에 서 있으면 `main` 으로 되돌린다 (사용자 결정 2026-08-09).
    # 체크아웃된 브랜치는 삭제 대상에서 빠지므로, 워커가 `task/<id>` 에 앉아 있는 한 그
    # 브랜치는 **영영 정리되지 않는다.** 작업물은 이미 원격에 있으니 잃는 것이 없다.
    # [주의] 단 워킹트리가 깨끗할 때만 — 더러우면 체크아웃이 사람의 편집을 건드린다.
    if p.current and _OURS.match(p.current):
        rc, out = _git(facts, "status --porcelain -- Source/", runner=runner)
        if rc != 0:
            p.errors.append("더티 확인 실패 — 브랜치를 되돌리지 않는다")
        elif out.strip():
            p.keep.append((p.current, f"{base_branch} 로 되돌리지 않았다 — Source/ 가 더럽다"))
        else:
            p.park = base_branch

    if closed is not None:
        _survey_dirs(facts, p, closed, runner=runner)
    return p


def _survey_dirs(facts, p: HostPlan, closed: dict, *, runner=None) -> None:
    """`.ax/work/<task_id>/` 를 훑는다. [중요] **성공·취소만 지운다.**"""
    work = f"{facts.path}\\{bundle.WORK_REL}".replace("/", "\\") if facts.windows \
        else f"{facts.path}/{bundle.WORK_REL}"
    cmd = (f'if exist "{work}" (dir /b "{work}") else (echo)') if facts.windows \
        else f'ls -1 "{work}" 2>/dev/null || true'
    if runner is not None:
        rc, out = runner(facts, cmd)
    else:
        rc, out = bundle._ssh(facts.host, facts.user, cmd, timeout=GIT_TIMEOUT)
    if rc != 0:
        p.errors.append("부산물 목록 실패 — 지우지 않는다")
        return
    for name in (x.strip() for x in out.splitlines()):
        if not name or not _TASK_ID.match(name):
            continue                                     # [중요] 이상한 이름은 손대지 않는다
        st = closed.get(name)
        if st in DROP_STATUSES:
            p.drop_dirs.append((name, st))
        elif st in KEEP_STATUSES:
            p.keep_dirs.append((name, f"{st} — 왜 실패했는지 볼 유일한 기록이다"))
        elif st is None:
            p.keep_dirs.append((name, "큐에 없다 — 모르는 것을 지우지 않는다"))
        else:
            p.keep_dirs.append((name, f"{st} — 아직 진행 중이다"))


def apply(facts, plan: HostPlan, *, runner=None) -> dict:
    """계획대로 지운다. [중요] **survey 가 정한 것 외에는 아무것도 건드리지 않는다.**"""
    done = {"branches": [], "dirs": [], "parked": "", "errors": list(plan.errors)}
    # [중요] **되돌리기를 먼저 한다** — 그래야 방금 서 있던 브랜치도 이번 회차에 지울 수 있다.
    if plan.park:
        rc, out = _git(facts, f"checkout {plan.park}", runner=runner)
        if rc == 0:
            done["parked"] = plan.park
            plan.keep = [(n, w) for n, w in plan.keep if w != "지금 체크아웃되어 있다"]
        else:
            done["errors"].append(f"{plan.park} 복귀 실패: {out.strip()[:80]}")
    for name, tip in plan.delete:
        # [중요] `-D` 를 쓰되 **survey 의 ancestor 판정이 통과한 것만** 온다. 그 판정이
        # `origin/<base>` 에 커밋이 살아 있음을 이미 보장한다 — `-d` 는 HEAD 기준이라
        # 워커가 task 브랜치에 앉아 있으면 병합된 것도 거부해 정리가 영영 안 된다.
        rc, out = _git(facts, f"branch -D {name}", runner=runner)
        if rc == 0:
            done["branches"].append(name)
        else:
            done["errors"].append(f"{name} 삭제 실패: {out.strip()[:80]}")

    for task_id, _st in plan.drop_dirs:
        if not _TASK_ID.match(task_id):                  # 방어를 두 번 한다
            done["errors"].append(f"{task_id}: 이름이 이상하다 — 건너뛴다")
            continue
        if facts.windows:
            target = f"{facts.path}\\{bundle.WORK_REL}\\{task_id}".replace("/", "\\")
            cmd = f'rmdir /s /q "{target}"'
        else:
            target = f"{facts.path}/{bundle.WORK_REL}/{task_id}"
            cmd = f'rm -rf "{target}"'
        if runner is not None:
            rc, out = runner(facts, cmd)
        else:
            rc, out = bundle._ssh(facts.host, facts.user, cmd, timeout=GIT_TIMEOUT)
        if rc == 0:
            done["dirs"].append(task_id)
        else:
            done["errors"].append(f"{task_id} 삭제 실패: {out.strip()[:80]}")
    return done


def closed_tasks(*, api=None) -> dict:
    """큐에서 `{task_id: status}`. [중요] **못 읽으면 `None`** — 그러면 부산물은 손대지 않는다."""
    from .runner import _api
    call = api or _api
    try:
        data = call("GET", "/api/v1/tasks")
    except Exception:                                     # noqa: BLE001
        return None
    items = data.get("tasks") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return None
    return {str(t.get("task_id") or ""): str(t.get("status") or "")
            for t in items if isinstance(t, dict)}


# ── CLI ──────────────────────────────────────────────────────────────────────
#
#   python -m master.work.cleanup plan  [프로젝트]    무엇을 지울지만 본다 (아무것도 안 지운다)
#   python -m master.work.cleanup apply [프로젝트]    계획대로 지운다
#
# [중요] **plan 을 먼저 본다.** 온톨로지의 `plan → dry → refresh` 와 같은 규칙이다 — 지우는 쪽은
# 되돌릴 수 없으므로 무엇이 남고 무엇이 사라지는지 눈으로 확인한 뒤 실행한다.

def _render(p: HostPlan) -> str:
    out = ["  " + p.summary]
    for n, tip in p.delete:
        out.append(f"    삭제  {n}  ({tip[:8]})")
    for n, why in p.keep:
        out.append(f"    보존  {n} — {why}")
    for t, st in p.drop_dirs:
        out.append(f"    삭제  .ax/work/{t}/  ({st})")
    for t, why in p.keep_dirs:
        out.append(f"    보존  .ax/work/{t}/ — {why}")
    return "\n".join(out)


# ── 원격 정리 (사용자 결정 2026-08-18 — 원전 cleanup_attempts 회귀) ────────────────

_CLEANUP_BASE_REF = "refs/ax/cleanup-base"


@dataclass
class RemotePlan:
    """원격 attempt/task 의 처분 계획. [중요] 판정 불가는 전부 「보존」 쪽으로 넘어진다."""
    delete: list = field(default_factory=list)       # [(ref, tip)] — 기준에서 도달 가능
    keep: list = field(default_factory=list)         # [(ref, tip, 사유)] — 사람 몫
    error: str = ""

    def render(self) -> str:
        out = [f"  원격(gitea-write): 삭제 후보 {len(self.delete)} · 보존 {len(self.keep)}"]
        for ref, tip in self.delete:
            out.append(f"    [삭제] {ref} @ {tip[:8]} — 기준에서 도달 가능(병합됨)")
        for ref, tip, why in self.keep:
            out.append(f"    [보존] {ref} @ {tip[:8]} — {why}")
        if self.error:
            out.append(f"    [중요] {self.error}")
        return "\n".join(out)


def survey_remote(paths, *, base_branch: str = "main", git=None) -> RemotePlan:
    """gitea-write 의 attempt/*·task/* 를 세고 **기준 도달 가능성**으로 가른다.

    [중요] 기준 팁을 fetch 하면 그 조상 전부가 로컬에 온다 — 도달 가능한 팁은 반드시
    로컬에 존재하므로, `merge-base --is-ancestor` 가 객체 부재로 죽는 경우는 곧
    「도달 불가」다. 판정 실패의 방향은 언제나 보존이다.
    """
    from pathlib import Path as _P

    from .attempt import WRITE_REMOTE, GitError, _git
    g = git or _git
    repo = _P(paths.repo)
    p = RemotePlan()
    try:
        g(repo, "fetch", WRITE_REMOTE,
          f"+refs/heads/{base_branch}:{_CLEANUP_BASE_REF}")
        out = g(repo, "ls-remote", "--heads", WRITE_REMOTE,
                "refs/heads/attempt/*", "refs/heads/task/*")
    except GitError as e:
        p.error = f"원격을 못 봤다 — 아무것도 판정하지 않는다: {e}"
        return p
    for ln in out.splitlines():
        parts = ln.split()
        if len(parts) != 2:
            continue
        tip, ref = parts[0], parts[1].removeprefix("refs/heads/")
        try:
            g(repo, "merge-base", "--is-ancestor", tip, _CLEANUP_BASE_REF)
            p.delete.append((ref, tip))
        except GitError:
            p.keep.append((ref, tip, f"origin/{base_branch} 에 없다 — 병합 안 됨, 사람 몫"))
    return p


def apply_remote(paths, plan: RemotePlan, *, git=None) -> dict:
    """계획된 삭제만 집행. pre-push 훅(#125)이 같은 판정을 한 번 더 한다 (이중 가드)."""
    from pathlib import Path as _P

    from .attempt import WRITE_REMOTE, GitError, _git
    g = git or _git
    repo = _P(paths.repo)
    done = {"deleted": [], "errors": []}
    for ref, tip in plan.delete:
        try:
            g(repo, "push", WRITE_REMOTE, "--delete", ref)
            done["deleted"].append(ref)
        except GitError as e:
            done["errors"].append(f"{ref}: {e}")
    return done


def main(argv) -> int:
    from ..context_search.paths import resolve
    from ..projects.config import ProjectConfig
    from .runner import pick_worker            # 역할 필터를 그대로 쓴다

    cmd = (argv[0] if argv else "plan").strip()
    if cmd == "remote":
        paths = resolve(argv[1] if len(argv) > 1 and not argv[1].startswith("--") else "")
        base = (ProjectConfig.load(paths.config).branch or "main").strip()
        plan = survey_remote(paths, base_branch=base)
        print(f"프로젝트 {paths.name} · 기준 {base}")
        print(plan.render())
        if "--apply" not in argv:
            print("\n  [중요] 아무것도 지우지 않았다. 실행하려면 `remote <프로젝트> --apply`.")
            return 0
        done = apply_remote(paths, plan)
        print(f"  [완료] 원격 브랜치 {len(done['deleted'])} 삭제")
        for e in done["errors"]:
            print(f"  [중요] {e}")
        return 1 if done["errors"] else 0
    if cmd not in ("plan", "apply"):
        print("  plan | apply | remote [--apply]")
        return 2
    paths = resolve(argv[1] if len(argv) > 1 else "")
    base = (ProjectConfig.load(paths.config).branch or "main").strip()
    facts = [bundle.probe(h, u, p, d, r) for h, u, p, d, r in bundle.workshops(paths.name)]
    # [중요] 정리는 파견보다 조건이 느슨하다 — 더러워도 지울 수 있다(브랜치·부산물만 건드린다).
    #    다만 **역할과 체크아웃은 그대로 본다.** 요청자 기계는 마스터가 치울 곳이 아니다.
    targets = [f for f in facts if pick_worker([f]).chosen is not None]
    closed = closed_tasks()
    if closed is None:
        print("  [주의] 큐를 못 읽었다 — 부산물은 손대지 않는다 (브랜치만 본다)")

    print(f"프로젝트 {paths.name} · 기준 브랜치 origin/{base}")
    rc = 0
    for f in targets:
        plan = survey(f, base_branch=base, closed=closed)
        print(_render(plan))
        if cmd == "apply":
            if not plan.delete and not plan.drop_dirs and not plan.park:
                print("    (지울 것 없음)")
                continue
            done = apply(f, plan)
            if done["parked"]:
                print(f"    [완료] {done['parked']} 로 복귀")
            print(f"    [완료] 브랜치 {len(done['branches'])} · 부산물 {len(done['dirs'])} 삭제")
            for e in done["errors"]:
                print(f"    [중요] {e}")
                rc = 1
            # [중요] 복귀했으면 **한 번 더 본다.** 방금까지 서 있던 브랜치는 1회차에 삭제
            # 후보에서 빠져 있었다 — 2회차를 사람이 기억해야 하는 건 설계가 아니다.
            # 상한은 2회다(복귀는 한 번뿐이므로 더 돌 이유가 없다).
            if done["parked"]:
                again = survey(f, base_branch=base, closed=closed)
                if again.delete or again.drop_dirs:
                    print(_render(again))
                    d2 = apply(f, again)
                    print(f"    [완료] (2회차) 브랜치 {len(d2['branches'])} · 부산물 {len(d2['dirs'])} 삭제")
                    for e in d2["errors"]:
                        print(f"    [중요] {e}")
                        rc = 1
    if cmd == "plan":
        print("\n  [중요] 아무것도 지우지 않았다. 실행하려면 `apply`.")
    return rc


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
