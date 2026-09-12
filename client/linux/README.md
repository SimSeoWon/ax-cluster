# `client/linux/` — 리눅스에서만 의미 있는 스크립트

규약은 `../windows/README.md` 와 같다: **로직은 `client/runtime/` 의 파이썬에, 여기에는
OS 파일만 최소로.** 등록 명령은 `client/init/residency.py` 가 조립한다.

## [주의] 리눅스는 윈도우의 세션 0 문제가 **없다**

실측 2026-09-12: `.43` 은 SSH 로 `codex exec` 도 `ax-client` MCP 도 완주한다
(`get_anti_patterns (completed)`). 여기서 데몬이 필요한 이유는 세션 문제가 아니라
**정본 ⑸**(워커가 끝내고 다음 작업을 요청한다)뿐이다 — 그래서 윈도우와 **같이 배선하지
않아도 된다.**

## 🔴 [중요] `loginctl enable-linger` 가 대칭 함정이다

윈도우의 `/IT` 에 대응하는 자리다. `systemd --user` 유닛은 **로그인 세션이 끝나면 같이
죽는다.** 실측 2026-09-12 `.43` 은 `Linger=no` 이므로, 그대로 배선하면 SSH 가 끊길 때
데몬이 **조용히** 죽는다. 등록 단계에서 linger 를 같이 건다.
