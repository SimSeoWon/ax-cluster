# CLAUDE.md

Guidance for Claude Code when working **in this repository**. Machine-level guides live in
[`machines/`](machines/README.md) — different purpose, don't confuse the two.

> 🔴 **This file is an index.** It holds only the rules that must never be missed plus pointers.
> Detail lives in [`PLAN.md`](PLAN.md) → [`docs/`](docs/). Add depth *there*, not here —
> this file is auto-loaded into every session, so length here is a tax on every task.

## Hard rules — inline on purpose

- 🔴 **Read which milestone you are in before planning anything.**
  **M1 (infrastructure) is closed; M2 (digital twin restoration) is open.**
  → [`docs/milestones/2-twin-restoration.md`](docs/milestones/2-twin-restoration.md)
  **Read only the open milestone** — closed ones are reference; don't load them. Progress
  lives in the milestone doc, never in the design docs (`docs/1`–`docs/10`, always current).
  🔴 **The twin cannot grow yet — 10 of 32 sub-tasks done.** Almost nothing *produces* the twin: the
  relation graphs (중 1.1) and the context-MD synthesiser (중 1.2) both landed, but 🔴 **the
  synthesiser is not wired into the indexer yet.** Our 35B described commented-out code as live
  functionality, so a **deterministic gate** now rejects that (design rule: deterministic gates
  outrank LLM judgment) — the gate is reused by 중 1.3. Use it to *fill new/changed* files, never
  to regenerate the 1,055 snapshot docs. No ontology, no thesaurus. The data is a snapshot
  received 2026-08-08 12:56, so code the pipeline writes never enters the twin. The breakdown is
  대 2 / 중 8 / 소 32 — **소분류가 작업 단위다.** Never size a task by line count: `class_graph`'s
  1,341 lines turn out to be *"delete the file → full rescan on restart"*.
  **This milestone's main is 대 1 (making the data).** `/distribute` and `/review-work` are the
  upper layer and stay 🕓 예정 — they *consume* the twin, so building them on a frozen snapshot
  means generating code against 2026-08-08 evidence.
  🔴 **Do not pick the next task yourself** — M1 failed that way (I chose an order, dug into one
  piece, declared it "complete", repeated). The order is the user's call.
- 🔴 **The GitHub remote is private. Keep it that way** — it contains LAN addresses and firewall rules.
- 🔴 **The master is infrastructure, not a workshop.** It assembles context and hands it over;
  the Windows PC applies, builds, tests, registers. **Files never leave Windows.** No file I/O or
  tool-calling on the master. → [`docs/2-architecture.md`](docs/2-architecture.md)
- 🔴 **All three services require a bearer token** (`task_queue` 8101, broker 8102, projects 8103).
  Token: `~/.config/ax-cluster/token`, 0600, **fail-closed — a service will not start without it**.
  Send `Authorization: Bearer <token>`; only `/livez` is open. They are *also* ufw LAN-only —
  **never widen those rules to `Anywhere`.** Two layers, not one instead of the other.
  → `master/auth.py`, PLAN §9.5.6
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
| Layer-3 gate (UE5 automation logs, fail-closed) | `master/layer3_verify.py` |
| Inference broker (Ollama-compatible) | `master/broker/` — **live**, `ax-broker.service` `:8102` |
| Task queue (ported, 2,717 lines) | `master/task_queue/` — **live**, `ax-task-queue.service` `:8101` |
| Project registry (MCP) | `master/projects/` — **live**, `ax-projects.service` `:8103` |
| Capability routing (`requires`/`capabilities`) | `master/task_queue/logic_claim.py` |
| Shared bearer auth (all 3 services, fail-closed) | `master/auth.py` |
| Event spool + **indexer** (Gitea hook → reindex) | `master/events/` — **live**: `ax-indexer.path` (inotify) → `ax-indexer.service` |
| Context search — vector + BM25, RRF fusion, mount-scoped | `master/context_search/` — context MDs only (961 docs). 🔴 **ontology 247 yaml = 0 indexed** (소 2.1.1) |
| Workflow — 2-tier branches, manifest, registration, generate → layer2 → hand over | `master/work/` — the loop runs (20.1s, APPROVE) but **on a half-built twin** — that run had 0 domain norms. Map: `docs/4-work-loop.md` §4.7 |
| **Relation graphs** — inheritance (tree-sitter C++) + `#include` (중 1.1, **done 5/5**) | `master/graph/` — **1,806 classes · 6,380 methods · 10,817 include edges** on ModularStage, 2.9s full scan. `python -m master.graph build\|status`. ⚠️ reverse include lookup is basename-approximate (9 ambiguous headers) |
| **Context-MD synthesis** — prompt+grounding, σ.7 fence strip + σ.7-B save gate, stamping, batch circuit breaker (중 1.2) | `master/context_synth/` — `python -m master.context_synth one\|fill\|all\|status`. 909 source groups, all already documented from the snapshot. 🔴 **not wired into the indexer.** A **deterministic factuality gate** (`verify.py`) rejects docs that describe commented-out code as live — validated on real data. `sample N` dry-runs to measure the pass rate without touching snapshot docs |
| Ollama node check + remote install (no residency) | `master/provision.py` — `python -m master.provision check` |
| venv + deps | `.venv/`, `master/requirements.txt` |

