# 156 — #923 R298 지적 6건: issue_wrapup 하위 명령 실패/예외 방어 · next 명령 인자 보강

> 2026-11-08 · Antigravity (Gemini Flash Medium 지휘 · Argon 서브에이전트 위임) · 일감 #923 · 시작 리비전 `06f53ac` · 작업 위치 `.ax-issues/923`(`issue/923`)

## 왜

#921 커밋 `aea3f94`에 대한 자동 리뷰 **R298**(지적 6건)에서 다음 문제들이 지적되었다:
1. `run()` ⑥ 배달 `d.deliver(repo)`가 `TimeoutExpired`(1800초)·`OSError` 미처리로 traceback 종료 위험 (R298-1)
2. `run()` ② `d.git(repo, "fetch", "-q", "origin")` rc 미검사로 fetch 실패 시 낡은 origin/main과 비교해 정상 동기화로 오판 가능 (R298-2)
3. `_active_state()` systemctl 시간 초과/실패 미처리 (R298-3) — 🔴 리뷰 권고(`"?"` 반환)는 「oneshot 없음」으로 읽혀 실행 중 재기동이 되므로, 조회 실패는 **판정 불가 → 재기동 없이 멈춤(rc 1)**으로 처리
4. `run()` ① 잠금 비교 `int(lk.get("issue_id", -1))`에서 `issue_id` 값이 None일 때 `TypeError` 발생 가능 (R298-4)
5. `run()` ⑤ `git log` 조회 시 rc≠0 실패도 `RC_HANDOFF`(대기, rc 2)로 분류하는 문제 (R298-5) — rc≠0은 `RC_FAIL`(rc 1)로 즉시 멈추고 빈 커밋일 때만 rc 2
6. `master/issue_flow.py` `finish()` 반환 `next` 명령에 repo·project가 고정값(`REPO`, 생략)으로 하드코딩된 문제 (R298-6)

사용자 결정: 「응 진행해줘」, 「응 아르곤으로 서브에이전트 작동시켜」.

## 변경 내용

- **`master/issue_wrapup.py`**:
  - `_active_state()`: `subprocess.TimeoutExpired` 및 기타 예외, rc≠0, 빈 응답 시 `RuntimeError` 발생.
  - `run()` ①: `str(lk.get("issue_id")) == str(issue_id)`로 None 안전 비교 적용.
  - `run()` ②: `rc, fetch_out = d.git(repo, "fetch", "-q", "origin")` rc 검사 추가. 실패 시 `fail("repo", ...)` (rc 1).
  - `run()` ④: `d.active_state(u)` 호출 시 예외를 잡아 `fail("restart", ...)`로 즉시 멈춤(rc 1).
  - `run()` ⑤: `git log` rc≠0이면 `fail("handoff", ...)` (rc 1), `rc==0 and not commits.strip()`일 때만 rc 2(대기).
  - `run()` ⑥: `d.deliver(repo)`를 try/except로 감싸 예외 발생 시 `fail("deliver", ...)` (rc 1).
- **`master/issue_flow.py`**:
  - `finish()`: 반환 `next` 명령에 `wrap_repo = Path(repo).resolve() if repo is not None else REPO` 및 `--project {project}` 반영.
- **`master/test_issue_wrapup.py`**:
  - `World`에 `deliver_err`, `fetch_rc`, `active_err`, `handoff_log_rc` 대역 주입 지원 추가.
  - `test_r298_regressions()` 신규 추가: R298-1~5 5개 케이스 전수 회귀 검증. 기존 34건 포함 **39/39 통과**.
- **`master/test_issue_flow.py`**:
  - `t_finish_confirm()`: `r.get("next")`에 실제 repo 경로 및 `--project AXCluster` 포함 검증 추가 (**175/175 통과**).

## 검증

- `test_issue_wrapup`: rc0 **39/39** 통과.
- `test_issue_flow`: rc0 **175/175** 통과.
- `git diff --check`: rc0 (공백·포맷 결함 없음).
- `pyflakes`: 변경 파일 오류 0건.
- `test_test_runnable`: rc0 **5/5** 통과.
- 공식 통합 검사: tests/integration/checks.json 191건 전수 통과 (`Ran 191 tests in 180.701s` · `OK`).

최종 결과는 Redmine 마감 노트.
