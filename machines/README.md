# machines — canonical copies of the per-machine Claude Code guides

Each machine's `~/CLAUDE.md` (the file Claude Code auto-loads at session start) is
**version-controlled here**.

| File | Machine | How it reaches that machine |
|---|---|---|
| [`sim-desktop.md`](sim-desktop.md) + [`sim-desktop.d/`](sim-desktop.d/) | master `sim-desktop` (192.168.0.57) | **symlink** → `/home/sim/CLAUDE.md` |
| [`bc250-1.md`](bc250-1.md) | BC-250 #1 (192.168.0.43) | **symlink** → `sim@192.168.0.43:/home/sim/CLAUDE.md` |
| [`win-worker-2.md`](win-worker-2.md) | Windows worker (192.168.0.2, account `janus`) | [중요] **copy** → `C:\Users\janus\CLAUDE.md` **and** `AGENTS.md` (derived: title + refresh line only) — no repo clone there, see below |
| [`win-main-33.md`](win-main-33.md) | Windows **main work PC** (192.168.0.33, account `user`) | [중요] **copy** → `C:\Users\USER\CLAUDE.md` (no `AGENTS.md` — not created on the human's PC) |

**192.168.0.33** now has its own guide — [`win-main-33.md`](win-main-33.md) — because SSH
(account **`user`**) and Ollama came up on 2026-08-08 and there is real operating detail to carry:
the Store-stub Python trap, the UE5 checkout path, and its model limits: the coder model does not
fit (7.6 GiB free VRAM < 9.0 GB), while `gemma4:e4b` is resident since the user approved it on
2026-10-03. It is a **copy**, like `.2`.

[중요] **`.2` and `.33` are not interchangeable.** `.2` is a workshop the master may drive freely;
`.33` is the human's own machine, so the master is a guest — read-only by preference, dirty check
before anything that writes.

## [중요] `.2` is a copy, not a symlink — refresh it deliberately

`ax-cluster` is **not cloned** on the Windows worker, so there is nothing for a symlink to point
at. Cloning the whole repo there just to carry one guide file costs more than the problem, so that
machine gets a copy. **Never `scp` by hand** — one command owns every home guide (#861):

```bash
cd ~/ax-cluster
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.client home-guides            # check only (rc=1 on any DIFF/FAIL)
AX_PROJECTS_ROOT=$PWD .venv/bin/python -m master.client home-guides --apply    # back up, write copies, re-read sha256
#   --host=<ip> limits it to one machine
```

It covers all four machines from one table (`master/client/home_guides.py`): copies are written
only with `--apply` after a remote `.bak-<timestamp>`; symlinks (`.57`, `.43`) are verified, never
written; `.2`'s `AGENTS.md` is generated from `win-worker-2.md` (the hand copy drifted — on
2026-10-31 it still described a resident `AxWorker` while `CLAUDE.md` said no daemon). A failed
query is reported as FAIL, never read as "absent".

**Copies drift — that is exactly what this directory exists to prevent**, so treat this as a
known exception with a compensating check, not as the pattern to copy. When `gjc` lands and that
box needs more of the repo anyway, clone it and switch to a symlink like the other two.

## [중요] `~/CLAUDE.md` is a symlink — never turn it back into a regular file

```
/home/sim/CLAUDE.md  →  /home/sim/ax-cluster/machines/sim-desktop.md
```

**Why a link:** Claude Code auto-loads `~/CLAUDE.md` from the home directory, so the file has to
*be* there; and for version control and three-way sync it has to be *in the repo*. A link satisfies
both. Keeping copies in both places guarantees they drift — and they did: a 2026-08-08 consistency
check found the repo's `CLAUDE.md` hadn't picked up a `PLAN.md` correction and was carrying
**wrong guidance** ("AgentTest's `worker/` ports to `master/`" — it actually stays on Windows).

**Edit the file in this directory** — opening it from home edits the same file anyway.

## These files are an index, not a dump

`sim-desktop.md` is auto-loaded into **every** session, so its length is a tax on every task.
Only rules that must never be missed stay inline; detail goes in `sim-desktop.d/`.
Same principle as [`../PLAN.md`](../PLAN.md) → `docs/`.

They are written in **English on purpose**: only Claude reads them, and Korean costs roughly
2.7× the tokens for the same content (measured 2026-08-08). Work reports under
`~/ax-cluster/reports/` stay in Korean — the user reads those.

## Update procedure

After editing a machine guide, commit and **`git pull` on the other machine** for its
`~/CLAUDE.md` to catch up. The repo lives in the master and BC-250 #1 clones plus the canonical
Gitea `origin` (GitHub is only Gitea's push mirror) — check they're in sync.
For the copies (`.2`, `.33`) run `master.client home-guides` and then `--apply` (section above).

```bash
# on the master
cd ~/ax-cluster && git add machines/ && git commit && git push origin main
# on BC-250 (its main is checked out, so push is rejected — pull instead)
ssh sim@192.168.0.43 'cd ~/ax-cluster && git pull --ff-only origin main'
```

## If the link breaks

Moving or deleting the repo leaves `~/CLAUDE.md` a dangling link and **the guide silently stops
loading.** Recover with:

```bash
ln -sfn ~/ax-cluster/machines/sim-desktop.md ~/CLAUDE.md    # master
ln -sfn ~/ax-cluster/machines/bc250-1.md    ~/CLAUDE.md     # BC-250 #1
```

## What does *not* belong here

The repo root's [`../CLAUDE.md`](../CLAUDE.md) is guidance for **working in this repository** — a
different thing, not a machine guide. That's also why these files aren't named `CLAUDE.md`: a file
with that name in a subdirectory could get the wrong machine's guide auto-loaded.
