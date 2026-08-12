"""통합자 — 🔴 **유일한 쓰기 주체** (중 1.4 · §8.4 · §4.5).

    워커        durable 을 읽고 추론만 → `response.txt`        (`infer.py`)
    마스터      응답을 되읽어 판정 → 스풀 (적용 순서대로)
    🔴 통합자   **적용 → 층1 → UE5 빌드 판정 → 통과분만 커밋·push**   ← 이 파일

## 🔴 빌드해 본 주체가 커밋한다 — 규율이 아니라 구조

옛 구조는 태스크를 워커의 자기 신고(`RESULT: DONE`)로 판정하고 *"컴파일되나"* 를 아무도 묻지
않았다. 원전이 정확히 그 구조에서 사고를 냈다 — 빌드를 등재 *뒤*에 두었더니 **깨진 골조가
`origin` 에 박히고 워커 전원이 그 위에서 작업**했다. 커밋 권한을 빌드한 주체에게 주면 **깨진
것이 원격에 못 박힌다.**

## 🔴 조각마다 빌드하고 조각마다 커밋한다

§4.5 는 비용 때문에 *"전부 적용 후 빌드 한 번"* 을 적어 뒀지만, 그러면 **실패 시 어느 조각이
원인인지 모른다**(그 절도 그 문제를 인정하고 있다). 리포트 12 가 그 전제를 뒤집었다 —
**증분 빌드 실측 35~65초**다. 조각당 한 번 세워도 4조각이 4분이다.

    조각마다   층1(무료·결정적) → 적용 → 빌드 → 🔴 통과하면 커밋, 실패하면 **되돌린다**
    끝에       push (ff-only). ⚠️ work 단위 통합 빌드는 소 2.3.5 의 몫이다

얻는 것이 이 마일스톤이 말하는 **증분**이다: 조각 3이 깨져도 **1·2 는 이미 durable 에 있고 그
상태는 컴파일된다.** 그리고 실패가 **정확히 어느 조각인지** 남는다.

🔴 **첫 실패에서 멈춘다** (기본값). 적용 순서는 include 의존 순서이므로, 앞 조각이 실패하면
뒤 조각은 **없는 선언 위에서 추론된 것**이다 — 계속 세우면 빌드 시간만 버린다. 남은 것은
*"적용하지 않았다 — 선행 실패"* 로 남긴다.

## 🔴 실패는 커밋하지 않는다 (소 1.4.4)

옛 규칙은 *"실패도 attempt 로 push 한다 — 증거를 버리지 않는다"* 였다. 쓰는 주체가 하나가 되면
실패 attempt 를 남길 브랜치가 없다. 대신:

    실패한 조각의 파일을 **되돌린다**(`git checkout -- <파일>`) → 커밋하지 않는다
    사유를 `[FEEDBACK]` 블록으로 만들어 큐에 돌려준다 → 다음 라운드가 그것을 읽는다
    🔴 증거는 **스풀**에 이미 있다 — 응답 원문·빌드 로그 꼬리가 남는다

⚠️ **`[FEEDBACK]` 은 지워질 수 있어야 한다.** 원전에 *"모든 주석을 보존하라"* 는 지시가
`[FEEDBACK]` 삭제를 막아 **검증이 무한 실패**한 잠복 버그가 있었다(리포트 11 §30). 그래서
이 블록은 **소스 파일에 넣지 않고** 큐/피드백 채널로만 나른다.
"""
from __future__ import annotations

import posixpath
from dataclasses import dataclass, field

from ..client import bundle
from . import runner, skeleton, skeleton_gate
from .infer import Response, spool_dir, unspool

WORKTREE_PREFIX = "ax-wt"
GIT_TIMEOUT = 300
FEEDBACK_BEGIN = "[FEEDBACK]"


class IntegrateError(RuntimeError):
    """통합을 시작할 수 없다. 🔴 **모르는 채로 적용하지 않는다.**"""


