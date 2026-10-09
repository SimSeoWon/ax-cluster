# #769 Redmine 위키 MCP — 로컬 구현·격리 검증

2026-10-09 · Codex · 기준 HEAD `65c33d1` · 사용자 선택: 로컬 서브 에이전트.
진행 정본: [Redmine #769](http://192.168.0.57:8080/issues/769).

## 변경과 근거

`ax-client → task_queue(8101) → master.redmine` 기존 경로에 위키 조회·작성을 연결했다.
RAG의 redmine/client_mcp 문서 본문과 실제 소스를 대조했다. 참조 전용 AgentTest의
`mcp/redmine_tracker/server.py`는 이슈 조회·쓰기를 제공하지만 위키 호출은 없었다.
위키 GET·PUT·버전 충돌·부모 보존 계약은
[Redmine 공식 REST WikiPages](https://www.redmine.org/projects/redmine/wiki/Rest_WikiPages)를 따른다.

- `redmine_get_wiki_page(title)`는 본문·버전·부모를 조회한다.
- `redmine_put_wiki_page(title, text, mode="append", version=None, comments="")`는
  기본적으로 기존 본문과 부모를 보존해 추가한다. 기존 페이지 전체 교체는 조회 버전이 필수다.
- 프로젝트는 체크아웃 태그를 기존 `project_of`로 변환한다. 태그가 없거나 설정이 없으면
  다른 프로젝트로 폴백하지 않는다. 제목·프로젝트 URL 세그먼트는 인코딩한다.
- 기존 페이지는 현재 버전을 PUT에 보내 충돌을 거부한다. 404만 신규 생성으로 처리한다.
  저장 후 GET으로 본문과 부모를 비교한다. 저장 결과 불명·되읽기 실패는
  `possibly_applied=true`, `retry_safe=false`로 반환하고 자동 재시도하지 않는다.
- 요청자 권한은 정확한 `PUT /api/v1/redmine/wiki`만 추가했다. 기존 접두·접미 규칙은 유지하고
  네 번째 문자열 `exact`로 완전 일치를 표시한다. 워커·삭제·다른 PUT 경로는 열지 않는다.
- GET·PUT의 `TAG` 정책 두 줄과 엄격한 요청 모델, MCP 도구 설명·스킬 호출 예를 추가했다.
- 기존 사양 검사의 `dry_run`도 모델을 호출하므로 테스트에 기존 `caller` 주입을 사용했다.
  Source 경계·정상 그룹·백슬래시 검사 조건을 유지하고 테스트 대역 호출 두 건을 확인한다.

백엔드와 MCP/스킬을 두 구현 에이전트에 나누고 읽기 전용 독립 검토로 대조했다.
독립 검토가 지적한 잘못된 부모 응답의 저장 후 예외 가능성은 응답 형식 검증에 반영했다.

## 실패·승인·재개

1. 첫 백엔드 패치는 auth 줄의 인라인 주석과 문맥이 달라 적용 실패했다. 백엔드 전체 미적용을
   확인하고 중단했다. 사용자 「응 다시 검증해줘」 승인으로 문맥을 바로잡아 재개했다.
2. 기존 사양 검사 `216/216`, rc0 안에서 실제 agy·Codex·브로커 샌드박스 오류가 출력됐고
   출력 일부가 잘렸다. 정상 검증 완료로 보지 않고 중단했다. 사용자 「응 진행해」로
   `tagging.py` 대상 추가와 사양 검사 호출 격리를 승인했다.
3. 최초 격리 검사는 테스트 대역이 문자열 계약에 dict를 반환해 `md.strip()`에서 rc1로 실패했다.
   외부 모델 호출은 없었다. 다시 중단했고 사용자 「응」으로 문자열 반환 수정·재검증을 승인했다.
   실제 `generate.call_broker`의 주입 caller 반환 계약을 대조한 뒤 수정했다.

## 최종 검사

모든 최종 검사는 rc0이며 출력 잘림 없이 확인했다. 검사 명령의 작업 위치는 저장소 루트다.

| 명령 | 결과 |
|---|---|
| `.venv/bin/python -B master/test_redmine_wiki.py` | 12 tests OK |
| `.venv/bin/python -B master/test_redmine.py` | 184/184 |
| `.venv/bin/python -B master/test_auth.py` | 69/69 |
| `.venv/bin/python -B master/test_client_mcp.py` | 194/194 |
| `.venv/bin/python -B master/test_client_spec.py` | 217/217, 테스트 대역만 2회 호출 |
| `.venv/bin/python -B master/test_tagging.py` | 78/78 |
| `.venv/bin/python -B master/test_client_master_local.py` | 81/81 |
| `.venv/bin/python -B master/test_client_bundle.py` | 468/468 |
| `.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v` | 25개 모듈·1,199건, 17.568초 |

위키 검사는 실제 MCP dispatch·실제 라우트 함수 본문·주입 Redmine sender·되읽기의 조합을
실행한다. 라우트 함수는 AST에서 추출해 호출했고 실제 FastAPI 서버는 기동하지 않았다.
프로젝트 태그 자동 주입은 별도 MCP 검사로 확인했다. 실 Redmine·DB·운영 서비스에 위키를
쓰는 검증과 현재 세션 네이티브 도구 노출 검증을 대신하지 않는다.

## 남은 운영 단계와 한계

- 구현·검증 직후에는 미커밋이었다. 이후 사용자 「응 그리고 인수인계서 작성해줘」로
  코드·검사·스킬10파일과 기록3파일의 커밋·푸시 및 인계 작성을 승인했다.
  실행 결과·커밋 해시는 Redmine #769와 인수인계서에서 확인한다. 서비스 재기동·배달은 미실행이다.
  운영 반영 후 MCP 노출과 실제 위키 조회·작성·되읽기를 확인해야 #769 전체 완료다.
  #768의 `아이디어수집` 위키 기록도 아직 실행하지 않았다.
- 신규 페이지의 GET 404와 PUT 사이에 다른 사용자가 같은 페이지를 생성하는 경합은 남는다.
  공식 API에는 생성 전용 조건이 명시돼 있지 않다. 기존 페이지 수정은 version으로 보호한다.
- 오늘 이전 Claude 세션(#762·#764·#767·#740)의 별도 리포트 미작성 상태는 이번 보고서로
  완료했다고 처리하지 않는다. 마스터 담당·워커 모드는 변경하지 않았다.

### 후속 (2026-10-09 20:20~, Claude 세션 · 사용자 승인)

- 커밋 `40c1012` 푸시 뒤 `ax-task-queue` 재기동(20:22:55, 신선도 3/3 OK) · 마운트 AXCluster
  배달 `update` rc=0 3/3 OK(출처 `ca395da`).
- 실 조회: MCP `redmine_get_wiki_page("아이디어수집")` → 8101 `GET /api/v1/redmine/wiki … 200`,
  응답 Redmine 404. 경로·`ax-cluster` 귀속은 동작했고, 페이지는 `modularstage` 위키에 있다
  (`docs/10-references.md:36`, 문서 근거 — 익명 위키 조회 401 이라 직접 미확인).
- 사용자 결정: 위키 페이지는 옮기지 않고 #768 은 일감 본문을 정본으로 둔다. #769 는
  「조회 실증 완료 · 실 쓰기·되읽기는 첫 실사용 때 확인」으로 **완료** 처리.
- 이전 Claude 세션 리포트는 [리포트 102](102-gemini-delegation-and-usage-dedupe.md)로 작성했다.
