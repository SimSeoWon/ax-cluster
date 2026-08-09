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
  🔴 **The twin grows now, but only on changed files — 20 of 38 sub-tasks done.**
  중 1.1 relation graphs ✅ · 중 1.2 context-MD synthesis ✅ **wired into the indexer** (verified on
  a real commit diff: graphs → synthesis → reindex) · 중 1.3 ontology **8/13** — the LLM
  re-synthesis now runs (measured: local 2-node and `claude` both passed the fact gate 100%) · 중 1.4 thesaurus has a
  window but **zero alias data**.
  🔴 **Never bulk-regenerate the 1,055 snapshot docs** — our local model measured *worse* than the
  received snapshot (it described commented-out code as live). A **deterministic fact gate** now
  rejects that, and 중 1.3 reuses it for call relations. The synthesiser is for *new/changed* files.
  The breakdown is
  대 2 / 중 8 / 소 36 — **소분류가 작업 단위다.** Never size a task by line count: `class_graph`'s
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

## Work flow — three places, three jobs (user-confirmed 2026-08-09)

🔴 **Don't collapse these.** Each answers a different question, and mixing them is how the
milestone doc grew stale numbers before.

| | Answers | Rule |
|---|---|---|
| **Milestone doc** `docs/milestones/2-*.md` | *Where are we?* — 대/중/소 breakdown, denominators, chains | Progress lives **only** here. Delete finished 소분류 to hold the line cap |
| **Redmine** `http://192.168.0.57:8080` | *What is being worked, by whom, now?* — individual items, priority, assignment | Open an issue for work that spans sessions; move it 신규 → 진행 → 해결 and put the commit hash in the note |
| **`reports/`** | *Why did we decide that?* — decisions, measurements, traps | One report per session, Korean. Not a task list |

**At session start**: read the open milestone, then `GET /issues.json?status_id=open` for `[AX]`
items. **At session end**: update the issues you moved, then write the report.

