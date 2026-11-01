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
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import wcommit                                     # noqa: E402
from master.verdict import Verdict                                  # noqa: E402

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


def _approved(files):
    return Verdict(True, None)


def _verified_run(*args, **kwargs):
    return wcommit.run(*args, verifier=_approved, **kwargs)


def test_commands():
    f = _Facts(Path("/w/clone"))
    co = wcommit.checkout_command(f, f"task/{WORK}/{TASK}", "abc123")
    check("[중요] `clean -fd` 에 `-x` 가 없다 (gitignore 보존)",
          "clean -fd" in co and "-fdx" not in co and "clean -fd -x" not in co, co)
    check("잔재를 지우고 서브 브랜치를 세운다",
          "reset --hard" in co and f'checkout -q -B "task/{WORK}/{TASK}" "abc123"' in co, co)
    check("`#787` ③ 워커 fetch 가 prune 한다 (원격에서 지운 브랜치의 원격추적 ref 를 남기지 않는다)",
          "git fetch --all --prune --quiet" in co, co)
    wf = _Facts(Path("/w/clone"))
    wf.windows = True
    try:
        wco = wcommit.checkout_command(wf, "b", "abc123")
        check("  윈도우 모양에서도 prune 한다", "git fetch --all --prune --quiet" in wco, wco)
    except Exception as e:      # noqa: BLE001
        check("  윈도우 모양에서도 prune 한다", False, f"{type(e).__name__}: {e}")
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
        c = _verified_run(facts, {"task_id": TASK}, work_id=WORK, base_commit=base,
                        want=[SRC], llm=_llm_writes(GOOD), ssh=_shell, reader=_reader,
                        baseline=lambda p: KEEP_HDR if p == HDR else None)
        check("통과한다", c.ok, c.summary)
        cur = sh(worker, "git", "rev-parse", "--abbrev-ref", "HEAD")
        check("[중요] **`main` 으로 돌아왔다**", cur == "main", cur)
        check("  그래도 커밋은 원격에 있다",
              _heads(bare).get(f"task/{WORK}/{TASK}") == c.head, f"{_heads(bare)}")
        # 실패 경로도 돌아와야 한다 — 잔재가 남는 것은 성공/실패와 무관하다
        c2 = _verified_run(facts, {"task_id": "bad1"}, work_id=WORK, base_commit=base,
                         want=[SRC], llm=_llm_writes({SRC: "// [PSEUDO] 안 채웠다\n"}),
                         ssh=_shell, reader=_reader)
        check("막혔어도 돌아온다", not c2.ok and
              sh(worker, "git", "rev-parse", "--abbrev-ref", "HEAD") == "main",
              c2.summary)



