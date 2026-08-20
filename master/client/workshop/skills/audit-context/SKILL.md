---
name: audit-context
description: `.claude/context/` 의 RAG 컨텍스트 MD 들을 일괄 진단·복구한다. σ.7 펜스 wrap·구 dir-단위 잔재·orphan stem 좀비 MD 등 누적된 손상을 8 카테고리로 분류 후 자동 복구 가능한 것 (pence_wrapped / natural_prefix) 만 즉시 strip 처리. 사용자 자연어 발화 "컨텍스트 손상 검사", "RAG MD 진단", "컨텍스트 일괄 복구" 등에 자동 발동. 빈 컨텍스트 MD 가 도메인 source 로 박혀 RAG 신뢰성을 흔드는 상황을 한 번에 정리하는 운영 도구.
---

# Audit Context — RAG 컨텍스트 MD 일괄 진단·복구

## 목적

`.claude/context/` 의 컨텍스트 MD 가 다음 원인으로 손상될 수 있다:

- **σ.7 펜스 wrap** — LLM 응답이 ` ```markdown ... ``` ` 으로 감싸진 채 저장됨 (frontmatter 매치 실패 → RAG 가 본문 못 읽음)
- **σ.7 자연어 도입부** — "두 작업을 수행한 결과입니다." 같은 텍스트가 frontmatter 앞에 붙음
- **shell only** — frontmatter shell (`---\ntags:[]\n---`) 만 있고 본문 없음 — 첫 부트스트랩 시 LLM 응답 결함
- **dir_named** — 구 dir-단위 컨텍스트 시절의 디렉토리명 MD 잔재
- **orphan_stem** — 코드 리팩토링으로 .h/.cpp 가 사라졌는데 MD 만 남은 좀비

본 스킬이 한 번에 진단 + 자동 복구 가능한 것만 정리한다.

## 호출 방법

사용자 발화:
- `/audit-context` — 진단만 (read-only)
- `/audit-context --repair` — 진단 + 자동 복구 (pence_wrapped + natural_prefix strip)
- `/audit-context --repair --archive-dir-named --archive-orphan` — 위 + dir_named / orphan_stem archive
- `/audit-context --regenerate` — `shell_only` (+ `empty_summary` / `no_frontmatter`) LLM 재생성 큐 등록 (다음 폴링에서 처리)
- `/audit-context --repair --regenerate` — 안전 strip + 재생성 큐 동시 등록 (한 번에 정리)
- `/audit-context --diagnose-post-unwrap` — σ.9.0 분기 진단 (펜스 복구 후 잔존 빈 파일을 source 활동 기준 4 카테고리로 재분류)

자연어 트리거도 허용:
- "컨텍스트 MD 손상 검사해줘"
- "RAG MD 일괄 진단"
- "빈 컨텍스트 정리"
- "shell_only 도 재생성해줘"
- "모두 재생성 트리거"
- "GlobalEventSystem.md 같이 비어있는 거 다 찾아줘"
- "σ.9.0 분기 진단 실행"
- "펜스 복구 후 빈 파일 source 활동 기준 분석"

## 진행 절차

### Step 1 — 진단 (read-only, 항상 시작점)

`context_search` MCP 의 `audit_context_md(project_root=".")` 도구 호출. 8 카테고리 분포 리포트가 반환됨:

| 카테고리 | 의미 | 자동 복구 가능 |
|---|---|---|
| `valid` | frontmatter + 본문 ≥ 50 chars + ## 요약 섹션 | — |
| `pence_wrapped` | ` ```markdown ``` ` 펜스 wrap (σ.7) | ✓ strip |
| `natural_prefix` | frontmatter 앞 자연어 도입부 (σ.7) | ✓ strip |
| `shell_only` | frontmatter shell 만 | ✗ LLM 재생성 필요 |
| `empty_summary` | 본문 있으나 `## 요약` 없음 | ✗ LLM 재생성 필요 |
| `no_frontmatter` | `^---` 미시작 | ✗ LLM 재생성 필요 |
| `dir_named` | 디렉토리 옆 같은 이름 MD (구 dir-단위 흔적) | ✓ archive 가능 |
| `orphan_stem` | 대응 소스 .h/.cpp/.cs/.py 부재 | ✓ archive 가능 |

리포트를 사용자에게 그대로 보여준다 (Markdown 그대로 — 정렬·요약 임의 생성 X).

### Step 2 — 사용자 의사결정 (AskUserQuestion)

진단 결과에 자동 복구 가능 항목이 있으면 사용자에게 확인:

```
다음 선택지 중 하나:
  1. 진단만 — 변경 없이 종료 (이 상태로 OK)
  2. 안전 복구만 — pence_wrapped + natural_prefix strip (LLM 비용 0)
  3. 안전 복구 + dir_named archive
  4. 안전 복구 + dir_named archive + orphan archive (전체 정리)
  5. shell_only 도 LLM 재생성 (비용 발생, 다음 폴링에서 처리)
  6. Dry-run — 시뮬레이션만 (실 파일 변경 없이 결과 확인)
```

