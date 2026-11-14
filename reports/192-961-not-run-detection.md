# 192 — #961 ‘검사 실행 안 함’ 검출 누락 수정

2026-11-14 · Codex · 사용자 선택으로 이 세션에서 직접 처리.

## 사용자 지시와 합의

- #908 구현 확인 결과를 전달했다. 기존 `test_plan_tools`는 74/74 rc0이지만
  `커밋 abc1234 · 검사 실행 안 함`의 `evidence_warning()` 반환은 빈 문자열이었다.
- 사용자 「응 우선 일감 추가해」로 #961을 마일스톤 8 - 버그/개선에 등록했다.
- 착수 지시 「961번 진행하자!」 뒤 범위 확인에서 사용자:
  - 「검사 실행 안 함 부분을 처리하려고 추가했어」
  - 「내가 원한건 저걸 전달받아서 수정해야 된다고 일감 추가한거야!」
  - 「응 진행해」
- 지휘자가 목적을 경고 문구 추가처럼 다시 물은 것은 잘못이었다. 개발 목적은 기존 경고가
  누락되는 검출 로직 수정이다. 이 목적을 다시 묻지 않고 T1(수정·회귀 검사),
  T2(공식 통합·리포트·마감·재기동 판정·배달)를 제시했다.
- 사용자 「이 세션에서 직접 처리하자」로 제시한 플랜의 수행 방식을 선택했다.
  이 범위의 일감 완결 승인은 공용 규칙 §1.9를 따른다.
- 다른 표현 전체 확장, 새 경고·거절 정책, #960, 과거 완료 기록 소급은 하지 않는다.

## 경로와 도구 근거

- `ax-plan`·`ax-redmine`·`distribute`·`ax-deliver` 기존 스킬과 MCP를 사용했다.
- RAG request_id `06dcd8698be5454f807dbfbdf3560958`.
  트윈의 `context/master/plan_tools.md`·`test_plan_tools.md` 전문을 읽고 현재 소스와 대조했다.
  합성 문서는 #908 이전 코드이므로 현재 계약으로 보지 않았다.
- `plan_start_tool(961)`: `verdict: plan_needed`, `ok: false`, `spec_missing: []`.
  제목 여섯 개 충족은 사용자 합의 증거가 아니다. 위 사용자 지시와 플랜 제시를 따로 기록했다.
- `plan_set_tool`: `ok: true`, `created: true`, `added: [T1, T2]`, `spec_missing: []`.
- `issue_start_tool(961)` 원문 필드:
  - `ok: true`, `branch: issue/961`, `already: false`, `lock: acquired`
  - `repo: /home/sim/ax-cluster/.ax-issues/961`
  - `checkout: /home/sim/ax-cluster`
  - `start_rev: 5729a1cf500bf905a6c720201d29ea347adac280`
  - `author: {client: codex-mcp-client, family: codex, authors: [codex]}`
  - `done`·`why` 필드는 이 성공 응답에 없었다.
- 편집·검사·커밋은 응답의 repo에서 했다. 운영 체크아웃은 main으로 유지했다.

## 구현과 실행 관측

- T1 커밋 `897a7e7c78441f9003203f2c5ce7b80596fa1101`.
- `master/plan_tools.py`의 `NOT_RUN_RE`에 `실행 안 함` 선택지를 추가했다.
  검사·테스트·실증·코드 실행이라는 기존 앞쪽 조건과 기존 간격·문장 경계는 유지했다.
  `안 함` 전체로 넓히지 않아 `검사 3/3 rc0 · 커밋 안 함`은 경고하지 않는다.
- 기존 `master/test_plan_tools.py`에 검사 8건 추가:
  - 단독 표현·해시 포함·검사 수치 포함 입력의 미실행 경고 3건.
  - 검사 결과 뒤 커밋 안 함이 미실행으로 취급되지 않는 것 1건.
  - 실제 `transition()` 함수와 기존 `FakeIssue`를 사용해 경고 응답·노트,
    완료 상태 유지·근거 원문 보존 4건.
- worktree 코드 직접 호출(rc0)의 변경 후 출력:
  - `커밋 abc1234 · 검사 실행 안 함` →
    `[주의] 완료 근거에 「검사 실행 안 함」 — 검사·실행 없이 완료로 기록된 것으로 읽힌다(#908)`
  - `커밋 abc1234 · 검사 미실시` → 기존 미실행 경고.
  - `커밋 abc1234 · test 3/3 rc0` → 빈 문자열.
- 실제 Redmine 완료 전이를 검증 목적으로 임의 생성하지 않았다.
  `FakeIssue`는 운영 API 실증이 아니다. 이 일감 T1 완료 전이는 검사 결과가 있는 근거로
  기존 운영 코드에서 처리됐고 경고는 없었다.

## 검사 명령과 결과

작업 위치는 `/home/sim/ax-cluster/.ax-issues/961`.

- `AX_PROJECTS_ROOT=/home/sim/ax-cluster /home/sim/ax-cluster/.venv/bin/python -B master/test_plan_tools.py`
  → rc0, `OK test_plan_tools: 82/82 통과`.
- `git diff --check` → rc0.
- 공식 통합 첫 실행:
  `AX_PROJECTS_ROOT=/home/sim/ax-cluster /home/sim/ax-cluster/.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v`
  → rc1, `Ran 4 tests`, `FAILED (failures=1)`.
  `FAIL test_source_scope: 28/32 통과`, 실패 원문 중 하나:
  `펼치면 서브모듈 안 변경 파일이 된다 — [] vendor/eng: 5f96607f 에 서브모듈 포인터가 없다(삭제?)`.
  로그 `/tmp/ax-961-integration.log`.
- 리포트 86·사용자 Git 검증 지침의 기본 샌드박스 그룹 권한 제약과 같은 양상이다.
  코드·저장소를 고치지 않고 동일 명령만 담은 `/tmp/ax-961-integration-approved.sh`의
  샌드박스 해제 승인을 받아 실행했다. 재실행의 `test_source_scope`는 통과했다.
  최종 결과: rc0, `Ran 199 tests in 216.834s`, `OK`.
  `test_plan_tools.py`는 공식 통합의 명시적 제외 목록에 있으므로 위 82/82를 별도로 실행했다.

## 세션 식별과 남은 관측

- 세션: `~/.codex/sessions/2026/11/14/rollout-2026-11-14T21-58-14-01a1da23-141d-7523-a3eb-bf0850f55788.jsonl`.
- #908의 재기동 후 실제 운영 완료 전이 경고 관측은 이 수정과 별도다. 강제로 전이를 만들지 않았다.
- 마감·상주 재기동·배달 결과는 리포트에 소급하지 않고 Redmine 마감 노트에 남긴다.

최종 결과는 Redmine #961 마감 노트.
