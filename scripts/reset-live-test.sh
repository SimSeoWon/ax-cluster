#!/usr/bin/env bash
# 실증 출발점 초기화 — [중요] **표면을 한 번에 전부** 훑는다
#
# 근거: 메모리 `live_test_starts_clean` — *"실증 테스트 중 무언가 실패하면 고쳐서 이어가지
# 않는다. 전부 지우고 처음부터"* · *"지울 때는 표면을 한 번에 전부 훑는다. 하나씩 지우고
# 「끝났다」고 말하면 다음 실행에서 또 걸린다(그날 네 번 걸렸다)"*.
#
# [중요] **왜 스크립트인가.** 2026-09-03 한 세션에서 이 절차를 손으로 세 번 돌렸고, 매번
# 빠뜨린 표면이 달랐다(워커 로컬 헤드 · `origin` 캐시 · `.33` 워크트리). 손으로 하면 빠진다.
#
# 사용법:  scripts/reset-live-test.sh <프로젝트>              계획만 (아무것도 안 지운다)
#          scripts/reset-live-test.sh <프로젝트> --apply       실행
#          ... --apply --redmine 351,352                      그 이슈도 지운다 (id 명시만)
#
# [주의] **레드마인은 id 를 명시해야만 지운다.** 2026-09-03 에 목록째 지워서 실증과 무관한
# 이슈 셋(`#299`·`#300`·`#302`)을 잃었다 — 복구 불가였다. 무엇인지 보고 고르는 것이 사람 몫이다.
#
# [주의] **사람의 미커밋 파일은 절대 건드리지 않는다** (`.33` 의 `.uasset`·`.uproject`).
# 되살릴 수 없는 것이고, `ax-review` 문서가 그 사고를 이미 기록해 뒀다.

set -uo pipefail

PROJ="${1:-}"
shift || true
APPLY=0
REDMINE_IDS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --apply)   APPLY=1 ;;
    --redmine) shift; REDMINE_IDS="${1:-}" ;;
    *) printf '[중요] 모르는 인자: %s\n' "$1" >&2; exit 2 ;;
  esac
  shift
done

if [ -z "$PROJ" ]; then
  cat >&2 <<'USAGE'
  scripts/reset-live-test.sh <프로젝트> [--apply] [--redmine <id,id>]
  [중요] 프로젝트 인자는 필수다 — 폴백은 없다 (남의 프로젝트를 지우지 않기 위해서다)
USAGE
  exit 2
fi

REPO="${AX_REPO:-$HOME/ax-cluster}"
TWIN="$REPO/$PROJ"
MIRROR="$TWIN/repo"
QUEUE_ROOT="${AX_TASK_QUEUE_ROOT:-$HOME/ax-state}"
HOLD="$HOME/.cache/ax-dispatch/hold.json"

[ -d "$MIRROR/.git" ] || { printf '[중요] 트윈 미러가 없다: %s\n' "$MIRROR" >&2; exit 2; }

mode() { [ "$APPLY" -eq 1 ] && printf '실행' || printf '계획'; }
hdr()  { printf '\n── %s ─────────────────────────────────────\n' "$1"; }
do_it() { if [ "$APPLY" -eq 1 ]; then "$@"; else printf '   (계획) %s\n' "$*"; fi; }

printf '실증 초기화 [%s] — 프로젝트 %s\n' "$(mode)" "$PROJ"

# ── 1. 깃티 task/* 브랜치 ─────────────────────────────────────────────────────────
# [주의] pre-push 훅(`#125`)이 **미병합 tip 삭제를 거부**한다. 그 판정은 옳고, 훅을 지우지
# 않는다 — 실증 잔재를 지우는 것은 사람이 판단한 자리이므로 이번 삭제만 `--no-verify` 로 넘긴다.
hdr "1. 깃티 task/* 브랜치"
cd "$MIRROR" || exit 2
branches=$(git ls-remote --heads gitea-write 2>/dev/null | awk '{print $2}' \
           | sed 's|refs/heads/||' | grep '^task/' || true)
if [ -z "$branches" ]; then
  printf '   없음\n'
else
  printf '%s\n' "$branches" | sed 's/^/   /'
  if [ "$APPLY" -eq 1 ]; then
    printf '%s\n' "$branches" | while read -r b; do
      [ -n "$b" ] && git push --no-verify gitea-write --delete "$b" 2>&1 \
        | grep -E 'deleted|error' | sed 's/^/     /'
    done
  fi
fi

# ── 2. 큐 — [중요] API 에 삭제가 없다. 디렉토리를 지우고 **재기동**해야 인덱스가 다시 읽는다 ──
hdr "2. 큐 상태 + 재기동"
n=$(find "$QUEUE_ROOT" -maxdepth 3 -name '_request.md' 2>/dev/null | wc -l)
printf '   work 레코드 %s개 · %s\n' "$n" "$QUEUE_ROOT"
if [ "$APPLY" -eq 1 ]; then
  rm -rf "$QUEUE_ROOT" && mkdir -p "$QUEUE_ROOT"
  sudo -n /usr/bin/systemctl restart ax-task-queue
  sleep 4
  # [중요] 판정은 종료코드가 아니라 **ExecMainStartTimestamp** 다 (`CLAUDE.md` § 운영)
  printf '   재기동 %s\n' "$(systemctl show ax-task-queue -p ExecMainStartTimestamp --value)"