자동 복구 가능 항목이 0건이면 안내만. `shell_only` / `empty_summary` / `no_frontmatter` 는 본 스킬 5번 옵션 (`regenerate_shell_only` MCP 도구 호출) 으로 별도 처리. 큐 등록 후 watch.exe 폴링 사이클이 실제 LLM 호출.

### Step 3 — 복구 실행

`context_search` MCP 의 `repair_context_md` / `regenerate_shell_only` 도구 호출. Args:

- `--repair` 단독 → `repair_context_md(archive_dir_named=False, archive_orphan=False)`
- `--archive-dir-named` 포함 → `archive_dir_named=True`
- `--archive-orphan` 포함 → `archive_orphan=True`
- `--regenerate` 포함 → `regenerate_shell_only()` 추가 호출 (큐 등록)
- 사용자가 6 (Dry-run) 선택 → 두 함수 모두 `dry_run=True`

응답을 그대로 사용자에게 보여준다 (진단 + 복구 + 재생성 큐 등록 섹션).

`--regenerate` 호출 시 큐 파일 `.claude/_regenerate_queue.jsonl` 이 작성됨. **실제 LLM 재생성은 다음 watch.exe 폴링 사이클 (최대 60초) 에서 자동 수행**. 진행 상황은 `watch_YYYY-MM-DD.log` 의 `[재생성]` 라인으로 추적.

### Step 4 — 결과 확인 + 사후 작업 안내

복구 후 stats 확인:

- `stripped` > 0 → 다음 watch 폴링 사이클에서 벡터 인덱스 자동 갱신 (변경 파일 감지 X — 본 도구가 직접 파일을 수정한 거라 git 커밋 없으면 인덱스 갱신 안 됨. 인덱스 강제 재구축 필요할 수 있음)
- `dir_named_archived` / `orphan_archived` > 0 → 인덱스에서 해당 MD 가 사라져야 함. `rebuild_index` 도구 호출 안내 또는 자동 호출

남은 `shell_only` / `empty_summary` / `no_frontmatter` 가 있으면:

> "남은 N건은 LLM 재생성이 필요합니다. 다음 git 커밋 사이클에서 해당 파일이 변경되면 자연 회복됩니다. 즉시 처리하려면 별도 LLM 재생성 트랙이 필요합니다 (현재 본 스킬 범위 밖)."

## BLOCKING — 호출 금지 사항

- **단일 파일만 보고 싶을 때** — `Read` 도구 직접 사용
- **검색 결과가 비어있는 원인 분석** — `combined_search` + 결과 비교가 더 정확
- **도메인 자동 승급 문제** — Phase σ.10 영역 (별개 트랙)
- **사용자가 코드 변경 요청** — 본 스킬은 RAG MD 만 다룸, 소스 코드는 무변경

## 운영 환경 권장

- **첫 가동 후 1회** — 누적 손상 일제 정리 (예상 50%+ 손상률)
- **분기 1회 점검** — `--audit-context` 진단만 실행해 분포 추세 관찰
- **σ.7 신규 발생 감지** — watch.exe 의 `[WARN] frontmatter 누락` 로그 빈도가 높아지면 즉시 진단

## σ.9.0 분기 진단 (선택)

`--diagnose-post-unwrap` 옵션 또는 자연어 트리거 시 다음 흐름:

1. `context_search` MCP 의 `diagnose_post_unwrap(project_root, recent_days=30)` 호출
2. `shell_only` + `empty_summary` 카테고리를 source 활동 기준으로 재분류:
   - `recent_but_empty` — source 가 30일 이내 변경 → **Level 5 silent failure** (σ.9-B 대상)
   - `old_inactive` — source 가 오래 변경 없음 → σ.8 트리거 정책 정상 산물
   - `orphan_md` — source 파일 자체 없음 → **좀비 MD** (σ.9-C 대상, git 이력 추적 필요)
   - `no_source_link` — frontmatter 에 source 링크 없음
3. 분기 판정 (D-a / D-b / D-c / D-b+D-c) + 다음 단계 가이드 출력
4. 산출물 자동 저장: `.claude/reviews/_silent_failure/post_unwrap_diagnosis.md`

판정 결과를 사용자에게 그대로 보여주고, σ.9-B / σ.9-C 진행 여부는 사용자 의사결정 (본 스킬 범위 밖).

## 관련 도구

- `audit_context_md(project_root)` — read-only 진단
- `repair_context_md(project_root, archive_dir_named, archive_orphan, dry_run)` — 자동 복구
- `regenerate_shell_only(project_root, ...)` — shell_only LLM 재생성 큐 등록
- `diagnose_post_unwrap(project_root, recent_days, write_report)` — σ.9.0 분기 진단
- HTTP 엔드포인트 (서버 모드): `/api/v1/audit/context` / `/api/v1/repair/context` / `/api/v1/regenerate/shell_only` / `/api/v1/diagnose/post_unwrap`
