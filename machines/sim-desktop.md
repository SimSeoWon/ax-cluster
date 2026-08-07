# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## About this directory

`/home/sim` is the user's home directory on **sim-desktop** — a personal Linux home server, not a software repository. There is no build, lint, or test tooling here; don't assume a codebase exists.

- Host: `sim-desktop`, LAN IP **192.168.0.57** (plus Docker bridges 172.17–19.0.1)
- OS: Ubuntu 22.04.2 LTS (jammy)
- Locale: `ko_KR.UTF-8` — **the user communicates in Korean; reply in Korean.**
- GPU: NVIDIA GT 1030 (2GB). **No NVIDIA driver is installed** — `nvidia-smi` fails. Anything CUDA-dependent needs the driver installed first.
- Remote access to this box is also possible via xrdp (3389).

## Role in the AX cluster

This machine is the **master** of the AX cluster (AI Transformation for a UE5 game production pipeline).

The project repo is cloned **here** at `~/ax-cluster` (`PLAN.md` is the SSOT), with copies on BC-250 #1 (`sim@192.168.0.43:~/ax-cluster`) and GitHub (`SimSeoWon/ax-cluster`, **private — keep it that way**, it contains LAN addresses and firewall rules). Keep all three in sync; pushing to the board's `main` is rejected because it's checked out there, so `git pull` on that side instead. `~/AgentTest` is the predecessor project, cloned **reference-only — never modify or push to it**.

```
sim-desktop (this box, 192.168.0.57)  = master: orchestration, RAG index,
                                         ontology/graph, task distribution
        │  internal LAN only
        ▼
BC-250 #1 (192.168.0.43)               = inference node: Ollama + Vulkan, stateless
BC-250 #2                               = 🎮 Bazzite gaming machine — NOT an inference
                                          node. Converting it means giving up that
                                          machine; never assume a 2nd node exists.
Windows UE5 PC ×2                       = the workshops: file ownership, engine
                                          execution, build/RunTests, code registration.
                                          Both work on the SAME UE5 project.
```

**There is only one inference node.** `MAX_LOADED_MODELS=1`, and switching models costs
~64s (35B) / ~36s (14b) — a round trip is ~100s. Anything premised on parallel inference,
node failover, or per-board model pinning does not hold today.

Design rules inherited from the AgentTest 2026-07-07 architecture:
- The inference nodes **never touch files** — only text (context / code fragments / diffs) crosses the wire. File I/O and builds happen on whichever machine owns the files.
- Master→node calls are **stateless** (Ollama `/api/generate` with the `context` field deliberately not reused).
- Deterministic gates (tests / type checkers / linters) outrank LLM judgment for verification.
- **Never shard a model across BC-250 boards** — each board is an independent endpoint and the master load-balances *requests*. The boards have 1GbE and no PCIe slots, so tensor/pipeline parallelism starves on bandwidth.

## Accessing the BC-250 inference node

Passwordless SSH is configured (`~/.ssh/id_rsa` → `sim@192.168.0.43`).

```bash
ssh sim@192.168.0.43                                    # shell
curl http://192.168.0.43:11434/api/tags                 # model list
curl http://192.168.0.43:11434/api/generate -d '{...}'  # inference
```

Two things that regularly trip up remote work on that board:

1. **`sudo` there needs a password and there is no TTY.** A heredoc piped over SSH consumes stdin, so `sudo -S` never sees the password. Write the script to the remote host first, then run it:
   ```bash
   ssh sim@192.168.0.43 'cat > /tmp/x.sh' << 'EOF'
   ...script...
   EOF
   printf '%s\n' "$PW" | ssh sim@192.168.0.43 'chmod +x /tmp/x.sh && sudo -S -p "" /tmp/x.sh'
   ```
   That board's own `~/CLAUDE.md` still documents a `pkexec` + graphical-polkit pattern — **that is stale**; it went headless (`multi-user.target`) on 2026-08-05, so there is no desktop session to show a polkit dialog.
2. Its Ollama port 11434 is firewalled to accept **only 192.168.0.57** (this machine). Adding another client means adding a firewalld rich rule there.

Before touching that board's hardware config (CU unlock, SMU OC, governor, boot params), read `sim@192.168.0.43:~/bc250-backup-staging/reports/*.md` — it carries hard-won constraints, and its `CLAUDE.md` mandates reading those reports in full rather than grepping.

## Self-hosted services

| Service | Port | Managed by | Config |
|---|---|---|---|
| Gitea | 3000 | systemd `gitea.service` | `/etc/gitea/app.ini`, SQLite DB |
| n8n | 5678 | Docker `n8n-n8n-1` | `~/n8n/docker-compose.yml` |
| Redmine | 8080 → 3000 | Docker `redmine-redmine-1` (+ `redmine-db-1`, postgres 15) | `~/redmine/docker-compose.yml` |
| Apache2 | — | systemd | |
| MySQL | 3306 | systemd | |
| **ax-task-queue** | **8101** | systemd `ax-task-queue.service` | `~/ax-cluster/master/systemd/`, state in `~/ax-state` |

**Gitea is intentionally exposed to the internet** via router port-forwarding so friends can collaborate. It has been hardened (registration disabled, OpenID disabled, sign-in required to view) but still serves plain HTTP — TLS migration was deferred; the options discussed were Tailscale (preferred) or DuckDNS+Caddy.

**`ax-task-queue`** (added 2026-08-08) is the AX cluster's job queue — `~/ax-cluster/master/task_queue/`,
running from `~/ax-cluster/.venv`. Its state lives in `~/ax-state` (a **separate local git repo**;
every state transition is an audit commit). It has **no auth layer at all**, so port 8101 is opened
**LAN-only** (`ufw allow from 192.168.0.0/24 to any port 8101`) — the firewall is the only defence.
Never widen that rule to `Anywhere`.

Check `ss -tln` before allocating a port for anything new. Prefer Docker Compose for new services,
matching the existing pattern — **with one deliberate exception**: the AX cluster's own services run
under **systemd + venv**, because they need host git, SSH keys, the `agy`/`claude` CLIs with their
home-directory auth, and the Gitea hook. Containerising those would mean mounting all of it back in.
Upstream off-the-shelf services (n8n, Redmine) still belong in Compose.

## Work journal

`~/claude-workspace/reports/` holds numbered work reports, mirroring the BC-250's `~/bc250-backup-staging/reports/` convention. For infra changes that require a reboot or risk losing access, **write the intended commands to a report file before running them and update it during the work** — a lost connection otherwise destroys the record of what was being attempted.

## Environment notes

- `~/.local/bin` is on PATH via an explicit block in `~/.bashrc` (added 2026-08-02). It is also in `~/.profile`, but `.profile` only runs for login shells, so a plain new terminal wouldn't have found the `claude` binary without the `.bashrc` entry.
- `sudo` on **this** machine requires a password (no NOPASSWD) — but **`pkexec <cmd>` works**: an
  authentication dialog appears on the user's screen and grants root once they accept. Run it with
  `run_in_background: true` and tell the user to look at the screen. Don't conflate the two, and don't
  declare a privileged task impossible without trying `pkexec` first. (The BC-250 is genuinely stuck:
  headless since 2026-08-05, so no authentication agent can exist there.)
- Python: `python3-venv` and `python3-pip` were **not** installed by default here; they were added
  2026-08-08 via `pkexec apt-get install`. The AX cluster's venv is `~/ax-cluster/.venv`.
