# 현재 AX 작업 인수인계 — #898 Codex → Claude

> 2026-11-08 · 사용자 「토큰이 없다 인수인계서 작성해주면 클로드에서 진행할게」.
> **이 최신 파일은 `/home/sim/ax-cluster/.ax-issues/898/docs/orchestrator-handoff.md`에만 있다.**
> 운영 main의 동명 파일은 이전 체크포인트다. 운영 저장소 편집 금지 때문에 여기 남겼다.
> #898 미마감·미커밋, 작업 잠금 활성. 세션 인계와 issue_pause는 다르다. 워커 모드는 codex 유지.

## 바로 다음 작업

1. 이 파일과 `reports/148-898-requester-management-proxy.md`, Redmine #898 본문·노트를 읽고 실제 diff와 대조한다.
2. 마지막 실패는 **스킬 규약 47/49**. 두 이름 표기를 고친 뒤 재실행할 자리에서 중단했다.
   - `master/client/workshop/skills/manage-domain/SKILL.md:151`: 제목 `클래스 개명·이동 (rename_class)`.
     실행 호출이 아닌 제목을 기존 무서버 이름 검사가 잡은 **오탐**. 실제 도구 표기와 맞추거나 호출/제목 판정을 바로잡는다.
   - `master/client/workshop/skills/refresh-ontology/SKILL.md:35`: `(개명/이동은 rename_class 또는 /manage-domain 후 본 스킬로 마무리.)`.
     **서버 없는 기존 안내**. 이 파일은 읽기만 했고 아직 수정 대상에 등록하지 않았다. 이 참조를 실제
     `ax-client:rename_class(domain, old, new, apply=False)` 계약과 맞추는 최소 수정이 다음 후보다.
   - 실패 뒤 코드·검사 중단. 사용자 마지막 발화는 인계 작성 요청이며 두 표기 수정의 재개 승인은 아직 없다.
3. 수정·재개 승인 후 `test_skill_conventions.py`, 필요시 정적 검사, **공식 통합**을 마무리한다.
   공식 통합은 아직 한 번도 실행하지 않았다. 검사 완료 뒤 커밋 범위·메시지를 보여주고 승인받는다.
4. 커밋·push·finish·배달·상주 재기동은 미승인·미실행. 일감을 닫거나 운영 데이터를 고치지 않았다.

## 위치·실제 상태

- 편집·검사·커밋 위치: `/home/sim/ax-cluster/.ax-issues/898`, 브랜치 `issue/898`.
- `issue_start_tool(898)` 응답: `repo=/home/sim/ax-cluster/.ax-issues/898`,
  `checkout=/home/sim/ax-cluster`, `start_rev=d946ba7eef5d4d6db9516628afcf1350aa32683d`, `lock=acquired`.
- 운영 `/home/sim/ax-cluster`: `main=origin/main=d946ba7`, `git status --short --branch` rc0은
  `## main...origin/main`뿐이다. **코드·인계서를 운영 main에 미커밋으로 복사하지 않는다.**
- Redmine 마지막 상태: #898 진행·done_ratio0; T1 작업중, T2 차단, T3 작업중. 완료 태스크 없음.
- 새 커밋 없음. worktree에 아래 파일과 이 인계서가 미커밋. 지우거나 새로 구현하지 말고 이어받는다.
- 마스터 마지막 담당 기록 claude(11-07), 워커 전역 codex(state). 이번 세션에서 기록·모드 변경 안 했다.
- 세션: `~/.codex/sessions/2026/11/08/rollout-2026-11-08T16-01-05-01a1b9f5-f096-70c2-a50b-7c5a24685d9e.jsonl`.

## 사용자 결정과 구현 범위

- 요청자 PC는 프로젝트마다 다르다. **요청자가 자기 프로젝트를 관리하고 마스터가 집행**한다.
  요청자 `ax-client` → 프로젝트 태그·요청자 토큰을 실은 **8101** → 기존 마스터 코어 한 벌.
  공개 8103 쓰기·요청자에 마스터 MCP 연결·임시 대체 실행 경로는 만들지 않는다.
