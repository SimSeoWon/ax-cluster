# 226 — 인터뷰 답변의 의미와 확정 상태를 구분한다 (#1051)

사용자 지시: 「진행하던 일 정지하고 1051번 진행해」, 「인터뷰가 멈추고 니가 헛짓거리 하는걸 막은거지 사용자의 의견을 무시하라고 만든게 아니라고」. 구현 방식은 「단독으로 진행해」. #1050은 분류 인터뷰에서 멈췄다. #1051의 질문 등록 뒤 사용자가 「응 진행해」라고 승인해 단독 플랜을 등록했다.

`issue_start_tool`: `repo=/home/sim/ax-cluster/.ax-issues/1051`, `branch=issue/1051`, `start_rev=4660328c529afeea2c964f7f648ad88c99bb980f`, `lock=acquired`, `author.family=codex`.

세션 기록: `~/.codex/sessions/2026/11/28/rollout-2026-11-28T15-33-58-01a220dc-4d63-7cc0-b53d-35682e4916f7.jsonl`.

## 재현과 변경

#1050에서 Codex가 「어느 분류로 진행할까요?」와 「1. 신규 기능 (추천)」「2. 기존 기능 수정」을 제시했다. 사용자가 「응 신규 기능이야」라고 답했지만, 기록 호출은 `#1050 classify: 추천 1번이 아닌 답(free)에 「어긋남 없음」을 적을 수 없다`를 반환했다. Codex는 의미를 확인하는 대신 `1`을 재입력하라고 안내했고, 그 답도 같은 오류가 났다. 입력 장부 로그 15:41:48·15:42:15 KST에는 두 입력이 모두 기록됐다. 현재 판정 함수로 확인한 기준선에서 두 답은 `('free', 0)`, 비교용 `1번`은 `('recommended', 1)`이었다. 착수 전 Stop 판정은 `{'block': False, 'reason': '활성 일감 없음'}`이었다.

- T1 `7b1f740` — 입력 훅이 실제 입력의 ID를 모델에 전달한다. 장부는 그 ID의 세션으로 질문을 연결하고, 질문 뒤 같은 세션에서 받은 원문을 검증한다. 이전 장부 행은 보존한다. 세션이 연결되지 않은 질문은 재개 때 현재 입력 ID로 질문을 등록한다.
- T2 `b065e2e` — 고정된 문구 목록 대신 등록 질문·보기와 실제 입력을 읽은 모델의 의미 판단을 받는다. 단계·스펙·플랜은 `followup_required`일 때 확정 내용을 쓰지 않고, 원문과 판단 근거로 후속 질문을 잇는다. 명확한 대안 선택은 선택 번호와 근거를 기록한다. 질문 미등록·다른 세션·실제 원문 불일치는 검증 오류다.
- T3 — 착수 전에도 같은 세션에 열린 질문의 미처리 답 또는 아직 후속 질문을 열지 않은 답이 있으면 Stop 훅이 차단한다. 질문을 등록해 답을 기다리거나, 답변을 확정했거나, 명시적으로 중단하면 통과한다. 활성 작업의 기존 Stop 판정과 차단 상한을 유지한다.

## 검증

작업 위치는 위 worktree, Python은 `/home/sim/ax-cluster/.venv/bin/python -B`.

- 수정 전 `-m master.test_interview_ledger` rc 0, 60/60. T1 68/68, T2 61/61, T3 69/69. T2에서 고정 어휘 검사 항목을 세션·명확한 대안·후속 질문 상태 검사로 바꿨다.
- T2 `-m master.test_interview` 53/53, `master.test_plan_tools` 107/107, `master.test_client_mcp` 397/397, `master.test_mcp_servers` 86/86, `master.test_skill_conventions` 54/54, 모두 rc 0.
- `-m master.test_prompt_ledger_hook` 샌드박스 안에서는 루프백 생성이 `PermissionError: [Errno 1] Operation not permitted`로 막혔다. 같은 기존 검사 명령을 승인된 샌드박스 해제로 실행해 T1 20/20, T3 21/21 rc 0을 확인했다.
- T2 패치 문맥 불일치는 실패 장부에 기록했다. `plan_start_tool`이 `resume`을 반환한 뒤 대상 파일의 실제 문맥에 맞춰 적용하고 rc 0을 기록했다.
- 공식 통합 `AX_PROJECTS_ROOT=/home/sim/ax-cluster /home/sim/ax-cluster/.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v` rc 0, 223/223, 32.505초, 실패 0. 8101 검사에서 실제 라우트에 입력 ID로 질문을 등록하고, 미처리 사용자 답변의 세션만 Stop 판정이 차단하는 결과를 확인했다. 모델이 문맥을 해석하는 코드는 도구 호출 계약으로 검증했으며, 운영 Claude·Codex의 새 인터뷰 세션 문답은 이 커밋 시점에 미실행이다.

최종 결과는 Redmine #1051 마감 노트.
