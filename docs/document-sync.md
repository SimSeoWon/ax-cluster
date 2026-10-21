# 운영 문서 최신화 (#838)

Python이 명시적으로 등록된 문서와 근거를 수집하고, 기존 LLM 호출 경로로 수정안을 받아 검증·적용한다.
README·CLAUDE·AGENTS·온보딩·인수인계서는 각 문서의 역할과 기존 사용자 결정을 보존한다.

## 등록 목록

기본 목록은 [document-registry.json](document-registry.json)이다. 문서별 `id`, `path`, `role`,
`protected`, `instructions`, `evidence`를 명시한다. 자동 검색한 모든 파일을 LLM에 보내지 않는다.
`evidence`는 저장소 안의 실제 파일 목록이다. 최신 검증·Redmine 결과를 반영하려면 해당 근거를
먼저 파일로 준비해 목록에 포함해야 한다. 등록되지 않은 운영 상태를 모델이 추측해서 채우지 않는다.

CLAUDE.md·AGENTS.md 및 홈 진입 문서 정본은 `protected=true`가 필요하다. 홈 심볼릭링크를
등록할 때는 저장소 안 정본을 가리키는 명시적 링크만 허용하며, 쓰기는 정본에 수행해 링크를 유지한다.
비밀 파일·배달 부산물·저장소 밖 정본은 대상이나 근거로 등록할 수 없다. 문서와 근거를 합쳐
500,000자를 넘으면 잘라서 진행하지 않고 오류로 보고한다. 필요한 문서를 `--id`로 선택한다.

## 실행

작업 위치 `/home/sim/ax-cluster`, Python `.venv/bin/python`.
대화형 세션에서는 [`ax-docsync`](../master/skills/ax-docsync/SKILL.md) 스킬(「문서 최신화 해」)이
아래 순서와 사람 승인 지점을 안내한다. 스킬은 같은 CLI를 부를 뿐 별도 경로가 아니다.

```bash
# 등록 문서·정본·역할 확인. LLM 호출과 파일 쓰기 없음
.venv/bin/python -B -m master.doc_sync plan

# 선택한 문서의 수정안 작성. 원본은 바꾸지 않는다
AX_PROJECTS_ROOT=/home/sim/ax-cluster .venv/bin/python -B -m master.doc_sync draft \
  --id readme --project AXCluster --lane codex --out /tmp/ax-doc-proposal.json
# Codex 한도가 없을 때: --lane claude

# 현재 등록·원문·근거와 대조하는 읽기 전용 적용 미리보기
.venv/bin/python -B -m master.doc_sync apply --artifact /tmp/ax-doc-proposal.json

# diff와 근거를 확인하고 승인한 ID만 적용
.venv/bin/python -B -m master.doc_sync apply --artifact /tmp/ax-doc-proposal.json \
  --confirm --approve readme
```

`--root`와 `--registry`로 다른 작업 사본과 등록 파일을 명시할 수 있다. 보호 문서를 실제로 수정할 때는
기존 계획·사람 승인 절차를 먼저 마친 뒤 `--allow-protected`도 명시한다. 이 옵션이 사람의 승인을
대신하지 않는다. 생성 레인은 `codex`(기본)와 `claude`다. 각각 공용 `layer2_verify.call_codex_why`·
`call_claude_why`(도구 `Read,Grep,Glob`)의 임시 작업 디렉토리·읽기 전용 실행과 기존 사용량 파서를 재사용한다.
레인은 사람이 고르며 암묵적 폴백이나 재시도는 하지 않는다. claude 레인이면 쓰는 쪽과 검토하는 세션이
같은 계열일 수 있으므로 사람의 diff 검토가 실제 게이트다.
마운트된 프로젝트의 사용량 로그에 `source=doc-sync`로 성공·실패를 기록한다.
`plan`·`apply`는 프로젝트 마운트를 바꾸지 않는다.

## 커밋 변경으로 영향 문서 찾기 (#839)

`plan`과 `draft`에 `--since <시작 커밋> [--until <종료 커밋>]`을 지정하면 두 커밋 사이의
변경 경로를 등록 문서 정본·`evidence`의 정확한 경로와 대조한다. 종료 기본값은 `HEAD`다.
rename은 이전·이후 경로를 모두 포함하며 삭제 경로도 보존한다. 등록 목록 자체가 변경되면
현재 등록 문서 모두를 후보로 삼는다. `--id`를 함께 주면 그 ID와 영향 후보의 교집합만 수집한다.
범위를 생략하면 기존의 전체 등록 또는 `--id` 선택 동작을 유지한다.

```bash
.venv/bin/python -B -m master.doc_sync plan --since HEAD~1
```

계획·수정안 JSON과 CLI 결과의 `selection`은 확정 커밋 해시·`changed_paths`·`included`·
`excluded`를 담는다. 포함 사유는 `registered-dependency-changed` 또는 `registry-changed`,
제외 사유는 `explicit-id-filter` 또는 `no-registered-dependency-change`다.
`matched_paths`로 대조 근거를 확인한다. 영향 없음으로 제외된 문서는 LLM에 보내지 않으며,
LLM이 읽고 판단한 `decision=unchanged`와 구분한다. Git 범위 조회 실패는 오류로 보고한다.

커밋 범위는 **후보 선택에만** 사용한다. 문서와 근거 본문은 항상 현재 작업 트리에서 읽고 해시를
보존한다. `selection.content_source=current-working-tree`, `content_head`, `working_tree_dirty`로
이를 표시한다. 과거 `--until`을 지정해도 과거 본문을 복원하지 않는다. 미커밋 변경은 변경 경로
탐지에 포함되지 않지만 선택된 문서의 현재 본문에는 포함될 수 있다. 삭제·이동으로 현재 등록된
파일이 없어졌다면 기존 등록 검증에서 오류가 나므로 먼저 등록 관계를 검토해야 한다.
이 탐지는 명시 등록 의존 관계의 후보 추천이며 의미적 영향 전체를 보장하지 않는다.
Redmine·운영 상태 수집과 보호 문서 적용은 기존의 별도 사람 결정·승인 절차를 따른다.

## 수정안과 적용

LLM은 사유와 제공 근거의 `경로:줄번호`, `update`/`unchanged`, 변경 본문 또는 정확한 부분 교체
`edits`를 JSON으로 반환한다. 도구·코드 실행이나 파일 쓰기는 시키지 않는다. Python이 전체 본문과
unified diff를 조립해 수정안 JSON에 보관한다. 기존 출력 파일을 덮지 않는다.

수정안에는 등록 목록·문서·근거의 해시가 포함된다. 적용 직전에 다시 읽어 바뀐 입력과 잘못된 경로를
거절한다. 미등록 문서나 다른 정본으로 수정안을 바꿔 적용할 수 없다. 빈 본문·잘못된 인용·새로 생긴
깨진 로컬 파일 링크와 `AX-ENTRY-MARK` 삭제를 거절한다. 이미 존재했던 깨진 링크는 새 오류와 구분한다.
앵커만 있는 링크와 외부 URL은 파일 존재 검사에서 제외하므로 링크 검사는 문서 내용의 의미 검증을 대신하지 않는다.

문서 전체를 사전 검증한 뒤 승인 문서만 원자적으로 교체하며 파일 모드를 보존한다. 동일 수정안을 다시
적용해 내용이 이미 같으면 재작성하지 않는다. 의미가 맞는지, 지침이 적절한지는 사람이 diff와 근거를
검토해야 한다. 자동 커밋·푸시·배포·서비스 재기동은 수행하지 않는다.
