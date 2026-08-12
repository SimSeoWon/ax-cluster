"""클러스터 상태 화면 (중 3.2).

🔴 지키는 계약은 다섯이다:

    ① **닿지 않는 것을 "값 없음" 으로 접지 않는다** — 빈칸은 사람이 "괜찮은가 보다" 로 읽는다
    ② **주기를 짧게 잡지 못하게 막는다** — BC-250 은 부하로 커널이 멈춘 전례가 있다
    ③ **상태는 아이콘 + 라벨 + 색** — 색만으로 의미를 전달하지 않는다
    ④ **외부 자원 0 · 새 서비스 0** — 포트를 늘리면 토큰·ufw 가 따라온다
    ⑤ 🔴 **요청자가 꺼진 것은 위험이 아니다** — 사람의 기계다 (역할로 판정이 갈린다)

`.venv/bin/python master/test_status.py`
"""
from __future__ import annotations

import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import status as S      # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


# ── 파싱·판정 ───────────────────────────────────────────────────────────────────

def test_temp_bands() -> None:
    check("55도는 정상", S.band(55.0) == S.GOOD)
    check("65도는 주의", S.band(65.0) == S.WARN)
    check("85도는 경고", S.band(85.0) == S.SERIOUS)
    check("95도는 위험", S.band(95.0) == S.CRIT)
    # 🔴 모르는 것을 정상으로 접지 않는다
    check("None 은 모름", S.band(None) == S.UNKNOWN)


def test_short_model_keeps_the_quant_suffix() -> None:
    """🔴 실측(화면 확인): 28자로 자르니 `…GGUF:IQ` 가 되어 양자화 접미사가 반쪽이 됐다."""
    long = "hf.co/bartowski/Qwen_Qwen3.5-35B-A3B-GGUF:IQ2_M"
    got = S.short_model(long)
    check("레지스트리 경로를 버린다", "hf.co" not in got, got)
    check("양자화 접미사가 온전하다", got.endswith(":IQ2_M"), got)
    check("길이 상한을 지킨다", len(got) <= 30, f"{len(got)}: {got}")
    check("짧은 것은 그대로", S.short_model("qwen2.5-coder:14b") == "qwen2.5-coder:14b")


def test_open_tasks_reads_the_real_queue_shape() -> None:
    """🔴 큐의 실제 응답으로 맞췄다 — `tasks` 는 총계, 상태별은 `tasks_by_status`."""
    snap = S.Snapshot(queue={"tasks_by_status": {"cancelled": 4, "failed": 2, "submitted": 2},
                             "works": 7, "tasks": 8})
    check("총계 - 종료분", snap.open_tasks == 2, str(snap.open_tasks))
    # 총계가 없으면 상태별에서 센다
    snap2 = S.Snapshot(queue={"tasks_by_status": {"claimed": 3, "verified": 9}})
    check("총계 없으면 상태별로", snap2.open_tasks == 3, str(snap2.open_tasks))
    check("큐 응답이 없으면 0", S.Snapshot().open_tasks == 0)
    # ⚠️ 종료 상태는 한 곳에서만 정한다
    check("종료 상태 목록이 한 군데", set(S.Snapshot.CLOSED) ==
          {"verified", "cancelled", "failed"}, str(S.Snapshot.CLOSED))


# ── ① 닿지 않는 것 · ⑤ 역할 ────────────────────────────────────────────────────

def test_unreachable_worker_is_critical_but_requester_is_not() -> None:
    """🔴 `.33` 은 사람의 기계다 — 꺼져 있는 것이 정상 상태일 수 있다."""
    w = S.Machine(host="h", role="worker", error="No route to host")
    r = S.Machine(host="h", role="requester", error="timeout")
    check("워커가 닿지 않으면 위험", w.status == S.CRIT, w.status)
    check("요청자가 닿지 않으면 주의", r.status == S.WARN, r.status)
    check("요청자에는 사람의 기계라고 적는다", "사람의 기계" in r.label, r.label)
    check("닿지 않음을 라벨로 말한다", "닿지 않음" in w.label, w.label)


def test_missing_gpu_reading_is_unknown_not_zero() -> None:
    m = S.Machine(host="h", role="worker", reachable=True)
    check("온도를 못 읽으면 모름", m.status == S.UNKNOWN, m.status)
    check("0도로 접지 않는다", m.gpu.temp is None)


