# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Planning-stage repository for **AX** (AI Transformation) — raising AI usage across an entire Unreal Engine 5 game production pipeline, not just code assistance: ontology-based digital twin, Unreal MCP (UE 5.8.1+), and code-writing agents unified into one pipeline, run from a small Linux cluster (1 master + BC-250 worker nodes).

**There is no implementation yet.** Only `PLAN.md` and two directory stubs (`master/README.md`, `worker/README.md`) exist — no build system, tests, or lint config. Don't invent tooling commands; check `PLAN.md` first for what's actually decided versus still open.

## Architecture (from PLAN.md)

- `master/` — orchestration code that will run on the Linux infra machine (192.168.0.57): task distribution to workers, RAG index, ontology/relationship graph, digital twin, and the driver for the `gajae-code` harness (Deep-Interview → Ralplan → Ultragoal → Team) that calls Claude/Antigravity.
- `worker/` — code/config for the BC-250 nodes. BC-250 #1 already has Ollama + Vulkan running with a verified local-LLM inference path (see `~/.claude/projects/-home-sim/memory/project_bc250_ollama_vulkan.md` on this machine); BC-250 #2's status is unconfirmed.
- Master↔worker calls are meant to be **stateless**: master sends a context string per request, worker infers and responds, no state persists between calls (already validated against BC-250 #1's Ollama API by not reusing its `context` field).
- Workers don't read/write files directly — only text (context/code fragments/diffs) crosses the wire; actual file I/O and builds happen on whichever machine holds the files.
- Deterministic gates (tests/linters/type-checkers) take priority over LLM judgment for verification — this is `gajae-code`'s `Ultragoal` stage's job once wired in.

## Related, external to this repo

- [AgentTest](https://github.com/SimSeoWon/AgentTest) — the predecessor Windows-based orchestration project this cluster is meant to take over the RAG/ontology workload from.
- [gajae-code](https://github.com/Yeachan-Heo/gajae-code) — the coding-agent harness (`gjc` CLI, TypeScript/Bun) this project plans to drive from the master.
- This machine (BC-250 #1) has its own hardware/OS setup history in `~/bc250-backup-staging/reports/` and `~/.claude/projects/-home-sim/memory/` — read there before touching CU unlock, ACPI, SMU OC, or other board-level config; none of that belongs in this repo.

## Open decisions (see PLAN.md §3)

Python vs Go for the master orchestrator, BC-250 #2's actual state, how `gajae-code`'s WebSocket SDK gets driven from the master, and the Unreal MCP integration point are all unresolved — don't assume an answer to these when writing code here.
