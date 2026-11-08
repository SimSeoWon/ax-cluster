# 148 — #898 요청자 관리 도구의 마스터 대행

2026-11-08 · Codex · http://192.168.0.57:8080/issues/898

## 사용자 지시·범위

- 원문: 「인수인계서 확인하고 #898 진행해. ax-client 에 대응 도구가 없는 기능은 대행을 만들지 스킬에서 뺄지 플랜 단계에서 나한테 물어봐. 작업 중간에 issue_pause_tool 로 한 번 보류했다가 issue_start_tool 로 재개해서 worktree 보류·재개도 확인해 줘.」
- 선택: 「요청자에서 관리하는게 맞아보여. 우리는 지금 AX 클러스터링 개수 작업을 하니까 같은 PC지만 다른 언리얼 프로젝트는 다른 컴퓨터에서 작업을 할꺼야!」 → 요청자가 자기 프로젝트를 관리하고 마스터가 집행한다.
- 확정: 「그래 그럼 네 추천한 방식으로 로컬로 작업 진행하자」 → `ax-client` → 인증 8101 → 기존 마스터 코어. 로컬 서브 에이전트 server_898/client_898/skills_898로 파일을 나눴다.
- 중단 후 「응! 도메인 처리쪽인가」로 `manage-domain` 포함 수정·재개 승인. 추가 기능 선택 질문 뒤 「일감을 나눠서 다른 일감에처 처리할지 아니면 여기서 처리할지 인가? 이번에 한번에 처리하자」로 구현된 마스터 기능의 대행을 같은 일감에서 처리한다.
- 커밋·push·마감·배달·재기동 승인은 아직 없다. 운영 온톨로지 실물 쓰기는 하지 않는다.
- 세션: `~/.codex/sessions/2026/11/08/rollout-2026-11-08T16-01-05-01a1b9f5-f096-70c2-a50b-7c5a24685d9e.jsonl`.

## 기준·근거

- 운영 `main=origin/main=d946ba7eef5d4d6db9516628afcf1350aa32683d`, 시작·재개 때 깨끗함.
- RAG request_id=`b4d70f8f74034edd89224d1fe30a0246`.
- 읽은 RAG 본문: 운영 트윈의 `AXCluster/context/master/projects/mcp_server.md`, `AXCluster/context/client/runtime/client_mcp.md`. 현재 `master/projects/mcp_server.py`, `client/runtime/client_mcp.py`, 서버·인증·태그 정책 및 온톨로지 코어와 대조했다.
- 읽기 전 경로 목록과 본문을 별도 호출했다. 이전 준비 조회의 `master/runtime` 부재(rc2)는 확인된 `client/runtime/client_mcp.py`로 재조회했다. 사용자 11-08 경로 부재 예외 규칙 적용 뒤 같은 이유로 멈추지 않는다.

## 실제 worktree 보류·재개

`issue_start_tool(898)` 응답 주요 원문:

```json
{"ok":true,"issue_id":898,"branch":"issue/898","repo":"/home/sim/ax-cluster/.ax-issues/898","checkout":"/home/sim/ax-cluster","already":false,"start_rev":"d946ba7eef5d4d6db9516628afcf1350aa32683d","lock":"acquired"}
```

T1 작업중 전이 후 편집 전 깨끗한 중간 상태에서 실행했다. `git status --short --branch` rc0=`## issue/898`, `git rev-parse HEAD` rc0=`d946ba7eef5d4d6db9516628afcf1350aa32683d`.

`issue_pause_tool(898)`:

```json
{"ok":true,"issue_id":898,"paused":true,"branch":"issue/898","end":"d946ba7eef5d4d6db9516628afcf1350aa32683d","start_rev":"d946ba7eef5d4d6db9516628afcf1350aa32683d"}
```

로그 원문: `pause.lock: [issue_lock] #898 pause: 보류 — 잠금 해제 · 브랜치 issue/898 유지`; `pause.switch: worktree /home/sim/ax-cluster/.ax-issues/898 제거 · issue/898 유지 @ d946ba7eef5d`.
운영 위치 `ls -la .ax-issues` rc0에는 `.`·`..`만 있었다. `git worktree list --porcelain` rc0에서 #898은 없고, `git show-ref --verify refs/heads/issue/898` rc0은 같은 리비전을 반환했다.

`issue_start_tool(898)` 재개:

```json
{"ok":true,"issue_id":898,"branch":"issue/898","repo":"/home/sim/ax-cluster/.ax-issues/898","checkout":"/home/sim/ax-cluster","already":false,"resumed":true,"start_rev":"d946ba7eef5d4d6db9516628afcf1350aa32683d","lock":"resumed"}
```

