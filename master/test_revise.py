"""`#388` — 상한 있는 재시도. **실 저장소·실 큐를 두드리지 않는다** (주입 자리를 쓴다)."""
import subprocess
import sys
import tempfile
from pathlib import Path
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

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


# ── 🔴 환경 실패는 코드 실패가 아니다 (`#391` 완결 · 실측 2026-09-12) ────────────────

# [중요] **`.2` 의 실제 출력이다.** 지어낸 문자열이 아니라 그날 지휘자가 남긴 말을 그대로
#    넣는다 — `#391` 이 이 출력을 남기게 만들었고, 그것이 판정 근거가 된다.
_REAL_2 = (
    '{"type":"item.completed","item":{"id":"item_4","type":"command_execution",'
    '"command":"\\"C:\\\\WINDOWS\\\\System32\\\\WindowsPowerShell\\\\v1.0\\\\powershell.exe\\" '
    '-Command \\"cmd /c type C:\\\\Users\\\\janus\\\\.codex\\\\skills\\\\ax-work\\\\SKILL.md\\"",'
    '"aggregated_output":"","exit_code":-1073741502,"status":"failed"}}'
)

check("🔴 실물 출력에서 환경 실패를 잡는다", R.environment_failure([_REAL_2]) == "-1073741502",
      R.environment_failure([_REAL_2]))
check("  정상 출력은 잡지 않는다 (오탐 금지)",
      R.environment_failure(["구현을 마쳤습니다", "RESULT: DONE"]) == "")
check("  0xC0000142 표기도 잡는다",
      R.environment_failure(["exec failed 0xC0000142"]) == "0xC0000142")
check("  세션 9 파이프 실패도 잡는다 (elevated runner)",
      R.environment_failure(["timed out after 15000ms connecting runner pipe-in"]) != "")
check("#721 실측 OAuth 만료는 인증 실패",
      R.authentication_failure(["Failed to authenticate: OAuth session expired and could not be refreshed"]) != "")
check("#721 사전 검사 고정 표식도 인증 확인 실패",
      R.authentication_failure(["AX_CLAUDE_AUTH_FAILED: 검사 실패"]) != "")
check("#721 일반 인증 코드 언급은 오탐 없음",
      R.authentication_failure(["authenticate 함수를 구현했다", "로그인 테스트 성공"]) == "")

# [중요] **환경 실패는 첫 번째에 멈춘다** — 층1 이슈가 있어도 revise 로 보내지 않는다.
#    피드백을 실어 보내도 그 기계에서는 스킬조차 못 읽는다(실측: `.2` 가 세 번 태웠다).
check("[중요] 층1 이슈가 있어도 환경 신호가 있으면 재시도 대상이 아니다",
      R.classify(["[PSEUDO] 가 남아 있다"], 1) == R.REVISE
      and R.environment_failure([_REAL_2]) != "",
      "classify 는 그대로 revise 를 내고, 환경 판정은 호출자가 앞에서 가른다")


# ── 🔴 한도 소진도 코드 실패가 아니다 (사용자 지적 2026-09-12) ────────────────────────

# [중요] **실측 문구다** — `lanes.py` 머리말이 기록한 그것: *"429 You've hit your session
#    limit 을 맞자 4조각 중 3이 동시에 죽고 라운드가 02:30 까지 보류됐다"*(2026-09-04).
check("🔴 실물 429 문구를 잡는다",
      R.quota_exhausted(["429 You've hit your session limit"]) == "429")
check("  usage limit 도 잡는다", R.quota_exhausted(["Error: usage limit reached"]) != "")
check("[주의] 오탐 금지 — 그냥 숫자 429 는 아니다",
      R.quota_exhausted(["코드 429줄을 읽었다", "line 429"]) == "")
check("  정상 출력은 잡지 않는다", R.quota_exhausted(["RESULT: DONE", "구현 완료"]) == "")

# 🔴 환경 실패와 **처분이 다르다** — 죽이지 않고 다른 워커에게 넘긴다
check("[중요] 한도와 환경은 다른 갈래다", R.QUOTA != R.ENV)
_src = (Path(__file__).resolve().parent / "work" / "infer.py").read_text(encoding="utf-8")
check("🔴 [중요] 한도면 `quota_exhausted` 로 신고한다 (큐가 pending 복귀로 받는다)",
      '"quota_exhausted" if quota_hit' in _src, "infer.py 의 사유 분기")
