# #899 — 기존 스킬 전체 분석: Claude 훅 의존 · Codex 실행 경로 · 주기 확인 폴백

## 현재 상태

- 분석 전용 일감이다. 코드·설정·배달·서비스는 바꾸지 않았다. 이 보고서 하나가 산출물이다.
- 시작 리비전 `7bf0dcb`, 브랜치 `issue/899`. 사용자 선택은 로컬 서브 에이전트(2026-11-07):
  스킬군별 3개(마스터 / 요청자·워커+Codex / 워크숍+훅)가 읽기 전용으로 조사했고, 마스터 Claude 가
  핵심 주장을 소스에서 다시 확인해 취합했다. 워커 SSH 는 읽기 명령(version·ls·Get-Content·
  Get-FileHash·schtasks /query)만 썼다. `.33` 게임 트리는 열지 않았다.
- RAG request `36fa21af74d941c8aa4d8962ee67a0f5`.
- 표기: **[사실]** 파일:줄·명령 출력 · **[추론]** 사실에서 끌어낸 판단 · **미실증** 실행 근거 없음
  (부재의 증명이 아니다).

## 1. 분모 — 정본 스킬 26 + 훅 5 [사실]

| 묶음 | 위치 | 수 | 번들 |
|---|---|---|---|
| 마스터 | `master/skills/` | 9 | `scripts/conductor.py` 2벌(ax-handoff·ax-mode, 서브명령만 다른 사본) |
| 요청자·워커 | `master/client/skills/` | 9 | ax-request `reference/` 3개뿐 |
| 워크숍 | `master/client/workshop/skills/` | 8 | 없음 |
| 훅 | `master/client/workshop/hooks/` | 5 .py | settings 등록 스크립트 3 · 등록 항목 4 |

- 착수 때 「마스터 10」으로 말한 것은 ax-gemini 를 두 번 센 것이다(정본은 요청자 쪽, 마스터 홈엔 링크).
- `AXCluster/repo`·`ax-review-*` 아래 사본(트윈·리뷰 트리)과 Kimodo 스킬 1개는 분모에서 뺐다.
- `workshop/README.md` §3 의 「11종 + debate」는 낡은 서술이다(실물 8).

## 2. 배달 — 누가 무엇을 어디서 받나 [사실]

- 요청자·워커 스킬: `spec.skills_for`(`spec.py:148-203`) 가 kind·role 로 고른다.
  unreal = 워커 ax-work·ax-infer / 요청자 7 · code(AXCluster) = 워커 ax-work / 요청자 6(ax-fix 제외) ·
  index_only = 요청자 ax-ontology·ax-gemini. 배달 위치 = 홈 `~/.claude/skills`·`~/.codex/skills` +
  체크아웃 `.agents/skills`(`spec.py:448-449`). `~/.agents/skills` 는 그림자 자리로 `check` 가 잡는다(`:467`).
- 워크숍 스킬 8: `bundle.workshop_files`(`bundle.py:1868-1895`) — **unreal 요청자만**, 체크아웃 `.claude/skills`.
  `.agents/skills`·`~/.codex/skills` 로는 안 간다 → **Codex 경로 없음**. `SKILLS_BY_ROLE`·`DEPRECATED_SKILLS` 밖.
- 훅: `MANAGED_HOOKS`(`spec.py:390-424`) → `managed_hooks_for`(requester 만, `:563-576`) →
  `merge_settings_json`(`bundle.py:1654`) 이 `.claude/settings.json` 에만 쓴다. **워커 0개.**
