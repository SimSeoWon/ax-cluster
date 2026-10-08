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
