"""통합자 — [중요] **유일한 쓰기 주체** (중 1.4 · §8.4 · §4.5).

    워커        durable 을 읽고 추론만 → `response.txt`        (`infer.py`)
    마스터      응답을 되읽어 판정 → 스풀 (적용 순서대로)
    [중요] 통합자   **적용 → 층1 → UE5 빌드 판정 → 통과분만 커밋·push**   ← 이 파일

## [중요] 빌드해 본 주체가 커밋한다 — 규율이 아니라 구조

옛 구조는 태스크를 워커의 자기 신고(`RESULT: DONE`)로 판정하고 *"컴파일되나"* 를 아무도 묻지
않았다. 원전이 정확히 그 구조에서 사고를 냈다 — 빌드를 등재 *뒤*에 두었더니 **깨진 골조가
`origin` 에 박히고 워커 전원이 그 위에서 작업**했다. 커밋 권한을 빌드한 주체에게 주면 **깨진
것이 원격에 못 박힌다.**

## [중요] 조각마다 빌드하고 조각마다 커밋한다

§4.5 는 비용 때문에 *"전부 적용 후 빌드 한 번"* 을 적어 뒀지만, 그러면 **실패 시 어느 조각이
원인인지 모른다**(그 절도 그 문제를 인정하고 있다). 리포트 12 가 그 전제를 뒤집었다 —
**증분 빌드 실측 35~65초**다. 조각당 한 번 세워도 4조각이 4분이다.

    조각마다   층1(무료·결정적) → 적용 → 빌드 → [중요] 통과하면 커밋, 실패하면 **되돌린다**
    끝에       push (ff-only). [주의] work 단위 통합 빌드는 소 2.3.5 의 몫이다

얻는 것이 이 마일스톤이 말하는 **증분**이다: 조각 3이 깨져도 **1·2 는 이미 durable 에 있고 그
상태는 컴파일된다.** 그리고 실패가 **정확히 어느 조각인지** 남는다.

[중요] **첫 실패에서 멈춘다** (기본값). 적용 순서는 include 의존 순서이므로, 앞 조각이 실패하면
뒤 조각은 **없는 선언 위에서 추론된 것**이다 — 계속 세우면 빌드 시간만 버린다. 남은 것은
*"적용하지 않았다 — 선행 실패"* 로 남긴다.

## [중요] 실패는 커밋하지 않는다 (소 1.4.4) — [주의] **이 토폴로지에서만** (2026-08-14 주석)

> [중요] **전역 규칙으로 읽지 말 것.** 아래 근거는 *"쓰는 주체가 하나라 실패 attempt 를 남길
> 브랜치가 없다"* 인데, **그 전제가 소 1.2.2(`#123`)에서 사라졌다** — attempt 계층이 돌아왔고
> 마스터가 `attempt/<task>/<workshop>/<ts>` 에 **성공·실패 무관** push 한다(`work/attempt.py`,
> 실 Gitea 실증 2026-08-14). 그 경로에서는 `docs/8-git-authority.md` §8.4 *"실패도 커밋한다"*
> 가 맞다 — ephemeral 이니 durable 은 더러워지지 않는다.
> [주의] **두 파일은 나란히 선다**(§8.4 규약: 측정으로 뒤집힐 여지가 있는 동안 되돌릴 수 있게).
> 이 파일의 규칙은 **이 파일의 토폴로지**(통합자 단일 writer)에서 참이다.

옛 규칙은 *"실패도 attempt 로 push 한다 — 증거를 버리지 않는다"* 였다. 쓰는 주체가 하나가 되면
실패 attempt 를 남길 브랜치가 없다. 대신:

    실패한 조각의 파일을 **되돌린다**(`git checkout -- <파일>`) → 커밋하지 않는다
    사유를 `[FEEDBACK]` 블록으로 만들어 큐에 돌려준다 → 다음 라운드가 그것을 읽는다
    [중요] 증거는 **스풀**에 이미 있다 — 응답 원문·빌드 로그 꼬리가 남는다

[주의] **`[FEEDBACK]` 은 지워질 수 있어야 한다.** 원전에 *"모든 주석을 보존하라"* 는 지시가
`[FEEDBACK]` 삭제를 막아 **검증이 무한 실패**한 잠복 버그가 있었다(리포트 11 §30). 그래서
이 블록은 **소스 파일에 넣지 않고** 큐/피드백 채널로만 나른다.
"""
from __future__ import annotations

import posixpath
from dataclasses import dataclass, field

from ..client import bundle
from . import layer1 as layer1_mod
from . import runner, skeleton_gate
from .infer import Response, spool_dir, unspool

WORKTREE_PREFIX = "ax-wt"
GIT_TIMEOUT = 300
FEEDBACK_BEGIN = "[FEEDBACK]"


class IntegrateError(RuntimeError):
    """통합을 시작할 수 없다. [중요] **모르는 채로 적용하지 않는다.**"""


# ── 소 1.4.1 워크트리 격리 — 추론 트리 ≠ 적용 트리 ──────────────────────────────
#
# [중요] 왜 갈라야 하나: `.2` 는 **워커이면서 통합자**다. 적용 중에 추론이 같은 트리를 읽으면
#    반쯤 적용된 소스를 근거로 추론한다. 그리고 `Source/` 더티 검사가 항상 빨간불이 된다.
#
# [완료] **비용 선결은 리포트 12 §6.2 가 풀었다** (문서의 "콜드 빌드 수십 분" 예상은 틀렸다):
#      worktree 체크아웃 10초 · 2,229 파일 · 1.08GB     (원본은 6,629 파일 · 9.91GB)
#      [중요] 콜드 빌드 144초 · 이후 증분 35~65초
#    엔진은 설치본을 그대로 쓰고 프로젝트 모듈만 짓기 때문이다. 그래서 **격리가 기본**이다.
#    [주의] 이것은 **코드 빌드만**이다 — 층3 `RunTests` 의 DDC(셰이더)는 여전히 미측정이다.

