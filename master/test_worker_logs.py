"""#220 ③-B — 워커 로그 회수와 열람 계약.

핵심 계약:
① 회수는 **이미 SSH 를 타는 순간**에만 — 화면은 로컬 사본만 읽는다 (서빙 중 scp 금지;
   15초 자동 리로드가 BC-250 을 두드리게 된다 — #105·120초 가드)
② 없는 것과 못 읽은 것을 섞지 않는다 — 빈 문자열은 「없다」, 예외는 사유째 요약에
③ 자른 것은 잘랐다고 적는다 (파일 꼬리·태스크 상한 둘 다)
④ 원격 경로는 claimer 의 규약(`.ax/logs/claimer_debug/<task_id>/`)과 같아야 한다 —
   윈도우는 역슬래시

실행: .venv/bin/python master/test_worker_logs.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import status as S                                    # noqa: E402
from master.work import logs as L                                 # noqa: E402


def _paths(tmp) -> SimpleNamespace:
    return SimpleNamespace(root=Path(tmp), name="P")


def _facts(host="192.168.0.2", windows=True, path="E:\\trunk\\ModularStage"):
    return SimpleNamespace(host=host, user="u", path=path, windows=windows)


# ── ④ 원격 경로 규약 ──────────────────────────────────────────

def test_remote_path_matches_claimer_convention():
    win = L._remote_path(_facts(), "t1", "heartbeat.log")
    assert win == "E:\\trunk\\ModularStage\\.ax\\logs\\claimer_debug\\t1\\heartbeat.log", win
    lin = L._remote_path(_facts("192.168.0.43", False, "/home/sim/trunk/ModularStage"),
                         "t1", "llm_stdout.log")
    assert lin == "/home/sim/trunk/ModularStage/.ax/logs/claimer_debug/t1/llm_stdout.log", lin


# ── ①② 회수 ──────────────────────────────────────────────────

def test_collect_task_logs_stores_only_existing_files():
    with tempfile.TemporaryDirectory() as tmp:
        paths = _paths(tmp)

        def reader(facts, p):
            if p.endswith("heartbeat.log"):
                return "[beat] ok\n"
            if p.endswith("llm_stdout.log"):
                return "RESULT: DONE\n"
            return ""                       # 없는 파일 — 정상
        got = L.collect_task_logs(paths, _facts(), "t1", reader=reader)
        assert sorted(got) == ["heartbeat.log", "llm_stdout.log"], got
        d = L.store_dir(paths, "t1")
        assert (d / "heartbeat.log").read_text(encoding="utf-8") == "[beat] ok\n"
        assert not (d / "build.log").exists()
        meta = json.loads((d / L.META_NAME).read_text(encoding="utf-8"))
        assert meta["host"] == "192.168.0.2" and meta["at"]


def test_collect_reports_reader_failure_and_keeps_going():
    """못 읽은 것은 사유째 요약에 남고, 다른 태스크 회수를 막지 않는다."""
    with tempfile.TemporaryDirectory() as tmp:
        paths = _paths(tmp)
        tasks = [{"task_id": "bad", "status": "failed", "worker_id": "h1",
                  "claimed_at": "2026-08-19T10:00:00"},
                 {"task_id": "ok", "status": "claimed", "worker_id": "h1",
                  "claimed_at": "2026-08-19T09:00:00"}]

        def reader(facts, p):
            if "/bad/" in p or "\\bad\\" in p:
                raise OSError("scp 실패")
            return "본문\n" if p.endswith("heartbeat.log") else ""
        got = L.collect(paths, facts=[_facts("h1", False, "/w")],
                        api=lambda m, path, b=None: tasks, reader=reader)
        assert got["tasks"] == 1 and got["files"] == 1
        assert any("회수 실패" in ln and "bad" in ln for ln in got["lines"]), got["lines"]


def test_collect_skips_unknown_host_and_closed_tasks():
    with tempfile.TemporaryDirectory() as tmp:
        paths = _paths(tmp)
        tasks = [{"task_id": "a", "status": "verified", "worker_id": "h1"},   # 종료 — 대상 아님
                 {"task_id": "b", "status": "claimed", "worker_id": "없는호스트"}]
        got = L.collect(paths, facts=[_facts("h1", False, "/w")],
                        api=lambda m, path, b=None: tasks,
                        reader=lambda f, p: "x")
        assert got["tasks"] == 0
        assert any("레지스트리에 없다" in ln for ln in got["lines"]), got["lines"]


def test_host_log_falls_back_to_earlier_day_and_marks_it():
    """[중요] 상주 claimer 는 일이 있을 때만 기록한다 — 오늘자 파일이 없는 것이 정상이고,
    오늘만 보면 화면이 대부분 빈칸이 된다. 되짚되 **몇 일 전 파일인지 적는다**."""
    with tempfile.TemporaryDirectory() as tmp:
        paths = _paths(tmp)
        f = _facts("h1", False, "/w")

        def reader(facts, p):
            return "어제 부팅\n" if "claimer_2026-08-18.log" in p else ""
        n = L.collect_host_log(paths, f, reader=reader, day="2026-08-19")
        assert n > 0
        text = L.host_store(paths, "h1").read_text(encoding="utf-8")
        assert "claimer_2026-08-18.log" in text and "오늘자가 아니다" in text
        assert "어제 부팅" in text
        # 오늘자가 있으면 그것을 쓰고 경고를 붙이지 않는다
        def reader2(facts, p):
            return "오늘\n" if "claimer_2026-08-19.log" in p else "어제\n"
        L.collect_host_log(paths, f, reader=reader2, day="2026-08-19")
        text2 = L.host_store(paths, "h1").read_text(encoding="utf-8")
        assert "오늘자가 아니다" not in text2 and "오늘" in text2


def test_host_log_skips_requester_role():
    """요청자(.33)에는 데몬이 없다 — 걷으러 가지 않는다."""
    with tempfile.TemporaryDirectory() as tmp:
        calls = []

        def reader(facts, p):
            calls.append(facts.host)
            return ""
        req = SimpleNamespace(host="192.168.0.33", user="u", path="C:\\p",
                              windows=True, role="requester")
        wk = SimpleNamespace(host="h1", user="u", path="/w", windows=False, role="worker")
        L.collect(_paths(tmp), facts=[req, wk],
                  api=lambda m, path, b=None: [], reader=reader)
        assert "192.168.0.33" not in calls and "h1" in calls


def test_read_host_logs_and_section_render():
    with tempfile.TemporaryDirectory() as tmp:
        paths = _paths(tmp)
        L.collect_host_log(paths, _facts("h1", False, "/w"),
                           reader=lambda f, p: "\n".join(f"<l{i}>" for i in range(60)))
        got = L.read_host_logs(paths)
        assert list(got) == ["h1"]
        out = S.daemon_log_section(got)
        assert "워커 데몬 로그" in out and "&lt;l59&gt;" in out and "&lt;l0&gt;" not in out
        assert S.daemon_log_section({}) == ""


def test_collect_says_when_target_has_no_logs():
    """[중요] 「파일 0」이 「대상 없음」인지 「로그 없음」인지 구별돼야 한다 (실측 2026-08-19:
    첫 라이브 회수가 한 줄도 안 내놓아 원인을 알 수 없었다)."""
    with tempfile.TemporaryDirectory() as tmp:
        tasks = [{"task_id": "t1", "status": "failed", "worker_id": "h1"}]
        got = L.collect(_paths(tmp), facts=[_facts("h1", False, "/w")],
                        api=lambda m, path, b=None: tasks, reader=lambda f, p: "")
        assert got["targets"] == 1 and got["files"] == 0 and got["empty"] == 1
        assert any("로그 없음" in ln for ln in got["lines"]), got["lines"]


def test_collect_says_when_queue_unreadable():
    with tempfile.TemporaryDirectory() as tmp:
        def api(*a, **k):
            raise OSError("큐 죽음")
        got = L.collect(_paths(tmp), facts=[], api=api)
        assert got["tasks"] == 0 and any("큐를 못 읽었다" in ln for ln in got["lines"])


def test_collect_caps_task_count_and_says_so():
    with tempfile.TemporaryDirectory() as tmp:
        tasks = [{"task_id": f"t{i}", "status": "claimed", "worker_id": "h1",
                  "claimed_at": f"2026-08-19T{i % 24:02}:00:00"} for i in range(L.MAX_TASKS + 3)]
        got = L.collect(_paths(tmp), facts=[_facts("h1", False, "/w")],
                        api=lambda m, path, b=None: tasks,
                        reader=lambda f, p: "x\n" if p.endswith("build.log") else "")
        assert got["tasks"] == L.MAX_TASKS
        assert any("걷지 않았다" in ln for ln in got["lines"]), got["lines"]


# ── ③ 자른 것은 적는다 ───────────────────────────────────────

def test_tail_marks_truncation():
    small = "짧다\n"
    assert L._tail(small) == small
    big = "".join(f"line{i}\n" for i in range(20000))
    cut = L._tail(big, limit=200)
    assert "앞부분 잘림" in cut and cut.endswith("line19999\n")
    assert len(cut.encode("utf-8")) < 400


# ── 열람 (화면 경로) ─────────────────────────────────────────

def test_read_stored_returns_files_and_age_source():
    with tempfile.TemporaryDirectory() as tmp:
        paths = _paths(tmp)
        L.collect_task_logs(paths, _facts(), "t1",
                            reader=lambda f, p: "본문\n" if p.endswith("build.log") else "")
        got = L.read_stored(paths, ["t1", "없는것"])
        assert list(got) == ["t1"]
        assert got["t1"]["files"]["build.log"] == "본문\n"
        assert got["t1"]["host"] == "192.168.0.2" and got["t1"]["at"]


def test_read_stored_without_meta_still_shows_files():
    """메타가 없어도 파일은 보여 준다 — 나이만 모른다."""
    with tempfile.TemporaryDirectory() as tmp:
        paths = _paths(tmp)
        d = L.store_dir(paths, "t2")
        d.mkdir(parents=True)
        (d / "heartbeat.log").write_text("beat\n", encoding="utf-8")
        got = L.read_stored(paths, ["t2"])
        assert got["t2"]["files"]["heartbeat.log"] == "beat\n" and got["t2"]["at"] == ""


def test_log_block_renders_tail_with_age_and_escape():
    stored = {"at": "2026-08-19T10:00:00+09:00", "host": "192.168.0.2",
              "files": {"llm_stdout.log": "\n".join(f"<line{i}>" for i in range(60))}}
    out = S.log_block("t1", stored)
    assert "<details" in out and "192.168.0.2" in out
    assert "&lt;line59&gt;" in out                 # 이스케이프 + 꼬리
    assert "&lt;line0&gt;" not in out              # 앞부분은 안 보인다
    assert f"앞 {60 - S.LOG_SHOW_LINES}줄 생략" in out
    assert S.log_block("t1", None) == "" and S.log_block("t1", {}) == ""


def test_work_section_shows_log_for_submitted_task():
    """[중요] 실측 2026-08-19: 빌드가 끝나 `submitted`(검증 대기)가 되면 진행 중도 실패도
    아니어서 **회수해 둔 로그를 볼 길이 사라졌다.** 닫히지 않은 태스크면 보여 준다."""
    works = [{"work_id": "W", "merge_status": "in_progress", "total": 1}]
    tasks = [{"task_id": "s1", "work_id": "W", "status": "submitted"}]
    logs = {"s1": {"at": "", "host": "h", "files": {"build.log": "BUILD OK(128.3s)"}}}
    out = S.work_section(works, tasks, logs=logs)
    assert "BUILD OK(128.3s)" in out and "submitted" in out
    # 닫힌 태스크는 안 보여 준다 (끝난 일의 로그는 work 이력으로 남는다)
    done = [{"task_id": "s1", "work_id": "W", "status": "verified"}]
    assert "BUILD OK" not in S.work_section(works, done, logs=logs)


def test_work_section_does_not_duplicate_failed_task_log():
    works = [{"work_id": "W", "merge_status": "in_progress", "total": 1}]
    tasks = [{"task_id": "f1", "work_id": "W", "status": "failed", "fail_reason": "x"}]
    logs = {"f1": {"at": "", "host": "h", "files": {"build.log": "표식하나"}}}
    out = S.work_section(works, tasks, logs=logs)
    assert out.count("표식하나") == 1                 # 실패 행에서 한 번만


def test_work_section_embeds_log_for_failed_and_running():
    works = [{"work_id": "W", "merge_status": "in_progress", "total": 2}]
    tasks = [{"task_id": "f1", "work_id": "W", "status": "failed",
              "fail_reason": "build-setup"},
             {"task_id": "r1", "work_id": "W", "status": "claimed"}]
    logs = {"f1": {"at": "", "host": "h", "files": {"build.log": "UBT 실패"}},
            "r1": {"at": "", "host": "h", "files": {"heartbeat.log": "[beat] ok"}}}
    out = S.work_section(works, tasks, logs=logs)
    assert "UBT 실패" in out and "[beat] ok" in out
    assert "claimed <code>r1</code>" in out          # 상태 라벨 + 태스크 id
    # 로그가 없으면 블록 자체가 없다 (빈 details 를 만들지 않는다)
    assert "<details" not in S.work_section(works, tasks)


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
