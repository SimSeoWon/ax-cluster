> Part of the AX Cluster plan. Index: [`../PLAN.md`](../PLAN.md).
> Section numbers are unchanged by the split — cross-references from other documents still resolve.

## 9.5 [완료] `task_queue` 이식 완료 — 이식 1단계 (2026-08-08)

`ax-cluster/master/task_queue/` (AgentTest `mcp/task_queue/` 9파일 2,717줄).
**실제로 기동해 claim→submit 흐름까지 확인했다.** AgentTest 원본은 미변경(참조 전용).

### 9.5.1 §5.4.7 판정("거의 그대로 이식")은 맞았지만, 진짜 작업은 3곳이었다

`sys.platform` 분기는 예상대로 무해했다(3건 전부 `creationflags = ... if win32 else 0`).
바꿔야 했던 것은 **플랫폼이 아니라 전제**다:

| # | 원본 | 왜 마스터에서 깨지나 | 조치 |
|---|---|---|---|
| 1 | 플랫 import (`from models import ...`) | PyInstaller 가 한 디렉터리로 묶는 전제. `python -m` 으로는 안 돈다 | 패키지 상대 import 전환(7파일 24건) |
| 2 | `_project_root()` = `Path(__file__).parent.parent.parent` | exe 가 UE5 프로젝트 루트 안에 있다는 전제. 마스터엔 그 루트가 없어 **`ax-cluster/` 에 상태를 쓴다** | `AX_TASK_QUEUE_ROOT` 명시 설정. **폴백 없이 즉시 실패** — 루트를 잘못 잡으면 재기동 후에야 "작업이 사라졌다"로 발견된다 |
| 3 | `--cleanup-branches` 가 `_git_repo(root)` 의 `worker/*` 삭제 | 원본은 root == UE5 저장소였다. 마스터 root 는 **큐 상태 저장소**라 지울 브랜치를 못 찾고 **조용히 성공한 척**한다 | **거부**. 브랜치 정리는 저장소를 소유한 윈도우의 일이다(§2.1) |

**추가로 하나 더 분리했다** — `server.py` 가 모듈 최상단에서 `from mcp.server.fastmcp import FastMCP`
를 해서, MCP SDK 가 없으면 **HTTP 서비스조차 기동 실패**한다. systemd 주 모드는 `--serve`(HTTP)이므로
MCP stdio 를 `mcp_server.py` 로 떼고 **지연 import** 로 바꿨다.

> [주의] **거부(3번)를 처음엔 함수 중간에 넣었다가 옮겼다.** 그 위치면 archive/purge 를 **이미 수행한 뒤**
> 실패를 반환한다 — 파괴적 작업을 해놓고 "실패"라고 보고하는 꼴이다. 진입부로 옮겨
> **아무것도 건드리기 전에** 거부하도록 고쳤다(실측으로 데이터 보존 확인).

### 9.5.2 상태 저장소 — `/home/sim/ax-state` (로컬 git)

감사 커밋은 전부 `idx.root` 로 간다(`target_repo` 가 아니다). 마스터는 UE5 저장소를 소유하지 않으므로
**큐 상태 전용 저장소**를 새로 뒀다. 리모트 없음 — 필요해지면 Gitea 리모트를 붙일 수 있다.

### 9.5.3 실측 — 두 작업장 경쟁 방어가 실제로 동작한다

§4.2 에서 "작업장 2대가 같은 프로젝트를 보므로 claim/lease/fencing 은 정확성 요건"이라 적었는데,
그게 실제로 도는지 확인했다:

| 검증 | 결과 |
|---|---|
| work 등록 → task 등록 → claim | [완료] `epoch=1`, `assignee=win-pc-1` |
| **다른 워커가 같은 task claim 시도** | [완료] **빈 응답 — 이중 claim 없음** |
| 올바른 epoch 로 submit | [완료] 수락 |
| [중요] **stale epoch(좀비 워커) 로 submit** | [완료] **거부** — `stale epoch 0 < current 1 (reassigned)` |
| 재기동 후 상태 복원 | [완료] 디스크 MD 에서 인덱스 재구축 |
| `--cleanup-branches` | [완료] 거부 + **데이터 보존** |
| 감사 커밋 | [완료] `[work-register]`·`[task-register]`·`[claim]`·`[submit]`·`[admin-reset]` 누적 |

### 9.5.4 실행 구성

- venv: `ax-cluster/.venv` (`master/requirements.txt` — AgentTest 엔 없어 `build.bat:29` 기준 신규 작성)
- [주의] 선결이었던 `python3-venv`·`python3-pip` 가 이 박스에 없어 `pkexec` 로 설치했다

### 9.5.5 [완료] systemd 등록 완료 (2026-08-08)

