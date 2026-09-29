# 현재 AX 작업 인수인계

> [중요] **한 벌만 유지한다.** 새 파일을 만들지 말고 이 파일을 덮어 쓴다.
> 양식은 `docs/15-orchestrator-handoff.md` §15.5 · 공용 규칙은 `docs/orchestrator-rules.md`.
> 모르는 상태는 **`미확인`** 으로 적는다. **이 기록은 잠금이 아니다** — 실행을 막지 않는다.
> 🔴 **여기 적힌 「완료」를 그대로 믿지 않는다.** 받는 쪽은 HEAD·dirty diff·이슈·프로세스를
> 직접 대조한다 (근거: `orchestrator-rules.md` §5).
> 🔴 [주의] **「완료」만 대조하면 부족하다** — 이 문서의 **관측 서술**도 대조 대상이다.

- **갱신 시각**: 2026-09-30 KST (세션 진행 중)
- **지휘 도구 / 세션 식별자**: **Claude** (Opus 5.5, 1M)
- **상태**: **진행 중** — 아래 §2 를 사용자가 고른 순서로 처리 중. 1번·2번(`a168340`)·3번·4번 완료
- **관련 일감**: **`#693`**(AX · index_only · 열림) · **`#694`**(kimodo · 따라가기 스크립트, 미착수)
- **저장소·브랜치·HEAD**: `~/ax-cluster` `main` **`a168340`** (GitHub 푸시 · `.43` 동기화 완료) + 이 인계서
- **실행 중인 작업·프로세스**: 없음
- 🔴 **마운트는 다시 `NS` 다** — Kimodo 89/89 채운 뒤 사용자 지시로 되돌렸다(2026-09-30).
  Kimodo 를 다시 다루려면 **먼저 마운트를 옮긴다**(§0)

---

## 🔴 0. 먼저 읽을 것 — 내가 깬 규칙

**검색·갱신은 마운트된 프로젝트만 한다.** `#693` 초판(`7db807b`)이 index_only 를 예외로 빼서 NS 마운트
상태로 BC-250 에서 Kimodo 를 합성했다 — 사용자 격노. 되돌림 `43e6319`. 메모리
`mount-only-rule-no-exceptions`. **새 프로젝트는 마운트를 먼저 옮기고 돌린다.**

## 1. 오늘 한 것 (전부 커밋·푸시·`.43` 동기화)

| 커밋 | 무엇 |
|---|---|
| `292b7be` | 레드마인 분리 — `ax-cluster`(id 3)·`kimodo`(id 4) · 열린 `[AX]` 69 + `[아이디어]` 7 이전 · `AX_PROJECT_ID="ax-cluster"` |
| `7db807b` | 프로필 `kind: unreal\|index_only` · 배달 축소(스킬 ax-ontology · 커밋된 CLAUDE.md/AGENTS.md/.mcp.json 안 씀 · MCP 로컬 스코프) · `SourceScope`(`config.yaml source:`) · 서브모듈 한 단계 + gitlink 펼치기 |
| `01c6b2b` | 온보딩 교착(새 프로젝트에서 profile 이 clone 에 막힘) · Kimodo 프로필 |
| `43e6319` | 🔴 마운트 예외 두 곳 되돌림 |
| `44c4b44` | 로컬 스코프 MCP 대조 PowerShell 파싱 결함 · 리포트 76 |
| `3fcbf27` | 낡은 Chroma 핸들 복구(빈 색인 선검색 → 외부 첫 색인) |
| `02519ef` | 웹 UI 「전문 보기」 — `GET /api/v1/context/doc`(공개, context/*.md 한정) |

실물: Gitea `Sim/KimodoMotion_WebUI`(private) · `.33` `C:\Users\USER\Documents\KimodoMotion_WebUI` ·
합성 86/89 · 색인 86 · `.33` check **OK** · `.33` 클라 MCP `search_context` 실측 · 브라우저 전문 보기 사용자 확인.
서비스 재시작: `ax-task-queue` 23:39 · `ax-projects` 00:57(마지막).

### 1-1. 2026-09-30 — §2 의 1번 완료 (`d628aef`)

거부는 **4건**이었다(`llm_final_norm_parity` 누락). 🔴 **파서 오인 추정은 틀렸다** — 보조 구조체가
실재했고, 게이트가 ① 소문자 한 단어를 언급으로 못 셌고 ② 함수 중심 파일에 클래스 언급을 요구했다.
① 전 프로젝트 수정 · ② `kind: index_only` 만(사용자 「타입으로 가른다」). Kimodo 89/89 · 재색인 89 ·
NS 회귀 104건 판정 동일 · 테스트 5872/5872 · `#693` 노트.

## 2. 남은 것 — 전부 사람 결정 (손대지 않았다)

1. ~~Kimodo 사실 게이트 거부~~ — **완료** (§1-1)
2. ~~합성 86/89 인데 워터마크가 찍혔다~~ — **`#274` 위반이었다**: 온보딩 `do_index` 가 `synth_complete()`
   없이 HEAD 를 찍었다(게이트는 푸시 경로에만). 사용자 A 결정 — 색인은 만들고 워터마크만 막는다 · `a168340`
   · NS 복사본 드라이런으로 옛 코드 재현/새 코드 차단 확인
3. ~~NS 고아 문서 9~~ — **완료**(09-30, 사용자 「옮기기」): 기존 `context_audit` 아카이브로
   `NS/_archive/orphan_md/2026-09-30/` 이동 · NS 재색인 113→104 · 104/104 · `#693` 노트
4. ~~NS 스풀 6 정리 · `.2` `AxWorker_NS` 헛돎~~ — **완료**(09-30): 스풀 6 삭제(`handover apply`, 보존 3) ·
   워커는 NS 재마운트로 정상 복귀(해제 불필요) · `#693` 노트
5. CLAUDE.md 두 곳(`ax-cluster/CLAUDE.md:190` · `machines/sim-desktop.md:479`) 「AX 는 ModularStage」 문구
6. `#694` kimodo 따라가기 · GitHub `Test_KimodoMotion` 과 Gitea 가 갈라질 수 있다(어느 쪽에서 커밋할지)
7. 🔴 밀린 것(09-23 인계에서 이월): `#661` `.2` 그림자 스킬 재발 원인 · 전체 `master.client update` 는 이번에도 안 돌렸다(Kimodo 만 배달)
   — 09-30 NS 전환 때 `.2`·`.33`·`.43` 이 HEAD 보다 **9커밋 뒤**로 보고됐다(align 안 함)
8. NS 고아 태스크 2건 `5c9f33b6`·`6831331b` — `failed`(`.2` 할당, 09-12 work 잔재) · 다시 집히지 않는다

## 3. 관련 파일

    master/projects/profile.py · master/client/spec.py · master/client/bundle.py
    master/context_search/paths.py (SourceScope) · master/context_search/index.py (핸들 복구)
    master/events/consumer.py · master/webui/{app,routes,web_ui_original}.py
    KimodoMotion_WebUI/config.yaml (git 밖) · master/client/payload/profile/KimodoMotion_WebUI.yaml
    reports/76-index-only-kimodo-onboarding.md