# ── ② 주기 가드 ─────────────────────────────────────────────────────────────────

def test_min_interval_refuses_frequent_collection() -> None:
    """🔴 BC-250 은 부하로 커널이 멈춘 전례가 있다."""
    d = Path(tempfile.mkdtemp(prefix="axst"))
    try:
        import time
        (d / S.STAMP_NAME).write_text(str(time.time()), encoding="utf-8")
        try:
            S.collect(state_dir=d)
            check("🔴 최소 간격을 막는다", False, "통과해버렸다")
        except RuntimeError as e:
            check("최소 간격을 막는다", "최소 간격" in str(e), str(e))
            check("이유를 말한다", "커널이 멈춘" in str(e), str(e))
            check("우회 방법을 알려준다", "--force" in str(e), str(e))
        check("간격이 120초 이상", S.MIN_INTERVAL >= 120, str(S.MIN_INTERVAL))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_collection_commands_are_read_only() -> None:
    """🔴 쓰는 명령이 하나도 없어야 한다."""
    src = Path(S.__file__).read_text(encoding="utf-8")
    # 수집 명령 문자열 안에 쓰기 동작이 섞여 있지 않은지
    for bad in ("rm ", "git checkout", "git commit", "git push", "systemctl start",
                "systemctl restart", "> /", "tee "):
        check(f"🔴 `{bad.strip()}` 를 쓰지 않는다", bad not in src, bad)
    check("nvidia-smi 는 조회 전용", "--query-gpu" in S._NVIDIA)
    # ⚠️ 윈도우 cmd 에는 파이프가 없다 (실측으로 물린 함정)
    check("🔴 윈도우 명령에 파이프가 없다", "|" not in S._NVIDIA, S._NVIDIA)


# ── ③④ 렌더 불변식 ─────────────────────────────────────────────────────────────

def _sample() -> S.Snapshot:
    snap = S.Snapshot(at="2026-08-12 14:00:00Z", seconds=4.2,
                      units={"ax-broker": "active", "ax-projects": "failed"},
                      queue={"tasks_by_status": {"claimed": 1}, "tasks": 3},
                      endpoints=[{"name": "bc250", "host": "192.168.0.43:11434",
                                  "healthy": True, "resident": "hf.co/x/Y:IQ2_M",
                                  "inflight": 0, "models": ["a", "b"]}],
                      tasks=[{"task_id": "abc12345", "status": "claimed",
                              "worker": "192.168.0.2", "file": "Source/A/Foo.h",
                              "since": "2026-08-12T13:00:00", "beat": "", "attempts": 1,
                              "requires": []}])
    m = S.Machine(host="192.168.0.43", role="worker", reachable=True,
                  gpu=S.Gpu(name="AMD BC-250", temp=52.0, watts=30.2,
                            note="⬜ gpu_busy_percent 안 읽힘"))
    snap.machines.append(m)
    snap.problems.append("서비스 `ax-projects` 가 failed 다")
    return snap


def test_render_has_no_external_resources() -> None:
    h = S.render(_sample())
    refs = re.findall(r'(?:src|href)=["\']([^"\']+)', h)
    outside = [r for r in refs if not r.startswith("#")]
    check("🔴 외부 자원 0", not outside, str(outside))
    for bad in ("http://", "https://", "cdn", "//fonts"):
        check(f"`{bad}` 참조 없음", bad not in h.replace("192.168", ""), bad)


def test_render_links_the_other_screen_not_a_new_service() -> None:
    h = S.render(_sample(), viewer_link="domains.html")
    check("도메인 뷰어로 링크", 'href="domains.html"' in h)
    check("🔴 새 포트를 언급하지 않는다", ":8104" not in h and ":8105" not in h)


def test_status_is_never_color_alone() -> None:
    """🔴 색만으로 의미를 전달하면 색을 못 보는 사람에게는 아무 정보가 아니다."""
    h = S.render(_sample())
    badges = re.findall(r'<span class="st (\w+)"><i>([^<]*)</i>([^<]*)', h)
    check("배지가 있다", len(badges) >= 3, str(len(badges)))
    check("전부 아이콘 동반", all(b[1].strip() for b in badges), str(badges[:3]))
    check("전부 라벨 동반", all(b[2].strip() for b in badges), str(badges[:3]))