- AXCluster 는 `requester: master`, 작업장 3대 전부 worker → **요청자 스킬·훅을 받는 기계가 없다.**
  마스터는 distribute·ax-plan 등 마스터 스킬로 그 자리를 대신한다(#798 「마스터 훅 금지」와 일치).
- 마스터 홈 링크: `~/.claude/skills`·`~/.agents/skills` 10개(9+ax-gemini), `~/.codex/skills` 8개
  (ax-worker-setup·ax-gemini 없음). Codex 는 두 디렉토리를 다 읽는다(11-07 롤아웃이 둘 다 인용).

## 3. 스킬별 대조표 (26행)

열: 훅 = Claude 훅 의존 · Codex = 지원/연결/실동작/미실증 · 완료 = 누가 끝을 알아채나.

### 3.1 마스터 9 (+ 링크 ax-gemini)

| 스킬 | 훅 | Codex | 완료·후속 | 실증·결함 |
|---|---|---|---|---|
| ax-deliver | 없음 | 연결·실동작(`master.client update` 22개 롤아웃) | 동기 rc | 일상 사용 |
| ax-docsync | 없음 | 연결·**부분**(임시 등록부 `/tmp/ax-838-live-…` 에서만) | 동기, 사람 게이트 | 127 |
| ax-handoff | 없음 | 연결·실동작(get_orchestration 56·record 5) | 동기 | scripts 사본 이중화 |
| ax-mode | 없음 | 연결·실동작(조회 43·전역 9), **work 단위 미실증** | 동기, 재조회 | — |
| ax-plan | 없음 | 연결·실동작(transition 98 등), **pause/cancel 미실증** | finish 가 닫음, 리뷰는 `ax-review-queue.timer` | 132·136·137 · 「도구 다섯」(실제 7) · §5 「닫기는 별도」가 #889 와 모순 |
| ax-redmine | 없음 | 연결·실동작(get 334·note 155), **위키·버전 미실증** | 동기, 되읽기 | 잠금 관문(`redmine.py:537`) 미언급 |
| ax-worker-setup | 없음 | `~/.agents` 만·**미실증**(0회) | 동기 | 130(스킬 경유 아님) |
| debate | 없음 | 연결·**실행 경로 미정의**(본문이 Claude Agent/Write 툴 전제) | 세션 내 | 08-18 1회 · `.2` 14b 서술 낡음 · 시스템 `python3` |
| distribute | 없음(`:163`) | 연결·앞단 실동작, **⑥ `--wait` 0회** | 타이머가 준비·노트, 세션은 `run_in_background` 깨우기 | `:51` search_context 인자 누락(#837 계약) · `:148` improve_work 미인지 |
| ax-gemini(링크) | 없음 | `~/.agents` 만·실행 8회, 완료 통지 미실증(`:114` 자인) | `run_in_background` | Write/Edit 도구 이름 |

### 3.2 요청자·워커 9

| 스킬 | 수신(unreal/code) | 훅 | Codex | 완료·후속 | 실증·결함 |
|---|---|---|---|---|---|
| ax-request | 요청자/요청자 | **직접**: work_completion asyncRewake + pending_works | 훅 미연결 → 등재 응답 `wait`(`client_mcp.py:373,408`), 스크립트가 `.claude/hooks/` 아래 | rc 0/2/3/4 | 훅 라이브 4/4(리포트 60) · Windows `--wait` 명령 실측(#799) · **세션 깨움 미실측** · §5 의 ax-projects 2종(#898) |
| ax-advance | 요청자/요청자 | 간접(improve_work 가 같은 훅) | 맨 `py -c` — Windows Codex 샌드박스 `py` 실패 부류(ax-fix 실측) **미실증** | 사람 승인 → push | ⑺ 라이브 09-05 · 리포트 88 |
| ax-review | 요청자/요청자 | 없음 | 같은 `py -c` 위험 | finalize 동기 | §7 「완료로 닫지 않는다」가 finalize/cancel 과 모순 |
| ax-fix | 요청자/미수신 | 없음 | `backends.python` 절대경로 규칙 있음 | diff→승인→commit | #631 · 리포트 68 |
| ax-gemini | 요청자/요청자 | 없음 | 위 3.1 | — | #763 `.33` 1회 미측 |
| ax-issue | 요청자/요청자 | 없음 | 공용 명시 | finish | **실제 배달 0**(unreal 미재배달 · AXCluster 요청자=마스터) |
| ax-ontology | 요청자/요청자 | 없음 | ax-projects 미등록 → 도구 부재 | — | **#898**: 11종 중 ax-client 대응 3(search_context·add_object_alias·mark_not_a_class), 8종 없음 |
| ax-work | 워커/워커 | 없음 | Linux SSH `codex exec`(`runner.py:579-584`) · Windows `schtasks /run AxConductor_*`(`:971`) | **SSH 결과 회수**(`done.flag` `:996`, `out/rc` `:1008-1009`) | AXCluster 3/3·4/4(88) · 89 · §2 「토큰·MCP 없음」 낡음(.43 에 `.ax/token`·ax-client 있음) |
| ax-infer | 워커/미수신 | 없음 | 위와 같음 | stdout 마커 | **운영 호출부 0**(`infer_task` 는 `test_infer.py` 만) · 홈 사본 낡음 |

### 3.3 워크숍 8 (unreal 요청자 `.claude/skills` 전용, Codex 경로 없음, 훅 의존 없음)

| 스킬 | 호출 대상 상태 | 실증 |
|---|---|---|
| audit-context · cleanup-drift · ontology-register · refresh-ontology | **전부 은퇴**(`context_search` MCP·`watch.exe`, 2026-08-20) | 없음 |
| manage-domain · manage-task | 조회만 실재(get_domain_layer·get_object_spec·add_object_alias·get/list_task_template), 쓰기 없음 | 없음 |
| generate-contract-test | 조회(get_task_template) 실재, 후속 등록 도구 없음 | 없음 |
| debate(워크숍판) | Claude Agent 전용, `history/` 로컬 저장이 「히스토리는 마스터가 쓴다」 규약과 충돌 | 없음 |

## 4. 훅과 세션 밖 경로 [사실]

| 훅 | 이벤트 | 상태·중복 방지 | 안 돌면 |
|---|---|---|---|
| domain_hint | PostToolUse `Edit\|Write` 10s | 무상태 | 힌트만 사라짐 |
| pending_works | SessionStart 15s + UserPromptSubmit 8s | 무상태 — 매 턴 같은 목록(의도) | 사람이 Redmine·8103 에서 찾음 |
| editor_mcp(모듈) | pending_works 경유 | 세션별 `last` 같으면 침묵 | 고지만 사라짐 |
| work_completion | PostToolUse `""` 7260s asyncRewake | 키 `sha256(session, work_id, round)` + O_EXCL 잠금(15s 하트비트·90s stale) | 세션 안 깨움 → `--wait` CLI(고지 파일 공유 안 함, 중복 허용 `:68-73`) |
| hook_paths(모듈) | — | — | — |

세션 밖 경로: post-receive 직접 신호 + 소비자 백업 → `ax-dispatch.path` · `ax-dispatch.timer` 10분 catchup
(work flock) · 큐 `_flip_if_all_terminal` 이 같은 저장에 `notice_pending` → 공지 →
`recover_stuck_works` 기동 재공지(#891) · `ax-followup.timer` 1분(AXCluster 고정, 키
`sha256(repo, work_id, round)` + RoundLock, 11-07 22:4x `scan_tick` 확인).

Codex [사실]: 마스터 0.167.0 · `.2`/`.43`/`.33` 0.159.3. 네 대 모두 `codex features list` 에
`hooks stable true`(마스터 직접 재확인). 그러나 네 대 모두 hooks.json·config 훅 키 없음 →
**지원 O · 연결 X · AX 실동작 미실증.** `.2` 의 `notify` 는 Codex 데스크톱 앱 값(AX 무관).
리포트 114 와 `ax-request/reference/wait-for-completion.md:49` 의 「Codex 에는 훅이 없다」는
「설정이 없다」로 읽어야 한다. 워커 파견 완료는 훅이 아니라 마스터의 SSH 회수라 이 공백과 무관하다.

## 5. 누락·중복 위험

### 5.1 Codex 에서 빠지는 자리

1. 요청자 Codex 의 라운드 완료 수신 — `wait` 명령뿐. 세션을 깨우는지·포그라운드로 막아야 하는지 미실측.
2. `wait` 스크립트 위치가 `.claude/hooks/work_completion.py` — Codex 경로가 Claude 작업장 자산 배달에 묶임.
3. 마스터 distribute ⑥ — Claude `run_in_background` 깨우기만 정의. 타이머가 준비·노트는 하므로 결과는
   안 사라지지만, 사용자에게 게이트를 묻는 일은 세션이 깨어나야 일어난다. ax-gemini 도 같은 구조.
4. ax-advance·ax-review 의 맨 `py -c`(Windows Codex 샌드박스) — 미실증.
5. 워크숍 8종 — Codex 로는 배달 자체가 없다(Claude 로도 6종은 동작 대상이 없다).

### 5.2 「전송 성공 · 상태 저장 전 종료」 창 — 경로마다 방향이 다르다 (마스터 재확인)

| 경로 | 순서 | 그 창에서 죽으면 |
|---|---|---|
| 큐 라운드 공지(#891) | `notice_pending` 저장 → 노트 → `noticed_round` 저장 | **중복**(다음 큐 기동에서 재공지). 단 재시도는 **기동 1회뿐** |
| 큐 조각 즉시 실패(#780) | `fail_notice_pending=True`(`logic_cleanup.py:776`, 메모리) → 노트 → `_record_piece_fail_notice`(`:688`, 여기서만 저장) | **누락**(표시가 디스크에 없고 task 단위 복구 경로 없음) |
| work_completion 훅 | `signal_emitted` 기록 → 출력·exit 2(`:270-273`) | **누락**(다음 감시 `already_noticed`). CLI `--wait`·pending_works 가 덮음 |
| followup ⑦ 노트 | `write_state(rec)` → `_post_note_once` → 재기록(`followup.py:1183-1185`) | **누락**(다음 주기 `already_prepared`, 노트 실패도 재시도 없음) |

### 5.3 이중 호출 자리

- `.33` Claude: 훅 + 세션이 띄운 `--wait` CLI 가 같은 라운드를 각각 고지(의도된 허용).
- pending_works 매 턴 반복(의도). 세션 안 register/improve 재응답은 잠금·`already_noticed` 로 막힘.
- [추론] 큐 공지의 멱등 검사는 잠금 안이나 전송은 잠금 밖 — 기동 재공지와 다른 경로가 거의 동시에
  돌면 둘 다 통과할 수 있다. 실제 발생 기록은 못 찾음.

## 6. 「훅 우선 + 주기 확인 폴백」 적용 범위

- **마스터(AXCluster)**: 이미 타이머 단일 수신자(#798)다. 훅과 겹칠 일이 없다. 남은 공백은 「세션에게
  묻기」(5.1-3)이며, 이것은 폴백 플래그가 아니라 Codex 세션 깨우기 수단의 문제다.
- **요청자(.33)**: 훅(Claude) + `--wait` CLI(Claude·Codex) + pending_works(Claude 다음 턴)가 이미
  「훅 우선 + 폴링 폴백」 꼴이다. 세션 독립 주기 확인으로 만들려면 `.33` 상주물이 필요해 #860 과 충돌한다.
- **공유 키 후보**: 세션 독립 정본 키는 큐의 `(work_id, round)` + `noticed_status` 로 이미 있다.
  「요청자 세션에 전달됨」을 큐에 적는 필드는 없다(`noticed_*` 는 Redmine 공지 기준).
- **Codex 훅**: 설치본이 기능을 갖고 있으므로, 배선하면 요청자 Codex 에도 「훅 우선」이 가능할 수 있다.
  설정 위치·이벤트 계약은 로컬 문서가 없어 미확정 — 실측이 먼저다.

## 7. 미결 선택지 (구현 여부·방식·순서는 사용자 결정)

1. 요청자 억제 키 — 세션 단위 유지 vs 큐에 「세션 전달」 필드를 두고 훅·CLI 가 공유.
2. 큐 `notice_pending` 재시도 — 기동 1회 vs 주기(예: 기존 catchup·followup 타이머에 얹기).
3. `fail_notice_pending` 디스크 선저장(현재 누락 창).
4. work_completion·followup 노트의 순서를 #891 처럼 「대기 표시 → 전송 → 완료 기록」으로 맞출지.
5. Codex 훅 배선 실측 — 설정 위치·이벤트 계약을 한 대에서 재고, 되면 work_completion 을 Codex 에도.
6. distribute ⑥·ax-gemini 의 Codex 대기 수단 정의(포그라운드 대기 명시 등).
7. 워크숍 8종 — 은퇴 도구 6종을 재배선·폐지(`DEPRECATED_*`)·유지 중 무엇으로, Codex 배달 여부.
8. 문서 불일치 정리 묶음: ax-plan(도구 수·§5) · ax-review §7 · ax-work §2 · ax-redmine 관문 ·
   distribute `:51`·`:148` · debate 장비 서술 · `workshop/README.md` §3.
9. 결함 후보 일감화: `editor_mcp.notice` 가 `checkout_root` 대신 payload `cwd` 사용(`editor_mcp.py:336`,
   코드 대조만) · ax-issue 실배달 0 · `.2` `~/.agents/skills` 그림자(ax-work 해시 `eff26466` ≠ 배달본
   `26daed5c`, check 미실행) · `.43`/`.2` 홈 ax-infer 낡은 사본 · `.43` `.ax/worker_daemon.lock` 잔존 ·
   ax-infer 운영 호출부 0 처리.

## 8. 미실증 · 못 본 것

- Codex hooks 설정 위치·이벤트 계약 · Codex 세션에서 `wait` 가 세션을 깨우는 방식
- `.33` 요청자 세션의 `ax-projects:*` 실제 호출 결과(#898) · `.33` 실물 settings.json·skills(이번 조사 범위 밖)
- `[boot-renotice]` 실발생 기록(journal 조회 0건 — 권한·위치 문제일 수 있어 판정 보류)
- `.2` 그림자 스킬이 `master.client check` 에서 FAIL 로 잡히는지(check 미실행)

## 9. 범위 밖 관찰

- `~/.claude.json`·`~/.codex/config.toml` 에 `ax-projects` Bearer 토큰이 평문으로 있다(마스터). 값은
  옮기지 않았다. `.2` Codex 홈 config 에도 손배선 `ax-projects` 헤더가 있다. 처리 여부는 사용자 결정.
