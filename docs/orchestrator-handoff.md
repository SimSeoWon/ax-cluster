# 현재 AX 작업 인수인계

> [중요] **한 벌만 유지한다.** 새 파일을 만들지 말고 이 파일을 덮어 쓴다.
> 양식은 `docs/15-orchestrator-handoff.md` §15.5 · 공용 규칙은 `docs/orchestrator-rules.md`.
> 모르는 상태는 **`미확인`** 으로 적는다. **이 기록은 잠금이 아니다** — 실행을 막지 않는다.
> 🔴 **여기 적힌 「완료」를 그대로 믿지 않는다.** 받는 쪽은 HEAD·dirty diff·이슈·프로세스를
> 직접 대조한다 (근거: `orchestrator-rules.md` §5).
> 🔴 [주의] **「완료」만 대조하면 부족하다** — 이 문서의 **관측 서술**도 대조 대상이다.

- **갱신 시각**: 2026-09-30 01:40 KST
- **지휘 도구 / 세션 식별자**: **Claude** (Opus 5.5, 1M)
- **상태**: **세션 종료** — 사용자 *"#694는 열어두고 오늘은 여기까지"* (2026-09-30). 1~8번 처리 · 6번(`#694`)은 빌드 경로 실측만 남음(사람 결정)
- **관련 일감**: **`#693`**(AX · index_only · 열림) · **`#661`**(`.2` 그림자 스킬 · 열림) · **`#694`**(kimodo, 미착수)
- **저장소·브랜치·HEAD**: `~/ax-cluster` `main` **`c344b4d`** (GitHub 푸시 · `.43` 동기화 완료) + 이 인계서
- **실행 중인 작업·프로세스**: 없음 · `ax-projects` 재시작 09-30 00:59:37(사용자 승인 — `a168340` 적용)
- 🔴 **워커 모드는 `codex` 다**(`~/.cache/ax-dispatch/mode.json`, 09-12 사용자 지시) — 그래서 `.2` 그림자가 실제로 읽힌다
- 🔴 **마운트는 `KimodoMotion_WebUI` 다** (사용자 지시 2026-09-30 — `#694` 착수 준비). NS 로 돌아갈 때 남은 것은
  보존 결정분 3건뿐(고아 태스크 2 · 스풀 1). [주의] 그래서 `.2` `AxWorker_NS` 는 다시 5분마다 `not_mounted` 를 받는다 — 정상
- 이 세션의 기록: [리포트 77](../reports/77-kimodo-followups-and-shadow-skill.md)

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
5. ~~CLAUDE.md 두 곳 「AX 는 ModularStage」~~ — **완료** `a7241c6`(사용자 동의 · `ax-cluster`(id 3))
6. `#694` — **스크립트·스킬 완성**(사용자: 커밋 기준 **Gitea**). Kimodo Gitea `637c09b`·`bdfa6f2`·`6cf1488` ·
   `scripts/follow-upstream.ps1` + 시나리오 테스트 `.33` 24/24 · `.33` Gitea 클론 서브모듈 초기화 · 실물 실행 「이미 최신」
   (`upstream/main` `5679ff1`). [미실측] 빌드·ctest 경로는 원본이 움직여야 돈다 — 기준선 빌드 여부 사람 결정.
   마스터 작업 클론 `~/claude-workspace/kimodo-work`(Gitea). 원래 클론 `Test_KimodoMotion`(GitHub)과 갈라질 수 있다
7. **전체 배달 완료**(09-30 01:00~, `master.client update`) — 3프로젝트 전부 **출처 = 마스터 HEAD** ·
   `.33`·`.43` OK · `.33` AGENTS.md 블록 교체 · `client_mcp.py` 불일치 해소. **FAIL 은 `.2` 그림자 하나뿐**(rc=1).
   🔴 `#661` **원인이 좁혀졌다 — Codex 데스크톱 앱 기동**: 09-26 15:34:24 앱 기동 → 15:34:31 그림자 ·
   09-30 00:52:42 앱 런타임(`AppData\Local\OpenAI\Codex\bin\…`) 기동 → **00:52:49 그림자**(내가 00:50 경 지운
   직후, 배달이 `.2` 에 쓴 01:03 보다 10분 앞). 두 번 다 **7초**. CLI 파견·배달은 원인이 아니다.
   [미확정] 옛 「너(Codex)」 판을 **어디서** 가져오나 — 디스크 전체 동일 해시 없음 · 앱 DB 에서도 못 찾음(WAL 미복사).
   백업 `~/claude-workspace/backups/2-agents-skills-20260930/`.
   🔴 **사용자 결정 (a) 2026-09-30: `.2` 에서는 Codex 데스크톱 앱을 쓰지 않는다** — 파견은 CLI 라 영향 없음.
   다섯 번째 삭제(해시가 백업과 같음) 뒤 `client check NS` **3/3 OK**. 앱을 다시 열면 재발한다 — 재발 신호는 check 의 `.2` FAIL
8. ~~NS 고아 태스크 2건~~ — **그대로 둔다**(사용자 결정 A 2026-09-30 · 08-23 「`failed` 는 증거로 보존」과 같은 판단).
   `5c9f33b6`(r1)·`6831331b`(r2) 는 머지된 work `…_198821b8` 의 `NSAnimNotify_MeleeHitCheck.h` 조각 — 각 3회 `revise` 실패,
   대상 파일은 `4baeb22`(F5)에서 재작성됐다. 인계 조사에 「보존」으로 계속 뜨는 것은 **정상**이다

## 3. 관련 파일

    master/projects/profile.py · master/client/spec.py · master/client/bundle.py
    master/context_search/paths.py (SourceScope) · master/context_search/index.py (핸들 복구)
    master/events/consumer.py · master/webui/{app,routes,web_ui_original}.py
    KimodoMotion_WebUI/config.yaml (git 밖) · master/client/payload/profile/KimodoMotion_WebUI.yaml
    reports/76-index-only-kimodo-onboarding.md
