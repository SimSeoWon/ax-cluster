# 리포트 76 — 비UE 프로젝트를 「색인 전용」으로 받았다 · 레드마인을 나눴다 (`#693`)

- 날짜: 2026-09-28
- 커밋: `292b7be`(레드마인 분리) · `7db807b`(index_only 본체) · `01c6b2b`(온보딩 교착 · 프로필) · `43e6319`(🔴 마운트 예외 되돌림) · 이 리포트 커밋(로컬 MCP 대조 결함)
- 일감: [`#693`](http://192.168.0.57:8080/issues/693) (AX) · [`#694`](http://192.168.0.57:8080/issues/694) (kimodo — 원본 따라가기, 미착수)

## 1. 요청과 실측이 바꾼 것

사용자: *"신규 프로젝트 추가할까하는데? https://github.com/SimSeoWon/Test_KimodoMotion"* →
이름 `KimodoMotion_WebUI`, *"엔비디아가 애니메이션 모션을 만드는 Kimodo 라는 프로젝트를 스테이블
디퓨전 WebUI 처럼 래퍼를 만드는 프로젝트"*.

레포를 받아 보니 **UE5 프로젝트가 아니었다** — `.uproject`·`Source/` 없음, Python WebUI(.py 32) +
C++ 엔진은 사용자 포크 서브모듈(`vendor/kimodo.cpp` · `motion/main`), 그 안에 다시 `ggml`(964 파일).
AX 파이프라인은 곳곳에서 UE5 를 전제한다(골조 UHT · 조각별 UE5 빌드 · synth `Source/` 한정 ·
상주는 UE5 기계만).

🔴 **내 첫 추천이 틀렸다** — 「색인까지만」을 권했는데 실측하니 그것도 **빈 색인**이었다:
graph 는 `Source/` + UE 매크로, synth 는 `Source/` + C++, index 는 synth 가 만든 MD 만 색인,
검색·색인기는 마운트만 본다(`#242`). 타입 분류만 넣었으면 남는 것은 Gitea 미러뿐이었다.
그래서 결정이 「색인 전용 타입 + 경계 일반화 + 마운트 없는 검색」으로 커졌다.

## 2. 사용자 결정 (2026-09-28)

| | 결정 |
|---|---|
| 레드마인 | `ax-cluster`(id 3) · `kimodo`(id 4) 신설 · 열린 `[AX]` 69건 + `[아이디어]` 7건 이전 · 닫힌 것은 `modularstage` 에 남김 · 종전 「AX 는 ModularStage 에 함께」(08-09) 폐기 |
| 타입 | `kind: unreal \| index_only` 명시 분류 — 0~2단계(등록·색인·요청자 콘솔)까지, 분산 작업은 받지 않는다 |
| 정본 | Gitea 에 복사(migrate · 미러 아님) + `.33` 에 Gitea 기반 클론 한 벌 더 |
| ② 검색 | 콘솔이 자기 프로젝트 태그를 싣는다 — 🔴 **단 마운트된 것만 검색·갱신한다**(아래 §4-0, 내가 예외로 넓혔다가 되돌렸다) |
| ③ 서브모듈 | 합성은 kimodo.cpp 본체까지 · `ggml` 제외 · 서브모듈 구조 유지 · 따라가기는 스크립트+스킬(`#694`) |
| ④ 배달 | `.33` 요청자 하나 · `ax-ontology` 만 · 커밋된 사람 파일(루트 CLAUDE.md·AGENTS.md·`.mcp.json`) 안 씀 · MCP 는 로컬 스코프 |
| 프로필 | purpose `tool` · language *"Python WebUI · C++ 엔진은 포크 서브모듈"* · overview 사용자 발화 원문 |

## 3. 구현

(커밋 `7db807b` 메시지와 `#693` 노트에 목록이 있다 — 여기에는 **판단**만 남긴다.)

- **기본값이 곧 종전 동작이다.** `SourceScope()` = `Source/` · C++ · `ls-files -- Source` 글자까지 같다.
  NS·ModularStage 에 `kind: unreal` 을 적고 NS blockers 0 이 유지되는 것을 확인했다.
- **판정은 한 자리.** `SourceScope.contains` 를 graph 목록 둘 · synth 입구·식별자 · consumer diff 가 읽는다.
  배달은 `spec.INDEX_ONLY_*`·`entry_docs_for`·`mcp_scope_for` 를 deliver·plan·check 가 같이 읽는다.
- ~~마운트 게이트에 index_only 예외~~ — **되돌렸다**(§4-0).
- 🔴 **서브모듈 포인터 변경을 펼친다** — 루트 diff 는 `vendor/kimodo.cpp` 한 줄만 안다. 안 펼치면
  `#694` 의 따라가기 커밋이 「소스 밖 변경」으로 접혀 문서가 영영 안 갱신된다.
  **진짜 git + 진짜 서브모듈**로 테스트했다(흉내로는 `--recurse-submodules` 계약이 빠진다).
- **`.mcp.json` 은 로컬 스코프로** — `.33` 에서 탐침 항목을 넣고 지워 실측: 키는
  `C:/Users/USER/Documents/<폴더>`, `git status` 빈 출력. 대조는 `claude mcp get`(접속을 시도해 느리다)
  대신 `~/.claude.json` 의 그 항목만 뽑는다.

## 4-0. 🔴 내가 규칙을 깼다 — 마운트 예외

사용자 답 ②(「검색은 자기 태그로」)를 내가 **「마운트 전환 없이」로 넓혀 읽고** 색인기·검색에
index_only 예외를 넣었다. 그 상태로 **NS 가 마운트된 채 BC-250 에서 Kimodo 를 합성**했다.
사용자: *"이 프로젝트 내가 말했지 마운트 된것만 검색하고 갱신한다고"* · 레드마인을 나눈 것도
**그 프로젝트로 마운트를 옮겨 작업하겠다**는 뜻이었다. 합성을 멈추고(29/89) 예외 두 곳을
되돌리고(`43e6319`) 마운트를 `KimodoMotion_WebUI` 로 옮긴 뒤 이어서 돌렸다.
사용자 요청으로 **NS 문서 113건 전수 검사** — Kimodo 오염 0(오늘 수정 0 · `Source/` 밖 0 ·
kimodo 경로 언급 0 · `source_commit` 31종 전부 NS 커밋 · BM25·벡터 id `Source/` 밖 0).
대신 **옛 고아 문서 9건**(`Source/NS/Combat/` 컴포넌트 9종 — 소스는 `28e6d47`·`4baeb22`(09-19·22 GAS
이전)에서 지워졌고 문서는 09-13 그대로)이 나왔다 — 미처리, 사람 결정.
메모리 `mount-only-rule-no-exceptions` 로 남겼다.

## 4. 드러난 결함 — 내가 만든 것이 아닌 것

- **온보딩 교착** (`01c6b2b`): 새 프로젝트에서 `profile` 이 clone 선결에 걸려 「막힘」 → 러너 없는
  단계라 `onboard --confirm` 이 **시작부터 거절** → 클론 못 함 → 판정 못 함. `#650` 이 이미 클론된
  NS 에 들어와 아무도 못 봤다. 실행 전에 코드를 읽다 잡았다.
- **검색 태그를 8103 호출자만 안 실었다** — NS 체크아웃도 늘 마운트를 검색했다. 이제 비마운트
  UE 태그는 남의 결과 대신 `not_mounted` 로 거절된다(실서비스 확인).

## 5. 실물

- Gitea `Sim/KimodoMotion_WebUI` private · HEAD `1c5929d`(GitHub 과 같다)
- `.33` `C:\Users\USER\Documents\KimodoMotion_WebUI` — 마스터 SSH 가 관리자라 `.git` 이
  `Administrators` 소유로 생겼다 → `icacls /setowner` 137 파일, 남은 0
- 온보딩: hook·clone(서브모듈 한 단계, `ggml` 빈 디렉토리 확인)·guard 완료 · profile 완료 ·
  conventions **[해당 없음]** · graph 클래스 42 · 메서드 53 · 의존 98
- 합성(마운트 전환 뒤 재개): **89 중 86** · LLM 실패 0 · 사실 게이트 거부 3(`src/sequence` ·
  `tests/multiprompt_fixture_parity` · `tests/root_parity` — 파서가 `mat`·`error`·`weights` 를 클래스로
  뽑은 것으로 보임, **미처리**) · 형식 거부 1(재시도로 통과)
- 색인: 벡터 86 · 워터마크 `1c5929d` — [주의] 합성 86/89 인데 워터마크가 찍혔다(`#274` 와 맞는지 미확인)
- `.33` 배달: `git status` 빈 출력 · 루트 CLAUDE.md·AGENTS.md 에 AX 블록 없음 · `.mcp.json` 그대로
- 🔴 **check FAIL 1회 — 내 결함**: 로컬 스코프 대조가 PowerShell `mcpServers.ax-client` 를 따옴표 없이 써
  `-client` 가 빼기로 파싱돼 통째로 죽었다(등록은 돼 있었다). 가짜 SSH 유닛은 못 봤다 → 따옴표 +
  명령 문자열을 고정하는 테스트. 배달 요약에 등록 줄이 빠진 것도 고쳤다

## 6. 남은 것 — 🔴 2026-09-30 에 처리했다 → [리포트 77](77-kimodo-followups-and-shadow-skill.md)

- ~~Kimodo 사실 게이트 거부 3건~~ — 4건이었고 파서 오인이 아니었다 · `d628aef`
- ~~워터마크 판정(`#274`)~~ — 위반이었다(온보딩 경로) · `a168340`
- ~~NS 고아 문서 9건 · NS 스풀 6건 · `.2` `AxWorker_NS` 헛돎~~ — 아카이브 · 삭제 · 재마운트로 해소
- 따라잡기(주기) 경로의 비마운트 처리는 이제 규칙과 일치(마운트만) — 추가 작업 없음
- `#694` kimodo 따라가기 스크립트+스킬 — **미착수**(커밋 기준 사람 결정 대기)
- ~~CLAUDE.md 두 곳 「AX 는 ModularStage」~~ — `a7241c6`
- GitHub `Test_KimodoMotion` 과 Gitea 가 갈라질 수 있다 — 어느 쪽에서 커밋할지는 **사람 결정**

## 7. 후속 (2026-09-29 00:35~01:00)

- **웹 UI 문서 탭 검색 실패** (사용자 보고): 8103 이 빈 색인을 한 번 검색한 뒤 다른 프로세스가 첫 색인을
  만들면 빈 Chroma 캐시를 계속 써서 `hnsw segment reader: Nothing found on disk`. 임시 트윈으로 재현
  (빈 색인 선검색 → 실패 · 검색 없이 첫 색인 → 정상 · 색인 있는 상태의 재색인 → 정상). **이번엔 내
  확인용 검색(00:04)이 그 순서를 만들었다.** → `3fcbf27`: 그 경로의 캐시 키만 빼고 다시 열어 한 번
  재시도 · 실물 테스트 `test_stale_index`(옛 코드에서 실패 확인)
- **웹 UI 「전문 보기」** (사용자 요청 · 공개로 결정): `02519ef` — `GET /api/v1/context/doc`(context/*.md 한정 ·
  탈출 400 실측) + 검색 결과·문서 목록 버튼 → 모달. 사용자 브라우저 확인 완료
