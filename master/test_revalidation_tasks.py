"""`#840` T1 — 표시된 조각의 클라우드 재생성 → **별도 후보 브랜치**. 실제 git + 실제 pre-push 훅.

임시 bare 원격 + 클론에 `gitea-write` remote 를 달고 `attempt.install_hook` 으로 원본 훅을
설치한다. LLM 은 가짜 생성기(`generator(prompt, lane)`)뿐이다 — 실제 CLI·브로커 호출 없음.

    ① 성공 — 후보 브랜치 내용·부모(base) · 조각/작업 브랜치 불변 · 표시 유지 + 후보 기록 · 재실행 0호출
    ② agy 형식 실패 → codex · 층1 위반 → 다음 클라우드
    ③ 클라우드 전부 실패 → 후보 없음 · 표시 유지 · 로컬 레인 0회
    ④ agy·codex 한도 → claude 허용 · 세 클라우드 한도 → 로컬 없이 종료
    ⑤ 조각 tip 변경 → LLM 0 · 후보가 이미 있음 → 덮어쓰지 않고 기록만 · LLM 0
    ⑥ work 닫힘 / 확인 예외 / metadata 불완전 → LLM 0
    ⑦ 쓰기 가드 없음 → LLM 0 · push 0
    ⑧ limit = 실제 호출 수 · 가장 오래 안 본 것부터
    ⑨ push 실패(그새 생긴 후보) → 덮어쓰지 않음 · worktree 는 지운다
    ⑩ 정산(T2, LLM 0) — 채택→해제 · 후보 삭제+열림→후보 뗌(다음 주기 재생성) ·
       삭제+닫힘→유지 · fetch 실패/work 조회 예외→무변경 · 대기→유지 · dry-run 무기록

`.venv/bin/python master/test_revalidation_tasks.py`
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import attempt as A                              # noqa: E402
from master.work import branch_names as B                          # noqa: E402
from master.work import revalidation as R                          # noqa: E402

PASS = FAIL = 0
TMPS: list = []
REMOTE = "gitea-write"
W = "20261103_0100_reval_aaaa1111"
CLOUDS = ("agy", "codex", "claude")

SKEL = ("// [DOC] adds two numbers\n"
        "int {name}(int a, int b)\n"
        "{{\n"
        "    // [PSEUDO] return the sum\n"
        "    return 0;\n"
        "}}\n")
LOCAL_BODY = "// [DOC] adds two numbers\nint {name}(int a, int b)\n{{\n    return a+b; // local\n}}\n"
CLOUD_BODY = "// [DOC] adds two numbers\nint {name}(int a, int b)\n{{\n    return a + b; // {lane}\n}}\n"


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _run(cwd: Path, *args: str, ok=True) -> tuple:
    r = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(cwd), *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if ok and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} rc={r.returncode}: {r.stderr}")
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


@dataclass
class Paths:
    root: Path
    name: str = "Proj"

    @property
    def repo(self) -> Path:
        return self.root / "repo"


class Fx:
    """bare 원격 · 클론 · 작업 브랜치(골조) · 조각 브랜치(로컬 생성 커밋) · 재검증 표시."""

    def __init__(self, tmp: Path, tasks=("T1",)):
        self.tmp = tmp
        self.origin = tmp / "origin.git"
        self.paths = Paths(root=tmp / "proj")
        self.paths.root.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.paths.repo)], check=True,
                       stderr=subprocess.DEVNULL)
        self.repo = self.paths.repo
        _run(self.repo, "remote", "add", REMOTE, str(self.origin))
        self.commit({"README": "x\n"}, "init")
        _run(self.repo, "push", "-q", REMOTE, "HEAD:refs/heads/main")
        self.skeleton = {f"Source/{t}.cpp": SKEL.format(name=t) for t in tasks}
        self.base = self.commit(self.skeleton, "skeleton")
        _run(self.repo, "push", "-q", REMOTE, f"{self.base}:refs/heads/{B.base_branch(W)}")
        self.heads = {}
        for t in tasks:
            _run(self.repo, "checkout", "-q", "--detach", self.base)
            head = self.commit({f"Source/{t}.cpp": LOCAL_BODY.format(name=t)}, f"local {t}")
            _run(self.repo, "push", "-q", REMOTE, f"{head}:refs/heads/{B.durable_branch(W, t, 1)}")
            self.heads[t] = head
            R.mark(self.paths.root, "task", t, fingerprint=f"fp-{t}", metadata=self.metadata(t))
        _run(self.repo, "checkout", "-q", "--detach", self.base)
        A.install_hook(self.paths)

    def metadata(self, t):
        rel = f"Source/{t}.cpp"
        return dict(needs_revalidation=True, model="qwen2.5-coder:14b",
                    provenance=[{"lane": n, "kind": "quota"} for n in CLOUDS],
                    skeleton={rel: self.skeleton[rel]}, prompt="p", work_id=W, task_id=t,
                    round=1, base_commit=self.base, checkout_commit=self.base,
                    branch=B.durable_branch(W, t, 1), head_commit=self.heads[t],
                    want=[rel], files={rel: LOCAL_BODY.format(name=t)})

    def head(self) -> str:
        return _run(self.repo, "rev-parse", "HEAD")[1]

    def commit(self, files: dict, msg: str) -> str:
        for rel, text in files.items():
            p = self.repo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        _run(self.repo, "add", "-A")
        _run(self.repo, "commit", "-q", "-m", msg)
        return self.head()

    def remote_refs(self) -> dict:
        out = _run(self.repo, "ls-remote", "--heads", REMOTE)[1]
        return {ln.split()[1][len("refs/heads/"):]: ln.split()[0]
                for ln in out.splitlines() if len(ln.split()) == 2}

    def record(self, t):
        return next((e for e in R.pending(self.paths.root) if e["key"] == t), None)

    def stray_trees(self):
        dirs = [p.name for p in self.paths.root.iterdir() if p.name.startswith("ax-revalidate-")]
        listed = _run(self.repo, "worktree", "list", "--porcelain")[1].count("worktree ")
        return dirs, listed


class Gen:
    """가짜 생성기. `plan[lane]` = ok · format · facts · quota · error. 호출 레인을 센다."""

    def __init__(self, plan=None, default="ok", on_call=None):
        self.plan, self.default, self.on_call = plan or {}, default, on_call
        self.calls = []

    def __call__(self, prompt, lane):
        self.calls.append(lane)
        if self.on_call:
            self.on_call(lane)
        mode = self.plan.get(lane, self.default)
        files = [ln[len("=== FILE: "):-4] for ln in prompt.splitlines()
                 if ln.startswith("=== FILE: ") and ln.endswith(" ===")]
        if mode == "quota":
            raise RuntimeError("quota exhausted for this account")
        if mode == "error":
            raise RuntimeError("connection reset")
        if mode == "format":
            return "Sure! here is some prose without blocks"
        out = []
        for rel in files:
            name = Path(rel).stem
            body = (SKEL.format(name=name) if mode == "facts"
                    else CLOUD_BODY.format(name=name, lane=lane))
            out += [f"=== FILE: {rel} ===", body]
        return "\n".join(out)


def run(fx, gen, **kw):
    logs = []
    kw.setdefault("work_open", lambda wid: True)
    res = R.run_tasks(fx.paths, generator=gen, logf=logs.append, **kw)
    return res, logs


def no_local(gen):
    return all(lane in CLOUDS for lane in gen.calls)


def scenario(title):
    print(f"── {title}")
    TMPS.append(Path(tempfile.mkdtemp(prefix="reval-tasks-")))
    return TMPS[-1]


def t_success():
    fx = Fx(scenario("① 성공"))
    before = fx.remote_refs()
    gen = Gen()
    res, logs = run(fx, gen)
    cand = B.candidate_branch(W, "T1", 1)
    refs = fx.remote_refs()
    check("① ok", res["ok"] and res["calls"] == 1, str(res))
    check("① agy 한 번만", gen.calls == ["agy"], str(gen.calls))
    check("① 후보 브랜치 생성", cand in refs and cand == f"task/{W}/r1/T1-cloud", str(refs))
    check("① 조각·작업 브랜치 불변",
          all(refs.get(k) == v for k, v in before.items()), f"{before} vs {refs}")
    _run(fx.repo, "fetch", "-q", REMOTE, cand)
    body = _run(fx.repo, "show", f"{refs[cand]}:Source/T1.cpp")[1]
    check("① 후보 내용 = 클라우드 본문", "return a + b; // agy" in body and "[PSEUDO]" not in body, body)
    parent = _run(fx.repo, "rev-parse", f"{refs[cand]}^")[1]
    check("① 후보 부모 = base_commit", parent == fx.base, parent)
    msg = _run(fx.repo, "log", "-1", "--format=%B", refs[cand])[1]
    check("① 커밋 메시지", "#840" in msg and "T1" in msg and "lane=agy" in msg
          and "cloud revalidation candidate" in msg, msg)
    rec = fx.record("T1")
    check("① 표시 유지 + 후보 기록", rec is not None and rec["needs_revalidation"] is True
          and rec["candidate"]["branch"] == cand and rec["candidate"]["head"] == refs[cand]
          and rec["candidate"]["lane"] == "agy"
          and rec["candidate"]["provenance"][-1] == {"lane": "agy", "kind": "success"}, str(rec))
    check("① worktree 정리", fx.stray_trees() == ([], 1), str(fx.stray_trees()))
    check("① 실제 훅이 서 있었다", A.hook_status(fx.paths)["state"] == A.STATE_OK)
    check("① 로그 — 시작·생성·push·기록",
          all(any(k in ln for ln in logs) for k in ("T1 시작", "층1 통과", "push", "기록")), "\n".join(logs))
    gen2 = Gen()
    res2, _ = run(fx, gen2)
    check("① 재실행 — 호출 0 · 채택 대기 1", gen2.calls == [] and res2["waiting"] == 1
          and res2["entries"] == 0, str(res2))


def t_next_cloud():
    fx = Fx(scenario("② 형식 실패 → codex"))
    gen = Gen({"agy": "format"})
    res, _ = run(fx, gen)
    rec = fx.record("T1")
    check("② agy→codex", gen.calls == ["agy", "codex"] and res["ok"], f"{gen.calls} {res}")
    check("② 후보 lane=codex", rec["candidate"]["lane"] == "codex"
          and rec["candidate"]["provenance"][0]["kind"] == "format", str(rec))
    fx = Fx(scenario("② 층1 위반 → 다음 클라우드"))
    gen = Gen({"agy": "facts"})
    res, logs = run(fx, gen)
    check("② 층1 위반 agy → codex 성공", gen.calls == ["agy", "codex"] and res["ok"]
          and fx.record("T1")["candidate"]["provenance"][0]["kind"] == "facts", f"{gen.calls} {res}")
    check("② 층1 위반 로그", any("층1 위반" in ln for ln in logs), "\n".join(logs))


def t_all_fail():
    fx = Fx(scenario("③ 클라우드 전부 실패"))
    gen = Gen(default="format")
    res, logs = run(fx, gen, limit=10)
    rec = fx.record("T1")
    check("③ claude 미개방(한도 아님) · 로컬 0", gen.calls == ["agy", "codex"] and no_local(gen),
          str(gen.calls))
    check("③ 후보 없음 · 표시 유지", not res["ok"] and "candidate" not in rec
          and rec["needs_revalidation"] is True, f"{res} {rec}")
    check("③ 원격 후보 없음", B.candidate_branch(W, "T1", 1) not in fx.remote_refs())
    check("③ 실패 로그", any("후보 없음" in ln for ln in logs), "\n".join(logs))


def t_quota():
    fx = Fx(scenario("④ agy·codex 한도 → claude"))
    gen = Gen({"agy": "quota", "codex": "quota"})
    res, _ = run(fx, gen, limit=5)
    check("④ claude 허용", gen.calls == ["agy", "codex", "claude"] and res["ok"]
          and fx.record("T1")["candidate"]["lane"] == "claude", f"{gen.calls} {res}")
    fx = Fx(scenario("④ 세 클라우드 한도 → 로컬 없음"))
    gen = Gen(default="quota")
    res, _ = run(fx, gen, limit=10)
    check("④ 로컬 0 · 후보 없음", gen.calls == list(CLOUDS) and no_local(gen) and not res["ok"]
          and "candidate" not in fx.record("T1"), f"{gen.calls} {res}")


def t_piece_and_existing():
    fx = Fx(scenario("⑤ 조각 tip 변경"))
    _run(fx.repo, "checkout", "-q", "--detach", fx.heads["T1"])
    moved = fx.commit({"Source/T1.cpp": "// human fix\n"}, "moved")
    _run(fx.repo, "push", "-q", REMOTE, f"{moved}:refs/heads/{B.durable_branch(W, 'T1', 1)}")
    gen = Gen()
    res, _ = run(fx, gen)
    out = res["outcomes"][0]
    check("⑤ tip 변경 → LLM 0 · 건너뜀", gen.calls == [] and out.get("skipped")
          and "바뀌었다" in out["reason"] and fx.record("T1")["needs_revalidation"], str(res))
    check("⑤ 후보 미생성", B.candidate_branch(W, "T1", 1) not in fx.remote_refs())

    fx = Fx(scenario("⑤ 후보 이미 있음"))
    cand = B.candidate_branch(W, "T1", 1)
    _run(fx.repo, "checkout", "-q", "--detach", fx.base)
    pre = fx.commit({"Source/T1.cpp": "// earlier candidate\n"}, "earlier")
    _run(fx.repo, "push", "-q", REMOTE, f"{pre}:refs/heads/{cand}")
    gen = Gen()
    res, _ = run(fx, gen)
    rec = fx.record("T1")
    check("⑤ 기존 후보 — LLM 0 · 덮어쓰지 않음", gen.calls == [] and fx.remote_refs()[cand] == pre,
          str(res))
    check("⑤ 기존 후보 기록 반영", rec["candidate"]["head"] == pre and rec["candidate"]["recovered"]
          and rec["needs_revalidation"] is True, str(rec))


def t_work_state():
    fx = Fx(scenario("⑥ work 닫힘 · 확인 실패 · metadata 불완전"))
    gen = Gen()
    res, _ = run(fx, gen, work_open=lambda wid: False)
    check("⑥ 닫힌 work → LLM 0", gen.calls == [] and "열려 있지 않다" in res["outcomes"][0]["reason"],
          str(res))

    def boom(wid):
        raise ConnectionError("queue down")
    res, _ = run(fx, gen, work_open=boom)
    check("⑥ 확인 예외 → LLM 0 (fail-closed)", gen.calls == []
          and "확인 실패" in res["outcomes"][0]["reason"], str(res))
    res, _ = run(fx, gen, work_open=lambda wid: None)
    check("⑥ 모르는 응답(None) → 건너뜀", gen.calls == [] and res["outcomes"][0].get("skipped"), str(res))
    meta = fx.metadata("T1")
    del meta["head_commit"]
    R.mark(fx.paths.root, "task", "T1", fingerprint="fp-broken", metadata=meta)
    res, _ = run(fx, gen)
    check("⑥ metadata 불완전 → LLM 0", gen.calls == []
          and "head_commit" in res["outcomes"][0]["reason"], str(res))
    meta = fx.metadata("T1")
    meta["branch"] = f"task/{W}/r2/T1"
    R.mark(fx.paths.root, "task", "T1", fingerprint="fp-branch", metadata=meta)
    res, _ = run(fx, gen)
    check("⑥ branch 규약 불일치 → LLM 0", gen.calls == [] and "규약" in res["outcomes"][0]["reason"],
          str(res))
    check("⑥ 모든 경우 원격 후보 없음", B.candidate_branch(W, "T1", 1) not in fx.remote_refs())


def t_guard():
    fx = Fx(scenario("⑦ 쓰기 가드 없음"))
    A.hook_target(fx.paths).unlink()
    gen = Gen()
    res, _ = run(fx, gen)
    check("⑦ 가드 없음 → LLM 0 · push 0", gen.calls == [] and "쓰기 가드" in res["outcomes"][0]["reason"]
          and B.candidate_branch(W, "T1", 1) not in fx.remote_refs(), str(res))


def t_limit():
    fx = Fx(scenario("⑧ limit = 호출 수"), tasks=("T1", "T2"))
    gen = Gen({"agy": "format"})
    res, logs = run(fx, gen, limit=2)
    check("⑧ 2호출에서 멈춤", gen.calls == ["agy", "codex"] and res["calls"] == 2
          and res["entries"] == 1, f"{gen.calls} {res}")
    check("⑧ 예산 소진 로그", any("예산" in ln for ln in logs), "\n".join(logs))
    fx = Fx(scenario("⑧ 예산 중간 소진 · 오래 안 본 것부터"), tasks=("T1", "T2"))
    gen = Gen({"agy": "format"})
    res, _ = run(fx, gen, limit=1)
    first = res["outcomes"][0]
    check("⑧ 사슬 중간 예산 소진 → 후보 없음", gen.calls == ["agy"] and first["key"] == "T1"
          and "예산" in first["reason"] and "candidate" not in fx.record("T1"), str(res))
    gen = Gen()
    res, _ = run(fx, gen, limit=1)
    check("⑧ 다음 주기는 T2 먼저", res["outcomes"][0]["key"] == "T2" and res["ok"]
          and gen.calls == ["agy"], str(res))
    res, _ = run(fx, Gen(), limit=0)
    check("⑧ limit=0 → 대상 0", res["entries"] == 0 and res["calls"] == 0, str(res))


def t_race():
    fx = Fx(scenario("⑨ push 실패 — 그새 생긴 후보"))
    cand = B.candidate_branch(W, "T1", 1)
    other = fx.tmp / "other"
    subprocess.run(["git", "clone", "-q", str(fx.origin), str(other)], check=True)
    state = {}

    def sneak(lane):
        _run(other, "checkout", "-q", "--detach", fx.base)
        (other / "Source/T1.cpp").write_text("// someone else\n", encoding="utf-8")
        _run(other, "commit", "-q", "-am", "racer")
        state["tip"] = _run(other, "rev-parse", "HEAD")[1]
        _run(other, "push", "-q", "origin", f"HEAD:refs/heads/{cand}")
    gen = Gen(on_call=sneak)
    res, logs = run(fx, gen)
    out = res["outcomes"][0]
    check("⑨ push 거절 — 덮어쓰지 않음", fx.remote_refs()[cand] == state["tip"] and not out["ok"]
          and "push 실패" in out["reason"], str(res))
    check("⑨ 표시 유지 · 후보 미기록", "candidate" not in fx.record("T1"))
    check("⑨ worktree 정리(실패에도)", fx.stray_trees() == ([], 1), str(fx.stray_trees()))


def t_names():
    print("── branch_names.candidate_branch")
    check("이름 r1", B.candidate_branch("W1", "T1", 1) == "task/W1/r1/T1-cloud")
    check("이름 r0", B.candidate_branch("W1", "T1") == "task/W1/T1-cloud")
    try:
        B.candidate_branch("W1", "base", 1)
        check("예약어 거절", False)
    except B.BranchNameError:
        check("예약어 거절", True)
    check("review 정확 이름과 다름", B.candidate_branch("W1", "T1", 2) != B.durable_branch("W1", "T1", 2))


def t_set_candidate():
    print("── set_candidate CAS")
    root = Path(tempfile.mkdtemp(prefix="reval-cas-"))
    TMPS.append(root)
    R.mark(root, "task", "t", fingerprint="one", metadata={})
    check("CAS 불일치 거절", not R.set_candidate(root, "task", "t", fingerprint="zzz",
                                             candidate={"branch": "b"}))
    check("CAS 일치 반영", R.set_candidate(root, "task", "t", fingerprint="one",
                                         candidate={"branch": "b"}))
    rec = R.pending(root)[0]
    check("표시 유지", rec["needs_revalidation"] is True and rec["candidate"] == {"branch": "b"})
    R.mark(root, "task", "t", fingerprint="two", metadata={})
    check("재표시(새 지문)는 후보를 비운다", "candidate" not in R.pending(root)[0])


def settle(fx, **kw):
    logs = []
    kw.setdefault("work_open", lambda wid: True)
    res = R.settle_tasks(fx.paths, logf=logs.append, **kw)
    return res, logs


def _with_candidate(title):
    fx = Fx(scenario(title))
    res, _ = run(fx, Gen())
    assert res["ok"], res
    return fx, fx.record("T1")


def _raw(fx):
    return (fx.paths.root / "revalidation" / "records.json").read_text(encoding="utf-8")


def t_settle_adopted():
    fx, rec = _with_candidate("⑩ 정산 — 채택")
    head = rec["candidate"]["head"]
    _run(fx.repo, "checkout", "-q", "--detach", fx.base)
    _run(fx.repo, "merge", "-q", "--no-ff", "-m", "adopt", head)
    merged = fx.head()
    _run(fx.repo, "push", "-q", REMOTE, f"{merged}:refs/heads/{B.base_branch(W)}")
    gen = Gen()

    # dry-run 은 판정만 — 기록 그대로
    before = _raw(fx)
    res, logs = settle(fx, dry_run=True)
    check("⑩ dry-run 채택 판정 · 기록 무변경", res["counts"]["adopted"] == 1 and _raw(fx) == before
          and res["outcomes"][0].get("dry_run"), str(res))
    check("⑩ dry-run 로그", any("dry-run" in ln and "해제 예정" in ln for ln in logs), "\n".join(logs))

    res, logs = settle(fx)
    check("⑩ 채택 → 해제", res["ok"] and res["counts"]["adopted"] == 1 and fx.record("T1") is None,
          str(res))
    check("⑩ 채택 로그 — 대상·결정·요약", any("T1 adopted" in ln for ln in logs)
          and any("요약" in ln for ln in logs), "\n".join(logs))
    res, _ = run(fx, gen)
    check("⑩ 해제 뒤 재생성 없음", gen.calls == [] and res["entries"] == 0, str(res))


def t_settle_waiting():
    fx, rec = _with_candidate("⑩ 정산 — 채택 대기")
    before = _raw(fx)
    res, logs = settle(fx)
    check("⑩ 미채택·후보 있음 → 유지", res["ok"] and res["counts"]["waiting"] == 1
          and _raw(fx) == before, str(res))


def _delete_candidate(fx):
    cand = B.candidate_branch(W, "T1", 1)
    subprocess.run(["git", "-C", str(fx.origin), "update-ref", "-d", f"refs/heads/{cand}"], check=True)
    assert cand not in fx.remote_refs()


def t_settle_deleted_open():
    fx, rec = _with_candidate("⑩ 정산 — 후보 삭제 · work 열림")
    _delete_candidate(fx)
    res, logs = settle(fx)
    after = fx.record("T1")
    check("⑩ 삭제+열림 → 후보 뗌 · 표시 유지", res["ok"] and res["counts"]["dropped"] == 1
          and after is not None and "candidate" not in after and after["needs_revalidation"] is True
          and after["fingerprint"] == rec["fingerprint"], f"{res} {after}")
    check("⑩ 후보 뗌 로그", any("T1 dropped" in ln for ln in logs), "\n".join(logs))
    gen = Gen()
    res, _ = run(fx, gen)
    check("⑩ 다음 주기에 재생성", res["ok"] and gen.calls == ["agy"]
          and B.candidate_branch(W, "T1", 1) in fx.remote_refs(), f"{gen.calls} {res}")


def t_settle_deleted_closed():
    fx, rec = _with_candidate("⑩ 정산 — 후보 삭제 · work 닫힘")
    _delete_candidate(fx)
    before = _raw(fx)
    res, logs = settle(fx, work_open=lambda wid: False)
    check("⑩ 삭제+닫힘 → 유지·보고", res["ok"] and res["counts"]["kept_closed"] == 1
          and _raw(fx) == before and "닫힘" in res["outcomes"][0]["reason"], str(res))

    def boom(wid):
        raise ConnectionError("queue down")
    res, _ = settle(fx, work_open=boom)
    check("⑩ 삭제 + work 조회 예외 → 무변경 · ok=False", not res["ok"]
          and res["counts"]["error"] == 1 and _raw(fx) == before, str(res))


def t_settle_fetch_failure():
    fx, rec = _with_candidate("⑩ 정산 — 원격 실패")
    _run(fx.repo, "remote", "set-url", REMOTE, str(fx.tmp / "missing.git"))
    before = _raw(fx)
    res, logs = settle(fx)
    check("⑩ 원격 실패 → 무변경 · ok=False", not res["ok"] and res["counts"]["error"] == 1
          and _raw(fx) == before and "원격 조회 실패" in res["reason"], str(res))
    check("⑩ 실패 로그 — 건드리지 않음", any("건드리지 않음" in ln for ln in logs), "\n".join(logs))

    fx, rec = _with_candidate("⑩ 정산 — 작업 브랜치 없음")
    subprocess.run(["git", "-C", str(fx.origin), "update-ref", "-d",
                    f"refs/heads/{B.base_branch(W)}"], check=True)
    before = _raw(fx)
    res, _ = settle(fx)
    check("⑩ 작업 브랜치 없음 → 무변경 · ok=False", not res["ok"] and _raw(fx) == before
          and "작업 브랜치" in res["reason"], str(res))


def t_drop_candidate_cas():
    print("── drop_candidate CAS")
    root = Path(tempfile.mkdtemp(prefix="reval-drop-"))
    TMPS.append(root)
    R.mark(root, "task", "t", fingerprint="one", metadata={})
    R.set_candidate(root, "task", "t", fingerprint="one", candidate={"branch": "b", "head": "h1"})
    check("지문 불일치 거절", not R.drop_candidate(root, "task", "t", fingerprint="x", head="h1"))
    check("head 불일치 거절", not R.drop_candidate(root, "task", "t", fingerprint="one", head="h2"))
    check("일치 → 후보만 뗌", R.drop_candidate(root, "task", "t", fingerprint="one", head="h1")
          and "candidate" not in R.pending(root)[0] and R.pending(root)[0]["needs_revalidation"])
    check("후보 없으면 거절", not R.drop_candidate(root, "task", "t", fingerprint="one", head="h1"))


def main() -> int:
    for t in (t_names, t_set_candidate, t_success, t_next_cloud, t_all_fail, t_quota,
              t_piece_and_existing, t_work_state, t_guard, t_limit, t_race,
              t_drop_candidate_cas, t_settle_adopted, t_settle_waiting, t_settle_deleted_open,
              t_settle_deleted_closed, t_settle_fetch_failure):
        try:
            t()
        except Exception as e:                               # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} 예외", False, f"{type(e).__name__}: {e}")
    import shutil
    for d in TMPS:
        shutil.rmtree(d, ignore_errors=True)
    print(f"{PASS}/{PASS + FAIL} 통과")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
