#!/bin/sh
# 마스터의 쓰기 표면 가드 — [중요] **봉인을 여는 비용이지 개선이 아니다.**
#
# [중요] **이 파일이 원본이고, `attempt.py install-hook` 이 정본 클론의 `.git/hooks/pre-push` 로
# 복사한다.** `.git/hooks/` 는 어느 저장소도 추적하지 않으므로, 훅을 그쪽에서만 고치면
# **클론을 다시 만드는 순간 가드가 조용히 사라진다** — 가드에는 최악의 실패다.
# (`events/post_receive_hook.py` 가 같은 규약을 같은 이유로 못박아 뒀다.)
#
# `origin` 의 push 는 `DISABLED://` 로 봉인돼 있다(§2.1 — 마스터는 소스 저장소에 쓰지 않는다).
# Flow Y(사용자 확정 2026-08-14)가 *"마스터가 diff 를 attempt 브랜치에 commit"* 을 요구해서
# `gitea-write` remote 를 열었고, 그 순간 봉인이 막아 주던 것 — **오발 push 를 시끄럽게 죽이는
# 것** — 을 대신할 자리가 여기다.
#
# [중요] 왜 서버가 아니라 여기냐 (실측 2026-08-14, 리포트 16 §5):
#   네 대(.57·.2·.43·.33)가 **전부 같은 Gitea 계정 `Sim`** 으로 인증한다. 등록된 것은 저장소별
#   배포키가 아니라 계정 키(`/user/keys`)다. Gitea 의 브랜치 보호 화이트리스트는 **사용자 단위**라
#   같은 계정을 쓰는 기계들을 구분할 수 없다 — 서버에 넣을 방법이 지금 구조에는 없다.
#
# 통과시키는 것:  refs/heads/attempt/*   ephemeral 시도 (성공·실패 무관, 증거 보존)
#                 refs/heads/task/*      durable — 검증 통과분만 merge 된다
# 막는 것:        그 외 전부 (특히 main)
# 삭제:           [중요] **`<remote>/main` 에서 도달 가능한 것만** (사용자 결정 2026-08-14, `#125`)
#                 예외 둘 (`#787` 사용자 승인 2026-10-10) — **그 밖의 도달 불가 삭제는 여전히 거부**:
#                 ⓐ `refs/heads/task/<W>/r<N>/<조각>` 이 `<remote>/task/<W>/base` 에서 도달 가능
#                    (⑺ 전진이 머지해 작업 브랜치에 들어갔다 = 지워도 잃는 것이 없다)
#                 ⓑ `AX_PRUNE_TERMINAL_WORK=<W>` 가 지목한 **그 work 하나**의 `refs/heads/task/<W>/*`
#                    — 큐가 rejected/cancelled 로 종결한 work. **훅은 큐를 묻지 않는다**: 판정은
#                    `work/cleanup.py terminal` 이 push 직전에 큐를 다시 읽어서 하고, 그 push 의
#                    환경에만 이 변수를 싣는다. 팁 해시는 지우기 전에 `refs/ax/pruned/` 에 보존하고
#                    저널·레드마인 노트에 남긴다(해시로 복원).
#
# [중요] 삭제 기준은 `work/cleanup.py` 가 로컬 브랜치에 쓰는 것과 **같은 것 하나**다:
#   *"그 팁이 origin/<기본브랜치> 에서 도달 가능한가"* = 정말 병합됐다 = 지워도 잃는 것이 없다.
#   도달 불가면 **그 커밋이 여기에만 있을 수 있으므로** 지우지 않는다. 판정 자체를 못 하면
#   (원격을 못 읽음·팁을 못 가져옴·git 실패) 역시 지우지 않는다 — [중요] **fail-closed 의 방향이 "보존"** 이다.
#
# [중요] **판정 기준은 로컬 추적 ref 가 아니라 원격의 실제 팁이다** (`#396`). 실측 2026-09-10:
#   로컬 `refs/remotes/gitea-write/main` 이 `c5d2c6e` 에 머문 사이 실제 main 은 `d93e7c8` 이었고,
#   가드가 이미 병합된 커밋을 *"여기에만 있을 수 있다"* 로 내놓았다 — **거짓 증거**다.
#   그래서 삭제 판정이 처음 필요할 때 **한 번만** `git ls-remote <remote>` 로 팁을 읽고, 그 커밋이
#   로컬에 없으면 그 브랜치만 fetch 한다(추적 ref 도 함께 갱신된다). 읽기·가져오기가 실패하면 거부한다.
#   삭제가 없는 push 는 네트워크를 더 쓰지 않는다. 거부 메시지는 **판정에 쓴 ref 와 해시**, 그리고
#   로컬 추적 ref 가 그와 다르면 그 해시도 찍는다 — 낡은 판정이 눈에 보이게.
#   [주의] 원격 이름(`$1`)의 **fetch URL** 로 읽는다. `gitea-write` 는 fetch·push URL 이 같다.
#   [주의] 네트워크 명령은 `</dev/null` 로 돌린다 — ssh 가 아래 루프의 stdin(ref 목록)을 먹는다.
#
# [주의] 실측이 이 기준을 골라 준 근거 (2026-08-14, 리포트 16 §9): 원격 attempt 4건이 **전부 main
# 에서 도달 불가**였고 스풀에는 그중 어느 것도 없었다. 원전대로 work 종료 시 일괄 삭제했다면
# **실패 시도 3건의 유일한 사본이 사라졌다.** 이 기준은 그것을 구조적으로 못 지운다.
#
# 되돌리기: rm <클론>/.git/hooks/pre-push
#
# [중요] **git-lfs 훅과 공존한다** (2026-08-28). `git lfs install` 은 `pre-push` 를 **자기 것으로
# 덮는다** — 실측: NS 클론의 훅이 LFS 것 세 줄뿐이었고 **우리 가드가 통째로 사라져 있었다.**
# 이 파일 머리말이 경고한 바로 그 사고다(*"클론을 다시 만드는 순간 가드가 조용히 사라진다"*).
# 반대로 우리가 그냥 덮으면 LFS 저장소(NS)의 `.uasset` push 가 깨진다. 그래서 **둘 다 돈다**:
#
#   [주의] `pre-push` 는 ref 목록을 **stdin** 으로 받는다 — 한 번 읽으면 사라진다.
#          그래서 먼저 통째로 버퍼에 담고 **두 번 먹인다.** 순서는 가드가 먼저다 —
#          거부할 push 에 LFS 업로드 비용을 치르지 않는다.