def worktree_path(facts, work_id: str) -> str:
    """체크아웃의 **형제** 디렉토리. [중요] 체크아웃 *안*에 두면 git 이 자기 트리를 삼킨다."""
    if not (work_id or "").strip():
        raise IntegrateError("work_id 가 비었다 — 격리 트리 이름을 만들 수 없다")
    safe = "".join(c if (c.isalnum() or c in "-_") else "-" for c in work_id)
    p = str(facts.path).rstrip("\\/")
    if getattr(facts, "windows", True):
        parent = p.rsplit("\\", 1)[0] if "\\" in p else p
        return f"{parent}\\{WORKTREE_PREFIX}-{safe}"
    parent = posixpath.dirname(p) or p
    return posixpath.join(parent, f"{WORKTREE_PREFIX}-{safe}")


def _git(facts, args: str, *, cwd: str = "", runner_=None) -> tuple:
    """워커에서 git 한 번. `(rc, stdout)`. **예외를 던지지 않는다** — 실패도 사실이다."""
    where = cwd or facts.path
    cmd = f'git -C "{where}" {args}'
    if runner_ is not None:
        return runner_(facts, cmd)
    return bundle._ssh(facts.host, facts.user, cmd, timeout=GIT_TIMEOUT)


@dataclass
class Worktree:
    path: str = ""
    created: bool = False          # 이번에 만들었나 (재사용이면 False)
    head: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.path and self.head and not self.error)


def ensure_worktree(facts, work_id: str, *, at_commit: str, runner_=None) -> Worktree:
    """격리 트리를 `at_commit` 에 세운다. 있으면 **그 커밋으로 맞춘다.**

    [중요] **detached HEAD 로 둔다.** 브랜치를 만들면 이름이 충돌하고, 정리기가 *"체크아웃된
    브랜치는 못 지운다"* 는 규칙에 걸려 durable 브랜치를 영영 못 지운다. push 는
    `HEAD:refs/heads/<durable>` 로 하므로 로컬 브랜치가 필요 없다.

    [중요] **`at_commit` 을 모르면 만들지 않는다.** 어느 시점에 적용하는지 모르면 적용해선 안 된다.
    """
    wt = Worktree(path=worktree_path(facts, work_id))
    if not (at_commit or "").strip():
        wt.error = "기준 커밋이 비었다 — 어느 시점에 적용할지 모르면 적용하지 않는다"
        return wt

    rc, out = _git(facts, "fetch --prune origin", runner_=runner_)
    if rc != 0:
        # [중요] fetch 를 못 했으면 그 커밋이 있는지조차 모른다
        wt.error = f"fetch 실패 — {out.strip()[:120]}"
        return wt

    rc, out = _git(facts, "worktree list --porcelain", runner_=runner_)
    have = wt.path.replace("\\", "/").lower() in (out or "").replace("\\", "/").lower()

    if not have:
        rc, out = _git(facts, f'worktree add --detach --force "{wt.path}" {at_commit}',
                       runner_=runner_)
        if rc != 0:
            wt.error = f"worktree 생성 실패 — {out.strip()[:160]}"
            return wt
        wt.created = True
    else:
        # [중요] 재사용할 때는 **깨끗한지 먼저 본다.** 앞 실행이 남긴 적용물 위에 또 쓰면
        #    무엇이 이번 변경인지 알 수 없다.
        rc, dirty = _git(facts, "status --porcelain", cwd=wt.path, runner_=runner_)
        if rc != 0:
            wt.error = f"기존 트리 상태를 못 읽었다 — {dirty.strip()[:120]}"
            return wt
        if (dirty or "").strip():
            # [주의] 되돌린다. [중요] 이 트리는 **파이프라인 소유**다 — 사람의 트리가 아니므로
            #    되돌려도 잃을 것이 없다(사람 트리라면 절대 하지 않는다).
            rc, out = _git(facts, "checkout -- .", cwd=wt.path, runner_=runner_)
            if rc != 0:
                wt.error = f"기존 트리를 되돌리지 못했다 — {out.strip()[:120]}"
                return wt
        rc, out = _git(facts, f"checkout --detach --force {at_commit}", cwd=wt.path,
                       runner_=runner_)
        if rc != 0:
            wt.error = f"기준 커밋으로 맞추지 못했다 — {out.strip()[:160]}"
            return wt

    rc, out = _git(facts, "rev-parse HEAD", cwd=wt.path, runner_=runner_)
    if rc != 0 or not (out or "").strip():
        wt.error = "HEAD 를 못 읽었다"
        return wt
    wt.head = out.strip().split()[0]
    # [중요] 정말 그 커밋인지 대조한다 — "맞췄다" 는 보고를 믿지 않는다
    if not wt.head.startswith(at_commit) and not at_commit.startswith(wt.head[:len(at_commit)]):
        wt.error = f"HEAD 가 기준과 다르다 — 기대 {at_commit[:12]} 실측 {wt.head[:12]}"
    return wt


# ── 소 1.4.2 층1 — [중요] 적용 **직전**에 (구현은 `layer1.py`) ────────────────────────
#
# [중요] 층1 은 **두 곳에** 박혀 있다(중 2.1): 응답 수락(`infer.judge`)과 여기. 검사가 무료라서
#    두 번 돌려도 잃는 것이 없고, 어느 한쪽이 우회되는 경로(스풀 손질·재사용)가 실재한다.
#    구현과 근거는 `layer1.py` 의 머리말에 있다.

