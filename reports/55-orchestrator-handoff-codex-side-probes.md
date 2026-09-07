# 55 — 지휘 교대 ① 조사: Codex 쪽 접근 실측

작성: 2026-09-07 · 일감 [#384](http://192.168.0.57:8080/issues/384)
설계: `docs/15-orchestrator-handoff.md` §15.6 ①
대조 대상: `54-orchestrator-handoff-claude-side-survey.md` §54.4의 12항목.

## 결론

이 Codex 세션은 로컬 파일 작업·서브 에이전트 위임을 수행할 수 있고, **샌드박스 밖 실행을
승인받으면** 마스터 서비스 조회·3대 SSH·AX HTTP/MCP 읽기도 가능하다.
기본 샌드박스의 차단을 노드 장애나 Codex 전체의 기능 부재로 판정하면 안 된다.

공용 진입점은 아직 연결하지 않았다. `AGENTS.md` 자동 로드와 시작 고지는 **미실증**이며,
셸에서 MCP를 호출한 것은 Codex의 네이티브 MCP 연결과 다르다. #384를 완료로 닫을 근거는 아니다.

## 55.1 방법과 변경 범위

사용자가 전달한 Claude 조사에 이어 Codex 담당 확인을 수행했다. 서비스 재시작·훅 설치·
워크 등록·추론·게임 빌드·원격 파일 변경 없이 읽기 위주로 측정했다.
인증 값은 출력하지 않고 기존 `~/.config/ax-cluster/token` 및 `master.redmine` 경로로 읽었다.
프로브는 `/tmp/ax-codex-access-probe.py`, `/tmp/ax-codex-mcp-probe.py`에 작성했다.
이 임시 파일은 배포 도구가 아니며 커밋 대상도 아니다.

## 55.2 12항목 판정

| # | 항목 | 이번 세션 결과 | 한계 / 다음 확인 |
|---|---|---|---|
| 1 | AGENTS.md 자동 로드 | `/AGENTS.md`, `/home/AGENTS.md`, `/home/sim/AGENTS.md`, `/home/sim/ax-cluster/AGENTS.md` 모두 없음 | 파일을 만들지 않았으므로 로드 위치 미실증 |
| 2 | 홈·저장소 양쪽 시작 | 이 세션 cwd는 `/home/sim`, 저장소를 지정한 셸 명령 실행 가능 | 셸 cwd 변경은 새 세션 지침 로드 검증이 아님. 두 시작 위치 새 세션 필요 |
| 3 | AX MCP | 승인 후 HTTP initialize → tools/list → tools/call `list_projects_tool` 성공 | 네이티브 연결 미배선. config.toml에 `[mcp_servers]` 없음, 현재 제공 도구에 AX MCP 없음 |
| 4 | SSH 3대 | 승인 후 `.2`·`.33`·`.43` 모두 hostname rc=0 | 기본 샌드박스에서는 세 곳 모두 socket EPERM. 접속 성공은 빌드/원격 쓰기 검증이 아님 |
| 5 | sudo systemctl restart | 승인 후 `sudo -n -l /usr/bin/systemctl restart ax-projects.service` rc=0 | 허용 정책 조회만. 실제 restart는 미실행이며 다른 유닛까지 일반화하지 않음 |
| 6 | sudo ax-install-hook | 승인 후 `sudo -n -l /usr/local/bin/ax-install-hook --apply` rc=0 | 허용 정책만 확인. 실제 설치·온보딩은 미실증 |
| 7 | 훅/자동 고지 | 이번 세션에서 인수인계 자동 고지나 AX 전용 훅 실행 증거 없음 | 도구 전체에 기능이 없다고 단정하지 않음. 진입점 배선 뒤 새 세션 확인 필요 |
| 8 | 서브 에이전트 | `handoff_read_probe` 생성 → 지정 문서 읽기 → 세 가지 근거와 결과 회수 성공 | 읽기 전용 1건. 병렬 파일 수정·도구 간 실행 ID 승계는 검증하지 않음 |
| 9 | HTTP 4포트 | 승인 후 8080/login=200, 8101/api/v1/health=200, 8102/health=200, 8103/mcp 무인증=401·인증 MCP 성공 | 기본 샌드박스에서는 네 곳 모두 EPERM. 401은 서버 다운이 아니라 인증 거절 |
| 10 | Python 모듈 | `.venv/bin/python` import 성공, `-m master.task_queue --status /tmp/ax-codex-empty-queue-probe` rc=0 | 임시 빈 큐에서 실행. 운영 큐 파일을 직접 열지 않음 |
| 11 | 긴 실행·출력 회수 | 3초 프로브를 1초 yield로 실행, session_id 반환 후 write_stdin으로 종료 출력·rc=0 회수 | 같은 세션 안의 출력 회수만. 앱 종료/지휘 교대 후 생존·재접속은 미실증 |
| 12 | 승인 모델 | 셸의 `require_escalated` 승인 후 동일 읽기 프로브 통과 | Claude allow 목록을 그대로 쓸 수 없음. 승인은 명령/접두 규칙 단위이며 셸 연산자로 나뉜 명령도 각각 심사 |

## 55.3 실제 응답

기본 샌드박스:

```text
systemctl: Failed to connect to bus: Operation not permitted
HTTP:      <urlopen error [Errno 1] Operation not permitted>
SSH:       socket: Operation not permitted
sudo:      The "no new privileges" flag is set
```

승인 후:

```text
ax-task-queue.service active
ax-broker.service     active
ax-projects.service   active
ax-indexer.path       active
ax-dispatch.path      active

janus@192.168.0.2  hostname → DESKTOP-HV0I6DL
user@192.168.0.33  hostname → DESKTOP-FU2GNGL
sim@192.168.0.43   hostname → fedora

MCP initialize → serverInfo.name=ax-projects
tools/list → 33 tools
tools/call list_projects_tool → rpc_error=null, isError=false, content_blocks=1
```

BC-250은 최근 종료 기록이 있지만 이번에는 접속됐다. 과거 종료 기록만으로 현재도 꺼져 있다고 판단하지 않는다.

## 55.4 리포트 54에 대한 보충

1. 실제 파일명은 `54-orchestrator-handoff-claude-side-survey.md`다.
   전달문의 축약명 `54-ore-survey.md`는 없었다.
2. MCP tools/list 실측은 **33종**으로, 54의 35종과 다르다. 비교 시점의 코드/설정/공개 조건을
   전수 대조하지 않아 차이의 원인은 미판정이다. 이번 세션에서 받은 결과를 기록한다.
3. `.codex/memories_1.sqlite`의 존재만으로 기억 자동 로드 계약이 확인되지는 않는다.
   이번 조사에서는 내용을 읽지 않았고 공용 기억이나 자동 이식 대상으로 사용하지 않는다.
4. AGENTS.md는 55.2의 후보 4곳을 확인했다. 홈 전체에 없다는 주장으로 일반화하지 않는다.

## 55.5 ②로 넘길 사항

- Claude가 공용 규칙/인수인계 기록을 만들 때 기본 샌드박스 차단과 승인 후 성공을 함께 적는다.
- 상태 스냅샷에만 의존할 필요는 없다. 승인 후 현재 상태를 조회할 수 있다.
  다만 실행 중 프로세스/로그/대상 파일은 따로 기록하고 새 세션에서 다시 대조한다.
- 시작 시 공용 문서를 읽는 진입점은 미연결이다. 후보 파일을 만든 뒤 홈/저장소의
  **실제 새 세션**으로 검증한다. 자식 에이전트나 셸 cwd 변경으로 대신하지 않는다.
- MCP 설정 변경과 재접속은 ② 구현으로 다룬다. 이번 HTTP 호출을 네이티브 연결 완료로 적지 않는다.
- 서브 에이전트 결과 회수는 가능하다. 실행 상태를 이전하는 대신 문서/산출물을 전달한다.
- 이번 조사는 ①의 부분 실측이다. 양방향 교대·중단 복구·자동 고지는 아직 완료되지 않았다.

기존 리포트 54·공용 계획·PLAN.md는 수정하지 않고 이 리포트를 추가했다.
커밋/푸시, 공용 진입점 생성, 서비스 재시작은 하지 않았다.