def test_problems_come_first_and_exactly_one_hero() -> None:
    h = S.render(_sample())
    check("🔴 히어로는 하나", h.count('class="hero"') == 1, str(h.count('class="hero"')))
    # 문제 배너가 머신 섹션보다 앞에 온다 (도메인 뷰어와 같은 판단)
    check("문제가 머신보다 먼저", h.index('class="band"') < h.index("<h2>머신</h2>"))
    check("문제 개수를 적는다", "문제 1건" in h, h[h.index('class="band"'):][:120])


def test_no_problems_says_so_positively() -> None:
    snap = _sample()
    snap.problems.clear()
    h = S.render(snap)
    check("문제 없음을 말한다", "문제 없음" in h)
    check("초록 배너", 'class="band ok"' in h)


def test_palette_matches_the_original_pages() -> None:
    """🔴 **이 화면만 다른 색이면 다른 앱으로 읽힌다** (사용자 지적 2026-08-13).

    전에 이 자리에는 *"다크는 OS 설정과 토글 양쪽에서 이긴다"* 를 검사하는 테스트가 있었다.
    그 규약 자체는 맞지만 **여기서는 틀린 규약이었다** — 이웃 화면(`/`·`/ontology`)에 라이트
    모드가 없으므로, 이 화면만 시스템 설정에 따라 흰 배경으로 뒤집히면 클러스터 화면 하나가
    혼자 다른 앱처럼 보인다. 그래서 검사를 **팔레트 일치**로 바꿨다: 값을 원전에서 읽어와
    대조하므로, 원전이 바뀌면 이 테스트가 알려 준다(내가 손으로 베낀 값을 믿지 않는다).
    """
    h = S.render(_sample())
    from master.webui.web_ui_original import WEB_UI_HTML
    m = re.search(r":root\s*\{([^}]*)\}", WEB_UI_HTML)
    check("원전에서 :root 를 읽었다", m is not None)
    if m:
        orig = dict(re.findall(r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{3,8})", m.group(1)))
        # 원전 토큰 이름 → 우리 토큰 이름
        for theirs, ours in (("--bg", "--bg"), ("--surface", "--card"), ("--border", "--line"),
                             ("--text", "--fg"), ("--dim", "--dim"), ("--accent", "--accent"),
                             ("--green", "--good"), ("--orange", "--warning"),
                             ("--red", "--critical")):
            want = (orig.get(theirs) or "").lower()
            check(f"{ours} = 원전 {theirs} ({want})",
                  bool(want) and f"{ours}:{want}" in h.lower(), f"원전값 {want!r}")
    check("🔴 라이트 모드 분기를 두지 않는다 — 이웃 화면에 없다",
          "prefers-color-scheme" not in h)
    check("배경을 명시한다 — 투명한 body 는 호스트 색을 빌린다", "background:var(--bg)" in h)


def test_meter_track_is_same_ramp_and_scale_is_labeled() -> None:
    """미터는 눈금 의미가 없으면 장식이다."""
    h = S.render(_sample())
    check("트랙이 같은 램프", "color-mix(in oklab" in h, "color-mix 없음")
    check("중립 트랙 폴백이 먼저", h.index("background:var(--track)") <
          h.index("color-mix(in oklab"))
    check("눈금을 적는다", "주의 60" in h and "100°C" in h)
    check("접근성 라벨", 'aria-label="온도 52도' in h, "aria-label 없음")


def test_measured_caveats_are_on_screen() -> None:
    """🔴 관례를 실측처럼 보이게 두지 않는다."""
    h = S.render(_sample())
    check("임계값이 관례라고 적는다", "관례" in h)
    check("읽기 전용임을 적는다", "읽기 전용" in h)
    check("추세 그래프를 왜 안 넣었는지 적는다", "희박" in h)
    check("안 읽히는 값을 적는다", "gpu_busy_percent" in h)


def test_in_flight_tasks_are_shown() -> None:
    """🔴 사용자가 요청한 항목: *"뭘 시작했고"* (소 3.2.3)."""
    h = S.render(_sample())
    check("진행 중 절이 있다", "진행 중인 작업" in h)
    check("태스크·워커를 보인다", "abc12345" in h and "192.168.0.2" in h)
    snap = _sample()
    snap.tasks.clear()
    check("없으면 없다고 적는다", "큐가 비어 있다" in S.render(snap))


def test_refresh_is_wired_to_a_timer_and_the_numbers_agree() -> None:
    """🔴 *"지금 70분째 갱신 안되는데?"* (사용자 2026-08-13) — 갱신은 **타이머**의 일이다.

    브라우저 새로고침으로 수집을 유발할 수는 없다(그게 `MIN_INTERVAL` 가드의 목적이다). 그러면
    갱신 주체는 유닛뿐인데, 그 주기가 코드와 유닛 파일 **두 곳**에 적히므로 어긋날 수 있다.
    어긋나면 화면이 "5분마다 갱신" 이라 적어 놓고 실제로는 안 하는, **거짓말하는 화면**이 된다.
    """
    from master import viewer as V
    unit_dir = Path(__file__).resolve().parent / "systemd"
    timer = (unit_dir / "ax-status.timer").read_text(encoding="utf-8")
    svc = (unit_dir / "ax-status.service").read_text(encoding="utf-8")

    m = re.search(r"OnUnitActiveSec=(\d+)(min|s)", timer)
    check("타이머에 주기가 있다", m is not None)
    if m:
        sec = int(m.group(1)) * (60 if m.group(2) == "min" else 1)
        check(f"REFRESH_SEC({S.REFRESH_SEC}) = 타이머 주기({sec})", S.REFRESH_SEC == sec)
    check(f"🔴 주기({S.REFRESH_SEC}) < 낡음 임계값({V.STALE_SEC}) — 늘 뜨는 경고는 안 읽힌다",
          S.REFRESH_SEC < V.STALE_SEC)
    check(f"주기({S.REFRESH_SEC}) > 최소 간격({S.MIN_INTERVAL}) — 가드에 상습적으로 걸리지 않는다",
          S.REFRESH_SEC > S.MIN_INTERVAL)
    check("화면이 갱신 주체를 밝힌다", "ax-status.timer" in S.render(_sample()))

    # 🔴 가드에 걸린 것은 고장이 아니다 — 유닛이 그 코드를 성공으로 받아야 한다
    check(f"유닛이 SuccessExitStatus={S.EXIT_TOO_SOON}",
          f"SuccessExitStatus={S.EXIT_TOO_SOON}" in svc)
    check("⚠️ 1 은 성공으로 받지 않는다 — 진짜 실패는 실패여야 한다",
          "SuccessExitStatus=1" not in svc)
    check("TooSoon 은 RuntimeError 의 하위형이다(기존 처리와 호환)",
          issubclass(S.TooSoon, RuntimeError))
    # 유닛이 fail-closed 환경변수를 넘겨야 한다 — 첫 실행이 이것 때문에 죽었다(실측)
    check("유닛이 AX_PROJECTS_ROOT 를 준다", "AX_PROJECTS_ROOT=" in svc)
    check("유닛 PATH 에 ~/.local/bin", "/home/sim/.local/bin" in svc)
    check("⚠️ 쓰기 명령이 유닛에 없다", "--force" not in svc and "push" not in svc)


def main() -> int:
    for fn in (test_temp_bands, test_short_model_keeps_the_quant_suffix,
               test_open_tasks_reads_the_real_queue_shape,
               test_unreachable_worker_is_critical_but_requester_is_not,
               test_missing_gpu_reading_is_unknown_not_zero,
               test_min_interval_refuses_frequent_collection,
               test_collection_commands_are_read_only,
               test_render_has_no_external_resources,
               test_render_links_the_other_screen_not_a_new_service,
               test_status_is_never_color_alone,
               test_problems_come_first_and_exactly_one_hero,
               test_no_problems_says_so_positively,
               test_palette_matches_the_original_pages,
               test_meter_track_is_same_ramp_and_scale_is_labeled,
               test_measured_caveats_are_on_screen,
               test_refresh_is_wired_to_a_timer_and_the_numbers_agree,
               test_in_flight_tasks_are_shown):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_status: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
