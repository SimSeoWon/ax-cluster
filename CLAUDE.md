# CLAUDE.md

Guidance for Claude Code when working **in this repository**. Machine-level guides live in
[`machines/`](machines/README.md) — different purpose, don't confuse the two.

> 🔴 **This file is an index.** It holds only the rules that must never be missed plus pointers.
> Detail lives in [`PLAN.md`](PLAN.md) → [`docs/`](docs/). Add depth *there*, not here —
> this file is auto-loaded into every session, so length here is a tax on every task.

## Hard rules — inline on purpose

- 🔴 **The GitHub remote is private. Keep it that way** — it contains LAN addresses and firewall rules.
- 🔴 **The master is infrastructure, not a workshop.** It assembles context and hands it over;
  the Windows PC applies, builds, tests, registers. **Files never leave Windows.** No file I/O or
  tool-calling on the master. → [`docs/2-architecture.md`](docs/2-architecture.md)
- 🔴 **No auth layer on `task_queue` (8101), the broker (8102), or projects (8103).** All three are
  LAN-only via `ufw allow from 192.168.0.0/24`; the firewall is the *only* defence.
  **Never widen any of them to `Anywhere`.**
- 🔴 **`/home/sim/AgentTest` is reference-only — never modify or push to it.** Port code *out* of it.
- 🔴 **Human sessions: never run** `push --force`, `reset --hard`, branch/tag deletion, `rebase`, or
  history rewriting — not even when told; describe the command instead. Don't read a first-person
  statement ("I'll commit and come back") as an instruction to you — that exact misreading caused an
  incident in AgentTest. Pipeline workers follow *different* rules.
  → [`docs/8-git-authority.md`](docs/8-git-authority.md)
- 🔴 **Never trust a delegated backend's "done".** Measured 2026-08-07: `agy` returned
  `status:"SUCCESS"` while writing no file. Verify the artifact, not the status.
- 🔴 **`worker` means three different things.** This repo's `worker/` = BC-250 inference node;
  AgentTest's `worker/` = the Windows harness (it stays there); this repo calls that layer `client/`.
  → [`docs/settled-decisions.md`](docs/settled-decisions.md)

There is no linter or CI config — **don't invent tooling commands.**

## Where things are

| Need | Go to |
|---|---|
| What's decided vs open | [`PLAN.md`](PLAN.md) — index of `docs/` |
| Closed decisions, don't relitigate | [`docs/settled-decisions.md`](docs/settled-decisions.md) |
| Still open | [`docs/3-open-items.md`](docs/3-open-items.md) |
| Per-machine operating guide | [`machines/`](machines/README.md) |
| **Machine inventory** — IPs, roles, what's reachable from where | [`machines/sim-desktop.md`](machines/sim-desktop.md) § Machine inventory |
| External projects, reports | [`docs/10-references.md`](docs/10-references.md) |

## What exists in code

| Component | Where |
|---|---|
| Layer-2 verdict contract (fail-closed) | `master/verdict.py`, `master/layer2_verify.py` |
| Inference broker (Ollama-compatible) | `master/broker/` — **live**, `ax-broker.service` `:8102` |
| Task queue (ported, 2,717 lines) | `master/task_queue/` — **live**, `ax-task-queue.service` `:8101` |
| Project registry (MCP) | `master/projects/` — **live**, `ax-projects.service` `:8103` |
| Capability routing (`requires`/`capabilities`) | `master/task_queue/logic_claim.py` |
| venv + deps | `.venv/`, `master/requirements.txt` |

`worker/` and `client/` are still README-only stubs.

**Tests — 142, all passing. No pytest**; each file runs standalone.

```bash
python3 master/test_verdict.py                      # 19 — pure logic
python3 master/test_broker_routing.py               #  9 — pure logic
.venv/bin/python master/test_capability_routing.py  # 16 — needs venv (pydantic)
.venv/bin/python master/test_broker_health.py       #  8 — needs venv
.venv/bin/python master/test_projects.py            # 63 — needs venv (pyyaml)
.venv/bin/python master/test_mcp_servers.py         # 27 — both MCP servers import + register

curl -s localhost:8102/health | python3 -m json.tool   # which node holds which model
systemctl status ax-task-queue ax-broker ax-projects
journalctl -u ax-projects -f
```

## Three clones — keep them in sync

Master (`sim@192.168.0.57:~/ax-cluster`), BC-250 #1 (`sim@192.168.0.43:~/ax-cluster`), and GitHub.
The board has `main` checked out, so **pushing to it is rejected — `git pull` there instead.**
Check sync before working.
