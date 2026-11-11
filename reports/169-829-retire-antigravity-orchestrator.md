# 169 — #829 Antigravity 지휘 타입 폐기 · Argon 서브 작업 한정

> 2026-11-11~12 · Codex 지휘 · 로컬 Codex 서브에이전트 3개 · 구현 `6c30a9dfc7acdc47174cb7b4458552d8e91cad5f`

## 사용자 결정과 범위

사용자 원문:

> 829번 진행해. 제미나이4 아르곤이 AX 클러스터링 전역에 오염을 발생시키고 작업에 이상한 오버해드로 MCP요청시마다 딜레이가 기하급수적으로 올라가 그래서 메인 오케스트레이터로 추가하려던 것을 폐기하고 서브에이전트로만 사용하도록 제한해야 할듯해

> 단독 로컬 서브에이전트로 진행해. 그리고 아르곤 모델 서브 에이전트 활용은 허용하지만, 오케스트레이션의 주체로 하기 위해 작업하는 LLM 타입에서 안티그래비티 타입 추가 한 것도 제거해버려

해석: 마스터 지휘는 Claude·Codex만, `antigravity`/`agy` 마스터 타입 제거. Argon은 지휘자가 범위를 정하고 검증하는 작은 서브 작업으로 허용한다.
실행 전 T1 지휘 차단·T2 서브 위임/진입 문구·T3 검사/기록/마감/배달과 자동 로드 문구를 제시했고 사용자가 로컬 방식으로 진행을 지시했다.
#829는 아이디어에서 「마일스톤 8 - 버그/개선」으로 옮겼다. 기존 R&D·분석 노트는 이력에 보존했다.

## 근거를 구분한다

1. **지휘 타입 추가 — 참**: `conductor.record_master`와 읽기 허용 목록, master MCP 설명, client MCP enum, CLI choices, WebUI 라벨에서 `antigravity`/`agy`를 허용했다. 리포트 157의 #924 추가 항목과 실제 소비자를 대조했다.
2. **운영 착수 허용 — 참**: `issue_flow.start`는 MCP 출처의 존재만 확인하고 `_start`를 호출했다. `INF.client_family("antigravity-client") == "agy"`는 작성 계열로 유지하되, 운영 착수에서는 준비·Git·잠금·Redmine 앞에서 거절하도록 바꿨다.
3. **전역 오염 — 과거 사례는 기록으로 확인**: #829 노트에 #929의 없는 해시 등록·실패 미보고, #930 실제 Claude 설정 오염과 #934 공용 인수인계 오염의 근거가 있다. 이번 작업에서 과거 세션 전체를 재분석하거나 그 사건을 재현하지 않았다.
4. **지연의 기하급수 증가·원인 — 미검증**: 사용자의 관측이다. #829의 기존 계측 노트는 MCP 건당 지연을 적었지만 증가 함수나 내부 원인을 입증하지 않는다. 이번에는 지연 개선 수치를 주장하지 않는다.

RAG: `search_context_tool` request_id=`85514d006644444f829e2422068c6538`, search_id=`651f01ad2c0d4160923444f84e93f6ed`.
검색된 `AXCluster/context/master/agy_models.md`·`.../skills/ax-handoff/scripts/conductor.md` 본문을 읽고 실제 소스와 대조했다.
리포트 159·157·165와 공용 규칙·스킬을 읽었다. `reports/` 전체 전문은 읽지 않았다.

## 변경

- 활성 마스터 타입은 `claude`·`codex`뿐이다. master MCP의 `Literal` enum, client MCP enum, CLI, 코어 저장 함수, WebUI를 맞췄다.
- 옛 `antigravity`/`agy` 담당 파일을 고치지 않는다. 읽을 때 `agent=unknown`, `retired_agent`와 폐기 안내를 반환한다. 마스터 담당을 새 지휘자로 자동 덮어쓰지 않았다.
- 운영 Antigravity 일감 시작을 거절한다. 주입 테스트 경로와 과거 `agy` authors·교차 리뷰·세션 수집은 보존했다. 이는 인증 경계가 아니며 MCP clientInfo를 신뢰하는 기존 계약이다.
- 기존 `master.work.gemini_report --task implementation`을 추가했다. 작은 구현은 자료 사본을 받아 unified diff를 응답/보고서로 회수하고 지휘자가 전체를 검토·적용·검사한다. 기본 research는 유지한다.
- 구현 모드에서 승인 우회 플래그를 빼고 `--sandbox --disable-slash-commands --mode plan`을 사용한다. `agy --help`에서 실제 플래그를 확인했다. 모델 대조·사용량·한도 시 Flash High 폴백과 task 전달을 유지한다.
- AGENTS/CLAUDE·홈 정본 machines 문서·GEMINI 전용 진입·공용 규칙·handoff 스킬/운영 설명을 두 지휘자로 정리했다. 홈 심볼릭 링크 자체는 덮지 않았다.

