# 97. #720 Codex 한도 오류 보존 — 로컬 구현·검증 완료

2026-10-07 · Codex · 사용자 #720 진행 및 로컬 서브 에이전트 방식 승인.

## 원인과 구현

RAG의 `AXCluster/context/master/work/usage.md`·`test_usage_accounting.md` 본문을 읽고
현재 소스와 대조했다. `usage.parse_codex_jsonl`은 `error.message`와
`turn.failed.error.message`를 버렸고, `wcommit._cycle`의 종료 코드 실패 경로는
본문 끝 300자만 실패 사유로 남겼다. 그래서 `infer.commit_task`의 기존 한도 분류까지
실제 오류 문구가 전달되지 않았다.

구현 에이전트 1개와 읽기 전용 검토 에이전트 1개를 사용했다. 변경은
`master/work/usage.py`·`runner.py`·`wcommit.py` 및
`master/test_runner.py`·`test_usage_accounting.py`·`test_infer.py`의 6파일이다.
중복 제거한 오류 원문을 메타데이터에 보존하고 `c.notes`로 전달한다. 사람 로그는
요약하며, 오류만 있는 출력도 실패 사유를 표시한다. 정상 본문·사용량 계약은 유지한다.

기존 `quota_exhausted` 신고와 pending 복귀·해당 워커 5시간 차단 정책을 유지한다.
원전 근거는 참조 전용 `/home/sim/AgentTest/worker/worker.py:749–756`의 한도 신고 경로이며,
현재 큐의 `master/task_queue/logic_lifecycle.py`에도 동일 분기가 있다.

## 최종 검증

- 구현 에이전트의 개별 회귀: runner160/160·usage18/18·infer230/230, 종료코드 모두 0.
  최종 출력 전문 확인. 별도 독립 검토에서 차단 결함 없음.
- 메인 직접 소스·회귀 diff 검토 및 정본 통합 검사 실행:
  `.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v`
  **25모듈·1,153건 통과**, rc 0, 17.086초. 출력 전문 확인.
- 메인 직접 `.venv/bin/python -B -m unittest master.test_usage_accounting -v`:
  **18/18**, rc 0. 이 검사는 통합 명시 목록에 없으므로 별도로 확인했다.
- 실제 JSONL 오류 → 파서 → wcommit → infer → quota_exhausted 제출과 일반 revise 제외를
  검증했다. 오류만 출력·긴 본문 뒤 오류·긴 오류·최대 시도·rc 0 층1 실패를 포함한다.
  요청자 고지는 대역의 호출 종류·횟수로 확인했으며 실제 워커/요청자 수신 실증은 아니다.
- 구조화 오류와 raw 로그 중복 제거 및 오류 합계 3개 요약 제한을 회귀로 확인했다.
  형식 판별은 usage 파서 한 곳에 있으며, 판정용 오류 원문은 요약과 별개로 유지한다.

## 검사 중 드러난 테스트 결함

두 차례 실패에서 수정 중단·보고 후 사용자가 각각 「응」으로 재개했다.
기존 `CycleCarriesUsage._run`의 필수 verifier 인자 누락·예외 숨김을 보정했고,
새 rc 0 회귀의 잘못된 baseline 대역 `{}`도 callable로 보정했다.
기존 오류를 삼키던 검사도 이제 실제 `_cycle` 호출 실패를 그대로 드러낸다.
현재 해결되지 않은 검사 실패나 재개 대기 조건은 없다.

## 반영 상태와 범위

기준 HEAD `fddf060` 위 소스·회귀 6파일 및 보고서·색인·인계서 미커밋.
사용자 「응 푸시하고 배포해줘」로 9파일 커밋·Gitea push·배포를 승인받았다.
이 문서는 배포 전 검증 기록이며, 실제 커밋 해시·워커 동기화·배달·서비스 확인 결과는
Redmine #720의 후속 배포 노트로 대조한다. 새 실워커 조각 파견은 범위 밖이다.
rc 0 성공 판정은 기존 디스크 검증을 따르며 오류 이벤트만으로 성공을 막는 정책은
이번 범위에 넣지 않았다. 배포 전까지 Redmine #720은 「진행」으로 유지한다.
