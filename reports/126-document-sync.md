# 126 · 등록 운영 문서 최신화 — #838 1차 구현·실증

## 범위와 승인

사용자가 #838 착수와 로컬 Codex 서브 에이전트 방식을 선택했다. 앞선 #837 문서 5파일은
`16d6b16`으로 커밋했다. #838 구현은 이 보고서 작성 시점에 미커밋이며 푸시·배포하지 않았다.
기존 운영 CLAUDE·AGENTS의 수정안 적용이나 신규 코드 커밋은 이번 구현 지시와 구분한다.

RAG 검색 후 검색 문서 본문과 `context_synth/prompt.py`·`synth.py`, `work/usage.py`,
`layer2_verify.py`의 실제 호출 계약을 대조했다. 기존 RAG 요약 프롬프트를 운영 지침에 그대로
쓰지 않고, 문서별 역할·기존 지침·명시 근거에 맞춘 수정안 생성 모듈로 분리했다.

## 구현

- `master/doc_sync/registry.py`: 명시 JSON 목록과 문서·근거 수집. 정본 경계·중복·UTF-8·크기·보호 문서를 검사하고 원문/해시를 보존한다. symlink는 저장소 내 정본을 향하는 명시 등록만 허용한다.
- `master/doc_sync/draft.py`: 이유·실제 근거 인용·전체 본문 또는 정확한 부분 교체를 받아 diff를 조립한다. 첫 구현은 Codex만 지원하며 공용 `call_codex_why(workdir=...)`로 빈 임시 디렉토리·read-only 실행을 강제한다. 기존 사용량 파서·기록기를 재사용하고 암묵적 폴백/재시도는 없다.
- `master/doc_sync/apply.py`: 현재 등록목록·본문·근거를 재검증하고, 기본은 읽기 전용 미리보기다. `--confirm --approve <id>`의 명시 범위만 적용한다. 보호 지침은 별도 `--allow-protected`도 필요하다. marker·새 깨진 파일 링크·잘못된 인용·오래된 입력을 거부한다. 정본/모드 보존·원자 교체·적용 실패 복구·이미 적용한 내용 재작성 방지를 구현했다.
- `master/doc_sync/__main__.py`: `plan` / `draft` / `apply` CLI. 생성 수정안은 기존 파일을 덮지 않으며 자동 커밋·배포·재기동은 없다.
- `docs/document-registry.json`: README·모듈 안내·온보딩·저장소 CLAUDE/AGENTS·홈 지침 정본·인수인계서 8개 초기 등록. 실제 `plan`에서 정본·역할·보호값을 확인했다. 목록은 명시적으로 확장할 수 있다.
- 사용법: `docs/document-sync.md`. README와 모듈 색인에도 연결했다. 로컬 에이전트 3개가 등록/생성/적용 모듈을 분담했고 부모가 CLI·설정·연결 검사를 구현했다.

## 검증

신규 직접 실행: 등록 6·생성 9·적용 9·CLI 5, 합계 **29/29**. pyflakes 경고0 및
`git diff --check` 통과. 공식 통합 목록에 네 검사 파일을 추가하고 **178/178 rc0** 확인.
공식 통합 실행 중 실제 호출 격리 계약을 보완했고, 보완된 생성/CLI 검사 14건과 pyflakes도
별도로 재실행해 통과했다. 기본 분산 프로필은 `kind=code`, 공식 목록 기반 검사다.

## 실제 Codex 드라이런

`/tmp/ax-838-live-7wu00v19/`에 `HEAD:README.md` 사본과 신규 CLI 소스의 실제 파일 사본을 준비했다.
사본 registry의 요구는 현재 CLI에 근거한 운영 문서 최신화 사용법 추가였다.

1. 실제 `master.doc_sync draft --root <사본> --registry registry.json --project AXCluster --id readme --lane codex` 실행. 공용 도구 로그에 별도 임시 작업 디렉토리와 read-only가 나타났다.
2. 실제 Codex가 근거 인용과 부분 교체 수정안을 반환했다. `proposal.json`의 diff는 기존 내용을 보존하고 `plan/draft/apply` 사용법 7줄을 추가한다. 근거 10개는 제공한 CLI 소스의 실제 줄 범위이며 호출 옵션·역할을 대조했다. 생성 명령 예시는 사용자의 `AX_PROJECTS_ROOT` 설정도 필요하므로 실제 사용법 문서는 환경변수 접두를 명시한다.
3. apply 미리보기 rc0·원본 불변 → 사본에 `--confirm --approve readme` 적용 rc0·changed=[readme] → 동일 수정안 재적용 rc0·changed=[]·unchanged=[readme]. 운영 원본 문서는 이 도구로 수정하지 않았다.
4. 실제 AXCluster `usage_log.jsonl`에 source=doc-sync 한 건, rc0, lane=codex를 되읽었다. 입력 28,303·출력 428·캐시 읽기 12,288, cost_known=false(무료라는 뜻이 아님), session_id `01a159f4-82b8-7f40-a5d8-4e2c9e16f224`.

## 현재 한계와 다음 단계

경로·해시·형식·근거 줄 범위 검사는 내용의 의미나 사용자 정책의 정확성을 증명하지 않는다.
기본 목록이 실제 최신 Redmine/배포 정보를 스스로 수집하지는 않는다. 해당 최신 근거를 등록 입력에
준비해야 하며, 없으면 모델이 상태를 추정해서 채우지 않도록 명시했다. 첫 레인은 Codex이며 다른
모델로 자동 전환하지 않는다. 실제 보호 지침의 변경은 diff 검토와 별도 사용자 동의 뒤 적용한다.

#838은 구현·검증 근거를 기록하고 진행 상태로 유지한다. 이후 사용자 「응 커밋하자」로 신규16파일
커밋이 승인됐다. 실제 커밋은 Git 기록으로 확인한다. 현재는 CLI 구현이며 스킬·MCP 연결은 없다.
「문서 최신화 해」 자연어 경로 실증에는 해당 연결을 먼저 추가해야 하며, 현재 CLI만 사용할 때는
서버 재기동이 필요 없다. 연결 구현과 푸시·배포는 이번 질문과 구분한다.
#837의 RAG 운영은 계속 실사용 로그 수집 단계다.
