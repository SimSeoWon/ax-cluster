# 230 — Codex 워커 티켓 권한 전달과 무착수 종료 처리 (#1065)

사용자는 「진행하자」로 #1065 착수 전 인터뷰를 시작했고, 「워커 계측 진행해」로 워커 계측부터 요청했다. 등록된 AXCluster 워커에서 계측 시나리오를 실행하고 #1062 전체 재발주는 별도 범위로 잡았다.

- `issue_start_tool` 응답은 `ok=true`, `repo=/home/sim/ax-cluster/.ax-issues/1065`, `branch=issue/1065`, `start_rev=a3350bb002f6d93d4a33c9ab37e2ee72ccf61c71`, `already=false`, `lock=acquired`였다.
- 세션은 `~/.codex/sessions/2026/11/28/rollout-2026-11-28T22-21-50-01a22251-b645-7c71-b8d3-1976f4bc725b.jsonl`이다.

## 수정 전 실측

`AXCluster/config.yaml`의 `workshops` 경로를 사용했다. .43은 `/home/sim/trunk/AXCluster`의 SSH, .2는 `C:\trunk\AXCluster`의 `AxConductor_AXCluster` 로그인 런처다. 두 프로젝트 로컬 `.codex/config.toml`에서 `ax-client=1 env_vars=0 grant_on_env_vars_line=0`이 나왔다.

원래 #1062 발주에서 양쪽 원본 로그에 「노드 일감 발주 권한이 없다」가 있었다. .43 rollout `01a2224c-467e-72c0-94f8-fc2f68f32ba5`에서 6줄, .2 요청 `b9a430bac2e14d9d9249b24d64d444c8`의 `out.txt`에서 4행이 일치했다. .2의 `rc.txt`는 0이었다. 착수·제출 기록은 0건이었고 Redmine에는 검수 대기 노트가 남았다.

운영 리비전의 `bundle.workshops("AXCluster")` → `bundle.probe(*registration)` → `runner.run_node_ticket`을 두 워커에서 실행했다. 번호는 #1065, 모드는 codex, 제한 130초, 테스트 입력은 서명 없는 비밀 아닌 값이다. 큐·배정 등록 없이 기존 시작 경로만 실행했다.

| 워커 | 진단 ID | 결과 |
|---|---|---|
| .43 | `0a485016d2584a79b9845b8368955bfd` | Codex 0.159.3, rc0, 종료 확인, `wayfinder_get_node_ticket`의 환경변수 누락 오류 |
| .2 | `99c9412585f84077a82929204991715f` | Codex 0.159.3, SessionId 1, 회수 41초, rc0, 종료 확인, 같은 오류 |

두 MCP 도구 응답의 오류는 「노드 일감 발주 권한이 없다 — 마스터에서 배정을 확인한다」이다. 이는 `client_mcp.py`에서 `AX_NODE_TICKET_GRANT`가 비었을 때 HTTP 호출 전에 반환된다. Linux는 SSH stdin을 읽고 환경으로 내보낸 뒤 Codex를 시작한다. Windows 런처는 비어 있지 않은 권한 파일을 읽고 환경에 넣은 뒤 Codex를 시작한다. 따라서 누락 지점은 Codex 실행 환경에서 stdio MCP 자식으로 넘어가는 경계와 일치한다. 수정 전 워커 실측에는 기존 배달물과 도구 응답을 사용했다. 새 계측 로그는 로컬에서 검증했다.

## 변경

`55ea644`로 T1~T3을 구현했다.

- Linux SSH 런처·Windows 예약 런처·stdio MCP에 배정 ID 및 권한 유무를 기록한다. MCP는 권한과 별개로 전달된 배정 ID를 사용해 권한 누락도 같은 실행과 연결한다.
- AXCluster Codex 워커의 프로젝트 로컬 `ax-client`에 `env_vars = ["AX_NODE_TICKET_GRANT"]`를 생성하고 배달 직후 Codex의 되읽기 결과에서 이름을 확인한다. 요청자·다른 프로젝트는 기존 설정을 사용한다.
- 종료를 확인한 현재 배정은 잠금 안에서 서버 착수 기록을 확인한다. 무착수 종료는 rc0이어도 사유를 남기고 재작업 대기, 착수한 배정은 검수 대기다. 종료 미확인은 실행 중이며 이전 배정의 늦은 종료는 새 배정을 변경할 수 없다.

## 검사

작업 트리에서 `AX_PROJECTS_ROOT=/home/sim/ax-cluster /home/sim/ax-cluster/.venv/bin/python -B`로 아래 모듈을 실행했다.

| 명령 | 결과 |
|---|---|
| `-m master.test_client_bundle` | rc0, 673/673 |
| `-m master.test_runner` | rc0, 464/464 |
| `-m master.test_wayfinder` | 수정 전 rc0 267/267, 수정 후 rc0 268/268 |
| `-m master.test_issue_lock` | rc0, 79/79 |
| `-m unittest discover -s tests/integration -p test_axcluster.py -f -v` | rc0, 223/223, 30.175초 |
| `git diff --check` | rc0 |

로컬 `client/runtime/client_mcp.py` 실행에서는 임의 배정 ID를 주고 테스트값 유무를 바꿔 stderr의 `grant=present`와 `grant=missing`을 각각 확인했다. 토큰 값이나 체크아웃 경로는 출력하지 않았다. Codex CLI의 `mcp get --json`에서 전달 목록은 `transport.env_vars`의 문자열 배열이었다.

남은 운영 확인은 마감·배달 뒤 .43과 .2 도구 경로다. 유효한 티켓 조회 성공은 서명 권한과 실행 중 배정이 함께 필요한 서버 조건이다. #1062의 기존 재작업 배정은 별도 재발주에서 실증한다.

최종 결과는 Redmine 마감 노트.
