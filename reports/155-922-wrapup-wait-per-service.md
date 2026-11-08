# 155 — #922 issue_wrapup 후속: 서비스별 oneshot 대기 · rc 2 노트

> 2026-11-08 · Claude · 일감 #922 · 시작 리비전 `2ea5058` · 작업 위치 `.ax-issues/922`(`issue/922`)

## 왜

#921 자기 마감 실경로(20:54~21:03)에서 두 가지가 드러났다.

1. ax-projects 하나를 재기동하는데 **색인기 510초를 기다렸다** — 마감 push 가 매번 색인을 깨우므로 매 마감 수 분.
2. rc 2(인수인계 대기) 경로가 Redmine 노트를 남기지 않아 1차의 재기동이 2차 노트(「재기동 없음」)에서 빠졌다.

사용자 「응 진행해줘」(배달 + 후속 개선). 설계 갈림길 없이 소스 대조로 정했다.

## oneshot → 실행 중 부르는 상주 (소스 대조)

| oneshot | 실행 중 쓰는 상주 | 근거 |
|---|---|---|
| 리뷰 큐 | broker 8102(초고) | `review_runner.py:48` — 8103 은 게시판 링크 문자열(`:542`)뿐 |
| 색인기 | broker(합성) · 8101 은 시작 때 게이트 1회 | `synth.py:9` · `events/gate.py` |
| 파견 | task-queue 8101 | `ax-dispatch.service` → `autodispatch --drain` |
| — | ax-projects 8103 을 실행 중 부르는 oneshot 없음 | — |

## 변경 (`master/issue_wrapup.py`)

- `WAIT_FOR` — `ax-broker` ← 리뷰 큐·색인기 · `ax-task-queue` ← 파견 · `ax-projects` ← 없음. 표에 없는 상주는 종전대로
  셋 다 기다린다. 기다릴 목록을 로그 한 줄로 찍는다.
- rc 2 에서도 「1단계: main · 재기동 · 인수인계서 대기(배달 전 정지, rc 2)」 노트를 남긴다(실패는 [주의] 로그, rc 는 2 유지).

## 검증

- `test_issue_wrapup` rc0 **34/34** — 기존 29 중 「rc2 는 노트 없음」 계약 1건을 「rc2 노트 1회」로 갱신 + 신규 5
  (projects 만 재기동 → 대기·상태 조회 0 · task-queue → 파견만 · broker → 리뷰 큐·색인기 · 모르는 상주는 전부).
- `test_test_runnable` 5/5 · 정적(`pystatic`, 기준 `2ea5058`): pyflakes·import·mypy 차단 0.
- 공식 통합(정본 명령, worktree): rc0 **`Ran 191 tests in 180.731s`·`OK`(191/191)**.
- 실경로: 이 일감 자기 마감에 `master.issue_wrapup 922` — 결과는 Redmine 마감 노트.

최종 결과는 Redmine 마감 노트.
