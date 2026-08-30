"""git-carried 매니페스트 배달 (#185) 계약 테스트.

재는 것 다섯 (git 실물 — SSH/LLM 0):
    ① publish       durable `task/<id>` 신설·적재, `.gitignore` 아래서도 `add -f` 로 실림
    ② 멱등          같은 본문 재-publish = 커밋 0 · 바뀐 본문 = tip 위에 새 커밋
    ③ 실체화        **실제 워커 클론**에서 materialize 명령이 돌아 파일이 생기고 blob 대조 통과
    ④ fail-closed   blob 불일치·rc≠0·기준 상실 — 전부 예외/오류, 조용한 폴백 없음
    ⑤ 배선          poster 주입(테스트) 등록은 git 을 안 만진다 · carrier 주입이 호출된다

실행: .venv/bin/python master/test_carry.py
"""
from __future__ import annotations

import subprocess
import pathlib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# [중요] `#319` — 조각 durable 은 `task/<work_id>/<task_id>` 다. work_id 가 이름의 한 칸이다.
W = "w1"

from master.work import carry as C                              # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def g(cwd, *args):
    r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                        "-c", "commit.gpgsign=false", "-C", str(cwd), *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()[:200]}")
    return r.stdout.strip()


class P:
    def __init__(self, root: Path):
        self.root = root
        self.repo = root / "repo"


class Facts:
    def __init__(self, path, windows=False):
        self.path = str(path)
        self.windows = windows
        self.host = "테스트호스트"
        self.user = "t"


def fixture():
    """정본 클론 + bare 원격(gitea-write) + 워커 클론. base 커밋 1개."""
    root = Path(tempfile.mkdtemp(prefix="ax-carry-"))
    p = P(root)
    bare = root / "gitea.git"
    g(root, "init", "--bare", "-q", str(bare))
    p.repo.mkdir()
    g(p.repo, "init", "-q", "-b", "main")
    (p.repo / ".gitignore").write_text(".ax/\n", encoding="utf-8")   # 원전 함정 재현
    (p.repo / "Source").mkdir()
    (p.repo / "Source" / "A.cpp").write_text("int F(){return 1;}\n", encoding="utf-8")
    g(p.repo, "add", "-A")
    g(p.repo, "commit", "-q", "-m", "base")
    g(p.repo, "remote", "add", "gitea-write", str(bare))
    g(p.repo, "push", "-q", "gitea-write", "main")
    worker = root / "worker"
    g(root, "clone", "-q", str(bare), str(worker))
    # [중요] **쓰기 가드를 세운다** (`#329`) — `publish` 가 push 직전에 확인하고, 없으면
    #    fail-closed 로 막는다. 실전 클론에는 있으므로 픽스처도 같게 둔다.
    #    [주의] 이 줄이 없으면 `publish` 가 (옳게) 거부한다 — 그것 자체가 게이트의 증거다.
    from master.work.attempt import install_hook
    install_hook(p)
    return p, bare, worker, g(p.repo, "rev-parse", "HEAD")


BODY = "# 매니페스트\n\n## 대상 파일\n- Source/A.cpp\n"


def test_publish_refuses_without_guard():
    """[중요] `#329` — 쓰기 가드가 없으면 **push 하지 않는다** (fail-closed).

    실측 2026-08-28: `git lfs install` 이 NS 클론의 훅을 덮어 가드가 통째로 사라졌는데
    **아무 표면도 말하지 않았다.** 이제 미는 자리에서 막는다.
    """
    p, bare, worker, base = fixture()
    from master.work.attempt import hook_target
    # ① 아예 없을 때
    hook_target(p).unlink()
    r = C.publish(p, W, "t-g1", BODY, base_commit=base)
    check("[중요] 가드가 없으면 거부한다", not r.ok and "가드가 서 있지 않다" in (r.error or ""),
          r.error)
    check("  복구 방법을 사유에 적는다", "install-hook" in (r.error or ""), r.error)
    # ② 남의 훅이 덮었을 때 (LFS 가 그랬다)
    hook_target(p).write_text("#!/bin/sh\ngit lfs pre-push \"$@\"\n", encoding="utf-8")
    r2 = C.publish(p, W, "t-g2", BODY, base_commit=base)
    check("[중요] 남의 훅이 덮어도 거부한다", not r2.ok and "가드가 서 있지 않다" in (r2.error or ""),
          r2.error)
    check("  「우리 가드가 아니다」라고 말한다", "우리 가드가 아니다" in (r2.error or ""), r2.error)
    # ③ 낡았을 뿐이면 **막지 않는다** — 우리 가드가 맞고 지금 막고 있다
    from master.work.attempt import HOOK_SOURCE
    hook_target(p).write_text(HOOK_SOURCE.read_text(encoding="utf-8") + "\n# 낡은 사본\n",
                              encoding="utf-8")
    hook_target(p).chmod(0o755)
    r3 = C.publish(p, W, "t-g3", BODY, base_commit=base)
    check("[주의] 낡았을 뿐이면 막지 않는다 (우리 가드가 맞다)", r3.ok, r3.error)


