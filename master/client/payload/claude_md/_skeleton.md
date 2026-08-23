# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

{PROJECT_LINE}

## Where you are, and what you can do here

[중요] **This body is machine-neutral on purpose.** What *this* machine can do — the checkout path,
whether UE5 is installed, which backends exist — is in the **AX managed block at the end of this
file**, generated per machine by the master. Read that before assuming you can build.

- `/CLAUDE.md` and `/.claude/` are **gitignored**, so this file is local to each checkout and never
  gets committed. Don't "fix" that by un-ignoring it.
- Push to the source repo is disabled on non-authoring checkouts. Work on
  `attempt/<task_id>/<workshop>/<ts>` branches; never push `main`.

## Build · modules · targets

[중요] **여기 적지 않는다 — 아래 AX 관리 블록에 있다.** 그 값(`.uproject`·타깃·모듈·빌드 명령)은
소스 트리 실측이고 **매 배달마다 마스터가 갱신한다.** 본문에 적으면 첫 배달 때 한 번 쓰이고
늙는다(파일이 있으면 병합이 본문을 건드리지 않는다 — 사람이 쓴 것을 지키는 규약).

{CONVENTIONS}

## [중요] What this file does **not** say yet

이 문서의 프로젝트 서술은 **실측된 것만** 담고 있다 — `.uproject`·`*.Target.cs`·`*.Build.cs` 에서
읽은 값이다. 아래는 **아직 비어 있고, 비어 있다는 것이 사실이다**:

- 이 프로젝트가 **왜 존재하는가** (핵심 시스템·설계 의도)
- 도메인 지도, include 규약, 하지 말아야 할 것들의 근거

[주의] **그것을 추측으로 채우지 말 것.** 매 세션 읽히는 문서이므로 틀린 서술은 코드가 덜 된 것보다
비싸다(`docs/12` §12.4). 채우는 경로는 둘이다 — 마스터의 `/init`(LLM, 비용 있음) 또는 사람이
`<트윈>/claude_md.md` 에 적는 것. 어느 쪽이든 **마스터가 배달한다**: 이 체크아웃에서 관리하지 않는다.