def test_return_home_syncs_main_871():
    """🔴 `#871` — 복귀는 로컬 `main` 을 `origin/main` 에 맞춘다(앞선 원격 · 갈라진 로컬 · 실패 경로)."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        facts, bare, base, worker = _world(tmp)
        old_main = sh(worker, "git", "rev-parse", "main")
        # 워커 클론을 만든 뒤 원격 main 이 앞서 나간다(다른 커밋이 쌓인 상황)
        seed = tmp / "seed"
        sh(seed, "git", "checkout", "-q", "main")
        (seed / "NEW").write_text("y\n", encoding="utf-8")
        sh(seed, "git", "add", "NEW")
        sh(seed, "git", "commit", "-q", "-m", "main 2")
        sh(seed, "git", "push", "-q", str(bare), "main")
        new_main = _heads(bare)["main"]
        check("#871 전제 — 워커 로컬 main 은 옛 커밋", old_main != new_main)
        c = _verified_run(facts, {"task_id": TASK}, work_id=WORK, base_commit=base,
                          want=[SRC], llm=_llm_writes(GOOD), ssh=_shell, reader=_reader,
                          baseline=lambda p: KEEP_HDR if p == HDR else None)
        check("#871 통과한다", c.ok, c.summary)
        check("#871 복귀 뒤 로컬 main == origin/main(앞선 원격을 따라잡는다)",
              sh(worker, "git", "rev-parse", "main") == new_main
              and sh(worker, "git", "rev-parse", "--abbrev-ref", "HEAD") == "main",
              sh(worker, "git", "rev-parse", "main"))
        check("#871 트리도 새 main 이다(NEW 파일)", (worker / "NEW").exists())
        # 갈라진 로컬 main(있어서는 안 되지만) — 파이프라인 소유 클론이라 원격에 맞춰 다시 세운다
        (worker / "LOCAL").write_text("z\n", encoding="utf-8")
        sh(worker, "git", "add", "LOCAL")
        sh(worker, "git", "commit", "-q", "-m", "diverged")
        c2 = _verified_run(facts, {"task_id": "bad871"}, work_id=WORK, base_commit=base,
                           want=[SRC], llm=_llm_writes({SRC: "// [PSEUDO] 안 채웠다\n"}),
                           ssh=_shell, reader=_reader)
        check("#871 막힌(실패) 경로도 · 갈라진 로컬 main 도 origin/main 으로",
              not c2.ok and sh(worker, "git", "rev-parse", "main") == new_main
              and not (worker / "LOCAL").exists(), c2.summary)


def test_return_home_command_shape_871():
    """명령 모양 — `-B main origin/main` 을 먼저, 없으면 종전 `checkout main` 대비(리눅스·윈도우)."""
    from master.work import wcommit as W
    for win in (False, True):
        f = _Facts("C:\\w" if win else "/w")
        f.windows = win
        cmd = W.return_home_command(f, branch="task/x/y", task_id="t1")
        check(f"#871 {'윈도우' if win else '리눅스'}: -B main origin/main 뒤 대비",
              '(git checkout -q -B "main" "origin/main" || git checkout -q "main")' in cmd, cmd)


def test_worker_keeps_nothing() -> None:
    """🔴 **워커는 임시 저장소다 — 커밋하고 나면 아무것도 안 남는다** (사용자 2026-09-04).

    *"작업 워커는 그냥 임시 저장소로 쓰는거야. 거기 뭘 남길 필요가 없어"*.

    [주의] 종전에는 `main` 복귀만 하고 조각 브랜치를 남겼다. 지우는 판정을 `cleanup.py` 가
    「팁이 `origin/main` 에서 도달 가능한가」로 했는데 전진분은 `main` 이 아니라 작업
    브랜치로 들어가므로 **영원히 「보존」** 이었다 — 실측 2026-09-04 에 라운드 하나가
    세 기계에 잔재를 남겼고 사람이 손으로 걷었다.
    """
    with tempfile.TemporaryDirectory() as td:
        facts, bare, base, worker = _world(Path(td))
        art = worker / ".ax" / "work" / TASK
        art.mkdir(parents=True, exist_ok=True)
        (art / "response.txt").write_text("x\n", encoding="utf-8")

        c = _verified_run(facts, {"task_id": TASK}, work_id=WORK, base_commit=base,
                        want=[SRC], llm=_llm_writes(GOOD), ssh=_shell, reader=_reader,
                        baseline=lambda p: KEEP_HDR if p == HDR else None)
        check("통과한다", c.ok, c.summary)
        local = sh(worker, "git", "for-each-ref", "--format=%(refname:short)", "refs/heads")
        check("🔴 **조각 브랜치가 로컬에 안 남는다**",
              f"task/{WORK}/{TASK}" not in local.split(), local)
        check("  `main` 만 남는다", local.split() == ["main"], local)
        check("[중요] 그래도 커밋은 원격에 있다 — 잃은 것이 없다",
              _heads(bare).get(f"task/{WORK}/{TASK}") == c.head, str(_heads(bare)))
        check("  부산물 디렉토리도 지운다", not art.exists(), str(art))

        # 실패 경로도 같다 — 잔재가 남는 것은 성공/실패와 무관하다
        c2 = _verified_run(facts, {"task_id": "bad9"}, work_id=WORK, base_commit=base,
                         want=[SRC], llm=_llm_writes({SRC: "// [PSEUDO] 안 채웠다\n"}),
                         ssh=_shell, reader=_reader)
        local2 = sh(worker, "git", "for-each-ref", "--format=%(refname:short)", "refs/heads")
        check("막혔어도 로컬에 안 남는다",
              not c2.ok and local2.split() == ["main"], f"{c2.summary} · {local2}")


def test_happy_path():
    with tempfile.TemporaryDirectory() as td:
        facts, bare, base, worker = _world(Path(td))
        c = _verified_run(facts, {"task_id": TASK}, work_id=WORK, base_commit=base,
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


def test_collects_delegations():
    """🔴 `#764` — 지휘자가 `.agy-work/out/` 에 남긴 agy 응답을 **복귀 전에** 마스터로 회수하고,
    복귀가 워커의 그 폴더를 지운다. 이름 규칙 밖 파일은 가져오지 않는다."""
    import os as _os
    with tempfile.TemporaryDirectory() as td:
        facts, bare, base, worker = _world(Path(td))
        root = Path(td) / "deleg"
        _os.environ["AX_DELEGATIONS_ROOT"] = str(root)
        inner = _llm_writes(GOOD)
        stale = Path(facts.path) / ".agy-work" / "out"
        stale.mkdir(parents=True, exist_ok=True)
        (stale / "old.json").write_text("지난 사이클", encoding="utf-8")
        seen = {}

        def llm(f, task_id, want):
            w0 = Path(f.path) / ".agy-work"
            seen["dirs"] = (w0 / "in").is_dir() and (w0 / "out").is_dir()
            seen["stale"] = (w0 / "out" / "old.json").exists()
            out = w0 / "out"
            out.mkdir(parents=True, exist_ok=True)
            (out / "1.json").write_text('{"status": "SUCCESS", "response": "조사 결과"}', encoding="utf-8")
            (out / "2.json").write_text('{"status": "ERROR", "response": ""}', encoding="utf-8")
            (out / "bad name.json").write_text("x", encoding="utf-8")
            (Path(f.path) / ".agy-work" / "in" / "src").mkdir(parents=True, exist_ok=True)
            return inner(f, task_id, want)
        try:
            c = _verified_run(facts, {"task_id": TASK}, work_id=WORK, base_commit=base,
                              want=[SRC], llm=llm, ssh=_shell, reader=_reader,
                              baseline=lambda p: KEEP_HDR if p == HDR else None)
        finally:
            _os.environ.pop("AX_DELEGATIONS_ROOT", None)
        check("[중요] 체크아웃이 .agy-work/in·out 을 미리 세운다 (`.2` 세션1 BLOCKED 재발 방지)",
              seen.get("dirs") is True, str(seen))
        check("  지난 사이클의 응답은 지운 채로 세운다", seen.get("stale") is False, str(seen))
        dest = root / WORK / TASK
        got = sorted(x.name for x in dest.iterdir()) if dest.is_dir() else []
        check("[중요] 위임 결과가 마스터로 회수된다", got == ["1.json", "2.json"], str(got))
        check("  내용 그대로", (dest / "1.json").read_text(encoding="utf-8").endswith('"조사 결과"}')
              if dest.is_dir() else False)
        check("  회수 노트", any("위임 결과 2개 회수" in n for n in c.notes), str(c.notes))
        check("  판정은 그대로 (통과)", c.ok, c.summary)
        w = Path(facts.path) / ".agy-work"
        check("[중요] 워커에는 .agy-work 가 남지 않는다", not w.exists(),
              str(list(w.iterdir()) if w.is_dir() else []))
        from master.client import spec as _spec
        check("[중요] 워커 체크아웃은 /.agy-work/ 를 git 에서 가린다 · 요청자는 아니다",
              "/.agy-work/" in _spec.git_excludes_for("worker")
              and "/.agy-work/" not in _spec.git_excludes_for("requester"))
        check("  위치는 .ax 밖 (Windows 샌드박스가 .ax 쓰기를 거부한다)", not wcommit.AGY_ROOT.startswith(".ax"))


def test_collect_delegations_continues_after_failure():
    """첫 파일 회수 실패가 뒤의 유효 응답까지 버리지 않는다."""
    for failure in ("none", "read", "write"):
        with tempfile.TemporaryDirectory(prefix="ax-collect-") as td:
            root = Path(td)
            facts = _Facts(root / "worker")
            c = wcommit.Committed(task_id=TASK)
            reads = []

            def reader(facts, path):
                name = Path(path).name
                reads.append(name)
                if name == "1.json":
                    if failure == "none":
                        return None
                    if failure == "read":
                        raise OSError("read fixture")
                return "" if name == "3.json" else '{"response":"ok"}'

            write_text = Path.write_text

            def write(path, *args, **kwargs):
                if failure == "write" and path.name == "1.json":
                    raise OSError("write fixture")
                return write_text(path, *args, **kwargs)

            dest = root / "deleg" / WORK / TASK
            with patch.object(wcommit, "delegations_root", return_value=root / "deleg"), \
                    patch.object(Path, "write_text", write):
                wcommit.collect_delegations(facts, lambda *a: (
                    0, "1.json\n2.json\n3.json\n../escape.json\nbad name.json\n"),
                    reader, c, WORK)
            check(f"{failure}: 뒤 파일과 빈 응답도 저장",
                  sorted(p.name for p in dest.iterdir()) == ["2.json", "3.json"])
            check(f"{failure}: 내용 보존", (dest / "2.json").read_text(encoding="utf-8")
                  == '{"response":"ok"}' and (dest / "3.json").read_text(encoding="utf-8") == "")
            check(f"{failure}: 안전명만 읽음", reads == ["1.json", "2.json", "3.json"], str(reads))
            check(f"{failure}: 실패 파일과 성공 수 기록",
                  any("1.json를 회수하지 못했다" in n for n in c.notes)
                  and any("위임 결과 2개 회수" in n for n in c.notes), str(c.notes))
        check(f"{failure}: 임시 루트 정리", not root.exists())


def test_layer1_blocks_commit():
    """[중요] 층1 위반이면 **커밋하지 않는다** — verify-then-commit."""
    with tempfile.TemporaryDirectory() as td:
        facts, bare, base, worker = _world(Path(td))
        bad = {SRC: "// [PSEUDO] 아직 안 채웠다\nvoid NSInteract::Use() {}\n"}
        c = _verified_run(facts, {"task_id": TASK}, work_id=WORK, base_commit=base,
                        want=[SRC], llm=_llm_writes(bad), ssh=_shell, reader=_reader)
        check("막힌다", not c.ok and c.layer1_violations, c.summary)
        check("  단계가 층1 로 남는다", c.stage == "층1", c.stage)
        check("[중요] **커밋이 생기지 않았다**", not c.head, c.head)
        check("[중요] **원격에 서브 브랜치가 안 생겼다**",
              f"task/{WORK}/{TASK}" not in _heads(bare), f"{_heads(bare)}")


def test_layer1_block_records_what_the_conductor_said():
    """🔴 **층1 이 막았을 때 지휘자의 말이 기록에 남는다** (`#391` · 실측 stdout).

    아래 `REAL` 은 2026-09-09 에 `.2` 에서 **실제로 나온 출력**이다. codex 는 파일 쓰기 도구가
    죽었다고 자기 입으로 말했는데 그 말이 어디에도 안 남아, 마스터에는 층1 의 `[PSEUDO]` 한
    줄만 보였다 ⇒ **환경 실패가 코드 실패로 위장**돼 재시도 3회를 태웠다.

    [중요] **`rc=0` 이다** — 이 사고의 핵심이 그것이라 그대로 재현한다.
    [주의] 이 못은 `#385` 회귀를 막는다: 레인 경로는 처음부터 시도마다 남기고 있었다.
    """
    REAL = (
        '{"type":"thread.started","thread_id":"01a0868f"}\n'
        '2026-09-09T14:26:13Z ERROR codex_core::tools::router: error=exec_command failed: '
        'CreateProcess { message: "Rejected(\\"Failed to create unified exec process: '
        'timed out after 15000ms connecting runner pipe-in\\")" }\n'
        '{"type":"item.completed","item":{"id":"item_2","type":"agent_message",'
        '"text":"Unable to create probe.txt because the file-writing tools failed."}}\n'
        '{"type":"turn.completed","usage":{"input_tokens":127154,"output_tokens":314}}\n'
    )

    def _llm_writes_nothing(facts, task_id, want):
        return 0, REAL          # 🔴 아무것도 안 쓰고 rc=0 — 그날의 상태 그대로

    with tempfile.TemporaryDirectory() as td:
        facts, bare, base, _w = _world(Path(td))
        c = _verified_run(facts, {"task_id": TASK}, work_id=WORK, base_commit=base,
                        want=[SRC], llm=_llm_writes_nothing, ssh=_shell, reader=_reader)
        check("막힌다 (골조가 그대로라 층1 이 잡는다)",
              not c.ok and c.layer1_violations, c.summary)
        notes = " | ".join(c.notes)
        check("🔴 지휘자가 한 말이 기록에 남는다",
              "file-writing tools failed" in notes, notes[:200])
        check("🔴 실패 원인 줄이 남는다 — 진짜 원인은 여기 있다",
              "pipe-in" in notes or "Rejected(" in notes, notes[:200])
        check("  누가 말했는지 표시한다", "[지휘자]" in notes, notes[:80])
        check("[중요] 커밋은 여전히 안 생긴다 (로그를 남긴다고 통과시키지 않는다)",
              not c.head, c.head)
        # `#764` 3a — codex 이벤트가 있는데 위임 명령이 없으면 「위임 없음」이 조각 기록에 남는다
        check("`#764` 위임 여부가 조각 기록에 남는다", "[지휘자] 위임 없음" in notes, notes[-200:])


def test_empty_body_blocks():
    with tempfile.TemporaryDirectory() as td:
        facts, bare, base, _w = _world(Path(td))
        c = _verified_run(facts, {"task_id": TASK}, work_id=WORK, base_commit=base,
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
        c = _verified_run(facts, {"task_id": TASK}, work_id=WORK, base_commit=base,
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
        c = _verified_run(f, task, **args)
        check(f"[중요] {name} → 아무것도 하지 않고 거절", not c.ok and c.stage == "입력", c.summary)


def test_llm_failure_does_not_commit():
    with tempfile.TemporaryDirectory() as td:
        facts, bare, base, _w = _world(Path(td))
        c = _verified_run(facts, {"task_id": TASK}, work_id=WORK, base_commit=base,
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
        c = _verified_run(facts, {"task_id": TASK}, work_id=WORK, base_commit=base,
                        want=[HDR], llm=lambda f, t, w: (0, "채울 것이 없다"),
                        ssh=_shell, reader=_reader, baseline=lambda p: KEEP_HDR)
        check("[중요] 실패가 아니다", c.ok, c.summary)
        check("  no_op 으로 표시한다", c.no_op, c.summary)
        check("  사유를 남기지 않는다", not c.reason, c.reason)
        check("  무엇이었는지 말한다", "[PSEUDO]" in c.summary and "0개" in c.summary, c.summary)


def test_layer2_commit_boundary():
    from master import layer2_verify as L2
    for label, verify in (
            ("reject", lambda files: L2.verify_files(list(files.items()), backends=[
                ("agy", lambda *a, **k: "- Unknown member\nVERDICT: REQUEST_CHANGES")], cooldown_sec=0)),
            ("invalid", lambda files: L2.verify_files(list(files.items()), backends=[
                ("agy", lambda *a, **k: "looks good")], cooldown_sec=0)),
            ("no_backend", lambda files: L2.verify_files(list(files.items()), backends=[], cooldown_sec=0)),
            ("exception", lambda files: (_ for _ in ()).throw(RuntimeError("backend failed"))),
            ("missing", None)):
        with tempfile.TemporaryDirectory() as td, patch.object(wcommit, "_log"):
            facts, bare, base, worker = _world(Path(td))
            c = wcommit.run(facts, {"task_id": TASK}, work_id=WORK, base_commit=base,
                            want=[SRC], llm=_llm_writes(GOOD), ssh=_shell, reader=_reader,
                            verifier=verify)
            check(f"층2 {label}: 커밋·push 차단", not c.ok and not c.head and
                  f"task/{WORK}/{TASK}" not in _heads(bare), c.summary)
            check(f"층2 {label}: finally main 복귀", c.stage == "층2" and
                  sh(worker, "git", "rev-parse", "--abbrev-ref", "HEAD") == "main", c.summary)
            if label == "reject":
                check("층2 지적·backend·원문 보존", c.layer2_findings == ["Unknown member"] and
                      "backend=agy" in " ".join(c.notes) and
                      "VERDICT: REQUEST_CHANGES" in " ".join(c.notes), str(c.notes))
    with tempfile.TemporaryDirectory() as td:
        facts, bare, base, worker = _world(Path(td))
        calls = []
        verify = lambda files: calls.append(files) or _approved(files)
        c = wcommit.run(facts, {"task_id": TASK}, work_id=WORK, base_commit=base,
                        want=[SRC], llm=_llm_writes({SRC: "// [PSEUDO] leftover\n"}),
                        ssh=_shell, reader=_reader, verifier=verify)
        check("층1 거절 때 층2 호출 0", not c.ok and calls == [], c.summary)
    with tempfile.TemporaryDirectory() as td:
        facts, bare, base, worker = _world(Path(td))
        verify = lambda files: L2.verify_files(list(files.items()), backends=[
            ("agy", lambda *a, **k: "VERDICT: APPROVE")], cooldown_sec=0)
        c = wcommit.run(facts, {"task_id": TASK}, work_id=WORK, base_commit=base,
                        want=[SRC], llm=_llm_writes(GOOD), ssh=_shell, reader=_reader,
                        verifier=verify)
        check("실제 verify_files Verdict 승인 뒤에만 원격 커밋", c.ok and
              _heads(bare).get(f"task/{WORK}/{TASK}") == c.head, c.summary)
    with tempfile.TemporaryDirectory() as td:
        facts, bare, base, worker = _world(Path(td))
        c = wcommit.run(facts, {"task_id": TASK}, work_id=WORK, base_commit=base,
                        want=[HDR], llm=lambda *a: (0, "unchanged"),
                        ssh=_shell, reader=_reader, baseline=lambda p: KEEP_HDR,
                        verifier=lambda files: Verdict(False, "no_backend"))
        check("no-op도 층2 우회 없음", not c.ok and not c.no_op and
              f"task/{WORK}/{TASK}" not in _heads(bare), c.summary)


def _racing_verifier(files):
    """`#818` 실측 증상을 흉내낸다 — 순회 중 크기가 바뀐 dict."""
    d = {"a": 1}
    for k in d:
        d[k + "x"] = 2


def test_layer2_exception_keeps_traceback():
    """🔴 `#818` — 층2 검증기 예외의 추적을 버리지 않는다.

    전체 추적은 파견 로그(`wcommit._log` → 저널)에 줄마다 태스크 id 를 붙여 남고,
    사유(`c.reason`)는 짧은 모양 그대로 **마지막 프레임**만 더 싣는다.
    """
    logs = []
    with tempfile.TemporaryDirectory() as td, \
            patch.object(wcommit, "_log", side_effect=logs.append):
        facts, bare, base, worker = _world(Path(td))
        c = wcommit.run(facts, {"task_id": TASK}, work_id=WORK, base_commit=base,
                        want=[SRC], llm=_llm_writes(GOOD), ssh=_shell, reader=_reader,
                        verifier=_racing_verifier)
        check("층2 예외: 커밋·push 차단", not c.ok and not c.head and
              f"task/{WORK}/{TASK}" not in _heads(bare), c.summary)
    check("층2 예외: verifier_exception 분류", c.layer2_failure == "verifier_exception",
          c.layer2_failure)
    check("층2 예외: 사유에 예외 원문", "RuntimeError: dictionary changed size during iteration"
          in c.reason, c.reason)
    check("층2 예외: 사유에 마지막 프레임(상대 경로:줄 in 함수)",
          " @ master/test_wcommit.py:" in c.reason and "in _racing_verifier" in c.reason
          and c.reason.endswith("— 커밋하지 않는다"), c.reason)
    check("층2 예외: 사유가 짧다(추적 전체를 싣지 않는다)", "Traceback" not in c.reason
          and "\n" not in c.reason and len(c.reason) < 300, c.reason)
    tb = [ln for ln in logs if ln.startswith(f"[wcommit] {TASK} 층2 예외 추적: ")]
    check("층2 예외: 추적이 로그로 — 줄마다 태스크 id", len(tb) >= 3 and len(tb) == len(logs) and
          "Traceback (most recent call last):" in tb[0] and
          "RuntimeError: dictionary changed size during iteration" in tb[-1], str(logs))
    check("층2 예외: 추적에 경합 자리(파일·함수)", any(
          "test_wcommit.py" in ln and "_racing_verifier" in ln for ln in tb), str(tb))


def main() -> int:
    for fn in (test_no_pseudo_and_no_change_is_a_no_op_not_a_failure,
               test_commands, test_returns_to_main, test_return_home_syncs_main_871,
               test_return_home_command_shape_871, test_worker_keeps_nothing,
               test_happy_path, test_collects_delegations,
               test_collect_delegations_continues_after_failure, test_layer1_blocks_commit,
               test_layer1_block_records_what_the_conductor_said,
               test_empty_body_blocks, test_no_change_is_not_success,
               test_refusals, test_llm_failure_does_not_commit, test_layer2_commit_boundary,
               test_layer2_exception_keeps_traceback):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_wcommit: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