def _commit_failure(notes, previous="", attempt=1):
    """실제 실패→판정→반납 경로. 외부실행·git·사용량·공지 API만 격리한다."""
    from master.work import infer as I, wcommit as WC
    calls = []
    def api(method, path, body=None):
        calls.append((method, path, body))
        return {"ok": True}
    committed = WC.Committed(task_id="isolated", stage="llm", reason="RESULT: BLOCKED", notes=notes)
    with ExitStack() as stack:
        stack.enter_context(patch("master.work.twin_base.local_baseline", return_value={}))
        stack.enter_context(patch.object(WC, "run", return_value=committed))
        stack.enter_context(patch("master.work.usage.record", return_value={"lane": "", "input_tokens": 0,
            "output_tokens": 0, "cost_known": False, "measured": False}))
        stack.enter_context(patch.object(I._MODE, "current", return_value=("codex", "test")))
        notice = stack.enter_context(patch.object(I, "_notify_blocked"))
        embed = stack.enter_context(patch.object(R, "embed", return_value=R.Embedded(
            task_id="isolated", head="1234567890", branch="task/isolated")))
        result = I.commit_task(SimpleNamespace(usage_log=Path("/unused")), SimpleNamespace(host="worker"),
            {"task_id": "isolated", "attempt_count": attempt, "last_feedback": previous, "epoch": 7},
            work_id="isolated-work", base="abc", want=[], branch="isolated", api=api)
    return result, calls, notice, embed

_quota_res, _quota_calls, _quota_notice, _quota_embed = _commit_failure(["usage limit reached", "0xC0000142"])
check("  한도가 환경보다 **먼저** 판정된다 (둘 다 걸리면 처분이 다르므로)",
      len(_quota_calls) == 1 and _quota_calls[0][2]["reason"] == "quota_exhausted"
      and not _quota_embed.called and any("pending" in n for n in _quota_res.notes), str(_quota_calls))
check("  요청자에게도 알린다", _quota_notice.call_count == 1
      and _quota_notice.call_args.kwargs.get("kind") == "quota")

# ── `#615` (가) 출력 반복 ─────────────────────────────────────────────────────
# [DOC] 실측 출력(같은 글자의 `RESULT: BLOCKED` 3회)이 같은 지문을 내고, 지문이 큐의 저장 한도
#    (detail 앞 600자)를 넘어 살아남는지와 실제 실패반납 경로를 잰다.
_BLOCKED_OUT = ["승인이 필요합니다. 계획을 검토해 주세요.", "RESULT: BLOCKED"]
_fp1 = R.output_fingerprint(_BLOCKED_OUT)
_fp2 = R.output_fingerprint(list(_BLOCKED_OUT))
_fp3 = R.output_fingerprint(list(_BLOCKED_OUT))
check("🔴 같은 출력 3회 → 같은 지문", _fp1 == _fp2 == _fp3 and _fp1 != "", f"{_fp1}/{_fp2}/{_fp3}")
check("  지문은 12 hex", len(_fp1) == 12 and all(ch in "0123456789abcdef" for ch in _fp1), _fp1)
check("  공백만 다른 출력도 같은 지문",
      R.output_fingerprint(["  승인이 필요합니다.   계획을 검토해 주세요. ", "", "RESULT:  BLOCKED\n"])
      == _fp1)
check("  다른 출력 → 다른 지문",
      R.output_fingerprint(["다른 사유", "RESULT: BLOCKED"]) != _fp1)

check("  빈 출력([]) 은 지문이 없다", R.output_fingerprint([]) == "")
check("  공백뿐인 출력도 지문이 없다", R.output_fingerprint(["", "  "]) == "")
check("[주의] 지문이 없으면 반복으로 판정하지 않는다",
      not R.repeated_output(f"{R.FP_PREFIX}{_fp1}] x", "")
      and not R.repeated_output("", ""))

_long = "가" * 3000
_saved = R.tag_detail(_long, _fp1)[:600]                 # 서버가 last_feedback 으로 남기는 앞 600자
check("🔴 앞 600자로 잘려도 지문이 살아남는다", R.repeated_output(_saved, _fp1), _saved[:40])
check("  다른 지문과는 반복이 아니다",
      not R.repeated_output(_saved, R.output_fingerprint(["다른 사유"])))
check("  지문 없는 옛 피드백은 반복이 아니다",
      not R.repeated_output("층1 — [PSEUDO] 잔존", _fp1))

_repeat_res, _repeat_calls, _repeat_notice, _repeat_embed = _commit_failure(_BLOCKED_OUT, R.tag_detail("previous", _fp1))
check("🔴 infer 실패경로에서 같은출력은 반복종결", len(_repeat_calls) == 1
      and _repeat_calls[0][2]["result"] != R.REVISE and not _repeat_embed.called
      and any("직전 시도와 출력이 같다" in n for n in _repeat_res.notes), str(_repeat_calls))
_first_res, _first_calls, _first_notice, _first_embed = _commit_failure(_BLOCKED_OUT)
check("🔴 infer 반납지문은 큐절단후에도 재시도에 전달", len(_first_calls) == 1
      and _first_calls[0][2]["result"] == R.REVISE and _first_embed.called
      and R.repeated_output(_first_calls[0][2]["detail"][:600], _fp1), str(_first_calls))

print("=" * 46)
print(f"통과 {PASS} · 실패 {FAIL}")
print("=" * 46)
sys.exit(1 if FAIL else 0)
