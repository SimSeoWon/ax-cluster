# machines — canonical copies of the per-machine Claude Code guides

Each machine's `~/CLAUDE.md` (the file Claude Code auto-loads at session start) is
**version-controlled here**.

| File | Machine | Link in its home |
|---|---|---|
| [`sim-desktop.md`](sim-desktop.md) + [`sim-desktop.d/`](sim-desktop.d/) | master `sim-desktop` (192.168.0.57) | `/home/sim/CLAUDE.md` |
| [`bc250-1.md`](bc250-1.md) | BC-250 #1 (192.168.0.43) | `sim@192.168.0.43:/home/sim/CLAUDE.md` |

## 🔴 `~/CLAUDE.md` is a symlink — never turn it back into a regular file

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
`~/claude-workspace/reports/` stay in Korean — the user reads those.

## Update procedure

After editing a machine guide, commit and **`git pull` on the other machine** for its
`~/CLAUDE.md` to catch up. The repo lives in three places (master, BC-250 #1, GitHub) — check
they're in sync.

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
