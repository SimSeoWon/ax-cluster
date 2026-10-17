# #815 — 기존 실패 2건 해소, 전수 실패 0

2026-10-17 21:15 ~ 21:30 · Claude · 마스터 담당 `codex`·워커 모드 `codex`는 바꾸지 않았다. 사용자 선택에 따라
**기존 실패 2건부터** 처리했고, 구현은 **로컬 서브 에이전트**가 했다. diff·전수·설치는 마스터가 직접 대조했다.

## 착수 전 — 남은 항목과 두 실패의 원인

#815에 남은 항목은 ①동작 정합(작업 방식 결정 필요) · ②mypy 오탐 측정 · ④층2 `[PSEUDO]` 이행 · ⑤⑦ 회귀
선택 보강 · ⑥공식 목록 확대(`test_client_bundle` 격리 픽스처가 먼저)였다. 여기에 커밋마다 걸리던 실패 2건이 있었다.
2건의 원인은 서로 반대였다.

| 파일 | 어느 쪽이 틀렸나 | 근거 |
|---|---|---|
| `test_mount_gate` | **테스트가 낡았다** | 소스를 `"if not batch.events:"`로 잘라 읽는데, 그 분기는 `if not res.results:`로 바뀌었다(`consumer.py:1316`). 검사 대상인 동작(마운트만 돈다 · `res.unmounted`)은 그대로 있다 |
| `test_sandbox` | **테스트가 맞았다** | 10-03에 생긴 최상위 `tests/`가 `ax-task-queue.service`의 `ReadOnlyPaths`에 없다. 루트가 `ReadWritePaths`라서 그동안 큐가 조용히 쓸 수 있었다. `scripts`·`AGENTS.md` 때와 같은 부류다 |

## 수정 (`caf6763`)

- `test_mount_gate`: 기준 문자열을 현재 코드(`if not res.results:` .. `for ev in synth:`)로 바꿨다. 기준이 다시
  옮겨 가면 IndexError 대신 이름 붙은 검사 실패로 드러난다. 검사 세 개는 그대로 뒀다. 결과 51/51.
- `ax-task-queue.service`: `ReadOnlyPaths=/home/sim/ax-cluster/tests`와 주석을 추가했다. 서브 에이전트는
  설치하지 않았다. 그래서 `test_sandbox`는 「저장소 사본 == 실물」 검사(diff 4줄) 하나만 남기고 실패했다.
  설치 전에는 이것이 예상대로였다.

## 운영 (사용자 「통과하면 커밋하고 재기동해」)

1. 커밋 `caf6763`, push.
2. 진행 중 조각이 0건인지 확인했다(작업 파일 상태: verified 176 · failed 11 · cancelled 19).
3. `pkexec`로 `/etc/systemd/system/`에 설치(cmp 동일) · `daemon-reload`.
4. `ax-task-queue` 재기동 → `ExecMainStartTimestamp` 21:27:28. 실물 `ReadOnlyPaths`에 `tests`가 있는 것을 확인했다.
   8101은 토큰 잠금(401)으로 응답했다.
5. `test_sandbox` 36/36 · **전수 170파일 실패 0**(10-11 이후 처음) · 배달 3/3 OK.
6. #815에 노트를 남겼다. 상태는 「신규」 그대로 뒀다(남은 항목이 많다).

이제부터 전수에서 실패가 하나라도 나오면 그것이 곧 새 회귀다. 「기존 2개뿐」으로 거르던 판정은 필요 없어졌다.

## 남은 것

- #815: ① 동작 정합(작업 방식 결정) · ② mypy 오탐 측정 · ④ 층2 `[PSEUDO]` 이행 · ⑤ ⑦ 회귀 선택 보강 ·
  ⑥ 공식 목록 확대 · `logic.py` 재수출 판단 · `test_runner` 간헐 실패(원문 미확보). 순서는 사용자가 정한다.
- 이전 보고서의 남은 것은 그대로다: #825 줄 번호 대조 라이브(10-24) · #823 10-24 회차 · `.33` 실측 셋 ·
  #798 마지막 라이브 · `watch.exe` 훅.

### 이후 경과

- 같은 날 #815 ② mypy 오탐 측정 → `distribute register` 결함 둘 — [리포트 117](117-815-mypy-measurement-distribute-defects.md).