# ── 소 1.4.1 워크트리 격리 — 추론 트리 ≠ 적용 트리 ──────────────────────────────
#
# 🔴 왜 갈라야 하나: `.2` 는 **워커이면서 통합자**다. 적용 중에 추론이 같은 트리를 읽으면
#    반쯤 적용된 소스를 근거로 추론한다. 그리고 `Source/` 더티 검사가 항상 빨간불이 된다.
#
# ✅ **비용 선결은 리포트 12 §6.2 가 풀었다** (문서의 "콜드 빌드 수십 분" 예상은 틀렸다):
#      worktree 체크아웃 10초 · 2,229 파일 · 1.08GB     (원본은 6,629 파일 · 9.91GB)
#      🔴 콜드 빌드 144초 · 이후 증분 35~65초
#    엔진은 설치본을 그대로 쓰고 프로젝트 모듈만 짓기 때문이다. 그래서 **격리가 기본**이다.
#    ⚠️ 이것은 **코드 빌드만**이다 — 층3 `RunTests` 의 DDC(셰이더)는 여전히 미측정이다.

def worktree_path(facts, work_id: str) -> str:
    """체크아웃의 **형제** 디렉토리. 🔴 체크아웃 *안*에 두면 git 이 자기 트리를 삼킨다."""
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

    🔴 **detached HEAD 로 둔다.** 브랜치를 만들면 이름이 충돌하고, 정리기가 *"체크아웃된
    브랜치는 못 지운다"* 는 규칙에 걸려 durable 브랜치를 영영 못 지운다. push 는
    `HEAD:refs/heads/<durable>` 로 하므로 로컬 브랜치가 필요 없다.

    🔴 **`at_commit` 을 모르면 만들지 않는다.** 어느 시점에 적용하는지 모르면 적용해선 안 된다.
    """
    wt = Worktree(path=worktree_path(facts, work_id))
    if not (at_commit or "").strip():
        wt.error = "기준 커밋이 비었다 — 어느 시점에 적용할지 모르면 적용하지 않는다"
        return wt

    rc, out = _git(facts, "fetch --prune origin", runner_=runner_)
    if rc != 0:
        # 🔴 fetch 를 못 했으면 그 커밋이 있는지조차 모른다
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
        # 🔴 재사용할 때는 **깨끗한지 먼저 본다.** 앞 실행이 남긴 적용물 위에 또 쓰면
        #    무엇이 이번 변경인지 알 수 없다.
        rc, dirty = _git(facts, "status --porcelain", cwd=wt.path, runner_=runner_)
        if rc != 0:
            wt.error = f"기존 트리 상태를 못 읽었다 — {dirty.strip()[:120]}"
            return wt
        if (dirty or "").strip():
            # ⚠️ 되돌린다. 🔴 이 트리는 **파이프라인 소유**다 — 사람의 트리가 아니므로
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
    # 🔴 정말 그 커밋인지 대조한다 — "맞췄다" 는 보고를 믿지 않는다
    if not wt.head.startswith(at_commit) and not at_commit.startswith(wt.head[:len(at_commit)]):
        wt.error = f"HEAD 가 기준과 다르다 — 기대 {at_commit[:12]} 실측 {wt.head[:12]}"
    return wt


# ── 소 1.4.2 층1 — 🔴 적용 **직전**에, 무료·결정적으로 ──────────────────────────
#
# 🔴 여기서 쓰는 것은 전부 중 1.1 이 만든 **결정적 함수**다(LLM 0):
#     `skeleton.frozen_decls` · `skeleton.violation` · `skeleton.pseudo_count`
#   ⚠️ **중 2.1 이 닫혔다는 뜻은 아니다** — 그쪽은 *제출 경로에* 층1 을 fail-closed 로 박는
#      일이고(소 2.1.3), 이건 **적용 경계**에서 같은 검사를 부르는 것이다. 사슬이
#      `1.1 → 2.1 → 1.4.2` 인 이유가 이 재사용이다.

@dataclass
class Layer1:
    """적용 직전 자기검증. 🔴 `ok` 가 아니면 **적용하지 않는다.**"""
    checked: bool = False
    problems: list = field(default_factory=list)
    skipped: list = field(default_factory=list)     # 기준 원본이 없어 못 본 파일

    @property
    def ok(self) -> bool:
        # 🔴 fail-closed — 검사를 못 돌렸으면 통과가 아니다
        return bool(self.checked and not self.problems)

    @property
    def summary(self) -> str:
        if not self.checked:
            return "⚠️ 층1 미확인"
        if self.problems:
            return "🔴 층1 위반 " + str(len(self.problems)) + ": " + "; ".join(self.problems[:3])
        s = "✅ 층1 통과"
        if self.skipped:
            s += f" (기준 원본 없어 동결 미검사 {len(self.skipped)})"
        return s


def layer1(files: dict, *, baseline=None) -> Layer1:
    """동결 위반 · `[PSEUDO]`/펜스 잔재를 본다. **무료·즉시·LLM 0.**

    `baseline(path) -> str|None` — 그 파일의 **적용 전** 내용. `None` 이면 신규 파일이므로
    동결 대조 대상이 없다(정상). 🔴 함수 자체가 없으면 **검사를 안 한 것**이다.
    """
    L = Layer1()
    if not files:
        L.problems.append("적용할 파일이 없다")
        return L
    L.checked = True
    for path in sorted(files):
        text = files[path] or ""
        if skeleton.pseudo_count(text):
            # 🔴 `[PSEUDO]` 는 *"여기를 채워라"* 는 표시다 — 남아 있으면 본문이 안 채워졌다
            L.problems.append(f"{path}: `[PSEUDO]` 가 남아 있다")
        if skeleton._FENCE_ANY.search(text):
            # 🔴 마크다운 펜스가 소스에 들어가면 컴파일이 깨진다 (14b 의 알려진 결함)
            L.problems.append(f"{path}: 마크다운 펜스가 남아 있다")
        if baseline is None:
            continue
        old = baseline(path)
        if old is None:
            continue                        # 신규 파일 — 동결할 원본이 없다
        if not skeleton.is_header(path):
            continue                        # 동결은 **선언**의 문제다 (`.cpp` 는 대상 아님)
        why = skeleton.violation(old, text)
        if why:
            L.problems.append(f"{path}: 동결 위반 — {why}")
    if baseline is None:
        L.skipped = sorted(files)
    return L


def local_baseline(paths, base_commit: str):
    """마스터의 색인 클론을 기준 원본으로 쓴다 — **왕복 없이** 동결을 대조한다.

    🔴 근거: §8.4 가 *"durable 을 만드는 기준 커밋 == 매니페스트의 twin_commit ==
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
        from ..source_text import decode          # 🔴 소스 44%가 CP949 다
        d = decode(p.read_bytes())
        # 🔴 `decode` 는 **`Decoded` 를 돌려준다 — 문자열이 아니다.** 실측 2026-08-12: 그대로
        #    넘겼더니 `frozen_decls` 가 터졌다. 단위 테스트가 `baseline` 을 주입해서 이 실물
        #    경로를 안 밟았고, **실전에서 나왔다.**
        if d.degraded:
            # ⚠️ 문자가 유실된 사본으로 동결을 판정하면 **없는 위반을 만든다**(치환된 글자가
            #    선언 키를 바꾼다). 정상 작업을 막는 게이트가 통과시키는 게이트보다 나쁘다 —
            #    `None` 을 돌려 그 파일은 **동결 미검사**로 기록되게 한다.
            return None
        return d.text
    return read


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
            return f"{self.task_id}: ⏭️ 적용 안 함 — {self.skipped}"
        if self.ok:
            b = f" · 빌드 {self.build.seconds:.0f}초" if getattr(self.build, "seconds", None) \
                else ""
            return f"{self.task_id}: ✅ 커밋 {self.commit[:8]}{b} · 파일 {len(self.files)}"
        bits = [f"{self.task_id}: 🔴"]
        if self.l1 is not None and not self.l1.ok:
            bits.append(self.l1.summary)
        elif self.build is not None and not self.build.passed:
            bits.append(self.build.summary())
        if self.error:
            bits.append(self.error)
        if self.reverted:
            bits.append("되돌렸다 (커밋하지 않았다)")
        return " — ".join(bits)


