"""`#323` — 파견 기록이 화면에 닿나 (**스풀에서 읽는다, SSH 0**).

## [중요] 이 파일은 `test_worker_logs.py` 였다

종전에는 **작업장의 `claimer` 로그를 SSH 로 걷는 것**을 쟀다. 그 상주가 `#320` 으로 철거되며
걷을 대상이 사라졌고, 회수는 **결과가 정해진 SSH**(5분마다, 언제나 「로그 없음」)가 됐다.
`#323` 이 그 경로를 걷어내고 **스풀**(파견이 이미 마스터 디스크에 쓴다)로 갈아 끼웠다.

    걷어낸 검사   `_remote_path` 규약 · `collect*` 계열 · `_hosts/` 일별 로그 · `_tail` 절단
                 → 전부 claimer 전용이었다. 대상이 없는 것을 재는 검사는 남기지 않는다.
    살린 검사     `log_block`·`work_section` 렌더 — **화면 쪽 계약은 안 바뀌었다.**
                 반환 모양(`{at, host, files}`)을 같게 둔 것이 그 뜻이다.
    새 검사       `read_runs` — 스풀에서 읽고, 최신만 남기고, 빈 것을 조용히 넘기지 않는다
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import status as S                                   # noqa: E402
from master.work import logs as L                                # noqa: E402


class _P:
    """`ProjectPaths` 대역 — 이 모듈이 보는 것은 `responses` 뿐이다."""
    def __init__(self, root: Path):
        self.root = root
        self.responses = root / "responses"
        self.name = "T"


def _spool(paths, work_id: str, task_id: str, **kw) -> None:
    d = paths.responses / work_id
    d.mkdir(parents=True, exist_ok=True)
    rec = {"task_id": task_id, "work_id": work_id, "worker": "192.168.0.2",
           "status": "DONE", "at": "2026-08-28T00:00:00Z", "tail": "RESULT: DONE"}
    rec.update(kw)
    (d / f"{task_id}.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")


def test_read_runs_reads_the_spool_not_the_workers():
    """[중요] 재료가 **마스터 디스크**다 — 원격을 타지 않는다."""
    with tempfile.TemporaryDirectory() as td:
        p = _P(Path(td))
        _spool(p, "W1", "t1", tail="첫 조각\nRESULT: DONE")
        _spool(p, "W1", "t2", at="2026-08-28T01:00:00Z", status="BLOCKED",
               tail="", reason="매니페스트 불일치")
        got = L.read_runs(p)
        assert set(got) == {"t1", "t2"}, got
        assert got["t1"]["host"] == "192.168.0.2"
        assert "첫 조각" in got["t1"]["files"]["워커 stdout 꼬리"]
        # [중요] 본문이 없어도 **사유**가 있으면 그것을 보여 준다
        assert "매니페스트 불일치" in got["t2"]["files"]["사유"], got["t2"]
        assert got["t2"]["status"] == "BLOCKED"


def test_read_runs_filters_and_keeps_latest():
    with tempfile.TemporaryDirectory() as td:
        p = _P(Path(td))
        _spool(p, "W1", "t1", at="2026-08-28T00:00:00Z", tail="옛것")
        _spool(p, "W2", "t1", at="2026-08-28T02:00:00Z", tail="새것")
        got = L.read_runs(p)
        assert list(got) == ["t1"]
        # [중요] 같은 태스크가 여러 번 파견됐으면 **최신 것**만 — 낡은 것을 최신인 척 보이지 않는다
        assert "새것" in got["t1"]["files"]["워커 stdout 꼬리"], got
        assert L.read_runs(p, ["없는것"]) == {}


def test_read_runs_does_not_swallow_empty():
    """[중요] 「기록 없음」이 「파견 안 함」인지 「남긴 것이 없음」인지 구분돼야 한다."""
    with tempfile.TemporaryDirectory() as td:
        p = _P(Path(td))
        _spool(p, "W1", "t1", tail="", reason="", notes=[])
        got = L.read_runs(p)
        assert "(비어 있음)" in got["t1"]["files"], got
        assert "파견은 됐는데" in got["t1"]["files"]["(비어 있음)"]


def test_read_runs_survives_broken_record():
    with tempfile.TemporaryDirectory() as td:
        p = _P(Path(td))
        _spool(p, "W1", "t1")
        (p.responses / "W1" / "broken.json").write_text("{ 깨짐", encoding="utf-8")
        # 깨진 스풀 한 건이 화면을 죽이지 않는다
        assert list(L.read_runs(p)) == ["t1"]


def test_no_ssh_surface_left():
    """[중요] 걷어낸 경로가 되살아나지 않는지 — 이름으로 잰다."""
    for gone in ("collect", "collect_task_logs", "read_host_logs", "read_stored", "DEBUG_REL"):
        assert not hasattr(L, gone), f"{gone} 이 남아 있다 — SSH 회수가 되살아났다"
    assert not hasattr(S, "daemon_log_section"), "「워커 데몬 로그」 절이 되살아났다"


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
