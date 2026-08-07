# machines — 머신별 Claude Code 가이드의 정본

각 머신 홈의 `~/CLAUDE.md`(Claude Code 가 세션 시작 시 자동 로드하는 파일)를 **여기서 버전 관리**한다.

| 파일 | 머신 | 홈의 링크 |
|---|---|---|
| [`sim-desktop.md`](sim-desktop.md) | 마스터 `sim-desktop` (192.168.0.57) | `/home/sim/CLAUDE.md` |
| [`bc250-1.md`](bc250-1.md) | BC-250 #1 (192.168.0.43) | `sim@192.168.0.43:/home/sim/CLAUDE.md` |

## 🔴 홈의 `~/CLAUDE.md` 는 심볼릭 링크다 — 일반 파일로 되돌리지 말 것

```
/home/sim/CLAUDE.md  →  /home/sim/ax-cluster/machines/sim-desktop.md
```

**왜 링크인가:** Claude Code 는 `~/CLAUDE.md` 를 홈에서 자동 로드하므로 파일이 거기 *있어야* 하고,
동시에 버전 관리·3자 동기가 되려면 저장소 안에 *있어야* 한다. 링크가 둘을 동시에 만족시킨다.
복사본을 양쪽에 두면 반드시 갈라진다 — 실제로 2026-08-08 정합성 점검에서
저장소 `CLAUDE.md` 가 `PLAN.md` 의 정정을 반영하지 못해 **틀린 지침**을 담고 있었다.

**편집은 이 디렉터리의 파일을 고치면 된다** — 홈에서 열어 고쳐도 같은 파일이다.

## 갱신 절차

머신 가이드를 고쳤으면 커밋하고 **다른 머신에서 `git pull`** 해야 그쪽 `~/CLAUDE.md` 가 최신이 된다.
저장소가 세 곳(마스터·BC-250 #1·GitHub)에 있으므로 동기 상태를 확인할 것.

```bash
# 마스터에서
cd ~/ax-cluster && git add machines/ && git commit && git push origin main
# BC-250 에서 (그쪽 main 은 체크아웃돼 있어 push 가 거부된다 — pull 로 받는다)
ssh sim@192.168.0.43 'cd ~/ax-cluster && git pull --ff-only origin main'
```

## 링크가 끊어졌을 때

저장소를 옮기거나 지우면 `~/CLAUDE.md` 가 깨진 링크가 되고 **가이드가 로드되지 않는다.**
복구:

```bash
ln -sfn ~/ax-cluster/machines/sim-desktop.md ~/CLAUDE.md    # 마스터
ln -sfn ~/ax-cluster/machines/bc250-1.md    ~/CLAUDE.md     # BC-250 #1
```

## 여기 두지 않는 것

저장소 루트의 [`../CLAUDE.md`](../CLAUDE.md) 는 **이 저장소에서 작업할 때의 지침**이고 성격이 다르다
(머신 가이드가 아니다). 파일명을 `CLAUDE.md` 로 짓지 않은 이유이기도 하다 —
하위 디렉터리에 그 이름이 있으면 엉뚱한 머신의 가이드가 자동 로드될 수 있다.
