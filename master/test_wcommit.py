"""정본 ⑸-a — 워커가 자기 서브 브랜치에 커밋한다 (사용자 확정 2026-09-02).

**실물 git 으로 잰다.** `ssh` 를 주입해 「원격 셸」을 로컬 `bash -c` 로 바꿔 놓으면, 명령
문자열이 실제로 도는지·ref 가 실제로 서는지가 그대로 잡힌다. 여기서 지키는 계약:

    ① 서브 브랜치에 **커밋이 실제로 생기고 원격에 올라간다**
    ② 층1 위반이면 **커밋하지 않는다** (verify-then-commit — 원전과 순서가 다른 그 칸)
    ③ 본문이 비면 커밋하지 않는다 · 커밋이 안 생겼으면(HEAD==base) 성공으로 읽지 않는다
    ④ `add` 는 **명시 목록만** — 사람의 WIP 를 삼키지 않는다
    ⑤ `clean -fd` 에 `-x` 가 없다 (gitignore 대상 보존)
    ⑥ [중요] **끝나면 `main` 으로 돌아온다** — 조각 브랜치에 서 있으면 정리기가 못 지운다

`python3 master/test_wcommit.py`
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import wcommit                                     # noqa: E402

PASS = FAIL = 0
WORK = "20260902_0035_ns_1_ea254ff3"
TASK = "58ff3406"
HDR = "Source/NS/NSInteract.h"
SRC = "Source/NS/NSInteract.cpp"


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def sh(cwd: Path, *args: str) -> str:
    r = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} → {r.stderr[:200]}")
    return r.stdout.strip()


class _Facts:
    """`HostFacts` 에서 이 모듈이 쓰는 네 필드만."""

    def __init__(self, path: Path):
        self.path = str(path)
        self.host = "rtx3060"
        self.user = "janus"
        self.windows = False


def _shell(facts, cmd: str, timeout: int):
    """주입 ssh — 「원격」 셸을 로컬 bash 로 바꾼다. 명령 문자열은 그대로 돈다."""
    r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _reader(facts, abs_path: str) -> str:
    p = Path(abs_path)
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def _world(tmp: Path):
    """bare 원격 + 골조가 실린 작업 브랜치 + **워커 클론**. `(facts, bare, base, worker_repo)`."""
    bare = tmp / "origin.git"
    bare.mkdir()
    sh(bare, "git", "init", "--bare", "-q", "-b", "main", ".")

    seed = tmp / "seed"
    seed.mkdir()
    sh(seed, "git", "init", "-q", "-b", "main", ".")
    sh(seed, "git", "config", "user.email", "t@t")
    sh(seed, "git", "config", "user.name", "t")
    (seed / "README").write_text("x\n", encoding="utf-8")
    sh(seed, "git", "add", "README")
    sh(seed, "git", "commit", "-q", "-m", "main")
    sh(seed, "git", "push", "-q", str(bare), "main")
    # 골조 — 헤더 `[DOC]` + `.cpp` 는 `[PSEUDO]` 껍데기
    sh(seed, "git", "checkout", "-q", "-b", "skel")
    for rel, body in ((HDR, "// [DOC] 상호작용 인터페이스\nclass NSInteract { void Use(); };\n"),
                      (SRC, "// [PSEUDO] Use 본문 구현\nvoid NSInteract::Use() {}\n")):
        f = seed / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body, encoding="utf-8")
    sh(seed, "git", "add", HDR, SRC)
    sh(seed, "git", "commit", "-q", "-m", "skeleton")
    base = sh(seed, "git", "rev-parse", "HEAD")
    sh(seed, "git", "push", "-q", str(bare), f"HEAD:refs/heads/task/{WORK}/base")

    worker = tmp / "worker-clone"
    sh(tmp, "git", "clone", "-q", str(bare), str(worker))
    sh(worker, "git", "config", "user.email", "w@w")
    sh(worker, "git", "config", "user.name", "w")
    return _Facts(worker), bare, base, worker


def _heads(bare: Path) -> dict:
    out = sh(bare, "git", "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads")
    return dict(ln.split() for ln in out.splitlines() if ln.strip())


def _llm_writes(bodies: dict):
    """골조를 채우는 LLM 흉내 — **파일만 쓴다. git 은 만지지 않는다.**"""
    def call(facts, task_id, want):
        for rel, body in bodies.items():
            f = Path(facts.path) / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(body, encoding="utf-8")
        return 0, "ok"
    return call


GOOD = {SRC: "// [DOC] 상호작용\nvoid NSInteract::Use() { DoTheThing(); }\n"}
KEEP_HDR = "// [DOC] 상호작용 인터페이스\nclass NSInteract { void Use(); };\n"


def test_commands():
    f = _Facts(Path("/w/clone"))
    co = wcommit.checkout_command(f, f"task/{WORK}/{TASK}", "abc123")
    check("[중요] `clean -fd` 에 `-x` 가 없다 (gitignore 보존)",
          "clean -fd" in co and "-fdx" not in co and "clean -fd -x" not in co, co)
    check("잔재를 지우고 서브 브랜치를 세운다",
          "reset --hard" in co and f'checkout -q -B "task/{WORK}/{TASK}" "abc123"' in co, co)
    cm = wcommit.commit_command(f, f"task/{WORK}/{TASK}", TASK, [SRC, HDR])
    check("[중요] `add` 는 명시 목록만 (`add -A` 아님)",
          f'git add "{SRC}" "{HDR}"' in cm and "add -A" not in cm, cm)
    check("[중요] `--force-with-lease` 이고 맨 `--force` 가 아니다",
          "--force-with-lease" in cm and "push --quiet --force " not in cm, cm)
    check("커밋 메시지는 원전 규약이다",
          f"[task:{TASK}] worker=rtx3060 target={SRC}" in cm, cm)
    try:
        wcommit.commit_command(f, "b", TASK, [])
        check("[중요] 대상이 없으면 커밋 명령을 만들지 않는다", False, "예외가 안 났다")
    except Exception:
        check("[중요] 대상이 없으면 커밋 명령을 만들지 않는다", True)


def test_returns_to_main():
    """🔴 [중요] 실측 2026-09-03 — 이 단계가 없어서 `.2` 가 조각 브랜치에 남았다.

    체크아웃된 브랜치는 `git branch -d` 대상에서 빠지므로, 병합이 끝나도 **정리기가 영영
    못 지운다**. 원전 사이클에 이 단계가 있고 이유가 정확히 그것이다.
    """
    with tempfile.TemporaryDirectory() as td:
        facts, bare, base, worker = _world(Path(td))
        c = wcommit.run(facts, {"task_id": TASK}, work_id=WORK, base_commit=base,
                        want=[SRC], llm=_llm_writes(GOOD), ssh=_shell, reader=_reader,
                        baseline=lambda p: KEEP_HDR if p == HDR else None)
        check("통과한다", c.ok, c.summary)
        cur = sh(worker, "git", "rev-parse", "--abbrev-ref", "HEAD")
        check("[중요] **`main` 으로 돌아왔다**", cur == "main", cur)
        check("  그래도 커밋은 원격에 있다",
              _heads(bare).get(f"task/{WORK}/{TASK}") == c.head, f"{_heads(bare)}")
        # 실패 경로도 돌아와야 한다 — 잔재가 남는 것은 성공/실패와 무관하다
        c2 = wcommit.run(facts, {"task_id": "bad1"}, work_id=WORK, base_commit=base,
                         want=[SRC], llm=_llm_writes({SRC: "// [PSEUDO] 안 채웠다\n"}),
                         ssh=_shell, reader=_reader)
        check("막혔어도 돌아온다", not c2.ok and
              sh(worker, "git", "rev-parse", "--abbrev-ref", "HEAD") == "main",
              c2.summary)


def test_happy_path():
    with tempfile.TemporaryDirectory() as td:
        facts, bare, base, worker = _world(Path(td))
        c = wcommit.run(facts, {"task_id": TASK}, work_id=WORK, base_commit=base,
                        want=[SRC], llm=_llm_writes(GOOD),
                        ssh=_shell, reader=_reader,
                        baseline=lambda p: KEEP_HDR if p == HDR else None)
        check("통과한다", c.ok, c.summary)
        check("커밋이 기준 커밋과 다르다", c.head and c.head != base, f"{c.head[:8]} vs {base[:8]}")
        heads = _heads(bare)
        want_ref = f"task/{WORK}/{TASK}"
        check("[중요] **원격 서브 브랜치에 커밋이 올라갔다**", heads.get(want_ref) == c.head,
              f"{heads}")
        # 그 커밋이 골조 위에 있고 대상 파일만 들었나
        log = sh(worker, "git", "log", "--format=%s", "-1", c.head)
        check("커밋 메시지가 원전 규약이다", log.startswith(f"[task:{TASK}]"), log)
        anc = subprocess.run(["git", "merge-base", "--is-ancestor", base, c.head],
                             cwd=str(worker)).returncode
        check("[중요] 골조 커밋의 자손이다 (작업 브랜치에서 갈라졌다)", anc == 0)
        names = sh(worker, "git", "show", "--name-only", "--format=", c.head).split()
        check("[중요] 대상 파일만 들었다", names == [SRC], str(names))


def test_layer1_blocks_commit():
    """[중요] 층1 위반이면 **커밋하지 않는다** — verify-then-commit."""
    with tempfile.TemporaryDirectory() as td:
        facts, bare, base, worker = _world(Path(td))
        bad = {SRC: "// [PSEUDO] 아직 안 채웠다\nvoid NSInteract::Use() {}\n"}
        c = wcommit.run(facts, {"task_id": TASK}, work_id=WORK, base_commit=base,
                        want=[SRC], llm=_llm_writes(bad), ssh=_shell, reader=_reader)
        check("막힌다", not c.ok and c.layer1_violations, c.summary)
        check("  단계가 층1 로 남는다", c.stage == "층1", c.stage)
        check("[중요] **커밋이 생기지 않았다**", not c.head, c.head)
        check("[중요] **원격에 서브 브랜치가 안 생겼다**",
              f"task/{WORK}/{TASK}" not in _heads(bare), f"{_heads(bare)}")


def test_empty_body_blocks():
    with tempfile.TemporaryDirectory() as td:
        facts, bare, base, _w = _world(Path(td))
        c = wcommit.run(facts, {"task_id": TASK}, work_id=WORK, base_commit=base,
                        want=[SRC], llm=_llm_writes({SRC: "   \n"}),
                        ssh=_shell, reader=_reader)
        check("빈 본문은 막힌다", not c.ok and c.missing, c.summary)
        check("  커밋 없음", not c.head and f"task/{WORK}/{TASK}" not in _heads(bare))


def test_no_change_is_not_success():
    """[주의] 채울 것이 있었는데 아무것도 안 바뀌었으면 **통과가 아니다.**

    🔴 [중요] **이 테스트의 전제가 2026-09-03 에 좁혀졌다** (사용자 결정 ⓑ · 원전 이식).
    종전에는 *"변경 0 이면 무조건 실패"* 였는데, 원전 `worker/validator.py:547` 은
    *"원본에 `[PSEUDO]` 가 없었으면 no-op(정상), 있었으면 진짜 실패"* 로 가른다.
    그래서 잼대를 **`[PSEUDO]` 가 있는 파일**(`.cpp` 골조)로 바꿨다 — 헤더는 `[DOC]` 만
    있어서 이제 정상 no-op 이다(`test_no_pseudo_and_no_change_is_a_no_op_not_a_failure`).

    [주의] 실제로 막는 것은 **층1** 이다 — 휘발 태그 잔재를 커밋 **전에** 잡는다. 커밋
    단계의 검사는 그 뒤를 받치는 두 번째 그물이다.
    """
    with tempfile.TemporaryDirectory() as td:
        facts, _bare, base, _w = _world(Path(td))
        c = wcommit.run(facts, {"task_id": TASK}, work_id=WORK, base_commit=base,
                        want=[SRC], llm=lambda f, t, w: (0, "아무것도 안 했다"),
                        ssh=_shell, reader=_reader, baseline=lambda p: None)
        check("변경 0 + `[PSEUDO]` 잔존 = 통과가 아니다", not c.ok, c.summary)
        check("  no_op 으로 접지 않는다", not c.no_op, c.summary)
        check("  사유를 말한다", bool(c.reason or c.layer1_violations), c.summary)


def test_refusals():
    f = _Facts(Path("/nope"))
    boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("여기까지 오면 안 된다"))
    for name, kw in (("task_id 없음", {"task": {}}),
                     ("대상 없음", {"task": {"task_id": TASK}, "want": []}),
                     ("기준 커밋 없음", {"task": {"task_id": TASK}, "base_commit": ""})):
        args = {"work_id": WORK, "base_commit": "abc", "want": [SRC], "llm": boom,
                "ssh": boom, "reader": boom}
        args.update(kw)
        task = args.pop("task")
        c = wcommit.run(f, task, **args)
        check(f"[중요] {name} → 아무것도 하지 않고 거절", not c.ok and c.stage == "입력", c.summary)


def test_llm_failure_does_not_commit():
    with tempfile.TemporaryDirectory() as td:
        facts, bare, base, _w = _world(Path(td))
        c = wcommit.run(facts, {"task_id": TASK}, work_id=WORK, base_commit=base,
                        want=[SRC], llm=lambda f, t, w: (1, "세션 한도"),
                        ssh=_shell, reader=_reader)
        check("본문 작성 실패는 커밋으로 가지 않는다",
              not c.ok and c.stage == "본문 작성" and not c.head, c.summary)
        check("  원격도 그대로", f"task/{WORK}/{TASK}" not in _heads(bare))



# ── 🔴 할 일이 없는 조각 (원전 `ok_no_op` 이식 · 사용자 결정 ⓑ 2026-09-03) ──────────

def test_no_pseudo_and_no_change_is_a_no_op_not_a_failure():
    """🔴 **정상 조각이 두 라운드 연속 죽은 자리다** (실측 2026-09-03).

    `NSInteractionPromptWidget` 의 골조가 *"UpdatePrompt 는 BlueprintImplementableEvent 라
    C++ 기본 구현이 없다 — 이 클래스에는 C++ 로직을 추가하지 않는다"* 이고 `[PSEUDO]` 0개다.
    워커는 골조를 **바이트 동일**하게 돌려줬고 **그것이 정답인데**, 커밋 단계가
    `nothing to commit` → rc=1 → BLOCKED 로 읽었다. 조각당 $0.66~$1.08 × 2 라운드.

    원전 계약: `worker/git_ops.py:149` 는 그 문구를 에러로 안 보고,
    `worker/validator.py:547` 이 *"원본에 `[PSEUDO]` 가 없었으면 no-op(정상), 있었으면
    진짜 실패"* 로 가른다. 여기 want 는 헤더뿐이고 헤더에는 `[DOC]` 만 있다.
    """
    with tempfile.TemporaryDirectory() as td:
        facts, _bare, base, _w = _world(Path(td))
        c = wcommit.run(facts, {"task_id": TASK}, work_id=WORK, base_commit=base,
                        want=[HDR], llm=lambda f, t, w: (0, "채울 것이 없다"),
                        ssh=_shell, reader=_reader, baseline=lambda p: KEEP_HDR)
        check("[중요] 실패가 아니다", c.ok, c.summary)
        check("  no_op 으로 표시한다", c.no_op, c.summary)
        check("  사유를 남기지 않는다", not c.reason, c.reason)
        check("  무엇이었는지 말한다", "[PSEUDO]" in c.summary and "0개" in c.summary, c.summary)


def main() -> int:
    for fn in (test_no_pseudo_and_no_change_is_a_no_op_not_a_failure,
               test_commands, test_returns_to_main, test_happy_path, test_layer1_blocks_commit,
               test_empty_body_blocks, test_no_change_is_not_success,
               test_refusals, test_llm_failure_does_not_commit):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_wcommit: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
