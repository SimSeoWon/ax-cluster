# 109 — 분산 작업 완료 후속을 공통 핵심으로 (#798)

- 날짜: 2026-10-11 · 지휘: Claude (Codex 인계 인수) · 방식: 로컬 서브 에이전트 (사용자 선택)
- 커밋: `636da9c` · `7e53df0` · `30739f7` · `b7c4ebe` (문서 `fa3e91f`)
- 관련: [#798](http://192.168.0.57:8080/issues/798) · 분리 [#799](http://192.168.0.57:8080/issues/799) · 실증 대상 #632 / work 이슈 #797

## 1. 무엇이 문제였나

#632 work 가 `ready_for_review` 가 됐는데 요청자(Codex)가 완료를 조회하고도 ⑦ 준비로 이어가지 않았다.
조사로 확인한 사실:

- AXCluster 의 요청자는 마스터인데 **요청자 작업장이 등록돼 있지 않았다** — 완료 훅
  `work_completion.py`(Claude `PostToolUse`+`asyncRewake`)는 `role: requester` 작업장에만 배달되므로
  설치될 자리가 없었다. 실제 요청자 트리 `~/ax-632-work` 에 `.claude/`·`.ax/` 가 없었다.
- **Codex 훅은 유휴 세션을 깨우지 못한다** (문서 기준: async 훅 출력은 다음 사용자 턴까지 보류,
  새 턴을 열지 않는다). 후보 `codex queue --thread` 는 실측 보류.
- `distribute` 스킬에 「완료를 보면 ⑦ 준비까지 간다」는 규정이 없었다.

## 2. 사용자 결정

| 결정 | 값 |
|---|---|
| 구조 | 얇은 래핑 유지 · **공통 핵심은 Python 한 곳** · 지휘자별로 갈리는 것은 수신 어댑터뿐 |
| 수신 | 바닥 = 요청자 호스트 1분 타이머(⑦ 준비까지) · 빠른 길 = Claude 훅 |
| 요청자 작업장 | 별도 클론 `/home/sim/trunk/AXCluster-requester` (정본 `~/ax-cluster` 와 분리) |
| 첫 주기 | 기준선만 긋는다 (옛 종결 work 를 자동 준비하지 않음) |
| 결과 전달 | Redmine 노트 + `pending_works` 매 턴 고지 + 훅의 즉시 준비 |
| 클론 위치 | `~/CLAUDE.md` 가 함께 로드되는 것 수용 |
| MCP 승인 | 첫 사용 때 사람이 직접 |
| Windows 요청자 폴백 | #799 로 분리 |

## 3. 만든 것

- `master/work/followup.py` — `prepare_round`(큐 재조회 → `advance_work(confirm=False, keep_tree=True)`
  → 게이트에서 멈춤, confirm 을 인자로 열지 않음) · `prepare_once`(키 `(정본 경로, work, round)`
  잠금·기록, Redmine 노트 1회) · `scan`(1분 타이머용, 주기마다 tick 한 줄) · `code` 검사 =
  공식 통합 + 바뀐 파일의 `master/test_<stem>.py` 회귀(둘 다 통과해야 통과).
- `master/systemd/ax-followup.{service,timer}` — `--scan --project AXCluster --repo <클론>`, 1분.
- `work_completion.py` — terminal 을 보면 같은 `prepare_once` 를 불러 결과를 붙여 깨운다.
- `pending_works.py` — 「⑦ 준비 결과」 블록 고지. 문구는 사실만(명령형 부재 검사).
- `bundle.py` — **마스터 호스트 요청자는 체크아웃 안에만 배달**. 처음 `plan` 이 홈
  `~/.claude/skills`·`~/.codex/skills` 설치와 **`distribute` 스킬 삭제**를 계획하고 있어 등록을
  되돌린 뒤 고쳤다(홈 `ax-gemini` 는 저장소로 가는 심볼릭 링크라 저장소 파일까지 덮였을 것).
  codex probe PATH(`~/.local/bin`) 보정 · 요청자 페이로드에 `followup.py`·`integration_checks.py` ·
  config `kind`.
- 스킬 `distribute`·`ax-request`·`ax-advance` — 「완료 확인」으로 턴을 끝내지 않는다 · 준비된 트리를
  다시 세우지 않는다.

## 4. 배포와 실증

- `master.client update` 4대 OK (마스터 requester 포함). 배달 전후 `~/.claude/skills`·`~/.claude.json`·
  `~/.codex/config.toml`·crontab 대조 — 불변.
- `ax-followup.timer` 가동. 01:50:32 첫 주기: 열린 work 9건 전부 기준선, 준비 0.
- `ax-projects` 재시작 (22:04:44 → 01:52:04) — 마운트 전환의 `align` 이 옛 배달 코드를 쓰지 않게.
- **5a 실증(타이머·CLI 경로, 실제 큐·Redmine)** — #632 에 `followup --force`:

| 회차 | 결과 | 비고 |
|---|---|---|
| 01:52 | 통합 TESTS FAILED (7 · failures=1) | 원문이 어디에도 없었다 → `30739f7` |
| 01:58 | 같은 실패, 원문 확보 | `test_revise` 실물 git 블록 |
| 02:05 | **통합 31/31 (63.3초) · 회귀 38/38 · at_gate · push 없음** | `b7c4ebe` 뒤 |

원인: 검사 Python 을 요청자 config `backends.python` 에서 읽는데 마스터 요청자에는
`/usr/bin/python3`(pydantic 없음)가 들어 있었다. 같은 트리를 venv 로 돌리면 통과(3회).
#797 에 정정 노트를 남겼다.

## 5. 여기서 배운 것

- **배달 코드의 `plan` 을 먼저 본 것이 사고를 막았다** — 홈을 공유하는 마스터에 「요청자 기계 =
  전용 홈」 가정이 그대로 적용되면 마스터 자신의 `distribute` 스킬이 지워진다.
- **실패 판정만 남기는 검사는 디버깅을 막는다** — 원문 꼬리를 남기자 한 번에 원인이 보였다.
- **유닛 통과 ≠ 라이브 통과** — 가짜 큐 166건이 통과한 경로가 실제 환경(Python 선택)에서 깨졌다.

## 6. 남은 것

- **5b Claude 훅 경로 실증** — 요청자 클론에서 세션을 열고 작은 work 를 등재해 무입력 깨우기 +
  「⑦ 준비 결과」 수신을 확인. work 내용은 사용자가 고른다.
- #799 Windows 요청자 1분 폴백 · Codex `codex queue` 깨우기 실측 · 마스터 담당 기록(`claude`) 미기록
  (권한 분류기 거부).
- 사소: code kind 에서도 고지 문구가 「UE5 빌드」 · `build_local` 오류 문장의 명령형 「확인할 것」.
- #632: ⑦ 전진·finalize 사람 승인 대기 (검수 트리 `/home/sim/trunk/ax-advance-20261011_0035_632_redmine_e5e894a9`,
  HEAD `c65247fc`, 통합 31/31).
