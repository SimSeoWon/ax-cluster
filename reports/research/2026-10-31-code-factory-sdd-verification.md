# 코드 팩토리·SDD 확장 보고서 — Codex 2차 검증
작성: 2026-10-31 · 기준 HEAD 884f8a2
대상: 2026-10-31-code-factory-sdd.md (Gemini 원문), .html (Codex 최종 보고서)

## 판정
핵심9항목을 대조해 일치6·불일치/과대해석3을 확인했다. Gemini 인용80개는 모두 범위 안이지만 내용80개 전체를 검증한 것은 아니다.
원문은 보존하고 검증 머리말만 갱신했다. 최종 HTML은 Codex가 직접 확인한 사실과 제안으로 편집했으며 아래 불일치 주장을 채택하지 않았다.

| 항목 | 대조 근거 | 결과 |
|---|---|---|
| 1. 이전 로그19검색/17요청, 반환100개 중 빈25개 | 이전 Codex 검증 기록11~16행 및 search.py:107~128, #851 | 일치. 이전 분석의 고정 스냅샷으로 사용. 현재 로그 총량으로 표현하지 않음. |
| 2. plan_register는 improvement_plan 등록 | citations.txt의 plan_register.py:275~276 절, 실제 소스249~315행 | 일치. 새 일반 실행 플랜 엔진이 구현됐다고 확대하지 않음. |
| 3. #826 버전→프리 에디터 및 어셋 우선 제거 | citations.txt의 issue-826.md:37~45 / 58~61 절, MCP 재조회 자료 | 일치. 사용자 승인 전 어셋 제거 금지 및 소스변경 위치 유지. |
| 4. advance/finalize confirm=False | citations.txt의 review-selected.txt:5~9 절, review.py:868~895 /1245~1272 | 일치. 기존 승인 계약을 재사용하며 새 게이트를 자동 추가하지 않음. |
| 5. Monolith/Epic 문서상 기능과 AX 실제 설치 분리 | Codex가 직접 연 공식 README/Epic 문서, issue-856 | 일치. 문서 확인은 설치·도구 호출 성공이 아님. |
| 6. #791 좁은 후속 라운드 실패 문제 | citations.txt issue-791.md:37~41 절, 최신3노트 사본 | 일치. 이슈 기록에 따른 현재 미결이며 이번에 실행 재현하지 않음. |
| 7. 세션 교대·중단이면 기존 승인 무효 (Gemini 200행) | orchestrator-rules.md:133~135 | [검증 불일치] 규칙은 승인 범위·근거를 전달하고 교대만으로 이미 받은 승인을 다시 요구하지 않는다고 명시. HTML은 기존 승인 유지와 변경 영향 대조로 작성. |
| 8. #851은 #855의 확정 선행조건, #820의 3표본 모두 정당한 연쇄수정 (Gemini 440행) | citations.txt issue-855.md:34 / issue-820.md:54~66 절 | [검증 불일치/과대해석] #855는 #851 연계·중복구현 금지라고만 한다. #820 표본3개는 연쇄수정·마스터 피드백 측정잡음·필요 선언으로 서로 다르다. HTML은 연계/우선순위 제안과 범위고지로 한정. |
| 9. Monolith 루프백 바인딩을 당장 적용할 수 있다는 해석 (Gemini 438행 제안) | 공식 Monolith README Network exposure 절 | [검증 한계/과대해석] README는 FHttpServerModule의 bind-address 인자 부재로 모든 인터페이스 listener를 설명한다. 코드변경 없이 loopback 설정 가능하다고 보증할 수 없다. HTML은 로컬 연결/중계·네트워크 계약 검토 제안으로 한정. |

외부 근거:
- https://github.github.com/spec-kit/quickstart
- https://www.anthropic.com/research/effective-harnesses-for-long-running-agents
- https://docs.github.com/en/copilot/tutorials/cloud-agent/get-the-best-results
- https://github.com/tumourlove/monolith
- https://dev.epicgames.com/documentation/unreal-engine/unreal-mcp-in-unreal-editor

## 조사·산출물 범위
웹 페이지 본문은 Codex가 직접 확인하고 요약 사본을 Gemini에 제공했다. Gemini에는 src/ 사본30개만 전달했다.
자료/BRIEF: /tmp/ax-gemini-code-factory-sdd-ARtygx
Gemini 실행: 정본 master.work.gemini_report, 모델 gemini-3.8-flash-medium 일치, rc0, 271.6초, 인용 범위80/80.
사용량은 AXCluster/usage_log.jsonl, 실행 봉투·인용은 2026-10-31-code-factory-sdd.run/에 남는다.
Redmine 조회15건은 본문과 최신3개 노트를 자료에 포함했으며 이전 전체 이력을 전수 검토한 것이 아니다.
소스 발췌/존재 확인, 이슈 기록, 외부 문서, 본 보고서의 제안을 HTML에서 구분했다.
전체 회귀/원격 워커/에디터 설치·편집 실증은 이번에 실행하지 않았다. 정책·코드·배포·어셋 변경 없음.

## HTML 확인
12개 절, 중복ID/누락목차 없음, 로컬 파일 링크 존재 확인. Chrome headless에서 데스크톱 렌더 스크린샷 확인.
Chrome CDP로 12개 절·최종 검증문구·부분/전체 필터·제거/코드 탭 전환 6항목 통과. 1440/390px 화면에서 문서 가로 넘침 없음, 데스크톱·모바일 스크린샷 확인. 인쇄 스타일은 포함했으나 실제 PDF 출력은 미실행.

