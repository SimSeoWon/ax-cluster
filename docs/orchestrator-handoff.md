# 현재 AX 작업 인수인계

> [중요] **한 벌만 유지한다.** 새 인계 파일을 만들지 않고 이 파일을 덮어 쓴다.
> 양식은 `docs/15-orchestrator-handoff.md` §15.5, 공용 규칙은 `docs/orchestrator-rules.md`.
> 받는 쪽은 이 문서의 완료 서술도 HEAD·dirty diff·Redmine·프로세스로 직접 대조한다.

- **갱신 시각**: 2026-10-03 21:20 KST — Claude
- **지휘 도구 / 세션**: Claude (Codex 는 사용 한도 소진 · 21:56 리셋 예고).
- **상태**: AXCluster 첫 분산 작업(#718)을 2라운드로 완주하고 `f22f741` 로 main 마감했다. 리포트 88.
  리포트 88·README·이 문서는 사용자 승인으로 커밋·push 했다. #716 은 아직 열려 있다(완료 판정은 사용자).
- **관련 일감**: #718(완료) · #260·#375·#615(완료) · 신규 결함 #719·#720·#721 · #716.
- **워커 지휘자 모드**: **`claude`** (사용자 지시 2026-10-03 20:44 「모두 클로드를 바탕으로 작동하게 바꿔줘」).
- **마운트**: `AXCluster` — `.57` 요청자, `.2`·`.33`·`.43` worker.
- **HEAD / origin/main**: `f22f741` (마스터 · `.43 ~/ax-cluster` 일치). `ax-projects` 21:15:54 재기동.

## 0. 지금 넘기는 상태 — 아래 이력보다 이 절이 최신

### 최신 — AXCluster 분산 작업 완주 (리포트 88)

- work `20261003_2046_axcluster_claude_260_375_615_54c7eb59`: 라운드1 3/3 → ⑦ 전진 → 라운드2 4/4
  (첫 파일만 전달된 결함 #719 때문에 남은 4파일을 한 파일짜리 조각으로) → ⑦ 전진 → finalize `f22f741`.
  브랜치 8개 자동 정리 · #718 완료. main 에서 통합 검사 `TESTS OK (10)` 426건.
- 첫 등재 `…_67758157`(codex 스탬프)은 codex 한도로 실패 → 조각 취소·work cancelled. 그 브랜치 5개(원격 base·미병합 조각 3 · 로컬 base)는 사용자 확인 후 21:40 삭제했다(조각 3개는 피드백 주석 커밋뿐).
- 마감 뒤 후속 처리: 색인 커서 `611fdba7→f22f741b`(#375 판정 첫 운영 통과) · 리뷰 큐 완료 12(R8~R12 등) · 포기 5 — 전부 `[ADVANCE]` 머지 커밋(고유 diff 없음 → deterministic 포기). 21:39 큐 0건.
- `.43` claude 인증은 사람이 `claude auth login` 으로 복구(21시경). 다음 세션은 #721 이 고쳐지기 전까지
  모드 변경 뒤 `claude auth status` 를 워커마다 직접 본다.
- 남은 판단: #719~#721 착수 순서 · #716 종결 여부 · 아래 이력의 「남은 일」은 이번에 대부분 소진됐다.


### 검증 완료 — Claude 인계 후 (최신, 아래 Codex 서술의 「미완료」를 대체)

리포트 [`87`](../reports/87-axcluster-integration-checks.md). 요지:

1. 5개 파일이 아래 서술과 일치. 회귀 직접 실행 15/15 OK.
2. 프로필 값으로 실제 `build_local.local_test_fn` 호출 → `TESTS OK (7)` · 3.4초 · 트리 불변.
   건수 broker14 · workshop77 · source_scope32 · python_commit_review7 · build_local36 ·
   skeleton_gate51 · integration_checks15. (샌드박스 밖 Claude 세션이라 source_scope 제약 없음.)
3. 저장소 밖 사본에 실패 주입 9/9 차단(rc1 · 0건 · 전부 skip · unittest 실패 · 파일 없음 ·
   빈 목록 · 깨진 JSON · 경계 밖 · 타임아웃). 한계: 자기 요약만 찍고 rc0 인 스크립트는 통과한다.
4. 연결: `payload/profile` → `bundle._tests_for` → 배달 `.ax/config.json` `tests` → `ax-advance`.
   **작업장 배달 전에는 효과 없음**(현 배달본 `384a07a`).
5. 공용 `parse_unittest` 가 첫 `Ran` 줄을 집어 실패 시 요약 숫자가 틀릴 수 있다(판정은 맞음).
   사용자 결정: #716 노트에만 남기고 고치지 않는다.

[완료] 커밋·푸시 `a3eb788`(Gitea · `.43 ~/ax-cluster` 동일). 워커 3대 AXCluster 체크아웃 ff-only →
`a3eb788`. 5프로젝트 `master.client update` rc=0 · 검사 15/15 OK · 출처 HEAD 일치 · AXCluster 워커
`tests` 새 값 실측. 아래 「남은 일」 1~4는 이로써 끝났다(#716 journal 참조).
[주의] deliver 가 `.2` Kimodo·AXCluster 에서 「claude_mcp_local … ~/.claude.json 에 없다」를 찍었으나
`claude mcp list` 실측은 ax-client Connected — 대조 오탐 추정, 원인 미조사.
남은 것: 분산 전체 실증(아래 5번)은 사용자 지시 대기. #716 완료 판정은 사용자 몫.

### 바로 다음 작업 — AXCluster 통합 검사 보완 (Codex 기록)

사용자 “보완작업은 어떻게 진행할거야?”→“진행해봐”로 구현을 승인했다. RAG와 기존 검사 계약을
조사한 뒤, 선택된 로컬 서브 에이전트 방식으로 구현·분류를 나눴다. 마지막 요청은 인수인계이므로
추가 검증·수정·배포를 멈췄다. **이번 변경에 대한 커밋·푸시 승인은 받지 않았다.**

문제: 기존 AXCluster 프로필의 `unittest discover -s master -p test_*.py`는
스크립트의 `__main__`/순수 함수 검사를 실행하지 않는다. 일부 TestCase만 실행돼 N>0을 만족해도
다른 검사의 누락이 감춰진다. 공용 `master/work/build_local.py`는 수정하지 않았다.

현재 구현 파일(새 파일4개 + 기존 프로필1개):

- `master/integration_checks.py`: 명시 JSON 검사 목록 검증, 각 스크립트 별도 Python 프로세스,
  rc·실행 건수·전체/실패/skip 증거 검사. 누락/0건/타임아웃/전부 skip/잘못된 목록은 차단.
  각 자식에 임시 AX_PROJECTS_ROOT·AX_GITEA_REPO_ROOT 및 -B를 적용한다.
  **환경 분리는 완전한 보안 샌드박스가 아니다. 검토된 목록만 실행해야 한다.**
- `master/test_integration_checks.py`: 실제 임시 자식 프로세스를 사용하는 회귀 TestCase15개.
- `tests/integration/checks.json`: 필수 검사7개를 명시. broker_routing, workshop_check,
  source_scope, python_commit_review, build_local, skeleton_gate 및 새 integration_checks.
  검사별180초 제한·출력 형식별 건수 정규식.
- `tests/integration/test_axcluster.py`: 목록을 읽어7개 unittest를 만들고 각 스크립트를 실제 실행.
- `master/client/payload/profile/AXCluster.yaml`: `test_start_dir: tests/integration`,
  `test_pattern: test_axcluster.py`로 변경. 나머지 프로필 값은 그대로다.

실행/검토 근거:

- 구현 에이전트 `/root/716_type_scope`가 새 회귀 검사 **직접 실행15/15 및
  `-m unittest master.test_integration_checks`15/15**, 당시 diff --check 통과를 보고했다.
  rc1·타임아웃·파일 없음·요약 누락/0건·total 불일치·failed>0·allskip·환경 비전파를 검증했다.
- 분류 에이전트 `/root/716_test_inventory`: 기존144파일 중 TestCase7파일을 AST로 식별했고
  후보9개만 전문 검토했다. **나머지135개 안전성은 미검토**, 전체144 검사 커버리지 아님.
  `test_client_bundle.py`는 실제 .33 SSH 및 기존 hooks/__pycache__ 삭제가 있어 목록에서 제외.
  layer1/project_profile은 실제 등록 프로젝트/소스 읽기 의존성이 있어 초기 목록에서 제외했다.
- 루트는 생성된 목록7개와 wrapper/프로필을 확인했고 broker·unittest 요약 샘플 정규식 매칭을
  확인했다. **전체7개 통합 실행과 실제 local_test_fn→wrapper 연결은 아직 실행하지 않았다.**
- `/root/716_independent_review`에 위5파일과 build_local 읽기 전용 리뷰를 요청했으나,
  인계 요청으로 중단을 통보했다. 반환된 부분 리뷰에서 주요 결함은 발견하지 않았고,
  프로필/discovery 호환·프로세스 분리·실패 차단·경로 검증을 확인했다.
  **검사 재실행, 7개 원본의 출력/부작용 전수 대조, 실제 어댑터 결과 검토는 미완료다.**

이어갈 순서:

1. `git status --short`와 위5파일 diff/신규 파일을 읽고, 회귀15개 보고와 구현을 대조한다.
   기존 dirty `docs/orchestrator-handoff.md`도 보존한다. 변경을 stash/reset/clean하지 않는다.
2. 프로필의 새 start_dir/pattern을 이용한 **실제 local_test_fn 통합 호출** 또는 아래 discovery를
   실행해 필수7개 모두 자식에서 실행되고 건수 증거가 통과하는지 확인한다:
   `.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py`.
   source_scope는 임시 Git·sg gitea를 쓰므로 알려진 샌드박스 제약에는 좁은 실행 승인을 사용한다.
   실패 시 공용 실패중단 규칙을 따른다. fixture의 예상 실패는 테스트 성공과 구분한다.
3. 실제 프로필→공용 어댑터 연결 및 wrapper/manifest의 실패 차단을 독립 리뷰한다.
   범위 밖135검사를 자동으로 목록에 넣지 않는다. `/tmp` 전체 탐색도 금지한다.
4. 결과를 `reports/87-axcluster-integration-checks.md`(아직 생성 안 함), reports/README,
   이 인수인계 및 Redmine #716에 기록한다. **이번 보완 내용은 아직 Redmine에 반영하지 않았다.**
   스킬의 AXCluster 검사 경로 예시도 새 프로필과 일치하는지 확인한다.
5. 검증이 끝난 구체적 결과로 사용자에게 이번 변경의 커밋·푸시 승인을 받는다.
   승인 후 깨끗한 커밋에서 아래 기존 워커 동기화·재배달 과제를 이어간다.

현재 작업은 로컬 구현뿐이다. 새 운영 큐/Redmine 일감·브랜치·원격 파견·서비스 재기동·배달·
커밋·푸시는 하지 않았다. 아래15/15 드라이런 및 fixture6/6을 이7개 통합 실행 성공으로 읽지 않는다.

### 완료와 근거

- 사용자 “모두 커밋 푸시하고 동기화해” 승인으로 이전 미커밋20파일 전체를 커밋·Gitea push했다.
  Windows Codex 지침/워커 예외/브로커3노드 설정, NS 분석, #716 지침·검사·스킬이 포함됐다.
  GitHub는 Gitea 푸시 미러이며 직접 push하지 않았다. 미러 도착 자체는 이번에 따로 재조회하지 않았다.
- `distribute` 정본을 RAG→소스 대조→사용자 단독/분산 선택→서브 에이전트→실물 검증 흐름으로
  재작성했다. 등록 `kind`로 분기하며 정본7단계·병렬 기본·요청자 통합·별도 전진/finalize 승인을 유지한다.
  현재 노출되지 않은 improve/advance/finalize MCP 도구를 가정하지 않고 실제 모듈 계약으로 안내한다.
- `~/.codex/skills/distribute`와 공식 사용자 경로 `~/.agents/skills/distribute`는 모두
  `~/ax-cluster/master/skills/distribute` 링크다. 둘 다 정본/파일 존재를 재확인했다.
  **이번 인수인계 요청 직전 현재 세션의 제공 스킬 목록에 distribute가 실제 추가됐다.**
  따라서 앞선 “현재 세션 미노출” 기록은 갱신한다. 등록을 위해 반드시 세션을 닫아야 하는 것은 아니다.
  새 세션은 갱신된 진입 지침·인수인계를 다시 받는 데 유용하다.
- 타입별 더티 검사는 code SourceScope와 rename 양쪽/quoted 경로를 보호하고 index_only는 파견 제외.
  workshop77/77 + SourceScope32/32 + broker routing14/14 = 관련 검사123개 통과.
  스킬 형식 검사·독립 코드/forward 검토도 통과. code 서브모듈 내부 더티 검사는 일반화 한계가 있으나
  AXCluster는 submodules=[]다.
- `.43 ~/ax-cluster`는 ff-only 동기화 후 해시 일치. 이것은 `.43 ~/trunk/AXCluster` 워커 트리와 다르다.
- `ax-projects`는 19:24:55, `ax-broker`는 19:23:42 KST로 재기동됐다. 19:33 재조회 모두
  active/running·Result=success. 큐도 active/running이며 앞선 권한 승인 최신성 검사3서비스 모두
  stale=False·why 빈값이다. `ax-dispatch.path`·실제 따라잡기 타이머 `ax-dispatch.timer`는 active/waiting.

### 남은 일과 시작 조건

1. **작업장 동기화 재개 범위를 확인한다.** 기존 전체 동기화 지시가 있었지만, 목록 조회 오류 후
   공용 실패중단 규칙에 따른 재개 질문에 별도 답을 받지 않은 채 사용자 요청으로 인수인계를 작성했다.
   실패는 필수 AX_PROJECTS_ROOT 누락 조회였으며 루트 명시 재조회가 성공했다. 코드/서비스 장애 아님.
   없는 경로를 추정해 읽거나 동일 방식을 재질문하는 반복을 만들지 않는다.
2. **배달 출처를 깨끗한 커밋으로 준비한다.** 이 문서가 미커밋인 채로 배달하면 dirty=true다.
   이 문서 커밋·푸시는 별도 승인 후 처리하거나, 승인된 동기화에서 검증된 깨끗한 체크아웃을 사용한다.
   임의 stash/reset/clean으로 현재 변경을 숨기지 않는다.
3. **AXCluster 워커 소스 Git 동기화**: Windows `.2 E:\trunk\AXCluster`, `.33 C:\trunk\AXCluster`는
   마지막 preflight에서0ffd74b·더티없음. `.43 ~/trunk/AXCluster` 현재 HEAD는 이번에 재조회하지 않았다.
   등록 config의 경로·역할, 브랜치·더티 상태를 먼저 읽고 ff-only로 맞춘 뒤 실제 해시를 확인한다.
   사람의 게임 트리나 작업 브랜치를 강제로 바꾸지 않는다.
4. **등록 전체5프로젝트 작업장 배달·최종 검사**: `ModularStage`, `NS`, `KimodoMotion_WebUI`,
   `MotionForge`, `AXCluster`. 프로젝트를 임의로 골라 일부만 갱신하지 않는다.
   배달 계획을 읽고, 준비된 깨끗한 트리에서 아래 정식 명령을 실행한다:
   `AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -m master.client update`.
   종료 결과·전 프로젝트 검사·출처 해시·프로젝트 로컬 skills/config·서비스 최신성을 대조한다.
   **현재까지 이 전체 update는 실행하지 않았다.**
5. **분산 전체 실증은 별도**: AXCluster의 Python 통합 실행기/기존 스크립트 검사 호환성을 확인하고
   실제 큐→골조→조각 브랜치→워커 구현/커밋→회수→요청자 통합을 실증한다. 0개 테스트는 통과 아님.
   이번 사용자는 전체 커밋·푸시·동기화를 지시했으며 신규 분산 작업을 고르거나 전진/finalize를
   승인한 것은 아니다. 이전 직접 apply_patch 프로브를 이 전체 흐름의 완주로 대체하지 않는다.

### 후속 테스트 — 현재 세션에서 실제 스킬 사용

사용자 “그럼 테스트해볼까?”로 distribute를 읽고 실제 MCP를 호출했다.
RAG 검색 성공·logged=true, AXCluster kind=code·blockers=[] 확인.
운영 check_workshops_clean_tool은 kind=code·master/client .py 경계로 세 워커 모두
checked/ok=true·blocking=[]·dispatchable3대를 반환했다. 스킬 quick_validate도 통과.
client check AXCluster는 세 워커 모두 배달 출처384a07a가 HEAD4fb7915보다3커밋 뒤여서
rc1이다. 스킬1종·payload10개는 일치하지만 출처 버전 검사는 실패다.
현재 마스터의 인수인계 문서는 여전히 미커밋. 실제 분산은 파견하지 않았다.
스킬 흐름/준비 검사와 동기화 후 실제 분산 중 테스트 범위를 사용자에게 물었으며 아직 미응답.

### 로컬 격리 드라이런 — 사용자 후속 요청

사용자 “드라이런 해볼까?” 승인으로 운영 큐/Git/워커를 변경하지 않는 하니스를 실행했다.
스크립트 `/tmp/ax-master-workflow-dryrun.py`, 산출물 `/tmp/ax-master-dryrun-y55d21bm/`의
`result.json`·`specs.json`·`queue_requests.json`·골조3개·격리 통합 fixture에 근거가 있다.
하니스15/15와 실제 local_test_fn으로 실행한 fixture unittest6/6 통과.
register_work에 모의 POST/PATCH 큐를 주입하고 실제 _post와 socket 연결은 금지했다.
실제 AXCluster 프로필의 Python 확장자 검사를 통과했으며, 3골조의 run_python·층1 동결 검사를
실행했다. 시그니처 변경·스텁 잔존·비Python 골조·구문 오류·테스트0개는 예상대로 거절했다.
등재 결과의 gate_checked=False도 확인했다: 등록 함수가 별도 골조 게이트 실행을 통과로
꾸며 기록하지 않는다. 골조 검사는 하니스에서 별도로3/3 실행한 것이다.
세 호스트별 서로 다른 브랜치 이름과 대상 파일을 산출했지만 **배정·병렬 실행은 모의 계획**이다.
Git HEAD·refs·status는 하니스 전후 동일. 실제 브랜치/커밋/push, 원격 워커·LLM층2·Git통합·
전진/finalize·Redmine 큐 등재는 실행하지 않았다. 후속 문서 기록만 이 dirty 파일에 추가했다.

읽기 전용 독립 관측에서 실제 호출 순서를 확인했다: work 등재로 ID 발급→base 이름 기록·
태스크 등재→요청자의 골조 브랜치 준비/검사/승인 커밋·push→원격 base 존재를 확인한 자동 파견.
**실제 등재와 골조 push는 자동 파견을 발동할 수 있어 드라이런으로 실행하면 안 된다.**
또 AXCluster의 unittest discovery는 순수 함수·__main__ 스크립트 검사를 누락할 수 있다.
test_broker_routing/test_workshop_check/test_source_scope 등은 실제 실행계약을 별도로 검토해야 한다.
이 fixture6개 통과를 AXCluster 전체 통합 검사 또는 실제 분산 완주로 확대하지 않는다.
하니스 산출물의 후속 독립 검토는 에이전트가 /tmp 전체 목록을 조회하다 접근 제한 디렉토리의
Permission denied를 만나 중단했다. 앞선 호출순서/테스트 계약 독립 관측은 완료됐지만,
산출물 독립 검토는 미완료다. 루트는 지정 result/queue JSON만 읽어15/15·TESTS OK(6)·
모의 큐 호출5개·실제 파견/Git 브랜치 생성 없음 기록을 직접 대조했다.

### 조회와 권한의 함정

- AX CLI는 작업 위치 `~/ax-cluster`, `.venv/bin/python`, AX_PROJECTS_ROOT 명시가 필요하다.
  조회에서 레지스트리를 직접 읽으면 `Registry.load(Path('/home/sim/ax-cluster'))`도 가능하다.
- Windows 옛 클론 조회 스크립트는 `.2` 출력 UTF8 decode오류를 냈다. 기존
  `/tmp/ax-axcluster-worker-deploy.py preflight`에서는 두대 rc0·클론/HEAD/깨끗함을 확인했다.
  출력 처리 오류를 워커 장애로 기록하지 않는다.
- 기본 샌드박스의 systemctl·sg gitea·Docker 조회 실패는 진단 결과로 남기고 좁은 승인 경로로
  재조회한다. 권한 승인은 OS sudo 비밀번호를 대신하지 않는다. 비밀값 출력 금지.
- 홈 AGENTS/CLAUDE 링크를 덮지 않는다. git 현재 트리와 Redmine journal을 함께 대조한다.

## 1. 오늘의 사용자 결정 (2026-10-03)

- 원격: **Gitea 정본**(`origin`) + **GitHub 푸시 미러**(Gitea 가 커밋 시 동기화). 🔴 **GitHub 직접 push 금지** —
  마스터 `github` 원격은 push 비활성. `.43` 도 `origin` = Gitea
- ax-cluster 를 프로젝트로 등록 — 트윈 이름 **`AXCluster`**(ax-cluster 는 저장소 루트와 겹쳐 `test_sandbox` 오탐)
- AXCluster profile: kind `code`(`.py`) · purpose `rnd` · AX 작업 요청자 = **마스터 세션**
- 합성 프롬프트: 비UE 의 긴 `.py` 는 **ast 요약본**(함수 본문 생략, 독스트링·주석 유지)
- 파이썬 그래프: 겹치는 클래스 이름만 모듈명(`master.verdict.Verdict`) · 테스트 파일은 클래스 그래프 제외 ·
  `related_classes` 의 `이름: ?` 는 그래프에 정확한 이름이 있을 때만 채움(**전 프로젝트**)
- 🔴 **컨텍스트 문서는 검색 보조다 — 작업 판단 근거는 실제 코드**
- 사용량 표시는 **토큰만**. `.33` 등 세션 기록은 로컬에 두고 마스터가 가져온다
- `.2` 상주 모델 = `gemma4:e4b`(종전 `qwen2.5-coder:14b`) — 합성을 두 노드에 나누려고
- 🔴 **AX 클러스터 기능 작업(AXCluster)에서는 `.33` 도 워커로 쓴다** — 등록·배달·진단 파일 수정 실증까지 확인(§3)

## 2. AXCluster 재합성 — 🔴 미완 (11:58 실측으로 정정)

- 색인기는 전체 따라잡기를 **하지 않았다** — push 이벤트 범위(`306576e→c657a7a`)의 **바뀐 소스 106건만**
  합성하고 끝났다. 문서 **76 / 347그룹** · 워터마크(`last_indexed_commit`) **비어 있음**
- 품질: `related_classes` 가 전부 `?` 인 문서 **69% → 25%**(76개 중 19) — 그래프·요약본 효과
- 병렬은 실물 확인됨: 11:44~ 브로커 `[route]` 가 `bc250` 20 · `rtx3060` 14 로 나눴다
- **남은 일**: 누락분 합성 → index. 색인기와 겹치지 않게 **push 를 멈춘 상태에서**:
  `AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.projects.onboard AXCluster --confirm --only synth`
  (onboard 합성은 누락분만 · 동시 N 은 상주 노드 수) → `--only index`
- [주의] 색인기 타이머(10분)·push 이벤트도 합성을 띄운다 — 잠금이 없어 겹칠 수 있다.
  멈추려면 마운트를 옮겨야 한다(`systemctl stop` 은 NOPASSWD 밖)

## 3. 다음 작업

**최신 우선순위는 §0의 남은 일이다.** 워커 동기화·등록 전체 배달·검사부터 인계한다.
기존 별도 항목인 §2 재합성 미완, #713 웹 UI·토큰 사용량, AXCluster 분산 첫 전체 실증은
사용자가 고르는 다음 작업으로 남아 있다. 이전 §3의 브로커·문서 미커밋/스킬 미완 기록은
4fb7915와 §0 상태로 갱신한다. 과거 실측은 아래 이력과 reports/82·85·86에 보존했다.

## 4. 오늘 커밋 (모두 Gitea push · GitHub 미러 · `.43` pull 완료)

`183f32a` claim 범위(work 혼입 방지, 큐 재시작) · `ef239fb` 원격 문서 · `c595c01` 온보딩 ·
`4c0823f` 합성 요약본+토큰 로그 · `a0cbf42` 트윈 이름 AXCluster · `c237a93` 파이썬 그래프(#712) ·
`6a18918` 세션 수집기(#713 ②) · `306576e` 브로커 호출 사용량(#713 ①) · `c657a7a` 병렬 합성·분배(#715)

## 5. 남은 결함·주의

- `#714` 스풀 고아 배치를 아무도 재처리하지 않는다(`claimed/` 에 3건 남음 — 실손 없음)
- Kimodo 작업장 3대가 마스터보다 뒤다(재배달 필요, 범위 밖이라 안 함)
- `onboard` 의 conventions 문구 「색인 전용」은 code 타입엔 부정확(동작 결함 아님)
- 요약본 뒤에도 4,000자를 넘는 파이썬 파일 125개는 앞에서 잘린다
- 세션 수집기 `master/work/session_usage.py` 는 유닛 테스트가 없다

## 6. 관련 근거

Redmine `#711`~`#715` 노트 · `docs/14-onboarding-runbook.md` · 메모리 `context-docs-are-search-aid` · `codex-windows-ssh-sandbox` · 리포트82 · `docs/windows-codex-remote.md`


## Python 커밋 자동 리뷰 — 구현·검증 통과 (2026-10-03 17:00)

사용자 최초 지시와 kind 기준 정정, “응 진행해” 재개 승인으로 구현·검증했다.
등재·소비·프롬프트·예시는 등록된 프로젝트 kind로 통일한다. unreal=UE, code=Python,
index_only=자동 리뷰 제외. source 경계·work_exts, 큐 중복 방지·재시도·작성자 제외는 유지.
Python 함수·클래스 선언은 현재 트리가 아닌 대상 commit Git 객체에서 AST로 읽는다.
신규6+기존268=274/274 통과, diff --check 통과. 초기 검사 오탐과 승인 후 재개는 리포트83에 보존.
실제 Python commit6a18918을 격리 큐에서 브로커 e4b→Antigravity로 처리하여 최종 저장·done 확인.
아티팩트 /tmp/ax-python-review-live-1392e70e33da4f61a3a92afefb042484/.
운영 큐에 소급 등재하지 않았음. 서비스는 oneshot이므로 다음 기동 때 로컬 수정 소스를 읽는다.
**commit·Gitea push 완료 `7ec14f5`**, 새 운영 커밋의 push감지→자동 리뷰 종결은 아직 미검증.
커밋 검토 범위: 리뷰 코드·테스트5개 + docs/17-review-queue.md + reports/83-python-commit-review.md.
앞선 브로커·원격 문서 dirty 변경과 구분한다. README·reports 색인 갱신은 문서 dirty에 함께 남음.

사용자 “커밋해줘” 승인으로 Python 리뷰 코드·테스트5개 + 설계·실증 문서2개만 커밋했다.
커밋: `7ec14f5` (`review: enable Python commit reviews by project kind`). 푸시는 실행하지 않았다.

사용자 “푸시해줘!” 승인으로 `7ec14f5`를 Gitea origin/main에 푸시했다.
원격 훅에서 Sim/ax-cluster 색인 이벤트1건 큐잉을 확인했다. 리뷰 큐 등재·소비 완료와는 별개다.


## R1 실제 자동 리뷰·검토 완료 (2026-10-03)

운영 commit7ec14f5가 리뷰 큐에 자동 등재되고 17:26:34 첫 시도 done, R1 최종 리뷰 저장 확인.
사용자 “R1 검토해줘”로 지적1건을 운영 Python3.10.12에서 검증: ast.parse 널 바이트는
ValueError이며 SyntaxError만 잡는 declarations에서 전파됨. 격리 큐에서 running잔존·재claim불가 확인.
권고: SyntaxError·ValueError 처리, msg·lineno 모두 getattr, diff 리뷰 계속·큐종결 회귀.
코드·리뷰 원문·R1 상태는 수정하지 않음. 근거 reports/84-r1-python-review-validation.md.

사용자 “수정해줘!” 승인 후 R1 코드 수정 완료: review_runner에서 SyntaxError·ValueError를
잡고 msg·lineno를 안전하게 읽는다. 구문 오류·널 바이트 실제 임시 Git 커밋 모두 리뷰 done,
pending/running=0 회귀 검증. 관련 검사 141건 및 diff --check 통과. 대상 코드·테스트2개만
수정했으며 커밋·푸시 전이다. 리포트84에 수정과 검증 근거 추가. 운영 R1 상태는 변경하지 않음.

사용자가 RAG·서브 에이전트 누락을 지적했다. 최초 수정은 둘 다 없이 진행했음을 인정했다.
**수정 전 관련 RAG 컨텍스트를 조회하고, 위임할 때 그 근거를 함께 전달한다.**
보완으로 AXCluster active 확인 후 search_context_tool 2회 조회, 관련 본문·설계·현재 코드 대조,
로컬 서브 에이전트 r1_context_review에 독립 검토 위임. AX 원격 워커 파견은 아니다.
컨텍스트의 Python 설명 누락·__repr__ 미구현 오기와 검색 excerpt 누락을 관측했으나
검색·합성 설정은 변경하지 않았다. 근거 리포트84.
독립 검토도 R1 추가 코드 수정 불필요로 판정. 널 바이트는 Git 바이너리 diff가 될 수 있으므로
검증 범위는 큐 고착 방지·진단 전달이며 모든 변경 라인 전달 보장은 아니다.

## 사용자 확정 — .57 인프라 정비에도 RAG·분산 도구 활용 (2026-10-03)

사용자 원문: “.33 메인 작업 컴퓨터가 서브에이전트를 활용하고 분산 작업을 시키고,
RAG를 요청하는 스킬이나 MCP를 인프라 서버를 관리할 때도 활용하길 바래서 워커를 등록한거야.”
사용자 후속 정정: “아니 .33에서 작업 하라는게 아니라 .57 이 인프라 서버에서 작업할 때도
.33처럼 RAG와 분산 작업이 가능하도록 구정되어 있냐고”. **작업 장소를 .33으로 옮기라는
뜻이 아니다. .57의 지휘 세션이 인프라 정비에도 RAG·서브 에이전트·AX 워커 분산을 활용한다.**
마스터 직접 수정 뒤 로컬 서브 에이전트 검토만 추가하여 워커 분산까지 했다고 판단하지 않는다.
이번 R1은 마스터 직접 수정 후 RAG·로컬 독립 검토로 보완했고 AX 워커 분산은 수행하지 않았다.
다음 실행 전 관련 스킬·MCP 계약과 기존 승인 범위를 확인한다. 역할 설정·배달은 변경하지 않았다.

준비 상태 실측: .57 현재 세션에서 search_context_tool 성공, register_work_tool 노출,
서브 에이전트 위임 가능. ax-projects·ax-task-queue active/running, ax-dispatch.path active/waiting,
ax-dispatch-catchup.timer inactive/dead. AXCluster 프로필 kind=code, work_exts=.py, blockers 없음.
세 워커 SSH·Codex0.159.3 확인. client check AXCluster는 실패: 세 배달 출처384a07a가
현재 HEAD보다1커밋 뒤, ax-projects는 profile.py 변경 전 기동되어 재기동 필요 판정.
기존 마스터 distribute 스킬도 통합자·기본직렬·UE골조 등 현재 공용 규칙과 어긋난 옛 내용이며
Codex의 현재 제공 스킬 목록에는 distribute가 없다. RAG는 사용 가능하나 분산 준비 완료로
단정하지 않는다. 실패 규칙에 따라 재배달·재기동·스킬 수정은 실행하지 않고 상태만 보고한다.

사용자 “일단 일감으로 등록해”로 Redmine **#716** `[AX] .57 인프라 정비의 RAG·서브 에이전트·분산 작업 준비 정비`
등록 완료. AX Cluster 프로젝트, 마일스톤6, 신규 상태. 버전 불일치·서비스 재기동 필요·
마스터 분산 스킬 갱신·Python 소스 더티 검사 확인과 실제 .57→워커 흐름 검증을 범위로 기록했다.
등록만 했으며 작업 실행·재배달·재기동·커밋·푸시는 하지 않았다. 항목·진행 정본:
http://192.168.0.57:8080/issues/716.

사용자 최신 절차: CLAUDE.md·AGENTS.md·스킬에 **RAG 검색→단독/분산을 사용자에게 물음→
선택에 따라 서브 에이전트 구성→단독 처리 또는 AX 워커 분산→실물 검증**을 반영한다.
이어 “NS에서 작업 요청을 받았을 때” 실제 방식 분석·참조를 지시하여 .33 NS 지침·스킬·
에이전트·MCP·훅을 읽기 전용으로 대조했다. 근거 reports/85-ns-requester-workflow-reference.md.
NS의 기존 컨텍스트/온톨로지·계획/선택·전문 위임·큐 등재·asyncRewake·되먹임 흐름을
참조하되 combined_search/watch.exe/attempt/클라이언트 등재금지 등 낡은 문구는 복사하지 않는다.
자동 로드 지침·스킬 반영, 재배달·서비스 재기동은 아직 실행하지 않았다. 이전 처리 방식 질문은
지침 반영에 관한 것이며 이번 분석·참조 요청을 분산 실행 승인으로 읽지 않는다.
사용자 “아까 신설한 레드마인에 연결해둬!”로 #716 journal1480에 리포트85 경로·NS 분석 결과·
사용자 확정 절차·남은 반영/운영 검증을 연결하고 재조회 확인했다. 미커밋 보고서임을 명시했고
일감 상태는 신규로 유지했다.

사용자 “아까 리뷰 대응한거 커밋하면서 리뷰 상태값 변경하고” 승인으로 R1 수정 코드·테스트·
리포트84의3파일만 커밋: **95906c87914c081ff6fb64ad05443ccfc75b8bfb**
(`fix(R1-1): handle Python declaration parse failures safely`). 핵심7건 재확인 통과.
fix_index.set_status로 AXCluster **R1-1→applied**, 실제 branch=main·위 커밋을 기록하고
get_doc 재조회로 상태·해시 일치 확인했다. R1 전체 항목1/1 applied. 푸시는 하지 않았다.
브로커·원격 설정·NS 분석 등 앞선 dirty 변경은 이 커밋에 포함하지 않았다.

사용자 “푸시해줘!” 승인으로 95906c8을 Gitea origin/main에 푸시 완료.
git ls-remote의 refs/heads/main=95906c87914c081ff6fb64ad05443ccfc75b8bfb 일치 확인,
원격 훅의 색인 이벤트1건 큐잉 확인. R1-1 applied 노트에 원격 반영도 기록한다.
새 커밋의 자동 리뷰 종결은 아직 확인하지 않았다.

#716 선행 정비: 사용자 동의로 로컬 서브 에이전트 2개가 지침5파일과 타입별 더티 검사2파일을
수정했다. workshop 검사77/77, SourceScope 권한 해제 재검사32/32 통과. 독립 코드 검토 진행.
실제 따라잡기 타이머는 **ax-dispatch.timer**이며 active/waiting이다. 앞선
ax-dispatch-catchup.timer 조회로 비활성이라 기록한 내용은 이 실측으로 정정한다.
경로 추정 조회 오류가 반복돼 공용 실패 규칙에 따라 추가 편집 중단. 남은 distribute 스킬은
루트 직접 인수 예정이며 아직 원본이다. 보고서86에 변경·검사·실패·운영 미검증을 기록했다.
스킬 완성·Codex 연결·깨끗한 커밋 기준 배달/서비스 반영·분산 전체 실증이 남았다.
이번 #716 변경의 커밋·푸시는 승인받지 않았으며 배달·재기동·원격 파견도 하지 않았다.

사용자 “모두 커밋 푸시하고 동기화해”로 전체 현재 변경 승인. distribute 스킬은 루트가
현재 흐름으로 재작성 완료했고 형식/독립 forward 검토 통과. Codex legacy·공식 사용자 경로
링크를 좁은 권한 승인 스크립트로 등록했다. 관련 코드 검사123개 통과. 이전 미완료/승인없음
기록은 위 승인·완성 상태로 갱신한다. 이제 전체 변경을 커밋·Gitea push하고 클론·등록 전체
작업장 배달 및 ax-projects/ax-broker 반영을 수행할 예정. 실측 결과 정본은 #716 journal.
스킬 자동 감지가 공식 동작이지만 이 세션의 새 스킬 노출은 미확인. 다음 세션에서 distribute
노출과 정본 경로를 확인한다. 실제 분산 전체 흐름과 Python 통합 실행기 호환성은 미실증이다.
