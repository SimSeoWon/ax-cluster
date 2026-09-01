# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`NS` is an Unreal Engine 5.8 project. [주의] **왜 존재하는가는 아직 이 문서에 없다** — 아래
「What this file does **not** say yet」 절을 볼 것. 규약은 확정됐고, 프로젝트 서술은 비어 있다.

## Where you are, and what you can do here

[중요] **This body is machine-neutral on purpose.** What *this* machine can do — the checkout path,
whether UE5 is installed, which backends exist — is in the **AX managed block at the end of this
file**, generated per machine by the master. Read that before assuming you can build.

- [중요] **게임 소스는 고치기 전에 계획을 말하고 동의를 받는다** (원전 1조 · `docs/11`).
  대상은 `Source/**` · `*.uproject` · `Config/*.ini` · `Content/**` 이고 **빌드·에디터 실행도
  그 뒤**다. 읽기·검색·계획 제시는 자유다 — 막는 것은 **쓰기**다.
  [주의] 「단일 클래스·미세 수정」은 *어디서* 처리할지의 기준이지 *동의가 필요한지*의 기준이
  **아니다**(실측 2026-08-24: 그 둘을 섞어 `.uproject` 를 동의 없이 고치고 빌드까지 갔다 —
  `#298`).
- `/CLAUDE.md` and `/.claude/` are **gitignored**, so this file is local to each checkout and never
  gets committed. Don't "fix" that by un-ignoring it.
  [중요] 그래서 **정본은 이 파일이 아니다** — `ax-cluster` 의
  `master/client/payload/claude_md/NS.md` 가 정본이고 git 이 관리한다. 이 체크아웃의 사본을
  고쳐도 다음 배달에 덮이지 않지만(파일이 있으면 병합이 본문을 건드리지 않는다) **다른 기계에는
  가지 않는다.** 규약을 바꾸려면 정본을 고친다.
- Push to the source repo is disabled on non-authoring checkouts. Never push `main`.

## Build · modules · targets

[중요] **여기 적지 않는다 — 아래 AX 관리 블록에 있다.** 그 값(`.uproject`·타깃·모듈·빌드 명령)은
소스 트리 실측이고 **매 배달마다 마스터가 갱신한다.** 본문에 적으면 첫 배달 때 한 번 쓰이고
늙는다(파일이 있으면 병합이 본문을 건드리지 않는다 — 사람이 쓴 것을 지키는 규약).

## Code conventions

[중요] **이것은 결정이지 실측이 아니다** (사용자 확정 2026-09-01). 현재 소스가 어떻게 생겼는지와
무관하게 **지켜야 하는 것**이다 — `NS` 는 에픽 템플릿에서 출발했으므로 기존 코드가 이 규약을
따르지 않는 곳이 있다. 그럴 때 **기존 코드를 기준으로 삼지 말고 이 절을 기준으로 삼는다.**
- **주석은 한국어로 쓴다.** 설계 의도는 `// [DOC]` 블록에 남긴다 — 구현 후에도 보존되는
  태그다(`[PSEUDO]`/`[IMPL]` 은 구현하면 지워진다).
- 헤더의 모든 `UPROPERTY` 객체 참조는 `TObjectPtr<T>`. 생 포인터는 지역 변수만.
- `X != nullptr` 대신 `IsValid(X)`. `Cast<T>` 결과를 바로 검사 — `IsA()` 후 `Cast` 금지.
- IWYU: `.h` 는 전방선언, `include` 는 `.cpp` 에.
- `FTimerHandle` 은 항상 멤버, 지역 변수 금지. 복제 컴포넌트는 생성자에서
  `CreateDefaultSubobject` — `BeginPlay` 의 `NewObject` 금지.
- 정적 데이터는 `UDataTable` / `UPrimaryDataAsset`. C++ 매직넘버 금지 —
  `UPROPERTY(EditDefaultsOnly)` 로 노출한다.
- 접두사: `A` 액터 · `U` UObject/컴포넌트/서브시스템 · `F` 구조체 · `E` 열거형 · `I` 인터페이스.

## 규약 이력 (사람용 — 워커에게 가지 않는다)

[중요] 이 절 이름은 `work/conventions.WANTED_SECTIONS` 밖이므로 **매니페스트에 실리지 않는다.**
이력을 규약 절에 두면 그 문장이 워커 프롬프트로 그대로 나가고, 부정문·인용문이 지시로 오독될 수
있다(*"주석은 영문"* 이라는 문자열이 프롬프트에 남는 것 자체가 함정이다).

- **2026-08-24** 온보딩이 정본 없이 돌아 `## Code conventions` 가 **골격+실측**으로 채워졌다.
  그 값이 *"한글 주석 0개 → 주석은 영어다"* 였고(`NS` 는 에픽 템플릿이라 사실은 맞다),
  `WANTED_SECTIONS` 가 그것을 SSOT 로 읽어 워커 매니페스트에 실었다.
- **2026-09-01** 첫 실전 파견에서 그 값이 골조 계약(한국어 주석)과 **정면으로 충돌**했다.
  사용자 지적으로 셋을 고쳤다 — 생성기가 실측을 규약 절에 넣지 않게(`client/bundle.py`),
  온보딩 판정이 **정본에서 왔는지**까지 재게(`projects/onboard.py`), 그리고 정본이 있으면
  미러의 규약 절을 정본에서 갱신하게. 이 파일이 그 정본이다.

## [중요] What this file does **not** say yet

규약(위 절)은 확정됐다. 그러나 이 문서의 **프로젝트 서술**은 아직 비어 있고, **비어 있다는 것이
사실이다**:

- 이 프로젝트가 **왜 존재하는가** (핵심 시스템·설계 의도)
- 도메인 지도, 어느 전방선언이 의도된 것인지, 하지 말아야 할 것들의 근거

[주의] **그것을 추측으로 채우지 말 것.** 매 세션 읽히는 문서이므로 틀린 서술은 코드가 덜 된 것보다
비싸다(`docs/12` §12.4). 채우는 경로는 둘이다 — 마스터의 `/init`(LLM, 비용 있음) 또는 사람이
정본(`payload/claude_md/NS.md`)에 적는 것. 어느 쪽이든 **마스터가 배달한다**: 이 체크아웃에서
관리하지 않는다.