## 작업 위치와 호출 증거

`issue_start_tool(829)` 핵심 응답 원문:

```json
{"ok":true,"issue_id":829,"branch":"issue/829","repo":"/home/sim/ax-cluster/.ax-issues/829","checkout":"/home/sim/ax-cluster","already":false,"start_rev":"996795757a9129ea07a2c437738713b437b5b1e6","redmine":"레드마인 #829 갱신 (notes, status_id)","lock":"acquired","author":{"client":"codex-mcp-client","family":"codex","authors":["codex"]}}
```

시작 응답에는 `done`·`why` 필드가 없었다. 편집·검사·커밋은 응답의 `repo`에서 했다. 운영 checkout은 main으로 두었다.
T1/T2는 구현 커밋·검사 근거로 완료 마킹했고 T3는 마감 뒤 배달까지 실제 결과가 나올 때 완료로 옮긴다.

## 검사와 결과

실행 위치 `/home/sim/ax-cluster/.ax-issues/829`, Python `/home/sim/ax-cluster/.venv/bin/python`, `AX_PROJECTS_ROOT=/home/sim/ax-cluster`.

| 검사 명령 | rc·결과 |
|---|---|
| `bash /tmp/ax-829-core-checks.sh` — `python -B master/test_orchestration_control.py`, `test_issue_flow.py`, `test_mcp_servers.py`, `test_client_mcp.py`를 순서대로 | rc0 · 30/30, 189/189, 56/56, 358/358 (총 633) |
| `bash /tmp/ax-829-integration.sh` — `python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v` | rc0 · `Ran 193 tests in 193.440s` · `OK` |
| 공식 통합 내 `test_gemini_report` | 122/122 · 구현 응답/실행 인자/사본 불변·Flash 폴백 task 유지 |
| `bash /tmp/ax-829-static.sh` — 기존 `pystatic.run_static`로 시작 리비전과 변경 `.py` 12개 대조 | rc0 · pyflakes 차단0(노트3), import 6모듈 차단0(경로명 사유 제외1), mypy call-arg 차단0(기타 코드 노트55) |
| `git diff --check` | rc0 |

검사 스크립트는 기존 검사 호출의 샌드박스 해제 범위를 좁히는 용도로만 만들었다. 기존 AX 기능의 대체 경로가 아니다.
원본 로그는 `/tmp/ax-829-integration.log`·`/tmp/ax-829-static.log`다.
핵심 검사 중 `[issue_flow] ... TypeError: Object of type object is not JSON serializable`, `[ax-client] JSON 파싱 실패 — 무시`는 기존 의도된 오류 주입 출력이며 해당 검사 rc는 0이다.

## 조회 실패와 재개

로그 경로 확인을 위해 `/tmp` 전체에서 `rg --files -g 'ax-829-*.log'`를 실행한 것은 범위를 불필요하게 넓힌 실수였다.
rc2, 실패 원문: `rg: ./systemd-private-c08ac009a2b64d3abe4095773749c6a5-ModemManager.service-TOU4dq: Permission denied (os error 13)` 등 시스템 전용 디렉터리 16건.
코드 실패로 해석하지 않고 편집·커밋·마감을 멈춰 보고했다. 실행 중 통합 검사는 그대로 보존했다.
사용자에게 「이 조회 오류를 기록하고 나머지 검증·마감·배달을 계속할까요?」라고 물었고 사용자 원문 「응!」으로 재개했다.
그 뒤 기존 통합 프로세스 종료 rc0과 위 요약을 회수했다. 직전 보고의 핵심 회귀 「673건」은 산술 오기이며 실제 합계는 **633건**이다.

## 한계와 남은 단계

- 실제 Argon 생성 호출은 0회다. `--sandbox`/`--mode plan`의 실제 제한과 unified diff 응답은 미실증이다. MCP·명령 금지는 프롬프트/지침 수준이며 완전한 접근 차단으로 보고하지 않는다.
- 서브 패치 회수는 `authors`에 `agy`를 자동 추가하지 않는다. 실제 반영 시 작성 사실을 기록하고 다른 계열이 직접 검증해야 한다. 기존 리뷰 분기를 훼손하지 않았다는 것과 서브 작성 계열 자동 추적은 다르다.
- 기본 연구 모드·기존 자동 Flash·작성 레인·세션 수집을 제거하지 않았다. 제거 대상은 마스터 지휘 타입이다.
- 마감·상주 신선도/재기동·인수인계 main 문서 커밋·워커 배달/check는 이 리포트 커밋 뒤 수행한다.
- 세션 파일: `~/.codex/sessions/2026/11/11/rollout-2026-11-11T23-49-01-01a1cb15-6c15-73b0-895f-c9ad856cd447.jsonl` (`cwd=/home/sim`, `originator=codex-tui`, 요청 「인수인계서 확인해」 일치).

최종 결과는 Redmine 마감 노트.