Layer1 = layer1_mod.Layer1


def layer1(files: dict, *, baseline=None):
    """`layer1.check` 로 위임한다. (호환 이름 — 이 모듈의 호출자가 쓰던 형태다)"""
    return layer1_mod.check(files, baseline=baseline)


def local_baseline(paths, base_commit: str):
    """마스터의 색인 클론을 기준 원본으로 쓴다 — **왕복 없이** 동결을 대조한다.

    [중요] 근거: §8.4 가 *"durable 을 만드는 기준 커밋 == 매니페스트의 twin_commit ==
    `index.last_indexed_commit`"* 로 정의해 뒀다. 세 값이 같으므로 마스터의 로컬 소스가 곧
    적용 전 상태다. **정말 같은지 확인하고**, 다르면 `None` 을 돌려 호출자가 원격에서 읽게 한다
    — 낡은 사본으로 동결을 판정하면 조용히 틀린다.
    """
    try:
        import yaml
        cfg = yaml.safe_load(paths.config.read_text(encoding="utf-8")) or {}
        indexed = str(((cfg.get("index") or {}).get("last_indexed_commit")) or "")
    except Exception:                                    # noqa: BLE001
        return None
    if not indexed or not base_commit:
        return None
    if not (indexed.startswith(base_commit) or base_commit.startswith(indexed)):
        return None

    root = paths.repo

    def read(path: str):
        p = root / str(path).replace("\\", "/")
        if not p.is_file():
            return None                          # 신규 파일 — 동결할 원본이 없다
        from ..source_text import decode          # [중요] 소스 44%가 CP949 다
        d = decode(p.read_bytes())
        # [중요] `decode` 는 **`Decoded` 를 돌려준다 — 문자열이 아니다.** 실측 2026-08-12: 그대로
        #    넘겼더니 `frozen_decls` 가 터졌다. 단위 테스트가 `baseline` 을 주입해서 이 실물
        #    경로를 안 밟았고, **실전에서 나왔다.**
        if d.degraded:
            # [주의] 문자가 유실된 사본으로 동결을 판정하면 **없는 위반을 만든다**(치환된 글자가
            #    선언 키를 바꾼다). 정상 작업을 막는 게이트가 통과시키는 게이트보다 나쁘다 —
            #    `None` 을 돌려 그 파일은 **동결 미검사**로 기록되게 한다.
            return None
        return d.text
    return read


def classes_in(paths, files) -> list:
    """대상 파일들이 선언하는 클래스 이름. **그래프에서 읽는다 (LLM 0).**

    층2 에 실을 선언부를 모으려면 클래스 이름이 필요한데, 스풀에는 파일만 있다(그것이
    파견 단위이므로 맞다). 그래프의 `classes` 표가 `name → file` 이라 **역조회**하면 된다.
    """
    # [중요] **여기서 죽지 않는다.** grounding 이 없는 것은 층2 의 검출력이 낮아지는 것이지
    #    통합을 멈출 이유가 아니다 — 그리고 그 사실은 `l2_grounded=False` 로 보고된다.
    #    (실측 2026-08-12: 그래프 없는 경로에서 `AttributeError` 로 통합자가 통째로 죽었다)
    try:
        from ..graph import db as gdb
        if not gdb.exists(paths):
            return []
        want = {str(f).replace("\\", "/") for f in (files or [])}
        conn = gdb.connect(paths)
        try:
            return sorted({r["name"] for r in conn.execute("SELECT name, file FROM classes")
                           if r["file"] and str(r["file"]).replace("\\", "/") in want})
        finally:
            conn.close()
    except Exception:                                    # noqa: BLE001
        return []


def layer2_grounding(paths, files) -> str:
    """층2 프롬프트에 실을 **선언부**. [중요] 이것이 검출력을 갈랐다 (실측 소 2.2.1).

    같은 표본을 후보 5개에 돌렸더니 **넷이 "없는 열거값" 을 놓쳤고**, 선언부를 함께 준
    변형에서는 잡았다. 층2 를 grounding 없이 돌리면 **문법만 보는 검사기**가 된다.

    [주의] 실패하면 빈 문자열이다 — 호출자가 *"grounding 없이 돌렸다"* 를 **말해야** 한다.
    """
    names = classes_in(paths, files)
    if not names:
        return ""
    try:
        from .skeleton import include_decls
        return include_decls(paths, names)
    except Exception:                                    # noqa: BLE001
        return ""


def remote_baseline(facts, tree: str, *, reader=None):
    """격리 트리에서 적용 전 내용을 읽는다. 왕복이 있지만 **근거가 정확하다.**"""
    r = reader or bundle._remote_read

    def read(path: str):
        abs_path = (skeleton_gate._win_join(tree, path)
                    if getattr(facts, "windows", True)
                    else posixpath.join(tree, str(path).replace("\\", "/")))
        try:
            text = r(facts, abs_path)
        except bundle.BundleError:
            return None
        return text or None
    return read


# ── 소 1.4.3 · 1.4.4 적용 → 빌드 → 커밋 / 실패는 커밋하지 않는다 ────────────────