`/etc/systemd/system/ax-task-queue.service` 설치 → `enable` → `start`. **is-enabled=enabled / is-active=active.**

| 검증 | 결과 |
|---|---|
| 서비스 기동·응답 | [완료] `0.0.0.0:8101`, journald 로 로그 수집 |
| `ExecStart` 가 `PYTHONPATH` 없이 도는가 | [완료] `WorkingDirectory` 만으로 `python -m master.task_queue` 성립 (등록 **전에** 확인) |
| 샌드박스 실제 적용 | [완료] `ProtectSystem=strict` · `ProtectHome=read-only` · `NoNewPrivileges=yes` · `ReadWritePaths=/home/sim/ax-state` |
| 샌드박스 하에서 상태 쓰기·git 감사 커밋 | [완료] 동작 (`ReadWritePaths` 구멍으로 통과) |
| [중요] **`Restart=always` 실동작** | [완료] `kill -9` 후 systemd 가 재기동(`NRestarts=1`), **상태는 디스크에서 복원** |

**→ §5.4.3 의 "`process_lifecycle.py`(Job Object) 폐기하고 systemd 에 넘긴다"가 실증됐다.**
자식 프로세스 `.poll()` 생존 감시를 손으로 하던 것이 `Restart=always` 한 줄로 대체된다.

### 9.5.6 [완료] 해소 — LAN 개방 + 인증 계층 (2026-08-08)

실측으로 드러난 두 가지:

1. **`ufw` 가 활성이고 기본 정책이 `deny (incoming)` 인데 8101 규칙이 없다.**
   현재 허용 목록: 22/tcp · 80 · 3000/tcp(Gitea, 의도된 인터넷 노출) · 3389/tcp(xrdp).
   즉 서비스는 `0.0.0.0:8101` 에 바인드돼 있지만 **윈도우 작업장에서 접근 불가**다.
2. ~~**`task_queue` HTTP 서버에 인증 계층이 0건이다**~~ → **해소 2026-08-08.**
   `master/auth.py` 의 공유 베어러 토큰을 세 서비스가 함께 쓴다. fail-closed —
   토큰이 없거나 약하거나 파일 권한이 열려 있으면 **서비스가 뜨지 않는다.**
   AgentTest 시절엔 팀 내부망 전제였다.

**둘을 같이 봐야 한다** — 인증이 없으므로 여는 범위를 반드시 제한해야 한다:

| 방식 | 평가 |
|---|---|
| `ufw allow 8101` (Anywhere) | [실패] **여전히 금지.** 토큰이 생겼어도 인터넷 노출은 별개다. Gitea 처럼 라우터 포트포워딩까지 걸리면 큐를 누구나 조작한다 |
| `ufw allow from 192.168.0.0/24 to any port 8101` | [완료] 현실적. BC-250 방화벽이 `192.168.0.57` 만 허용하는 것과 같은 결 |
| 바인드를 `127.0.0.1` 로 낮추고 SSH 터널 | 더 안전하나 작업장 2대 연결이 번거롭다 |

**[완료] LAN 한정으로 개방 완료 (2026-08-08, 사용자 지시):**

```
ufw allow from 192.168.0.0/24 to any port 8101 proto tcp \
    comment "AX task_queue (LAN only, no auth layer)"
```

| 검증 | 결과 |
|---|---|
| 규칙 범위 | [완료] `8101/tcp ALLOW IN 192.168.0.0/24` — 출발지 한정(Anywhere 아님) |
| 실제 LAN 호스트에서 도달 | [완료] BC-250(192.168.0.43)에서 `/api/v1/health` 200 |
| 쓰기 경로 | [완료] 같은 곳에서 work 등록 성공 |
| 부팅 시 유지 | [완료] `ufw`·`ax-task-queue` 둘 다 `enabled` |

 **출발지 한정이라 포트포워딩 사고까지 막는다** — 라우터가 실수로 8101 을 포워딩해도
외부에서 온 패킷의 출발지는 `192.168.0.0/24` 가 아니라 기본 정책 `deny` 에 걸린다.
Gitea(3000)가 `Anywhere` 로 열려 있는 것과 대조된다.

[완료] **인증 계층이 생겼다 (2026-08-08).** 이제 방어선이 둘이다 — 토큰과 방화벽.
그래도 방화벽 규칙은 **그대로 유지한다**(토큰은 대체가 아니라 추가다). 아래 원 서술:
~~지금 방어선은 방화벽 하나뿐이므로,~~
① 8101 규칙을 `Anywhere` 로 넓히지 말 것 ② LAN 안의 기기를 신뢰할 수 없게 되면
(예: 게스트 기기 접속) 인증을 먼저 붙일 것.

---
