"""`/cluster` v2 (#216) 계약 테스트 — 실시간 층·토폴로지·이벤트 갱신.

핵심 계약 셋:
① 실시간 층은 **마스터 자신의 상태만** 다루고, 못 읽으면 사유를 화면에 적는다 (조용한 빈칸 금지)
② 스냅샷에는 LIVE_MARK 가 있고, 머신 카드에 토폴로지 클릭이 착지할 id 가 있다
③ refresh_after_event 는 백그라운드로 던질 뿐 — 실패해도 예외를 밖으로 내지 않는다

실행: python3 master/test_status_live.py  (순수 로직 — venv 불필요)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from master import status as S                                  # noqa: E402


def _snap(machines=2):
    s = S.Snapshot(at="2026-08-17 12:00:00Z")
    s.units = {"ax-task-queue": "active", "ax-broker": "active"}
    hosts = ["192.168.0.2", "192.168.0.43", "192.168.0.33"]
    roles = ["worker", "worker", "requester"]
    for i in range(machines):
        m = S.Machine(host=hosts[i], role=roles[i], reachable=True)
        m.gpu.temp = 50.0
        s.machines.append(m)
    return s


# ── ① 실시간 층 ────────────────────────────────────────────────

def test_live_error_is_visible_not_blank():
    out = S.live_section(None, None, None, error="큐(8101)가 응답하지 않는다")
    assert "실시간 층을 못 읽었다" in out and "8101" in out


def test_live_counts_open_and_skips_closed():
    q = {"tasks_by_status": {"claimed": 2, "verified": 5, "cancelled": 1}}
    out = S.live_section(q, [], [])
    assert "열린 태스크 <b>2</b>" in out           # verified·cancelled 는 닫힌 것


def test_live_task_rows_and_escape():
    tasks = [{"task_id": "abcd1234ffff", "status": "claimed", "assignee": "192.168.0.2",
              "target_file": "Source/<B>.cpp", "claimed_at": "2026-08-17T12:00:00"},
             {"task_id": "done00000000", "status": "verified"}]
    out = S.live_section({}, tasks, [])
    assert "abcd1234" in out and "done0000" not in out   # 닫힌 행은 안 그린다
    assert "&lt;B&gt;.cpp" in out                        # 이스케이프


def test_live_endpoint_inflight_shown():
    eps = [{"name": "bc250", "healthy": True, "inflight": 1},
           {"name": "rtx3060", "healthy": False, "inflight": 0}]
    out = S.live_section({}, [], eps)
    assert "추론 중 1건" in out and "유휴" in out and "unhealthy" in out


def test_live_empty_queue_says_so():
    out = S.live_section({"tasks_by_status": {}}, [], [])
    assert "큐가 비어 있다" in out


# ── ② 스냅샷 쪽 자리 ────────────────────────────────────────────

def test_render_has_live_mark_and_tile_ids():
    html_text = S.render(_snap())
    assert S.LIVE_MARK in html_text
    assert 'id="m-192.168.0.2"' in html_text


def test_topology_draws_master_and_clickable_nodes():
    svg = S.topology_svg(_snap(3))
    assert ".57 master" in svg
    assert svg.count('onclick="axGo(') == 3             # 머신 수만큼 클릭 노드 (함수 정의 제외)
    assert "m-192.168.0.33" in svg
    assert "<script>" in svg                            # 클릭 핸들러 동봉 (자립형)


def test_topology_empty_machines_is_empty():
    assert S.topology_svg(S.Snapshot()) == ""


# ── ②-1 최근 추론·활동 피드 (#216 후속) ────────────────────────

def test_live_recent_inference_chips():
    rec = [{"at": "12:00:01", "model": "gemma4:e4b", "endpoint": "bc250", "ms": 8700, "ok": True},
           {"at": "12:00:02", "model": "qwen3:8b", "endpoint": "rtx3060", "ms": 300, "ok": False}]
    out = S.live_section({}, [], [], recent=rec)
    assert "최근 추론" in out and "8.7s" in out and "실패" in out


def test_live_activity_feed():
    act = [{"at": "08-18 00:30", "kind": "토론", "detail": "사이클 1 <시작>"}]
    out = S.live_section({}, [], [], activity=act)
    assert "마스터 활동" in out and "토론" in out and "&lt;시작&gt;" in out


def test_activity_roundtrip_and_cap(tmp_root=None):
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(S.ACTIVITY_KEEP + 10):
            S.log_activity(tmp, "k", f"d{i}")
        got = S.read_activity(tmp, limit=3)
        assert [x["detail"] for x in got] == [f"d{S.ACTIVITY_KEEP + 9 - j}" for j in range(3)]
        lines = (S.Path(tmp) / S.ACTIVITY_NAME).read_text(encoding="utf-8").splitlines()
        assert len(lines) <= S.ACTIVITY_KEEP    # 무한히 자라지 않는다


def test_activity_missing_file_is_empty():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        assert S.read_activity(tmp) == []


# ── ③ 이벤트 갱신 ───────────────────────────────────────────────

def test_refresh_spawns_status_html():
    seen = []
    msg = S.refresh_after_event("파견", project="P", spawner=lambda cmd: seen.append(cmd))
    assert "파견" in msg and len(seen) == 1
    assert seen[0][-3:] == ["master.status", "html", "P"] or "master.status" in seen[0]
    assert "html" in seen[0] and "P" in seen[0]


def test_refresh_failure_is_message_not_exception():
    def boom(cmd):
        raise OSError("no exec")
    msg = S.refresh_after_event("통합", spawner=boom)
    assert msg.startswith("[주의]") and "통합" in msg


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
