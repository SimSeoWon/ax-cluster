---
name: ax-docsync
description: AX 마스터의 등록된 운영 문서(README·모듈 안내·온보딩 런북·CLAUDE·AGENTS·인수인계서)를 실제 소스 근거로 최신화한다 — `master.doc_sync` 의 plan(목록) → draft(LLM 수정안) → apply(미리보기·승인 적용). "문서 최신화 해", "문서 갱신해", "README 최신화", "운영 문서 맞춰", "/ax-docsync" 같은 발화에 발동. Claude·Codex 공용.
---

# ax-docsync — 운영 문서 최신화

> 정본: `~/ax-cluster/master/skills/ax-docsync/SKILL.md` · 명령 정본 `master/doc_sync/__main__.py`
> 근거: `#838` · 사용법·계약 `docs/document-sync.md` · 등록 목록 `docs/document-registry.json`

## 0. 무엇을 하는가

Python 이 **등록된 문서와 근거 파일만** 모아 Codex 에 수정안을 받고, 해시·인용·링크를 검증한 뒤
**사람이 승인한 문서 ID 만** 적용한다. **명령이 일을 하고, 이 스킬은 순서와 멈출 자리를 정한다.**
등록되지 않은 운영 상태(Redmine·서비스 상태)는 모델이 추측해 채우지 않는다 — 필요하면 근거 파일을
먼저 만들어 등록 목록에 넣는 것이 사람의 결정이다.

작업 위치 `/home/sim/ax-cluster`, Python 은 `.venv/bin/python`. 실행 전 쓸 명령을 사용자에게 알린다.

## 1. 목록 확인 (읽기 전용)

    .venv/bin/python -B -m master.doc_sync plan

- 등록 문서의 `id`·`path`·`role`·`protected` 를 사용자에게 표로 보인다.
- **대상 ID 는 사용자가 고른다.** 발화에 대상이 없으면 묻는다 — 「전부」라고 해도
  `protected=true`(CLAUDE·AGENTS·홈 지침 정본) 는 따로 확인한다.
- 사용자가 말한 문서가 목록에 없으면 멈추고 보고한다. 등록 목록을 임의로 고치지 않는다.

## 2. 수정안 작성 (LLM 호출 · 원본 불변)

    AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -B -m master.doc_sync draft \
      --project <마운트된 프로젝트> --id <id> [--id <id> ...] \
      --out <스크래치패드>/doc-sync-<YYYYMMDD-HHMM>.json

- 상용 호출(Codex)이다 — 문서 수만큼 공용 쿼터를 쓴다는 것을 실행 전에 한 줄로 말한다.
- `--out` 은 **존재하지 않는 새 파일**이어야 한다(덮지 않는다). 프로젝트는 마운트된 것만 받는다.
- 문서마다 수 분이 걸릴 수 있다 — 실행 중에는 단계마다 한 줄씩 진행을 알린다.
- 사용량은 마운트 프로젝트 로그에 `source=doc-sync` 로 남는다. 자동 폴백·재시도는 없다.

## 3. 검토 — 사람 게이트

- 결과 JSON 의 문서별 `decision`·`reason`·`diff` 를 **그대로** 보인다(요약으로 대체하지 않는다).
- diff 의 핵심 주장이 실제 소스와 맞는지 인용 `경로:줄번호` 를 열어 확인하고, 틀린 주장은 지적한다.
- 미리보기(쓰지 않음):

      .venv/bin/python -B -m master.doc_sync apply --artifact <수정안.json>

- 승인 여부를 문서 ID 별로 묻는다. **「응」 같은 짧은 수긍은 물음이 앞에 있었을 때만 승인이다.**

## 4. 적용 (승인한 ID 만)

    .venv/bin/python -B -m master.doc_sync apply --artifact <수정안.json> \
      --confirm --approve <id> [--approve <id> ...]

- 보호 문서는 기존 계획·사람 동의를 마친 뒤에만 `--allow-protected` 를 붙인다 — 이 옵션이 동의를 대신하지 않는다.
- 적용 뒤 `git diff --stat` 으로 바뀐 파일이 승인 목록과 같은지 대조해 보고한다.

## 5. 결과 보고와 하지 않는 것

- rc 와 출력 요약을 전한다. 문서별 update/unchanged 분모를 말한다(「됐다」만 말하지 않는다).
- **실패는 고치는 자리가 아니라 보고하는 자리다.** `[doc-sync] 실패:` 사유(입력 해시 변동·잘못된 인용·
  깨진 링크·출력 파일 존재 등)를 그대로 전하고 갈래를 내고 멈춘다. 코드·등록 목록을 손으로 고치지 않는다.
- 문서 파일을 손으로 편집해 수정안을 대신하지 않는다. 홈 `~/CLAUDE.md` 링크를 일반 파일로 덮지 않는다.
- 커밋·push·배포·서비스 재기동은 이 스킬이 하지 않는다 — 각각 따로 승인받는다.
