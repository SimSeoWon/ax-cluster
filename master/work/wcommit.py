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
# [중요] 사이클이 끝나면 **`main` 으로 돌아온다** (원전 § 워커 사이클 · 사용자 결정 2026-08-09).
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
    notes: list = field(default_factory=list)       # [주의] 로 시작하는 것은 비치명 경고다
    stage: str = ""                                 # 어디까지 갔나 (실패 지점)
    reason: str = ""
    # 🔴 **할 일이 없던 조각** (원전 `worker/validator.py:547` = `ok_no_op`).
    #    골조에 `[PSEUDO]` 가 하나도 없으면 그것은 **완성된 파일**이고(`skeleton.py` 머리말),
    #    워커가 그대로 돌려준 것이 정답이다. 그때 커밋은 생기지 않는다 — **실패가 아니다.**
    no_op: bool = False

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
    return (f'{cd} && git fetch --all --quiet && git reset --hard --quiet HEAD && '
            f'git clean -fd && git checkout -q -B "{branch}" "{base_commit}" && '
            f'git rev-parse HEAD')


def return_home_command(facts, home: str = HOME_BRANCH) -> str:
    """사이클 종료 자세 — `main` 으로 복귀한다.

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
    return (f'{cd} && git reset --hard -q HEAD && git clean -fdq && '
            f'git checkout -q "{home}" && git rev-parse --abbrev-ref HEAD')


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

    # ⑥ [중요] **복귀는 `finally` 다** — 실측 2026-09-03: 성공 경로에만 붙였더니 층1 에서
    #    막힌 조각이 브랜치에 체크아웃된 채 남았고, 테스트가 그것을 잡았다. **잔재가 남는
    #    것은 성공/실패와 무관하다** — 체크아웃을 옮긴 쪽이 되돌릴 책임을 진다.
    try:
        return _cycle(facts, task_id, c, base, llm, do_ssh, do_read, baseline)
    finally:
        _return_home(facts, do_ssh, c)


def _cycle(facts, task_id: str, c: "Committed", base: str, llm, do_ssh, do_read,
           baseline) -> "Committed":
    """체크아웃이 선 뒤의 사이클 — ② 본문 → ③ 되읽기 → ④ 층1 → ⑤ 커밋·push."""
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


def _return_home(facts, do_ssh, c: Committed) -> None:
    """`main` 복귀. [주의] **실패를 치명으로 보지 않는다** — 커밋은 이미 원격에 있다."""
    try:
        rc, out = do_ssh(facts, return_home_command(facts), GIT_TIMEOUT)
        if rc != 0 or HOME_BRANCH not in (out or ""):
            c.notes.append(f"[주의] `{HOME_BRANCH}` 복귀 실패 (rc={rc}) — 조각 브랜치에 "
                           f"체크아웃된 채 남으면 정리기가 그것을 못 지운다: "
                           f"{(out or '').strip()[-160:]}")
    except Exception as e:                                   # noqa: BLE001
        c.notes.append(f"[주의] `{HOME_BRANCH}` 복귀를 시도하지 못했다 — {type(e).__name__}: {e}")
