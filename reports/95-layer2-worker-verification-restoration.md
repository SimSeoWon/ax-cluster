# #696 — 워커 커밋 전 층2 선언 검증 복원

2026-10-05 21:14 KST · Codex 마스터 · 사용자 선택: 로컬 서브 에이전트 3개(선언/실행 연결/독립 검토).
기준 HEAD `f9bc7bf`. 아래 변경은 로컬 미커밋이며 서비스 재시작·배달·원격 파견은 하지 않았다.

## 문제와 결과

기존 `infer.commit_task → wcommit.run`은 층1 검사 뒤 바로 커밋했다. 층2 모듈이 존재해도 이 운영 경로에서 호출되지 않았다.
이제 되읽은 파일에 층1을 적용한 뒤 동결 base 선언을 대조하는 층2를 거쳐 승인된 파일만 커밋한다.
검증기 없음·예외·판정 계약 오류·프로필 미확정·grounding 결손은 차단한다. 실제 코드 지적은 기존 bounded revise에 전달하며,
검증 인프라 실패는 유료 코드 재작성으로 보내지 않는다. 기존 커밋 명령·요청자 main·cleanup 계약은 유지했다.

RAG `search_context_tool` 결과의 `AXCluster/context/master/layer2_verify.md`, `AXCluster/context/master/work/usage.md` 본문과
현재 `layer2_verify`, `wcommit`, `infer`, `declarations`, usage 소스를 대조했다. AgentTest의 checker는 참조만 했으며 fail-open을 가져오지 않았다.

## 변경 범위

- `master/work/wcommit.py`: 층1 뒤·커밋 앞 verifier 게이트, 지적·실패·판정 원문 보존. verifier 없는 직접 호출도 차단.
- `master/work/infer.py`: 등록 kind/work_exts와 base 선언 전달, 실제 작성 계열 추적·제외, 선언 수집/상용 검증 중 즉시 및 주기 heartbeat.
  기존 agy→claude 체인은 agy 미가용에만 폴백하며 판정 거절이나 계약 오류는 폴백으로 덮지 않는다.
- `master/work/declarations.py`: 기존 헤더-only 기본 계약 유지. 대상의 기준 헤더·Python AST 선언·직접 로컬 import를 수집하며
  함수 본문은 생략하고 self/cls 필드 이름을 포함한다. missing/truncated/dropped가 있으면 검증에 사용하지 않는다.
- `master/layer2_verify.py`: 패키지 정본 Verdict 사용, code/Python 프롬프트, 전체 소스 전달, 빈 입력 차단.
  16k 이후를 조용히 자르던 기존 동작을 제거했다.
- 검증 구간은 `usage.sink(source="layer2", work_id, task_id)`로 backend 호출별 기록한다. 기존 대시보드 dispatch 이슈 연결과
  all 중복 방지 계약을 회귀 검사했다. all의 `issues=[]` 계약은 유지했다.
- 관련 검사 및 `tests/integration/checks.json`에 wcommit·declarations·새 grounding 검사를 등록했다.

## 검증

`.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v`
종료코드 0 · **23모듈 923건 통과**, 15.324초. infer 190, wcommit 59, declarations 20, grounding 9, dashboard 12 포함.
`git diff --check` 종료코드 0. 독립 읽기 검토에서 16k 입력 제한 문제를 발견해 제거했고 최종 diff에 추가 고위험 지적은 없었다.

실제 `verify_files`와 임시 bare Git을 연결한 검사는 판정 타입 전달, 승인 커밋/거절 무커밋, 작성 계열 제외,
폴백 호출별 사용량 귀속, no_backend에서 commit/submit/revise 차단을 검증한다. 모델 응답과 워커 실행은 주입한 fixture이며
실제 상용 모델 품질·로그인 상태·운영 워커 실행 성공을 증명하지 않는다.

## 남은 범위

- Python 전이 import 전체·동적/조건부 API, C++ include tree 전체를 수집하지 않는다. 기존 선언 발췌 예산은 파일당16k/합계64k이며
  초과하면 차단한다. `complete`는 수집한 발췌의 결손 없음이지 프로젝트 API 전체의 완전성을 뜻하지 않는다.
- 큰 프롬프트의 기존 CLI/OS 인자 한도 실패는 fail-closed지만 입력 전송 방식 개선은 이 범위 밖이다.
- 커밋·푸시·서비스 반영·워커 배달 및 실제 상용 층2 운영 실증 전이다. #696은 진행 상태로 유지한다.