@dataclass
class Applied:
    """조각 하나의 통합 결과."""
    task_id: str = ""
    files: list = field(default_factory=list)
    l1: Layer1 | None = None
    l2 = None                                      # verdict.Verdict (층2) · None = 안 돌렸다
    l2_grounded: bool = False                      # [중요] 선언부를 실었나 (검출력을 가른다)
    build = None                                   # layer3_verify.BuildResult
    commit: str = ""
    reverted: bool = False
    error: str = ""
    skipped: str = ""                              # 아예 시도하지 않은 사유

    @property
    def ok(self) -> bool:
        return bool(self.commit and not self.error)

    @property
    def summary(self) -> str:
        if self.skipped:
            return f"{self.task_id}: ⏭ 적용 안 함 — {self.skipped}"
        if self.ok:
            b = f" · 빌드 {self.build.seconds:.0f}초" if getattr(self.build, "seconds", None) \
                else ""
            return f"{self.task_id}: [완료] 커밋 {self.commit[:8]}{b} · 파일 {len(self.files)}"
        bits = [f"{self.task_id}: [중요]"]
        if self.l1 is not None and not self.l1.ok:
            bits.append(self.l1.summary)
        elif self.l2 is not None and not self.l2.approved:
            bits.append("층2 " + self.l2.summary()
                        + ("" if self.l2_grounded else " [주의](선언부 없이 돌렸다)"))
        elif self.build is not None and not self.build.passed:
            bits.append(self.build.summary())
        if self.error:
            bits.append(self.error)
        if self.reverted:
            bits.append("되돌렸다 (커밋하지 않았다)")
        return " — ".join(bits)


def feedback_block(a: Applied) -> str:
    """다음 라운드가 읽을 `[FEEDBACK]`. [중요] **소스 파일에 넣지 않는다** (§ 머리말)."""
    lines = [f"{FEEDBACK_BEGIN} {a.task_id} — 통합자가 적용했지만 통과하지 못했다",
             ""]
    if a.l1 is not None and not a.l1.ok:
        lines.append("층1 (적용 직전 자기검증) 위반:")
        lines += [f"  - {p}" for p in a.l1.problems]
        lines.append("")
    if a.l2 is not None and not a.l2.approved:
        lines.append("층2 (상용 모델 문법·API 검사) 판정:")
        lines.append(f"  {a.l2.summary()}"
                     + ("" if a.l2_grounded else "  [주의] 선언부 없이 돌렸다"))
        lines += [f"  - {f}" for f in a.l2.findings[:10]]
        lines.append("")
    if a.build is not None and not a.build.passed:
        lines.append("UE5 빌드 판정:")
        lines.append(f"  {a.build.summary()}")
        tail = getattr(a.build, "tail", "") or ""
        if tail:
            lines.append("")
            lines.append("빌드 로그 꼬리 ([중요] 요약하지 않는다 — 원문이 근거다):")
            lines += [f"  {ln}" for ln in tail.strip().split("\n")[-15:]]
        lines.append("")
    if a.error:
        lines += [f"오류: {a.error}", ""]
    lines.append("[중요] 이 조각의 파일은 **되돌렸다 — 커밋하지 않았다.** 같은 durable 브랜치에서 "
                 "다시 시도한다. 맞게 짠 부분을 버리지 말고 **고쳐서 전진**한다.")
    return "\n".join(lines)


def _revert(facts, tree: str, files: list, *, runner_=None) -> bool:
    """실패한 조각의 파일만 되돌린다. [중요] `clean` 도 `reset --hard` 도 쓰지 않는다.

    이 트리는 파이프라인 소유이지만, 그 둘은 **범위를 넘는다** — 다른 조각이 방금 커밋한 것,
    또는 추적되지 않은 산출물까지 지운다. 대상은 **이번 조각의 파일**뿐이다.
    """
    if not files:
        return True
    quoted = " ".join(f'"{f}"' for f in sorted(files))
    rc, _ = _git(facts, f"checkout -- {quoted}", cwd=tree, runner_=runner_)
    if rc == 0:
        return True
    # 신규 파일은 `checkout --` 이 안 먹는다(HEAD 에 없다) → 지운다
    rc2, _ = _git(facts, f"rm -f --quiet -- {quoted}", cwd=tree, runner_=runner_)
    return rc2 == 0


