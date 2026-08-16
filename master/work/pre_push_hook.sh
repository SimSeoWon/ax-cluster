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
#
# [중요] 삭제 기준은 `work/cleanup.py` 가 로컬 브랜치에 쓰는 것과 **같은 것 하나**다:
#   *"그 팁이 origin/<기본브랜치> 에서 도달 가능한가"* = 정말 병합됐다 = 지워도 잃는 것이 없다.
#   도달 불가면 **그 커밋이 여기에만 있을 수 있으므로** 지우지 않는다. 판정 자체를 못 하면
#   (tracking ref 없음·git 실패) 역시 지우지 않는다 — [중요] **fail-closed 의 방향이 "보존"** 이다.
#
# [주의] 실측이 이 기준을 골라 준 근거 (2026-08-14, 리포트 16 §9): 원격 attempt 4건이 **전부 main
# 에서 도달 불가**였고 스풀에는 그중 어느 것도 없었다. 원전대로 work 종료 시 일괄 삭제했다면
# **실패 시도 3건의 유일한 사본이 사라졌다.** 이 기준은 그것을 구조적으로 못 지운다.
#
# 되돌리기: rm <클론>/.git/hooks/pre-push

remote_name="$1"

# 기본 브랜치 — `cleanup.py` 의 `base_branch` 와 같은 역할. 바뀌면 양쪽을 같이 고친다.
base_branch="main"

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
		if ! git rev-parse --verify --quiet "$tracking" >/dev/null; then
			echo "[중요] pre-push 거부: $remote_ref 삭제 — $tracking 이 없어 도달 여부를 못 잰다" >&2
			echo "   판정을 못 하면 보존한다 (fail-closed). 먼저: git fetch $remote_name" >&2
			status=1
			continue
		fi

		if git merge-base --is-ancestor "$remote_sha" "$tracking"; then
			:	# 병합됐다 — 지워도 잃는 것이 없다
		else
			echo "[중요] pre-push 거부: $remote_ref 삭제 — $tracking 에 병합되지 않았다" >&2
			echo "   그 커밋($remote_sha)이 여기에만 있을 수 있다 — 증거다" >&2
			echo "   지울 근거가 생기면 사람이 판단한다 (#125 사용자 결정 2026-08-14)" >&2
			status=1
		fi
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
exit $status