def feedback_block(a: Applied) -> str:
    """다음 라운드가 읽을 `[FEEDBACK]`. 🔴 **소스 파일에 넣지 않는다** (§ 머리말)."""
    lines = [f"{FEEDBACK_BEGIN} {a.task_id} — 통합자가 적용했지만 통과하지 못했다",
             ""]
    if a.l1 is not None and not a.l1.ok:
        lines.append("층1 (적용 직전 자기검증) 위반:")
        lines += [f"  - {p}" for p in a.l1.problems]
        lines.append("")
    if a.build is not None and not a.build.passed:
        lines.append("UE5 빌드 판정:")
        lines.append(f"  {a.build.summary()}")
        tail = getattr(a.build, "tail", "") or ""
        if tail:
            lines.append("")
            lines.append("빌드 로그 꼬리 (🔴 요약하지 않는다 — 원문이 근거다):")
            lines += [f"  {ln}" for ln in tail.strip().split("\n")[-15:]]
        lines.append("")
    if a.error:
        lines += [f"오류: {a.error}", ""]
    lines.append("🔴 이 조각의 파일은 **되돌렸다 — 커밋하지 않았다.** 같은 durable 브랜치에서 "
                 "다시 시도한다. 맞게 짠 부분을 버리지 말고 **고쳐서 전진**한다.")
    return "\n".join(lines)


