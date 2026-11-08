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

## [중요] 예외 하나 — 큐가 취소(cancelled)로 종결한 work 의 `task/<W>/*` (`#787`, 2026-10-10)

🔴 **반려(rejected) work 은 지우지 않는다** (`#821` · 사용자 결정 2026-10-13: *"브랜치는 분리되어
있어, 문법 문제든 검증 실패든 main 은 온존하니 그냥 놔두고 사용자에게 고지해"*). 실측 2026-10-11:
work `#817` 이 층2 인프라 예외 한 조각 때문에 `rejected` 가 됐고 이 정리가 **성공 조각 8개의
브랜치**까지 지웠다. 반려 work 은 계획에 `[보존]` 사유와 함께 남고, 고지는 라운드 공지가 한다.

사용자 승인(2026-10-10): **취소로 종결된** work 의 원격 브랜치는 도달 불가여도 지운다 —
증거는 **팁 해시**로 남긴다(저널 · 그 work 의 레드마인 노트 · 마스터 트윈의
`refs/ax/pruned/task/<W>/…` 로컬 보존). 판정은 **여기서** 한다 — push 직전에 큐를 다시 읽어
`merge_status == cancelled` 이고 조각이 전부 terminal 인지 보고, 그 push 의 환경에만
`AX_PRUNE_TERMINAL_WORK=<W>` 를 싣는다. 훅은 큐를 묻지 않고 **그 work 하나의 접두어**만 통과시킨다.
[중요] 자동 실행 자리는 `autodispatch --catchup`(10분 타이머) — 마운트된 프로젝트만, 그리고
**설치된 훅이 원본과 같을 때만** 돈다(낡은 훅이면 반쯤 지우게 되므로 건너뛰고 그 사실을 찍는다).
수동: `python -m master.work.cleanup terminal [프로젝트] [--apply]` (기본은 드라이런).

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
    lag: str = ""                                        # `#333` ⓒ — main 이 origin/main 과 어긋난 정도
    errors: list = field(default_factory=list)

    @property
    def summary(self) -> str:
        s = (f"{self.host}: 브랜치 삭제 {len(self.delete)} · 보존 {len(self.keep)}"
             f" · 부산물 삭제 {len(self.drop_dirs)} · 보존 {len(self.keep_dirs)}")
        if self.park:
            s += (f" · {self.current} → {self.park} 복귀" if self.current != self.park
                  else f" · {self.park} 를 origin/{self.park} 로 앞당긴다") + (f" ({self.lag})" if self.lag else "")
        elif self.lag:
            s += f" · {self.lag}"
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
    # [중요] **범위가 `Source/` 뿐이었다 — `#321` 완료 조건 4 가 지목한 그 구멍이다.**
    #    조건이 이름 붙인 손실 경로는 미커밋 **`.uasset`**(= `Content/`)인데, 가드는 그것을
    #    보지 않았다. 트리 전체로 넓힌다.
    # [주의] **추적 파일만** 본다(`-uno`). 미추적까지 세면 빌드 부산물 하나로 정리가 영영
    #    안 돌고, 그 방향의 실패는 조용하다 — 「가드가 있는데 아무것도 안 지워진다」로 보인다.
    #    미추적 파일은 `git checkout` 이 지우지도 않으므로 손실 경로가 아니다.
    if p.current and _OURS.match(p.current):
        rc, out = _git(facts, "status --porcelain -uno", runner=runner)
        if rc != 0:
            p.errors.append("더티 확인 실패 — 브랜치를 되돌리지 않는다")
        elif out.strip():
            first = [ln.strip() for ln in out.splitlines() if ln.strip()][:3]
            p.keep.append((p.current, f"{base_branch} 로 되돌리지 않았다 — 추적 파일이 더럽다: "
                                      + ", ".join(first)))
        else:
            p.park = base_branch
    elif p.current == base_branch:
        # 🔴 `#333` ⓒ (사용자 결정 2026-11-01, (가)) — 사이클이 중간에 죽어 #871 의 복귀(-B main origin/main)를
        #    못 탔으면 로컬 main 이 옛 트리로 남는다. 보이고, 깨끗하고 **앞선 커밋이 없을 때만** 앞당긴다
        #    (`merge --ff-only` — 커밋을 잃는 경로가 없다). 재지 못하면 아무것도 하지 않는다.
        rb, ob = _git(facts, f"rev-list --count {base_branch}..origin/{base_branch}", runner=runner)
        ra, oa = _git(facts, f"rev-list --count origin/{base_branch}..{base_branch}", runner=runner)
        try:
            behind = int(ob.strip()) if rb == 0 else None
            ahead = int(oa.strip()) if ra == 0 else None
        except ValueError:
            behind = ahead = None
        if behind is None or ahead is None:
            p.lag = f"{base_branch} 뒤처짐을 재지 못했다 — 앞당기지 않는다"
        elif ahead:
            p.lag = f"{base_branch} 에 origin 에 없는 커밋 {ahead}개 — 사람이 볼 것(앞당기지 않는다)"
        elif behind:
            rc, out = _git(facts, "status --porcelain -uno", runner=runner)
            if rc != 0:
                p.lag = f"{base_branch} 가 {behind} 커밋 뒤 · 더티 확인 실패 — 앞당기지 않는다"
            elif out.strip():
                p.lag = f"{base_branch} 가 {behind} 커밋 뒤 · 추적 파일이 더럽다 — 앞당기지 않는다"
            else:
                p.park, p.lag = base_branch, f"origin/{base_branch} 보다 {behind} 커밋 뒤"

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
            # `#333` ⓒ — 복귀한 main 을 origin 에 맞춘다. ff-only 라 커밋을 잃지 않는다(갈라졌으면 실패만 기록)
            rc2, out2 = _git(facts, f"merge --ff-only -q origin/{plan.park}", runner=runner)
            if rc2 != 0:
                done["errors"].append(f"{plan.park} 앞당기기(ff) 실패 — 그대로 둔다: {out2.strip()[:80]}")
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


CANDIDATE_LABEL = "클라우드 후보(미채택)"                 # `#840` T4
REPLACED_LABEL = "채택으로 대체된 원래 조각"               # `#840` T4


@dataclass
class RemotePlan:
    """원격 attempt/task 의 처분 계획. [중요] 판정 불가는 전부 「보존」 쪽으로 넘어진다.

    `#840` T4 — 도달 불가(보존)분 중 클라우드 재검증 부류는 `keep` 이 아니라 따로 든다:
    `candidates`(미채택 후보) · `replaced`(⑦ 에서 후보 채택으로 대체된 원래 조각). [중요] 둘 다
    **지우지 않는다** — 사용자 결정(보고만). 도달 가능한 후보(채택분)는 종전대로 `delete` 다.
    """
    delete: list = field(default_factory=list)       # [(ref, tip)] — 기준에서 도달 가능
    keep: list = field(default_factory=list)         # [(ref, tip, 사유)] — 사람 몫
    candidates: list = field(default_factory=list)   # [(ref, tip, 사유)] — 미채택 후보 · 보존
    replaced: list = field(default_factory=list)     # [(ref, tip, 사유)] — 대체된 원래 조각 · 보존
    error: str = ""

    def render(self) -> str:
        out = [f"  원격(gitea-write): 삭제 후보 {len(self.delete)} · 보존 {len(self.keep)}"
               + (f" · {CANDIDATE_LABEL} {len(self.candidates)}" if self.candidates else "")
               + (f" · {REPLACED_LABEL} {len(self.replaced)}" if self.replaced else "")]
        for ref, tip in self.delete:
            out.append(f"    [삭제] {ref} @ {tip[:8]} — 기준에서 도달 가능(병합됨)")
        for ref, tip, why in self.keep:
            out.append(f"    [보존] {ref} @ {tip[:8]} — {why}")
        for ref, tip, why in self.candidates:
            out.append(f"    [보존·{CANDIDATE_LABEL}] {ref} @ {tip[:8]} — {why}")
        for ref, tip, why in self.replaced:
            out.append(f"    [보존·{REPLACED_LABEL}] {ref} @ {tip[:8]} — {why}")
        if self.error:
            out.append(f"    [중요] {self.error}")
        return "\n".join(out)


def _piece_of(ref: str) -> str:
    """`task/<W>/<T>` · `task/<W>/r<N>/<T>` 조각 이름이면 work_id, 아니면 "" (후보·base 제외)."""
    from .branch_names import BASE_LEAF, parse_candidate
    parts = ref.split("/")
    if parse_candidate(ref) or len(parts) not in (3, 4) or parts[0] != "task":
        return ""
    if len(parts) == 3 and parts[2] == BASE_LEAF:
        return ""
    if len(parts) == 4 and not re.fullmatch(r"r\d+", parts[2]):
        return ""
    return parts[1]


def _classify_candidates(repo, plan: "RemotePlan", bases: dict, *, git, log) -> None:
    """`#840` T4 — `plan.keep`(도달 불가) 중 후보·대체된 원래 조각을 따로 옮긴다. **읽기만 한다.**

    대체 판정의 증거는 ⑦ 채택 머지 제목(`review.parse_adopt_subject`)이다 — 기준 이력과, 로컬에
    객체가 있는 작업 브랜치 팁에서 찾는다. 객체가 없거나 조회가 실패하면 그 조각은 종전대로
    `keep` 에 남는다(「대체 아님」이 아니라 「모름」 — 로그로 밝힌다).
    """
    from .attempt import GitError
    from .branch_names import parse_candidate
    from .review import parse_adopt_subject, ADOPT_MARK
    rest = []
    for ref, tip, why in plan.keep:
        if parse_candidate(ref):
            plan.candidates.append((ref, tip, f"{why} · ⑦ 에서 채택되지 않았다 — 지우지 않는다(보고만 · #840)"))
        else:
            rest.append((ref, tip, why))
    plan.keep = rest
    works = sorted({w for w in (_piece_of(r) for r, _, _ in plan.keep) if w})
    if plan.candidates:
        log(f"{CANDIDATE_LABEL} {len(plan.candidates)}건 — 보존·보고만 (#840): "
            + ", ".join(r for r, _, _ in plan.candidates[:6]))
    if not works:
        return
    revs, unseen = [_CLEANUP_BASE_REF], []
    for w in works:
        tip = bases.get(w)
        if not tip:
            continue
        try:
            git(repo, "cat-file", "-e", f"{tip}^{{commit}}")
            revs.append(tip)
        except GitError:
            unseen.append(w)
    try:
        out = git(repo, "log", "--merges", "--format=%s", "--fixed-strings",
                  f"--grep={ADOPT_MARK}", *revs, "--")
    except GitError as e:
        log(f"[주의] 채택 이력 조회 실패 — 대체된 원래 조각을 가리지 못했다(보존은 그대로): {e}")
        return
    pairs = {}
    for line in out.splitlines():
        got = parse_adopt_subject(line)
        if got:
            pairs[got["durable"]] = got["candidate"]
    rest = []
    for ref, tip, why in plan.keep:
        if ref in pairs:
            plan.replaced.append((ref, tip, f"⑦ 에서 `{pairs[ref]}` 채택으로 대체 — 작업 브랜치에서도 "
                                            f"도달 불가, 지우지 않는다(보고만 · #840)"))
        else:
            rest.append((ref, tip, why))
    plan.keep = rest
    if plan.replaced:
        log(f"{REPLACED_LABEL} {len(plan.replaced)}건 — 보존·보고만 (#840): "
            + ", ".join(r for r, _, _ in plan.replaced[:6]))
    if unseen:
        log(f"[주의] 작업 브랜치 객체가 로컬에 없다 — 대체 여부 모름(보존): {', '.join(unseen[:6])}")


def survey_remote(paths, *, base_branch: str = "main", git=None, logf=None) -> RemotePlan:
    """gitea-write 의 attempt/*·task/* 를 세고 **기준 도달 가능성**으로 가른다.

    [중요] 기준 팁을 fetch 하면 그 조상 전부가 로컬에 온다 — 도달 가능한 팁은 반드시
    로컬에 존재하므로, `merge-base --is-ancestor` 가 객체 부재로 죽는 경우는 곧
    「도달 불가」다. 판정 실패의 방향은 언제나 보존이다.

    `#840` T4 — 보존분 중 클라우드 후보(미채택)·채택으로 대체된 원래 조각은 `candidates`·
    `replaced` 로 따로 든다(`_classify_candidates`). 지우는 판정은 바뀌지 않는다.
    """
    from pathlib import Path as _P

    from .attempt import WRITE_REMOTE, GitError, _git
    g = git or _git
    log = logf or (lambda m: print(f"[cleanup] {m}", flush=True))
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
    bases: dict = {}
    for ln in out.splitlines():
        parts = ln.split()
        if len(parts) != 2:
            continue
        tip, ref = parts[0], parts[1].removeprefix("refs/heads/")
        bits = ref.split("/")
        if len(bits) == 3 and bits[0] == "task" and bits[2] == "base":
            bases[bits[1]] = tip
        try:
            g(repo, "merge-base", "--is-ancestor", tip, _CLEANUP_BASE_REF)
            p.delete.append((ref, tip))
        except GitError:
            p.keep.append((ref, tip, f"origin/{base_branch} 에 없다 — 병합 안 됨, 사람 몫"))
    _classify_candidates(repo, p, bases, git=g, log=log)
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


# ── 종결 work 의 원격 브랜치 (`#787` ① — 사용자 승인 2026-10-10) ──────────────────────
#
# 🔴 `#821` (사용자 결정 2026-10-13) — **지우는 것은 cancelled 뿐이다.** rejected 는 후보로 세되
# `terminal_skip_reason` 이 보존 사유를 돌려준다(계획·로그에 `[보존]` 으로 보인다).
#
# [중요] **판정은 큐, 집행은 훅의 좁은 예외.** 이 모듈이 push 직전에 큐를 다시 읽어 종결을
# 확인하고, 그 push 프로세스의 환경에만 `AX_PRUNE_TERMINAL_WORK=<W>` 를 싣는다. 훅
# (`pre_push_hook.sh` 예외 ⓑ)은 큐를 모르고 **그 work 하나의 `refs/heads/task/<W>/` 접두어**만
# 통과시킨다 — 다른 work·다른 접두어의 도달 불가 삭제는 그대로 거부된다.
# [중요] **지우기 전에 보존한다** — `refs/ax/pruned/task/<W>/…` 로 fetch 하고 해시가 맞는지 대조한
#    뒤에만 지운다. 삭제는 `--force-with-lease=<ref>:<팁>` 이라 **기록한 그 팁**만 지운다.
#    기록(저널 줄 + 레드마인 노트)에 `git push <remote> <팁>:refs/heads/<ref>` 복원 명령을 싣는다.

TERMINAL_WORK_ENV = "AX_PRUNE_TERMINAL_WORK"
TERMINAL_MERGE_STATUSES = ("rejected", "cancelled")       # 후보로 세는 종결 상태
PRUNABLE_MERGE_STATUSES = ("cancelled",)                   # 🔴 `#821` — 실제로 지우는 것은 이것뿐
REJECTED_KEEP_REASON = ("반려(rejected) work — 브랜치 보존, 라운드 공지로 고지 "
                        "(#821 · 사용자 결정 2026-10-13)")
_TASK_TERMINAL = ("verified", "failed", "cancelled")
PRUNED_NS = "refs/ax/pruned"


@dataclass
class TerminalWork:
    work_id: str
    status: str = ""
    project: str = ""
    issue_id: str = ""
    refs: list = field(default_factory=list)          # [(ref, tip)] — ref 는 refs/heads/ 뗀 이름
    skip: str = ""                                    # 비어 있지 않으면 지우지 않는다(사유)

    @property
    def candidates(self) -> list:
        """`#840` T4 — `refs` 중 클라우드 재검증 후보. [중요] 처분은 다른 ref 와 같다(취소 work 정책 ·
        `refs/ax/pruned` 보존) — 사람이 따로 보게 **이름만** 가른다."""
        from .branch_names import parse_candidate
        return [(r, t) for r, t in self.refs if parse_candidate(r)]


@dataclass
class TerminalPlan:
    project: str = ""
    remote: str = ""
    works: list = field(default_factory=list)
    hook_state: str = ""
    error: str = ""

    def render(self) -> str:
        n = sum(len(w.refs) for w in self.works if not w.skip)
        out = [f"  종결 work 원격 브랜치 ({self.remote}) · 프로젝트 {self.project} · "
               f"대상 work {len([w for w in self.works if not w.skip])} · ref {n} · "
               f"훅 {self.hook_state or '?'}"]
        for w in self.works:
            head = (f"    work {w.work_id} · {w.status} · 레드마인 "
                    f"{('#' + w.issue_id) if w.issue_id else '(없음)'}")
            cands = {r for r, _ in w.candidates}
            out.append(head + (f" · 클라우드 후보 {len(cands)}" if cands else "")
                       + (f" · [보존] {w.skip}" if w.skip else ""))
            for ref, tip in w.refs:
                tag = ("[보존" if w.skip else "[삭제") + ("·클라우드 후보]" if ref in cands else "]")
                out.append(f"      {tag} {ref} @ {tip}  ({w.status})")
        if not self.works and not self.error:
            out.append("    (종결 work 의 남은 브랜치 없음)")
        if self.error:
            out.append(f"    [중요] {self.error}")
        return "\n".join(out)


def _queue_api(api):
    if api is not None:
        return api
    from .runner import _api
    return _api


def terminal_skip_reason(work: dict, tasks) -> str:
    """종결 work 로 지워도 되는가. `""` 이면 된다 — **그 외엔 사유**(지우지 않는다)."""
    st = str((work or {}).get("merge_status") or "")
    if st not in TERMINAL_MERGE_STATUSES:
        return f"merge_status={st!r} — 종결(rejected/cancelled) 이 아니다"
    if st not in PRUNABLE_MERGE_STATUSES:
        # 🔴 `#821` — 반려 work 은 문법·검증 실패여도 main 과 분리돼 있으므로 남긴다.
        #    골조 재작업 대상이면 종전의 더 구체적인 사유를 그대로 돌려준다(어느 쪽이든 보존).
        from .workmodel import Work
        if Work.from_record(work, tasks).execution_summary()["rework_required"]:
            return "골조 재작업 대상 — 통합 기준과 실패·성공 결과 브랜치를 보존한다"
        return REJECTED_KEEP_REASON
    live = [t.get("task_id") for t in (tasks or [])
            if str(t.get("status") or "") not in _TASK_TERMINAL]
    if live:
        return f"아직 terminal 이 아닌 조각이 있다: {', '.join(map(str, live[:4]))}"
    return ""


def _ls_task_refs(repo, remote: str, *, git=None) -> dict:
    """`{work_id: [(ref, tip)]}` — `refs/heads/task/<W>/…` 를 한 번에 센다."""
    from .attempt import _git
    g = git or _git
    out = g(repo, "ls-remote", "--heads", remote, "refs/heads/task/*")
    found: dict = {}
    for ln in out.splitlines():
        parts = ln.split()
        if len(parts) != 2 or not parts[1].startswith("refs/heads/task/"):
            continue
        ref = parts[1][len("refs/heads/"):]
        wid = ref.split("/")[1] if ref.count("/") >= 2 else ""
        if not wid or not _TASK_ID.match(wid):
            continue
        found.setdefault(wid, []).append((ref, parts[0]))
    return found


def survey_terminal(paths, *, api=None, remote: str = "", project: str = "",
                    git=None) -> TerminalPlan:
    """[중요] **읽기만 한다** — 큐(works·tasks)와 `ls-remote` 만 부른다."""
    from pathlib import Path as _P

    from .attempt import WRITE_REMOTE, GitError, hook_status
    remote = remote or WRITE_REMOTE
    call = _queue_api(api)
    name = project or getattr(paths, "name", "") or ""
    plan = TerminalPlan(project=name, remote=remote)
    try:
        plan.hook_state = str(hook_status(paths).get("state") or "")
    except Exception as e:                                # noqa: BLE001
        plan.hook_state = f"확인 실패 ({type(e).__name__})"
    try:
        works = call("GET", f"/api/v1/works?project={name}") if name else call("GET", "/api/v1/works")
    except Exception as e:                                # noqa: BLE001
        plan.error = f"큐를 못 읽었다 — 아무것도 판정하지 않는다: {type(e).__name__}: {e}"
        return plan
    rows = works if isinstance(works, list) else []
    cand = {}
    for w in rows:
        wid = str(w.get("work_id") or "")
        if not wid or not _TASK_ID.match(wid):
            continue
        if str(w.get("merge_status") or "") not in TERMINAL_MERGE_STATUSES:
            continue
        stamp = str(w.get("project") or "").strip()
        if name and stamp and stamp != name:
            continue
        cand[wid] = w
    if not cand:
        return plan
    try:
        found = _ls_task_refs(_P(paths.repo), remote, git=git)
    except GitError as e:
        plan.error = f"원격을 못 봤다 — 아무것도 판정하지 않는다: {e}"
        return plan
    for wid in sorted(cand):
        refs = sorted(found.get(wid) or [])
        if not refs:
            continue                                      # 이미 정리됐다 — 멱등
        tw = TerminalWork(work_id=wid, project=name, refs=refs,
                          status=str(cand[wid].get("merge_status") or ""),
                          issue_id=str(cand[wid].get("redmine_issue_id") or ""))
        try:
            resp = call("GET", f"/api/v1/works/{wid}") or {}
            tw.skip = terminal_skip_reason(resp.get("work") or {}, resp.get("tasks") or [])
            tw.status = str((resp.get("work") or {}).get("merge_status") or tw.status)
        except Exception as e:                            # noqa: BLE001
            tw.skip = f"work 상세를 못 읽었다 ({type(e).__name__}) — 보존"
        plan.works.append(tw)
    return plan


def _push_delete(repo, remote: str, ref: str, tip: str, *, allow_work: str = "") -> tuple:
    """`push --delete` 한 번. [중요] 예외 변수는 **이 프로세스의 환경에만** 싣는다."""
    import os
    import subprocess

    from .coordinator import _git_cmd
    env = {k: v for k, v in os.environ.items() if k != TERMINAL_WORK_ENV}
    if allow_work:
        env[TERMINAL_WORK_ENV] = allow_work
    r = subprocess.run(_git_cmd(repo, "push", f"--force-with-lease=refs/heads/{ref}:{tip}",
                                remote, "--delete", f"refs/heads/{ref}"),
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=GIT_TIMEOUT, env=env)
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


def _terminal_note(tw: TerminalWork, deleted: list, failed: list, remote: str) -> str:
    lines = [f"[브랜치 정리] 종결 work ({tw.status}) 의 원격 브랜치 {len(deleted)}건 삭제 (#787)",
             "", f"- work_id: {tw.work_id}",
             f"- 마스터 트윈 로컬 보존: {PRUNED_NS}/task/{tw.work_id}/…",
             "", "## 지운 ref 와 팁 (해시로 복원)"]
    for ref, tip in deleted:
        lines.append(f"- {ref} @ {tip}")
    cands = {r for r, _ in tw.candidates}
    gone = [(r, t) for r, t in deleted if r in cands]
    if gone:
        # `#840` T4 — 같은 정책으로 지웠지만 사람이 따로 보게 이름을 다시 적는다
        lines += ["", f"## 그중 클라우드 재검증 후보 {len(gone)}건 (#840 — 미채택 상태로 취소됨)"]
        lines += [f"- {ref} @ {tip}" for ref, tip in gone]
    lines += ["", "복원: git push " + remote + " <팁>:refs/heads/<ref>"]
    if failed:
        lines += ["", "## 지우지 못한 것"] + [f"- {ref}: {why[:160]}" for ref, why in failed]
    return "\n".join(lines)


def apply_terminal(paths, plan: TerminalPlan, *, api=None, git=None,
                   require_current_hook: bool = True, logf=None) -> dict:
    """계획된 종결 work 의 원격 브랜치를 지운다. **work 마다 큐를 다시 읽는다.**"""
    from pathlib import Path as _P

    from .attempt import STATE_OK, GitError, _git, hook_status
    g = git or _git
    log = logf or (lambda m: print(f"[prune] {m}", flush=True))
    call = _queue_api(api)
    repo = _P(paths.repo)
    remote = plan.remote
    done = {"deleted": [], "failed": [], "skipped": [], "notes": []}
    if plan.error:
        done["skipped"].append(("*", plan.error))
        return done
    if require_current_hook:
        st = hook_status(paths)
        if st.get("state") != STATE_OK:
            why = (f"[중요] 설치된 pre-push 훅이 원본과 같지 않다(state={st.get('state')}) — "
                   f"종결 work 예외(#787)가 없을 수 있어 반쯤 지우게 된다. 건너뛴다. "
                   f"복구: python -m master.work.attempt install-hook {plan.project}")
            log(why)
            done["skipped"].append(("*", why))
            return done
    for tw in plan.works:
        if tw.skip:
            done["skipped"].append((tw.work_id, tw.skip))
            continue
        # ① 지금 다시 큐를 본다 — 판정은 push 직전의 상태로 한다
        try:
            resp = call("GET", f"/api/v1/works/{tw.work_id}") or {}
            why = terminal_skip_reason(resp.get("work") or {}, resp.get("tasks") or [])
        except Exception as e:                            # noqa: BLE001
            why = f"큐 재확인 실패 ({type(e).__name__}: {e})"
        if why:
            log(f"{tw.work_id}: 건너뛴다 — {why}")
            done["skipped"].append((tw.work_id, why))
            continue
        # ② 지우기 전에 보존한다 — 실패하면 그 work 은 지우지 않는다
        try:
            g(repo, "fetch", "--no-tags", remote,
              f"+refs/heads/task/{tw.work_id}/*:{PRUNED_NS}/task/{tw.work_id}/*")
        except GitError as e:
            why = f"보존 fetch 실패 — 지우지 않는다: {e}"
            log(f"{tw.work_id}: {why}")
            done["skipped"].append((tw.work_id, why))
            continue
        deleted, failed = [], []
        cand_refs = {r for r, _ in tw.candidates}
        if cand_refs:
            log(f"{tw.work_id}: 클라우드 후보 {len(cand_refs)}건도 취소 work 정책대로 지운다 "
                f"(팁은 {PRUNED_NS} 에 보존 · #840): " + ", ".join(sorted(cand_refs)[:6]))
        for ref, tip in tw.refs:
            try:
                kept = g(repo, "rev-parse", "--verify", "--quiet", f"{PRUNED_NS}/{ref}")
            except GitError:
                kept = ""
            if kept.strip() != tip:
                failed.append((ref, f"보존 ref 가 팁과 다르다({kept.strip()[:12] or '없음'}) — 안 지운다"))
                log(f"[중요] {ref} @ {tip} — 보존 대조 실패, 지우지 않는다")
                continue
            rc, out = _push_delete(repo, remote, ref, tip, allow_work=tw.work_id)
            if rc == 0:
                deleted.append((ref, tip))
                log(f"삭제 {ref} @ {tip} (work {tw.work_id} · {tw.status}"
                    + (" · 클라우드 후보 #840" if ref in cand_refs else "")
                    + f" · 복원: git push {remote} {tip}:refs/heads/{ref})")
            else:
                failed.append((ref, out))
                log(f"[중요] 삭제 실패 {ref} @ {tip} — {out[:200]}")
        done["deleted"] += [(tw.work_id, r, t) for r, t in deleted]
        done["failed"] += [(tw.work_id, r, w) for r, w in failed]
        if deleted and tw.issue_id:
            try:
                resp = call("POST", "/api/v1/redmine/note",
                            {"project": tw.project, "issue_id": int(tw.issue_id),
                             "notes": _terminal_note(tw, deleted, failed, remote),
                             "work_id": tw.work_id})
                ok = not (isinstance(resp, dict) and resp.get("ok") is False)
                msg = (f"레드마인 #{tw.issue_id} 기록" if ok else
                       f"[중요] 레드마인 #{tw.issue_id} 기록 실패 — {resp}")
            except Exception as e:                        # noqa: BLE001
                msg = f"[중요] 레드마인 #{tw.issue_id} 기록 실패 — {type(e).__name__}: {e}"
            log(f"{tw.work_id}: {msg}")
            done["notes"].append((tw.work_id, msg))
        elif deleted:
            msg = f"[주의] {tw.work_id}: 레드마인 이슈 id 가 없다 — 저널과 {PRUNED_NS} 에만 남는다"
            log(msg)
            done["notes"].append((tw.work_id, msg))
    return done


# ── 보존 고지는 한 번만 (`#821` 후속) ─────────────────────────────────────────────────
#
# `#821` 이후 반려 work 은 **영원히** 보존 대상이라, 10분 catchup 마다 같은 「보존」 줄이 쌓였다.
# 그래서 `(프로젝트/work, 사유)` 를 한 번만 찍는다 — 상태는 파견기와 같은 디렉토리
# (`~/.cache/ax-dispatch/`, `hold.json` 옆)의 작은 JSON 이다. 사유가 바뀌면 다시 찍는다.
# [중요] **지우고 남기는 판정과 무관하다** — 줄을 줄일 뿐이다. 상태를 못 읽거나 못 쓰면
# 종전처럼 전부 찍고, 못 저장한 사실을 **한 줄** 남긴다(조용히 넘기지 않는다 · 죽지 않는다).

PRUNE_STATE_ENV = "AX_PRUNE_STATE_DIR"
PRUNE_STATE_FILE = "prune_reported.json"


def prune_state_path():
    import os
    from pathlib import Path as _P
    d = os.environ.get(PRUNE_STATE_ENV)
    return (_P(d) if d else _P.home() / ".cache" / "ax-dispatch") / PRUNE_STATE_FILE


def _report_kept_once(project: str, skips: dict, log) -> None:
    """`skips` = `{work_id: 보존 사유}`. 새것·사유가 바뀐 것만 「보존」 줄로 찍는다."""
    import json
    import os
    path = prune_state_path()
    prev: dict = {}
    try:
        if path.exists():
            got = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(got, dict):
                raise ValueError(f"형식이 dict 가 아니다({type(got).__name__})")
            prev = {str(k): str(v) for k, v in got.items()}
    except Exception as e:                                   # noqa: BLE001
        log(f"[주의] 보존 고지 상태를 읽지 못했다({PRUNE_STATE_FILE}) — "
            f"{type(e).__name__}: {e} · 이번 회차는 보존 줄을 전부 찍는다")
        prev = {}
    prefix = f"{project}/"
    cur = {f"{prefix}{wid}": why for wid, why in skips.items()}
    for wid, why in skips.items():
        if prev.get(f"{prefix}{wid}") != why:
            log(f"{wid}: 보존 — {why}")
    # 다른 프로젝트 항목은 그대로 두고, 이 프로젝트는 지금 보존 중인 것만 남긴다
    new = {k: v for k, v in prev.items() if not k.startswith(prefix)}
    new.update(cur)
    if new == prev:
        return
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(new, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                       encoding="utf-8")
        os.replace(tmp, path)
    except Exception as e:                                   # noqa: BLE001
        log(f"[주의] 보존 고지 상태를 저장하지 못했다({PRUNE_STATE_FILE}) — "
            f"{type(e).__name__}: {e} · 다음 회차에 같은 보존 줄이 다시 찍힌다")
        try:
            tmp.unlink()
        except OSError:
            pass


def sweep_terminal(paths=None, *, api=None, apply_: bool = True, logf=None) -> dict:
    """`autodispatch --catchup` 이 부르는 자리. **마운트된 프로젝트만** 본다(마운트 규칙)."""
    from ..context_search.paths import resolve
    log = logf or (lambda m: print(f"[prune] {m}", flush=True))
    paths = paths or resolve("")
    plan = survey_terminal(paths, api=api)
    n = sum(len(w.refs) for w in plan.works if not w.skip)
    if plan.error:
        log(f"[중요] {paths.name}: {plan.error}")
        return {"deleted": [], "failed": [], "skipped": [("*", plan.error)], "notes": []}
    # `#821` 후속 — 같은 (work, 사유) 의 「보존」 줄은 한 번만 찍는다(상태 실패 시 전부 찍는다)
    _report_kept_once(paths.name, {w.work_id: w.skip for w in plan.works if w.skip}, log)
    if not n:
        return {"deleted": [], "failed": [], "skipped": [], "notes": []}
    nc = sum(len(w.candidates) for w in plan.works if not w.skip)
    log(f"{paths.name}: 종결 work 원격 브랜치 {n}건 정리 시작"
        + (f" (그중 클라우드 후보 {nc}건 · #840)" if nc else ""))
    if not apply_:
        return {"deleted": [], "failed": [], "skipped": [], "notes": [], "plan": plan}
    return apply_terminal(paths, plan, api=api, logf=log)


# ── ⓐ 기계 단위 열거 (`#333`) — **읽기 전용** ───────────────────────────────────
#
# [DOC] #333 ⓐ: `plan` 은 한 프로젝트의 워커 로컬 브랜치와 `.ax/work` 만 보고 worktree 는 0 이었다 —
#       08-29·09-01·09-09 세 번 손으로 치운 잔재(요청자 검수·전진 worktree · 죽은 등록 · 지워진 원격의
#       추적 ref · 같은 기계의 다른 프로젝트 소속)가 그때마다 「0건」 으로 보였다. 여기서는 **기계마다
#       등록된 체크아웃 전부(모든 프로젝트) + 마스터 저장소**를 `git worktree list` 로 연다 — 이름 패턴
#       금지(09-01 `ms-wt-probe` 는 `ax-wt-*` 밖이었다). 🔴 아무것도 지우지 않는다 · 쓰는 git 명령 0.
#       안전 조건(09-01 미추적 유실): worktree 마다 미추적·수정 수를 싣고, 하나라도 있으면 「사람이 볼
#       것」이다. 도달 가능성은 커밋만 본다 — 미추적은 따로 센다.

@dataclass
class RepoScan:
    """저장소 하나의 열거 결과. `candidates`=[(무엇, 사유)] · `review`=[(무엇, 사유)]."""
    machine: str
    repo: str
    label: str = ""                     # 프로젝트·역할
    base_ref: str = ""
    candidates: list = field(default_factory=list)
    review: list = field(default_factory=list)
    worktrees: int = 0
    errors: list = field(default_factory=list)


def parse_worktrees(text: str) -> list:
    """`git worktree list --porcelain` → `[{path, head, branch, detached, prunable}]`. 첫 항목이 주 트리."""
    out, cur = [], None
    for raw in (text or "").splitlines():
        line = raw.rstrip("\r")
        if line.startswith("worktree "):
            cur = {"path": line[len("worktree "):].strip(), "head": "", "branch": "",
                   "detached": False, "prunable": ""}
            out.append(cur)
        elif cur is None:
            continue
        elif line.startswith("HEAD "):
            cur["head"] = line[5:].strip()
        elif line.startswith("branch "):
            cur["branch"] = line[7:].strip().removeprefix("refs/heads/")
        elif line == "detached":
            cur["detached"] = True
        elif line.startswith("prunable"):
            cur["prunable"] = line[len("prunable"):].strip() or "prunable"
    return out


def _status_counts(text: str) -> tuple:
    rows = [ln for ln in (text or "").splitlines() if ln.strip()]
    untracked = sum(1 for ln in rows if ln.startswith("??"))
    return untracked, len(rows) - untracked


_WID_RE = re.compile(r"\d{8}_\d{4}_[A-Za-z0-9_.-]+")


def work_id_of(path: str = "", branch: str = "") -> str:
    """worktree 경로의 마지막 이름이나 `task/<W>/…` 브랜치에서 work_id 를 뽑는다(`#874`). 없으면 ""."""
    for seg in ([x for x in branch.split("/") if x] + [path.replace("\\", "/").rstrip("/").split("/")[-1]]):
        m = _WID_RE.search(seg)
        if m:
            return m.group(0)
    return ""


def scan_repo(run, repo: str, *, machine: str, label: str = "", base: str = "main",
              work_status=None, local_branches: bool = False) -> RepoScan:
    """`run(path, args) -> (rc, out)` 로 `git -C <path> <args>` 를 돌려 열거한다. **읽기만 한다.**

    [DOC] #874: `work_status(work_id) -> merge_status | None` 를 주면 이름에서 뽑은 work_id 로 큐를 대조한다 —
          cancelled → 후보(#787 기준 · 이 저장소의 원격추적·refs/ax 밖 고유 커밋 수 — 다른 저장소(트윈 미러)의 보존은 모른다) · rejected → 볼 것(#821 보존) ·
          열린 work → 볼 것 · 조회 실패·id 없음 → 종전(도달 판정만). `local_branches=True`(마스터 저장소)면
          worktree 에 붙지 않은 로컬 브랜치도 연다 — `task/*`·`attempt/*` 는 같은 판정, `issue/*` 는 볼 것,
          그 밖(`fix/*` 등)은 도달 판정만(#886).
    """
    r = RepoScan(machine=machine, repo=repo, label=label)
    rc, out = run(repo, f"rev-parse --verify -q origin/{base}")
    if rc == 0 and out.strip():
        r.base_ref = f"origin/{base}"
    else:
        rc, out = run(repo, f"rev-parse --verify -q {base}")
        r.base_ref = base if (rc == 0 and out.strip()) else ""
    if not r.base_ref:
        r.errors.append(f"기준 ref(origin/{base}·{base})가 없다 — 도달 판정을 못 한다(전부 사람이 볼 것)")

    def reachable(sha: str):
        if not sha or not r.base_ref:
            return None
        rc2, _ = run(repo, f"merge-base --is-ancestor {sha} {r.base_ref}")
        return True if rc2 == 0 else (False if rc2 == 1 else None)

    def unique(sha: str) -> str:
        rc2, o2 = run(repo, f"rev-list --count {sha} --not --remotes --glob=refs/ax/*")
        return o2.strip() if rc2 == 0 and o2.strip().isdigit() else "?"

    def by_queue(wid: str, sha: str):
        """`(판정, 사유)` — 판정은 "candidate"·"review"·"" (큐로 못 정함 → 종전 판정)."""
        if not wid or work_status is None:
            return "", ""
        try:
            st = work_status(wid)
        except Exception:                                    # noqa: BLE001
            st = None
        if not st:
            return "", ""
        if st == "cancelled":
            n = unique(sha)
            return "candidate", (f"취소 work {wid}(#787 기준) · 이 저장소의 원격추적·refs/ax 밖 고유 커밋 {n}개"
                                 + (" — 지우면 그 커밋은 gc 대상" if n not in ("0", "?") else ""))
        if st == "rejected":
            return "review", f"반려 work {wid} — #821 보존(사람이 판단)"
        if st == "merged":
            return "", ""
        return "review", f"진행 중 work {wid}({st}) — 파이프라인이 쓰는 중일 수 있다"

    rc, out = run(repo, "worktree list --porcelain")
    if rc != 0:
        r.errors.append(f"worktree 목록 실패 ({out.strip()[:80]})")
        wts = []
    else:
        wts = parse_worktrees(out)
    r.worktrees = max(0, len(wts) - 1)
    for w in wts[1:]:                                     # 첫 항목 = 주 트리(체크아웃 자신)
        name = f"worktree {w['path']} @ {w['head'][:8] or '?'}" + (f" [{w['branch']}]" if w["branch"] else "")
        reach = reachable(w["head"])
        if w["prunable"]:
            if reach:
                r.candidates.append((name, f"죽은 등록({w['prunable']}) · HEAD 가 {r.base_ref} 에 도달 — "
                                           "`git worktree prune` 은 관리 정보만 지운다"))
            else:
                r.review.append((name, f"죽은 등록({w['prunable']}) · HEAD 가 {r.base_ref or '기준'} 에 "
                                       f"{'도달 불가' if reach is False else '도달 미판정'} — prune 하면 gc 대상이 될 수 있다"))
            continue
        rc, st = run(w["path"], "status --porcelain")
        if rc != 0:
            r.review.append((name, f"상태를 못 읽었다 ({st.strip()[:60]})"))
            continue
        un, mod = _status_counts(st)
        why = []
        if un:
            why.append(f"미추적 {un}")
        if mod:
            why.append(f"수정 {mod}")
        if reach is False:
            why.append(f"HEAD 가 {r.base_ref} 에 도달 불가")
        elif reach is None:
            why.append("도달 미판정")
        if un or mod:
            r.review.append((name, " · ".join(why) + " — 지우면 잃을 수 있다"))
            continue
        verdict, qwhy = by_queue(work_id_of(w["path"], w["branch"]), w["head"])
        if verdict == "candidate":
            r.candidates.append((name, f"미추적 0 · 수정 0 · {qwhy}"))
        elif verdict == "review":
            r.review.append((name, qwhy))
        elif why:
            r.review.append((name, " · ".join(why) + " — 지우면 잃을 수 있다"))
        else:
            r.candidates.append((name, f"미추적 0 · 수정 0 · HEAD 가 {r.base_ref} 에 도달"))

    if local_branches:
        # [DOC] #886: 종전에는 refs/heads/task·attempt 만 열어 병합된 fix/R* 8개가 「0건」으로 보였다.
        #       이제 refs/heads 전부를 연다 — 기준 브랜치·worktree 에 붙은 브랜치는 빼고, task/·attempt/ 는
        #       종전 큐 대조, issue/<N> 은 일감 흐름(issue_flow)이 소유하므로 늘 「볼 것」(보류 중이면
        #       main 에 도달해도 지우면 안 된다), 그 밖은 도달 판정만. 🔴 여전히 읽기 전용이다.
        held = {w["branch"] for w in wts if w["branch"]}
        rc, out = run(repo, "for-each-ref --format=%(refname:short):%(objectname) refs/heads")
        if rc != 0:
            r.errors.append(f"로컬 브랜치 목록 실패 ({out.strip()[:80]})")
        else:
            for ln in out.splitlines():
                if ":" not in ln:
                    continue
                br, sha = ln.strip().rsplit(":", 1)
                if br in held or br == base:
                    continue                                  # worktree 줄에서 이미 본다 · 기준 브랜치
                what = f"로컬 브랜치 {br} @ {sha[:8]}"
                if br.startswith("issue/"):
                    r.review.append((what, "일감 브랜치 — issue_flow 가 소유(보류 중일 수 있다) · "
                                           "마감·취소로 정리한다"))
                    continue
                pipeline = br.startswith(("task/", "attempt/"))
                verdict, qwhy = by_queue(work_id_of("", br), sha) if pipeline else ("", "")
                if verdict == "candidate":
                    r.candidates.append((what, qwhy))
                elif verdict == "review":
                    r.review.append((what, qwhy))
                else:
                    reach = reachable(sha)
                    if reach:
                        r.candidates.append((what, f"{r.base_ref} 에 도달 — 지워도 잃는 커밋 없음"))
                    else:
                        r.review.append((what, f"{r.base_ref or '기준'} 에 "
                                               f"{'도달 불가' if reach is False else '도달 미판정'} · "
                                               f"이 저장소의 원격추적·refs/ax 밖 고유 커밋 {unique(sha)}개"))

    rc, out = run(repo, "remote")
    remotes = {x.strip() for x in out.splitlines() if x.strip()} if rc == 0 else None
    if remotes is None:
        r.errors.append("원격 목록 실패 — 추적 ref 판정 생략")
        return r
    rc, out = run(repo, "for-each-ref --format=%(refname):%(objectname) refs/remotes")
    if rc != 0:
        r.errors.append(f"추적 ref 목록 실패 ({out.strip()[:80]})")
        return r
    gone: dict = {}
    for ln in out.splitlines():
        if ":" not in ln:
            continue
        ref, sha = ln.strip().rsplit(":", 1)
        parts = ref.split("/")
        if len(parts) < 4 or parts[2] in remotes:
            continue
        gone.setdefault(parts[2], []).append((ref, sha))
    for rem, refs in sorted(gone.items()):
        for ref, sha in refs:
            reach = reachable(sha)
            what = f"추적 ref {ref} @ {sha[:8]} (원격 `{rem}` 이 없다)"
            if reach:
                r.candidates.append((what, f"{r.base_ref} 에 도달 — 지워도 잃는 커밋 없음"))
            else:
                r.review.append((what, f"{r.base_ref or '기준'} 에 {'도달 불가' if reach is False else '도달 미판정'}"
                                       " — 이 ref 가 유일한 사본일 수 있다"))
    return r


def render_scan(r: RepoScan) -> str:
    head = (f"  {r.machine} {r.repo}" + (f" ({r.label})" if r.label else "")
            + f" — worktree {r.worktrees} · 지울 것 후보 {len(r.candidates)} · 사람이 볼 것 {len(r.review)}")
    out = [head]
    for e in r.errors:
        out.append(f"    [주의] {e}")
    for w, why in r.candidates:
        out.append(f"    후보   {w} — {why}")
    for w, why in r.review:
        out.append(f"    볼 것  {w} — {why}")
    return "\n".join(out)


def _local_run(path: str, args: str) -> tuple:
    import shlex
    import subprocess
    p = subprocess.run(["git", "-C", path, *shlex.split(args)], capture_output=True, text=True,
                       timeout=GIT_TIMEOUT)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _remote_run(host: str, user: str, windows: bool):
    def run(path: str, args: str) -> tuple:
        if windows:                                        # cmd 는 큰따옴표 · POSIX 는 작은따옴표(fmt_arg 와 같은 이유)
            spec = args.replace("--format=%(refname):%(objectname)", '--format="%(refname):%(objectname)"')
        else:
            spec = args.replace("--format=%(refname):%(objectname)", "--format='%(refname):%(objectname)'")
        return bundle._ssh(host, user, f'git -C "{path}" {spec}', timeout=GIT_TIMEOUT)
    return run


def machine_targets(*, registry=None) -> list:
    """`[(machine, run, [(repo, label)])]` — 마스터(로컬 저장소들) + 등록부의 모든 작업장(모든 프로젝트)."""
    from pathlib import Path
    from ..context_search.paths import resolve
    from ..projects.config import Registry
    reg = registry or Registry.load()
    master_repos = [(str(Path(__file__).resolve().parents[2]), "마스터 개발 클론")]
    by_host: dict = {}
    for name in reg.names:
        try:
            master_repos.append((str(resolve(name, registry=reg).repo), f"{name} 트윈 미러"))
        except Exception:                                    # noqa: BLE001
            pass
        try:
            ws = bundle.workshops(name)
        except Exception:                                    # noqa: BLE001
            continue
        for host, user, path, driven, role, _dp in ws:
            if not (user and path):
                continue
            ent = by_host.setdefault(host, {"user": user, "windows": (":" in path[:3]), "repos": []})
            tag = f"{name} · {role}" + (" · 사람 트리 — 보고만" if role != "worker" else "")
            ent["repos"].append((path, tag))
    out = [("마스터(.57)", _local_run, [(p, l) for p, l in master_repos if Path(p, ".git").exists()])]
    for host, ent in sorted(by_host.items()):
        out.append((host, _remote_run(host, ent["user"], ent["windows"]), ent["repos"]))
    return out


def _queue_status():
    """`work_id → merge_status | None` (`#874`). 큐 GET 만 — 실패는 None(종전 판정으로 물러난다)."""
    cache: dict = {}

    def get(wid: str):
        if wid not in cache:
            try:
                from .review import fetch_work
                work, _ = fetch_work(wid)
                cache[wid] = (work or {}).get("merge_status") or None
            except Exception:                                # noqa: BLE001
                cache[wid] = None
        return cache[wid]
    return get


def survey_machines(targets=None, *, work_status=None) -> list:
    ws = work_status if work_status is not None else _queue_status()
    return [scan_repo(run, repo, machine=m, label=label, work_status=ws,
                      local_branches=m.startswith("마스터"))          # 워커 로컬 브랜치는 plan 워커 구역이 본다
            for m, run, repos in (targets if targets is not None else machine_targets())
            for repo, label in repos]


def subbranch_label(ref: str, reachable: bool) -> str:
    """`merged-subs` 의 줄 머리. `#840` T4 — 클라우드 후보는 이름으로 따로 단다(판정은 그대로)."""
    from .branch_names import is_candidate
    if is_candidate(ref):
        return "[삭제·클라우드 후보(채택분)]" if reachable else f"[보존·{CANDIDATE_LABEL}]"
    return "[삭제]" if reachable else "[보존]"


def main(argv) -> int:
    from ..context_search.paths import resolve
    from ..projects.config import ProjectConfig
    from .runner import pick_worker            # 역할 필터를 그대로 쓴다

    cmd = (argv[0] if argv else "plan").strip()
    if cmd == "terminal":
        pos = [a for a in argv[1:] if not a.startswith("--")]
        paths = resolve(pos[0] if pos else "")
        plan = survey_terminal(paths)
        print(f"프로젝트 {paths.name} · 취소(cancelled) work 의 task/<W>/* (#787 · rejected 는 보존 #821)")
        print(plan.render())
        if "--apply" not in argv:
            print("\n  [중요] 드라이런 — 아무것도 지우지 않았다. 실행하려면 `terminal [프로젝트] --apply`.")
            return 1 if plan.error else 0
        done = apply_terminal(paths, plan)
        print(f"  [완료] 삭제 {len(done['deleted'])} · 실패 {len(done['failed'])} · "
              f"건너뜀 {len(done['skipped'])}")
        for wid, ref, tip in done["deleted"]:
            print(f"    삭제 {ref} @ {tip}")
        for wid, ref, why in done["failed"]:
            print(f"    [중요] {ref}: {why[:200]}")
        for wid, why in done["skipped"]:
            print(f"    건너뜀 {wid}: {why[:200]}")
        for wid, msg in done["notes"]:
            print(f"    {msg}")
        return 1 if (done["failed"] or any(w == "*" for w, _ in done["skipped"])) else 0
    if cmd == "merged-subs":
        # `#787` ② 의 수동판 — 이미 전진한 work 에 남은 `task/<W>/r<N>/*` 를 같은 판정으로 정리
        from pathlib import Path as _P

        from .attempt import WRITE_REMOTE, _git
        from .branch_names import is_candidate as _is_candidate
        from .review import prune_merged_subbranches, work_base_branch
        pos = [a for a in argv[1:] if not a.startswith("--")]
        if not pos:
            print("  merged-subs [프로젝트] <work_id> [--apply]")
            return 2
        wid = pos[-1]
        paths = resolve(pos[0] if len(pos) > 1 else "")
        if not _TASK_ID.match(wid):
            print(f"  [중요] work_id 가 이상하다: {wid!r}")
            return 2
        repo = _P(paths.repo)
        target = work_base_branch(wid)
        tracking = f"refs/remotes/{WRITE_REMOTE}/{target}"
        _git(repo, "fetch", "--no-tags", WRITE_REMOTE, f"+refs/heads/{target}:{tracking}")
        out = _git(repo, "ls-remote", "--heads", WRITE_REMOTE, f"refs/heads/task/{wid}/*")
        by_round: dict = {}
        print(f"프로젝트 {paths.name} · work {wid} · 기준 {tracking}")
        for ln in out.splitlines():
            parts = ln.split()
            if len(parts) != 2:
                continue
            ref, tip = parts[1][len("refs/heads/"):], parts[0]
            cand = _is_candidate(ref)
            m = re.match(rf"^task/{re.escape(wid)}/r(\d+)/[^/]+$", ref)
            if not m:
                print(f"    [보존{'·클라우드 후보' if cand else ''}] {ref} @ {tip} — 서브 브랜치가 아니다"
                      + (" (라운드 없는 후보 — 이 명령의 대상 밖 · #840)" if cand else ""))
                continue
            rc = 0
            try:
                _git(repo, "merge-base", "--is-ancestor", tip, tracking)
            except Exception:                              # noqa: BLE001
                rc = 1
            print(f"    {subbranch_label(ref, rc == 0)} {ref} @ {tip}"
                  + ("" if rc == 0 else f" — {tracking} 에서 도달 불가")
                  + ("" if not cand else (" — 채택돼 작업 브랜치에 들어간 후보" if rc == 0 else
                                          " — 미채택 후보, 지우지 않는다(보고만 · #840)")))
            if rc == 0:
                by_round.setdefault(int(m.group(1)), []).append(ref)
        if "--apply" not in argv:
            print("\n  [중요] 드라이런 — 아무것도 지우지 않았다. 실행하려면 `--apply`.")
            return 0
        bad = 0
        for rnd, refs in sorted(by_round.items()):
            deleted, kept = prune_merged_subbranches(repo, work_id=wid, round_no=rnd, target=target,
                                                     merged=refs, remote=WRITE_REMOTE)
            for r, t in deleted:
                print(f"    삭제 {r} @ {t}")
            for r, w in kept:
                print(f"    [중요] 보존 {r} — {w}")
                bad += 1
        return 1 if bad else 0
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
    if cmd == "machines":
        print("── 기계 단위 (#333 ⓐ · 읽기 전용 · 모든 프로젝트 · 마스터 포함) ──")
        for scan in survey_machines():
            print(render_scan(scan))
        print("\n  [중요] 아무것도 지우지 않았다 — 읽기 전용 열거다.")
        return 0
    if cmd not in ("plan", "apply"):
        print("  plan | apply | machines | remote [--apply] | terminal [프로젝트] [--apply]"
              " | merged-subs [프로젝트] <work_id> [--apply]")
        return 2
    paths = resolve(argv[1] if len(argv) > 1 else "")
    base = (ProjectConfig.load(paths.config).branch or "main").strip()
    facts = [bundle.probe(h, u, p, d, r, dp) for h, u, p, d, r, dp in bundle.workshops(paths.name)]
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
        # `#333` ⓐ — 기계 단위(마스터 포함 · 모든 프로젝트) worktree·추적 ref. 읽기만 한다.
        print("\n── 기계 단위 (#333 ⓐ · 읽기 전용 · 모든 프로젝트 · 마스터 포함) ──")
        for scan in survey_machines():
            print(render_scan(scan))
        print("\n  [중요] 아무것도 지우지 않았다. 실행하려면 `apply`(기계 단위 항목은 apply 가 다루지 않는다).")
    return rc


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
