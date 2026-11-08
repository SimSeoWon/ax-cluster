# 현재 AX 작업 인수인계

> 2026-11-08 17:00 Claude 체크포인트(#898 마감 후). 항목·진행의 정본은 Redmine이다.
> 이전 상세는 Git `d946ba7`(운영 체크포인트)·`54b5632`(#898 Codex→Claude 인계본)의 이 파일·리포트138~148·각 일감 노트에 있다.
> 진행 중 일감·일감 잠금은 없다. #898 은 ax-task-queue 재기동(16:49:16)·배달 3/3 OK 까지 반영됐다.

## 🔴 오늘 오후 바뀐 규칙 (사용자 결정 2026-11-08)

- **마감 뒤 기록 몫**(`ax-plan` 3-1 · `331b260`·`ed0b5d6`): 리포트=일감 커밋 시점까지(끝에 「최종 결과는 Redmine 마감 노트」) ·
  Redmine 마감 노트=결과 정본 · **이 문서=마감 직후 main 문서 커밋**(마감·배포 승인에 포함). 배포를 마감 뒤 **따로** 승인받아
  했으면 배포 결과로 이 문서를 **한 번 더** 맞춰 커밋·push 한다.
- **읽기 조회 경로 부재 예외**(`6284054` — `~/CLAUDE.md`·`AGENTS.md`·`docs/orchestrator-rules.md`): 「실패는 보고하는 자리」의
  유일한 예외. 읽기 전용 조회가 `No such file or directory` 면 확인된 경로로 재조회하고 보고에 남긴다.
- 🔴 **이 문서의 절 제목 「바로 다음 작업」은 바꾸지 않는다** — `test_handoff_size` 가 `^#{2,3}\s*바로 다음 작업` 으로 판정하고
  `AGENTS.md` 가 이 절을 이름으로 가리킨다. #898 Codex 인계본이 「바로 이어갈 자리」로 써서 공식 통합이 1회 실패했다.

## #898 마감 (Codex 구현 → Claude 인수·마감)

- Codex 한도 소진으로 worktree 에 인계 → Claude 가 인계서·리포트148·Redmine·diff 대조 후 인수(마스터 담당 기록 claude 16:41).
- 내용: 요청자 `ax-client` 관리 도구 **20개**(용어·온톨로지 편집/잠금·작업장·도메인 필드·로그 태그·staging·개명)를
  인증 **8101 POST 대행**(`master/task_queue/ontology_proxy.py`)으로 기존 마스터 코어에 연결. 요청자 스킬
  `ax-ontology`·`ax-request`·`manage-domain`·`refresh-ontology` 를 실제 도구·인자로 정정, `test_skill_conventions` 에
  역할별 MCP 서버 호출 검사 추가. 도메인 전체 삭제·멤버 추가/제거는 코어 미확인이라 미지원으로 명시.
- Claude 몫: 규약 47/49 의 두 표기(manage-domain:151 제목 → `rename-class`, refresh-ontology:35 → `ax-client:rename_class`)
  · 인계서 절 제목 복원. 사용자 「응 refresh-ontology 포함해서 진행해」·「응 1번으로 진행해」.
- 검증: 공식 통합 rc0 **188/188**(`Ran 188 tests in 167.594s`) · 규약 49/49 · 서버 13/13 · client 350/350 · `diff --check` rc0.
- 사용자 「응 커밋하고 마감까지 진행해」 → 커밋 `54b5632`(14파일) → `issue_finish_tool(898, confirm=True)`:
  `done=[push, ff, worktree_remove, delete_branch, register, link, release, close, redmine]`, `closed=true`, `why=""`.
  종합 리뷰는 비동기이며 완료를 주장하지 않는다.
- 반영: 사용자 「응 재기동하고 배달까지 진행해」 → `sudo -n /usr/bin/systemctl restart ax-task-queue` rc0,
  `ExecMainStartTimestamp` 12:31:43 → **16:49:16**, active. 무토큰 `POST /api/v1/workshops/list` 401(인증 관문).
  `master.client update` rc0, 마운트된 AXCluster `.43`·`.2`·`.33` **3/3 OK**(출처 HEAD `048dc25`), 신선도 경고 없음.
- [주의] **게임 프로젝트(요청자) 쪽은 아직 배달 전**이다 — `update` 는 마운트된 AXCluster 만 맞춘다. 게임 프로젝트는 마운트 전환 때
  `set_active` 가 뒤처진 기계만 맞춘다. **실제 `.33` 요청자 세션에서의 새 도구 호출은 재지 않았다.**

## 🔴 일감 작업 위치 (#907)

- **AXCluster 일감은 운영 체크아웃에서 편집하지 않는다.** 운영 `/home/sim/ax-cluster` 는 서비스 코드라 **늘 `main`**.
  `ax-projects:issue_start_tool(N)` 이 `/home/sim/ax-cluster/.ax-issues/<N>` 에 `issue/<N>` worktree 를 만든다.
  **응답의 `repo` 가 편집·검사·커밋 위치**, `checkout` 은 운영 저장소(편집 금지).
- `finish(confirm=True)` = push → 운영 main ff → worktree 제거 → 브랜치 삭제 → 마감 추적·잠금 해제·완료.
  상주 서비스(ax-projects·ax-task-queue·ax-broker) 재기동은 별도 승인.
- `pause` = worktree 제거(브랜치 유지), 재개 = `issue_start_tool`. **#898 에서 깨끗한 worktree 의 보류→재개를 실증했다**
  (16:15, 리비전 보존). 미커밋 변경이 있는 보류는 미검증 — dirty 상태에서 pause 하지 않는다.
- 🔴 `AXCluster/repo`(`track.local_clone`)는 **색인기의 push 봉인 미러**다 — 작업 위치가 아니다(#906).
- 실증 6회: #909·#912·#898(Claude 마감), #910(Codex→Claude), #897·#894(Codex) — 모두 같은 `done` 9단계.

## 오늘 완료한 일감 (2026-11-08)

| 일감 | 결과 | 커밋 |
|---|---|---|
| #893 | 미검토 커밋 목록 유실 수정 | `c62b2fb` |
| #906 | 일감 작업 위치 운영 저장소 복귀 + 봉인 저장소 거절 | `201a81a` |
| #907 | 마스터 일감 worktree · `master_workspace`(AXCluster 전용) — 리포트 143 | `9f7248d` |
| #909 | #893 후속 — 해시 지적 0건이면 판정 절 요구 안 함 | `5de2c16` |
| #910 | worktree 에서 `test_ontology`·`test_sandbox` 상시 실패 해소 — 리포트 144 | `1f07442`·`2142338` |
| #897 | 상주 서비스 신선도를 기동 내용 해시로 판정 — 리포트 145, 상주 3개 재기동(12:31) | `172cea8` |
| #912 | #897 후속 — journal `-n` 제거 · mtime 1차 거름 | `478a820` |
| #894 | 종합 리뷰 판정 칸 마크다운 꾸밈 인식 — 리포트 146 | `c47d5b2` |
| #895 | 라운드 공지 검사의 멱등 저장 대기 — 리포트 147, 배달 3/3 OK | `dc778fe` |
| #898 | 요청자 관리 도구 8101 대행 — 리포트 148 (위) | `54b5632` |

- 등록: **#908**·**#911** 아이디어(일감 아님).
- [주의] systemd 249 는 `journalctl -n` 을 `--grep` 보다 먼저 적용한다 — 서비스 기동 기록 조회에 `-n` 을 붙이지 않는다.

## 실제 Git·경로 상태

| 역할 | 위치 | 상태 |
|---|---|---|
| 운영 저장소 | `/home/sim/ax-cluster` | main=origin/main=`048dc25`(+ 이 문서 커밋), 깨끗함 |
| 일감 worktree 부모 | `/home/sim/ax-cluster/.ax-issues/` | 비어 있음 · 일감 잠금 없음 |
| 색인 미러 | `/home/sim/ax-cluster/AXCluster/repo` | main 하나 · origin/main 추적 |
| AXCluster 워커 | `.43 /home/sim/trunk/AXCluster`, `.2`·`.33 C:\trunk\AXCluster` | `048dc25` 배달·검사 3/3 OK |

- 상주 재기동: ax-task-queue 16:49:16(#898) · ax-broker·ax-projects 12:31(#897). #898 은 ax-projects 코드를 바꾸지 않았다.
- `.2` 검사의 `[주의] 홈 중복 스킬 ~/.agents/skills/ax-work`(#661 부류)는 손대지 않았다.
- 남은 worktree `ax-788-work`·`ax-896-local`·`ax-900-local`·advance 1개는 보존. 자동 정리하지 않는다.

## Codex 가 알아야 할 것

- **검사 기준**: `AX_PROJECTS_ROOT=/home/sim/ax-cluster` 를 주고 일감 worktree 에서. 공식 통합 목록 `tests/integration/checks.json`
  (현재 188건) — 실패 0 이 기준. `-f` 라 첫 실패에서 멈추니 실패 뒤 수치는 분모가 아니다.
- **샌드박스**: Codex 기본 샌드박스는 `sg gitea` 를 막아 `test_source_scope` 가 28/32 가 된다(리포트 86). 서버 TestClient 검사도
  기본 샌드박스에서 무출력 대기한 적이 있다(#898). 원인 미확인으로 보고하지 말고 그 명령만 담은 좁은 스크립트로 해제 승인을 요청한다.
- **인계서 형식**: 상한 150줄 · 「바로 다음 작업」 절 필수(`test_handoff_size`). worktree 에 인계를 남겨도 같은 검사가 공식 통합에서 돈다.
- 검사·커밋·push·재기동은 각각 승인 규칙대로.

## 유지할 운영 상태

- 마스터 담당 기록 **claude(11-08 16:41)**, 워커 전역 codex(state, 10-18). Codex 가 실제 인수하면 `ax-handoff` 절차로 기록한다.
- ax-projects·ax-broker active(12:31) · ax-task-queue active(16:49), ax-followup.timer·ax-indexer.path·ax-review-queue.timer active.
- 마스터 완료 수신자는 ax-followup.timer 하나, 세션 훅 없음.
- #893~#898·#899~#907·#909·#910·#912 완료: 리포트138~148·Redmine. 중복 마감·산출물 재생성 금지.
- #885 는 사용자 보류 기록 유지 — 내용이 #897·#912·#907 로 해소됐을 가능성이 크나 닫을지는 사용자 결정(경우별 대조 후).
  #884 T7 의 닫는 방법은 미결.
- #890 R251·R252 및 후속 리뷰 처분은 최신 목록·코드와 대조 후 사용자 결정.
- 큐/스풀 #709·#211·#650, ax-788-work, ax-review-788 반려#821, MotionForge·NS 잔재는 보존한다.
- 미결: doc_sync 의존 등록 보강, #883 중복 플랜 제목, 훅 wait 일시오류 비대칭, 마스터 MCP 토큰 평문
  (`~/.codex/config.toml` bearer 평문 — 외부 전송 없음).

## 바로 다음 작업

1. `ax-handoff`로 이 문서와 실제 상태(운영 main·`.ax-issues` 비어 있음·잠금 없음)를 대조한다.
2. #898 실사용 확인은 남아 있다 — 게임 프로젝트 마운트 전환 뒤 `.33` 요청자 세션에서 새 `ax-client` 관리 도구를 한 번 불러 본다(사용자 결정).
3. 다음 일감은 사용자가 고른다 — 후보 #886(마스터 로컬 브랜치·worktree 잔재 정리, 삭제마다 승인). 시작은 `issue_start_tool`.
4. 커밋·push·재기동·⑦ 전진·finalize는 기존 승인 규칙을 따른다. 다른 일감을 자동 시작하지 않는다.