def apply_one(facts, res: Response, *, tree: str, project: str, baseline=None,
              layer2=None, declarations: str = "",
              builder=None, writer=None, runner_=None,
              timeout: int = skeleton_gate.BUILD_TIMEOUT) -> Applied:
    """조각 하나: 층1 → 층2 → 적용 → 빌드 → [중요] 통과하면 커밋, 실패하면 되돌린다.

    `layer2(files, declarations=...) -> Verdict` — 주지 않으면 **층2 를 돌리지 않는다**(그것은
    통과가 아니라 미확인이고, `Applied.l2 is None` 으로 구분된다).
    """
    a = Applied(task_id=res.task_id, files=sorted(res.files))

    # ① 층1 — 무료다. [중요] 비싼 빌드 앞에 싼 검사를 둔다
    a.l1 = layer1(res.files, baseline=baseline)
    if not a.l1.ok:
        a.error = "층1 에서 막혔다 — 적용하지 않았다"
        return a

    # ② 층2 — [중요] **비싼 빌드 앞에 싼 검사를 둔다** (소 2.2.2). 존재 이유가 그것이다:
    #    환각 API 를 컴파일 전에 걸러 142초 빌드의 실패율을 낮춘다(§4.3).
    #    [중요] fail-closed — 판정을 못 받으면 막는다. [주의] 그 차단이 값싼 이유는 스풀이 응답을
    #    들고 있어서다(재시도에 추론을 다시 사지 않는다).
    if layer2 is not None:
        a.l2_grounded = bool((declarations or "").strip())
        a.l2 = layer2([(f, res.files[f]) for f in a.files], declarations=declarations or "")
        if not a.l2.approved:
            a.error = ("층2 에서 막혔다 — 적용하지 않았다"
                       + ("" if a.l2_grounded else
                          " [주의] 선언부 없이 돌렸다 (검출력이 낮은 조건이다)"))
            return a

    # ③ 적용 — `skeleton_gate.place` 가 해시 대조까지 한다
    try:
        skeleton_gate.place(facts, tree, res.files, writer=writer)
    except Exception as e:                                   # noqa: BLE001
        a.error = f"적용 실패: {e}"
        _revert(facts, tree, a.files, runner_=runner_)
        a.reverted = True
        return a

    # ④ 빌드 판정 — [중요] fail-closed. 판정을 못 받으면 막는다
    bb = skeleton_gate._build_bat_from(facts)
    if not bb:
        a.error = "UE5 Build.bat 을 찾지 못했다 — 확인 불가이므로 막는다"
        a.reverted = _revert(facts, tree, a.files, runner_=runner_)
        return a
    up = skeleton_gate._win_join(tree, f"{project}.uproject")
    fn = builder or __import__("master.layer3_verify", fromlist=["x"]).run_build_on_workshop
    a.build = fn(facts.host, facts.user, bb, skeleton_gate.target_name(project), up,
                 timeout=timeout)
    if not getattr(a.build, "passed", False):
        # [중요] 실패는 커밋하지 않는다 (소 1.4.4) — 되돌리고 사유를 남긴다
        a.reverted = _revert(facts, tree, a.files, runner_=runner_)
        if not a.reverted:
            a.error = "[중요] 되돌리지 못했다 — 트리가 더러운 채 남았다. 사람이 확인할 것"
        return a

    # ⑤ 커밋 — **빌드해 본 주체가 커밋한다**
    quoted = " ".join(f'"{f}"' for f in a.files)
    rc, out = _git(facts, f"add -- {quoted}", cwd=tree, runner_=runner_)
    if rc != 0:
        a.error = f"git add 실패 — {out.strip()[:120]}"
        return a
    msg = f"{res.task_id}: 통합자 적용 (빌드 통과)"
    rc, out = _git(facts, f'commit --quiet -m "{msg}"', cwd=tree, runner_=runner_)
    if rc != 0:
        # [주의] 변경이 없으면 git 은 rc≠0 을 낸다 — 그것과 진짜 실패를 가른다
        low = (out or "").lower()
        if "nothing to commit" in low or "no changes added" in low:
            a.error = "커밋할 변경이 없다 — 응답이 기존 파일과 같다"
        else:
            a.error = f"commit 실패 — {out.strip()[:120]}"
        return a
    rc, out = _git(facts, "rev-parse HEAD", cwd=tree, runner_=runner_)
    if rc != 0 or not (out or "").strip():
        a.error = "커밋했지만 HEAD 를 못 읽었다"
        return a
    a.commit = out.strip().split()[0]
    return a


# ── 소 2.3.1·2.3.2·2.3.5 층3 RunTests — [중요] **work 단위로 한 번** ────────────────
#
# 조각별 빌드가 이미 **누적된 트리**를 세우므로(조각 2의 빌드는 base+1+2 를 짓는다) 소 2.3.5 가
# 걱정한 *"모듈 의존·include 누락·private 접근"* 은 **빌드 쪽에서는 이미 잡힌다.** 남은 것은
# `RunTests` 이고, 그것은 에디터를 띄우므로 **끝에 한 번만** 돈다.
#
# [중요] **실측 2026-08-12: 이 프로젝트에 자동화 테스트가 0개다.**
#   `Source/` 전체에 `AUTOMATION_TEST`·`FunctionalTest`·spec 이 하나도 없다(모듈 4·타깃 4).
#   그래서 지금 `RunTests` 는 **판정할 것이 없다** — 돌리면 `parse_automation_log` 가
#   *"성공한 테스트가 0건"* 으로 **차단**한다(라이브러리로서는 맞는 계약이다).
#
# [주의] 그러므로 여기서는 마일스톤이 못박은 대로 **갈라서** 다룬다(소 2.3.5):
#
#     테스트가 **불합격**했다 (`failure is None` · fail>0)   → [중요] **막는다** (실재하는 결함)
#     테스트가 **돌 게 없다/못 돌았다** (`failure` 있음)      → [주의] **fail-open**, 대신 **말한다**
#
# [중요] fail-open 이 위험한 선택인 것은 맞다. 그래서 **기본값을 조용히 두지 않는다** — 결과에
#   *"테스트로 검증하지 않았다"* 가 반드시 실린다. 그리고 §4.3 이 실측한 두 부류
#   (`Cast<IInteractable>` · `IsValid()` 로직 오류)는 **테스트만 잡을 수 있으므로**, 테스트가
#   0개인 동안 그 구멍은 **닫히지 않는다.** 그것은 배선으로 메울 수 있는 문제가 아니다.

def run_tests(facts, *, tree: str, project: str, test_filter: str = "",
              tester=None, timeout: int = 3600) -> tuple:
    """`(Layer3Result|None, 막아야 하나, 사람에게 할 말)`.

    `tester` 를 주입할 수 있는 이유는 테스트다 — 에디터 없이 계약을 검증한다.
    """
    if not getattr(facts, "ue5", ""):
        return None, False, "[주의] 층3 RunTests 미확인 — 이 기계에 UE5 가 없다 (fail-open)"
    fn = tester or __import__("master.layer3_verify",
                             fromlist=["x"]).run_tests_on_workshop
    up = skeleton_gate._win_join(tree, f"{project}.uproject")
    r = fn(facts.host, facts.user, facts.ue5, up, test_filter or project, timeout=timeout)
    if getattr(r, "passed", False):
        return r, False, f"[완료] 층3 RunTests {r.summary()}"
    if getattr(r, "failure", None):
        # [주의] **돌 게 없거나 못 돌았다** — 막지 않는다. 다만 통과라고 적지 않는다.
        return r, False, ("[주의] 층3 RunTests 로 **검증하지 못했다** (fail-open): "
                          f"{r.failure} [중요] 이 프로젝트는 자동화 테스트가 0개다 — "
                          "빌드가 통과해도 런타임 결함은 아무도 안 본다")
    # [중요] 진짜 불합격이다
    names = ", ".join(t.name or t.path for t in r.failures()[:3])
    return r, True, f"[중요] 층3 RunTests 불합격 — {r.summary()}: {names}"


