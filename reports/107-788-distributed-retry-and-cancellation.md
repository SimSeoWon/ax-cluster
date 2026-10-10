# #795 실제 분산 재실증 결과와 사용자 지시 취소

2026-10-10 22:30 KST · Codex · 관련 #788/#794/#795/#796

사용자 승인으로 요청자 골조 ca196a5에 배포된 #790/#794를 반영한 b510d2f를 커밋하고 새 work `20261010_2214_788_794_4_codex_2bda5a1f`를 Codex 모드로 등재·base push했다. 골조4/4 및 grounding26/26 통과, 워커3/3 dispatchable. 자동 hook으로22:15:02 파견이 시작됐다. 수동 정본 resume은 최초 sandbox 큐 접속 거절 뒤 승인 해제 재실행에서 기존 잠금을 확인해 중복 파견하지 않았다.

## 실제 결과 — 전체 성공 아님

| 조각 | 워커 | 결과 |
|---|---|---|
| A1f648d81 컨텍스트 | .43 | Gemini APPROVE, b29cb46d |
| B47d837d9 레인 | .2 | Gemini APPROVE, 5cec480f |
| C25990f03 온톨로지 | .33 | Gemini APPROVE, 583507bc |
| D915a3150 주기 | .2 | 계약 모순 보고 후 구현 중단, 층1 스텁 차단, 자동 피드백4abbcb81 |

22:20:57 파견 명령은 성공3/실패1로 끝났다. A/B/C notes에는 backend=agy, Gemini 원응답 APPROVE가 남아 실제 새 #794 경로 사용을 확인했다. 이번 실파견에서는 Codex 재확인이 발동하지 않았다. B infer.py의 orchestrator mode 전달 보존도 확인했다. Windows localhost8000 MCP 연결오류는 별도 기록이며 구현 결과 회수는 rc0였다.

D가 지적한 모순은 실제 소스와 호출로 확인했다. revalidation._identity는 context/ontology/task만 허용하지만, B/D 골조는 code를 요구했다. task는 허용되고 code는 ValueError였다. 재파견을 준비한 Codex가 기존 골조의 계약을 다시 확인하지 않은 검증 누락이다. 코드/환경을 임의로 고치지 않았다. 전체 통합검사·⑺ 전진·finalize 미실행.

## 사용자 지시 정리

사용자 「분산작업 하던거 다 제거해」「레드마인 일감 선택해서 처리하는 플로우로 다시 시도」에 따라 미완료 D를 정본 runner.cancel로 취소해 work cancelled 종결. 정본 cleanup terminal AXCluster --apply로 base와 서브4 원격 브랜치 삭제5/실패0/건너뜀0. 삭제 전 완료3커밋과 피드백 커밋은 마스터에 fetch했고 로그/스풀을 보존했다.

워커 .43/.2/.33 실제 브랜치 조회 모두 main이며 #788 로컬 task 브랜치0. 마스터 fetch --prune로 삭제된 추적 참조 정리. 요청자 /home/sim/ax-788-work는 b510d2f detached HEAD로 보존하고 옛 #788 로컬 base 브랜치 삭제. main84abb5b는 유지하며 관련 #788 원격 브랜치0 확인. ax-dispatch inactive/MainPID0. 원격 잔존 프로세스 자체를 전수 조사하거나 종료한 것은 아니다.

워커 상주/잔존 실행 오동작 사용자 보고는 ax-redmine으로 버그 #796(버그·개선, 높음) 등록하고 되읽었다. 마스터 catchup 자동 재시도, 세션1 실행기, AgyRelay/하위 프로세스와 구분해 조사해야 하며 원인 확정이나 코드 수정은 하지 않았다.

다음은 사용자가 Redmine 일감을 선택하는 흐름이다. 새 등재·재파견·추가 구현은 하지 않는다. 보고서/인계서 및 앞선 실증 기록은 미커밋이며 별도 커밋 승인 필요.
