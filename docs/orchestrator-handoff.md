# 현재 AX 작업 인수인계

> 현재 체크포인트 한 벌이다. 지난 11월 1일 상세 요약은 Git `c4d4fc1`의 이 파일과 각 Redmine 노트에 있다.
> 항목·진행의 정본은 Redmine이다. HEAD·dirty·마운트·모드는 재조회한다.

## 상태

- **갱신**: 2026-11-03 KST · Claude · 상태 재대조만(코드 변경 없음).
- **저장소**: `main` · HEAD=`origin/main`=`500b1de`, 작업 트리 깨끗. #234는 `fb48155`,
  #259 `.gitignore` 1줄은 `500b1de`로 분리 커밋·push 완료(11-02 00:16).
- **배달**: `master.client check AXCluster` — `.43`·`.2`·`.33` 모두 OK, 출처=마스터 HEAD(11-03 재확인).
  `.2`는 홈 중복 스킬 1개 주의(프로젝트 로컬 정본 우선).
- **마운트**: AXCluster 유지. ServerTest는 등록만 했고 마운트·실제 온보딩은 하지 않았다.
- **재부팅**: 마스터 11-02 23:56:08 부팅. ax-projects·ax-broker·ax-task-queue 23:56:25 기동, active.
  원인은 조사하지 않았다. `.2`는 `janus` console 세션 ID 1 활성(로그온 23:55), `AxConductor` 준비·대화형만.
  `.2` 부팅 시각은 미확인, 실제 파견 실행은 미검증.
- **지휘 기록**: 마스터 마지막 기록 claude(10-21), 워커 전역 codex(10-18). 변경하지 않았다.

## #234 — 불필요 코드 제거 및 검증

- 사용자 지시: 전체 조사 → 불필요 코드 제거 → 검사 → 일감 종결. 커밋·push·배달 승인은 별도다.
- Gemini 조사: `reports/research/2026-11-01-234-unused-code.md`. 핵심 인용 7개 대조, 5일치·2불일치/자료미제공 표시.
  coordinator의 공용 Git 헬퍼 사용과 옛 epoch 실행부 사용을 혼동한 주장, 미제공 이력 인용은 제거 근거에서 제외했다.
- 제거: selftest·벡터 폴백 파일/전용 검사, coordinator의 옛 2-tier 실행부, 미사용 아카이브 이동 helper,
  웹 거부 스텁 2개, MCP wrapper 2개. 공용 Git 헬퍼·fetch_work·실제 MCP 조회·SQLite 캐시·문서 진단/복구는 유지했다.
- 초기 패치 실수로 부분 적용된 상태는 사용자 지시로 11파일 복구했고, 기준 검사199/53/59건 통과 후 다시 작업했다.
  `/tmp/ax-234-cleanup.Qfx0cN`에서 완성·검증한 뒤 단일 Git 패치로 마스터 반영했다. 18개 경로의 바이트 동일 확인.
- 관련 회귀: retired12·coordinator6·client_mcp199·cache22·context_audit38·attempt47·webwrite9·daemon18 모두 통과.
  실제 변경 Python12파일 정적 검사: pyflakes/import/mypy(call-arg) 차단0, import 환경 누락0.
  공식 통합184/184 rc0(163.331초), 로그 `/tmp/ax-234-integration.log`. 마스터 핵심12/6/199 재확인·diff --check 통과.
- 공용 Git 헬퍼5개 AST는 기존 HEAD와 동일. 실제 트윈 문서·운영 브랜치·원격 데이터는 삭제하지 않았다.
- 완결 패치 `/tmp/ax-234-complete-removal.patch`, 초기 부분 변경 백업 `/tmp/ax-234-partial-before-recovery.patch`.
- #234 T1·T2·T3 완료 반영, 일감 「완료」·100 종결. 이후 `fb48155` 커밋·push·워커 배달까지 완료(11-03 대조).

## 함께 이어받을 상태

- **#874 완료**: `c4d4fc1` 구현·검사 커밋 및 origin push 완료. cleanup84/84·전수198파일rc0·통합184/184.
  운영 machines 조회에서 취소 로컬 task/777/base 후보(고유1·gc 경고), 반려 로컬·미러 worktree #821 보존 확인. 삭제0.
- **#259 완료**: 사용자 지시로 완료100 종결. 사용자 제공 `http://192.168.0.57:3000/Sim/ServerTest.git`를 등록했다.
  `ServerTest` main `00cdf011`, onboard 계획조회rc0: bare/register 완료·나머지8단계 남음/차단. 실제 초기화 실증은 아니다.
  프로필·컨벤션·작업장 미설정, 워터마크 빈 값. 작업장 등록·`--confirm`·합성·배달·마운트 전환 미실행.
- 11월1일 종결: #862·#864·#865·#863·#867·#868·#869·#851·#853·#871·#333·#875. 상세는 각 일감과 기존 Git 체크포인트.
- 기존 미결: #839②·#840①·#791D·#820·#372·#855·#826 next_steps 표시. 상태는 다시 조회한다.
- 잔재·보존: AXCluster 큐 고아/스풀(#709·#211·#650), 마스터 ax-788-work, 미러 ax-review-788 반려 #821,
  MotionForge 미병합 durable·스풀 및 NS 고아/스풀은 손대지 않았다. 자동 삭제하지 않는다.
- #875의 정식 취소 입구는 review.cancel_work다. 큐 직접 PATCH로 취소·Redmine 종결을 우회하지 않는다.

## 바로 다음 작업

1. HEAD·dirty·Redmine·마운트를 대조한다. #234·#259 커밋·배달은 끝났다 — 다시 하지 않는다.
2. 재부팅 뒤 첫 파견이면 `.2` 세션 1 경로의 실제 실행·결과 회수를 확인한다.
3. 커밋·운영 배달·재기동·마운트 전환은 각각 승인을 확인한다. dirty 상태로 배달하지 않는다.
4. 다음 일감은 사용자가 고른다. plan_start → 상태 전이 → 실제 코드·검사·기록 순서를 지킨다.
5. 실패 시 코드·설정을 자동 수정하지 않고 보고·중단한다. 기존 경로 재사용 전 폐기·복원 이력을 확인한다.