else
  printf '   (계획) rm -rf %s && systemctl restart ax-task-queue\n' "$QUEUE_ROOT"
fi

# ── 3. 보류 — 재부팅을 넘고 시각이 지나도 자동으로 안 풀린다 ──────────────────────
hdr "3. 파견 보류"
if [ -f "$HOLD" ]; then printf '   %s\n' "$(cat "$HOLD")"; do_it rm -f "$HOLD"; else printf '   없음\n'; fi

# ── 4. 트윈 스풀 ────────────────────────────────────────────────────────────────
hdr "4. 트윈 스풀 ($PROJ)"
for d in responses worker_logs reviews manifests; do
  c=$(ls "$TWIN/$d" 2>/dev/null | wc -l)
  printf '   %-12s %s개\n' "$d" "$c"
  [ "$c" -gt 0 ] && [ "$APPLY" -eq 1 ] && rm -rf "$TWIN/$d"/*
done
if [ -f "$TWIN/failure-catalog.json" ]; then
  fc=$(python3 -c "import json;print(len(json.load(open('$TWIN/failure-catalog.json'))))" 2>/dev/null || echo '?')
  printf '   %-12s %s건\n' failure-catalog "$fc"
  if [ "$APPLY" -eq 1 ]; then
    cp "$TWIN/failure-catalog.json" "$TWIN/failure-catalog.bak.json"
    printf '[]' > "$TWIN/failure-catalog.json"
    printf '     (백업: failure-catalog.bak.json)\n'
  fi
fi

# ── 5. 클론들 — [중요] **로컬 헤드까지** 본다. `for-each-ref` 전수다 ────────────────
# [주의] 2026-09-03 실측: `refs/remotes/origin/task` 만 보고 「깨끗하다」고 보고했는데
# `refs/heads/task/*` 가 워커마다 남아 있었다. 그리고 prune 은 **리모트별**이다 —
# `origin` 만 걷고 `gitea-write` 캐시를 원격 사실로 읽어 또 틀렸다.
hdr "5. 마스터 트윈 미러"
git for-each-ref --format='   %(refname)' | grep -v 'refs/tags/'
if [ "$APPLY" -eq 1 ]; then
  for r in $(git remote); do git remote prune "$r" >/dev/null 2>&1; done
  for r in $(git for-each-ref --format='%(refname)' refs/ax 2>/dev/null); do
    git update-ref -d "$r" && printf '   삭제 %s\n' "$r"
  done
  git reflog expire --expire=now --all; git gc --prune=now -q
  printf '   ── 정리 후 ──\n'; git for-each-ref --format='   %(refname)' | grep -v 'refs/tags/'
fi

# 작업장들 — 레지스트리의 config.yaml 에서 읽는다 (하드코딩하지 않는다)
# [주의] **`ssh -n` 이 필수다.** `ssh` 는 stdin 을 읽으므로 `while read` 루프 안에서 쓰면
#    루프의 입력을 먹어치우고 **첫 작업장만 처리하고 끝난다** (실측 2026-09-03: `.2` 만 나왔다).
hdr "6. 작업장 클론 (레지스트리 기준)"
python3 - "$TWIN/config.yaml" <<'PY' | while IFS='|' read -r host user path role; do
import sys, yaml
cfg = yaml.safe_load(open(sys.argv[1], encoding='utf-8')) or {}
for host, w in (cfg.get('workshops') or {}).items():
    print(f"{host}|{w.get('user','')}|{w.get('path','')}|{w.get('role','')}")
PY
  [ -z "$host" ] && continue
  printf '   -- %s (%s · %s)\n' "$host" "$role" "$path"
  case "$path" in
    /*) # 리눅스 작업장
      cmd='cd "'"$path"'" && git for-each-ref --format="%(refname)" | grep -v refs/tags/ && echo "branch=$(git branch --show-current) dirty=$(git status --short|wc -l)"' ;;
    *)  # 윈도우 — [주의] `python -c` 는 Store 스텁이라 못 쓴다. git 만 부른다
      cmd='cd /d "'"$path"'" && git for-each-ref --format="%(refname)" && echo branch: && git branch --show-current && echo dirty: && git status --short' ;;
  esac
  timeout 60 ssh -n -o BatchMode=yes -o ConnectTimeout=10 "$user@$host" "$cmd" 2>&1 | sed 's/^/     /'
  if [ "$APPLY" -eq 1 ]; then
    case "$path" in
      /*) clean='cd "'"$path"'"; git remote prune origin >/dev/null 2>&1
          for b in $(git for-each-ref --format="%(refname:short)" refs/heads | grep "^task/"); do git branch -D "$b"; done
          for r in $(git for-each-ref --format="%(refname)" refs/ax 2>/dev/null); do git update-ref -d "$r"; echo "삭제 $r"; done
          for w in $(git worktree list --porcelain | awk "/^worktree/{print \$2}" | grep -v "^'"$path"'$"); do git worktree remove --force "$w" && echo "워크트리 삭제 $w"; done
          git worktree prune; rm -rf .ax/work/* 2>/dev/null
          git reflog expire --expire=now --all; git gc --prune=now -q
          echo "-- 정리 후 --"; git for-each-ref --format="%(refname)" | grep -v refs/tags/
          echo "branch=$(git branch --show-current) dirty=$(git status --short|wc -l)"' ;;
      *)  clean='' ;;   # [주의] 윈도우는 아래에서 한 줄씩 처리한다 (cmd for 문이 ssh 를 타면 깨진다)
    esac
    # [주의] 윈도우는 cmd 의 for/따옴표가 ssh 를 타면 깨진다(실측) — 브랜치 열거 후 한 줄씩 지운다
    case "$path" in
      /*) timeout 90 ssh -n -o BatchMode=yes "$user@$host" "$clean" 2>&1 | sed 's/^/     /' ;;
      *)  wt=$(timeout 60 ssh -n -o BatchMode=yes "$user@$host" \
                 'cd /d "'"$path"'" && git worktree list --porcelain' 2>/dev/null \
               | awk '/^worktree/{print $2}' | grep -vi "^${path//\\/\/}$" || true)
          for w in $wt; do
            timeout 60 ssh -n -o BatchMode=yes "$user@$host" \
              'cd /d "'"$path"'" && git worktree remove --force "'"$w"'"' 2>&1 | sed 's/^/     /'
          done
          bs=$(timeout 60 ssh -n -o BatchMode=yes "$user@$host" \
                 'cd /d "'"$path"'" && git for-each-ref --format="%(refname:short)" refs/heads' 2>/dev/null \
               | tr -d '\r' | grep '^task/' || true)
          for b in $bs; do
            timeout 60 ssh -n -o BatchMode=yes "$user@$host" \
              'cd /d "'"$path"'" && git branch -D "'"$b"'"' 2>&1 | sed 's/^/     /'
          done
          timeout 60 ssh -n -o BatchMode=yes "$user@$host" \
            'cd /d "'"$path"'" && git remote prune origin && git worktree prune && git reflog expire --expire=now --all && git gc --prune=now -q && echo "-- 정리 후 --" && git for-each-ref --format="%(refname)" && echo dirty: && git status --short' 2>&1 | sed 's/^/     /' ;;
    esac
  fi
done

# ── 7. 레드마인 — [주의] id 를 명시해야만 지운다 ────────────────────────────────
hdr "7. 레드마인 ($PROJ)"
KEY=$(docker exec redmine-db-1 psql -U redmine -d redmine -tAc \
        "select value from tokens where action='api' limit 1" 2>/dev/null | tr -d ' \n')
RP=$(python3 -c "
import sys, yaml
cfg = yaml.safe_load(open('$TWIN/config.yaml', encoding='utf-8')) or {}
print(((cfg.get('redmine') or {}).get('project') or '').strip())" 2>/dev/null)
if [ -z "$KEY" ] || [ -z "$RP" ]; then
  printf '   [주의] 키 또는 redmine.project 를 못 읽었다 — 건너뛴다 (키=%s 프로젝트=%s)\n' \
         "${KEY:+있음}${KEY:-없음}" "${RP:-없음}"
else
  curl -s -H "X-Redmine-API-Key: $KEY" \
    "http://127.0.0.1:8080/issues.json?project_id=$RP&status_id=*&limit=25" \
    | python3 -c "
import json,sys
d=json.load(sys.stdin)
for i in d.get('issues',[]): print(f\"   #{i['id']} {i['created_on'][:16]} {i['subject'][:60]}\")
print('   total', d.get('total_count'))"
  if [ -n "$REDMINE_IDS" ] && [ "$APPLY" -eq 1 ]; then
    for id in ${REDMINE_IDS//,/ }; do
      curl -s -o /dev/null -w "   DELETE #$id → %{http_code}\n" -X DELETE \
        -H "X-Redmine-API-Key: $KEY" "http://127.0.0.1:8080/issues/$id.json"
    done
  elif [ -n "$REDMINE_IDS" ]; then
    printf '   (계획) DELETE %s\n' "$REDMINE_IDS"
  else
    printf '   [주의] --redmine 이 없어 아무것도 지우지 않았다 (무엇인지 보고 고르는 것이 사람 몫)\n'
  fi
fi

printf '\n[%s] 끝\n' "$( [ "$APPLY" -eq 1 ] && printf 완료 || printf 계획 )"
[ "$APPLY" -eq 1 ] || printf '실행하려면 --apply\n'
