# BC-250 inference node — remote access from the master

Index: [`../sim-desktop.md`](../sim-desktop.md) (= the master's `~/CLAUDE.md`)

Passwordless SSH is configured (`~/.ssh/id_rsa` → `sim@192.168.0.43`).

```bash
ssh sim@192.168.0.43                                    # shell
curl http://192.168.0.43:11434/api/tags                 # model list
curl http://192.168.0.43:11434/api/generate -d '{...}'  # inference
```

## Two things that regularly trip up remote work on that board

### 1. `sudo` there needs a password and there is no TTY

A heredoc piped over SSH **consumes stdin**, so `sudo -S` never sees the password.
Write the script to the remote host **first**, then run it:

```bash
ssh sim@192.168.0.43 'cat > /tmp/x.sh' << 'EOF'
...script...
EOF
printf '%s\n' "$PW" | ssh sim@192.168.0.43 'chmod +x /tmp/x.sh && sudo -S -p "" /tmp/x.sh'
```

⚠️ That board's own `~/CLAUDE.md` still documents a `pkexec` + graphical-polkit pattern —
**that is stale.** It went headless (`multi-user.target`) on 2026-08-05, so there is no desktop
session to show a polkit dialog.

### 2. Its Ollama port 11434 accepts only 192.168.0.57

The firewall there allows this machine and nothing else. Adding another client means adding a
firewalld rich rule on that board.

## 🔴 Before touching that board's hardware config

Read `sim@192.168.0.43:~/bc250-backup-staging/reports/*.md` before changing CU unlock, SMU OC,
governor, or boot params. It carries hard-won constraints, and that board's `CLAUDE.md` mandates
**reading those reports in full rather than grepping** — there is an incident where near-miss
wording was filtered out and already-recorded work got re-investigated from scratch.