🔴 **Redmine is the *same* project as the game — `ModularStage` (id 1), tracker `코드리뷰`
(user-confirmed: *"동일한 프로젝트네"*).** The AX cluster is tooling **for** that R&D, not a
separate deliverable. **Never create a new project or tracker**; distinguish with an `[AX]` subject
prefix only. Read is public; writing needs the admin API key, which is **not on disk** — pull it
from the master's own container DB. 🔴 **Never write the key value into a doc or commit.**
→ [`docs/10-references.md`](docs/10-references.md) §10.1

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
| Event spool + **indexer** (Gitea hook → graphs → **synthesis** → reindex) | `master/events/` — **live**: `ax-indexer.path` (inotify) → `ax-indexer.service`. 🔴 **This is where the twin grows**: changed files → relation graphs (LLM 0) → context-MD synthesis (35B) → reindex. Lost groups are logged by name — the watermark has already advanced, so they can't be found again |
| Context search — **multilingual** vector + BM25 (+trigram KR table), RRF, `[대괄호]` focus | `master/context_search/` — context MDs (961 docs) **and now domain packages** (7, 소 2.1 ✅ 3/3). Domains live in a **separate DB + collection** (`bm25_domains.db` / `ontology_domains`) so they can't crowd out file-level hits; `search_norms` applies a 🔴 **triple noise gate** (BM25-zero ⇒ empty · vector-only needs threshold · hard cap). Wired into `rebuild_all`, skipped by fingerprint when unchanged |
| Workflow — 2-tier branches, manifest, registration, generate → layer2 → hand over, **domain norms** | `master/work/` — 소 2.3.1 ✅: `norms.py` turns `search_norms` hits into an invariants-first bundle in the manifest (≤2 domains × actions touching the target classes). **Measured**: same prompt/model, norms flipped the generated code from an invented member to 4/4 real ones and it honoured a real invariant — but **near-miss spellings survived** (`CurrentStep` vs real `Step`), which is why "ship source declarations to the node" is still open. 🔴 `master.work.generate` the *function* shadows the same-named submodule in `__init__` — import the module path directly. Map: `docs/4-work-loop.md` §4.7 |
| **Relation graphs** — inheritance (tree-sitter C++) + `#include` (중 1.1, **done 5/5**) | `master/graph/` — **1,806 classes · 6,380 methods · 10,817 include edges** on ModularStage, 2.9s full scan. `python -m master.graph build\|status`. ⚠️ reverse include lookup is basename-approximate (9 ambiguous headers) |
| **Ontology** — YAML io (no PyYAML) · stale · L1/L2/L3 layers · member proposals · concept hierarchy · **fact gate** · package writer · **LLM re-synthesis** (중 1.3, **8/13**) | `master/ontology/` — `python -m master.ontology status\|plan\|verify\|dry\|refresh`. 🔴 **`plan` → `dry` first**: `plan` sizes prompts with **no LLM**, `dry` synthesises without writing. Domain MD (intent) + source excerpts + graphs → actions/invariants → deterministic gates → package. 🔴 **Payload is chunked by `#include` cohesion and split across both nodes** — model name selects the node; the defaults are each node's **resident** model (any other evicts the pin). `claude`/`agy` are also valid lanes. Prompt budget is **measured** (2.79–2.85 chars/token, `num_ctx` 8192 both nodes). 🔴 Decision rules live in that package's `__init__.py` |
| **Context-MD synthesis** — prompt+grounding, σ.7 fence strip + σ.7-B save gate, stamping, batch circuit breaker (중 1.2) | `master/context_synth/` — `python -m master.context_synth one\|fill\|all\|status`. 909 source groups, all already documented from the snapshot. **Wired into the indexer** (changed files only). A **deterministic factuality gate** (`verify.py`) rejects docs describing commented-out code as live — **75% pass rate measured on the 35B (3/4)**, and the one rejection was a real catch. `sample N` dry-runs without touching snapshot docs. 🔴 **BC-250 reclaims ~170 MB per request and never gives it back until the model unloads** — `UNLOAD_EVERY=5` handles that; set 0 for dedicated-VRAM nodes |
| **Worker bundle** — per-machine config · skill · CLAUDE.md merge, delivered over SSH (#21) | `master/client/` — `python -m master.client probe\|plan\|deliver\|check`. **Role-aware**: `worker` gets `ax-work`; `requester` (the human's PC) gets `ax-request`/`ax-ontology` and is **excluded from `drivable_hosts`** — `driven` (can we reach it) and `role` (may we dispatch to it) are different axes. 🔴 **Paths are never hardcoded**: the master generates `<checkout>/.ax/config.json` from the registry, because a worker's config was found pointing at *another machine's* path. Capabilities are **probed, not declared**, and the block states the *consequence* ("no UE5 ⇒ layer-3 cannot be verified here"). CLAUDE.md is merged **marker-delimited** — human text is never overwritten. 🔴 Delivery verifies by re-reading sha256; that caught PowerShell adding BOM/CRLF and an 18KB stdin hang, so transfers use `scp` |
| Ollama node check + remote install (no residency) | `master/provision.py` — `python -m master.provision check` |
| venv + deps | `.venv/`, `master/requirements.txt` |

`worker/` is still a README-only stub. **`client/` is live** — see the table row above.

🔴 **Say "done" only for a whole area.** The twin now grows *and* is searchable end to end, but the
**goal ② now runs end to end** — but the measured output shows the node still guesses exact
identifiers, so `docs/3-open-items.md`'s "ship source declarations in the manifest" is the next
real gap, not a nicety. When
reporting status, give the denominator (*"twin sub-tasks 18 of 36"*), never a scope narrowed to
what got built.
→ `docs/5-master-orchestration.md` §5.2-E ④-1, §5.3 진행 현황

**Tests — 1,145, all passing. No pytest**; each file runs standalone.

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
.venv/bin/python master/test_context_search.py       # 82 — search core: mount routing, RRF, generation pointer
.venv/bin/python master/test_work.py                 # 149 — 2-tier branches, manifest, registration, generate+layer2
.venv/bin/python master/test_provision.py            #  43 — Ollama node check/install; .33 must stay non-resident
.venv/bin/python master/test_indexer.py              #  49 — spool consumer: ff-only mirror, digest guard, watermark
.venv/bin/python master/test_graph.py                #  80
.venv/bin/python master/test_ontology.py             #  127 — YAML io: 왕복 보존, 안 바뀌면 안 씀 — relation graphs: Source-only, fail-closed, no ghost rows
.venv/bin/python master/test_context_synth.py        #  102 — σ.7/σ.7-B gates, comment preservation, circuit breaker + factuality gate
.venv/bin/python master/test_ontology_synth.py       #  42 — 도메인 MD 두 스키마 · 조각 고지 · 응답 파서의 도메인 밖 차단
.venv/bin/python master/test_twin_base.py           #  18 — 기준 커밋: 모른다·없다·못 봤다를 뭉치지 않는가
.venv/bin/python master/test_client_bundle.py        #  63 — role(파견 가능 ≠ 닿음) · CLAUDE.md 블록 병합 · config 에 비밀 없음
.venv/bin/python master/test_norms.py                #  20 — 도메인 규범: 관련성 필터 · 예산 · 🔴 결손 명시
.venv/bin/python master/test_domain_index.py         #  30 — 도메인 색인: 페이로드에 항목 본문 녹이기 · 지문 · 🔴 노이즈 3중 차단

# Ontology — 🔴 plan(LLM 0) → dry(안 씀) → refresh 순서
.venv/bin/python -m master.ontology status
.venv/bin/python -m master.ontology plan <도메인>     # 조각 수·프롬프트 토큰·출력 여유

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