def report_to_redmine(subject: str, body: str, *, api_key: str = "", url: str = "",
                      project_id: int = 1, poster=None) -> str:
    """실패를 레드마인에 등재한다 (소 2.3.3). [중요] **실패해도 파이프라인을 막지 않는다.**

    전임 시스템의 `[빌드 실패] 통합 빌드 게이트 차단` 이슈가 정확히 이 형태다(#13~#20).

    [주의] **API 키는 저장소에도 `~/.config` 에도 없다** — 마스터의 컨테이너 DB 에서 꺼낸다
    (§10.1). 그래서 키가 없으면 **조용히 건너뛰지 않고** 사유를 돌려준다: 이슈 추적이 안 되는
    것과 게이트가 통과한 것은 다르다.
    """
    import json as _json
    import os as _os
    import urllib.request
    key = api_key or _os.environ.get("AX_REDMINE_API_KEY", "")
    base = (url or _os.environ.get("AX_REDMINE_URL", "http://192.168.0.57:8080")).rstrip("/")
    payload = {"issue": {"project_id": project_id, "subject": subject[:250],
                         "description": body[:8000]}}
    # [중요] 키 검사는 **기본 전송 수단**에 대한 것이다. `poster` 를 주입했다면 전송의 책임은
    #    주입자에게 있다 — `writer`·`runner`·`builder` 와 같은 규약이다.
    if poster is None and not key:
        return ("[주의] 레드마인 등재 건너뜀 — API 키가 없다 "
                "(`AX_REDMINE_API_KEY` 또는 컨테이너 DB, §10.1)")
    try:
        if poster is not None:
            return poster(base, payload, key)
        req = urllib.request.Request(f"{base}/issues.json",
                                     data=_json.dumps(payload).encode("utf-8"),
                                     method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("X-Redmine-API-Key", key)
        with urllib.request.urlopen(req, timeout=20) as r:
            got = _json.loads(r.read().decode("utf-8", "replace"))
        return f"레드마인 #{(got.get('issue') or {}).get('id', '?')} 등재"
    except Exception as e:                                   # noqa: BLE001
        return f"[주의] 레드마인 등재 실패 — {type(e).__name__}: {e}"


@dataclass
class Integration:
    work_id: str = ""
    tree: str = ""
    base: str = ""
    applied: list = field(default_factory=list)
    pushed: str = ""
    branch: str = ""
    note: str = ""
    l3 = None                                        # layer3_verify.Layer3Result | None
    l3_note: str = ""                                # [중요] 사람이 읽을 층3 상태 (미확인 포함)
    catalog: int = 0                                 # 실패 카탈로그 총 항목 수 (소 2.3.4)
    reported: list = field(default_factory=list)     # 레드마인 등재 결과 (소 2.3.3)

    @property
    def passed(self) -> list:
        return [a for a in self.applied if a.ok]

    @property
    def failed(self) -> list:
        return [a for a in self.applied if not a.ok and not a.skipped]

    @property
    def ok(self) -> bool:
        return bool(self.passed) and not self.failed

    def summary(self) -> str:
        out = [f"통합 — 커밋 {len(self.passed)} / 조각 {len(self.applied)}"
               + (f" · [중요] 실패 {len(self.failed)}" if self.failed else "")]
        if self.tree:
            out.append(f"  격리 트리 {self.tree} @ {self.base[:8]}")
        for a in self.applied:
            out.append("  " + a.summary)
        if self.l3_note:
            out.append("  " + self.l3_note)
        if self.catalog:
            out.append(f"  실패 카탈로그 {self.catalog}건 — 다음 골조 프롬프트에 실린다")
        for r in self.reported:
            out.append("  " + r)
        if self.pushed:
            out.append(f"  [중요] push [완료] {self.branch} ← {self.pushed[:8]}")
        elif self.passed:
            out.append("  [주의] push 하지 않았다 — durable 이 없거나 거부됐다 (아래 참조)")
        if self.note:
            out.append("  " + self.note)
        return "\n".join(out)


def load_handoff(paths, work_id: str) -> list:
    """스풀에서 **통과분만**, 적용 순서대로. [중요] 실패한 응답은 통합자에게 가지 않는다."""
    d = spool_dir(paths, work_id)
    if not d.is_dir():
        raise IntegrateError(f"스풀이 없다: {d} — 먼저 파견해야 적용할 것이 생긴다")
    import json
    recs = []
    for p in sorted(d.glob("*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        r = unspool(paths, rec.get("task_id", ""), work_id)
        if r is not None and r.ok:
            recs.append((int(rec.get("order") or 0), r))
    return [r for _, r in sorted(recs, key=lambda kv: kv[0])]


def one_base(responses: list) -> str:
    """[중요] **모든 응답이 같은 기준 커밋이어야 한다.** 섞이면 적용하지 않는다.

    조각들은 한 트윈 커밋을 근거로 동시에 추론됐다. 기준이 다른 것이 섞였다면 어떤 것은
    **낡은 소스에서** 나온 것이고, 그것을 적용하면 통합자의 빌드가 남의 실패로 깨진다.
    """
    bases = {(r.base_commit or "") for r in responses}
    if not bases:
        raise IntegrateError("적용할 응답이 없다")
    if len(bases) > 1:
        raise IntegrateError("응답들의 기준 커밋이 섞여 있다 — 적용하지 않는다: "
                             + ", ".join(sorted(b[:8] or "(없음)" for b in bases)))
    base = bases.pop()
    if not base:
        raise IntegrateError("기준 커밋이 비었다 — 어느 시점에 적용할지 모르면 적용하지 않는다")
    return base


AUTO = "auto"        # [중요] 기본은 **돌리는 것**이다. 끄려면 호출자가 명시적으로 None 을 준다


def _default_layer2():
    from .. import layer2_verify as L2

    def call(files, *, declarations=""):
        return L2.verify_files(files, declarations=declarations)
    return call


def run(paths, facts, work_id: str, *, project: str = "", durable: str = "",
        stop_on_fail: bool = True, baseline=None, layer2=AUTO, builder=None, writer=None,
        runner_=None, push: bool = True, api=runner._api, tester=None,
        catalog: bool = True, redmine: bool = True, poster=None,
        timeout: int = skeleton_gate.BUILD_TIMEOUT) -> Integration:
    """work 하나를 통합한다 — [중요] **적용은 순차, 통과분만 커밋.**

    `durable` — durable 브랜치 이름(없으면 push 하지 않고 로컬 커밋까지만 한다).
    """
    responses = load_handoff(paths, work_id)
    base = one_base(responses)
    itg = Integration(work_id=work_id, base=base, branch=durable)
    proj = project or paths.name

    wt = ensure_worktree(facts, work_id, at_commit=base, runner_=runner_)
    itg.tree = wt.path
    if not wt.ok:
        itg.note = f"[중요] 격리 트리를 세우지 못했다 — {wt.error}"
        return itg

    # [중요] 기준 원본: 마스터의 로컬 클론이 같은 커밋이면 그것을 쓰고(왕복 0), 아니면 원격에서
    #    읽는다. 둘 다 안 되면 `baseline=None` 이라 **동결 미검사**로 기록된다(통과가 아니다).
    base_fn = baseline or local_baseline(paths, base) or remote_baseline(facts, wt.path)

    l2_call = _default_layer2() if layer2 == AUTO else layer2
    if l2_call is None:
        # [주의] 미확인을 통과처럼 읽히게 두지 않는다
        itg.note = "[주의] 층2 를 돌리지 않았다 (호출자가 껐다) — 문법·API 검사는 미확인이다"

    stopped = ""
    for r in responses:
        if stopped:
            a = Applied(task_id=r.task_id, files=sorted(r.files),
                        skipped=f"선행 {stopped} 이 실패했다 (적용 순서 = 의존 순서)")
            itg.applied.append(a)
            continue
        a = apply_one(facts, r, tree=wt.path, project=proj, baseline=base_fn,
                      layer2=l2_call, declarations=layer2_grounding(paths, sorted(r.files)),
                      builder=builder, writer=writer, runner_=runner_, timeout=timeout)
        itg.applied.append(a)
        if not a.ok:
            _submit_fail(r, a, api=api)
            if catalog:
                # [중요] 되먹임 (소 2.3.4) — **결정적 판정 원문에서만** 뽑는다
                try:
                    from . import failures as F
                    itg.catalog = F.add(paths, F.from_applied(a))
                except Exception as e:                   # noqa: BLE001
                    itg.note = (itg.note + " · " if itg.note else "") + \
                        f"[주의] 실패 카탈로그 적립 실패: {e}"
            if redmine:
                # [중요] 이슈 추적이 안 되는 것과 게이트가 통과한 것은 다르다 — 사유를 남긴다
                itg.reported.append(report_to_redmine(
                    f"[통합 실패] {a.task_id} — work {work_id}",
                    feedback_block(a), poster=poster))
            if stop_on_fail:
                stopped = a.task_id

    if not itg.passed:
        itg.note = "[중요] 커밋된 것이 없다 — push 할 것도 없다"
        return itg

    # [중요] 층3 RunTests — **work 단위로 한 번**, push 앞에 (소 2.3.5). 에디터를 띄우므로 비싸다.
    itg.l3, block, itg.l3_note = run_tests(facts, tree=wt.path, project=proj, tester=tester)
    if block:
        # [중요] 테스트가 실제로 불합격했다 — push 하지 않는다. 커밋은 격리 트리에 남는다.
        if catalog:
            try:
                from . import failures as F
                itg.catalog = F.add(paths, [F.Failure(
                    key=f"층3 RunTests 불합격: {itg.l3.summary()}"[:200], layer="층3")])
            except Exception:                            # noqa: BLE001
                pass
        if redmine:
            itg.reported.append(report_to_redmine(
                f"[층3 실패] work {work_id} — RunTests 불합격",
                itg.l3_note + "\n\n" + (getattr(itg.l3, "raw_tail", "") or ""),
                poster=poster))
        itg.note = ("[중요] 층3 불합격으로 push 하지 않았다 — 커밋은 격리 트리에 남아 있다"
                    + (f" ({itg.note})" if itg.note else ""))
        return itg

    if not durable:
        # [주의] 없는 것을 있는 척하지 않는다
        itg.note = ("[주의] durable 브랜치를 받지 못해 **로컬 커밋까지만** 했다. "
                    "요청자(`.33`)가 `task/<id>` 를 만들어야 push 할 곳이 생긴다(§8.4)")
        return itg
    if push:
        # [중요] ff-only. `--force` 는 쓰지 않는다 — 남의 커밋을 지운다
        rc, out = _git(facts, f"push origin HEAD:refs/heads/{durable}",
                       cwd=wt.path, runner_=runner_)
        if rc != 0:
            itg.note = (f"[중요] push 거부됨 — {out.strip()[:160]}. 커밋은 격리 트리에 남아 있다 "
                        f"(잃지 않았다). ff 가 안 되면 사람이 판단한다 — **force 하지 않는다**")
            return itg
        itg.pushed = itg.passed[-1].commit
        for a, r in zip(itg.applied, responses):
            if a.ok:
                _submit_ok(r, a, durable, api=api, l3_note=itg.l3_note)
    _lay_signals(paths, itg, api=api)
    return itg


def _lay_signals(paths, itg: Integration, *, api=runner._api) -> None:
    """생산자② (#206) — 게이트 **통과분**의 작업 과정을 신호로 적재한다.

    원전에서 code-writer 가 작업 종료 직전에 남기던 자리의 파이프라인 대응물. intent 는
    큐의 task 제목(사람이 쓴 요청)이고, 없으면 task_id 로라도 남긴다 — 신호 유실이
    제목 조회 실패보다 비싸다. [중요] 불합격은 여기 안 온다 — 실패 카탈로그(소 2.3.4)의
    소관이다. 적재 실패는 통합을 막지 않되 note 로 말한다 (원전도 로그만 남긴다).
    """
    from ..context_synth import signals as SG
    for a in itg.passed:
        intent = a.task_id
        try:
            t = api("GET", f"/api/v1/tasks/{a.task_id}") or {}
            # 실측 스키마 — task 레코드에 title 은 없다. 사람이 읽을 수 있는 순서로 폴백:
            # target_file(무엇을 만들었나) → task_id (신호 유실이 제일 비싸다)
            intent = (t.get("title") or t.get("target_file") or "").strip() or a.task_id
        except Exception:                                    # noqa: BLE001
            pass
        try:
            SG.append_signal(paths, SG.make_record(
                intent=intent,
                files_modified=[{"path": p, "summary": ""} for p in a.files],
                work_id=itg.work_id, source="pipeline"))
        except Exception as e:                               # noqa: BLE001
            itg.note = (itg.note + " · " if itg.note else "") + \
                f"[주의] 신호 적재 실패({a.task_id}): {e}"


def _submit_ok(r: Response, a: Applied, durable: str, *, api=runner._api,
               l3_note: str = "") -> None:
    """[중요] **여기가 큐에 제출하는 유일한 자리다** (소 1.4.3) — 빌드를 통과한 커밋이 근거다."""
    try:
        api("POST", f"/api/v1/tasks/{r.task_id}/submit", {
            "branch": durable, "head_commit": a.commit,
            "self_check": {"layer1": a.l1.summary if a.l1 else "",
                           "layer2": (a.l2.summary() if a.l2 else "미확인"),
                           "layer2_grounded": a.l2_grounded,
                           "build": a.build.summary() if a.build else "",
                           "layer3": l3_note or "미확인",
                           "by": "integrator"},
            "epoch": r.epoch,
        })
    except Exception:                                    # noqa: BLE001 — 통합을 되돌리지 않는다
        pass


def _submit_fail(r: Response, a: Applied, *, api=runner._api) -> None:
    try:
        api("POST", f"/api/v1/tasks/{r.task_id}/submit-fail",
            {"reason": "통합 실패", "detail": feedback_block(a)[-2000:]})
    except Exception:                                    # noqa: BLE001
        pass


# ── CLI ──────────────────────────────────────────────────────────────────────────
#
#   python -m master.work.integrate plan <프로젝트> <work_id>   무엇을 어떤 순서로 적용하나
#   python -m master.work.integrate run  <프로젝트> <work_id> [durable]
#
# [중요] `plan` 은 아무것도 쓰지 않는다. 남의 기계에 쓰는 작업이라 먼저 본다(`client` 와 같은 규약).

def main(argv) -> int:
    from ..context_search.paths import resolve
    cmd = (argv[0] if argv else "").strip()
    if cmd not in ("plan", "run") or len(argv) < 3:
        print("  plan <프로젝트> <work_id> | run <프로젝트> <work_id> [durable]")
        return 2
    paths = resolve(argv[1])
    work_id = argv[2]
    try:
        responses = load_handoff(paths, work_id)
        base = one_base(responses)
    except IntegrateError as e:
        print(f"[중요] {e}")
        return 1

    facts = [bundle.probe(h, u, p, d, r) for h, u, p, d, r in bundle.workshops(paths.name)]
    # [중요] 통합자는 **UE5 가 있는 기계**다. 없으면 빌드 판정을 못 하므로 통합자가 아니다.
    ue = [f for f in facts if f.role == "worker" and f.checkout_ok and f.ue5]
    if cmd == "plan":
        print(f"work {work_id} · 기준 {base[:12]} · 조각 {len(responses)}")
        for i, r in enumerate(responses, 1):
            print(f"  {i}. {r.task_id} — {', '.join(sorted(r.files))}")
        print(f"통합자 후보: {', '.join(f.host for f in ue) or '[중요] UE5 가 있는 워커가 없다'}")
        if ue:
            print(f"격리 트리: {worktree_path(ue[0], work_id)}")
        return 0
    if not ue:
        print("[중요] UE5 가 있는 워커가 없다 — 빌드 판정을 못 하므로 통합하지 않는다")
        return 1
    itg = run(paths, ue[0], work_id, durable=(argv[3] if len(argv) > 3 else ""))
    print(itg.summary())
    return 0 if itg.ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
