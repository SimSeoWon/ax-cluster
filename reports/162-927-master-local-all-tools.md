# 162 — #927 마스터 CLI 전체 도구 허용 정책과 생성기 일치

> 2026-11-09 · Codex 지휘 · 로컬 서브 에이전트 구현·독립 검토 · 시작 `fc82297ada17cd0c8f54d7969809096731f54727`

## 사용자 결정과 범위

- 사용자: 「모두 승인하는 것으로 통일해 안티그래비티는 그냥 모든 툴과 MCP 스킬 허용했어」.
- 방식: 「서브 에이전트로 진행하고」. Antigravity는 MCP 109개와 CLI·편집을 허용했다는 사용자 전달을 보존 대상으로 삼았다.
- 이번 수정은 마스터 로컬 Claude·Codex·Antigravity 설정 생성기다. 워커 지휘자 모드·OS 권한·Codex sandbox/approval_policy는 변경하지 않는다.
- 스킬에 별도 허용 키를 발명하지 않는다. 스킬이 사용하는 도구의 승인 정책을 맞춘다.

## 관측과 판정

1. **참 — 기존 승인 손실:** 현재 Codex ax-client approve 17개, 생성기 READ_APPROVE 3개. 기존 관리 블록 전체 교체라 14개가 사라지는 구조였다(`master_local.codex_text`, `apply`).
2. **참 — 검사 기준 불일치:** 기존 check는 approve 집합을 3개와 정확히 비교했다. 현재 17개는 코드상 불통과 조건이다. 변경 전 실제 --check는 실행하지 않았다.
3. **참 — 검사도 옛 정책 고정:** 기존 회귀 검사의 「읽기 셋만 approve」 기대값을 전체 허용 정책으로 바꿨다.
4. **부분 — Antigravity 전면 허용:** 사용자 보고와 기존 설정 보존을 확인 대상으로 삼는다. 이번 작업에서 새 대화 세션의 팝업 0건을 실증했다고 주장하지 않는다.

## 구현

- `all_client_tools()`는 실제 `bundle.client_tool_names()`에서 전체 도구 목록을 얻는다. Codex 기존 approve 항목을 합집합으로 보존하며 두 AX MCP 서버의 `default_tools_approval_mode="approve"`를 기록한다.
- 등록된 ax-projects의 연결·인증 헤더는 보존하고, 승인 override·enabled·enabled_tools/disabled_tools/omit_tools_from만 전체 허용 정책에 맞춘다. 다른 서버·모델·sandbox 설정은 파싱 결과로 보존을 확인한다.
- Claude 사용자 settings.json에는 정식 `permissions.defaultMode="bypassPermissions"`를 병합한다. 기존 hooks·다른 설정은 보존하고 계획·적용·되읽기 검사에 연결했다.
- Antigravity의 기존 allow·mode·model은 보존하면서 전체 ax-client 도구와 기존 기본 CLI 접두사를 더한다. 기존 ax-projects 전수 승인은 제거하지 않는다.
- 대상 소스는 `master/client/master_local.py`, `master/test_client_master_local.py` 두 파일이다.

## 검증 근거

- `issue_start_tool(927)` 응답: `repo="/home/sim/ax-cluster/.ax-issues/927"`, `checkout="/home/sim/ax-cluster"`, `branch="issue/927"`, `start_rev="fc82297ada17cd0c8f54d7969809096731f54727"`, `lock="acquired"`, `author.family="codex"`.
- `sh /tmp/ax-927-checks.sh` **rc0**: `OK test_client_master_local: 109/109 통과`; `git diff --check` rc0; 기존 정본 `pystatic.run_static` 2파일 결과 pyflakes/import/mypy 차단 0·setup_error 없음. mypy 비차단 노트 25건(타입 관련)은 통과 기준과 구분한다.
- `sh /tmp/ax-927-integration.sh` **rc0**: `AX_PROJECTS_ROOT=/home/sim/ax-cluster`, 일감 worktree, 운영 venv로 정본 `python -B -m unittest discover -s tests/integration -p test_axcluster.py -f -v` 실행. **`Ran 191 tests in 203.398s` · `OK`**. Git 그룹 권한 차단을 피하도록 해당 좁은 스크립트만 sandbox 밖에서 실행했다.
- 독립 읽기 검토: 기존 17개·미등재 추가 승인 보존, 멱등, AX MCP 제한 해소, 타 서버·인증 헤더·sandbox 보존, Claude·Antigravity 병합을 대조했고 현재 설정 기준 blocking 지적 없음.
- 적용 전 파일 SHA256: Antigravity settings `f85c631f36256e8368993d6787b02a859ed911a15c33e08bccf905efd0796a3a`; Codex config `ec77c0ba850284faf1efee0040cdc767ddb9477f274ec85e37548a432e96edf9`; Claude settings `ca3d163bab055381827226140568f3bef7eaac187cebd76878e0b63e9e442356`.

## 실패·중단·미확인

- 지원 계약 조사 중 `codex --strict-config -c 'mcp_servers.ax-client.default_tools_approval_mode="approve"' mcp get ax-client --json` **rc1**: `Error: --strict-config is not supported for codex mcp`(원문은 옵션에 백틱 포함). 키 거절이 아닌 하위 명령 옵션 미지원이다. 중단 보고 후 사용자 「응」으로 재개했다.
- 보조 세션 파일 목록 조회가 `aborted before dispatch`로 중단된 때도 작업을 멈추고 사용자 재개를 받았다. 실행 중 검사의 출력 회수도 한 번 dispatch 전 중단됐으나 동일 세션 결과 회수로 실제 검사 rc0를 확인했다.
- 일반 `codex mcp get ax-client --json`은 rc0, 운영 경로 기동 명령·enabled true·enabled_tools/disabled_tools null을 반환했다. `could not create PATH aliases: Read-only file system` 경고는 rc0 조회와 구분한다.
- 실제 master-local 적용은 **main 반영 후 운영 경로에서만** 한다. worktree에서 적용하면 제거될 worktree 경로를 영구 MCP 설정에 넣을 수 있기 때문이다. 이 리포트 시점에는 실제 적용·새 세션 팝업 검증 미실행이며 마감 노트에 결과를 남긴다.
- Claude 검사는 사용자 설정 파일 대조다. managed/project override나 이미 실행 중인 세션의 유효 권한까지 보장하지 않는다. Codex sandbox·OS 승인 계층 역시 별도다.
- 세션 파일: `~/.codex/sessions/2026/11/08/rollout-2026-11-08T22-10-34-01a1bb48-36b4-70b0-b949-37e3453366be.jsonl`.

## 설정 계약 근거

- Codex 공식 config reference: https://developers.openai.com/codex/config-reference/ (조회 시 https://learn.chatgpt.com/docs/config-file/config-reference 로 리디렉션). `default_tools_approval_mode`는 서버 기본값, `tools.<tool>.approval_mode`는 개별 override다.
- Claude 공식 permissions: https://code.claude.com/docs/en/permissions . 로컬 Claude 2.1.319 도움말의 bypassPermissions 및 Codex 0.167.0 도움말을 함께 대조했다.

최종 결과는 Redmine 마감 노트.