- 「그래 그럼 네 추천한 방식으로 로컬로 작업 진행하자」 → 로컬 서브 에이전트 방식.
- manage-domain 추가 기능 선택 질문 뒤 「이번에 한번에 처리하자」 → 구현된 마스터 기능 대행까지 #898에서 함께 처리.
- 도메인 전체 삭제·멤버 추가/제거는 현재 코어를 확인하지 못해 새 코어를 지어내지 않았고 스킬에 미지원 명시.
- 생성의 한글 이름 허용과 개명의 ASCII 제한은 서로 다른 현행 코어 계약이다.
- RAG request_id=`b4d70f8f74034edd89224d1fe30a0246`.
  운영 트윈의 `context/master/projects/mcp_server.md`·`context/client/runtime/client_mcp.md`를 현재 소스와 대조했다.
  **기존 search_context는 후보 질문을 반환하지 않는다.** 부모의 초기 대체 설명을 정정하고 resolve_terms를 별도 대행했다.

## 현재 구현·변경 파일

- `client/runtime/client_mcp.py`, `master/test_client_mcp.py`: 관리 **20개** 도구·스키마·dispatch·회귀.
  resolve_terms, create_domain, edit/remove/lock_ontology_item, list_locked, unassigned_classes, sync_ontology,
  list_workshops, check_workshops_clean, edit_domain_field, list/set/remove_log_tag,
  staging_begin/commit/discard/status, rename_domain, rename_class.
- `master/auth.py`, `master/task_queue/server.py`, `master/task_queue/tagging.py`:
  20개 POST 대행·역할 스코프·필수 태그/마운트 정책. 새 관리 경로는 exact, 시소러스의 기존 prefix는 유지.
- 신규 `master/task_queue/ontology_proxy.py`, 신규 `master/test_ontology_proxy.py`:
  기존 코어 호출, 이름·실경로 경계, 입력 여분 금지, nullable 생략/null/빈목록 의미 보존.
  rename는 기본 계획, apply 때 서버가 현재 계획 재생성. 클라이언트 plan 경로 주입 금지.
  staging 편집·삭제·잠금·잠금 목록은 실제 사본 대상, commit/discard 전 라이브 보존.
  세션중 필드·로그 쓰기·sync 적용·개명·별칭 등록은 유실 방지를 위해 거절. 잠금/force 보호 유지.
- `master/client/skills/ax-ontology/SKILL.md`, `master/client/skills/ax-request/SKILL.md`,
  `master/client/workshop/skills/manage-domain/SKILL.md`: 실제 요청자 도구·인자·결과 범위로 정정.
- `master/test_skill_conventions.py`: 배달 역할별 MCP 서버·실재 도구 검사. 여러 역할이면 서버 교집합.
  “그 도구가 아니다”라는 명시 부정 설명은 해당 참조 하나만 제외한다.
- 신규 `reports/148-898-requester-management-proxy.md`: 사용자 원문·실증 응답·실패·검사 상세.
  리포트는 마감 전 시점까지만, 마지막은 「최종 결과는 Redmine 마감 노트」.

## 검증 결과와 한계

- 클라이언트(에이전트): `AX_PROJECTS_ROOT=/home/sim/ax-cluster /home/sim/ax-cluster/.venv/bin/python -B master/test_client_mcp.py`
  rc0, **350/350**. JSON-RPC→queue_api→HTTP 경로·태그·토큰·nullable·기본값·캐시 미사용·거절 보존.
- 서버(에이전트): 승인된 `sh /tmp/ax-898-server-check.sh`, rc0, **13/13**, `Ran 13 tests in 0.908s · OK`.
  20경로 분모·인증/태그·실제 코어·staging live 보존/반영/폐기/manifest·색인1회·경로 방어 확인.
  임시 프로젝트 데이터/실제 ASGI 앱이며 일부 조회·색인·서비스 스레드는 대역. 운영 배포 실증은 아니다.