def _revert(facts, tree: str, files: list, *, runner_=None) -> bool:
    """실패한 조각의 파일만 되돌린다. 🔴 `clean` 도 `reset --hard` 도 쓰지 않는다.

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
              builder=None, writer=None, runner_=None,
              timeout: int = skeleton_gate.BUILD_TIMEOUT) -> Applied:
    """조각 하나: 층1 → 적용 → 빌드 → 🔴 통과하면 커밋, 실패하면 되돌린다."""
    a = Applied(task_id=res.task_id, files=sorted(res.files))

    # ① 층1 — 무료다. 🔴 비싼 빌드 앞에 싼 검사를 둔다
    a.l1 = layer1(res.files, baseline=baseline)
    if not a.l1.ok:
        a.error = "층1 에서 막혔다 — 적용하지 않았다"
        return a

    # ② 적용 — `skeleton_gate.place` 가 해시 대조까지 한다
    try:
        skeleton_gate.place(facts, tree, res.files, writer=writer)
    except Exception as e:                                   # noqa: BLE001
        a.error = f"적용 실패: {e}"
        _revert(facts, tree, a.files, runner_=runner_)
        a.reverted = True
        return a

    # ③ 빌드 판정 — 🔴 fail-closed. 판정을 못 받으면 막는다
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
        # 🔴 실패는 커밋하지 않는다 (소 1.4.4) — 되돌리고 사유를 남긴다
        a.reverted = _revert(facts, tree, a.files, runner_=runner_)
        if not a.reverted:
            a.error = "🔴 되돌리지 못했다 — 트리가 더러운 채 남았다. 사람이 확인할 것"
        return a

    # ④ 커밋 — **빌드해 본 주체가 커밋한다**
    quoted = " ".join(f'"{f}"' for f in a.files)
    rc, out = _git(facts, f"add -- {quoted}", cwd=tree, runner_=runner_)
    if rc != 0:
        a.error = f"git add 실패 — {out.strip()[:120]}"
        return a
    msg = f"{res.task_id}: 통합자 적용 (빌드 통과)"
    rc, out = _git(facts, f'commit --quiet -m "{msg}"', cwd=tree, runner_=runner_)
    if rc != 0:
        # ⚠️ 변경이 없으면 git 은 rc≠0 을 낸다 — 그것과 진짜 실패를 가른다
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


@dataclass
class Integration:
    work_id: str = ""
    tree: str = ""
    base: str = ""
    applied: list = field(default_factory=list)
    pushed: str = ""
    branch: str = ""
    note: str = ""

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
               + (f" · 🔴 실패 {len(self.failed)}" if self.failed else "")]
        if self.tree:
            out.append(f"  격리 트리 {self.tree} @ {self.base[:8]}")
        for a in self.applied:
            out.append("  " + a.summary)
        if self.pushed:
            out.append(f"  🔴 push ✅ {self.branch} ← {self.pushed[:8]}")
        elif self.passed:
            out.append("  ⚠️ push 하지 않았다 — durable 이 없거나 거부됐다 (아래 참조)")
        if self.note:
            out.append("  " + self.note)
        return "\n".join(out)


def load_handoff(paths, work_id: str) -> list:
    """스풀에서 **통과분만**, 적용 순서대로. 🔴 실패한 응답은 통합자에게 가지 않는다."""
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
    """🔴 **모든 응답이 같은 기준 커밋이어야 한다.** 섞이면 적용하지 않는다.

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