`worker/` and `client/` are still README-only stubs.

🔴 **Say "done" only for a whole area.** The work loop runs, but the digital twin it stands on is
partial — ontology unindexed, and the MD synthesiser is built but not wired in. When reporting status,
give the denominator (*"loop runs; twin sub-tasks 10 of 32"*), never a scope narrowed to what got built.
→ `docs/5-master-orchestration.md` §5.2-E ④-1, §5.3 진행 현황

**Tests — 794, all passing. No pytest**; each file runs standalone.

```bash
python3 master/test_verdict.py                      # 19 — pure logic
python3 master/test_broker_routing.py               #  9 — pure logic
.venv/bin/python master/test_capability_routing.py  # 16 — needs venv (pydantic)
.venv/bin/python master/test_broker_health.py       #  8 — needs venv
.venv/bin/python master/test_projects.py            # 63 — needs venv (pyyaml)
.venv/bin/python master/test_mcp_servers.py         # 31 — both MCP servers import + register
.venv/bin/python master/test_workshop_check.py      # 47 — dirty-check rules (no SSH; runner injected)
.venv/bin/python master/test_layer3_verify.py       # 63 — layer-3 gate: automation + build logs, fail-closed
.venv/bin/python master/test_auth.py                 # 46 — bearer auth, fail-closed
.venv/bin/python master/test_events.py               # 38 — event spool: no-loss, at-least-once, coalescing
.venv/bin/python master/test_context_search.py       # 75 — search core: mount routing, RRF, generation pointer
.venv/bin/python master/test_work.py                 # 135 — 2-tier branches, manifest, registration, generate+layer2
.venv/bin/python master/test_provision.py            #  43 — Ollama node check/install; .33 must stay non-resident
.venv/bin/python master/test_indexer.py              #  35 — spool consumer: ff-only mirror, digest guard, watermark
.venv/bin/python master/test_graph.py                #  69 — relation graphs: Source-only, fail-closed, no ghost rows
.venv/bin/python master/test_context_synth.py        #  86 — σ.7/σ.7-B gates, comment preservation, circuit breaker + factuality gate

# Relation graphs (deterministic, no LLM) — full rebuild ~2.9s for 1,654 files
.venv/bin/python -m master.graph build               # inheritance + #include
.venv/bin/python -m master.graph status

# Full reindex of the mounted project (vector + BM25, one generation flip)
.venv/bin/python -m master.context_search.rebuild

curl -s localhost:8102/health | python3 -m json.tool   # which node holds which model
systemctl status ax-task-queue ax-broker ax-projects ax-indexer.path
journalctl -u ax-indexer -n 30 --no-pager      # push → reindex 이력
.venv/bin/python -m master.events.install_hook  # Gitea 훅 설치 상태 점검
journalctl -u ax-projects -f
```

## Three clones — keep them in sync

Master (`sim@192.168.0.57:~/ax-cluster`), BC-250 #1 (`sim@192.168.0.43:~/ax-cluster`), and GitHub.
The board has `main` checked out, so **pushing to it is rejected — `git pull` there instead.**
Check sync before working.
