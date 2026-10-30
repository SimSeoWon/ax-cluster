# 131 — 온톨로지 상용 합성의 고정 트리 (#849)

날짜: 2026-10-30 · 담당 Codex · [#849](http://192.168.0.57:8080/issues/849)

## 결정과 범위

사용자가 #849 착수와 로컬 서브 에이전트 수행을 선택했다. 기존 #848 구현과 RAG 문서
`AXCluster/context/master/ontology/synth.md`를 실제 소스에 대조했다.

- 상용 CLI 작업 폴더는 합성 시작 시 미러 HEAD를 SHA로 확정한 고정 트리다.
- agy·codex에는 기존 `context_synth.pinned_tree.pinned_worktree`를 재사용한다.
- 상용 프롬프트에만 도메인 자료와 직접 관련 소스 열람 범위를 추가한다. 테스트·빌드·전체 탐색·파일 변경을 제한한다.
- 로컬 레인 진입 정책과 로컬 프롬프트는 유지한다.

## 구현

- `master/ontology/synth.py`: `_CloudTree`가 시작 SHA를 보관하고 실제 상용 호출 때 트리를 생성한다.
  `run` 배치가 하나를 공유하고 `refresh_domain`·`describe_domain` 직접 호출도 자기 수명을 관리한다.
  `ExitStack`으로 정리하며 생성 실패는 레인 실패로 남긴다. 라이브 트리로 돌아가지 않는다.
- `master/ontology/prompt.py`: 상용 전용 작업 범위 문구.
- `master/test_ontology_synth.py`: 실제 임시 Git에서 HEAD 이동 후 시작 SHA 유지, 레인 간 공유,
  트리·등록 정리, 생성 실패 시 상용 호출 차단, 로컬 프롬프트 유지, 세 진입점의 정리를 검사한다.
  외부 CLI는 모의 호출이다.

기존 `_LazyTree`는 HEAD를 첫 CLI 호출 때 해석하므로 그대로 가져오지 않았다.
기존 고정 트리 생성·정리 구현만 재사용해 온톨로지 내부에서 시작 시점을 관리한다.

## 검사와 중단 이력

1. 실증 사전조회 `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -B -m master.ontology status`
   는 rc=1, `active 도메인이 없다`였다. 중단·보고 후 사용자가 구현·회귀 먼저, 실제 합성은 나중에 하도록 승인했다.
2. 첫 회귀는 63/64 통과였다. 새 테스트가 상용 레인의 quota 선행 없이 로컬 호출을 기대했다.
   기존 `llm_policy.eligible`가 이를 차단한 것이 원인이다. 중단·보고 후 사용자 승인으로 테스트 조건만 수정했다.
3. 수정 후 `.venv/bin/python -B master/test_ontology_synth.py`: **64/64 통과**, rc=0.
4. `git diff --check`: 통과.
5. `.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v`:
   **181/181 통과**, 188.167초, rc=0. 온톨로지·서술·재검증·정책·고정 트리 검사 포함.

독립 읽기 검토에서는 범위 내 구현 결함을 발견하지 못했다.

## 미검증과 다음 단계

- 실제 도메인 합성, agy 도구 호출 수·소요 시간, 실호출 전후 마스터 `status --ignored` 불변은 미검증이다.
  사용자가 실증 대상 도메인을 정한 뒤 수행한다. 현재 마운트 AXCluster에는 active 도메인이 없다.
- 고정 SHA는 **CLI 작업 폴더**에 적용된다. 프롬프트 발췌·사실 검증은 기존 `paths.repo`를 읽으므로
  합성 전체 입력의 단일 SHA 스냅샷을 보장하는 변경은 아니다.
- 세 진입점의 정리 검사는 내부 본체를 모의 호출한다. 실제 전체 합성 경로 실증을 대신하지 않는다.
- 커밋·푸시·배달·서비스 재시작은 하지 않았다. #849는 실증을 남겨 진행 상태로 유지한다.
