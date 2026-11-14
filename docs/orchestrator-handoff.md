# 현재 AX 작업 인수인계

> 2026-11-14 체크포인트(낮) — Claude 가 #942 를 T6 까지 끝내고 T7(검사·마감) 도중 토큰 소진으로 멈췄다. **사용자 결정: Codex 가 이어서 마감한다.**
> 🔴 **#942 일감 잠금이 활성이다**(`issue/942`, worktree `/home/sim/ax-cluster/.ax-issues/942`). 이 인수인계서는 그 **worktree 의 `issue/942` 에 커밋**돼 있다 — 운영 `main`(`1aed470`)의 같은 파일은 아직 #710 체크포인트다. main 에 따로 커밋하면 브랜치가 갈라져 rebase 가 필요해지므로 그렇게 하지 않았다.
> 항목·진행의 정본은 Redmine. 이전 상세는 Git 이력·리포트 170~180·각 일감 노트.

## 진행 중 — #942 세 CLI 대화 중계 상위 레이어 (`master/relay/`) · T7 에서 중단

**사용자 승인**: 「응 942 진행해」(공용 규칙 §1.9 — 커밋·finish·판정된 재기동·인수인계 push·배달까지 포함). 그 전에 운영 저장소 미추적 파일 때문에 시작이 거절돼 「커밋해서 넣고 진행해」로 `1aed470`(#730 리서치 보고서) 을 main 에 올렸다. 작성 계열 `['claude']` — **Codex 가 이어받으면 `ax-projects:issue_start_tool(942)` 를 한 번 불러 계열을 더한다**(같은 worktree 면 `already`).

**사용자와 정한 것**(리포트 180 첫 절 · Redmine #942 본문·노트): 터미널 창 3개·agy 자동 라우팅·agy Handoff Brief 는 뺐다. 일감 선택 → 에이전트 객관식 선택(작업 중 교체 가능) → 대화 중계. 세션 로그 하나가 미러링 대상이자 공유 메모리. 마무리 = 일감 「완료」 + 보고서. 1차는 `.57` AX 일감, 코드 위치는 `master/` 아래(동작이 정립되면 이동), 도구 권한 전부 자동 허용. 오동작 지점마다 로그를 파일로 남긴다. 웹 UI·토큰량·로그인 점검·`.33`·`#941` 은 추후.

**끝난 것** (플랜 T1~T6 「완료」, `issue/942` 커밋 6건 + 이 인수인계 커밋):

| 커밋 | 내용 |
|---|---|
| `9dd1e85` | 리포트 180 — 결정·T1 세 CLI 실측 |
| `1dcc6a1` | `relay/store.py` 세션 로그 저장소 + `master/test_relay.py` + `checks.json` 등록 |
| `083e39c` | `relay/agents.py` 세 CLI 호출부 |
| `fa39222` | `relay/boundary.py` 작업 경계 판정 |
| `d2363ac` | `relay/console.py`·`__main__.py` 콘솔 |
| `ba9dbc2` | `master/README.md` 행 추가 · 리포트 180 구현·T6 실증·한계 |

- 검사: `master/test_relay.py` 113/113 rc0 · 정적(pyflakes·imports·mypy) 차단 0·노트 26 · `test_integration_coverage` OK.
- T6 실증(실제 세 CLI, 일감 #942, 저장 위치는 저장소 밖 임시 디렉터리): claude → codex → agy → claude 교체, 네 차례 rc0, 교체된 에이전트가 전달문의 사실 문장만 보고 세션 기록을 읽어 이어받음. 해석 실패 0.
- `log_history` 기록 완료(`AXCluster/history/2026-11-14_1204_#942_…`).

**남은 것 — T7 (「작업중」)**:

1. **공식 통합 검사는 통과했다** — `d2363ac` 시점 코드(그 뒤 커밋은 문서뿐), **196건 · 195.908초 · OK · rc0**, `test_relay` 113건 포함. 로그 `/tmp/claude-1000/-home-sim/0910090d-a3ae-48b1-ab07-9db26f1114a0/scratchpad/integration.log`. 리포트 180 에는 아직 적지 않았다.
2. **`master/test_*.py` 전수**(커밋 전 전수 규칙) — 아직 안 돌렸다.
3. 리포트 180 에 통합·전수 결과를 적고 커밋 → T7 「완료」 → `ax-projects:issue_finish_tool(942)` 미리보기 확인 뒤 `confirm=True` → `.venv/bin/python -m master.issue_wrapup 942 --project AXCluster`(인수인계서 갱신 커밋·push 뒤 재실행) → Redmine 결과 노트.
4. 새 모듈은 상주 서비스가 import 하지 않는다 — 재기동 판정은 wrapup 이 한다(추정하지 않는다).

**미확인·한계**(리포트 180 「한계」): 긴 작업·한도 소진·중단 뒤 이어가기 미실증 · 레이어 안에서 일감 시작·마감 도구를 부르는 경로 미실증(비대화 세션의 `issue_start_tool` 작성 계열 기록 포함) · 한 줄 입력만 · `fcntl`·프로세스 그룹은 리눅스 기준 · 실행 래퍼 없음(저장소 밖에서는 `PYTHONPATH` 필요).

**사용자가 직접 써 볼 수 있다**: 마감 전 `cd /home/sim/ax-cluster/.ax-issues/942 && AX_PROJECTS_ROOT=/home/sim/ax-cluster /home/sim/ax-cluster/.venv/bin/python -m master.relay`, 마감 뒤 `cd ~/ax-cluster && .venv/bin/python -m master.relay`. 사용자가 실행했다면 `~/ax-state/relay/sessions/942/` 에 실제 세션이 남아 있을 수 있다(지우지 않는다 — 일감 완료 뒤 `/close` 가 보관한다).

## 이전에 끝낸 것 — #710 삭제된 Kimodo 체크아웃 안내 정리

- 사용자 「710 진행하자」 후 두 곳 삭제·다른 경로 유지·로컬 서브에이전트 수행 구체안에 「응!」 승인. `win-main-33.md` 체크아웃 목록과 프로젝트 표의 KimodoMotion_WebUI만 제거. 현재 등록과 일치하는 ModularStage·NS Documents 경로는 유지하고 sim-desktop·온보딩 예시는 수정하지 않았다.
- 문서 `2c557a8` · 리포트179 `3a28f81`. diff 검사rc0, 공식 통합195건210.233초OK(rc0). 실행 코드·검사 코드 변경 없음.
- finish `repo="/home/sim/ax-cluster/.ax-issues/710"`, `done=["push","ff","worktree_remove","delete_branch","register","link","release","close","redmine"]`, `why=""`, `registered=true`, `round=1`, `closed=true`, `lock_released=true` (해시2개 등록).
- 정본 `master.client home-guides --host=192.168.0.33 --apply` rc0. `C:\Users\USER\CLAUDE.md.bak-20261114-004431` 백업 후 정본 SHA256 `92c97d62310d` 일치, AGENTS.md 없음(정상·생성 안 함). 게임 트리·브랜치·등록 경로 변경 없음.
- 마감 뒤 단계 rc0(main `ef8386a`, 재기동 없음, 배달 rc0), T2 완료. 자동 리뷰는 소스 변경 없음으로 생략·지적 0건(2026-11-14 Claude 가 Redmine 에서 확인).

## 이번에 끝낸 것 — #750 related 근거 검증·YAML 미상 문자열 인용

- 사용자 「750 진행하자」「응 단독으로 진행해줘!」, 추가 결정 「YAML에서 기존 ?표도 모두 정리하고 앞으로도 따옴표로 묶는게 맞아」. 코드 `01307dc` · 리포트 178 `a817484`. 모델 체인은 변경하지 않았다(현행 로컬 gemma4:e4b).
- related 이름을 프로젝트 심볼·실측 선언·실제 소스 참조와 정확 대조. 정상 외부·엔진 참조 및 qualified Python 이름 허용. 예시 클래스·태그 목록을 프롬프트에서 제거하고 명백한 placeholder 태그 거부. related 정규화를 사실 검사 앞으로 옮김.
- 미상 경로 정본 `"?"`. 과거 bare `?`는 생성 결과 형식 검사 전에 인용, 소비자는 기존 값 `?`로 읽음. graph의 정확 이름→실제 경로 보정 유지. 정본 `related --quote-unknown-only`로 기존 문서 인용만 교정(재합성·경로 변경 없음): AXCluster 92파일180줄, NS 56파일85줄, ModularStage 101파일231줄, ServerTest 0. 총249파일496줄. 적용 뒤 네 프로젝트 계획 재조회 모두 bare 잔여0(rc0).
- 검사: related33/33·합성251/251·검색96/96·사실게이트41/41 모두 rc0. 정적 10파일 차단0(6모듈 import), 공식 통합195건206.265초OK, diff 검사rc0. 통합 1차는 기존 테스트의 LogNS 근거 누락3건으로 실패했고, 사용자 승인 후 실제 NS_H/NS_CPP 심볼을 known으로 전달하여 통과(근거 없으면 거부되는 대조군 유지).
- finish 원문: `repo="/home/sim/ax-cluster/.ax-issues/750"`, `done=["push","ff","worktree_remove","delete_branch","register","link","release","close","redmine"]`, `why=""`, `registered=true`, `round=1`, `lock_released=true`, `closed=true`. 해시2개 등록. 마감 뒤 결과는 Redmine 노트.
- wrapup rc0: 인수인계6d02169 push 뒤 task-queue00:35:28·projects00:35:33 재기동·재판정 깨끗, broker최신 유지. 배달·검사rc0, T2완료·Redmine 노트 되읽기 확인.
- 한계: related 이름 실재 근거를 확인하며 경로 정확성·협력 강도까지 증명하지 않는다. 정상 개념 태그의 의미 적합성은 자동 판정하지 않는다. LLM 주입 합성 경로로 검증했고 운영 상용 LLM 품질 측정은 하지 않았다. 자동 리뷰 결과 미확인.

## 이전에 끝낸 것 — #344 워커 지시(abort)를 읽고 따르게 했다

- 경과: Claude가 직접 구현(사용자 선택, 작성 계열 `["claude"]`). T1~T4 커밋·검사·리포트 177 작성 후 `issue_finish` 9단계 완료(`why=""`, `.ax-issues/344` 및 브랜치 제거 완료, 마감 추적 회차 1: `ea57860aadd5..48733bb09607` 해시 6개 등록).
- `issue_wrapup 344` 1차 실행 중 `ax-task-queue` 옛 코드 판정 후 ⑤ 인수인계 확인 단계(`rc=2`, 끝 커밋 `48733bb` 뒤 `docs/orchestrator-handoff.md` 커밋 대기)에서 정지한 직후 토큰 소진으로 중단됨.
- Codex 후속 완료: 인수인계 `a229011` push 후 wrapup rc0, 상주3종 최신·추가 재기동 없음, 배달·검사rc0, Redmine 결과 노트·T6완료 되읽기 확인.
- 커밋 6건 (`5782dd2` · `c66e58b` · `c7a9835` · `a16e67c` · `02bdad4` · `48733bb` · 리포트 177):
  - `5782dd2`: 큐(`logic_claim`·`models`) — 허용 지시를 `abort` 하나로 제한(`pause`·`resume`·`drain`은 400, 도는 조각 없는 워커의 `abort`는 409 거절), 대상 태스크(`targets`/`abort_targets`) 반환·기록.
  - `c66e58b`: 파견 루프(`runner`) — `heartbeat` 응답 지시를 `follow_directives`로 이행(큐 취소 종결), `stop_requested`로 10초마다 지시·취소 조회.
  - `c7a9835` · `a16e67c`: 리눅스 직접 SSH(`_ssh_stoppable`) — 원격 셸 세션을 `/tmp/ax-run-<id>.sid`(`trap … EXIT` 정리)에 적고 중단·타임아웃 시 `pkill -s <sid>`로 세션 종료 및 `GONE`/`ALIVE`/`NOSID` 확인. 단위 검사에서 실제 SSH 호출을 막는 `runner._POPEN` 가드 추가.
  - `02bdad4`: `ax-request` 스킬 §6 · `master/README.md` 현행화.
- 검사: `test_queue_worker_contracts` 43/43 · `test_runner` 456/456 · `test_skill_conventions` 50/50 · 정적(`pystatic.run_static`) 차단0 · 공식 통합 195건 187.991초 OK · `git diff --check` rc0.
- 실경로 확인(임시 큐 앱 + `.43` 실제 SSH 대역 `sleep`, LLM 0): `pause` 400 · 유휴 워커 `abort` 409 · 실행 중 `abort` 및 태스크 취소 모두 약 11.2초 내 원격 종료·잔여 프로세스 0·sid 파일 0 확인.
- 한계: 실제 `codex`·`claude` 조각 중단과 운영 큐 서비스 실물 등재는 미실증(대역 `sleep`으로 검증). Windows 세션 1 `abort`는 단위 검사까지(`#796` `cancel.flag` 경로 재사용). `lane` 본문 생성·층2 검증 구간 및 `ax-infer`는 범위 밖. 해시별·종합 자동 리뷰는 미확인.

## 이번에 끝낸 것 — #940 리포트 뷰어 정렬 안내문 정정 (R340-3)

- #919 해시 리뷰 R340 지적 5건을 코드와 대조(모두 사실). 사용자 「R340-3은 안내문만 고치고 나머지는 기각해」 → R340-1·2·4·5 `dismissed` 기록, R340-3은 #940으로 처리.
- 커밋 `3b1cea7` · 리포트 176. 안내문 세 곳 「파일명순」→「파일명 역순」, 정렬 코드 불변, 순서 검사 1건 추가(16건 OK). 정적 차단0 · 공식 통합 195건 191.417초 OK. finish `done` 9단계·`why=""`·closed=true.
- wrapup 1차: `ax-projects` 23:07:48 재기동·재판정 깨끗. 실제 `/reports` 200·고친 문구 확인·「파일명순」 잔존 0.
- #919 배달 경과: 1회차는 `.33` 전원 꺼짐으로 `master.client update` rc1, 사용자가 켠 뒤 재실행 rc0.

## 이번에 끝낸 것 — #919 웹 작업 리포트 뷰어

- 경과: Codex가 로컬 서브에이전트 구현을 회수한 직후 5h 한도로 중단(미커밋). 사용자 「919 이어서 진행해, rebase도 승인」으로 Claude 인수. 작성 계열 `["codex","claude"]`.
- 인수 때 기록과 달랐던 점: 인수인계 커밋 `318519d`가 이미 push돼 있어 `issue/919`를 `main` 위로 rebase했다(커밋 없는 브랜치, 미커밋 변경 그대로).
- 커밋 `98b37b8` · 리포트 175. `http://192.168.0.57:8103/reports` — `reports/*.md`·`reports/research/*.md` 목록·검색·분류·상세, `#N` Redmine 링크, 실재 해시의 Gitea 커밋 링크.
- 검사: 관련 32건 OK · 정적 차단0 · 공식 통합 195건 202.579초 OK. finish `done=[push,ff,worktree_remove,delete_branch,register,link,release,close,redmine]`, `why=""`, closed=true.
- wrapup 1차: `ax-projects`만 옛 코드 판정 → 22:37:10 재기동·active·재판정 깨끗. 실제 HTTP: 목록 200(193개)·연구 24개·상세 200·경로 탈출 400·없는 파일 404·POST 405·다른 화면 메뉴에 링크 있음.
- 한계: 8103은 로그인이 없어 리포트 본문(사용자 발화 인용·절대 경로)이 LAN 안에서 읽힌다 — `api_history`와 다른 선택이지만 **사용자 결정 2026-11-13: 그대로 둔다**(「내 집에서 하는 개인 프로젝트」) — 다시 꺼내지 않는다. 목록은 캐시 없이 매번 전체를 읽는다(실측 약 0.5초). 해시 리뷰 R340은 처리 끝(위 #940), 종합 리뷰는 미확인.

## 신규 등록 아이디어 및 선행 분석 기록 (착수 아님)

- **#939**: `[AX] 아이디어 — addyosmani/agent-skills 분석: 작업 시작 전 인터뷰 로직 등 클러스터 이식 요소 발굴` (`아이디어 — 추후 검토 수집` 마일스톤 등록 및 `interview-me`·`doubt-driven`·`Floor Guard` 선행 분석 코멘트 기록 완료).
- **#911 · #731 코멘트**: `#911`(`cursor/plugins` `pstack` 선행 분석 코멘트), `#731`(Google NotebookLM 웹 연동 제약 및 로컬 대안 코멘트) 기록 완료.
- **CTO 아키텍처 진단 및 #911·#938·#939 리서치 리포트 4건 저장**:
  - `reports/research/2026-11-13-ax-cluster-cto-review.md` (CTO 비판적 진단 + 기업 AX 이식 가이드 + #911·#939·#938 통합 개발 플랜)
  - `reports/research/2026-11-13-911-pstack-playbook-analysis.md` (#911 `pstack` 정밀 분석 및 6대 스펙 아젠다)
  - `reports/research/2026-11-13-938-cognitive-debt-prevention.md` (#938 작업자 3단계 정의 및 인지적 부채·판단 포기 예방 설계)
  - `reports/research/2026-11-13-939-agent-skills-interview-analysis.md` (#939 `addyosmani/agent-skills` 사전 인터뷰 및 5대 가드레일 분석)

## 이전 #936 결과

- 사용자: Gitea 저장소 직접 삭제 보고, 남은 클론·트윈 전체 제거·백업 불필요 승인. .33 미커밋 DefaultEditor.ini·미추적 Content/MotionForge 포함 목록 재확인 후 삭제했다.
- .2/.33 C:\trunk\MotionForge, .43 /home/sim/trunk/MotionForge, .2 AxConductor_MotionForge, 마스터 MotionForge 전체 삭제·부재 확인 rc0. Registry/MCP 재조회에서 MotionForge 없음·active=AXCluster·problems=[]. 백업 생성 없음.
- #694·#697·#703·#704·#707·#755·#758·#761은 각각 폐기로 닫고 되읽기 확인. #759/#760은 AX 공통 문제로 열린 상태 보존. Redmine motionforge 프로젝트는 이슈·이력 보존을 위해 유지(삭제·보관전환·이동 안 함).
- 승인된 machines3문서에서 MotionForge 현재형 체크아웃 표기만 제거. 커밋 b1f0cc4, 공식 통합194건209.308초OK·diff 검사rc0. finish done=[push,ff,worktree_remove,delete_branch,register,link,release,close,redmine], why="", closed=true.
- wrapup: 상주3종 최신·재기동 없음. 인수인계 `bb71407` push 후 배달·`check AXCluster` 3대 OK(rc0) 및 Redmine #936 마감 노트 확인. 자동 리뷰 결과는 미확인.

## 이전 #733 결과

- Argon `gemini-4-argon-medium` 패치 제안, Codex 전체 검토·적용. 주간 플랜 `weekly_plan`(주차:작성자)·레시피 `recipe_synthesis`(프로젝트) 사용량 기록. 기존 scope 기록 불변.
- 최초 diff 헤더 행 수 오류로 적용 rc128·변경0 → 사용자 재요청 승인 → v2 형식8구간 일치·적용rc0. 제안2개·실패 근거는 리포트173.
- 관련 검사57/57·67/67·18/18, 정적 차단0, 공식 통합194건204.239초OK. 격리 입력의 실제 상용 CLI로 두 source 각1행·토큰·rc0 확인(운영 데이터 전체 배치 실증과 구분).
- finish `done=[push,ff,worktree_remove,delete_branch,register,link,release,close,redmine]`, `why=""`, closed=true. 해시별·종합 자동 리뷰는 미확인. Argon 작성 사실을 리포트에 명시했으며 agy 자동 리뷰만으로 교차 계열 검증을 주장하지 않는다.
- wrapup: task-queue만 23:52:39 재기동·active·재판정 깨끗. 인수인계7e09726 push 후 배달·검사rc0 및 Redmine 완료·100 확인. Argon 지연·신뢰성·중복 토큰을 포함한 조사·분석 비동기 큐 아이디어 #937을 등록했다(착수 아님).

## 지휘 상태

- 마스터 담당 기록 `claude`(2026-11-12 21:40:27) — 2026-11-14 조회에서 그대로였고 이번 세션은 기록을 바꾸지 않았다. Codex 가 실제로 인수하면 사용자 지시에 따라 기록한다. 워커 전역 `codex`(state, 2026-10-18) 변경 없음.

## 이전 세션에서 끝낸 것 (전부 마감·배달 rc0)

| 일감 | 내용 | 커밋 |
|---|---|---|
| #932 | 마감 추적 해시가 30분 넘게 미러에 없으면 일감에 노트 1회 | `c4a31e2` · 리포트 170 |
| #639 | 범위 플랜 `kind=scope` — CLI `scope_plan request` · MCP `request_scope_plan_tool` · `plans/_scope/` | `8331dac` · 리포트 171 |
| #815 | `/reviews` 카드가 4절(골조 지시 이행) 행 수를 센다 | `9c7d78b` · 리포트 172 |

- #639 한계: 상용 플랜 생성 호출은 실물 미확인(지금 데이터는 대부분 「플랜 기준 미달」). `done` 대상 재요청 불가 · 대기 상한 12. 리포트 171 §8.
- #932 한계: 타이머+배포 코드의 부재 알림은 따로 실증하지 않았다.
- `--limit 0` 은 LLM 호출 0이 아니다(`drain` 이 `max(1, limit)`). 일감 미등록.

## Redmine 정리 (사용자 지시: 「확인만 하지 말고 안 맞으면 폐기, 필요하면 드라이런」)

- 🔴 사용자 불만: 일감 노트가 「대조: 유지」「이관」만 반복됐다. **남긴 일감에 그런 노트를 더 달지 않는다.** 닫거나, 고치거나, 정할 것만 묻는다.
- 닫음(폐기): #363 · #771 · #729 · #742 · #743 · #296
- 닫음(완료): #633 · #384 · #406 · #726
- 결정 대기: #935(#815 잔여 — 조각 테스트 작성 여부 · `verdict.py:61` 문구). #936은 이번에 마감했다.
- #639 는 #633 에서, 아이디어 #854 는 #729 에서 부모 연결을 뗐다. #370 제목·본문을 현재 상태로 고쳤다(남은 것 #372).
- #929 추적 기록은 이미 복구돼 있었다(회차 2 R314·R317). 남은 것은 그 리뷰 지적 처리.
- #709: 11-12 사용자 GitHub 삭제 뒤 웹·API404로 종결됐음을 이번 이슈 조회에서 확인했다. 과거 인수인계의 대기 표기는 낡았다.

## 남은 열린 일감 (마일스톤 8, 수는 Redmine) — 다음 세션이 물을 것

- 바로 고칠 수 있는 결함 후보: #738(스킬 홈 배달 → 「홈 중복 스킬」 경고) · #372(종결 work 차단 게이트).
  #733·#344·#750은 마감했다. 나머지는 **제안만 했고 사용자 답을 받지 못했다**. 자동 시작하지 않는다.
- 결정 대기: #326(트윈 4개 원격 없음·미커밋 누적 — Gitea 보관 여부) · #791(후속 라운드 실패를 라운드 실패로 둘지) · #935 · #839 · #741 · #383. #710은 이번에 마감했다.
- 다른 조건 대기: #272·#650(ModularStage 마운트) · #649(NS 마운트) · #211·#855 · #826·#858(#856) · #370.

## 미확인 보존

- 리뷰 지적 미처리: #929 R314/R317 · #930 R315/R316 · #931 R325 · #934 R326 · #829 R328/R329 · 오늘 마감분(#932·#639·#815·#919·#940·#344)의 해시별·종합 리뷰는 큐 결과로 붙는다(읽지 않았다).
- `.33` 첫 실제 요청자 마감·연결 미확인. 실제 BC-250 poweroff 미실행. 자동 로드 문서의 「M7 open」 서술 미정리(M8 이 열린 마일스톤).
- `.2` check 의 「홈 중복 스킬 `~/.agents/skills/ax-work`」 주의는 통과 판정이라 건드리지 않았다(#738 축).

## 바로 다음 작업

1. #942 T7 을 위 「남은 것」 순서로 끝낸다(사용자 「942 진행해」 승인 범위 안). 실패는 고치지 않고 보고한다.
2. 마감 뒤 다음 일감은 사용자가 고른다. 「바로 고칠 수 있는 결함」(#738·#372) 제안은 아직 답을 받지 못했다.
3. ⑦ 전진·finalize·파괴적 git·자동 로드 문서 변경은 기존 사람 게이트를 따른다.