# ── ① publish + ② 멱등 ──────────────────────────────────────

def test_publish_and_idempotency():
    p, bare, worker, base = fixture()
    logs = []
    pub = C.publish(p, W, "t-1", BODY, base_commit=base, logf=logs.append)
    check("[중요] publish 성공 — 조각 durable 신설 (계층형, #319)", pub.ok and pub.created
          and pub.durable == f"task/{W}/t-1", pub.error)
    check("[중요] .gitignore 아래서도 실린다 (add -f — 원전 함정)",
          g(p.repo, "ls-remote", "--heads", str(bare), f"refs/heads/task/{W}/t-1") != "")
    remote_file = g(p.repo, "show", f"{pub.head}:.ax/tasks/t-1/context.md")
    check("본문이 커밋에 그대로", remote_file == BODY.rstrip("\n"), remote_file[:50])
    check("원전 커밋 메시지 그대로", "skeleton context manifest for t-1" in
          g(p.repo, "log", "-1", "--format=%s", pub.head))
    check("worktree 잔재가 없다", not (p.root / "ax-carry-t-1").exists())

    pub2 = C.publish(p, W, "t-1", BODY, base_commit=base)
    check("[중요] 같은 본문 재-publish = 커밋 없음 (멱등 — 파견 루프가 매번 불러도 안전)",
          pub2.ok and pub2.skipped and pub2.head == pub.head, pub2.skipped or pub2.error)
    check("blob 은 동일", pub2.blob == pub.blob)

    pub3 = C.publish(p, W, "t-1", BODY + "\n## 갱신\nbase 가 바뀌었다\n", base_commit=base)
    check("[중요] 바뀐 본문 = durable tip **위에** 새 커밋 (이력 보존)",
          pub3.ok and not pub3.skipped and
          g(p.repo, "rev-parse", f"{pub3.head}^") == pub.head, pub3.error)


# ── ③ 실체화 — 실제 워커 클론 왕복 ───────────────────────────

def test_materialize_real_roundtrip():
    p, bare, worker, base = fixture()
    pub = C.publish(p, W, "t-2", BODY, base_commit=base)
    f = Facts(worker, windows=False)

    def sh(facts, cmd, timeout):
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True,
                           encoding="utf-8", timeout=timeout)
        return r.returncode, r.stdout + r.stderr

    got = C.materialize(f, W, "t-2", expect_blob=pub.blob, runner_=sh)
    check("[중요] 실 클론 왕복 — fetch → show → 파일 실체화 → blob 대조 통과",
          got == pub.blob)
    mat = (worker / ".ax" / "work" / "t-2" / "manifest.md").read_text(encoding="utf-8")
    check("[중요] 경로·내용이 scp 시절과 동일 (소비 형식 불변 — 운송만 바뀐다)", mat == BODY)
    check("워커에 브랜치를 만들지 않는다 (임시 ref 만)",
          "task/t-2" not in g(worker, "branch", "--list", "task/t-2"))

    # refresh 후 재배달 — 새 blob 이 실체화된다
    pub2 = C.publish(p, W, "t-2", BODY + "갱신\n", base_commit=base)
    got2 = C.materialize(f, W, "t-2", expect_blob=pub2.blob, runner_=sh)
    check("갱신본 재실체화", got2 == pub2.blob and
          "갱신" in (worker / ".ax" / "work" / "t-2" / "manifest.md").read_text(encoding="utf-8"))


# ── ④ fail-closed ────────────────────────────────────────────

