# .57 인프라 RAG·위임 준비 정비 — #716

일감 정본: http://192.168.0.57:8080/issues/716

## 승인과 범위

사용자는 NS 요청자 흐름(리포트85)을 참조해 `.57`에도 RAG 검색·소스 대조 → 단독/분산 선택 → 선택에 맞춘 서브 에이전트 → 실물 검증을 반영하도록 지시했다. 분산 준비가 미완료임을 확인한 뒤 로컬 서브 에이전트로 선행 정비하는 방안에 동의했다. 이번 변경의 커밋·푸시 승인은 아직 받지 않았다.

## 반영한 내용

- 홈 정본 `machines/sim-desktop-agents.md`·`machines/sim-desktop.md`, 저장소 `AGENTS.md`·`CLAUDE.md`, 공용 규칙에 사용자 결정 흐름을 추가했다. 기존 미커밋 Windows 원격 실행 지침은 보존했다.
- `master/projects/workshop_check.py`의 프로젝트 검사를 등록 `kind`로 분기했다. `unreal`은 기존 `Source/` 검사, `code`는 `SourceScope` roots·exclude·exts, `index_only`는 SSH 없이 파견 제외다. code 확장자는 설정이 없으면 프로필 `work_exts`를 사용하며 둘 다 비면 거절한다.
- code의 Git quoted 경로를 해석하고 rename 양쪽을 검사한다. 소스를 경계 밖으로 옮겨도 소스 삭제가 차단 대상으로 남는다.

## 검증

`master/test_workshop_check.py` 77/77 통과. 실제 임시 Git의 한글 경로, 이름 안의 ` -> `, 경계 안팎 rename을 포함한다. 대상 두 파일 `git diff --check` 통과.

`master/test_source_scope.py`는 기본 샌드박스에서 28/32였다. 내부 `sg gitea`가 `Cannot open audit interface - aborting.`으로 Git 조회를 못 한 환경 오류다. 사용자 권한 승인 후 동일 명령을 샌드박스 밖에서 다시 실행해 32/32 통과했다. 이를 고치기 위한 코드 변경은 하지 않았다.

독립 코드 검토는 별도 로컬 에이전트가 수행했다. 현재 AXCluster의 Python 소스 계약을 검토하며, 일반 code 프로젝트의 서브모듈 내부 더티 검사 한계는 별도 확인 대상이다.

## 운영 준비와 남은 작업

`ax-dispatch.timer`와 `ax-dispatch.path`는 모두 active/waiting이다. 따라잡기 서비스는 `ax-dispatch.timer`의 `Unit=ax-dispatch-catchup.service`로 깨운다. 이전에 조회한 `ax-dispatch-catchup.timer`는 실제 타이머 이름이 아니므로 그 조회만으로 따라잡기가 꺼졌다고 판단하면 안 된다.

`ax-projects.service`는 active/running이며 기동 시각은 2026-10-03 11:10:31 KST다. 수정한 Python 검사가 서비스에 반영됐다는 실증은 아직 없다.

마스터 `distribute` 스킬은 통합자·기본 직렬·마스터 골조 생성 등 낡은 내용을 유지한다. 재작성과 Codex 검색 경로 연결이 남아 있다. 깨끗한 커밋 기준 워커 배달·서비스 반영 확인·실제 큐/브랜치 파이프라인 완주도 남아 있다. 기존 직접 Codex 쓰기 프로브를 전체 분산 완주로 보지 않는다.

문서 에이전트가 존재하지 않는 `master/task_queue/client.py`, 재개 후 `master/clientside`를 추정해 조회하다 rc2로 실패했다. 루트도 존재하지 않는 `infra`·`systemd`를 조회했다. 실제 경로는 `rg --files master`로 확인했다. 공용 규칙 §1.1에 따라 추가 코드·설정·스킬 편집을 중단하고 사용자에게 보고했다. 반복 조회 오류 이후 남은 스킬 작업은 루트가 직접 인수하는 방안이다.

이 보고서는 진행·중단 사유 기록이며, #716 완료 또는 분산 실행 준비 완료 판정이 아니다. 커밋·푸시·배달·서비스 재기동·원격 파견은 하지 않았다.

## 커밋·동기화 준비 — 후속 승인

사용자 “모두 커밋 푸시하고 동기화해”로 기존 미커밋 변경 전체의 커밋·푸시·동기화 승인을 받았다.
메인 지휘자가 distribute 스킬을 현재 RAG/사용자 선택/로컬 위임/등록 kind/정본7단계로 재작성했다.
Codex 기존 검색 경로 `~/.codex/skills/distribute`와 공식 사용자 경로 `~/.agents/skills/distribute`는
저장소 정본을 가리키는 링크로 등록한다. 샌드박스의 읽기 전용 차단은 좁은 링크 스크립트 승인으로 처리했다.

스킬 quick_validate 통과, workshop77/77와 broker routing14/14 재확인 통과, 전체 diff 공백 검사 통과.
독립 forward 검토에서 현재 도구·모듈·문서 링크·타입 분기·기승인 방식 재사용을 확인했다.
기존 SourceScope32/32를 합하면 관련 코드 검사123개 통과다. 스킬 형식 검사는 별도다.

공식 안내는 스킬 변경 자동 감지, 미노출 시 Codex 재시작을 명시한다. 공식 경로는 `.agents/skills`이며
심볼릭 링크를 지원한다. 이 대화의 스킬 목록에 새 distribute가 나타났다는 증거는 아직 없다.
근거: https://learn.chatgpt.com/docs/build-skills (2026-10-03 조회).

아래 운영 작업은 이 커밋 직후 수행하고 실제 결과는 #716에 기록한다:
Gitea push·클론 ff 동기화, ax-projects/ax-broker 서비스 반영, 등록 전체 client update와 최종 검사.
Python 통합 실행기 호환성 및 실제 큐·조각 브랜치 완주 검증은 별도 남아 있으므로 이번 동기화를
분산 전체 완주 또는 #716 완료로 기록하지 않는다.
