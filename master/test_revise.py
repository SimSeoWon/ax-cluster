"""`#388` — 상한 있는 재시도. **실 저장소·실 큐를 두드리지 않는다** (주입 자리를 쓴다)."""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master.work import revise as R                                    # noqa: E402

PASS = FAIL = 0


def check(name, cond, got=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [완료] {name}")
    else:
        FAIL += 1
        print(f"  [중요] 실패: {name}" + (f" — {got}" if got else ""))


def _git(cwd, *a):
    return subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                           "-C", str(cwd), *a], capture_output=True, text=True)


print("[1] classify — 원전 `_classify_verify_issues` 와 같은 표")
check("이슈 없으면 pass", R.classify([], 1) == R.PASS)
check("1회차는 revise", R.classify(["x"], 1) == R.REVISE)
check("2회차도 revise", R.classify(["x"], 2) == R.REVISE)
check("🔴 3회차는 reject (상한)", R.classify(["x"], 3) == R.REJECT)
check("상한 넘겨도 reject", R.classify(["x"], 9) == R.REJECT)
check("[중요] 상한값이 원전과 같다 (3)", R.MAX_ATTEMPTS == 3, str(R.MAX_ATTEMPTS))

print("[2] 피드백 블록 — 원전과 같은 표식")
b = R.build_block(["[PSEUDO] 가 남아 있다", "빈 본문"], 2)
check("원전 표식으로 연다", b.startswith("/* AUTO-VERIFY FEEDBACK"))
check("attempt 번호가 있다", "#2" in b)
check("이슈가 전부 실린다", "[PSEUDO] 가 남아 있다" in b and "빈 본문" in b)
check("닫는다", b.rstrip().endswith("*/"))

print("[3] strip — 누적되지 않는다")
src = b + "\n\nvoid F() {}\n"
check("이전 블록을 걷는다", R.strip_feedback(src).strip() == "void F() {}")
check("없으면 그대로", R.strip_feedback("void F() {}\n").strip() == "void F() {}")
check("🔴 닫는 줄이 없으면 손대지 않는다 (본문 보호)",
      R.strip_feedback("/* AUTO-VERIFY FEEDBACK 잘림\nvoid F(){}") .startswith("/* AUTO"))
twice = R.build_block(["새 사유"], 3) + "\n\n" + R.strip_feedback(src)
check("두 번 박아도 블록은 하나", twice.count("AUTO-VERIFY FEEDBACK") == 1)

print("[4] embed — 거절 조건 (조용히 성공하지 않는다)")


class _P:
    def __init__(self, repo):
        self.repo = repo
        self.name = "T"


e = R.embed(_P("/nonexistent"), "w1", "t1", issues=["x"], attempt=2, targets=[])
check("대상이 없으면 실패", not e.ok and "대상 파일이 없다" in e.error, e.error)
e = R.embed(_P("/nonexistent"), "w1", "t1", issues=[], attempt=2, targets=["a.cpp"])
check("이슈가 비면 실패", not e.ok and "비었다" in e.error, e.error)