def test_fail_closed():
    p, bare, worker, base = fixture()
    pub = C.publish(p, W, "t-3", BODY, base_commit=base)
    f = Facts(worker)

    try:
        C.materialize(f, W, "t-3", expect_blob="0" * 40,
                      runner_=lambda ft, c, t: (0, pub.blob + "\n"))
        check("[중요] blob 불일치는 예외 (전송을 신뢰하지 않는다)", False)
    except C.CarryError as e:
        check("[중요] blob 불일치는 예외 (전송을 신뢰하지 않는다)", "다르다" in str(e))
    try:
        C.materialize(f, W, "t-3", expect_blob=pub.blob, runner_=lambda ft, c, t: (1, "죽음"))
        check("rc≠0 은 예외", False)
    except C.CarryError:
        check("rc≠0 은 예외", True)
    try:
        C.materialize(f, W, "t-3", expect_blob=pub.blob, runner_=lambda ft, c, t: (0, "sha아님"))
        check("sha 를 못 읽으면 예외", False)
    except C.CarryError:
        check("sha 를 못 읽으면 예외", True)
    try:
        C.materialize(f, W, "t-3", expect_blob="")
        check("[중요] 기대 blob 없이 실체화하지 않는다", False)
    except C.CarryError:
        check("[중요] 기대 blob 없이 실체화하지 않는다", True)

    check("빈 본문은 publish 오류", not C.publish(p, W, "t-4", "  ", base_commit=base).ok)
    check("[중요] 기준 커밋도 durable 도 없으면 오류 (어디에 얹을지 모른 채 커밋 금지)",
          "기준 커밋" in C.publish(p, W, "t-5", BODY, base_commit="").error)
    check("브랜치명이 못 되는 task_id 는 오류", not C.publish(p, W, "t 5", BODY, base_commit="x").ok)


# ── 명령 모양 (양 OS) ─────────────────────────────────────────

def test_base_commit_missing_locally():
    """[중요] **미러에 base 커밋이 없으면 가져온다** (`#341`, 실측 2026-08-30).

    첫 실전 파견이 여기서 죽었다:

        git worktree add --detach --force …/ax-carry-0c98a727 953587343eda…
        fatal: 잘못된 레퍼런스: 953587343eda…

    `.33` 이 gitea 에 골조를 push 했는데 **마스터 미러가 fetch 를 안 했다.** durable 갈래는
    위에서 fetch 하는데 base 갈래는 `#319` 때 빠뜨렸다 — **첫 조각은 durable 이 없어 반드시
    이리 온다.**
    [주의] `twin_base.resolve()` 는 bare 를 직접 읽어 `exists=True` 를 냈다. carry 는 미러의
    로컬 객체를 쓴다 — 둘이 보는 곳이 달라 「있다고 했는데 없다」가 됐다.
    """
    print("\n[base fetch] 미러에 기준 커밋이 없으면 가져온다 (#341)")
    p, bare, worker, base = fixture()

    check("[중요] 로컬에 있으면 그대로 쓴다 (fetch 안 한다)",
          C._has_commit(pathlib.Path(p.repo), base))
    check("없는 sha 는 False", not C._has_commit(pathlib.Path(p.repo), "0" * 40))
    check("빈 sha 는 False", not C._has_commit(pathlib.Path(p.repo), ""))

    # 미러가 모르는 커밋 → base 브랜치도 원격에 없다 → 사유를 말하고 멈춘다
    got = C.publish(p, W, "t-nofetch", BODY, base_commit="0" * 40)
    check("[중요] 기준 커밋이 없으면 조용히 넘어가지 않는다", not got.ok, str(got.error)[:120])
    check("  사유가 기준 커밋과 base 브랜치를 둘 다 말한다",
          "기준 커밋" in got.error and "base" in got.error.lower(), got.error[:160])


def test_command_shapes():
    win = C.materialize_command(Facts(r"C:\Users\u\Documents\MS", windows=True), W, "t-9")
    check("[중요] 윈도우 모양 — cd /d · 역슬래시 · mkdir 가드",
          'cd /d "C:\\Users\\u\\Documents\\MS"' in win and ".ax\\work\\t-9" in win
          and "if not exist" in win, win[:120])
    lin = C.materialize_command(Facts("/home/sim/trunk/MS"), W, "t-9")
    check("리눅스 모양 — mkdir -p · 슬래시", "mkdir -p" in lin and ".ax/work/t-9" in lin)
    for cmd in (win, lin):
        check("fetch→show→hash-object 사슬", "git fetch origin" in cmd
              and "git --no-pager show" in cmd and "git hash-object" in cmd)
        check("stdout 을 건너는 것은 sha 뿐 (CP949 함정 회피)", cmd.rstrip().endswith('"')
              or cmd.rstrip().endswith("hash-object \".ax/work/t-9/manifest.md\""))


