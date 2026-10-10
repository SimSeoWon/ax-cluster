# #794 분산 층2 Gemini 판정의 오케스트레이터 재확인

2026-10-10 · Codex · 관련 일감 #788, #793, #794

## 문제와 사용자 결정

#793의 A 조각에서 Gemini가 `l2.call_claude_why`가 없다고 지적했지만 골조 ca196a5와 현재 main에 실제 정의가 있었다. B 조각은 Gemini 300초 timeout 뒤 Claude 세션 한도로 `no_backend` 차단됐다. 코드 결함과 판정자 실패를 구분하지 못하고, 선택된 Codex 지휘자에게 재확인도 맡기지 못했다.

사용자 결정은 오케스트레이터(Codex 또는 Claude)가 Gemini에 기본 문법 검사를 요청하고, Gemini 오탐 또는 판정 불가 시 실제 소스를 다시 확인해 최종 판단하는 것이다. 요청자가 전체 조각을 머지한 뒤 통합검사하는 기존 절차는 유지한다.

## 구현

- `master/layer2_verify.py`: 명시적인 `orchestrator` 경로를 추가했다. Gemini APPROVE는 추가 호출 없이 반환한다. REQUEST_CHANGES·timeout·quota·잘못된 응답·쿨다운은 선택된 Codex/Claude의 기존 `_why` 호출로 재확인한다. 재확인에는 전체 대상 소스, 동결 선언, 기준 원본, Gemini 원응답과 실패 사유를 전달한다. 실제 오류는 REQUEST_CHANGES로 남고 최종 판정자도 실패하면 차단한다. 이 명시 경로에는 작성자 계열 제외를 적용하지 않는다.
- `master/work/infer.py`: work에 선택된 codex/claude 모드를 검증기에 전달한다. lane 및 비분산 호출은 종전 경로를 유지한다.
- `master/test_layer2_grounding.py`, `master/test_infer.py`: 오탐 재확인, 실제 오류 유지, 판정 실패, 추가 호출 없는 승인, 사용량 귀속, 기존 경로, 분산 모드 전달을 검사한다.

두 판정자의 원응답·실패 사유는 Verdict warnings에 보존한다. 기존 wcommit이 warnings를 notes로 전달하므로 결과 스풀에서도 확인할 수 있다. 기존 layer2 usage sink를 사용한다.

## 검사

- grounding 26/26, infer 250/250 통과.
- verdict 22/22, wcommit 71/71, usage_cli_paths 46/46 통과.
- 공식 `.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v`: 31/31 통과, 60.503초, rc0.
- `git diff --check` 통과.

첫 infer 검사에서는 기존 BACKENDS 주입이 명시 codex 경로를 막지 못해 실제 CLI 실행을 시도하고 샌드박스 실패가 발생했다. 관련 legacy 검사를 lane로 명시하고 분산 재확인 경로를 mock으로 별도 검사해 최종 전체 통과했다. 이 과정에서 잘못 바꾼 다른 quota 테스트의 mode는 복원했다.

## 현재 경계와 다음 작업

main HEAD d969a36 위의 미커밋 변경이다. 커밋·push·배포·서비스 재시작은 하지 않았다. 실 모델 재확인과 #793 재파견은 아직 검증하지 않았다. #794는 진행으로 남겨 운영 실증과 구분한다.

별도 승인 후 커밋·push, ax-deliver 정본 배달 및 서비스 적용을 수행하고 #793의 실패 조각을 정본 경로로 다시 실증해야 한다. 기존 C 완료 커밋 8fe0ee2f와 요청자 골조 ca196a5는 유지한다. ⑺ 전진과 finalize 승인은 별도다.
