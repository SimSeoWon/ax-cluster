# sim-desktop — self-hosted services

Index: [`../sim-desktop.md`](../sim-desktop.md) (= the master's `~/CLAUDE.md`)

| Service | Port | Managed by | Config |
|---|---|---|---|
| Gitea | 3000 | systemd `gitea.service` | `/etc/gitea/app.ini`, SQLite DB |
| n8n | 5678 | Docker `n8n-n8n-1` | `~/n8n/docker-compose.yml` |
| Redmine | 8080 → 3000 | Docker `redmine-redmine-1` (+ `redmine-db-1`, postgres 15) | `~/redmine/docker-compose.yml` |
| Apache2 | — | systemd | |
| MySQL | 3306 | systemd | |
| **ax-task-queue** | **8101** | systemd `ax-task-queue.service` | `~/ax-cluster/master/systemd/`, state in `~/ax-state` |
| **ax-broker** | **8102** | systemd `ax-broker.service` | `~/ax-cluster/master/broker/` |
| **ax-projects** | **8103** | systemd `ax-projects.service` | `~/ax-cluster/master/projects/`, registry in `~/ax-cluster/projects.yaml`. Also serves the ported web UI (`master/webui/`) |
| ax-indexer | — | systemd `ax-indexer.path` + `.service` | path-triggered; grows the twin on push |
| **ax-status** | — | systemd **`ax-status.timer`** (5 min) + `.service` | 🔴 the only thing that refreshes `/cluster`; **read-only SSH probes**, exit code 3 = throttle guard, not a failure |

## Gitea is intentionally exposed to the internet

Via router port-forwarding, so friends can collaborate. It has been hardened (registration
disabled, OpenID disabled, sign-in required to view) but still serves **plain HTTP** — TLS
migration was deferred; the options discussed were Tailscale (preferred) or DuckDNS + Caddy.

## 🔴 The three AX services require a bearer token (since 2026-08-08)

`ax-task-queue` (8101), `ax-broker` (8102), and `ax-projects` (8103) all authenticate with a
**shared bearer token**: `~/.config/ax-cluster/token` (0600). Send
`Authorization: Bearer <token>`. Only `/livez` is open — it returns `{"ok":true}` and nothing else,
so liveness checks work without a credential while `/health` (which reveals node addresses and
resident models) stays behind auth.

**Fail-closed: a service will not start if the token is missing, empty, under 32 chars, or if the
file's permissions are open.** "Run without auth" is not a fallback — that was the state being fixed.

🔴 **One documented exception on 8103: the web pages are open, the APIs are not** (user decision,
2026-08-13). `/`, `/ontology`, `/cluster` and the read-only endpoints they call are served with **no
login**; `/mcp` and every mutating path still demand the bearer token (measured: `/mcp` → 401 at the
same moment the pages returned 200). The reasoning is that the token rule exists to protect what can
*change* things, and putting an intruder model on a read-only viewer for a one-person four-machine
LAN produces a screen nobody uses. The remaining defence is the ufw LAN restriction above — so
**that rule is now load-bearing for the viewer, not just defence in depth.**

They remain **LAN-only** by firewall as well:

```
ufw allow from 192.168.0.0/24 to any port 8101 proto tcp
ufw allow from 192.168.0.0/24 to any port 8102 proto tcp
ufw allow from 192.168.0.0/24 to any port 8103 proto tcp
```

**Never widen any of these rules to `Anywhere`.**

`ax-projects` (8103) is an MCP server, so a browser can reach it too — **DNS rebinding protection
is therefore enabled** as well. These defend different threats: the firewall blocks access from
outside the LAN; rebinding protection blocks a browser *inside* the LAN being tricked by a
malicious page into poking the port. Both are needed.

⚠️ The SDK's `allowed_hosts` **does not support the `*` wildcard** — only exact matches or `host:*`
(port wildcard). Passing `["*"]` rejects everything (measured 2026-08-08).

## Adding a new service

Check `ss -tln` before allocating a port. Prefer **Docker Compose** for upstream off-the-shelf
services (n8n, Redmine), matching the existing pattern.

**One deliberate exception:** the AX cluster's own services run under **systemd + venv**, because
they need host git, SSH keys, the `agy`/`claude` CLIs with their home-directory auth, and the Gitea
hook. Containerising those would mean mounting all of it back in.
