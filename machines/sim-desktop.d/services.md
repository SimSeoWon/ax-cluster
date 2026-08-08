# sim-desktop — 자체 호스팅 서비스

색인: [`../sim-desktop.md`](../sim-desktop.md) (= 마스터의 `~/CLAUDE.md`)

| Service | Port | Managed by | Config |
|---|---|---|---|
| Gitea | 3000 | systemd `gitea.service` | `/etc/gitea/app.ini`, SQLite DB |
| n8n | 5678 | Docker `n8n-n8n-1` | `~/n8n/docker-compose.yml` |
| Redmine | 8080 → 3000 | Docker `redmine-redmine-1` (+ `redmine-db-1`, postgres 15) | `~/redmine/docker-compose.yml` |
| Apache2 | — | systemd | |
| MySQL | 3306 | systemd | |
| **ax-task-queue** | **8101** | systemd `ax-task-queue.service` | `~/ax-cluster/master/systemd/`, 상태는 `~/ax-state` |
| **ax-broker** | **8102** | systemd `ax-broker.service` | `~/ax-cluster/master/broker/` |
| **ax-projects** | **8103** | systemd `ax-projects.service` | `~/ax-cluster/master/projects/`, 레지스트리는 `~/ax-cluster/projects.yaml` |

## Gitea 는 의도적으로 인터넷에 열려 있다

라우터 포트 포워딩으로 친구들과 협업하기 위해서다. 하드닝은 되어 있다(가입 비활성 · OpenID 비활성 ·
열람에 로그인 요구). 다만 여전히 **평문 HTTP** 다 — TLS 이전은 보류됐고, 논의된 선택지는
Tailscale(선호) 또는 DuckDNS+Caddy 였다.

## 🔴 AX 서비스 3종은 인증 계층이 아예 없다

`ax-task-queue`(8101) · `ax-broker`(8102) · `ax-projects`(8103) — 셋 다 auth 가 없다.
그래서 **LAN 한정으로만** 열려 있고, **방화벽이 유일한 방어선**이다.

```
ufw allow from 192.168.0.0/24 to any port 8101 proto tcp
ufw allow from 192.168.0.0/24 to any port 8102 proto tcp
ufw allow from 192.168.0.0/24 to any port 8103 proto tcp
```

**어느 규칙도 `Anywhere` 로 넓히지 말 것.**

`ax-projects`(8103) 는 MCP 서버라 브라우저에서도 닿을 수 있어 **DNS 리바인딩 보호도 켜 두었다** —
방화벽이 막는 것은 LAN 밖 접근이고, 이 보호가 막는 것은 LAN 안 브라우저가 악성 페이지에 속아
이 포트를 찌르는 경로다. 서로 다른 위협이라 둘 다 필요하다.
⚠️ SDK 의 `allowed_hosts` 는 와일드카드 `*` 를 지원하지 않는다 — 정확 일치 또는 `host:*` 뿐이다
(`["*"]` 를 넣으면 전부 거부된다, 2026-08-08 실측).

## 새 서비스를 올릴 때

포트를 잡기 전에 **`ss -tln` 으로 확인**할 것. 기성 서비스(n8n·Redmine 류)는 기존 패턴대로
**Docker Compose** 를 쓴다.

**단 한 가지 의도적 예외:** AX 클러스터 자체 서비스는 **systemd + venv** 로 돈다.
호스트 git, SSH 키, `agy`/`claude` CLI 의 홈 디렉토리 인증, Gitea 훅이 필요해서다 —
컨테이너에 넣으면 그걸 전부 다시 마운트해 넣어야 한다.