def run(paths, facts, work_id: str, *, project: str = "", durable: str = "",
        stop_on_fail: bool = True, baseline=None, builder=None, writer=None,
        runner_=None, push: bool = True, api=runner._api,
        timeout: int = skeleton_gate.BUILD_TIMEOUT) -> Integration:
    """work 하나를 통합한다 — 🔴 **적용은 순차, 통과분만 커밋.**

    `durable` — durable 브랜치 이름(없으면 push 하지 않고 로컬 커밋까지만 한다).
    """
    responses = load_handoff(paths, work_id)
    base = one_base(responses)
    itg = Integration(work_id=work_id, base=base, branch=durable)
    proj = project or paths.name

    wt = ensure_worktree(facts, work_id, at_commit=base, runner_=runner_)
    itg.tree = wt.path
    if not wt.ok:
        itg.note = f"🔴 격리 트리를 세우지 못했다 — {wt.error}"
        return itg

    # 🔴 기준 원본: 마스터의 로컬 클론이 같은 커밋이면 그것을 쓰고(왕복 0), 아니면 원격에서
    #    읽는다. 둘 다 안 되면 `baseline=None` 이라 **동결 미검사**로 기록된다(통과가 아니다).
    base_fn = baseline or local_baseline(paths, base) or remote_baseline(facts, wt.path)

    stopped = ""
    for r in responses:
        if stopped:
            a = Applied(task_id=r.task_id, files=sorted(r.files),
                        skipped=f"선행 {stopped} 이 실패했다 (적용 순서 = 의존 순서)")
            itg.applied.append(a)
            continue
        a = apply_one(facts, r, tree=wt.path, project=proj, baseline=base_fn,
                      builder=builder, writer=writer, runner_=runner_, timeout=timeout)
        itg.applied.append(a)
        if not a.ok:
            _submit_fail(r, a, api=api)
            if stop_on_fail:
                stopped = a.task_id

    if not itg.passed:
        itg.note = "🔴 커밋된 것이 없다 — push 할 것도 없다"
        return itg

    if not durable:
        # ⚠️ 없는 것을 있는 척하지 않는다
        itg.note = ("⚠️ durable 브랜치를 받지 못해 **로컬 커밋까지만** 했다. "
                    "요청자(`.33`)가 `task/<id>` 를 만들어야 push 할 곳이 생긴다(§8.4)")
        return itg
    if push:
        # 🔴 ff-only. `--force` 는 쓰지 않는다 — 남의 커밋을 지운다
        rc, out = _git(facts, f"push origin HEAD:refs/heads/{durable}",
                       cwd=wt.path, runner_=runner_)
        if rc != 0:
            itg.note = (f"🔴 push 거부됨 — {out.strip()[:160]}. 커밋은 격리 트리에 남아 있다 "
                        f"(잃지 않았다). ff 가 안 되면 사람이 판단한다 — **force 하지 않는다**")
            return itg
        itg.pushed = itg.passed[-1].commit
        for a, r in zip(itg.applied, responses):
            if a.ok:
                _submit_ok(r, a, durable, api=api)
    return itg


def _submit_ok(r: Response, a: Applied, durable: str, *, api=runner._api) -> None:
    """🔴 **여기가 큐에 제출하는 유일한 자리다** (소 1.4.3) — 빌드를 통과한 커밋이 근거다."""
    try:
        api("POST", f"/api/v1/tasks/{r.task_id}/submit", {
            "branch": durable, "head_commit": a.commit,
            "self_check": {"layer1": a.l1.summary if a.l1 else "",
                           "build": a.build.summary() if a.build else "",
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
# 🔴 `plan` 은 아무것도 쓰지 않는다. 남의 기계에 쓰는 작업이라 먼저 본다(`client` 와 같은 규약).

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
        print(f"🔴 {e}")
        return 1

    facts = [bundle.probe(h, u, p, d, r) for h, u, p, d, r in bundle.workshops(paths.name)]
    # 🔴 통합자는 **UE5 가 있는 기계**다. 없으면 빌드 판정을 못 하므로 통합자가 아니다.
    ue = [f for f in facts if f.role == "worker" and f.checkout_ok and f.ue5]
    if cmd == "plan":
        print(f"work {work_id} · 기준 {base[:12]} · 조각 {len(responses)}")
        for i, r in enumerate(responses, 1):
            print(f"  {i}. {r.task_id} — {', '.join(sorted(r.files))}")
        print(f"통합자 후보: {', '.join(f.host for f in ue) or '🔴 UE5 가 있는 워커가 없다'}")
        if ue:
            print(f"격리 트리: {worktree_path(ue[0], work_id)}")
        return 0
    if not ue:
        print("🔴 UE5 가 있는 워커가 없다 — 빌드 판정을 못 하므로 통합하지 않는다")
        return 1
    itg = run(paths, ue[0], work_id, durable=(argv[3] if len(argv) > 3 else ""))
    print(itg.summary())
    return 0 if itg.ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