재개 뒤 status·HEAD도 위와 동일했다. 운영 `AXCluster/issue_lock.json`의 #898 이력은 acquire=`2026-11-08T16:13:05+09:00`, pause=`16:15:41`, resume=`16:15:54`; active는 #898, paused는 빈 사전이다. 이 실증은 미커밋 변경 없는 worktree의 보류·재개이며, 변경·추가 커밋을 가진 보류를 검증한 것은 아니다. finish 미호출로 `done`·`why` 응답은 없다.

## 항목별 대조

1. **참 — 스킬의 서버 불일치.** `spec.MCP_BY_ROLE`은 요청자·워커에 ax-client만 배달한다. 기존 ax-ontology와 ax-request §5의 ax-projects 호출은 그 계약과 다르다. 실제 .33 세션에서의 과거 호출 실패는 재현하지 않았다.
2. **거짓 — search_context로 용어 후보 조회까지 대체 가능하다는 부모의 초기 설명.** 실제 8103 combined 검색은 질의 확장·검색만 하고 `resolve_terms_tool`의 후보·질문 응답을 돌려주지 않는다. 설명을 사용자에게 정정하고 별도 resolve_terms 대행을 포함했다.
3. **참 — manage-domain의 옛 계약.** 신규 도구 등록 뒤 기존 무서버 호출 검사가 create_domain/edit_ontology_item을 검출했다. 지원하지 않는 생성 인자·옛 항목 인자·로컬 watch.exe 경로·자동 staging/DB cascade 주장도 현재 코어와 대조가 필요했다.
4. **부분 — 도메인명 한글 금지.** 현재 create.validate_name은 한글을 허용한다. rename 코어는 새 이름의 ASCII를 요구하므로 생성과 개명의 규칙을 하나로 단정하면 안 된다.
5. **참 — 미구현 안내.** 도메인 전체 삭제·멤버 추가/제거는 현재 Python 정의/사용 검색에서 구현을 확인하지 못했다. 새 도구 이름을 지어내거나 코어가 있는 것처럼 안내하지 않는다.

## 실패와 승인된 재개

- 스킬 검사: `AX_PROJECTS_ROOT=/home/sim/ax-cluster /home/sim/ax-cluster/.venv/bin/python -B master/test_skill_conventions.py`, rc1, `FAIL test_skill_conventions: 48/49 통과`. 유일 실패 `master/client/workshop/skills/manage-domain`의 `SKILL.md: 서버 없는 MCP 도구 이름 ['create_domain', 'edit_ontology_item']`. 즉시 중단·T2 차단, 사용자 승인 뒤 대상 포함·재개.
- 서버 검사: 동일 환경의 `master/test_ontology_proxy.py -v`, 기본 샌드박스에서 첫 테스트 2분 이상 무출력 대기, Ctrl-C rc130(단언·예외 출력 없음). 구조를 바꾸지 않고 같은 명령만 담은 `/tmp/ax-898-server-check.sh`를 승인 후 밖에서 실행했다. 밖에서는 0.450초에 8개 실행, rc1, `FAILED (failures=1)`, `test_ontology_proxy.py:79 AssertionError: 405 != 403`. 원문은 GET 거절 코드 기대값이다. 기존 GET `/api/v1/works` prefix가 `/api/v1/workshops`에도 일치해 POST 전용 라우터가 405를 내는 것으로 소스 대조했다. 신규 POST 관리 권한 우회로 단정하지 않았다. 즉시 중단·T1 차단, 사용자 「이번에 한번에 처리하자」 뒤 검사의 실제 거절·코어 미실행 확인으로 보완 승인.
- 독립 읽기 검토: proxy의 원문 이름 경계 검사와 코어 trim 경로 불일치 지적. validate_name 반환값을 검사·실제 호출 양쪽에 사용하도록 고쳤고 dangling symlink 회귀를 추가했다. 운영 트윈 공격 실증은 하지 않았다.

## 검증·현재 지점

확장 20도구 클라이언트 회귀 rc0 `350/350 통과`(에이전트 실행 결과)。staging item edit/remove/lock adapter 적용 중 `apply_patch verification failed: Failed to find expected lines in .../master/task_queue/ontology_proxy.py`가 발생했다. 실제 domain 블록과 다른 주석 문맥을 쓴 편집 오류이며 실패 패치는 미적용이었다. 중단 뒤 사용자 「응!」으로 재개했다. 직후 에이전트가 불필요하게 `/tmp` 전체를 `rg --files`로 조회해 systemd-private 경로의 `Permission denied` rc2가 났다. 코드·검사 문제가 아니며 다시 중단했고, 사용자 「응 좁혀서 진행해」 뒤 이미 부모가 생성·실행한 정확한 스크립트만 사용했다.

