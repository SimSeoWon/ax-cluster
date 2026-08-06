# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Planning-stage repository for **AX** (AI Transformation) — raising AI usage across an entire Unreal Engine 5 game production pipeline, not just code assistance: ontology-based digital twin, Unreal MCP (UE 5.8.1+), and code-writing agents unified into one pipeline, run from a small Linux cluster (1 master + BC-250 worker nodes).

**There is no implementation yet.** Only `PLAN.md` and three directory stubs (`master/`, `worker/`, `client/` — READMEs only) exist — no build system, tests, or lint config. Don't invent tooling commands; check `PLAN.md` first for what's actually decided versus still open.

**This repo exists on two machines**: the master (`sim@192.168.0.57:~/ax-cluster`) and BC-250 #1 (`sim@192.168.0.43:~/ax-cluster`), both tracking `git@github.com:SimSeoWon/ax-cluster.git` (**private — keep it that way**, it contains LAN addresses and firewall rules). Check whether the two are in sync before working.

## Architecture (from PLAN.md)

🔴 **`worker` means three different things.** This repo's `worker/` is the BC-250 inference node. AgentTest's `worker/` is the operator harness that *used to* run on Windows PCs — as of 2026-08-07 it ports to `master/`, and `client/` keeps the name only as a pointer to where it lived. Always disambiguate by directory. See `PLAN.md` §4.1.

**Premise (settled 2026-08-07):** AgentTest was **team** infrastructure — every teammate's Windows PC ran its own local LLM. This cluster is **one person pooling their own machines at home**: BC-250 inherits that *inference compute*, and much of AgentTest's complexity is *team* complexity that should be trimmed, not ported (`PLAN.md` §2.0, §5.2-D).

🔴 **The master is infrastructure, not a workshop.** It assembles the right code chunk from RAG/ontology and hands it over; the Windows PC applies it, builds, tests, and registers the code — or asks again. Files never leave Windows. Don't put file I/O or tool-calling on the master (`PLAN.md` §2.1, §2.3).

**There are two orchestrators**, not one: the Windows work PC's Claude Code (where the user gives instructions) and the master (which orchestrates with Claude, Antigravity `agy`, and BC-250). They share Gitea, task_queue, and the RAG index — so claim/lease/fencing must NOT be stripped just because it's a solo project.

- `master/` — infrastructure: RAG index, ontology/graph, task_queue, the BC-250 inference broker, layer-2 verification calls (agy → Claude), and the `gajae-code` driver. It orchestrates *model calls and routing*, never file work.
- `worker/` — code/config for the BC-250 **inference nodes**. Pure text in/out, never touches files — not workers (`PLAN.md` §2.3: workers are I/O-bound, so hosting them on the boards adds no parallelism; the bottleneck is inference capacity). BC-250 #1 runs Ollama + Vulkan; #2's status is unconfirmed.
- `client/` — the Windows UE5 PC, the **workshop**: orchestrator ① (user-facing Claude Code), the only layer that owns files, applies code, runs UE5 build + `RunTests` (layer 3), and registers passing code. AgentTest's `worker/` harness stays here.
- Master↔worker calls are meant to be **stateless**: master sends a context string per request, worker infers and responds, no state persists between calls (already validated against BC-250 #1's Ollama API by not reusing its `context` field).
- Neither the master nor the inference nodes read/write project files — only text (context/code fragments/diffs) crosses the wire. All file I/O happens on Windows.
- Deterministic gates (tests/linters/type-checkers) take priority over LLM judgment for verification — this is `gajae-code`'s `Ultragoal` stage's job once wired in.

## Related, external to this repo

- [AgentTest](https://github.com/SimSeoWon/AgentTest) — the predecessor Windows-based orchestration project this cluster is meant to take over the RAG/ontology workload from.
- [gajae-code](https://github.com/Yeachan-Heo/gajae-code) — the coding-agent harness (`gjc` CLI, TypeScript/Bun) this project plans to drive from the master.
- BC-250 #1 has its own hardware/OS setup history in `sim@192.168.0.43:~/bc250-backup-staging/reports/` (master-side copies in `sim@192.168.0.57:~/claude-workspace/reports/`) — read there before touching CU unlock, ACPI, SMU OC, or other board-level config; none of that belongs in this repo.
- AgentTest is cloned on the master at `/home/sim/AgentTest` as **reference only — do not modify or push to it.** Port code *out* of it; never edit it in place.

## Settled — don't relitigate (PLAN.md §4–§6)

Python for the master orchestrator (it's a port, not a rewrite); master-as-broker for inference requests (orchestration and brokering are different layers — two orchestrators, one broker); `qwen2.5-coder:14b` for code generation and `35B-A3B IQ2_M` for context cooking; streaming chunk gaps as the node heartbeat; **Gitea event-driven instead of polling** and **systemd instead of `process_lifecycle.py`** on the master (§5.4); **BC-250 stays inference-only** and the worker pool lives on the master (§2.3).

## git operations — two different rule sets (PLAN.md §8)

**Human sessions (this one):** commit/push on request is fine. **Never run** `push --force`, `reset --hard`, branch/tag deletion, `rebase`, or history rewriting — not even when told; describe the command instead. Don't read a first-person statement ("I'll commit and come back") as an instruction to you; that exact misreading caused an incident in AgentTest, whose CLAUDE.md responded by banning Claude commits outright.

**Pipeline workers (master's worker processes):** the human rule does NOT apply — they autonomously commit/push `task/<id>` and attempt branches and advance durable via CAS. They must never push to `main` directly or force-push. The branch boundary is what separates the two rule sets.

**Never trust a delegated backend's "done".** Measured 2026-08-07: `agy` returned `status:"SUCCESS"`/`"DONE"` while writing no file (print mode needs `--mode accept-edits`). Always verify the artifact — file exists, diff applied, build passes — not just the status. This is why `worker/validator.py` and the layer-1 gate exist.

## Open decisions (see PLAN.md §3)

systemd vs Docker Compose for the master's execution model, BC-250 #2's actual state, how `gajae-code`'s WebSocket SDK gets driven from the master, and the Unreal MCP integration point are all unresolved — don't assume an answer to these when writing code here.
