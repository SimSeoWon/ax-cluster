#!/usr/bin/env bash
# 세 클론 동기 — 마스터 → GitHub → BC-250 #1
#
# [중요] **왜 스크립트인가.** `CLAUDE.md` § Three clones 가 *"셋을 맞춘 상태로 둔다"* 이고,
# 메모리 `sudo_privilege_handling` 이 *"사용자에게 명령을 떠넘기지 말 것"* 이다. 그런데 대화형
# 세션에서 `git push` 를 직접 부르면 막히는 경우가 있어(2026-09-03 실측) 매번 사람에게 두 줄을
# 적어 주고 있었다 — 그것이 규칙 위반이었다. 절차를 여기 고정한다.
#
# [주의] **`.43` 은 `main` 이 체크아웃돼 있어 push 가 거부된다** — 그쪽은 `pull` 이다
# (`CLAUDE.md`: *"The board has `main` checked out, so pushing to it is rejected"*).
#
# [중요] **판정은 커밋 해시 3개가 같은가로 한다** (메모리 `live_test_starts_clean` ⑸:
# *"정리 뒤 `.57 = GitHub = .43` 을 커밋 해시로 확인한다"*). "push 했다" 는 확인이 아니다.
#
# 사용법:  scripts/sync-clones.sh            검사 + 동기
#          scripts/sync-clones.sh --check    검사만 (아무것도 바꾸지 않는다)

set -uo pipefail

REPO="${AX_REPO:-$HOME/ax-cluster}"
NODE="${AX_NODE:-sim@192.168.0.43}"
NODE_REPO="${AX_NODE_REPO:-ax-cluster}"
BRANCH="${AX_BRANCH:-main}"
CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

say() { printf '%s\n' "$*"; }
fail() { printf '[중요] %s\n' "$*" >&2; }

cd "$REPO" || { fail "저장소가 없다: $REPO"; exit 2; }

# ── 0. 로컬이 깨끗한가 — 미커밋을 두고 동기하면 무엇이 올라갔는지 모른다 ──────────
dirty=$(git status --porcelain | wc -l)
local_sha=$(git rev-parse "$BRANCH")
say "[로컬]   $REPO"
say "         $BRANCH = ${local_sha:0:12} · 미커밋 ${dirty}개"
if [ "$dirty" -ne 0 ]; then
  fail "미커밋이 ${dirty}개다 — 커밋 승인을 먼저 받아야 한다. 동기하지 않는다."
  git status --short | sed 's/^/         /'
  exit 1
fi

# ── 1. 실물 조회 — [주의] 로컬 트래킹 ref 는 원격이 아니다 (2026-09-03 실측 오류) ──
gh_sha=$(git ls-remote --heads origin "$BRANCH" 2>/dev/null | awk '{print $1}')
nd_sha=$(git ls-remote --heads node "$BRANCH" 2>/dev/null | awk '{print $1}')
say "[GitHub] ${gh_sha:0:12}${gh_sha:+ }${gh_sha:-(조회 실패)}"
say "[.43]    ${nd_sha:0:12}${nd_sha:+ }${nd_sha:-(조회 실패)}"

if [ "$local_sha" = "$gh_sha" ] && [ "$local_sha" = "$nd_sha" ]; then
  say "[완료] 셋이 같다 — 할 일이 없다"
  exit 0
fi
if [ "$CHECK_ONLY" -eq 1 ]; then
  say "[주의] 어긋나 있다 (--check 라 아무것도 바꾸지 않았다)"
  exit 1
fi

rc=0

# ── 2. GitHub push — [주의] force 는 쓰지 않는다. 거부되면 사람이 판단한다 ─────────
if [ "$local_sha" != "$gh_sha" ]; then
  say "→ GitHub push"
  if git push origin "$BRANCH" 2>&1 | sed 's/^/         /'; then
    :
  else
    fail "GitHub push 실패 — force 하지 않는다. 사람이 판단할 자리다"; rc=1
  fi
fi

# ── 3. `.43` 은 pull (그쪽은 main 체크아웃 상태라 push 가 거부된다) ────────────────
if [ "$local_sha" != "$nd_sha" ]; then
  say "→ .43 pull --ff-only"
  if ssh -o BatchMode=yes -o ConnectTimeout=10 "$NODE" \
       "cd ~/$NODE_REPO && git pull --ff-only" 2>&1 | sed 's/^/         /'; then
    :
  else
    fail ".43 pull 실패 — ff 가 안 되면 그쪽에 로컬 커밋이 있다. 사람이 판단할 자리다"; rc=1
  fi
fi

# ── 4. [중요] 해시로 증명한다 — "돌렸다" 가 아니라 "같아졌다" 를 본다 ──────────────
say "── 동기 후 실측 ──"
gh2=$(git ls-remote --heads origin "$BRANCH" 2>/dev/null | awk '{print $1}')
nd2=$(git ls-remote --heads node "$BRANCH" 2>/dev/null | awk '{print $1}')
say "[로컬]   ${local_sha:0:12}"
say "[GitHub] ${gh2:0:12}"
say "[.43]    ${nd2:0:12}"
if [ "$local_sha" = "$gh2" ] && [ "$local_sha" = "$nd2" ]; then
  say "[완료] 셋이 같다"
  exit "$rc"
fi
fail "아직 어긋난다 — 위 해시를 보라"
exit 1