print("[5] embed — 실물 git 한 바퀴 (원격까지)")
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    bare = td / "remote.git"
    _git(td, "init", "--bare", "-b", "main", str(bare))
    seed = td / "seed"
    seed.mkdir()
    _git(seed, "init", "-b", "main")
    src_dir = seed / "Source"
    src_dir.mkdir()
    (src_dir / "A.cpp").write_text("// [PSEUDO] 채워라\nvoid A() {}\n", encoding="utf-8")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-m", "skeleton")
    _git(seed, "remote", "add", "origin", str(bare))
    _git(seed, "push", "origin", "main")
    base = _git(seed, "rev-parse", "HEAD").stdout.strip()
    # 서브 브랜치를 base 위에 세운다 (`subbranch.create` 가 하는 것과 같다)
    _git(seed, "push", "origin", f"{base}:refs/heads/task/w1/r1/t1")

    mirror = td / "mirror"
    _git(td, "clone", str(bare), str(mirror))

    class _Paths:
        repo = str(mirror)
        name = "T"

    # [중요] **쓰기 가드를 세운다** (`#329`) — 없으면 `embed` 가 fail-closed 로 막는다.
    #    그것이 정상 동작이고, 이 테스트는 가드가 선 뒤를 잰다.
    from master.work import attempt as A
    A.install_hook(_Paths())
    check("가드가 섰다", A.hook_status(_Paths()).get("state") == A.STATE_OK,
          str(A.hook_status(_Paths())))

    got = R.embed(_Paths(), "w1", "t1", issues=["층1 위반: [PSEUDO] 가 남아 있다"],
                  attempt=2, targets=["Source/A.cpp"], round_no=1,
                  remote="origin", logf=lambda m: None)
    check("커밋이 만들어졌다", got.ok, got.error)
    check("대상 파일이 기록됐다", got.files == ["Source/A.cpp"], str(got.files))
    check("브랜치 이름이 라운드를 담는다", got.branch.endswith("/r1/t1"), got.branch)
    if got.ok:
        check("🔴 base 커밋과 다르다 (새 커밋이다)", got.head != base)
        # 원격에서 되읽어 확인 — **디스크 상태로 판정한다**
        out = _git(mirror, "fetch", "origin", f"+refs/heads/{got.branch}:refs/ax/t")
        body = _git(mirror, "show", "refs/ax/t:Source/A.cpp").stdout
        check("🔴 원격 파일에 피드백이 실려 있다", "AUTO-VERIFY FEEDBACK" in body, body[:80])
        check("🔴 원래 본문이 보존됐다", "void A() {}" in body)
        check("[PSEUDO] 지시가 그대로 보인다", "[PSEUDO]" in body)
        # 두 번째 시도 — 블록이 누적되지 않아야 한다
        got2 = R.embed(_Paths(), "w1", "t1", issues=["다시: [PSEUDO]"], attempt=3,
                       targets=["Source/A.cpp"], round_no=1, remote="origin")
        check("두 번째도 성공", got2.ok, got2.error)
        if got2.ok:
            _git(mirror, "fetch", "origin", f"+refs/heads/{got.branch}:refs/ax/t2")
            b2 = _git(mirror, "show", "refs/ax/t2:Source/A.cpp").stdout
            check("🔴 블록이 누적되지 않는다", b2.count("AUTO-VERIFY FEEDBACK") == 1,
                  str(b2.count("AUTO-VERIFY FEEDBACK")))
            check("새 사유로 갱신됐다", "다시: [PSEUDO]" in b2)
            check("본문은 여전히 있다", "void A() {}" in b2)
    check("워크트리 잔재가 없다", not (mirror.parent / ".revise-t1").exists())

print("[6] 큐 전이 — claimed → needs_revision → **다른 기계가** 재클레임 → terminal")
import tempfile as _tf                                                 # noqa: E402
from master.task_queue.persistence import TaskIndex                    # noqa: E402
from master.task_queue.logic import register_work, register_task       # noqa: E402
from master.task_queue import logic_lifecycle as LL, logic_claim as LC  # noqa: E402

_idx = TaskIndex(Path(_tf.mkdtemp(prefix="ax-revise-q-")))
_w = register_work(_idx, title="t", target_repo="/tmp/repo")
_t = register_task(_idx, work_id=_w["work_id"], type="write", task_data={}, stem="A",
                   target_file="Source/A.cpp", header_file="Source/A.h")
_tid = _t["task_id"]
_c = LC.claim_task(_idx, worker_id="192.168.0.2", capabilities=[])
check("워커가 집었다", _c.get("task_id") == _tid and _idx.tasks[_tid]["status"] == "claimed")

_r = LL.submit_fail(_idx, _tid, "BLOCKED", "층1 위반: [PSEUDO] 가 남아 있다",
                    epoch=_idx.tasks[_tid].get("epoch"), worker_id="192.168.0.2",
                    result="revise", new_base_commit="bbbbbbb")
_tk = _idx.tasks[_tid]
check("revise 가 받아들여졌다", _r.get("ok") and _r.get("revised"), str(_r))
check("🔴 terminal 이 아니라 needs_revision 이다", _tk["status"] == "needs_revision", _tk["status"])
check("🔴 base 가 피드백 커밋으로 옮겨졌다", _tk["base_commit"] == "bbbbbbb", _tk["base_commit"])
check("워커를 놓아 줬다", not _tk.get("worker_id"), str(_tk.get("worker_id")))
check("사유가 레코드에 남았다", "[PSEUDO]" in (_tk.get("last_feedback") or ""))

_c2 = LC.claim_task(_idx, worker_id="192.168.0.43", capabilities=[])
check("🔴 **다른 기계**가 다시 집는다", _c2.get("task_id") == _tid, str(_c2)[:120])
check("attempt 가 올랐다", int(_idx.tasks[_tid].get("attempt_count") or 0) == 2,
      str(_idx.tasks[_tid].get("attempt_count")))
check("epoch 가 올랐다 (fencing)", int(_idx.tasks[_tid].get("epoch") or 0) == 2,
      str(_idx.tasks[_tid].get("epoch")))

_r2 = LL.submit_fail(_idx, _tid, "BLOCKED", "또 같은 사유",
                     epoch=_idx.tasks[_tid].get("epoch"), worker_id="192.168.0.43")
check("🔴 result 를 안 주면 종전대로 terminal 이다", _idx.tasks[_tid]["status"] == "failed",
      _idx.tasks[_tid]["status"])

print()
print("=" * 46)
print(f"통과 {PASS} · 실패 {FAIL}")
print("=" * 46)
sys.exit(1 if FAIL else 0)
