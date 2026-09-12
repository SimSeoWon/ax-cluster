# ── 🔴 추론(code) 테스트를 들어냈다 (`#404`, 2026-09-12) ────────────────────────────
#
# [중요] **미룬 것이 아니라 폐기다.** 이 테스트들은 `carry.py` + `manifest.md` 운송 규약을
# 재는데, 그 둘은 2026-09-02 에 철거됐다 — `master.work.manifest` 모듈이 없어서 import 부터
# 죽었다. 지시는 이제 골조의 `[DOC]`/`[PSEUDO]` 주석으로 옮겨 다니고 git 이 나른다.
# 주석으로 남기면 「되살릴 것」으로 읽히므로 지운다. 되살릴 것은 `#405` 처럼 주석으로 남겼다.
#
# [주의] **추론 파견이 죽은 것이 아니다** — 마스터 push(`work/infer.py`)가 그대로 맡는다.
# 이 데몬은 `--types=build` 만 집는다(원본의 기본값이기도 하다).

"""#204 계약 테스트 — 유형 필터·워커 스코프·claimer 실행·buildjob 등록·추론 pull.

핵심 계약:
① claim 의 `types` 필터 — build claimer 가 infer(write) 일감을 **절대 훔치지 않는다**
② WORKER_SCOPE — worker 토큰으로 verify·등록은 **못 한다** (κ.0 ①/② 경계의 강제)
③ claimer 는 판단하지 않는다 — 빌드 실패도 submit(사실 보고)이고, 착수 실패만 submit-fail
④ buildjob.enqueue 는 pull 모드 work + requires=["ue5"] build 태스크를 건다
⑤ 추론 pull (2단계) — 워커는 사실만 기록(submit 없음), 판정·스풀은 마스터 collect 가;
   프롬프트는 infer.py 정본과 글자까지 같아야 한다

실행: .venv/bin/python master/test_worker_daemon.py  (task_queue 가 pydantic — venv)
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.auth import WORKER_SCOPE  # noqa: E402
from master.task_queue.logic import register_work, register_task, claim_task  # noqa: E402
from master.task_queue.persistence import TaskIndex  # noqa: E402
from master.work import buildjob, worker_daemon, infer  # noqa: E402


def _idx() -> TaskIndex:
    root = Path(tempfile.mkdtemp(prefix="ax-claimer-"))
    idx = TaskIndex(root)
    r = register_work(idx, title="t", target_repo="/tmp/repo")
    assert r.get("ok"), r
    idx._wid = r["work_id"]
    return idx


# ── ① 유형 필터 ────────────────────────────────────────────────

def test_types_filter_skips_other_types():
    idx = _idx()
    register_task(idx, work_id=idx._wid, type="write", task_data={}, stem="w")
    got = claim_task(idx, "w-.2", capabilities=["ue5"], types=["build"])
    assert got is None                       # write 일감을 훔치지 않는다


def test_types_filter_takes_matching_type():
    idx = _idx()
    register_task(idx, work_id=idx._wid, type="write", task_data={}, stem="w")
    r = register_task(idx, work_id=idx._wid, type="build", task_data={},
                      stem="b", requires=["ue5"])
    got = claim_task(idx, "w-.2", capabilities=["ue5"], types=["build"])
    assert got and got["task_id"] == r["task_id"]


def test_no_types_is_backward_compatible():
    idx = _idx()
    r = register_task(idx, work_id=idx._wid, type="write", task_data={}, stem="w")
    got = claim_task(idx, "w-.2", capabilities=["ue5"])          # 기존 호출자 모양
    assert got and got["task_id"] == r["task_id"]


# ── ② 워커 스코프 ──────────────────────────────────────────────

def _scope_allows(method: str, path: str) -> bool:
    for rule in WORKER_SCOPE:
        m, pfx = rule[0], rule[1]
        sfx = rule[2] if len(rule) > 2 else ""
        if method == m and path.startswith(pfx) and (not sfx or path.endswith(sfx)):
            return True
    return False


def test_worker_scope_allows_claim_heartbeat_submit():
    assert _scope_allows("POST", "/api/v1/tasks/claim")
    assert _scope_allows("POST", "/api/v1/tasks/abc123/heartbeat")
    assert _scope_allows("POST", "/api/v1/tasks/abc123/submit")
    assert _scope_allows("POST", "/api/v1/tasks/abc123/submit-fail")


def test_worker_scope_denies_judgment_paths():
    # [중요] κ.0 경계 — 검증(판단)·등록·work 조작은 워커 토큰으로 불가
    assert not _scope_allows("POST", "/api/v1/tasks/abc123/verify")
    assert not _scope_allows("POST", "/api/v1/tasks")            # 등록
    assert not _scope_allows("POST", "/api/v1/works")
    assert not _scope_allows("PATCH", "/api/v1/works/abc")


# ── ③ claimer 실행 계약 ────────────────────────────────────────

class _FakeClient:
    def __init__(self, root):
        self.root = Path(root)
        self.project = "P"
        self.ue5_cmd = ""
        self.worker_id = "w-test"
        self.calls = []

    def heartbeat(self, tid, note=""):
        self.calls.append(("heartbeat", tid))
        if note:
            self.notes = getattr(self, "notes", []) + [note]

    def submit(self, tid, **kw):
        self.calls.append(("submit", tid, kw))
        return 200, {}

    def submit_fail(self, tid, reason, detail=""):
        self.calls.append(("submit-fail", tid, reason))
        return 200, {}


def test_build_failure_is_submitted_not_submitfail():
    """[중요] 빌드 FAIL 은 사실이지 사고가 아니다 — submit 으로 보고한다 (판단은 마스터)."""
    with tempfile.TemporaryDirectory() as tmp:
        c = _FakeClient(tmp)
        out = worker_daemon.run_one(
            c, {"task_id": "t1", "type": "build", "task_data": {"tree": tmp}},
            build_fn=lambda tree: {"ok": False, "passed": False, "failure": "컴파일 에러"},
            log=lambda m: None)
        kinds = [x[0] for x in c.calls]
        # #220: 심박은 위상 전환마다 즉시 1회 (빌드 시작·종료 note) — 횟수가 아니라
        # 「심박이 있었고 마지막이 submit」이 계약이다
        assert "heartbeat" in kinds and kinds[-1] == "submit", kinds
        assert any("빌드" in n for n in getattr(c, "notes", [])), getattr(c, "notes", None)
        assert out["build_ok"] is False and out["submit_http"] == 200


def test_setup_error_is_submitfail():
    with tempfile.TemporaryDirectory() as tmp:
        c = _FakeClient(tmp)

        def boom(tree):
            raise RuntimeError("Build.bat 없음")
        worker_daemon.run_one(c, {"task_id": "t2", "type": "build", "task_data": {}},
                        build_fn=boom, log=lambda m: None)
        assert ("submit-fail", "t2", "build-setup") in [x[:3] for x in c.calls]


def test_unsupported_type_bounces():
    with tempfile.TemporaryDirectory() as tmp:
        c = _FakeClient(tmp)
        out = worker_daemon.run_one(c, {"task_id": "t3", "type": "write"},
                              build_fn=lambda t: {}, log=lambda m: None)
        assert any(x[0] == "submit-fail" for x in c.calls)
        assert "지원 안 하는 유형" in out["outcome"]


# ── ④ buildjob 등록 ────────────────────────────────────────────

def test_enqueue_registers_pull_work_and_ue5_build_task():
    seen = []

    def fake_api(method, path, payload):
        seen.append((method, path, payload))
        if path == "/api/v1/works":
            assert payload["distribution_mode"] == "pull"
            # [중요] 프로젝트 태그·target_repo 가 **하드코딩이 아니어야** 한다 (#257).
            #    실측 2026-08-22: `target_repo` 가 `"ModularStage"` 문자열로 박혀 있었고
            #    `project` 는 안 보내서 큐에 `project: null` work 3건이 남았다.
            assert payload["project"] == "NS", payload
            assert payload["target_repo"] == "NS", payload
            return 200, {"ok": True, "work_id": "W1"}
        if path == "/api/v1/tasks":
            assert payload["type"] == "build" and payload["requires"] == ["ue5"]
            assert payload["project"] == "NS", payload
            return 200, {"ok": True, "task_id": "T1"}
        raise AssertionError(path)
    got = buildjob.enqueue(tree="E:/trunk/ModularStage", api=fake_api, project="NS")
    assert got == {"ok": True, "work_id": "W1", "task_id": "T1"}
    assert seen[1][2]["task_data"]["tree"] == "E:/trunk/ModularStage"


def test_enqueue_work_failure_reports_step():
    got = buildjob.enqueue(api=lambda m, p, b: (503, {"error": "down"}), project="NS")
    assert not got["ok"] and got["step"] == "work"


def test_close_retries_until_terminal_sticks():
    """[중요] verify 후의 비동기 auto-cleanup 이 종결을 **되덮는다** (실측 2026-08-18, 같은
    초에 merged → ready_for_review). close 는 쓰고-되읽고-되덮였으면 다시 쓴다 —
    안 그러면 work 가 미종결로 남아 전환 가드(#210)에 걸린다."""
    state = {"merge_status": "in_progress", "patches": 0}

    def fake_api(method, path, payload=None):
        if (method, path) == ("GET", "/api/v1/works"):
            return 200, [{"work_id": "W1", "merge_status": state["merge_status"]}]
        if (method, path) == ("GET", "/api/v1/tasks"):
            return 200, [{"task_id": "T1", "work_id": "W1", "type": "build",
                          "status": "submitted"}]
        if path == "/api/v1/tasks/T1/verify":
            assert payload == {"passed": True, "result": "pass"}
            state["merge_status"] = "ready_for_review"       # verify 의 동기 flip
            return 200, {"ok": True}
        if (method, path) == ("PATCH", "/api/v1/works/W1"):
            assert payload == {"merge_status": "merged"}
            state["patches"] += 1
            # 첫 PATCH 는 비동기 cleanup 이 되덮는 것을 흉내 — 두 번째부터 붙는다
            state["merge_status"] = ("ready_for_review" if state["patches"] == 1
                                     else "merged")
            return 200, {"ok": True}
        if (method, path) == ("GET", "/api/v1/works/W1"):
            # [주의] 실물 그대로 — 단건 GET 은 {"work": {...}} 로 감싼다 (실측: 이 포장을
            #    안 읽어서 close 가 60초를 헛기다린 버그가 있었다)
            return 200, {"work": {"work_id": "W1",
                                  "merge_status": state["merge_status"]}, "tasks": []}
        raise AssertionError((method, path))
    got = buildjob.close("W1", result="pass", api=fake_api,
                         sleeper_close=lambda s: None)
    assert got["ok"] and state["patches"] == 2, got
    assert got["settle"].startswith("merged 확정")


def test_close_rejects_bad_result():
    got = buildjob.close("W1", result="ok?", api=lambda *a: (500, {}))
    assert not got["ok"] and "pass|fail" in got["error"]


# ── ⑤ 추론 pull (#204 2단계) ───────────────────────────────────



def test_types_cli_rejects_unknown():
    try:
        worker_daemon.main(["--types=xyz"])
        raise AssertionError("모르는 유형이 통과했다")
    except worker_daemon.ClaimerError as e:
        assert "xyz" in str(e)




_MANIFEST = "## 대상 파일\n\n- `Source/X.h`\n\n## 지시\n\n짧게.\n"












# ── ⑦ 상주 운영 계약 ──────────────────────────────────────────

def test_singleton_lock_excludes_second_instance():
    """[중요] 상주는 하나만 — 잠금은 OS 가 프로세스 죽음과 함께 푼다 (stale 판정 불필요)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        first = worker_daemon.acquire_singleton(root)
        assert first is not None
        assert worker_daemon.acquire_singleton(root) is None      # 겹치면 물러난다
        first.close()
        again = worker_daemon.acquire_singleton(root)             # 죽으면(닫히면) 자리가 난다
        assert again is not None
        again.close()


def test_capabilities_read_from_config_not_hardcoded():
    """[중요] 능력은 deliver 가 실측으로 쓴 config 값 — .43(UE5 없음)의 허위 신고를 막는다."""
    with tempfile.TemporaryDirectory() as tmp:
        ax = Path(tmp) / ".ax"
        ax.mkdir()
        (ax / "config.json").write_text(json.dumps({
            "master": {"host": "127.0.0.1", "services": {"task_queue": 8101}},
            "this_host": {"host": "192.168.0.43"},
            "project": "P", "capabilities": [],
            "backends": {}}), encoding="utf-8")
        (ax / "token").write_text("tok\n", encoding="utf-8")
        c = worker_daemon.Client(Path(tmp))
        assert c.capabilities == []                         # ue5 를 지어내지 않는다


# ── ⑥ 마스터 collect — 판정은 전부 여기서 ──────────────────────

def _paths(tmp: Path):
    return SimpleNamespace(root=tmp, responses=tmp / "responses", name="P",
                           repo=tmp / "no-repo")


def _facts(host="192.168.0.2"):
    return SimpleNamespace(host=host, user="u", path="E:\\t", windows=True)




def _reader_for(files: dict):
    from master.client import bundle

    def r(facts, path):
        for key, text in files.items():
            if path.replace("\\", "/").endswith(key):
                return text
        raise bundle.BundleError(f"없음: {path}")
    return r












# ── ⑦ #220 — 작업별 로그 축적 · heartbeat note ─────────────────

def test_heartbeat_note_stored_and_empty_preserves():
    """note 는 「지금 하는 일」 — 빈 note 는 이전 값을 지우지 않는다 (심박마다 note 의무 없음)."""
    from master.task_queue.logic_claim import heartbeat
    idx = _idx()
    register_task(idx, work_id=idx._wid, type="build", task_data={}, stem="b")
    t = claim_task(idx, "w-.2", capabilities=["ue5"], types=["build"])
    tid = t["task_id"]
    assert heartbeat(idx, tid, "w-.2", note="UE5 빌드 중")["ok"]
    assert idx.tasks[tid]["note"] == "UE5 빌드 중" and idx.tasks[tid]["note_at"]
    assert heartbeat(idx, tid, "w-.2")["ok"]                 # note 없는 심박
    assert idx.tasks[tid]["note"] == "UE5 빌드 중"            # 이전 값 유지
    assert heartbeat(idx, tid, "w-.2", note="x" * 500)["ok"]
    assert len(idx.tasks[tid]["note"]) == 200                # 서버가 자른다


def test_log_to_file_false_keeps_daily_log_clean():
    """[중요] 감시자가 겹쳐 부를 때의 「이미 상주 중」은 파일에 안 남는다 — 5분×하루=288줄이
    일별 로그를 뒤덮어 정작 볼 것(부팅·claim·실패)이 묻혔다 (실측 2026-08-19, #220 화면이 잡음)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        worker_daemon._log(root, "[boot] 이미 상주 중", to_file=False)
        assert not worker_daemon._log_path(root).exists()
        worker_daemon._log(root, "[boot] 진짜 부팅")
        assert "진짜 부팅" in worker_daemon._log_path(root).read_text(encoding="utf-8")
        assert "이미 상주 중" not in worker_daemon._log_path(root).read_text(encoding="utf-8")


def test_boot_rotation_renames_today_log():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        p = worker_daemon._log_path(root)
        p.parent.mkdir(parents=True)
        p.write_text("이전 부팅\n", encoding="utf-8")
        worker_daemon._bootstrap_log_rotation(root)
        assert not p.exists()
        assert p.with_name(f"{p.stem}_1{p.suffix}").exists()
        worker_daemon._log(root, "새 부팅")                         # 새 파일로 다시 쓴다
        assert "새 부팅" in p.read_text(encoding="utf-8")


def test_retention_sweeps_old_logs_and_debug_dirs():
    import os
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        d = worker_daemon._log_dir(root)
        old_log = d / "claimer_2020-01-01.log"
        old_dbg = d / "claimer_debug" / "oldtask"
        old_dbg.mkdir(parents=True)
        old_log.write_text("x", encoding="utf-8")
        past = 1577836800                                    # 2020-01-01 — 7일보다 오래됨
        os.utime(old_log, (past, past))
        os.utime(old_dbg, (past, past))
        fresh = d / "claimer_debug" / "newtask"
        fresh.mkdir(parents=True)
        n = worker_daemon._retention_sweep(root)
        assert n == 2 and not old_log.exists() and not old_dbg.exists()
        assert fresh.exists()                                # 최근 것은 남는다


def test_heart_note_beats_immediately_and_logs():
    """set_note 는 다음 interval 을 기다리지 않는다 — /cluster 가 위상을 놓치지 않도록."""
    with tempfile.TemporaryDirectory() as tmp:
        hb_p = Path(tmp) / "heartbeat.log"
        beats = []
        with worker_daemon._Heart(lambda n="": beats.append(n), interval=9999,
                            hb_path=hb_p) as hb:
            hb.set_note("실체화 중")
        assert beats == ["실체화 중"]                          # interval 없이 즉시 1회
        text = hb_p.read_text(encoding="utf-8")
        assert "[note] 실체화 중" in text and "[beat] ok" in text







def test_probe_tells_what_it_could_not_read() -> None:
    """[중요] **「없다」와 「깨졌다」를 가른다** (`#296`).

    `probe_state` 의 값이 `#277`(배달이 상주를 갱신하지 않는다) 판정의 근거다. 상태 파일을 못
    읽었을 때 조용히 빈 값으로 접으면 판정이 *"안 돈다"* 로 나오고, 그것은 **정말 안 도는 것과
    구분되지 않는다.** [주의] 파일 **부재**는 정상(첫 기동)이라 사유는 **깨진 경우만** 싣는다.
    """
    from master.work import worker_daemon as C

    tmp = Path(tempfile.mkdtemp(prefix="ax-probe-"))
    try:
        (tmp / ".ax").mkdir(parents=True)
        st = C.probe_state(tmp)
        assert "read_errors" not in st, st          # 첫 기동은 사유가 없다

        (tmp / ".ax" / C.BOOT_FILE).write_text("{깨진 JSON", encoding="utf-8")
        (tmp / ".ax" / C.ALIVE_FILE).write_text("숫자가 아니다", encoding="utf-8")
        st = C.probe_state(tmp)
        errs = st.get("read_errors") or []
        assert len(errs) == 2, errs                 # 깨진 둘을 사유로 남긴다
        assert any(C.BOOT_FILE in e for e in errs), errs   # 이름으로 말한다
        assert "running" in st and "stale" in st, st       # 판정은 계속 나온다
    finally:
        shutil.rmtree(tmp, ignore_errors=True)




def test_submit_carries_identity() -> None:
    """🔴 **고지자 신원이 없으면 빌드가 PASS 여도 거절된다** (`#318` · 실측 2026-09-12).

    `.2` 첫 실물에서 UE5 빌드를 96초에 통과하고 **submit 이 409 로 튕겼다** —
    *"worker_id 가 없다 — 고지자를 확인할 수 없다. 미확인은 통과가 아니다"*.
    `#318` 이 `#320`(상주 철거) **뒤에** 생긴 계약이라 되살린 데몬이 그 필드를 몰랐다.
    [주의] `metrics.worker` 와 다른 것이다 — 그쪽은 계측, 이쪽은 신원 게이트다.
    """
    from master.work import worker_daemon as C

    sent = {}

    class _C(C.Client):
        def __init__(self):
            self.worker_id = "192.168.0.2"
        def _call(self, method, path, payload=None):
            sent[path] = payload
            return 200, {}

    c = _C()
    c.submit("t1", head_commit="abc", build={"passed": True}, seconds=1.0)
    c.submit_fail("t1", "why", "detail")
    for path, body in sent.items():
        assert body.get("worker_id") == "192.168.0.2", f"{path} 에 신원이 없다: {body}"
    assert sent["/api/v1/tasks/t1/submit"]["metrics"]["worker"] == "192.168.0.2"

if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} 통과")
    sys.exit(1 if failed else 0)