최종 서버 회귀(에이전트): `sh /tmp/ax-898-server-check.sh` rc0, `Ran 13 tests in 0.908s`, `OK`。20개 HTTP 라우트 분모, 인증·태그, 기존 코어, 편집/잠금/삭제의 실제 staging 전환, commit/discard·라이브 보존·manifest 갱신·색인 호출 1회, 세션중 라이브 쓰기 거절, 개명 계획/적용, 경로 경계를 확인했다. 운영 트윈이 아닌 임시 프로젝트 데이터와 실제 ASGI 앱의 회귀다. 서버 실행·스레드·색인·일부 조회는 명시 대역이며 운영 배포 성공으로 확대하지 않는다.

부모 정적 검사: 기존 `master.work.pystatic.run_static('.', 'd946ba7eef5d4d6db9516628afcf1350aa32683d', files8, python=sys.executable, flakes_python=sys.executable)`를 `/tmp/ax-898-static-check.sh`에 정확히 담아 승인 후 실행. rc0; pyflakes8파일 차단0·노트1(auth의 기존 f-string), import5모듈 차단0·환경0, mypy8파일 차단0·비차단 노트42, setup_error없음. 노트42는 정책상 비차단이며 새 파일의 분기별 결과 변수 재사용에 따른 assignment/attr-defined도 포함한다. 이것을 모든 타입 오류0으로 표현하지 않는다.

최종 스킬 검사 재실행 rc1 `FAIL test_skill_conventions: 47/49 통과`로 현재 중단했다. manage-domain:151의 제목 `클래스 개명·이동 (rename_class)`은 실행 호출이 아닌 오탐이고, 대상 밖 refresh-ontology:35의 `(개명/이동은 rename_class 또는 /manage-domain 후 본 스킬로 마무리.)`는 서버 없는 기존 안내다. 미수정·T2차단, 사용자 재개 승인 대기다. 현재 manage-domain은 staging 사본 편집·조회·commit/discard 및 거절 계약으로 갱신됐다. 공식 통합·커밋은 미실행이다. 전체 reports 전문 복원을 마쳤다고 주장하지 않는다.

## Claude 인수 뒤 (2026-11-08 16:40~)

Codex 한도 소진으로 사용자 「토큰이 없다 인수인계서 작성해주면 클로드에서 진행할게」 → Claude가 worktree 인계서·이 리포트·Redmine 노트·실제 diff를 대조해 인수했다(마스터 담당 기록 claude 16:41). 규약 47/49를 인수 시점에 재현했다.

- 사용자 「응 refresh-ontology 포함해서 진행해」: manage-domain:151 제목을 `클래스 개명·이동 (rename-class)`(같은 파일 60행 하위 명령 이름)로, refresh-ontology:35를 `ax-client:rename_class`로 고쳤다(그 줄의 기존 후행 공백 제거 — `git diff --check` rc0). 규약 rc0 `OK test_skill_conventions: 49/49 통과`.
- 같은 시점 재실행: 서버 `sh /tmp/ax-898-server-check.sh` rc0 `Ran 13 tests in 0.838s`·OK, 클라이언트 rc0 `350/350 통과`.
- 공식 통합 1차: rc1, `Ran 100 tests in 79.368s`·`FAILED (failures=1)`(`-f`로 100번째에서 중단). 실패 `test_182_test_handoff_size` 6/7 — 「「바로 다음 작업」 절 없음」. Codex 인계본이 절 제목을 `## 바로 이어갈 자리`로 써서 `^#{2,3}\s*바로 다음 작업` 판정과 어긋났다. #898 코드 회귀가 아니다. 중단·T3 차단 후 사용자 「응 1번으로 진행해」로 제목만 `## 바로 다음 작업`으로 바꿨다(`test_handoff_size` 7/7).
- 공식 통합 2차: 정본 명령(`AX_PROJECTS_ROOT=/home/sim/ax-cluster … -m unittest discover -s tests/integration -p test_axcluster.py -f -v`) rc0, **`Ran 188 tests in 167.594s`·`OK`(188/188)**.
- 커밋·push·마감·배달·상주 재기동은 이 시점까지 미승인·미실행이다.

최종 결과는 Redmine 마감 노트.
