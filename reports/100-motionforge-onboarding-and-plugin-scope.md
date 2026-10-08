# MotionForge 온보딩 완료 판정과 Unreal 플러그인 경계

2026-10-08 · Codex · 사용자 선택: 로컬 서브 에이전트 구현·독립 검토.

## 실증

MotionForge는 등록된 Unreal 프로젝트(UE5 5.8)다. 사용자 승인으로 마운트를 전환했고
워커 .2/.33/.43을 HEAD `354e751` 출처로 맞췄다. 배달 검사 3/3 통과.
#745의 뒤처진 워커 정렬은 실증했지만 같은 버전 생략 분기는 실증하지 않았다.

최초 온보딩은 rc0을 반환했지만 합성·색인이 남았다. 실행 시점 결과는 97그룹 중
written86/skipped7/unfactual4/failed0, 색인 94/99그룹과 워터마크 미작성이다.
동시에 ax-indexer가 같은 프로젝트를 처리하며 미러 기준이 변경됐다.
이후 pending에서 확인한 given_up 3건은 별도 시점의 관측이며 위 4건과 합치지 않는다.
declared symbol `mat`, `loaded`, `error`는 실제 struct에 있다. 합성 실패 응답 원문은
확보하지 않았으므로 구체적인 누락 문장과 정책 변경 필요성은 확정하지 않는다.

## 수정

- `master/projects/onboard.py`: 승인 실행이 기존 Spool consumer.lock을 공유한다.
  최초 판정부터 실행·클라이언트 검사·최종 판정까지 잠금을 유지하고 finally로 해제한다.
  계획은 Spool을 생성하지 않는다. 최종 미완료는 API 오류·CLI rc1으로 반환한다.
  `--only`는 기존 선결 조건을 유지하며 선택 단계 완료와 전체 남음을 구분한다.
  `--limit`은 실행량 제한이며 미완료를 성공으로 표시하지 않는다.
- `master/projects/workshop_check.py`: Unreal은 등록 source.roots/exclude 경계 안의
  모든 추적 파일을 보호한다. 기본 Source/와 code 확장자 계약은 유지한다.
  rename의 이전·새 경로를 모두 검사한다.
- 관련 두 회귀 파일과 `master/client/skills/ax-work/SKILL.md`를 수정했다.

## 검증과 한계

메인 직접 실행: test_onboard 80/80, test_events 57/57, test_workshop_check 81/81.
정본 `.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v`
25모듈 모두 통과. 독립 검토에서 발견한 --only 선결 조건 우회는 보정했고 최종 추가 차단 없음.

기존 잠금은 전역이므로 다른 프로젝트 색인 소비도 기다린다. 사람이 직접 미러를
변경하는 경우까지 잠금이 보호하지 않는다. 서브모듈 내부 dirty는 이번 검증 범위 밖이다.
사실 게이트 정책은 변경하지 않았다. 운영 재온보딩·커밋·푸시·배포·서비스 재시작은 미실행.
#259/#706/#695 전체 완료를 주장하지 않는다.

## 후속 배포·재실증 및 합성 수정

사용자 별도 승인으로 `e3bca87` 커밋·푸시·MotionForge 배달 완료. 최초 update는
ax-projects가 이전 코드로 실행 중이라 rc1. 추가 승인 후 기존 ax-service-restart로
2026-10-08 22:25:20 KST 재기동(active/running), 배포 재검사 rc0·3/3 통과.
온보딩 재실증은 기준 f57b82b, 작성2/건너뜀94/사실게이트3/실패0, vector96,
96/99그룹과 워터마크 미작성으로 최종 rc1을 반환했다. 거짓 완료 판정 수정은 운영 실증했다.

남은 3개는 mat/loaded/error 미언급으로 거부됨을 pending·실제 struct·verify 소스로 확인.
unreal에는 index_only 전용 live_counts 예외를 적용하지 않는다. 형식 대체 사슬은 사실
거부에 적용되지 않는 기존 계약이다. 실패 원문이 없으므로 전체 요약의 사실성은 미확정.
동시2 합성 시작에서 검색기 AttributeError bindings와 경로 KeyError도 관측했다.
설치된 Chroma가 초기화 전 시스템을 공유 캐시에 등록하는 코드와 병렬 open_search를
대조했으며 초기화 경합이 유력하다. 실제 Chroma 사고 재현으로 확정하지 않았다.

사용자 후속 수정 승인·기존 로컬 서브 에이전트 방식으로 다음 네 파일을 수정했다.
- context_synth/prompt.py: 실측 선언이 있으면 요약에 최소 하나의 이름과 소스상 역할 명시.
- context_synth/synth.py: 첫 실제 작업에서 검색기를 한 번 열고 coordinator에서 검색 후
  목록만 병렬 합성에 전달. 초기화 실패는 한 번만 기록, 소유 검색기는 finally close.
  모두 skip이면 초기화 없음. caller 주입은 명시 searcher 없으면 실제 검색 생략.
  직접 그룹 호출도 초기화 잠금·소유 검색기 해제를 적용했다.
- test_context_synth.py·test_synth_parallel.py: 소문자 선언과 검색기 수명·격리 회귀.

메인 직접 검증: context_synth189/189, synth_parallel25/25(합계214), 정본 통합25모듈 통과.
독립 검토 추가 차단 없음. 사실 게이트 정책·타입·대체 모델 사슬은 그대로다.
검색기 close는 기존 BM25 해제를 사용하며 Chroma 공유 자원 수명 자체는 변경하지 않았다.
CLI만 모의 호출하는 테스트는 별도 searcher 주입이 필요하다.
테스트 로그 경로 확인용 /tmp 목록 조회 rc2(시스템 전용 디렉터리 접근 거부)는 보고했고
권한 변경·재시도하지 않았다. 테스트 자체는 rc0. 후속 수정은 미커밋·미배포이며 운영 재실행 없음.
