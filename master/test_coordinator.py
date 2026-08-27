"""2-tier 코디네이터 — [중요] **실제 git 저장소로** 돌린다.

리포트 13 §14 가 같은 교훈을 네 번 적었다: **주입은 계약을 재고 실물을 재지 않는다.**
그래서 여기서는 git 을 흉내내지 않는다 — `tmp` 에 bare origin + 작업 클론을 실제로 만들고
assign → push_attempt → verify_and_merge 를 태운다 (`#327` 이후 합성은 이 파일 안에). 검증하는 것:

    ① attempt 가 원격에 생기고 작업분이 실려 있다
    ② 첫 통과분이 durable 을 **만든다**
    ③ 두 번째 라운드가 durable 에 **누적**된다 (폐기·재구현이 아니다 — 2026-06-21 정정)
    ④ [중요] stale epoch 은 **부작용 없이** 거부된다 (durable 이 안 움직인다)
    ⑤ cleanup 기본값은 **지우지 않는다** (증거 보존, 08-09 결정)
    ⑥ `delete=True` 면 ephemeral 만 지우고 **durable 은 산다**

`.venv/bin/python master/test_coordinator.py`
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# [중요] `#319` — 브랜치가 계층형이라 work_id 가 이름의 한 칸이다.
WORK = "w1"

from master.work import coordinator as C            # noqa: E402
from master.work.branch_names import attempt_branch, durable_branch  # noqa: E402

PASS = FAIL = 0
TASK = "t5"
SHOP = "HV0I6DL"
TARGET = "Source/ModularStage/Mission/MissionTask_Probe.cpp"


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _run(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "-C", str(cwd), *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} rc={r.returncode}: {r.stderr}")
    return (r.stdout or "").strip()


class Repo:
    """bare origin + 작업 클론. 실제 git 이다."""

    def __init__(self, tmp: Path):
        self.origin = tmp / "origin.git"
        self.work = tmp / "work"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.work)], check=True)
        p = self.work / TARGET
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("// [PSEUDO] 골조\n", encoding="utf-8")
        _run(self.work, "add", "-A")
        _run(self.work, "commit", "-q", "-m", "[skeleton] probe")
        _run(self.work, "push", "-q", "origin", "main")
        self.base = _run(self.work, "rev-parse", "HEAD")

    def remote_branches(self) -> list:
        out = _run(self.work, "ls-remote", "--heads", "origin")
        return sorted(ln.split("refs/heads/")[-1] for ln in out.splitlines() if "refs/heads/" in ln)

    def file_at(self, ref: str) -> str:
        _run(self.work, "fetch", "-q", "origin", ref)
        return _run(self.work, "show", f"origin/{ref}:{TARGET}")


def _round(repo, *, work_id, task_id, workshop, ts, base_ref, target_rel, work_fn,
           submit_epoch, current_epoch, message, logf=C._noop_log) -> dict:
    """assign → push_attempt → verify_and_merge 를 한 번에 (`#327` 이후 테스트 안의 합성).

    [중요] 종전에는 `coordinator.run_round` 가 이 합성을 들고 있었는데 **부르는 곳이 이 테스트
    뿐**이었고 `#327` 로 걷혔다. **밑의 세 함수는 산다** — `selftest` 드라이런이 쓴다. 그래서
    검사를 지우지 않고 합성만 여기로 옮겼다.
    [주의] 순서는 실전 형태 그대로다: `assign`(서버) → `push_attempt`(작업장) →
    `verify_and_merge`(서버). selftest 가 *"real 모드는 합성을 쓰지 않는다"* 며 택한 그 형태다.
    """
    a = C.assign_attempt(work_id, task_id, workshop, ts)
    head = C.push_attempt(repo, a["attempt"], base_ref, work_fn, target_rel,
                          message=message, logf=logf)
    res = C.verify_and_merge(repo, a["attempt"], a["durable"],
                             submit_epoch=submit_epoch, current_epoch=current_epoch, logf=logf)
    return {**a, "head": head, **res}


def test_full_round_creates_durable():
    with tempfile.TemporaryDirectory() as td:
        r = Repo(Path(td))
        res = _round(r.work, work_id=WORK, task_id=TASK, workshop=SHOP, ts="t1", base_ref=r.base,
                          target_rel=TARGET, work_fn=C.fake_workshop("// round1"),
                          submit_epoch=1, current_epoch=1, message="[probe] r1")

        check("attempt 이름이 규약과 같다",
              res["attempt"] == attempt_branch(WORK, TASK, SHOP, "t1"), res["attempt"])
        check("durable 이름이 규약과 같다",
              res["durable"] == durable_branch(WORK, TASK), res["durable"])
        check("① attempt 가 원격에 있다", res["attempt"] in r.remote_branches(),
              str(r.remote_branches()))
        check("① 작업분이 attempt 에 실렸다", "// round1" in r.file_at(res["attempt"]))
        check("② 첫 통과분이 durable 을 만든다",
              res["merged"] and res["reason"] == "created_from_first_attempt", str(res))
        check("② durable 이 원격에 있다", durable_branch(WORK, TASK) in r.remote_branches())
        check("② durable 에 작업분이 있다", "// round1" in r.file_at(durable_branch(WORK, TASK)))


def test_second_round_accumulates():
    """[중요] reject 는 폐기·재구현이 아니라 전진·수정이다 (2026-06-21 정정)."""
    with tempfile.TemporaryDirectory() as td:
        r = Repo(Path(td))
        _round(r.work, work_id=WORK, task_id=TASK, workshop=SHOP, ts="t1", base_ref=r.base,
                    target_rel=TARGET, work_fn=C.fake_workshop("// round1"),
                    submit_epoch=1, current_epoch=1, message="[probe] r1")
        dur = durable_branch(WORK, TASK)
        res2 = _round(r.work, work_id=WORK, task_id=TASK, workshop=SHOP, ts="t2",
                           base_ref=f"origin/{dur}", target_rel=TARGET,
                           work_fn=C.fake_workshop("// round2"),
                           submit_epoch=1, current_epoch=1, message="[probe] r2")
        body = r.file_at(dur)
        check("③ 2라운드가 merge 된다", res2["merged"] and res2["reason"] == "merged", str(res2))
        check("③ 1라운드분이 살아 있다 (누적)", "// round1" in body, body)
        check("③ 2라운드분도 있다", "// round2" in body, body)
        check("③ ephemeral 이 둘 다 남는다",
              attempt_branch(WORK, TASK, SHOP, "t1") in r.remote_branches()
              and attempt_branch(WORK, TASK, SHOP, "t2") in r.remote_branches())


def test_stale_epoch_rejected_without_side_effects():
    with tempfile.TemporaryDirectory() as td:
        r = Repo(Path(td))
        _round(r.work, work_id=WORK, task_id=TASK, workshop=SHOP, ts="t1", base_ref=r.base,
                    target_rel=TARGET, work_fn=C.fake_workshop("// round1"),
                    submit_epoch=1, current_epoch=1, message="[probe] r1")
        dur = durable_branch(WORK, TASK)
        before = _run(r.work, "ls-remote", "origin", dur)

        # zombie: 회수돼 epoch 이 2로 올라간 뒤 들어온 epoch 1 의 시도
        zombie = attempt_branch(WORK, TASK, "JFVS693", "t9")
        C.push_attempt(r.work, zombie, r.base, C.fake_workshop("// zombie"), TARGET,
                       message="[probe] zombie")
        res = C.verify_and_merge(r.work, zombie, dur, submit_epoch=1, current_epoch=2)

        check("④ stale epoch 은 거부된다", not res["ok"] and not res["merged"], str(res))
        check("④ 사유에 epoch 가 적힌다", "stale_epoch:1<2" in res["reason"], res["reason"])
        check("④ durable 이 움직이지 않았다",
              _run(r.work, "ls-remote", "origin", dur) == before)
        check("④ zombie 내용이 durable 에 없다", "// zombie" not in r.file_at(dur))
        check("④ zombie attempt 자체는 남는다 (증거)", zombie in r.remote_branches())


def test_cleanup_default_keeps_everything():
    with tempfile.TemporaryDirectory() as td:
        r = Repo(Path(td))
        _round(r.work, work_id=WORK, task_id=TASK, workshop=SHOP, ts="t1", base_ref=r.base,
                    target_rel=TARGET, work_fn=C.fake_workshop("// round1"),
                    submit_epoch=1, current_epoch=1, message="[probe] r1")
        out = C.cleanup_attempts(r.work, WORK, TASK)
        check("⑤ 기본값은 찾기만 한다", out["deleted"] == [] and len(out["found"]) == 1, str(out))
        check("⑤ 원격이 그대로다", attempt_branch(WORK, TASK, SHOP, "t1") in r.remote_branches())


def test_cleanup_delete_spares_durable():
    with tempfile.TemporaryDirectory() as td:
        r = Repo(Path(td))
        _round(r.work, work_id=WORK, task_id=TASK, workshop=SHOP, ts="t1", base_ref=r.base,
                    target_rel=TARGET, work_fn=C.fake_workshop("// round1"),
                    submit_epoch=1, current_epoch=1, message="[probe] r1")
        out = C.cleanup_attempts(r.work, WORK, TASK, delete=True)
        names = r.remote_branches()
        check("⑥ ephemeral 이 지워졌다", len(out["deleted"]) == 1
              and attempt_branch(WORK, TASK, SHOP, "t1") not in names, str(names))
        check("⑥ durable 은 산다", durable_branch(WORK, TASK) in names, str(names))


def test_no_change_is_a_fact():
    """[주의] 아무것도 안 고치면 commit 이 실패한다 — 그건 사실이므로 삼키지 않는다."""
    with tempfile.TemporaryDirectory() as td:
        r = Repo(Path(td))
        try:
            C.push_attempt(r.work, attempt_branch(WORK, TASK, SHOP, "t0"), r.base,
                           lambda repo, rel: None, TARGET, message="[probe] noop")
            check("변경 0건은 GitError 로 올라온다", False, "예외가 안 났다")
        except C.GitError:
            check("변경 0건은 GitError 로 올라온다", True)


def main() -> int:
    for fn in (test_full_round_creates_durable, test_second_round_accumulates,
               test_stale_epoch_rejected_without_side_effects,
               test_cleanup_default_keeps_everything, test_cleanup_delete_spares_durable,
               test_no_change_is_a_fact):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_coordinator: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
