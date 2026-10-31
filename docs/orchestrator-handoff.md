# 현재 AX 작업 인수인계

> 한 벌만 유지하는 **현재 체크포인트**다. 양식 `docs/15-orchestrator-handoff.md` §15.5 ·
> 공용 규칙 `docs/orchestrator-rules.md`. 체크포인트를 갱신할 때는 이 파일을 **덮어써서** 짧게
> 유지한다(`master/test_handoff_size.py` 가 막는다, `#842`) — 지난 내용은 `reports/`·Redmine 노트에 남기고,
> 2026-10-21 까지의 원문은 [`orchestrator-handoff-history.md`](orchestrator-handoff-history.md) 에 있다(이력 전용).
> 직전 체크포인트(10-31 02:19 Codex — #211 분석·코드 팩토리 보고서·드라이런 4건)는 이 파일의 git 이력(`b80c8e4`)에 있다.
> 여기 적힌 상태는 **기록 시점의 값**이다 — HEAD·dirty·Redmine·모드는 재조회해서 쓴다.

## 상태

- **갱신**: 2026-10-31 17:20 KST · Claude · 사용자 지시(#826 Phase A·#852 완료 뒤 인계서 반영)
- **저장소**: `~/ax-cluster` · `main` · HEAD=`origin/main`=`b5ec5eb`. 미커밋: 이 인계서 수정뿐(커밋은 별도 승인).
- **배달**: 커밋마다 `master.client update` — `.43`·`.2`·`.33` 전부 OK, 출처 HEAD 일치(`b5ec5eb` 기준).
  `.2` 홈 중복 `~/.agents/skills/ax-work` 주의는 종전과 같다(수정 안 함).
- **서비스 재기동**(사용자 승인): `ax-task-queue` 15:59:54·17:06:15 · `ax-projects` 16:39:01.
- **지휘 기록**: 마스터 담당 `claude`(10-21 기록) · 워커 전역 `codex`(state, 10-18). 바꾸지 않았다.
- **실행 중**: 없음. 서브 에이전트 없음(전부 마스터 로컬).
- **저장소 밖 변경**: `ax-plan` 스킬 링크 3개(`~/.claude/skills` · `~/.agents/skills` · `~/.codex/skills`).

## 이번 세션 — #729 묶음 · #826 Phase A · #852

- **일감 정리**: [#729](http://192.168.0.57:8080/issues/729)·[#826](http://192.168.0.57:8080/issues/826) 를 아이디어 → M7 로 이동,
  제목 `[아이디어]` 제거. #854·#856 은 아이디어에 남김. [#856](http://192.168.0.57:8080/issues/856) 에 Monolith MIT
  라이선스 배포 조건 노트(저작권·허가 문구 전문 유지, 번들 의존성·UE EULA 별도 확인 — LICENSE 원문 미대조).
- **#826 본문**: Textile → Markdown 변환(이 Redmine 서식이 Markdown — `h2.` 가 글자로 보였다).
  **플랜 영역 형식 v1**(사용자 결정): 본문 안 `<!-- ax:plan:begin v=1 -->` ~ `<!-- ax:plan:end -->`,
  표 칸 ID·상태·목표·대상·선행·검증·근거, 상태 대기·작업중·완료·차단·해당없음. 주석 태그는 화면에서 숨겨짐(실측).
- **#826 Phase A 플랜 T1~T6 전부 완료** (kind=code 파일럿, 7단계 중 1·3·5·7):

  | T | 커밋 | 내용 |
  |---|---|---|
  | T1 | `79a3c0d` | `master/plan_block.py`(태그 사이만 읽고 쓰기·영역 밖 바이트 보존) · `redmine._update_mismatches` CRLF 오탐 수정 |
  | T2 | `4cab2b1` | `master/plan_state.py` — 전이는 `transition` 하나, 근거 없는 완료·사유 없는 차단·선행 미완료 착수·완료 되돌리기 거절 |
  | T3 | `a02e7ee` | `master/plan_start.py` — no_spec·plan_needed·plan_invalid·plan_violations·resume·next·blocked·plan_done |
  | T4 | `90ed562` | `master/plan_steps.py` — kind 별 7단계(code 2·4·6 해당없음 · unreal 조건부 · 빈/index_only 거절) |
  | T5 | `2552ff4` | `master/plan_tools.py` + MCP `plan_start_tool`·`plan_set_tool`·`plan_transition_tool` + 스킬 `ax-plan` |
  | T6 | `b5ec5eb` | [#852](http://192.168.0.57:8080/issues/852) 파일럿 완주 — 아래 |

  설계 선택(사용자에게 보고함): 완료는 되돌리지 않는다 · 근거와 사유는 같은 칸 · `plan_set` 은 상태·근거를 못 바꾸고
  시작된 태스크를 못 뺀다 · 읽기-쓰기 사이 사람 수정은 덮인다(Redmine 조건부 갱신 없음 → 동시 마킹 금지).
- **#852 완료** — `find_history` 자유 질의 공백 단위 AND(`history_harvest.search`). plan_start → RAG·소스 대조 →
  승인 → plan_set → T1~T3 마킹 → plan_done 의 첫 실사용. MCP 실호출 '언어 분기 온톨로지'·'온톨로지 언어' 0→1, 기존 1·1·5 유지.
- **CRLF 오탐**: Redmine 이 본문을 CRLF 로 저장해 description 갱신이 매번 「반영 안 됨」이었다(직전 Codex 세션에서도).
  T1 에서 고쳤고 큐 재기동 뒤 `ok: true` 확인.
- 검사(마지막 커밋 기준): `master/test_*.py` 192개 9049/9049 · 통합 181 OK.
- 결정은 `log_history` 로 올렸다(플랜 영역 형식·Phase A 범위).

## 미검증·정정

- **#826 T6 의 「다른 세션이 다음 태스크를 정확히 집는지」는 미검증** — 같은 세션 안에서만 확인했다(#826 보충 노트).
  다음 세션에서 `plan_start_tool(826)`(→ plan_done) · `plan_start_tool(852)`(→ plan_done) 를 불러 확인한다.
- [정정] 세션 중 `find_history` 의 `next_steps` 가 `alternatives_considered` 와 같은 것을 「매핑 결함 후보」로 보고했으나,
  원전 계약이다 — `history_harvest.py:293-296` 이 alternatives + 후속 섹션을 합치고, 원전 `AgentTest/watcher/history_harvest.py:317`
  과 양쪽 테스트(`test_alternatives_in_next_steps`, 우리 `test_history_harvest.py:71`)가 그렇게 못박는다. 결함 등록은 보류하고 사용자에게 물었다.

## 사용자 답을 기다리는 것

1. **#826 다음 단계** — 본문 범위(Unreal 제네레이트·에디터·MCP·클래스 추가/제거)는 Phase A 밖. 다음 Phase 플랜을 #826 에 더할지, 하위 일감으로 나눌지. #826 은 닫지 않았다.
2. **`next_steps` 표시** — 원전 계약을 유지할지, MCP 응답에서 「다음 단계」에 기각된 대안이 섞이는 것을 개선 일감으로 올릴지.
3. 앞 세션에서 넘어온 결정(그대로 유효): [#839](http://192.168.0.57:8080/issues/839) ② 스냅샷 범위 · [#840](http://192.168.0.57:8080/issues/840) ① 후보 보관 ·
   [#791](http://192.168.0.57:8080/issues/791) D 라운드 실패 처리 · [#820](http://192.168.0.57:8080/issues/820) ⑦ 범위 밖 고지 · [#372](http://192.168.0.57:8080/issues/372) 차단 게이트 ·
   [#855](http://192.168.0.57:8080/issues/855) 착수 방식 · 포기된 `f3e3d96` 리뷰 재등재.

## 바로 다음 작업

1. HEAD·dirty·Redmine 을 재조회한다. 다음 작업은 사용자가 고른다 — 스스로 착수하지 않는다.
2. **일감을 시작할 때는 `ax-plan` 스킬**: `plan_start_tool` 이 먼저, `ok:false` 면 구현하지 않는다. 마킹은 `plan_transition_tool` 로만 —
   `redmine_note` 로 본문 전체를 보내 플랜을 고치지 않는다.
3. 위 「미검증」의 새 세션 확인부터 하면 #826 T6 공백이 닫힌다.
4. agy 를 쓰는 실측은 공용 한도 영향을 먼저 말한다. AXCluster 운영 온톨로지 도메인은 여전히 0개(등록은 사용자 결정).
5. **마운트 전환 때**: ModularStage → [#650](http://192.168.0.57:8080/issues/650) 프로필 · NS → [#649](http://192.168.0.57:8080/issues/649) E(쓰기 전 `.33` dirty 확인).
6. 마스터 worktree 2개(`ax-788-work`·`ax-advance-…_831`) 정리 미결([#333](http://192.168.0.57:8080/issues/333)).
   `b510d2f` 는 트윈 미러 `refs/ax/pruned/…` 에 보존돼 있다.

## 열려 있지만 별개인 것 (기록 시점 — Redmine 재조회)

- `.2` 새 경로 Codex 셸 읽기·apply_patch·결과 회수 — 다음 파견에서 확인
- 비마운트 3개(ModularStage·NS·MotionForge)의 `.2` 클론 — 마운트 전환 때 `set_active`
- #846 효과 재측정 · [#709](http://192.168.0.57:8080/issues/709) GitHub 저장소 삭제(사용자 웹 작업 뒤 404 확인)
- [#211](http://192.168.0.57:8080/issues/211) RAG 품질 — 분석·2차 검증 완료(`reports/research/2026-10-31-211-*`), 정책·구현 미착수
- 코드 팩토리·SDD 보고서 `reports/research/2026-10-31-code-factory-sdd.html`(+검증 MD) — Phase A 가 그 권고의 첫 파일럿이었다
- 앞선 Claude 세션 리포트: [130](../reports/130-worker2-board-swap-setup-host-ollama.md) · [131](../reports/131-849-ontology-pinned-tree.md)
