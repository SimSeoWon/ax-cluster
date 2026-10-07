# 98 — #753 provision 모델별 상주 허용과 실제 상주 상태 진단

- 날짜: 2026-10-07 · Codex 마스터
- 사용자 선택: 로컬 서브 에이전트 구현1개·읽기 전용 독립 검토1개
- 기준 HEAD: `f3ed507` · 검증 후 사용자 커밋·푸시 승인

## 근거와 수정

RAG `master/provision.md`는 8월의 `.33` 전체 상주 금지를 설명한다. 현재
`master/broker/config.py`의 `.33` pin/prefer는 `gemma4:e4b`이며,
`machines/win-main-33.md`의 2026-10-03 승인 기록과 대조했다.
옛 `Node.resident=False`는 어떤 모델이 적재돼도 위반으로 표시해 e4b를 오탐했다.
provision은 점검과 설치만 수행하며 모델을 적재·해제하지 않는다.

수정은 `master/provision.py`·`master/test_provision.py` 두 파일이다.
`Node`·`NodeStatus` 마지막에 선택 `resident_models`를 추가했다. `None`이면 기존 bool
계약을 유지하고, 명시 목록이 있으면 그 목록의 모델만 허용한다. 빈 목록은 전부 금지다.
입력은 frozenset으로 복사해 정책 스냅샷을 유지하며 위치 인자 계약도 보존한다.
`.33`은 `want=[CODER,SYNTH]`, e4b만 상주 허용한다. 경고에는 금지 모델만 표시한다.
`.2`·`.43` 배정, 브로커 코드, 실제 모델·서비스 상태는 변경하지 않았다.

## 검증

- 구현 에이전트 `.venv/bin/python -B master/test_provision.py`: 69 통과·0 실패·rc0,
  출력 전문 확인. e4b 허용·14b/혼재/미지 모델 금지·CLI 종료코드·위치 인자·정책 스냅샷·
  브로커 기본 pin 대조 및 기존 GET-only/pull 재검증/dry-run 검사 포함.
- 메인 실제 diff 확인 및 독립 최종 검토: 차단 결함 없음.
- 메인 정본 `.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v`:
  25모듈·1,153건 통과·rc0, 17.301초. 출력 전문 확인.
- 메인 `git diff --check`: rc0.

## 실제 .33 점검 — 조건 미충족으로 중단

기존 `master.provision.check_node`를 호출하는 좁은 권한 승인 스크립트
`/tmp/ax-753-check-approved.sh`를 실행했다. 네트워크 승인 뒤 `.33`의 tags/ps를 읽을 뿐,
모델 설치·적재·해제나 서비스를 변경하지 않는다.

실제 결과는 reachable=true, models=`gemma4:e4b,qwen2.5-coder:14b`, missing=[],
loaded=[], violating_models=[]다. 보유 및 위반 없음은 확인됐지만 실제 e4b 상주 확인 조건은
충족되지 않아 스크립트 rc1로 끝났다. `check_node`는 `/api/ps` 예외를 빈 목록으로 처리하는
기존 계약이므로, 상주가 실제로 없는 것인지 ps 조회 오류인지 이번 결과만으로 확정하지 않는다.
회귀 검사 성공을 실제 상주 성공으로 확대하지 않는다.

실패 후 코드·설정·조회 스크립트를 보정하거나 모델을 올리지 않고 중단했다.
재개 시 기존 `/api/ps` GET 응답·오류를 직접 확인하는 읽기 전용 진단이 먼저다.
실제 적재가 필요하다면 사용자의 별도 결정 후 수행한다.

## 사용자 재개 후 읽기 전용 진단

사용자 「응」으로 위 진단 재개를 승인했다. 기존 `master.provision._get`의 HTTP 조회
계약을 소스에서 확인하고 같은 좁은 권한 스크립트를 `/api/ps` 응답 직접 조회로 변경했다.
GET 결과는 `{"models": []}`이며 rc0다. 실제 API 응답이 빈 목록이므로 앞선 loaded=[]는
조회 예외로 숨겨진 결과가 아니라, 진단 시점의 비상주 상태임을 확인했다.
모델·서비스 변경은 하지 않았다. e4b가 상주 중일 때의 운영 실측은 여전히 없지만,
현재 보유 상태 점검과 정책 회귀·정본 통합 검증은 완료했다.

`/tmp` 경로 목록 조회는 하위 systemd 전용 디렉토리 권한 거부로 rc2가 났다.
진단 파일은 목록에 존재했고, 깊이1로 제한한 목록 조회 rc0 뒤 확인된 파일만 읽었다.
이 경로 조회 제약을 Ollama API 오류로 해석하지 않았다.

## 기록 상태

사용자 「응」으로 소스2개와 보고서98·보고서색인·인계서 총5파일 커밋·푸시를 승인했다.
이 문서는 커밋 전 검증 기록이며 실제 커밋 해시·푸시·완료 상태는 Redmine #753 후속
노트로 확인한다. 배포·파견·모델 변경 없음. 머신 자동 로드 문서의 옛 provision 불일치
설명은 아직 수정하지 않았으며 후속 문서 갱신 대상으로 남는다.