# ── ⑤ 등록 배선 ──────────────────────────────────────────────

def test_register_wiring():
    from master.work import register as REG
    calls = []

    def poster(url, payload):
        if url.endswith("/works"):
            return {"work_id": "w-1"}
        return {"task_id": f"t-{len(calls)}"}

    class Paths:
        root = Path(tempfile.mkdtemp(prefix="ax-cw-"))
        repo = root / "repo"
        name = "테스트"
        ontology = root / "ontology"

    spec = REG.TaskSpec(stem="a", target_file="Source/A.cpp", header_file="Source/A.h",
                        classes=["A"], skeleton="int F();")
    fake_mf_calls = []

    class FakeM:
        body = BODY
        base_commit = "abc123"
        hits = 0
        degraded = []

    import master.work.manifest as mf
    orig_build, orig_write = mf.build, mf.write
    mf.build = lambda *a, **k: FakeM()
    mf.write = lambda paths, m: "/tmp/x.md"
    try:
        got = REG.register_work("제목", [spec], paths=Paths(), target_repo="r",
                                poster=poster, searcher=object(), make_skeleton=lambda *a, **k: "",
                                carrier=lambda paths, wid, tid, body, *, base_commit:
                                    fake_mf_calls.append((wid, tid, body, base_commit)) or
                                    type("X", (), {"ok": True, "head": "h1", "error": ""})())
        # [중요] `#319` — carrier 는 work_id 도 받는다. 조각 durable 이 `task/<W>/<T>` 라서다.
        check("[중요] carrier 가 태스크마다 불린다 (work_id·본문·base 동반)",
              fake_mf_calls == [("w-1", "t-0", BODY, "abc123")], str(fake_mf_calls))
        check("carried_head 가 결과에 실린다", got.tasks[0].carried_head == "h1")

        got2 = REG.register_work("제목", [REG.TaskSpec(stem="b", target_file="Source/B.cpp",
                                                     header_file="Source/B.h", classes=["B"],
                                                     skeleton="int G();")],
                                 paths=Paths(), target_repo="r", poster=poster,
                                 searcher=object(), make_skeleton=lambda *a, **k: "")
        check("[중요] poster 주입(테스트) 등록은 git 을 안 만진다 (carrier=None 자동)",
              got2.tasks[0].carried_head == "" and got2.tasks[0].carried_error == "")
    finally:
        mf.build, mf.write = orig_build, orig_write


def test_carry_failure_is_loud():
    """[중요] carry 실패가 **사람 화면에 찍혀야** 한다 (리포트 39 지적).

    등록은 성립하지만 파견은 fail-closed 로 막힌다 — 그 사실이 등록 응답에 없으면
    요청자 세션이 「성공」으로 읽고 다음 단계로 간다.
    """
    from master.work import register as REG
    ok = REG.TaskResult(stem="a", task_id="t-0", carried_head="h1")
    bad = REG.TaskResult(stem="b", task_id="t-1", carried_error="pre-push 훅이 막았다")
    got = REG.Registered(work_id="w-1", tasks=[ok, bad])
    s = got.summary()
    check("[중요] carry 실패 건수를 말한다", "carry 실패 1건" in s, s)
    check("[중요] 파견이 막힌다고 말한다", "파견이 막힌다" in s, s)
    check("어느 태스크인지 말한다", "t-1" in s, s)
    check("사유를 말한다", "pre-push" in s, s)
    clean = REG.Registered(work_id="w-1", tasks=[ok]).summary()
    check("성공만이면 그 절이 없다", "carry 실패" not in clean, clean)


def main() -> int:
    for fn in (test_publish_and_idempotency, test_materialize_real_roundtrip,
               test_fail_closed, test_base_commit_missing_locally,
               test_command_shapes, test_register_wiring,
               test_carry_failure_is_loud,
               test_publish_refuses_without_guard):
        fn()
    print(f"{'OK' if not FAIL else '[실패]'} test_carry: {PASS}/{PASS + FAIL} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