remote_name="$1"

# stdin 을 한 번만 읽는다 (아래에서 두 번 쓴다)
_refs=$(cat)

_guard() {

# 기본 브랜치 — `cleanup.py` 의 `base_branch` 와 같은 역할. 바뀌면 양쪽을 같이 고친다.
base_branch="main"

# ── 원격 실제 팁 (#396) — 목록은 한 번만 읽고, 커밋이 없을 때만 그 브랜치를 fetch 한다 ──
_ls_done=""; _ls_ok=""; _ls_out=""
_main_done=""; _main_sha=""; _main_err=""

_ls_lookup() {	# $1 = 전체 ref 이름 → 원격 해시(없으면 빈 출력)
	printf '%s\n' "$_ls_out" | while read -r _s _r; do
		if [ "$_r" = "$1" ]; then echo "$_s"; break; fi
	done
}

_remote_tip() {	# $1 = 브랜치 이름 → 성공 시 _rt_sha, 실패 시 _rt_err
	_rt_sha=""; _rt_err=""
	if [ -z "$_ls_done" ]; then
		_ls_done=1
		if _ls_out=$(git ls-remote --heads "$remote_name" </dev/null 2>/dev/null); then
			_ls_ok=1
		fi
	fi
	if [ -z "$_ls_ok" ]; then
		_rt_err="원격 '$remote_name' 을 읽지 못했다 (ls-remote 실패)"
		return 1
	fi
	_rt_sha=$(_ls_lookup "refs/heads/$1")
	if [ -z "$_rt_sha" ]; then
		_rt_err="원격 '$remote_name' 에 refs/heads/$1 이 없다"
		return 1
	fi
	if ! git cat-file -e "$_rt_sha^{commit}" 2>/dev/null; then
		git fetch -q "$remote_name" "+refs/heads/$1:refs/remotes/$remote_name/$1" \
			</dev/null >/dev/null 2>&1
		if ! git cat-file -e "$_rt_sha^{commit}" 2>/dev/null; then
			_rt_err="원격 팁 $_rt_sha (refs/heads/$1) 을 가져오지 못했다 (fetch 실패)"
			_rt_sha=""
			return 1
		fi
	fi
	return 0
}

_main_resolve() {	# 한 번만 — 두 번째부터는 저장된 값
	[ -n "$_main_done" ] && return 0
	_main_done=1
	if _remote_tip "$base_branch"; then
		_main_sha=$_rt_sha
	else
		_main_err=$_rt_err
	fi
	return 0
}

status=0
while read -r local_ref local_sha remote_ref remote_sha; do
	# 빈 줄 방어 — refspec 없이 부른 push 에서 나온다
	[ -z "$remote_ref" ] && continue

	# 삭제 (local_sha 가 전부 0) — [중요] 도달 가능한 것만 통과시킨다
	case "$local_sha" in
	*[!0]*) ;;
	*)
		case "$remote_ref" in
		refs/heads/attempt/*|refs/heads/task/*) ;;
		*)
			echo "[중요] pre-push 거부: $remote_ref 삭제 — 우리 브랜치가 아니다" >&2
			status=1
			continue
			;;
		esac

		tracking="refs/remotes/$remote_name/$base_branch"
		_main_resolve	# #396 — 로컬 추적 ref 가 아니라 원격의 실제 팁으로 잰다
		if [ -n "$_main_sha" ] &&
		   git merge-base --is-ancestor "$remote_sha" "$_main_sha" 2>/dev/null; then
			continue	# 병합됐다 — 지워도 잃는 것이 없다
		fi

		# 예외 ⓐ (#787) — ⑺ 전진이 머지한 서브 브랜치: 작업 브랜치에서 도달 가능하면 통과
		_w=""; _rest=""; _rnd=""; _leaf=""
		case "$remote_ref" in
		refs/heads/task/*/r*/*)
			_rest=${remote_ref#refs/heads/task/}
			_w=${_rest%%/*}; _rest=${_rest#*/}
			_rnd=${_rest%%/*}; _leaf=${_rest#*/}
			;;
		esac
		case "$_rnd" in r|r*[!0-9]*) _rnd="" ;; esac
		case "$_leaf" in ""|*/*) _rnd="" ;; esac
		case "$_w" in ""|*[!A-Za-z0-9_.-]*) _rnd="" ;; esac
		if [ -n "$_rnd" ]; then
			# 작업 브랜치도 원격 실제 팁으로 잰다 (#396 — 목록은 위에서 읽은 것을 다시 쓴다)
			if _remote_tip "task/$_w/base" &&
			   git merge-base --is-ancestor "$remote_sha" "$_rt_sha" 2>/dev/null; then
				echo "[주의] pre-push 허용: $remote_ref 삭제 — $remote_name refs/heads/task/$_w/base ($_rt_sha) 에서 도달 가능 (#787 ⓐ, 팁 $remote_sha)" >&2
				continue
			fi
		fi

		# 예외 ⓑ (#787) — 큐가 종결(rejected/cancelled)한 work 하나. 이름 검사가 판정의 전부다
		_tw="${AX_PRUNE_TERMINAL_WORK:-}"
		case "$_tw" in ""|[!A-Za-z0-9]*|*[!A-Za-z0-9_.-]*) _tw="" ;; esac
		if [ -n "$_tw" ]; then
			case "$remote_ref" in
			"refs/heads/task/$_tw/"?*)
				echo "[주의] pre-push 허용: $remote_ref 삭제 — 종결 work $_tw (#787 ⓑ, 팁 $remote_sha)" >&2
				continue
				;;
			esac
		fi

		_track_sha=$(git rev-parse --verify --quiet "$tracking" 2>/dev/null)
		if [ -z "$_main_sha" ]; then
			echo "[중요] pre-push 거부: $remote_ref 삭제 — 판정 기준(원격 $base_branch 의 실제 팁)을 못 얻었다" >&2
			echo "   사유: $_main_err" >&2
			echo "   로컬 추적 ref $tracking = ${_track_sha:-없음} — 낡았을 수 있어 판정에 쓰지 않는다 (#396)" >&2
			echo "   판정을 못 하면 보존한다 (fail-closed). 원격 연결을 확인한 뒤 다시 push 한다" >&2
		else
			echo "[중요] pre-push 거부: $remote_ref 삭제 — 원격 $base_branch 에 병합되지 않았다" >&2
			echo "   판정 기준: $remote_name refs/heads/$base_branch = $_main_sha (ls-remote 로 읽은 실제 팁, #396)" >&2
			if [ "$_track_sha" != "$_main_sha" ]; then
				echo "   [주의] 로컬 추적 ref $tracking = ${_track_sha:-없음} — 실제 팁과 다르다(낡았다), 판정에 쓰지 않았다" >&2
			fi
			echo "   그 커밋($remote_sha)이 여기에만 있을 수 있다 — 증거다" >&2
			echo "   지울 근거가 생기면 사람이 판단한다 (#125 사용자 결정 2026-08-14)" >&2
		fi
		status=1
		continue
		;;
	esac

	case "$remote_ref" in
	refs/heads/attempt/*|refs/heads/task/*)
		;;
	*)
		echo "[중요] pre-push 거부: $remote_ref → remote '$remote_name'" >&2
		echo "   마스터가 쓸 수 있는 것은 refs/heads/attempt/* · refs/heads/task/* 뿐이다 (§2.1)" >&2
		echo "   main 을 옮기는 것은 사람의 자리다 — 요청자(.33)에서 한다" >&2
		status=1
		;;
	esac
done

[ $status -ne 0 ] && echo "   (가드를 지우지 말 것. 근거 = reports/16-master-write-surface.md §5)" >&2
	return $status
}

printf '%s\n' "$_refs" | _guard
_g=$?
if [ $_g -ne 0 ]; then
	exit $_g
fi

# ── LFS 위임 — [중요] 가드가 통과했을 때만 ──
if command -v git-lfs >/dev/null 2>&1; then
	printf '%s\n' "$_refs" | git lfs pre-push "$@"
	exit $?
fi
# [중요] **조용히 넘기지 않는다.** LFS 저장소에서 git-lfs 없이 push 하면 포인터만 올라가
# 나중에 smudge 가 죽는다(`#313` 이 그 부류였다). 우리 가드는 이미 통과시켰으므로 막지는
# 않되, 사실을 크게 말한다.
if [ -f .gitattributes ] && grep -q "filter=lfs" .gitattributes 2>/dev/null; then
	echo "[중요] 이 저장소는 LFS 를 쓰는데 git-lfs 가 PATH 에 없다 — LFS 오브젝트가 안 올라간다" >&2
fi
exit 0