- 정적(부모): 승인된 `sh /tmp/ax-898-static-check.sh`, 기준 d946ba7·Python8파일, rc0.
  pyflakes 차단0·비차단노트1, import5 차단0·환경0, mypy 차단0·비차단노트42, setup_error없음.
  모든 타입 오류0이라는 뜻은 아니다. 새 proxy의 분기별 결과 변수 재사용에 따른 비차단 노트도 있다.
- 마지막 규약: rc1 **47/49**, 위 두 표기만 실패. 변경 후 재실행 필요.
- `git diff --check` 마지막 rc0. 독립 읽기 검토에서 최종 서버 추가 차단 지적 없음.
- 공식 통합: **미실행**. 준비만 한 `/tmp/ax-898-integration-approved.sh`는 승인·실행 전.
  정본 명령: `AX_PROJECTS_ROOT=/home/sim/ax-cluster /home/sim/ax-cluster/.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v`.
  공식 목록은 auth/tagging/client/도메인 코어/스킬 검사를 포함한다. 새 서버13개 회귀는 목록 밖 별도 결과다.
- 전체 reports 전문 복원을 마쳤다고 주장하지 않는다. 서비스 재기동·새 도구의 현재 세션 노출도 검증하지 않았다.

## worktree 보류·재개는 실증 완료

- T1 시작·편집 전 깨끗한 상태에서 사용자 요청대로 `issue_pause_tool(898)` → `issue_start_tool(898)`.
- 보류: `ok=true, paused=true, branch=issue/898, end=d946ba7...`.
  로그 `잠금 해제 · 브랜치 issue/898 유지`, `worktree .../.ax-issues/898 제거`.
  `ls -la .ax-issues`는 빈 부모, worktree 목록에 #898 없음, show-ref는 같은 브랜치 리비전.
- 재개: `ok=true, resumed=true, repo=.../.ax-issues/898, start_rev=d946ba7..., lock=resumed`.
  status와 HEAD도 동일. 잠금 이력 acquire16:13:05 → pause16:15:41 → resume16:15:54 KST.
- 이는 깨끗한 worktree의 제거·복원 실증이다. 미커밋 파일/추가 커밋을 가진 보류는 검증하지 않았다.
  **현재는 dirty이므로 pause 재실행 금지.** 인계를 이유로 잠금을 풀거나 파일을 지우지 않는다.

## 중단·승인 이력과 유지 규칙

- 첫 규약48/49 실패(manage-domain 옛 호출) → 「응! 도메인 처리쪽인가」로 대상 추가·재개.
- 서버 TestClient가 기본 샌드박스에서 2분 대기→Ctrl-C rc130. 동일 검사 밖에서 rc1 8개중1실패(405≠403).
  기존 GET /works prefix가 /workshops에도 일치해 POST 전용 라우터405였다. 현재 검사는 거절+core 미실행으로 보완.
- staging 패치 문맥 오류 미적용→중단, 사용자 「응!」 재개. 이후 불필요 /tmp 재귀조회 Permission denied rc2→중단,
  「응 좁혀서 진행해」로 확인된 파일만 사용해 재개. /tmp 전체 검색하지 않는다.
- 읽기 조회 `No such file or directory`만 확인된 경로 재조회 예외. 다른 실패는 보고·중단.
  Git sg gitea/audit 차단은 저장소 부재가 아니다. 좁은 검사 스크립트 승인으로 같은 검사만 밖에서 실행한다.
- 운영 main 편집 금지·issue_start 응답 repo에서 작업·AXCluster/repo는 push봉인 색인 미러.
  마감 승인 뒤에만 main 인계 문서 커밋·push 규칙을 적용한다. 현재는 새 커밋·finish 응답(done/why) 없음.
- 과거 #895 등 완료 작업·보존 worktree/큐/스풀은 건드리지 않는다. 이전 운영 기록은 d946ba7의 운영 인계서에 있다.
- 이 세션 서브 에이전트는 모두 종료/편집 중단. Claude는 실행 ID 인수 대신 실제 파일·리포트·Redmine으로 이어받는다.
