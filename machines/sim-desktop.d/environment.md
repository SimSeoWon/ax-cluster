# sim-desktop — 환경·권한 메모

색인: [`../sim-desktop.md`](../sim-desktop.md) (= 마스터의 `~/CLAUDE.md`)

## PATH

`~/.local/bin` 은 `~/.bashrc` 의 명시적 블록으로 PATH 에 들어간다 (2026-08-02 추가).
`~/.profile` 에도 있지만 `.profile` 은 로그인 셸에서만 실행되므로,
평범한 새 터미널은 그 블록이 없으면 `claude` 바이너리를 못 찾았다.

## 🔴 sudo 와 pkexec 는 다르다 — 혼동하지 말 것

이 머신의 `sudo` 는 비밀번호가 필요하다(NOPASSWD 없음). **하지만 `pkexec <cmd>` 는 된다** —
사용자 화면에 인증 대화상자가 뜨고, 승인하면 root 권한이 부여된다.

- `run_in_background: true` 로 실행하고 **사용자에게 화면을 보라고 알릴 것**
- **`pkexec` 를 시도해 보기 전에 "권한이 필요해서 불가능하다"고 선언하지 말 것**
- 사용자에게 명령을 떠넘기지 말고 마스터에서 직접 처리한다

BC-250 쪽은 진짜로 막혀 있다 — 2026-08-05 부터 헤드리스라 인증 에이전트가 존재할 수 없다.
그쪽 절차는 [`bc250-access.md`](bc250-access.md) 참조.

## Python

`python3-venv` 와 `python3-pip` 는 기본 설치가 **아니었다**. 2026-08-08 에 `pkexec apt-get install`
로 추가했다. AX 클러스터의 venv 는 `~/ax-cluster/.venv`.

## GPU

NVIDIA GT 1030 (2GB). **드라이버가 설치돼 있지 않다** — `nvidia-smi` 는 실패한다.
CUDA 가 필요한 것은 무엇이든 드라이버 설치가 선결이다.
GTX 1070 증설 검토는 [`../../docs/7-master-gpu.md`](../../docs/7-master-gpu.md).
