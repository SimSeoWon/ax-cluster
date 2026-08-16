"""유휴 배치 — 원전 `watch.py` 유휴 사이클의 리눅스 대응 (소 3.4.4 · `#192`).

[중요] **폴링 루프가 아니다.** `docs/3-open-items.md` §5.4.2 가 *"`watch.py` 의 `while True`
폴링 루프는 이식 대상이 아니다"* 로, §5.4.3 이 *"systemd 에 넘긴다"* 로 확정했다 —
자리는 `ax-batch.timer` 다.

    gates   시간 게이트 (원전 `watch_state` 84~233 이식)
    run     구동 주체 + CLI — [중요] `plan` 이 기본이다
"""
